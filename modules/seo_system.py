from __future__ import annotations

import re
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import pandas as pd

from config import settings


TOPIC_GROUPS = {
    "AI coding tools": {"cursor", "codex", "copilot", "windsurf", "coding", "code", "debugging", "repo"},
    "AI SEO tools": {"seo", "semrush", "ahrefs", "surfer"},
    "AI writing tools": {"writing", "writer", "jasper", "copy", "notion", "content"},
    "AI automation tools": {"automation", "make", "zapier", "workflow"},
    "pricing": {"pricing", "price", "cost", "plan"},
    "alternatives": {"alternative", "alternatives"},
    "comparisons": {"comparison", "compare", "vs"},
}

GENERIC_PHRASES = [
    "may be useful",
    "can help",
    "this tool is",
    "in today's digital world",
    "game changing",
    "ultimate",
    "best tool",
]

EXPERIENCE_TERMS = {"i use", "i tested", "my workflow", "builder note", "real workflow", "what failed", "experience"}
USE_CASE_TERMS = {"best for", "use case", "workflow", "team", "solo", "startup", "agency", "debugging"}
OPINION_TERMS = {"i think", "i prefer", "i would", "tradeoff", "risk", "not ideal", "avoid", "recommend"}
COMPARISON_TERMS = {" vs ", "compare", "comparison", "alternative", "better than", "tradeoff"}


@dataclass
class PageAudit:
    path: Path
    url: str
    title: str
    meta_description: str
    h1_count: int
    internal_links: list[str]
    related_posts_count: int
    canonical: str
    schema_types: list[str]
    text: str


class SEOParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.in_title = False
        self.in_h1 = False
        self.title_parts: list[str] = []
        self.h1_count = 0
        self.meta_description = ""
        self.canonical = ""
        self.links: list[str] = []
        self.schema_texts: list[str] = []
        self._script_type = ""
        self._script_parts: list[str] = []
        self.text_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = {key.lower(): value or "" for key, value in attrs}
        if tag == "title":
            self.in_title = True
        elif tag == "h1":
            self.in_h1 = True
            self.h1_count += 1
        elif tag == "meta" and attrs_dict.get("name", "").lower() == "description":
            self.meta_description = attrs_dict.get("content", "")
        elif tag == "link" and attrs_dict.get("rel", "").lower() == "canonical":
            self.canonical = attrs_dict.get("href", "")
        elif tag == "a" and attrs_dict.get("href"):
            self.links.append(attrs_dict["href"])
        elif tag == "script":
            self._script_type = attrs_dict.get("type", "")
            self._script_parts = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self.in_title = False
        elif tag == "h1":
            self.in_h1 = False
        elif tag == "script":
            if self._script_type == "application/ld+json":
                self.schema_texts.append("".join(self._script_parts))
            self._script_type = ""
            self._script_parts = []

    def handle_data(self, data: str) -> None:
        if self.in_title:
            self.title_parts.append(data)
        if self._script_type == "application/ld+json":
            self._script_parts.append(data)
        if data.strip():
            self.text_parts.append(data.strip())


def run_seo_system() -> dict[str, int]:
    pages = audit_pages()
    topical = build_topical_map(pages)
    seo_audit = build_seo_audit(pages)
    tracking = build_link_tracking_map()
    quality = build_content_quality_report(pages)
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    topical.to_csv(settings.data_dir / "topical_map.csv", index=False)
    seo_audit.to_csv(settings.data_dir / "seo_audit_report.csv", index=False)
    tracking.to_csv(settings.data_dir / "link_tracking_map.csv", index=False)
    quality.to_csv(settings.data_dir / "content_quality_report.csv", index=False)
    return {
        "pages": len(pages),
        "topical_rows": len(topical),
        "seo_audit_rows": len(seo_audit),
        "tracking_rows": len(tracking),
        "quality_rows": len(quality),
    }


def audit_pages() -> list[PageAudit]:
    output = settings.site_output_dir
    pages: list[PageAudit] = []
    if not output.exists():
        return pages
    for file in sorted(output.rglob("index.html")):
        rel = file.relative_to(output).as_posix()
        if rel.startswith(("assets/", "go/")):
            continue
        html = file.read_text(encoding="utf-8", errors="ignore")
        parser = SEOParser()
        parser.feed(html)
        url = "/" if rel == "index.html" else "/" + rel[: -len("index.html")]
        pages.append(
            PageAudit(
                path=file,
                url=url,
                title=" ".join(parser.title_parts).strip(),
                meta_description=parser.meta_description.strip(),
                h1_count=parser.h1_count,
                internal_links=sorted({normalize_internal_link(link) for link in parser.links if normalize_internal_link(link)}),
                related_posts_count=related_count(html),
                canonical=parser.canonical.strip(),
                schema_types=schema_types(parser.schema_texts),
                text=" ".join(parser.text_parts),
            )
        )
    return pages


def build_topical_map(pages: list[PageAudit]) -> pd.DataFrame:
    rows = []
    for page in pages:
        slug_text = f"{page.url} {page.title} {page.meta_description}".lower()
        groups = detect_topic_groups(slug_text)
        page_type = classify_page(page.url)
        for group in groups:
            rows.append(
                {
                    "topic_group": group,
                    "page_url": full_url(page.url),
                    "page_type": page_type,
                    "title": page.title,
                    "internal_links_count": len(page.internal_links),
                    "related_posts_count": page.related_posts_count,
                    "canonical": page.canonical,
                }
            )
    return pd.DataFrame(rows)


def build_seo_audit(pages: list[PageAudit]) -> pd.DataFrame:
    rows = []
    for page in pages:
        warnings = []
        if not 35 <= len(page.title) <= 70:
            warnings.append("title_length_check")
        if not 90 <= len(page.meta_description) <= 170:
            warnings.append("meta_description_length_check")
        if page.h1_count != 1:
            warnings.append("h1_count_not_1")
        if len(page.internal_links) < 3:
            warnings.append("few_internal_links")
        if page.related_posts_count < 4 and classify_page(page.url) not in {"home", "static"}:
            warnings.append("few_related_posts")
        if not canonical_ok(page):
            warnings.append("canonical_check")
        if "BreadcrumbList" not in page.schema_types and classify_page(page.url) not in {"home", "static"}:
            warnings.append("missing_breadcrumb_schema")
        if has_faq(page.text) and "FAQPage" not in page.schema_types:
            warnings.append("missing_faq_schema")
        if "Review" in page.schema_types and not has_rating_data(page.text):
            warnings.append("review_schema_without_rating_data")
        rows.append(
            {
                "page_url": full_url(page.url),
                "title_length": len(page.title),
                "meta_description_length": len(page.meta_description),
                "h1_count": page.h1_count,
                "internal_links_count": len(page.internal_links),
                "related_posts_count": page.related_posts_count,
                "canonical_ok": str(canonical_ok(page)).lower(),
                "schema_types": "|".join(page.schema_types),
                "warnings": "|".join(warnings),
            }
        )
    return pd.DataFrame(rows)


def build_link_tracking_map() -> pd.DataFrame:
    path = settings.data_dir / "social_calendar.csv"
    if not path.exists():
        return pd.DataFrame(columns=["post_id", "platform", "target_url", "tracked_url", "topic", "campaign", "content_angle"])
    calendar = pd.read_csv(path).fillna("")
    rows = []
    for _, row in calendar.iterrows():
        post_id = str(row.get("id", "")).strip()
        platform = str(row.get("platform", "")).strip()
        target_url = str(row.get("short_url", "") or row.get("target_url", "")).strip()
        topic = str(row.get("topic", "") or row.get("post_title", "")).strip()
        angle = str(row.get("angle", "") or row.get("content_style", "")).strip()
        campaign = campaign_name(topic, angle)
        tracked_url = with_utm(target_url, platform, campaign, post_id)
        rows.append(
            {
                "post_id": post_id,
                "platform": platform,
                "target_url": target_url,
                "tracked_url": tracked_url,
                "topic": topic,
                "campaign": campaign,
                "content_angle": angle,
                "has_utm": str(has_required_utm(tracked_url)).lower(),
            }
        )
    df = pd.DataFrame(rows)
    if not calendar.empty:
        updated = calendar.copy()
        if "tracked_url" not in updated.columns:
            updated["tracked_url"] = ""
        tracked_map = df.set_index("post_id")["tracked_url"].to_dict()
        updated["tracked_url"] = updated["id"].astype(str).map(tracked_map).fillna(updated["tracked_url"])
        updated.to_csv(path, index=False, encoding="utf-8-sig")
    return df


def build_content_quality_report(pages: list[PageAudit]) -> pd.DataFrame:
    rows = []
    for page in pages:
        page_type = classify_page(page.url)
        if page_type in {"home", "static"}:
            continue
        text = page.text.lower()
        generic_score = min(100, sum(text.count(item) for item in GENERIC_PHRASES) * 18)
        has_experience = any(term in text for term in EXPERIENCE_TERMS)
        has_use_case = any(term in text for term in USE_CASE_TERMS)
        has_opinion = any(term in text for term in OPINION_TERMS)
        has_comparison = any(term in text for term in COMPARISON_TERMS)
        missing = []
        if generic_score >= 45:
            missing.append("too_generic")
        if not has_experience:
            missing.append("add_experience")
        if not has_use_case:
            missing.append("add_use_case")
        if not has_opinion:
            missing.append("add_opinion")
        if not has_comparison and page_type in {"review", "comparison", "toplist", "pricing"}:
            missing.append("add_comparison")
        if not has_cta(page.text):
            missing.append("add_cta")
        rows.append(
            {
                "page_url": full_url(page.url),
                "topic": "|".join(detect_topic_groups(f"{page.url} {page.title}".lower())),
                "generic_score": generic_score,
                "has_experience": str(has_experience).lower(),
                "has_use_case": str(has_use_case).lower(),
                "has_opinion": str(has_opinion).lower(),
                "has_comparison": str(has_comparison).lower(),
                "recommendation": "ok" if not missing else "|".join(missing),
            }
        )
    return pd.DataFrame(rows)


def normalize_internal_link(link: str) -> str:
    value = str(link or "").split("#", 1)[0].split("?", 1)[0]
    if not value.startswith("/") or value.startswith("//"):
        return ""
    if value.startswith(("/assets/", "/go/", "/rss.xml", "/sitemap.xml", "/robots.txt", "/llms.txt")):
        return ""
    return value.rstrip("/") + "/" if value != "/" else "/"


def related_count(html: str) -> int:
    blocks = re.findall(r"data-auto-internal-links=['\"]1['\"].*?</section>", html, flags=re.DOTALL)
    if blocks:
        return sum(block.count("<a ") for block in blocks)
    lowered = html.lower()
    if "related" not in lowered:
        return 0
    return len(re.findall(r"<a\s+[^>]*href=", html))


def schema_types(schema_texts: list[str]) -> list[str]:
    found: set[str] = set()
    for text in schema_texts:
        for match in re.findall(r'"@type"\s*:\s*"([^"]+)"', text):
            found.add(match)
    return sorted(found)


def classify_page(url: str) -> str:
    if url == "/":
        return "home"
    if url.startswith("/review/") or re.search(r"/[^/]+/$", url) and "review" in url:
        return "review"
    if url.startswith(("/compare/", "/comparisons/")):
        return "comparison"
    if url.startswith("/pricing/") or url.rstrip("/").endswith("-pricing"):
        return "pricing"
    if url.startswith("/category/"):
        return "category"
    if url.startswith("/hub/"):
        return "hub"
    if url.startswith("/blog/"):
        return "blog"
    if url.rstrip("/").split("/")[-1].startswith("best-"):
        return "toplist"
    return "static"


def detect_topic_groups(text: str) -> list[str]:
    groups = []
    tokens = set(re.findall(r"[a-z0-9]+", text.lower()))
    for group, terms in TOPIC_GROUPS.items():
        if tokens & terms or any(term in text for term in terms if " " in term):
            groups.append(group)
    return groups or ["general"]


def canonical_ok(page: PageAudit) -> bool:
    return page.canonical.rstrip("/") == full_url(page.url).rstrip("/")


def full_url(path: str) -> str:
    base = (settings.base_site_url or settings.site_domain or "https://review.mssmileenglish.com").rstrip("/")
    return base + (path if path.startswith("/") else f"/{path}")


def has_faq(text: str) -> bool:
    return "faq" in text.lower() or "frequently asked" in text.lower()


def has_rating_data(text: str) -> bool:
    lowered = text.lower()
    return "rating" in lowered or "score" in lowered or "overall" in lowered


def has_cta(text: str) -> bool:
    lowered = text.lower()
    return any(item in lowered for item in ["visit official", "read review", "see pricing", "try ", "compare", "read the"])


def campaign_name(topic: str, angle: str) -> str:
    raw = f"{topic}-{angle}".strip("-") or "affiliate-content"
    return slugify(raw)[:80]


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(value).lower()).strip("-")
    return slug or "content"


def with_utm(url: str, platform: str, campaign: str, post_id: str) -> str:
    if not url:
        return ""
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    source = platform_source(platform)
    query.setdefault("utm_source", [source])
    query.setdefault("utm_medium", ["social"])
    query.setdefault("utm_campaign", [campaign])
    query.setdefault("utm_content", [slugify(post_id)])
    encoded = urlencode({key: values[-1] for key, values in query.items()})
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, encoded, parsed.fragment))


def platform_source(platform: str) -> str:
    value = str(platform).strip().lower()
    if value in {"x/twitter", "twitter", "x"}:
        return "twitter"
    return slugify(value)


def has_required_utm(url: str) -> bool:
    query = parse_qs(urlparse(str(url)).query)
    return all(key in query for key in ["utm_source", "utm_medium", "utm_campaign", "utm_content"])
