from __future__ import annotations

import re
import sys
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site_output"
SITEMAP = SITE / "sitemap.xml"
BASE = "https://smileaireviewhub.com"
INDEX_PAGES = {
    "reviews": "/reviews/",
    "comparisons": "/comparisons/",
    "pricing": "/pricing/",
    "categories": "/categories/",
    "hubs": "/hubs/",
}
HOMEPAGE_REQUIRED = ["/reviews/", "/comparisons/", "/pricing/", "/categories/", "/hubs/"]
PLACEHOLDER_PATTERNS = ["placeholder", "todo", "lorem ipsum", "example.com", "yourdomain", "fake affiliate"]


class LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = {key: value or "" for key, value in attrs}
        if tag == "a" and attrs_dict.get("href"):
            self.links.append(attrs_dict["href"])


def main() -> int:
    errors: list[str] = []
    if not SITE.exists():
        print("Navigation page validation failed:")
        print("- site_output does not exist. Run python main.py first.")
        return 1

    homepage = SITE / "index.html"
    if not homepage.exists():
        errors.append("homepage index.html missing")
    else:
        home_text = homepage.read_text(encoding="utf-8", errors="ignore")
        for required in HOMEPAGE_REQUIRED:
            if f'href="{required}"' not in home_text and f"href='{required}'" not in home_text:
                errors.append(f"homepage missing link to {required}")
        if "AI Tool Review Center" not in home_text:
            errors.append("homepage missing AI Tool Review Center hero")
        if '"@type": "FAQPage"' not in home_text:
            errors.append("homepage missing FAQ schema")
        if '"@type": "Organization"' not in home_text or '"@type": "WebSite"' not in home_text:
            errors.append("homepage missing Organization/WebSite schema")
        errors.extend(placeholder_errors("index.html", home_text))

    sitemap_text = SITEMAP.read_text(encoding="utf-8", errors="ignore") if SITEMAP.exists() else ""
    if not sitemap_text:
        errors.append("missing sitemap.xml")
    if "/go/" in sitemap_text:
        errors.append("sitemap.xml contains /go/")

    for slug, url in INDEX_PAGES.items():
        page = SITE / slug / "index.html"
        rel = f"{slug}/index.html"
        if not page.exists():
            errors.append(f"{rel}: missing")
            continue
        text = page.read_text(encoding="utf-8", errors="ignore")
        parser = LinkParser()
        parser.feed(text)
        if "<h1" not in text:
            errors.append(f"{rel}: missing H1")
        if 'name="description"' not in text:
            errors.append(f"{rel}: missing meta description")
        canonical = f'<link rel="canonical" href="{BASE}{url}">'
        if canonical not in text:
            errors.append(f"{rel}: missing canonical {BASE}{url}")
        if '"@type": "BreadcrumbList"' not in text:
            errors.append(f"{rel}: missing BreadcrumbList schema")
        internal_links = {normalize_link(link) for link in parser.links if normalize_link(link)}
        if len(internal_links) < 5:
            errors.append(f"{rel}: fewer than 5 internal links")
        if f"<loc>{BASE}{url}</loc>" not in sitemap_text:
            errors.append(f"sitemap.xml missing {url}")
        errors.extend(placeholder_errors(rel, text))

    if errors:
        print("Navigation page validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"Navigation page validation passed: {len(INDEX_PAGES)} index pages")
    return 0


def normalize_link(link: str) -> str:
    if not link.startswith("/") or link.startswith("//"):
        return ""
    if link.startswith(("/assets/", "/go/", "/rss.xml", "/sitemap.xml", "/robots.txt", "/llms.txt")):
        return ""
    return link.split("#")[0].split("?")[0]


def placeholder_errors(rel: str, text: str) -> list[str]:
    lower = re.sub(r"<script.*?</script>", " ", text.lower(), flags=re.DOTALL | re.IGNORECASE)
    lower = re.sub(r"<style.*?</style>", " ", lower, flags=re.DOTALL | re.IGNORECASE)
    lower = re.sub(r"<!--.*?-->", " ", lower, flags=re.DOTALL)
    errors = []
    for pattern in PLACEHOLDER_PATTERNS:
        if pattern in lower:
            errors.append(f"{rel}: contains placeholder pattern {pattern}")
    return errors


if __name__ == "__main__":
    sys.exit(main())
