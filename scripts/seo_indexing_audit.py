from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "docs"
BASE_URL = "https://smileaireviewhub.com"


@dataclass
class PageAudit:
    path: Path
    url_path: str
    title: str
    robots: str
    canonical: str
    meta_refresh: bool
    internal_links: set[str]


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit Smile AI Review Hub SEO indexing output.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--audit-report", type=Path, default=ROOT / "docs" / "SEO_INDEXING_AUDIT.md")
    parser.add_argument("--fix-report", type=Path, default=ROOT / "docs" / "SEO_INDEXING_FIX_REPORT.md")
    args = parser.parse_args()

    output = args.output
    pages = scan_pages(output)
    sitemap_urls = read_sitemap(output / "sitemap.xml")
    redirects = read_redirects(output / "_redirects")
    page_map = {page.url_path: page for page in pages}
    missing_internal = find_missing_internal_links(pages, output, redirects)
    noindex_pages = [page for page in pages if "noindex" in page.robots.lower()]
    public_noindex = [page for page in noindex_pages if not intentionally_noindex(page.url_path)]
    meta_refresh_pages = [page for page in pages if page.meta_refresh]
    canonical_issues = [page for page in pages if page.canonical and clean_url(page.canonical) != page.url_path and page.url_path not in redirects]
    sitemap_issues = sitemap_problems(sitemap_urls, page_map)

    args.audit_report.parent.mkdir(parents=True, exist_ok=True)
    args.audit_report.write_text(
        render_audit_report(
            pages=pages,
            sitemap_urls=sitemap_urls,
            noindex_pages=noindex_pages,
            public_noindex=public_noindex,
            meta_refresh_pages=meta_refresh_pages,
            canonical_issues=canonical_issues,
            sitemap_issues=sitemap_issues,
            missing_internal=missing_internal,
            redirects=redirects,
        ),
        encoding="utf-8",
    )
    args.fix_report.write_text(
        render_fix_report(
            pages=pages,
            sitemap_urls=sitemap_urls,
            public_noindex=public_noindex,
            meta_refresh_pages=meta_refresh_pages,
            canonical_issues=canonical_issues,
            sitemap_issues=sitemap_issues,
            missing_internal=missing_internal,
            redirects=redirects,
        ),
        encoding="utf-8",
    )
    print(f"SEO audit report: {args.audit_report}")
    print(f"SEO fix report: {args.fix_report}")
    print(f"Pages: {len(pages)} | Sitemap URLs: {len(sitemap_urls)} | Public noindex: {len(public_noindex)} | Missing internal links: {len(missing_internal)}")
    return 0


def scan_pages(output: Path) -> list[PageAudit]:
    pages: list[PageAudit] = []
    for path in sorted(output.rglob("*.html")):
        rel = path.relative_to(output).as_posix()
        if rel.startswith("assets/"):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        url_path = html_path_to_url(rel)
        pages.append(
            PageAudit(
                path=path,
                url_path=url_path,
                title=extract_title(text),
                robots=extract_meta(text, "robots"),
                canonical=extract_canonical(text),
                meta_refresh=bool(re.search(r"<meta\b[^>]*http-equiv=['\"]?refresh", text, flags=re.I)),
                internal_links=extract_internal_links(text),
            )
        )
    return pages


def html_path_to_url(rel: str) -> str:
    if rel == "index.html":
        return "/"
    if rel.endswith("/index.html"):
        return "/" + rel[: -len("index.html")]
    if rel.endswith(".html"):
        return "/" + rel[: -len(".html")]
    return "/" + rel


def extract_title(text: str) -> str:
    match = re.search(r"<title>(.*?)</title>", text, flags=re.I | re.S)
    return re.sub(r"\s+", " ", match.group(1)).strip() if match else ""


def extract_meta(text: str, name: str) -> str:
    match = re.search(rf"<meta\b(?=[^>]*\bname=['\"]{re.escape(name)}['\"])[^>]*\bcontent=['\"]([^'\"]+)['\"]", text, flags=re.I)
    return match.group(1).strip() if match else ""


def extract_canonical(text: str) -> str:
    match = re.search(r"<link\b(?=[^>]*\brel=['\"]canonical['\"])[^>]*\bhref=['\"]([^'\"]+)['\"]", text, flags=re.I)
    return match.group(1).strip() if match else ""


def extract_internal_links(text: str) -> set[str]:
    links: set[str] = set()
    for href in re.findall(r"<a\b[^>]*\bhref=['\"]([^'\"]+)['\"]", text, flags=re.I):
        value = href.split("#", 1)[0].split("?", 1)[0].strip()
        if not value or value.startswith(("#", "mailto:", "tel:", "javascript:", "//")):
            continue
        parsed = urlparse(value)
        if parsed.scheme or parsed.netloc:
            if parsed.netloc != "smileaireviewhub.com":
                continue
            value = parsed.path
        if not value.startswith("/") or value.startswith(("/assets/", "/go/")):
            continue
        links.add(normalize_path(value))
    return links


def normalize_path(path: str) -> str:
    value = "/" + str(path).strip("/")
    if value == "/":
        return "/"
    if value.endswith(".html"):
        value = value[: -len(".html")]
    return value.rstrip("/") + "/"


def clean_url(url: str) -> str:
    parsed = urlparse(url)
    return normalize_path(parsed.path or "/")


def read_sitemap(path: Path) -> list[str]:
    if not path.exists():
        return []
    try:
        root = ET.fromstring(path.read_text(encoding="utf-8", errors="ignore"))
    except ET.ParseError:
        return []
    namespace = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
    return [node.text.strip() for node in root.findall(f".//{namespace}loc") if node.text]


def read_redirects(path: Path) -> dict[str, str]:
    redirects: dict[str, str] = {}
    if not path.exists():
        return redirects
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        parts = stripped.split()
        if len(parts) >= 3 and parts[2] in {"301", "302", "307", "308"}:
            redirects[normalize_path(parts[0])] = parts[1]
    return redirects


def find_missing_internal_links(pages: list[PageAudit], output: Path, redirects: dict[str, str]) -> list[tuple[str, str]]:
    missing: list[tuple[str, str]] = []
    for page in pages:
        for link in page.internal_links:
            if link in redirects:
                continue
            target = output / link.strip("/") / "index.html" if link != "/" else output / "index.html"
            if not target.exists():
                missing.append((page.url_path, link))
    return missing


def intentionally_noindex(path: str) -> bool:
    return path.startswith("/go/") or "/draft" in path or path.startswith(("/search/", "/admin/", "/api/"))


def sitemap_problems(urls: list[str], page_map: dict[str, PageAudit]) -> list[str]:
    problems: list[str] = []
    seen: set[str] = set()
    for url in urls:
        parsed = urlparse(url)
        path = clean_url(url)
        if parsed.netloc and parsed.netloc != "smileaireviewhub.com":
            problems.append(f"outside_domain: {url}")
        if parsed.query:
            problems.append(f"query_url: {url}")
        if path in seen:
            problems.append(f"duplicate_url: {url}")
        seen.add(path)
        if path.startswith("/go/"):
            problems.append(f"go_url_in_sitemap: {url}")
        page = page_map.get(path)
        if not page:
            problems.append(f"missing_page: {url}")
            continue
        if "noindex" in page.robots.lower():
            problems.append(f"noindex_in_sitemap: {url}")
        if page.meta_refresh:
            problems.append(f"meta_refresh_in_sitemap: {url}")
        if page.canonical and clean_url(page.canonical) != path:
            problems.append(f"canonical_mismatch: {url} -> {page.canonical}")
    return problems


def bullet(items: list[str], limit: int = 40) -> str:
    if not items:
        return "- None\n"
    rows = [f"- {item}" for item in items[:limit]]
    if len(items) > limit:
        rows.append(f"- ... {len(items) - limit} more")
    return "\n".join(rows) + "\n"


def render_audit_report(**data: object) -> str:
    pages: list[PageAudit] = data["pages"]  # type: ignore[assignment]
    sitemap_urls: list[str] = data["sitemap_urls"]  # type: ignore[assignment]
    noindex_pages: list[PageAudit] = data["noindex_pages"]  # type: ignore[assignment]
    public_noindex: list[PageAudit] = data["public_noindex"]  # type: ignore[assignment]
    meta_refresh_pages: list[PageAudit] = data["meta_refresh_pages"]  # type: ignore[assignment]
    canonical_issues: list[PageAudit] = data["canonical_issues"]  # type: ignore[assignment]
    sitemap_issues: list[str] = data["sitemap_issues"]  # type: ignore[assignment]
    missing_internal: list[tuple[str, str]] = data["missing_internal"]  # type: ignore[assignment]
    redirects: dict[str, str] = data["redirects"]  # type: ignore[assignment]
    return f"""# SEO Indexing Audit

Generated from local publish output.

## Summary

- HTML files scanned: {len(pages)}
- Sitemap URLs: {len(sitemap_urls)}
- Redirect rules: {len(redirects)}
- Noindex pages: {len(noindex_pages)}
- Public noindex candidates: {len(public_noindex)}
- Meta refresh pages: {len(meta_refresh_pages)}
- Canonical issues: {len(canonical_issues)}
- Sitemap issues: {len(sitemap_issues)}
- Missing internal links: {len(missing_internal)}

## Public Noindex Candidates

{bullet([page.url_path for page in public_noindex])}
## Meta Refresh Pages

{bullet([page.url_path for page in meta_refresh_pages])}
## Canonical Issues

{bullet([f"{page.url_path} -> {page.canonical}" for page in canonical_issues])}
## Sitemap Issues

{bullet(sitemap_issues)}
## Missing Internal Links

{bullet([f"{source} -> {target}" for source, target in missing_internal])}
## Redirect Map Sample

{bullet([f"{source} -> {target}" for source, target in sorted(redirects.items())], limit=30)}
"""


def render_fix_report(**data: object) -> str:
    pages: list[PageAudit] = data["pages"]  # type: ignore[assignment]
    sitemap_urls: list[str] = data["sitemap_urls"]  # type: ignore[assignment]
    public_noindex: list[PageAudit] = data["public_noindex"]  # type: ignore[assignment]
    meta_refresh_pages: list[PageAudit] = data["meta_refresh_pages"]  # type: ignore[assignment]
    sitemap_issues: list[str] = data["sitemap_issues"]  # type: ignore[assignment]
    missing_internal: list[tuple[str, str]] = data["missing_internal"]  # type: ignore[assignment]
    redirects: dict[str, str] = data["redirects"]  # type: ignore[assignment]
    required_redirects = [
        "/surfer-seo-pricing-2026/",
        "/vi/surfer-seo-pricing-2026/",
        "/review/codeium/",
        "/vi/marketing-software-review/",
        "/vi/crm-alternatives/",
    ]
    return f"""# SEO Indexing Fix Report

## What Was Fixed In The Generator

- Added/kept 301 redirect coverage for known Google Search Console 404 legacy URLs.
- Added root topical hubs for AI coding, AI SEO, AI video, AI writing, AI productivity, AI agents, and AI automation.
- Added homepage crawl sections for latest reviews, tutorials, tool hubs, and recently updated pages.
- Standardized auto internal related blocks to `Related Articles` with a maximum of 6 links per page.
- Sitemap generation remains filtered to canonical, indexable local pages only.
- IndexNow remains incremental and does not submit `/go/`, draft, preview, localhost, or off-domain URLs.

## Known GSC 404 Redirect Coverage

{bullet([f"{source} -> {redirects.get(source, 'missing')}" for source in required_redirects])}
## Validation Snapshot

- HTML files scanned: {len(pages)}
- Sitemap URLs: {len(sitemap_urls)}
- Public noindex candidates remaining: {len(public_noindex)}
- Meta refresh pages remaining: {len(meta_refresh_pages)}
- Sitemap issues remaining: {len(sitemap_issues)}
- Missing internal links remaining: {len(missing_internal)}

## Remaining Items To Review

{bullet(sitemap_issues[:20] + [f"{source} -> {target}" for source, target in missing_internal[:20]])}
"""


if __name__ == "__main__":
    raise SystemExit(main())
