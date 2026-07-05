from __future__ import annotations

import re
import sys
import html as html_lib
from pathlib import Path
from urllib.parse import urlparse
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site_output"
BASE = "https://smileaireviewhub.com"


def main() -> int:
    errors: list[str] = []
    sitemap = parse_sitemap(errors)
    validate_public_reviews(errors, sitemap)
    validate_sitemap(errors, sitemap)
    validate_go_pages(errors, sitemap)
    validate_titles(errors)
    if errors:
        print(f"Technical SEO validation FAILED: {len(errors)} issue(s)")
        for error in errors[:200]:
            print(f"- {error}")
        return 1
    print(f"Technical SEO validation OK: sitemap={len(sitemap)} URLs")
    return 0


def parse_sitemap(errors: list[str]) -> set[str]:
    path = SITE / "sitemap.xml"
    if not path.exists():
        errors.append("missing sitemap.xml")
        return set()
    try:
        root = ET.fromstring(path.read_text(encoding="utf-8", errors="ignore"))
    except ET.ParseError as exc:
        errors.append(f"invalid sitemap.xml: {exc}")
        return set()
    return {node.text.strip() for node in root.findall(".//{http://www.sitemaps.org/schemas/sitemap/0.9}loc") if node.text}


def validate_public_reviews(errors: list[str], sitemap: set[str]) -> None:
    for page in sorted((SITE / "reviews").glob("*/index.html")):
        text = page.read_text(encoding="utf-8", errors="ignore")
        url = f"{BASE}/reviews/{page.parent.name}/"
        if "noindex" in robots(text):
            errors.append(f"{url}: public review contains noindex")
        if has_refresh(text):
            errors.append(f"{url}: public review contains meta refresh")
        if canonical(text) != url:
            errors.append(f"{url}: canonical mismatch ({canonical(text)})")
        if url not in sitemap:
            errors.append(f"{url}: missing from sitemap")


def validate_sitemap(errors: list[str], sitemap: set[str]) -> None:
    for url in sorted(sitemap):
        parsed = urlparse(url)
        if parsed.netloc != "smileaireviewhub.com":
            errors.append(f"{url}: unexpected host")
        if parsed.query:
            errors.append(f"{url}: sitemap URL contains query")
        if parsed.path.startswith("/go/"):
            errors.append(f"{url}: sitemap contains /go/")
        target = SITE / "index.html" if parsed.path == "/" else SITE / parsed.path.strip("/") / "index.html"
        if not target.exists():
            errors.append(f"{url}: missing local 200 HTML target")
            continue
        text = target.read_text(encoding="utf-8", errors="ignore")
        if "noindex" in robots(text):
            errors.append(f"{url}: sitemap target contains noindex")
        if has_refresh(text):
            errors.append(f"{url}: sitemap target contains meta refresh")
        if canonical(text) != url:
            errors.append(f"{url}: sitemap target canonical mismatch ({canonical(text)})")


def validate_go_pages(errors: list[str], sitemap: set[str]) -> None:
    redirects = (SITE / "_redirects").read_text(encoding="utf-8", errors="ignore") if (SITE / "_redirects").exists() else ""
    for page in sorted((SITE / "go").glob("*/index.html")):
        text = page.read_text(encoding="utf-8", errors="ignore")
        url = f"{BASE}/go/{page.parent.name}/"
        if "noindex" not in robots(text):
            errors.append(f"{url}: /go/ page must remain noindex")
        if has_refresh(text):
            errors.append(f"{url}: /go/ page contains meta refresh")
        if url in sitemap:
            errors.append(f"{url}: /go/ page appears in sitemap")
        if f"/go/{page.parent.name}/ " not in redirects:
            errors.append(f"{url}: missing Cloudflare redirect rule")


def validate_titles(errors: list[str]) -> None:
    for page in SITE.rglob("*.html"):
        text = page.read_text(encoding="utf-8", errors="ignore")
        match = re.search(r"<title\b[^>]*>(.*?)</title>", text, flags=re.I | re.S)
        title = html_lib.unescape(re.sub(r"<[^>]+>", " ", match.group(1))).strip() if match else ""
        if len(title) > 60:
            errors.append(f"{page.relative_to(SITE).as_posix()}: title is {len(title)} characters")


def robots(text: str) -> str:
    match = re.search(r"<meta\b(?=[^>]*\bname=['\"]robots['\"])(?=[^>]*\bcontent=['\"]([^'\"]*)['\"])[^>]*>", text, flags=re.I)
    return match.group(1).lower() if match else ""


def canonical(text: str) -> str:
    match = re.search(r"<link\b(?=[^>]*\brel=['\"]canonical['\"])(?=[^>]*\bhref=['\"]([^'\"]+)['\"])[^>]*>", text, flags=re.I)
    return match.group(1).strip() if match else ""


def has_refresh(text: str) -> bool:
    return bool(re.search(r"<meta\b[^>]*http-equiv=['\"]?refresh['\"]?", text, flags=re.I))


if __name__ == "__main__":
    raise SystemExit(main())
