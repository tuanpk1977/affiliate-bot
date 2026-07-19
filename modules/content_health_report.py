from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse

from modules.public_content_hub import classify_category, classify_content_type


TRUST_ROUTES = (
    "/about/",
    "/editorial-policy/",
    "/how-we-review/",
    "/affiliate-disclosure/",
    "/contact/",
    "/privacy-policy/",
    "/terms/",
)
HOMEPAGE_SECTIONS = (
    "Featured Reviews",
    "Best AI Tools",
    "Latest Comparisons",
    "Practical Tutorials",
    "Buying Guides",
    "Recently Published",
)
NON_ARTICLE_ROOTS = {
    "about",
    "about-author",
    "affiliate-disclosure",
    "author-profile",
    "blog",
    "categories",
    "comparisons",
    "contact",
    "editorial-policy",
    "how-we-review",
    "how-we-review-tools",
    "hubs",
    "media-kit",
    "pricing",
    "privacy",
    "privacy-policy",
    "reviews",
    "sitemap",
    "terms",
    "terms-of-service",
    "testing-methodology",
}
INTERNAL_ONLY_ROOTS = {
    "admin",
    "dashboard",
    "draft",
    "preview",
    "report",
    "review",
    "upload",
}


@dataclass
class ParsedPage:
    path: Path
    route: str
    title: str = ""
    description: str = ""
    canonical: str = ""
    headings: list[str] = field(default_factory=list)
    links: list[str] = field(default_factory=list)
    og_names: set[str] = field(default_factory=set)
    schemas: list[dict] = field(default_factory=list)
    text: list[str] = field(default_factory=list)
    classes: set[str] = field(default_factory=set)

    @property
    def words(self) -> int:
        return len(re.findall(r"\b[\w'-]+\b", " ".join(self.text)))


class _AuditParser(HTMLParser):
    def __init__(self, path: Path, route: str) -> None:
        super().__init__(convert_charrefs=True)
        self.page = ParsedPage(path=path, route=route)
        self._capture = ""
        self._json_ld: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key.lower(): value or "" for key, value in attrs}
        lower = tag.lower()
        if lower == "title":
            self._capture = "title"
        elif lower in {"h1", "h2", "h3"}:
            self._capture = "heading"
        elif lower == "script" and values.get("type", "").lower() == "application/ld+json":
            self._capture = "jsonld"
            self._json_ld = []
        elif lower not in {"style", "script"}:
            self._capture = "text"

        if lower == "meta":
            name = (values.get("name") or values.get("property") or "").lower()
            if name == "description":
                self.page.description = values.get("content", "").strip()
            if name.startswith("og:"):
                self.page.og_names.add(name)
        elif lower == "link" and "canonical" in values.get("rel", "").lower():
            self.page.canonical = values.get("href", "").strip()
        elif lower == "a":
            self.page.links.append(values.get("href", "").strip())
        for class_name in values.get("class", "").split():
            self.page.classes.add(class_name.lower())

    def handle_endtag(self, tag: str) -> None:
        lower = tag.lower()
        if lower == "script" and self._capture == "jsonld":
            raw = "".join(self._json_ld).strip()
            try:
                value = json.loads(raw)
                if isinstance(value, dict):
                    self.page.schemas.append(value)
                elif isinstance(value, list):
                    self.page.schemas.extend(item for item in value if isinstance(item, dict))
            except json.JSONDecodeError:
                self.page.schemas.append({"@type": "INVALID_JSON_LD"})
        if lower in {"title", "h1", "h2", "h3", "script", "p", "li", "main", "section"}:
            self._capture = ""

    def handle_data(self, data: str) -> None:
        value = " ".join(data.split())
        if not value:
            return
        if self._capture == "title" and not self.page.title:
            self.page.title = value
        elif self._capture == "heading":
            self.page.headings.append(value)
            self.page.text.append(value)
        elif self._capture == "jsonld":
            self._json_ld.append(data)
        elif self._capture == "text":
            self.page.text.append(value)


def audit_content_health(
    root: Path,
    *,
    base_url: str,
    sitemap_path: Path | None = None,
) -> dict:
    root = root.resolve()
    base = base_url.rstrip("/")
    pages = _read_pages(root)
    sitemap = _read_sitemap(sitemap_path or root / "sitemap.xml")
    articles = [page for page in pages if _is_article(page)]
    page_by_route = {page.route: page for page in pages}

    missing_title = [page.route for page in articles if not page.title]
    missing_description = [page.route for page in articles if not page.description]
    missing_canonical = [page.route for page in articles if not page.canonical]
    missing_og = [
        page.route
        for page in articles
        if not {"og:title", "og:description", "og:type", "og:url"}.issubset(page.og_names)
    ]
    missing_schema = [
        page.route
        for page in articles
        if not any(schema.get("@type") in {"Article", "BlogPosting"} for schema in page.schemas)
    ]
    zero_internal = []
    broken_links: list[dict] = []
    no_related = []
    for page in articles:
        internal_links = _internal_routes(page, base)
        if not internal_links:
            zero_internal.append(page.route)
        for route in sorted(set(internal_links)):
            if route == page.route:
                continue
            if not _local_target_exists(root, route):
                broken_links.append({"source": page.route, "target": route})
        if not ({"related", "related-content"} & page.classes):
            no_related.append(page.route)

    title_groups = {
        title: sorted(page.route for page in articles if page.title == title)
        for title, count in Counter(page.title for page in articles if page.title).items()
        if count > 1
    }
    thin = [page.route for page in articles if page.words < 500]
    counts_by_type = Counter(
        classify_content_type(page.route.strip("/"), page.title) for page in articles
    )
    counts_by_category = Counter(
        classify_category(page.route.strip("/"), page.title) for page in articles
    )
    homepage = page_by_route.get("/")
    homepage_present = {
        section: bool(homepage and section in homepage.headings)
        for section in HOMEPAGE_SECTIONS
    }
    trust_present = {
        route: _local_target_exists(root, route)
        for route in TRUST_ROUTES
    }
    sitemap_status = {
        page.route: f"{base}{page.route}" in sitemap
        for page in articles
    }
    disclosure_present = any(
        "affiliate" in " ".join(page.text).lower()
        for page in pages
        if page.route in {"/", "/affiliate-disclosure/"}
    )
    return {
        "root": str(root),
        "base_url": base,
        "read_only": True,
        "summary": {
            "published_article_count": len(articles),
            "content_type_counts": dict(sorted(counts_by_type.items())),
            "category_counts": dict(sorted(counts_by_category.items())),
            "missing_title_count": len(missing_title),
            "missing_description_count": len(missing_description),
            "missing_canonical_count": len(missing_canonical),
            "missing_open_graph_count": len(missing_og),
            "missing_structured_data_count": len(missing_schema),
            "broken_local_internal_link_count": len(broken_links),
            "zero_internal_link_count": len(zero_internal),
            "no_related_content_count": len(no_related),
            "duplicate_title_group_count": len(title_groups),
            "thin_content_warning_count": len(thin),
            "sitemap_listed_count": sum(sitemap_status.values()),
            "sitemap_not_listed_count": sum(not value for value in sitemap_status.values()),
        },
        "findings": {
            "missing_title": missing_title,
            "missing_description": missing_description,
            "missing_canonical": missing_canonical,
            "missing_open_graph": missing_og,
            "missing_structured_data": missing_schema,
            "broken_local_internal_links": broken_links,
            "zero_internal_links": zero_internal,
            "no_related_content_block": no_related,
            "duplicate_title_candidates": title_groups,
            "thin_content_warnings": thin,
        },
        "trust_pages": trust_present,
        "homepage_sections": homepage_present,
        "sitemap_membership": sitemap_status,
        "affiliate_disclosure_present": disclosure_present,
        "limitations": [
            "Local files and sitemap membership are checked; Google indexing is not inferred.",
            "Thin content uses a simple local 500-word warning threshold.",
            "No network, analytics, Search Console, or paid API data is used.",
        ],
    }


def format_content_health(report: dict) -> str:
    summary = report["summary"]
    lines = [
        "Smile AI Review Hub - Content Health Report",
        f"Root: {report['root']}",
        f"Published articles: {summary['published_article_count']}",
        f"Content types: {json.dumps(summary['content_type_counts'], sort_keys=True)}",
        f"Categories: {json.dumps(summary['category_counts'], sort_keys=True)}",
        f"Missing title: {summary['missing_title_count']}",
        f"Missing description: {summary['missing_description_count']}",
        f"Missing canonical: {summary['missing_canonical_count']}",
        f"Missing Open Graph: {summary['missing_open_graph_count']}",
        f"Missing structured data: {summary['missing_structured_data_count']}",
        f"Broken local internal links: {summary['broken_local_internal_link_count']}",
        f"Zero internal links: {summary['zero_internal_link_count']}",
        f"No related-content block: {summary['no_related_content_count']}",
        f"Duplicate title groups: {summary['duplicate_title_group_count']}",
        f"Thin-content warnings: {summary['thin_content_warning_count']}",
        f"Sitemap listed: {summary['sitemap_listed_count']}",
        f"Sitemap not listed: {summary['sitemap_not_listed_count']}",
        f"Affiliate disclosure present: {report['affiliate_disclosure_present']}",
        "Read-only: YES",
    ]
    return "\n".join(lines)


def _read_pages(root: Path) -> list[ParsedPage]:
    pages: list[ParsedPage] = []
    if not root.exists():
        return pages
    for path in sorted(root.rglob("index.html")):
        route = _route_for_path(root, path)
        first = route.strip("/").split("/", 1)[0]
        if first in INTERNAL_ONLY_ROOTS:
            continue
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        pages.append(_parse_page_fast(path, route, source))
    return pages


def _parse_page_fast(path: Path, route: str, source: str) -> ParsedPage:
    page = ParsedPage(path=path, route=route)
    page.title = _first_group(r"<title\b[^>]*>(.*?)</title>", source)
    page.description = _meta_content(source, "description")
    page.canonical = _first_group(
        r"<link\b(?=[^>]*\brel\s*=\s*['\"][^'\"]*canonical[^'\"]*['\"])[^>]*\bhref\s*=\s*['\"]([^'\"]+)['\"][^>]*>",
        source,
    )
    page.headings = [
        _clean_html(value)
        for value in re.findall(r"<h[1-3]\b[^>]*>(.*?)</h[1-3]>", source, re.I | re.S)
        if _clean_html(value)
    ]
    page.links = re.findall(
        r"<a\b[^>]*\bhref\s*=\s*['\"]([^'\"]*)['\"]",
        source,
        re.I,
    )
    page.og_names = {
        value.lower()
        for value in re.findall(
            r"<meta\b[^>]*(?:property|name)\s*=\s*['\"](og:[^'\"]+)['\"][^>]*>",
            source,
            re.I,
        )
    }
    page.classes = {
        class_name.lower()
        for raw in re.findall(r"\bclass\s*=\s*['\"]([^'\"]+)['\"]", source, re.I)
        for class_name in raw.split()
    }
    for raw in re.findall(
        r"<script\b[^>]*type\s*=\s*['\"]application/ld\+json['\"][^>]*>(.*?)</script>",
        source,
        re.I | re.S,
    ):
        try:
            value = json.loads(raw.strip())
            if isinstance(value, dict):
                page.schemas.append(value)
            elif isinstance(value, list):
                page.schemas.extend(item for item in value if isinstance(item, dict))
        except json.JSONDecodeError:
            page.schemas.append({"@type": "INVALID_JSON_LD"})
    visible = re.sub(r"<(?:script|style)\b.*?</(?:script|style)>", " ", source, flags=re.I | re.S)
    page.text = [_clean_html(visible)]
    return page


def _meta_content(source: str, name: str) -> str:
    patterns = (
        rf"<meta\b(?=[^>]*(?:name|property)\s*=\s*['\"]{re.escape(name)}['\"])[^>]*\bcontent\s*=\s*['\"]([^'\"]*)['\"][^>]*>",
        rf"<meta\b(?=[^>]*\bcontent\s*=\s*['\"]([^'\"]*)['\"])[^>]*(?:name|property)\s*=\s*['\"]{re.escape(name)}['\"][^>]*>",
    )
    for pattern in patterns:
        value = _first_group(pattern, source)
        if value:
            return value
    return ""


def _first_group(pattern: str, source: str) -> str:
    match = re.search(pattern, source, re.I | re.S)
    return _clean_html(match.group(1)) if match else ""


def _clean_html(value: str) -> str:
    without_tags = re.sub(r"<[^>]+>", " ", value)
    return " ".join(without_tags.replace("&nbsp;", " ").split())


def _is_article(page: ParsedPage) -> bool:
    if page.route == "/":
        return False
    parts = page.route.strip("/").split("/")
    if not parts or parts[0] in NON_ARTICLE_ROOTS:
        return False
    if parts[0] == "vi" and len(parts) > 1 and parts[1] in NON_ARTICLE_ROOTS:
        return False
    return any(
        schema.get("@type") in {"Article", "BlogPosting"}
        for schema in page.schemas
    ) or bool(page.title and page.headings)


def _internal_routes(page: ParsedPage, base_url: str) -> list[str]:
    host = urlparse(base_url).netloc.lower()
    result: list[str] = []
    for href in page.links:
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        resolved = urlparse(urljoin(f"{base_url}{page.route}", href))
        if resolved.netloc.lower() != host:
            continue
        route = re.sub(r"/+", "/", resolved.path or "/")
        if route != "/" and not Path(route).suffix:
            route = route.rstrip("/") + "/"
        result.append(route)
    return result


def _local_target_exists(root: Path, route: str) -> bool:
    clean = route.split("?", 1)[0].split("#", 1)[0].lstrip("/")
    if not clean:
        return (root / "index.html").is_file()
    target = root / clean
    if route.endswith("/") or not target.suffix:
        return (target / "index.html").is_file()
    return target.is_file()


def _route_for_path(root: Path, path: Path) -> str:
    relative = path.relative_to(root)
    parent = relative.parent.as_posix()
    return "/" if parent == "." else f"/{parent.strip('/')}/"


def _read_sitemap(path: Path) -> set[str]:
    if not path.is_file():
        return set()
    try:
        tree = ET.parse(path)
    except (ET.ParseError, OSError):
        return set()
    return {
        element.text.strip()
        for element in tree.getroot().iter()
        if element.tag.endswith("loc") and element.text
    }
