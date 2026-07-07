from __future__ import annotations

import re
import sys
import json
from html import unescape
from html.parser import HTMLParser
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site_output"
FAQ_SCHEMA_DISABLED = {
    "comparisons/framer-vs-webflow/index.html",
    "vi/comparisons/framer-vs-webflow/index.html",
}
CONTENT_DRAFTS = ROOT / "data" / "content_drafts.csv"
CLICK_EVENTS = ROOT / "data" / "click_events.csv"
AFFILIATE_LINKS = ROOT / "data" / "affiliate_links.csv"
TRACK_CLICK_FUNCTION = ROOT / "netlify" / "functions" / "track-click.js"
VALID_DRAFT_STATUSES = {"Draft", "Pending Review", "Need Edit", "Approved", "Rejected", "Published"}
WEBSITE_DRAFT_TYPES = {"Review page", "Comparison page", "FAQ page", "Blog article", "Website article"}
PUBLIC_HTML_FORBIDDEN_MARKERS = (
    "Research package snapshot",
    "Content planning snapshot",
    "Affiliate placeholder fields",
    "{{",
    "}}",
)


class LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []
        self.titles = 0
        self.meta_descriptions = 0
        self.schemas = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = {key: value or "" for key, value in attrs}
        if tag == "a" and attrs_dict.get("href"):
            self.links.append(attrs_dict["href"])
        if tag == "title":
            self.titles += 1
        if tag == "meta" and attrs_dict.get("name") == "description":
            self.meta_descriptions += 1
        if tag == "script" and attrs_dict.get("type") == "application/ld+json":
            self.schemas += 1


def main() -> int:
    if not SITE.exists():
        print("site_output does not exist. Run python main.py first.")
        return 1

    errors: list[str] = []
    html_files = sorted(SITE.rglob("*.html"))
    for file in html_files:
        rel = file.relative_to(SITE).as_posix()
        text = file.read_text(encoding="utf-8", errors="ignore")
        parser = LinkParser()
        parser.feed(text)
        is_vi_page = rel.startswith("vi/")

        if "<title>" not in text:
            errors.append(f"{rel}: missing title")
        if 'name="description"' not in text:
            errors.append(f"{rel}: missing meta description")
        if not rel.startswith("go/") and "application/ld+json" not in text:
            errors.append(f"{rel}: missing schema")
        if "localhost" in text:
            errors.append(f"{rel}: contains localhost")
        if "yourdomain" in text:
            errors.append(f"{rel}: contains yourdomain")

        is_content_page = (
            not is_vi_page
            and (
                is_review(rel)
                or is_comparison(rel)
                or is_pricing(rel)
                or is_toplist(rel)
                or (rel.startswith("blog/") and rel != "blog/index.html")
            )
        )
        internal_links = [link for link in parser.links if link.startswith("/") and not link.startswith("//")]
        if not rel.startswith("go/") and len(set(normalize_internal_link(link) for link in internal_links if normalize_internal_link(link))) < 3:
            errors.append(f"{rel}: fewer than 3 internal links")
        current_url = "/" if rel == "index.html" else "/" + rel[: -len("index.html")]
        auto_links = re.findall(r"data-auto-internal-links=['\"]1['\"].*?</section>", text, flags=re.DOTALL)
        for block in auto_links:
            for link in re.findall(r"href=['\"]([^'\"]+)['\"]", block):
                if normalize_internal_link(link) == current_url:
                    errors.append(f"{rel}: self-link loop in related content block")
        if not is_vi_page and (is_comparison(rel) or is_pricing(rel) or is_toplist(rel)) and not has_schema_type(text, "BreadcrumbList"):
            errors.append(f"{rel}: missing BreadcrumbList schema")
        if not is_vi_page and is_pricing(rel):
            errors.extend(validate_pricing_page(rel, text))
        if is_content_page:
            if "FAQ" not in text and "<details" not in text:
                errors.append(f"{rel}: missing FAQ")
            if "Some links may be affiliate links" not in text and "Một số liên kết có thể là liên kết tiếp thị liên kết" not in text:
                errors.append(f"{rel}: missing affiliate disclosure")
            if (
                "Visit Official Website" not in text
                and "Read review" not in text
                and "Read " not in text
                and "Truy cập website chính thức" not in text
                and "Đọc đánh giá" not in text
                and "Đọc " not in text
                and "CTA" not in text
            ):
                errors.append(f"{rel}: missing CTA")
            if ("FAQ" in text or "<details" in text) and not has_schema_type(text, "FAQPage") and rel not in FAQ_SCHEMA_DISABLED:
                errors.append(f"{rel}: FAQ section present but FAQPage schema missing")
            for marker in PUBLIC_HTML_FORBIDDEN_MARKERS:
                if marker in text:
                    errors.append(f"{rel}: contains forbidden public HTML marker {marker!r}")
            errors.extend(validate_json_ld(rel, text))

        for link in parser.links:
            if not link.startswith("/") or link.startswith("//"):
                continue
            if link.startswith(("/assets/", "/rss.xml", "/sitemap.xml", "/robots.txt", "/llms.txt")):
                continue
            normalized = normalize_internal_link(link)
            if not normalized:
                continue
            target = SITE / normalized.strip("/")
            if link.endswith("/") or "." not in Path(link).name:
                target = target / "index.html"
            if not target.exists():
                errors.append(f"{rel}: broken internal link {link}")

    for required in ["sitemap.xml", "robots.txt", "rss.xml", "llms.txt"]:
        if not (SITE / required).exists():
            errors.append(f"missing {required}")
    errors.extend(validate_sitemap())
    errors.extend(validate_content_drafts())
    errors.extend(validate_tracking_files())
    errors.extend(validate_netlify_tracking_function())
    errors.extend(validate_tracking_routes(html_files))

    if errors:
        print("Site validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"Site validation passed. Checked {len(html_files)} HTML files.")
    return 0


def is_comparison(rel: str) -> bool:
    return (rel.startswith("comparisons/") or rel.startswith("compare/")) and rel.count("/") >= 2


def has_schema_type(text: str, schema_type: str) -> bool:
    return bool(
        re.search(
            rf'["\']@type["\']\s*:\s*["\']{re.escape(schema_type)}["\']',
            text,
            flags=re.I,
        )
    )


def is_review(rel: str) -> bool:
    static_prefixes = (
        "blog/",
        "category/",
        "hub/",
        "hubs/",
        "go/",
        "comparisons/",
        "reviews/",
        "about/",
        "about-author/",
        "author-profile/",
        "editorial-policy/",
        "how-we-review-tools/",
        "testing-methodology/",
        "privacy-policy/",
        "terms/",
        "contact/",
        "affiliate-disclosure/",
        "sitemap/",
        "media-kit/",
        "aeo-action-plan/",
        "pricing/",
    )
    return rel.endswith("/index.html") and "/" in rel and not rel.startswith(static_prefixes)


def is_pricing(rel: str) -> bool:
    return rel.endswith("-pricing/index.html") or (rel.startswith("pricing/") and rel.endswith("/index.html"))


def is_toplist(rel: str) -> bool:
    return rel.startswith("best-") and rel.endswith("/index.html")


def normalize_internal_link(link: str) -> str:
    if not link.startswith("/") or link.startswith("//"):
        return ""
    return link.split("#")[0].split("?")[0] or "/"


def validate_content_drafts() -> list[str]:
    errors: list[str] = []
    if not CONTENT_DRAFTS.exists():
        errors.append("data/content_drafts.csv does not exist")
        return errors
    try:
        df = pd.read_csv(CONTENT_DRAFTS).fillna("")
    except Exception as exc:
        return [f"data/content_drafts.csv cannot be read: {exc}"]
    required = {
        "draft_id",
        "created_at",
        "content_type",
        "target_channel",
        "title",
        "slug",
        "topic",
        "status",
        "draft_content",
        "target_url",
        "notes",
    }
    missing = required - set(df.columns)
    if missing:
        errors.append(f"data/content_drafts.csv missing columns: {', '.join(sorted(missing))}")
        return errors
    for _, row in df.iterrows():
        draft_id = str(row.get("draft_id", "")).strip() or "(missing draft_id)"
        status = str(row.get("status", "")).strip()
        if status not in VALID_DRAFT_STATUSES:
            errors.append(f"{draft_id}: invalid status {status}")
        if not str(row.get("title", "")).strip():
            errors.append(f"{draft_id}: empty title")
        if not str(row.get("draft_content", "")).strip():
            errors.append(f"{draft_id}: empty content")
        if status == "Approved" and str(row.get("content_type", "")).strip() in WEBSITE_DRAFT_TYPES and not str(row.get("slug", "")).strip():
            errors.append(f"{draft_id}: approved website draft missing slug")
        if status == "Published" and str(row.get("content_type", "")).strip() in WEBSITE_DRAFT_TYPES and not str(row.get("target_url", "")).strip():
            errors.append(f"{draft_id}: published website draft missing URL")
    return errors


def validate_json_ld(rel: str, text: str) -> list[str]:
    errors: list[str] = []
    for idx, match in enumerate(re.findall(r'<script type="application/ld\+json">(.*?)</script>', text, flags=re.DOTALL), start=1):
        try:
            json.loads(match)
        except Exception as exc:
            errors.append(f"{rel}: invalid JSON-LD block {idx}: {exc}")
    return errors


def validate_sitemap() -> list[str]:
    errors: list[str] = []
    sitemap = SITE / "sitemap.xml"
    if not sitemap.exists():
        return ["missing sitemap.xml"]
    text = sitemap.read_text(encoding="utf-8", errors="ignore")
    if "localhost" in text:
        errors.append("sitemap.xml contains localhost")
    if "yourdomain" in text:
        errors.append("sitemap.xml contains yourdomain")
    if "<loc>https://smileaireviewhub.com/</loc>" not in text:
        errors.append("sitemap.xml missing homepage")
    if "/comparisons/" not in text:
        errors.append("sitemap.xml missing comparison pages")
    if "/assets/" in text:
        errors.append("sitemap.xml contains asset URLs")
    if "/go/" in text:
        errors.append("sitemap.xml contains tracking /go/ URLs")
    return errors


def validate_tracking_files() -> list[str]:
    errors: list[str] = []
    click_required = {
        "timestamp",
        "session_id",
        "click_id",
        "tool_slug",
        "tool_name",
        "source_page",
        "source_page_type",
        "cta_label",
        "target_url",
        "referrer",
        "event_type",
        "page_load_seconds",
        "user_agent_hint",
        "is_suspicious",
        "suspicious_reason",
        "click_quality_score",
    }
    affiliate_required = {"tool_slug", "tool_name", "official_url", "affiliate_url", "affiliate_status", "notes"}
    if not CLICK_EVENTS.exists():
        errors.append("data/click_events.csv does not exist")
    else:
        try:
            df = pd.read_csv(CLICK_EVENTS)
            missing = click_required - set(df.columns)
            if missing:
                errors.append(f"data/click_events.csv missing columns: {', '.join(sorted(missing))}")
        except Exception as exc:
            errors.append(f"data/click_events.csv cannot be read: {exc}")
    if not AFFILIATE_LINKS.exists():
        errors.append("data/affiliate_links.csv does not exist")
    else:
        try:
            df = pd.read_csv(AFFILIATE_LINKS).fillna("")
            missing = affiliate_required - set(df.columns)
            if missing:
                errors.append(f"data/affiliate_links.csv missing columns: {', '.join(sorted(missing))}")
            valid = {"pending", "approved", "rejected", "official_only", "pending_approval"}
            if "affiliate_status" in df.columns:
                bad = sorted(set(str(value).strip() for value in df["affiliate_status"]) - valid - {""})
                if bad:
                    errors.append(f"data/affiliate_links.csv invalid affiliate_status: {', '.join(bad)}")
        except Exception as exc:
            errors.append(f"data/affiliate_links.csv cannot be read: {exc}")
    return errors


def validate_tracking_routes(html_files: list[Path]) -> list[str]:
    errors: list[str] = []
    if not AFFILIATE_LINKS.exists():
        return errors
    try:
        links = pd.read_csv(AFFILIATE_LINKS).fillna("")
    except Exception:
        return errors
    tracked_targets = []
    for _, row in links.iterrows():
        slug = str(row.get("tool_slug") or row.get("slug") or "").strip()
        if not slug:
            continue
        go_file = SITE / "go" / slug / "index.html"
        if not go_file.exists():
            errors.append(f"missing tracking route /go/{slug}/")
        else:
            go_text = go_file.read_text(encoding="utf-8", errors="ignore")
            if "aiip_session_id" not in go_text:
                errors.append(f"go/{slug}/index.html: missing anonymous session_id script")
            if "click_id" not in go_text or "click_quality_score" not in go_text:
                errors.append(f"go/{slug}/index.html: missing click quality script")
            if "/.netlify/functions/track-click" not in go_text:
                errors.append(f"go/{slug}/index.html: missing production tracking POST")
            if "catch(function()" not in go_text or "redirectAfterTracking" not in go_text or "Promise.race" not in go_text:
                errors.append(f"go/{slug}/index.html: redirect may not survive tracking failure")
            forbidden_tracking_patterns = ["document.cookie", "ip_address", "user_email", "email_address", "personal_data"]
            for pattern in forbidden_tracking_patterns:
                if pattern in go_text.lower():
                    errors.append(f"go/{slug}/index.html: tracking script may store personal data pattern {pattern}")
        for column in ["official_url", "affiliate_url"]:
            url = str(row.get(column, "")).strip()
            if url:
                tracked_targets.append((slug, url))
    for file in html_files:
        rel = file.relative_to(SITE).as_posix()
        if rel.startswith("go/"):
            continue
        text = file.read_text(encoding="utf-8", errors="ignore")
        for slug, url in tracked_targets:
            if f'href="{url}"' in text or f"href='{url}'" in text:
                errors.append(f"{rel}: direct outbound CTA should use /go/{slug}/ instead of {url}")
    return errors


def validate_netlify_tracking_function() -> list[str]:
    errors: list[str] = []
    if not TRACK_CLICK_FUNCTION.exists():
        return ["missing netlify/functions/track-click.js"]
    text = TRACK_CLICK_FUNCTION.read_text(encoding="utf-8", errors="ignore")
    for required in ["exports.handler", "click_id", "session_id", "click_quality_score", "console.log", "CLICK_WEBHOOK_URL", "click_webhook_failed"]:
        if required not in text:
            errors.append(f"netlify/functions/track-click.js missing {required}")
    if "missing_required_fields" not in text or "validateRequired" not in text:
        errors.append("netlify/functions/track-click.js missing required field validation")
    forbidden_patterns = ["x-forwarded-for", "client-ip", "ip_address", "user_email", "email_address", "personal_data"]
    lower = text.lower()
    for pattern in forbidden_patterns:
        if pattern in lower:
            errors.append(f"netlify/functions/track-click.js may store personal data pattern {pattern}")
    return errors


def validate_pricing_page(rel: str, text: str) -> list[str]:
    if rel.startswith("pricing/"):
        tool_slug = rel.removeprefix("pricing/").removesuffix("/index.html")
    else:
        slug = rel.removesuffix("/index.html")
        tool_slug = slug.removesuffix("-pricing")
    expected = expected_tool_name(tool_slug)
    errors: list[str] = []
    if not expected:
        return errors
    title = extract_tag(text, "title")
    h1 = extract_tag(text, "h1")
    meta = extract_meta_description(text)
    cta_text = " ".join(re.findall(r"<a[^>]*>(.*?)</a>", text, flags=re.DOTALL))
    breadcrumb_blocks = re.findall(r'<script type="application/ld\+json">(.*?)</script>', text, flags=re.DOTALL)
    breadcrumb_text = " ".join(block for block in breadcrumb_blocks if '"@type": "BreadcrumbList"' in block)
    checks = {
        "title": title,
        "h1": h1,
        "meta description": meta,
        "CTA text": cta_text,
        "breadcrumb": breadcrumb_text,
    }
    for label, value in checks.items():
        clean_value = re.sub(r"<.*?>", "", unescape(value))
        if expected not in clean_value:
            errors.append(f"{rel}: pricing {label} missing exact tool name {expected}")
    common_bad = bad_tool_name(expected)
    if common_bad and common_bad in text:
        errors.append(f"{rel}: contains truncated tool name {common_bad}; expected {expected}")
    return errors


def expected_tool_name(tool_slug: str) -> str:
    scores = ROOT / "data" / "offer_scores.csv"
    if scores.exists():
        try:
            df = pd.read_csv(scores).fillna("")
            for _, row in df.iterrows():
                if str(row.get("offer_id", "")).strip() == tool_slug:
                    return str(row.get("brand_name", "")).strip()
        except Exception:
            pass
    fallback = {
        "cursor": "Cursor",
        "github-copilot": "GitHub Copilot",
        "semrush": "Semrush",
        "surfer-seo": "Surfer SEO",
        "jasper": "Jasper",
        "elevenlabs": "ElevenLabs",
        "make": "Make",
        "zapier": "Zapier",
        "canva": "Canva",
        "activecampaign": "ActiveCampaign",
        "mailchimp": "Mailchimp",
        "pictory": "Pictory",
        "grammarly": "Grammarly",
    }
    return fallback.get(tool_slug, "")


def bad_tool_name(expected: str) -> str:
    if expected == "Cursor":
        return "Curl"
    return ""


def extract_tag(text: str, tag: str) -> str:
    match = re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", text, flags=re.DOTALL | re.IGNORECASE)
    return match.group(1) if match else ""


def extract_meta_description(text: str) -> str:
    match = re.search(r'<meta\s+name=["\']description["\']\s+content=["\']([^"\']+)["\']', text, flags=re.IGNORECASE)
    return match.group(1) if match else ""


if __name__ == "__main__":
    sys.exit(main())
