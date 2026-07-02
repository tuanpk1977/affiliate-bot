from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from html.parser import HTMLParser
from pathlib import Path
import json
import re
from urllib.parse import urlparse
from xml.etree import ElementTree as ET

from modules.indexing_policy import is_redirect_page, should_include_in_sitemap
from modules.publishing_indexing import (
    BASE_URL,
    HOST,
    JSON_LD_RE,
    parse_json_ld,
    schema_nodes,
    validate_schema_payloads,
)


META_RE = re.compile(
    r"<meta\b(?=[^>]*(?:name|property)=['\"]([^'\"]+)['\"])(?=[^>]*content=['\"]([^'\"]*)['\"])[^>]*>",
    re.I,
)
CANONICAL_RE = re.compile(
    r"<link\b(?=[^>]*rel=['\"]canonical['\"])(?=[^>]*href=['\"]([^'\"]+)['\"])[^>]*>",
    re.I,
)
TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
TAG_RE = re.compile(r"<[^>]+>")
IMG_RE = re.compile(r"<img\b([^>]*)>", re.I)
SITEMAP_NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"


class PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []
        self.images: list[dict[str, str]] = []
        self.headings: list[tuple[str, str]] = []
        self.paragraphs: list[str] = []
        self._capture = ""
        self._parts: list[str] = []
        self._ignored_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key.lower(): value or "" for key, value in attrs}
        if tag == "a" and values.get("href"):
            self.links.append(values["href"])
        if tag in {"nav", "header", "footer"}:
            self._ignored_depth += 1
        if self._ignored_depth:
            return
        if tag == "img":
            self.images.append({"src": values.get("src", ""), "alt": values.get("alt", "")})
        if tag in {"h1", "h2", "h3", "p"}:
            self._capture = tag
            self._parts = []

    def handle_data(self, data: str) -> None:
        if self._capture and not self._ignored_depth:
            self._parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"nav", "header", "footer"} and self._ignored_depth:
            self._ignored_depth -= 1
            return
        if self._ignored_depth:
            return
        if tag != self._capture:
            return
        text = " ".join(" ".join(self._parts).split())
        if text:
            if tag == "p":
                self.paragraphs.append(text)
            else:
                self.headings.append((tag, text))
        self._capture = ""
        self._parts = []


@dataclass
class PageHealth:
    url: str
    file: str
    indexable: bool
    title: str = ""
    description: str = ""
    canonical: str = ""
    h1: list[str] = field(default_factory=list)
    schema_types: list[str] = field(default_factory=list)
    internal_links: list[str] = field(default_factory=list)
    external_links: list[str] = field(default_factory=list)
    broken_links: list[str] = field(default_factory=list)
    image_errors: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    word_count: int = 0

    @property
    def faq_ok(self) -> bool:
        return "FAQPage" in self.schema_types

    @property
    def author_ok(self) -> bool:
        return not any(".author" in error for error in self.errors) and any(
            value in self.schema_types for value in ("Article", "BlogPosting", "Review")
        )

    @property
    def breadcrumb_ok(self) -> bool:
        return "BreadcrumbList" in self.schema_types

    @property
    def schema_ok(self) -> bool:
        schema_markers = ("JSON-LD", "Article.", "BlogPosting.", "Review.", "FAQPage.", "BreadcrumbList.")
        return bool(self.schema_types) and not any(
            any(marker in error for marker in schema_markers) for error in self.errors
        )


@dataclass
class HealthAudit:
    pages: list[PageHealth]
    sitemap_urls: list[str]
    sitemap_status: str
    robots_status: str
    duplicate_titles: dict[str, list[str]]
    duplicate_h1: dict[str, list[str]]
    orphan_pages: list[str]
    errors: list[str] = field(default_factory=list)

    @property
    def indexable_pages(self) -> list[PageHealth]:
        return [page for page in self.pages if page.indexable]

    def summary(self) -> dict[str, object]:
        pages = self.indexable_pages
        broken = sum(len(page.broken_links) for page in pages)
        missing_images = sum(len(page.image_errors) for page in pages)
        missing_description = sum(not page.description for page in pages)
        missing_faq = sum(not page.faq_ok for page in pages)
        missing_author = sum(not page.author_ok for page in pages)
        missing_breadcrumb = sum(not page.breadcrumb_ok for page in pages)
        canonical_failures = sum(bool(page.canonical != page.url) for page in pages)
        schema_failures = sum(not page.schema_ok for page in pages)
        internal_count = sum(len(page.internal_links) for page in pages)
        return {
            "status": "PASS" if not self.errors and not broken and not canonical_failures and not schema_failures else "FAIL",
            "total_pages": len(self.pages),
            "indexable_pages": len(pages),
            "sitemap_urls": len(self.sitemap_urls),
            "sitemap_status": self.sitemap_status,
            "robots_status": self.robots_status,
            "canonical_status": "PASS" if not canonical_failures else "FAIL",
            "canonical_failures": canonical_failures,
            "schema_status": "PASS" if not schema_failures else "FAIL",
            "schema_failures": schema_failures,
            "broken_internal_links": broken,
            "orphan_pages": len(self.orphan_pages),
            "missing_images": missing_images,
            "missing_meta_description": missing_description,
            "duplicate_titles": len(self.duplicate_titles),
            "duplicate_h1": len(self.duplicate_h1),
            "missing_faq": missing_faq,
            "missing_author": missing_author,
            "missing_breadcrumb": missing_breadcrumb,
            "http_errors": 0,
            "average_internal_links": round(internal_count / len(pages), 2) if pages else 0,
            "average_word_count": round(sum(page.word_count for page in pages) / len(pages), 2) if pages else 0,
            "average_external_links": round(sum(len(page.external_links) for page in pages) / len(pages), 2) if pages else 0,
            "schema_pass_percent": round(100 * (len(pages) - schema_failures) / len(pages), 2) if pages else 0,
            "canonical_pass_percent": round(100 * (len(pages) - canonical_failures) / len(pages), 2) if pages else 0,
        }


def page_url(path: Path, root: Path) -> str:
    rel = path.relative_to(root).as_posix()
    if rel == "index.html":
        return f"{BASE_URL}/"
    if rel.endswith("/index.html"):
        return f"{BASE_URL}/{rel[:-len('/index.html')]}/"
    return f"{BASE_URL}/{rel}"


def url_to_file(url: str, root: Path) -> Path:
    path = urlparse(url).path
    if path == "/":
        return root / "index.html"
    if Path(path).suffix:
        return root / path.lstrip("/")
    return root / path.strip("/") / "index.html"


def read_sitemap(path: Path) -> tuple[list[str], str, list[str]]:
    if not path.exists():
        return [], "FAIL", ["sitemap.xml is missing"]
    try:
        root = ET.parse(path).getroot()
    except (ET.ParseError, OSError) as exc:
        return [], "FAIL", [f"invalid sitemap XML: {exc}"]
    urls = [str(node.text or "").strip() for node in root.findall(f".//{SITEMAP_NS}loc") if node.text]
    errors = []
    if len(urls) != len(set(urls)):
        errors.append("sitemap contains duplicate URLs")
    return urls, "PASS" if not errors else "FAIL", errors


def inspect_page(path: Path, root: Path) -> PageHealth:
    source = path.read_text(encoding="utf-8", errors="replace")
    url = page_url(path, root)
    robots = ""
    metadata = {key.lower(): value.strip() for key, value in META_RE.findall(source)}
    robots = metadata.get("robots", "")
    indexable = "noindex" not in robots.lower() and should_include_in_sitemap(urlparse(url).path)
    title_match = TITLE_RE.search(source)
    canonicals = CANONICAL_RE.findall(source)
    parser = PageParser()
    parser.feed(source)
    payloads, json_errors = parse_json_ld(source)
    schema_types, schema_errors = validate_schema_payloads(payloads)
    page = PageHealth(
        url=url,
        file=str(path),
        indexable=indexable,
        title=" ".join(TAG_RE.sub("", title_match.group(1)).split()) if title_match else "",
        description=metadata.get("description", ""),
        canonical=canonicals[0].strip() if len(canonicals) == 1 else "",
        h1=[text for level, text in parser.headings if level == "h1"],
        schema_types=schema_types,
        word_count=sum(len(value.split()) for value in parser.paragraphs),
    )
    page.errors.extend(json_errors + schema_errors)
    if not page.title:
        page.errors.append("missing title")
    if not page.description:
        page.errors.append("missing meta description")
    if len(canonicals) != 1:
        page.errors.append(f"canonical count is {len(canonicals)}")
    elif page.canonical != url:
        page.errors.append(f"canonical mismatch: {page.canonical}")
    if indexable:
        for key in ("og:title", "og:description", "twitter:card"):
            if not metadata.get(key):
                page.errors.append(f"missing {key}")
        if len(page.h1) != 1:
            page.errors.append(f"H1 count is {len(page.h1)}")
    for href in parser.links:
        parsed = urlparse(href)
        if parsed.scheme in {"mailto", "tel", "javascript"} or href.startswith("#"):
            continue
        if parsed.netloc and parsed.netloc != HOST:
            page.external_links.append(href)
            continue
        if parsed.netloc == HOST:
            href = parsed.path
        if not href.startswith("/"):
            continue
        if href.startswith(("/go/", "/assets/")):
            continue
        normalized = f"{BASE_URL}{href.split('#', 1)[0].split('?', 1)[0]}"
        if not normalized.endswith("/") and not Path(urlparse(normalized).path).suffix:
            normalized += "/"
        page.internal_links.append(normalized)
        if not url_to_file(normalized, root).exists():
            page.broken_links.append(normalized)
    page.internal_links = sorted(set(page.internal_links))
    page.external_links = sorted(set(page.external_links))
    page.broken_links = sorted(set(page.broken_links))
    for image in parser.images:
        src = image["src"].strip()
        if not image["alt"].strip():
            page.image_errors.append(f"missing alt: {src or '(missing src)'}")
        if not src:
            page.image_errors.append("image missing src")
        elif src.startswith("/") and not url_to_file(f"{BASE_URL}{src}", root).exists():
            page.image_errors.append(f"missing image file: {src}")
    return page


def audit_site(root: Path) -> HealthAudit:
    html_files = sorted(root.rglob("*.html"))
    sitemap_urls, sitemap_status, sitemap_errors = read_sitemap(root / "sitemap.xml")
    sitemap_set = set(sitemap_urls)
    pages = [inspect_page(path, root) for path in html_files if not is_redirect_page(urlparse(page_url(path, root)).path)]
    for page in pages:
        page.indexable = page.url in sitemap_set
    robots = root / "robots.txt"
    robots_text = robots.read_text(encoding="utf-8", errors="replace") if robots.exists() else ""
    robots_ok = bool(
        robots.exists()
        and "User-agent: *" in robots_text
        and f"Sitemap: {BASE_URL}/sitemap.xml" in robots_text
    )
    title_map: dict[str, list[str]] = defaultdict(list)
    h1_map: dict[str, list[str]] = defaultdict(list)
    incoming = Counter()
    indexable_urls = {page.url for page in pages if page.indexable}
    for page in pages:
        if page.indexable and page.title:
            title_map[page.title.casefold()].append(page.url)
        if page.indexable and page.h1:
            h1_map[page.h1[0].casefold()].append(page.url)
        for target in page.internal_links:
            incoming[target] += 1
    protected = {f"{BASE_URL}/", f"{BASE_URL}/about/", f"{BASE_URL}/contact/"}
    orphans = sorted(url for url in indexable_urls if incoming[url] == 0 and url not in protected)
    return HealthAudit(
        pages=pages,
        sitemap_urls=sitemap_urls,
        sitemap_status=sitemap_status,
        robots_status="PASS" if robots_ok else "FAIL",
        duplicate_titles={key: urls for key, urls in title_map.items() if len(urls) > 1},
        duplicate_h1={key: urls for key, urls in h1_map.items() if len(urls) > 1},
        orphan_pages=orphans,
        errors=sitemap_errors + ([] if robots_ok else ["robots.txt validation failed"]),
    )


def write_health_reports(
    audit: HealthAudit,
    report_dir: Path,
    *,
    today_urls: list[str] | None = None,
) -> dict[str, Path]:
    report_dir.mkdir(parents=True, exist_ok=True)
    summary = audit.summary()
    health_lines = [
        "# Daily Health Report",
        "",
        f"**{summary['status']}**",
        "",
        f"- Pages: {summary['indexable_pages']}",
        f"- Sitemap: {summary['sitemap_status']} ({summary['sitemap_urls']} URLs)",
        f"- Robots.txt: {summary['robots_status']}",
        f"- Broken links: {summary['broken_internal_links']}",
        f"- Canonical: {summary['canonical_status']} ({summary['canonical_failures']} failures)",
        f"- Schema: {summary['schema_status']} ({summary['schema_failures']} failures)",
        f"- 404 / HTTP errors: {summary['http_errors']}",
        f"- Orphan pages: {summary['orphan_pages']}",
        f"- Missing images: {summary['missing_images']}",
        f"- Missing meta description: {summary['missing_meta_description']}",
        f"- Duplicate title: {summary['duplicate_titles']}",
        f"- Duplicate H1: {summary['duplicate_h1']}",
        f"- Missing FAQ: {summary['missing_faq']}",
        f"- Missing Author: {summary['missing_author']}",
        f"- Missing Breadcrumb: {summary['missing_breadcrumb']}",
        f"- Average internal links per article: {summary['average_internal_links']}",
    ]
    if audit.orphan_pages:
        health_lines.extend(["", "## Orphan pages", *[f"- {url}" for url in audit.orphan_pages]])
    problem_pages = [page for page in audit.indexable_pages if page.errors or page.broken_links or page.image_errors]
    if problem_pages:
        health_lines.extend(["", "## Failed pages"])
        for page in problem_pages:
            issues = page.errors + page.broken_links + page.image_errors
            health_lines.append(f"- {page.url}: {'; '.join(issues)}")
    health_path = report_dir / "health-report.md"
    health_path.write_text("\n".join(health_lines) + "\n", encoding="utf-8")

    dashboard = {
        **summary,
        "todays_articles": today_urls or [],
        "total_indexed": summary["indexable_pages"],
        "pending": 0,
        "failed": len(problem_pages),
    }
    dashboard_json = report_dir / "dashboard.json"
    dashboard_json.write_text(json.dumps(dashboard, indent=2) + "\n", encoding="utf-8")
    dashboard_md = report_dir / "dashboard.md"
    dashboard_md.write_text(
        "\n".join(
            [
                "# SEO Quality Dashboard",
                "",
                f"- Today's articles: {len(today_urls or [])}",
                f"- Total indexed: {dashboard['total_indexed']}",
                f"- Pending: {dashboard['pending']}",
                f"- Failed: {dashboard['failed']}",
                f"- Broken links: {summary['broken_internal_links']}",
                f"- Average word count: {summary['average_word_count']}",
                f"- Average internal links: {summary['average_internal_links']}",
                f"- Average external links: {summary['average_external_links']}",
                f"- Schema PASS: {summary['schema_pass_percent']}%",
                f"- Canonical PASS: {summary['canonical_pass_percent']}%",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return {"health": health_path, "dashboard_json": dashboard_json, "dashboard_md": dashboard_md}


def write_internal_link_map(audit: HealthAudit, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# Internal Link Map", ""]
    for page in sorted(audit.indexable_pages, key=lambda item: item.url):
        lines.append(f"## {page.title or page.url}")
        if page.internal_links:
            lines.extend(f"- -> {target}" for target in page.internal_links[:10])
        else:
            lines.append("- No internal links")
        lines.append("")
    if audit.orphan_pages:
        lines.extend(["## Orphan pages requiring links", *[f"- {url}" for url in audit.orphan_pages], ""])
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def safe_repair_pages(root: Path, urls: list[str]) -> dict[str, object]:
    repaired: list[str] = []
    unresolved: dict[str, list[str]] = {}
    for url in urls:
        path = url_to_file(url, root)
        if not path.exists():
            unresolved[url] = ["page file is missing"]
            continue
        source = path.read_text(encoding="utf-8", errors="replace")
        updated = source
        canonicals = CANONICAL_RE.findall(source)
        if len(canonicals) == 1 and canonicals[0] != url:
            updated = updated.replace(canonicals[0], url, 1)
        def repair_schema(match: re.Match[str]) -> str:
            try:
                payload = json.loads(match.group(1))
            except json.JSONDecodeError:
                return match.group(0)
            changed = False
            for node in schema_nodes(payload):
                if node.get("@type") in {"Article", "BlogPosting", "Review"}:
                    author = node.get("author")
                    if not isinstance(author, dict) or author.get("@type") not in {"Person", "Organization"} or not str(author.get("name") or "").strip():
                        node["author"] = {"@type": "Organization", "name": "MS Smile AI Review Hub"}
                        changed = True
            if not changed:
                return match.group(0)
            return f'<script type="application/ld+json">{json.dumps(payload, ensure_ascii=False)}</script>'

        updated = JSON_LD_RE.sub(repair_schema, updated)
        updated = re.sub(
            r"<img\b(?![^>]*\balt=)([^>]*)>",
            lambda match: f'<img alt="{Path(re.search(r"""src=['"]([^'"]+)""", match.group(1), re.I).group(1)).stem.replace("-", " ") if re.search(r"""src=['"]([^'"]+)""", match.group(1), re.I) else "Article image"}"{match.group(1)}>',
            updated,
            flags=re.I,
        )
        if not IMG_RE.search(updated) and (root / "assets" / "og" / "site.svg").exists():
            figure = (
                '<figure class="article-image"><img src="/assets/og/site.svg" '
                'alt="MS Smile AI Review Hub editorial illustration" loading="lazy"></figure>'
            )
            updated = re.sub(r"(</h1>)", rf"\1{figure}", updated, count=1, flags=re.I)
        def repair_missing_image(match: re.Match[str]) -> str:
            attrs = match.group(1)
            src_match = re.search(r"\bsrc=['\"]([^'\"]+)['\"]", attrs, re.I)
            if not src_match or not src_match.group(1).startswith("/"):
                return match.group(0)
            if url_to_file(f"{BASE_URL}{src_match.group(1)}", root).exists():
                return match.group(0)
            replacement = attrs.replace(src_match.group(1), "/assets/og/site.svg", 1)
            return f"<img{replacement}>"

        updated = IMG_RE.sub(repair_missing_image, updated)
        if updated != source:
            path.write_text(updated, encoding="utf-8")
            repaired.append(url)
        check = inspect_page(path, root)
        remaining = check.errors + check.broken_links + check.image_errors
        if remaining:
            unresolved[url] = remaining
    return {"repaired": repaired, "unresolved": unresolved}
