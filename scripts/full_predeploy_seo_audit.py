from __future__ import annotations

import csv
import html
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urlparse
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site_output"
DATA = ROOT / "data"
BASE = "https://smileaireviewhub.com"
REPORT_JSON = DATA / "final_seo_technical_audit.json"
REPORT_CSV = DATA / "final_seo_technical_issues.csv"
REPORT_TXT = DATA / "final_seo_technical_summary.txt"
SCHEMA_RE = re.compile(
    r"<script\b[^>]*type=['\"]application/ld\+json['\"][^>]*>(.*?)</script>",
    flags=re.I | re.S,
)


def main() -> int:
    pages = discover_pages()
    sitemap = read_sitemap()
    review_urls = discover_review_urls(pages)
    issues: list[dict[str, str]] = []
    title_map: dict[str, list[str]] = defaultdict(list)
    description_map: dict[str, list[str]] = defaultdict(list)
    structured_types: Counter[str] = Counter()
    internal_links_total = 0
    images_total = 0
    missing_alt = 0
    missing_lazy = 0
    broken_links: set[tuple[str, str]] = set()
    indexable_urls: set[str] = set()
    non_indexable_urls: set[str] = set()

    for url, page in pages.items():
        source = page.read_text(encoding="utf-8", errors="ignore")
        noindex = "noindex" in robots(source)
        redirect = has_refresh(source)
        indexable = not noindex and not redirect and not url.startswith(f"{BASE}/go/")
        (indexable_urls if indexable else non_indexable_urls).add(url)

        title = extract(source, r"<title\b[^>]*>(.*?)</title>")
        description = meta_content(source, "name", "description")
        canonical_values = re.findall(
            r"<link\b(?=[^>]*rel=['\"]canonical['\"])(?=[^>]*href=['\"]([^'\"]+)['\"])[^>]*>",
            source,
            flags=re.I,
        )
        if not title:
            add(issues, "error", url, "missing_title")
        elif indexable:
            title_map[clean_text(title).lower()].append(url)
        if not description:
            add(issues, "error", url, "missing_meta_description")
        elif indexable:
            description_map[clean_text(description).lower()].append(url)
        if len(canonical_values) != 1:
            add(issues, "error", url, "canonical_count", str(len(canonical_values)))
        elif canonical_values[0] != url:
            add(issues, "error", url, "canonical_mismatch", canonical_values[0])

        if indexable and url not in sitemap:
            add(issues, "error", url, "indexable_page_missing_from_sitemap")
        if not indexable and url in sitemap:
            add(issues, "error", url, "non_indexable_page_in_sitemap")

        if indexable:
            validate_hreflang(source, url, pages, issues)
            validate_social_meta(source, url, issues)
        payloads = validate_schema(source, url, issues)
        for payload in payloads:
            schema_type = payload.get("@type")
            if isinstance(schema_type, str):
                structured_types[schema_type] += 1
        if indexable and url in review_urls:
            require_types(payloads, url, issues, ("Article", "BreadcrumbList", "SoftwareApplication", "Review"))
        if indexable and page_kind(url) == "comparison":
            require_types(payloads, url, issues, ("Article", "BreadcrumbList", "ItemList"))
        validate_faq_visible(source, payloads, url, issues)
        if indexable:
            validate_video(source, payloads, url, issues)

        links = re.findall(r"<a\b[^>]*href=['\"]([^'\"]+)['\"]", source, flags=re.I)
        internal = [normalize_internal_link(link) for link in links]
        internal = [link for link in internal if link]
        internal_links_total += len(internal)
        for link in internal:
            if link.startswith("/go/"):
                continue
            target_url = BASE + link
            if target_url not in pages and not asset_exists(link):
                broken_links.add((url, link))
        if indexable:
            validate_link_intent(url, internal, issues, review_urls)

        for tag in re.findall(r"<img\b[^>]*>", source, flags=re.I):
            images_total += 1
            if not re.search(r"\balt\s*=", tag, flags=re.I):
                missing_alt += 1
                add(issues, "warning", url, "image_missing_alt", tag[:160])
            if not re.search(r"\bloading=['\"](?:lazy|eager)['\"]", tag, flags=re.I) and not re.search(
                r"\bfetchpriority=['\"]high['\"]", tag, flags=re.I
            ):
                missing_lazy += 1
                add(issues, "warning", url, "image_missing_lazy_loading", tag[:160])

    for title, urls in title_map.items():
        if title and len(urls) > 1:
            add(issues, "warning", urls[0], "duplicate_title", " | ".join(urls))
    for description, urls in description_map.items():
        if description and len(urls) > 1:
            add(issues, "warning", urls[0], "duplicate_meta_description", " | ".join(urls))
    for source, link in sorted(broken_links):
        add(issues, "error", source, "broken_internal_link", link)
    validate_sitemap(sitemap, pages, indexable_urls, issues)
    validate_robots(issues)

    errors = sum(item["severity"] == "error" for item in issues)
    warnings = sum(item["severity"] == "warning" for item in issues)
    score = max(0, 100 - min(75, errors * 4) - min(15, warnings * 0.03))
    payload = {
        "deployment_readiness_score": round(score, 1),
        "summary": {
            "total_pages": len(pages),
            "indexable_pages": len(indexable_urls),
            "non_indexable_pages": len(non_indexable_urls),
            "sitemap_urls": len(sitemap),
            "structured_data": dict(structured_types),
            "internal_links": internal_links_total,
            "broken_links": len(broken_links),
            "canonical_issues": sum("canonical" in item["issue"] for item in issues),
            "duplicate_metadata": sum(item["issue"].startswith("duplicate_") for item in issues),
            "missing_metadata": sum(
                item["issue"] in {"missing_title", "missing_meta_description", "missing_open_graph", "missing_twitter_card"}
                for item in issues
            ),
            "images": images_total,
            "images_missing_alt": missing_alt,
            "images_missing_lazy_loading": missing_lazy,
            "errors": errors,
            "warnings": warnings,
        },
        "remaining_warnings": [
            "HTTP status is validated from static publish targets before deployment; verify live HTTP 200 after deployment.",
            "Core Web Vitals require live field or Lighthouse data; this audit checks static performance signals only.",
        ],
        "issues": issues,
    }
    DATA.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    REPORT_TXT.write_text(summary_text(payload), encoding="utf-8")
    with REPORT_CSV.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["severity", "url", "issue", "detail"])
        writer.writeheader()
        writer.writerows(issues)
    print(summary_text(payload))
    return 1 if errors else 0


def discover_pages() -> dict[str, Path]:
    pages: dict[str, Path] = {}
    for page in SITE.rglob("index.html"):
        rel = page.relative_to(SITE).as_posix()
        url = f"{BASE}/" if rel == "index.html" else f"{BASE}/" + rel[: -len("index.html")]
        pages[url] = page
    return pages


def read_sitemap() -> set[str]:
    root = ET.fromstring((SITE / "sitemap.xml").read_text(encoding="utf-8", errors="ignore"))
    return {node.text.strip() for node in root.findall(".//{http://www.sitemaps.org/schemas/sitemap/0.9}loc") if node.text}


def discover_review_urls(pages: dict[str, Path]) -> set[str]:
    result: set[str] = set()
    for url, page in pages.items():
        source = page.read_text(encoding="utf-8", errors="ignore")
        if any(payload.get("@type") == "Review" for payload in validate_schema(source, url, [])):
            result.add(url)
    return result


def validate_sitemap(sitemap: set[str], pages: dict[str, Path], indexable: set[str], issues: list[dict[str, str]]) -> None:
    for url in sitemap:
        parsed = urlparse(url)
        if parsed.netloc != "smileaireviewhub.com" or parsed.query or parsed.fragment:
            add(issues, "error", url, "invalid_sitemap_url")
        if "/go/" in parsed.path:
            add(issues, "error", url, "affiliate_redirect_in_sitemap")
        if url not in pages:
            add(issues, "error", url, "sitemap_url_missing_public_html")
        if url not in indexable:
            add(issues, "error", url, "sitemap_url_not_indexable")


def validate_robots(issues: list[dict[str, str]]) -> None:
    path = SITE / "robots.txt"
    if not path.exists():
        add(issues, "error", f"{BASE}/robots.txt", "missing_robots_txt")
        return
    source = path.read_text(encoding="utf-8", errors="ignore")
    if f"Sitemap: {BASE}/sitemap.xml" not in source:
        add(issues, "error", f"{BASE}/robots.txt", "missing_sitemap_declaration")
    for bot in ("Googlebot", "Bingbot", "OAI-SearchBot", "ChatGPT-User", "PerplexityBot"):
        block = re.search(rf"User-agent:\s*{re.escape(bot)}(.*?)(?=User-agent:|\Z)", source, flags=re.I | re.S)
        if block and re.search(r"Disallow:\s*/\s*$", block.group(1), flags=re.I | re.M):
            add(issues, "error", f"{BASE}/robots.txt", "crawler_blocked", bot)


def validate_hreflang(source: str, url: str, pages: dict[str, Path], issues: list[dict[str, str]]) -> None:
    values = dict(
        re.findall(
            r"<link\b(?=[^>]*rel=['\"]alternate['\"])(?=[^>]*hreflang=['\"]([^'\"]+)['\"])(?=[^>]*href=['\"]([^'\"]+)['\"])[^>]*>",
            source,
            flags=re.I,
        )
    )
    required = ("vi", "x-default") if "/vi/" in url and "en" not in values else ("en", "vi", "x-default")
    for lang in required:
        if lang not in values:
            add(issues, "error", url, "missing_hreflang", lang)
        elif values[lang] not in pages:
            add(issues, "error", url, "hreflang_target_missing", values[lang])
    expected_self = values.get("vi") if "/vi/" in url else values.get("en")
    if expected_self and expected_self != url:
        add(issues, "error", url, "hreflang_self_mismatch", expected_self)


def validate_social_meta(source: str, url: str, issues: list[dict[str, str]]) -> None:
    for prop in ("og:title", "og:description", "og:url", "og:type", "og:image"):
        if not meta_content(source, "property", prop):
            add(issues, "error", url, "missing_open_graph", prop)
    for name in ("twitter:card", "twitter:title", "twitter:description", "twitter:image"):
        if not meta_content(source, "name", name):
            add(issues, "error", url, "missing_twitter_card", name)
    if meta_content(source, "property", "og:url") != url:
        add(issues, "error", url, "og_url_mismatch", meta_content(source, "property", "og:url"))


def validate_schema(source: str, url: str, issues: list[dict[str, str]]) -> list[dict[str, object]]:
    payloads: list[dict[str, object]] = []
    for raw in SCHEMA_RE.findall(source):
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            add(issues, "error", url, "invalid_json_ld", str(exc))
            continue
        if isinstance(payload, dict):
            payloads.append(payload)
    types = [str(payload.get("@type", "")) for payload in payloads]
    for schema_type, count in Counter(types).items():
        if schema_type and count > 1:
            add(issues, "error", url, "duplicate_schema_type", schema_type)
    return payloads


def validate_faq_visible(source: str, payloads: list[dict[str, object]], url: str, issues: list[dict[str, str]]) -> None:
    visible = {
        clean_text(item)
        for item in re.findall(r"<summary\b[^>]*>(.*?)</summary>", source, flags=re.I | re.S)
        if clean_text(item)
    }
    schemas = [payload for payload in payloads if payload.get("@type") == "FAQPage"]
    if schemas and not visible:
        add(issues, "error", url, "faq_schema_without_visible_faq")
    for schema in schemas:
        for entity in schema.get("mainEntity", []):
            if isinstance(entity, dict) and clean_text(str(entity.get("name", ""))) not in visible:
                add(issues, "error", url, "faq_schema_question_not_visible", str(entity.get("name", "")))


def validate_video(source: str, payloads: list[dict[str, object]], url: str, issues: list[dict[str, str]]) -> None:
    has_youtube = bool(re.search(r"(?:youtube\.com/(?:embed/|watch\?v=)|youtu\.be/)", source, flags=re.I))
    has_schema = any(payload.get("@type") == "VideoObject" for payload in payloads)
    if has_youtube and not has_schema:
        add(issues, "error", url, "youtube_video_missing_videoobject")
    if has_schema and not has_youtube:
        add(issues, "error", url, "videoobject_without_real_youtube_video")


def validate_link_intent(
    url: str,
    links: list[str],
    issues: list[dict[str, str]],
    review_urls: set[str],
) -> None:
    kind = page_kind(url)
    links_to_review = any(BASE + link in review_urls for link in links)
    if url in review_urls and not links_to_review:
        add(issues, "error", url, "review_missing_related_review_link")
    if kind == "comparison" and not links_to_review:
        add(issues, "error", url, "comparison_missing_review_link")


def page_kind(url: str) -> str:
    path = urlparse(url).path
    clean = path[3:] if path.startswith("/vi/") else path
    if (clean.startswith("/review/") or clean.startswith("/reviews/")) and clean not in {"/review/", "/reviews/"}:
        return "review"
    if (clean.startswith("/compare/") or clean.startswith("/comparisons/")) and clean not in {"/compare/", "/comparisons/"}:
        return "comparison"
    return "other"


def require_types(payloads: list[dict[str, object]], url: str, issues: list[dict[str, str]], required: tuple[str, ...]) -> None:
    types = {payload.get("@type") for payload in payloads}
    for schema_type in required:
        if schema_type not in types:
            add(issues, "error", url, "missing_required_schema", schema_type)


def normalize_internal_link(link: str) -> str:
    parsed = urlparse(html.unescape(link))
    if parsed.scheme or parsed.netloc or not parsed.path.startswith("/"):
        return ""
    path = parsed.path
    if path.startswith(("/assets/", "/downloads/")) or "." in Path(path).name:
        return path
    return path if path.endswith("/") else path + "/"


def asset_exists(link: str) -> bool:
    return (SITE / link.lstrip("/")).exists()


def robots(source: str) -> str:
    return meta_content(source, "name", "robots").lower()


def has_refresh(source: str) -> bool:
    return bool(re.search(r"<meta\b[^>]*http-equiv=['\"]?refresh", source, flags=re.I))


def meta_content(source: str, attribute: str, value: str) -> str:
    return extract(
        source,
        rf"<meta\b(?=[^>]*{re.escape(attribute)}=['\"]{re.escape(value)}['\"])(?=[^>]*content=['\"]([^'\"]*)['\"])[^>]*>",
    )


def extract(source: str, pattern: str) -> str:
    match = re.search(pattern, source, flags=re.I | re.S)
    return html.unescape(match.group(1).strip()) if match else ""


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html.unescape(value or ""))).strip()


def add(issues: list[dict[str, str]], severity: str, url: str, issue: str, detail: str = "") -> None:
    issues.append({"severity": severity, "url": url, "issue": issue, "detail": detail})


def summary_text(payload: dict[str, object]) -> str:
    summary = payload["summary"]
    lines = [
        "Final SEO Technical Audit",
        f"Deployment readiness score: {payload['deployment_readiness_score']}/100",
        f"Total pages: {summary['total_pages']}",
        f"Indexable pages: {summary['indexable_pages']}",
        f"Non-indexable pages: {summary['non_indexable_pages']}",
        f"Sitemap URLs: {summary['sitemap_urls']}",
        f"Internal links: {summary['internal_links']}",
        f"Broken links: {summary['broken_links']}",
        f"Canonical issues: {summary['canonical_issues']}",
        f"Duplicate metadata: {summary['duplicate_metadata']}",
        f"Missing metadata: {summary['missing_metadata']}",
        f"Images missing alt: {summary['images_missing_alt']}",
        f"Images missing lazy loading: {summary['images_missing_lazy_loading']}",
        f"Errors: {summary['errors']}",
        f"Warnings: {summary['warnings']}",
        "Structured data: " + json.dumps(summary["structured_data"], ensure_ascii=False, sort_keys=True),
        "Remaining warnings:",
        *[f"- {warning}" for warning in payload["remaining_warnings"]],
        f"JSON report: {REPORT_JSON}",
        f"CSV issues: {REPORT_CSV}",
    ]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
