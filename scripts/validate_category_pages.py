from __future__ import annotations

import re
import sys
from html.parser import HTMLParser
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site_output"
INDEX = ROOT / "data" / "category_pages_index.csv"
SITEMAP = SITE / "sitemap.xml"
BASE = "https://review.mssmileenglish.com"
PLACEHOLDER_PATTERNS = ["placeholder", "todo", "lorem ipsum", "example.com", "yourdomain", "fake affiliate"]


class PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = {key: value or "" for key, value in attrs}
        if tag == "a" and attrs_dict.get("href"):
            self.links.append(attrs_dict["href"])


def main() -> int:
    errors: list[str] = []
    if not INDEX.exists():
        print("Category page validation failed:")
        print("- data/category_pages_index.csv does not exist")
        return 1
    if not SITE.exists():
        print("Category page validation failed:")
        print("- site_output does not exist. Run python main.py first.")
        return 1

    df = pd.read_csv(INDEX).fillna("")
    built = df[df["status"].astype(str) == "built"] if "status" in df.columns else df
    if len(built) < 8:
        errors.append(f"expected at least 8 category pages, found {len(built)}")

    sitemap_text = SITEMAP.read_text(encoding="utf-8", errors="ignore") if SITEMAP.exists() else ""
    if "/go/" in sitemap_text:
        errors.append("sitemap.xml contains /go/ tracking URLs")

    h1_values: dict[str, str] = {}
    meta_values: dict[str, str] = {}
    word_counts: list[int] = []
    for _, row in built.iterrows():
        slug = str(row.get("category_slug", "")).strip()
        rel = f"category/{slug}/index.html"
        page = SITE / "category" / slug / "index.html"
        if not slug:
            errors.append("category_pages_index.csv has empty category_slug")
            continue
        if not page.exists():
            errors.append(f"{rel}: missing generated HTML file")
            continue
        text = page.read_text(encoding="utf-8", errors="ignore")
        parser = PageParser()
        parser.feed(text)
        words = word_count(text)
        word_counts.append(words)
        h1 = extract_tag(text, "h1")
        meta = extract_meta_description(text)

        if words < 1000:
            errors.append(f"{rel}: word count below 1000 ({words})")
        if not h1:
            errors.append(f"{rel}: missing H1")
        if not meta:
            errors.append(f"{rel}: missing meta description")
        canonical = f'<link rel="canonical" href="{BASE}/category/{slug}/">'
        if canonical not in text:
            errors.append(f"{rel}: missing canonical {BASE}/category/{slug}/")
        if '"@type": "FAQPage"' not in text:
            errors.append(f"{rel}: missing FAQPage schema")
        if '"@type": "BreadcrumbList"' not in text:
            errors.append(f"{rel}: missing BreadcrumbList schema")
        if text.count("/go/") < 2:
            errors.append(f"{rel}: fewer than 2 /go/ CTAs")
        internal_links = {normalize_link(link) for link in parser.links if normalize_link(link)}
        if len(internal_links) < 5:
            errors.append(f"{rel}: fewer than 5 internal links")
        if "Best tools table" not in text:
            errors.append(f"{rel}: missing Best tools table")
        if "Best for solo / team / agency" not in text:
            errors.append(f"{rel}: missing buyer fit section")
        if "How to choose" not in text:
            errors.append(f"{rel}: missing How to choose section")
        if "Common mistakes" not in text:
            errors.append(f"{rel}: missing Common mistakes section")
        lower = text.lower()
        for pattern in PLACEHOLDER_PATTERNS:
            if pattern in lower:
                errors.append(f"{rel}: contains placeholder pattern {pattern}")
        if f"<loc>{BASE}/category/{slug}/</loc>" not in sitemap_text:
            errors.append(f"{rel}: sitemap missing category URL")
        if h1 in h1_values:
            errors.append(f"{rel}: duplicate H1 with {h1_values[h1]}")
        if meta in meta_values:
            errors.append(f"{rel}: duplicate meta description with {meta_values[meta]}")
        h1_values[h1] = rel
        meta_values[meta] = rel

    if errors:
        print("Category page validation failed:")
        for error in errors:
            print(f"- {error}")
        if word_counts:
            print(f"Checked {len(word_counts)} category pages | avg_word_count={sum(word_counts)//len(word_counts)}")
        return 1

    avg = sum(word_counts) // len(word_counts) if word_counts else 0
    print(f"Category page validation passed: {len(built)} pages | avg_word_count={avg}")
    return 0


def normalize_link(link: str) -> str:
    if not link.startswith("/") or link.startswith("//"):
        return ""
    if link.startswith(("/assets/", "/go/", "/rss.xml", "/sitemap.xml", "/robots.txt", "/llms.txt")):
        return ""
    return link.split("#")[0].split("?")[0]


def word_count(text: str) -> int:
    cleaned = re.sub(r"<script.*?</script>", " ", text, flags=re.DOTALL | re.IGNORECASE)
    cleaned = re.sub(r"<style.*?</style>", " ", cleaned, flags=re.DOTALL | re.IGNORECASE)
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    return len(re.findall(r"[A-Za-z0-9][A-Za-z0-9'-]*", cleaned))


def extract_tag(text: str, tag: str) -> str:
    match = re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", text, flags=re.DOTALL | re.IGNORECASE)
    return re.sub(r"<[^>]+>", "", match.group(1)).strip() if match else ""


def extract_meta_description(text: str) -> str:
    match = re.search(r'<meta\s+name=["\']description["\']\s+content=["\']([^"\']+)["\']', text, flags=re.IGNORECASE)
    return match.group(1).strip() if match else ""


if __name__ == "__main__":
    sys.exit(main())
