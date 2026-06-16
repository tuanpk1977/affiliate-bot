from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import urlparse
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site_output"
BASE = "https://smileaireviewhub.com"
UTILITY_ROOT_FILES = {"yandex_265dcf14a6c419f2.html"}


def main() -> int:
    errors: list[str] = []
    redirects = read_redirects()
    canonical_paths = discover_canonical_paths()
    checked = 0

    for page in sorted(SITE.rglob("*.html")):
        rel = page.relative_to(SITE).as_posix()
        if rel in UTILITY_ROOT_FILES or rel.startswith("go/"):
            continue
        if page.name != "index.html" and (SITE / rel.removesuffix(".html") / "index.html").exists():
            continue
        text = page.read_text(encoding="utf-8", errors="ignore")
        if "noindex" in robots(text).lower() or has_refresh(text):
            continue
        checked += 1
        expected_path = rel_to_path(page)
        expected = BASE + expected_path
        canonicals = re.findall(r"<link\b(?=[^>]*\brel=['\"]canonical['\"])(?=[^>]*\bhref=['\"]([^'\"]+)['\"])[^>]*>", text, flags=re.I)
        if len(canonicals) != 1:
            errors.append(f"{rel}: canonical count={len(canonicals)}")
            continue
        if canonicals[0] != expected:
            errors.append(f"{rel}: canonical mismatch {canonicals[0]} != {expected}")
        for source in alternate_paths(expected_path):
            if redirects.get(source) != expected_path:
                errors.append(f"{rel}: missing redirect {source} -> {expected_path}")
        for href in internal_hrefs(text):
            parsed = urlparse(href)
            if parsed.netloc and parsed.netloc != "smileaireviewhub.com":
                continue
            path = parsed.path
            if path.endswith("/index.html") or (path.endswith(".html") and path not in {"/yandex_265dcf14a6c419f2.html"}):
                errors.append(f"{rel}: non-canonical internal href {href}")
            if path and not path.endswith("/") and path in canonical_paths:
                errors.append(f"{rel}: internal href missing trailing slash {href}")

    sitemap_urls = read_sitemap(errors)
    if len(sitemap_urls) != len(set(sitemap_urls)):
        errors.append("sitemap contains duplicate URLs")
    for url in sitemap_urls:
        parsed = urlparse(url)
        if parsed.netloc != "smileaireviewhub.com":
            errors.append(f"sitemap host mismatch: {url}")
        if parsed.query:
            errors.append(f"sitemap contains query URL: {url}")
        if parsed.path.endswith(".html") or parsed.path.endswith("/index.html"):
            errors.append(f"sitemap contains non-canonical URL: {url}")
        if parsed.path.startswith("/go/"):
            errors.append(f"sitemap contains /go/ URL: {url}")
    canonical_urls = {BASE + path for path in canonical_paths}
    for url in sitemap_urls:
        if url not in canonical_urls:
            errors.append(f"sitemap URL has no matching canonical page: {url}")

    if errors:
        print(f"Canonical routing audit FAILED: {len(errors)} issue(s); pages_checked={checked}; sitemap_urls={len(sitemap_urls)}")
        for error in errors[:200]:
            print(f"- {error}")
        return 1
    print(f"Canonical routing audit OK: pages_checked={checked}; sitemap_urls={len(sitemap_urls)}; redirects={len(redirects)}")
    return 0


def read_redirects() -> dict[str, str]:
    path = SITE / "_redirects"
    result: dict[str, str] = {}
    if not path.exists():
        return result
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        parts = stripped.split()
        if len(parts) >= 3 and parts[2] == "301":
            result[parts[0]] = parts[1]
    return result


def discover_canonical_paths() -> set[str]:
    paths: set[str] = set()
    for page in SITE.rglob("*.html"):
        rel = page.relative_to(SITE).as_posix()
        if rel in UTILITY_ROOT_FILES or rel.startswith("go/"):
            continue
        if page.name != "index.html" and (SITE / rel.removesuffix(".html") / "index.html").exists():
            continue
        text = page.read_text(encoding="utf-8", errors="ignore")
        if "noindex" in robots(text).lower() or has_refresh(text):
            continue
        paths.add(rel_to_path(page))
    return paths


def rel_to_path(page: Path) -> str:
    rel = page.relative_to(SITE).as_posix()
    if rel == "index.html":
        return "/"
    if rel.endswith("/index.html"):
        return "/" + rel[: -len("index.html")]
    if rel.endswith(".html"):
        return "/" + rel[: -len(".html")].strip("/") + "/"
    return "/" + rel.strip("/") + "/"


def alternate_paths(canonical: str) -> list[str]:
    if canonical == "/":
        return ["/index.html", "/home", "/home/"]
    stem = canonical.rstrip("/")
    return [stem, f"{stem}.html", f"{stem}/index.html"]


def read_sitemap(errors: list[str]) -> list[str]:
    path = SITE / "sitemap.xml"
    if not path.exists():
        errors.append("missing sitemap.xml")
        return []
    root = ET.fromstring(path.read_text(encoding="utf-8", errors="ignore"))
    return [node.text.strip() for node in root.findall(".//{http://www.sitemaps.org/schemas/sitemap/0.9}loc") if node.text]


def robots(text: str) -> str:
    match = re.search(r"<meta\b(?=[^>]*\bname=['\"]robots['\"])(?=[^>]*\bcontent=['\"]([^'\"]*)['\"])[^>]*>", text, flags=re.I)
    return match.group(1) if match else ""


def has_refresh(text: str) -> bool:
    return bool(re.search(r"<meta\b[^>]*http-equiv=['\"]?refresh['\"]?", text, flags=re.I))


def internal_hrefs(text: str) -> list[str]:
    return re.findall(r"\bhref=['\"]([^'\"]+)['\"]", text, flags=re.I)


if __name__ == "__main__":
    raise SystemExit(main())
