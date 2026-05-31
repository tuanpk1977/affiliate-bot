from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site_output"
DATA = ROOT / "data"
REPORT = DATA / "seo_indexing_report.txt"
BASE_URL = "https://smileaireviewhub.com"

sys.path.insert(0, str(ROOT))

from modules.indexing_policy import is_article_page, is_redirect_page, rel_path_for_html, should_include_in_sitemap  # noqa: E402


@dataclass
class SeoResult:
    indexed_pages: int = 0
    excluded_pages: int = 0
    redirect_pages: int = 0
    sitemap_urls: int = 0
    excluded_redirect_pages: int = 0
    canonical_errors: list[str] | None = None
    robots_errors: list[str] | None = None
    sitemap_errors: list[str] | None = None
    robots_txt_errors: list[str] | None = None
    grep_findings: list[str] | None = None

    def __post_init__(self) -> None:
        self.canonical_errors = self.canonical_errors or []
        self.robots_errors = self.robots_errors or []
        self.sitemap_errors = self.sitemap_errors or []
        self.robots_txt_errors = self.robots_txt_errors or []
        self.grep_findings = self.grep_findings or []


def main() -> int:
    DATA.mkdir(parents=True, exist_ok=True)
    result = SeoResult()
    if not SITE.exists():
        result.robots_errors.append("site_output directory is missing")
        write_report(result)
        print_summary(result)
        return 1

    html_files = sorted(SITE.rglob("*.html"))
    validate_html_files(html_files, result)
    validate_sitemap(result)
    validate_robots_txt(result)
    result.grep_findings = grep_indexing_terms()
    write_report(result)
    print_summary(result)
    return 1 if has_errors(result) else 0


def validate_html_files(html_files: list[Path], result: SeoResult) -> None:
    for file in html_files:
        text = file.read_text(encoding="utf-8", errors="ignore")
        page_path = rel_path_for_html(file, SITE)
        rel = file.relative_to(SITE).as_posix()
        robots = extract_meta_content(text, "robots")
        canonical = extract_canonical(text)

        if is_redirect_page(page_path):
            result.redirect_pages += 1
            result.excluded_pages += 1
            if "noindex" not in robots.lower() or "follow" not in robots.lower() or "nofollow" in robots.lower():
                result.robots_errors.append(f"{rel}: redirect page must use robots noindex,follow")
            continue

        if should_include_in_sitemap(page_path):
            result.indexed_pages += 1
        else:
            result.excluded_pages += 1

        if is_article_page(page_path):
            if robots.lower().replace(" ", "") != "index,follow":
                result.robots_errors.append(f"{rel}: article page must use robots index,follow")
            expected = f"{BASE_URL}{page_path}"
            if not canonical:
                result.canonical_errors.append(f"{rel}: missing canonical")
            elif canonical != expected:
                result.canonical_errors.append(f"{rel}: canonical mismatch expected {expected} got {canonical}")
            if canonical == f"{BASE_URL}/" and page_path != "/":
                result.canonical_errors.append(f"{rel}: canonical points to homepage")
            if "/go/" in canonical:
                result.canonical_errors.append(f"{rel}: canonical points to redirect page")


def validate_sitemap(result: SeoResult) -> None:
    sitemap_path = SITE / "sitemap.xml"
    if not sitemap_path.exists():
        result.sitemap_errors.append("sitemap.xml missing")
        return
    text = sitemap_path.read_text(encoding="utf-8", errors="ignore")
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        result.sitemap_errors.append(f"sitemap.xml parse error: {exc}")
        return
    urls = [loc.text.strip() for loc in root.findall(".//{http://www.sitemaps.org/schemas/sitemap/0.9}loc") if loc.text]
    result.sitemap_urls = len(urls)
    seen = set()
    blocked_fragments = ["/go/", "/rss.xml", "/sitemap/", "/media-kit/", "/about-author/", "/author-profile/", "/search"]
    for url in urls:
        if url in seen:
            result.sitemap_errors.append(f"duplicate sitemap URL: {url}")
        seen.add(url)
        parsed = urlparse(url)
        path = parsed.path or "/"
        if parsed.netloc != "smileaireviewhub.com":
            result.sitemap_errors.append(f"unexpected sitemap host: {url}")
        if any(fragment in url for fragment in blocked_fragments):
            result.sitemap_errors.append(f"non-indexable URL in sitemap: {url}")
        if not should_include_in_sitemap(path):
            result.sitemap_errors.append(f"policy-excluded URL in sitemap: {url}")
        target = SITE / "index.html" if path == "/" else SITE / path.strip("/") / "index.html"
        if not target.exists():
            result.sitemap_errors.append(f"sitemap URL missing file: {url}")
    result.excluded_redirect_pages = result.redirect_pages


def validate_robots_txt(result: SeoResult) -> None:
    path = SITE / "robots.txt"
    if not path.exists():
        result.robots_txt_errors.append("robots.txt missing")
        return
    lines = [line.strip() for line in path.read_text(encoding="utf-8", errors="ignore").splitlines() if line.strip()]
    required = [
        "User-agent: *",
        "Allow: /",
        f"Sitemap: {BASE_URL}/sitemap.xml",
    ]
    for line in required:
        if line not in lines:
            result.robots_txt_errors.append(f"robots.txt missing {line}")
    for line in lines:
        lower = line.lower()
        if lower.startswith("disallow:"):
            result.robots_txt_errors.append(f"robots.txt must not contain {line}")
        if not (lower.startswith("user-agent:") or lower.startswith("allow:") or lower.startswith("sitemap:")):
            result.robots_txt_errors.append(f"unexpected robots.txt directive: {line}")


def grep_indexing_terms() -> list[str]:
    findings: list[str] = []
    valid_note = {
        "noindex": "valid only for /go/ redirect pages and validation code",
        "Disallow": "invalid in generated robots.txt; acceptable in tests/docs explaining blocked states",
        "nofollow": "valid for sponsored outbound links, not for robots meta on /go/",
    }
    skip_dirs = {".git", "__pycache__", ".pytest_cache", "node_modules", "logs"}
    for root in ["modules", "scripts", "config", "content", "data", "docs", "site_output"]:
        base = ROOT / root
        if not base.exists():
            continue
        for file in base.rglob("*"):
            if not file.is_file() or any(part in skip_dirs for part in file.parts):
                continue
            if file.suffix.lower() not in {".py", ".html", ".txt", ".xml", ".md", ".json", ".csv"}:
                continue
            try:
                text = file.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for term, reason in valid_note.items():
                if term.lower() in text.lower():
                    rel = file.relative_to(ROOT).as_posix()
                    findings.append(f"{rel}: contains {term} ({reason})")
                    break
    return findings[:250]


def extract_meta_content(text: str, name: str) -> str:
    pattern = rf"<meta\b(?=[^>]*\bname=['\"]{re.escape(name)}['\"])(?=[^>]*\bcontent=['\"]([^'\"]*)['\"])[^>]*>"
    match = re.search(pattern, text, flags=re.I)
    return match.group(1).strip() if match else ""


def extract_canonical(text: str) -> str:
    match = re.search(r"<link\b(?=[^>]*\brel=['\"]canonical['\"])(?=[^>]*\bhref=['\"]([^'\"]+)['\"])[^>]*>", text, flags=re.I)
    return match.group(1).strip() if match else ""


def has_errors(result: SeoResult) -> bool:
    return bool(result.canonical_errors or result.robots_errors or result.sitemap_errors or result.robots_txt_errors)


def write_report(result: SeoResult) -> None:
    lines = [
        "SEO Indexing Validation Report",
        f"Checked at: {datetime.now().isoformat(timespec='seconds')}",
        "",
        f"Indexed pages: {result.indexed_pages}",
        f"Excluded pages: {result.excluded_pages}",
        f"Redirect pages: {result.redirect_pages}",
        f"Excluded redirect pages: {result.excluded_redirect_pages}",
        f"Sitemap URLs: {result.sitemap_urls}",
        "",
        f"Canonical errors: {len(result.canonical_errors)}",
        *[f"- {item}" for item in result.canonical_errors[:100]],
        "",
        f"Robots meta errors: {len(result.robots_errors)}",
        *[f"- {item}" for item in result.robots_errors[:100]],
        "",
        f"Sitemap errors: {len(result.sitemap_errors)}",
        *[f"- {item}" for item in result.sitemap_errors[:100]],
        "",
        f"Robots.txt errors: {len(result.robots_txt_errors)}",
        *[f"- {item}" for item in result.robots_txt_errors[:100]],
        "",
        "Indexing term grep findings:",
        *[f"- {item}" for item in result.grep_findings],
    ]
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def print_summary(result: SeoResult) -> None:
    print(f"Indexed pages: {result.indexed_pages}")
    print(f"Excluded pages: {result.excluded_pages}")
    print(f"Redirect pages: {result.redirect_pages}")
    print(f"Sitemap URLs: {result.sitemap_urls}")
    print(f"Canonical errors: {len(result.canonical_errors)}")
    print(f"Robots meta errors: {len(result.robots_errors)}")
    print(f"Sitemap errors: {len(result.sitemap_errors)}")
    print(f"Robots.txt errors: {len(result.robots_txt_errors)}")
    print(f"Report: {REPORT}")


if __name__ == "__main__":
    raise SystemExit(main())
