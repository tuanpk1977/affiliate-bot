from __future__ import annotations

import re
import sys
from html.parser import HTMLParser
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site_output"
INDEX = ROOT / "data" / "pricing_pages_index.csv"
SITEMAP = SITE / "sitemap.xml"
BASE = "https://smileaireviewhub.com"
REQUIRED_SECTIONS = [
    "Quick pricing verdict",
    "Pricing plan explanation",
    "Free plan / trial note",
    "Hidden cost / contract risk",
    "Best plan for solo user",
    "Best plan for small team",
    "Best plan for agency/business",
    "Alternative if too expensive",
]
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
    if not INDEX.exists():
        print("Pricing page validation failed:")
        print("- data/pricing_pages_index.csv does not exist")
        return 1
    if not SITE.exists():
        print("Pricing page validation failed:")
        print("- site_output does not exist. Run python main.py first.")
        return 1

    df = pd.read_csv(INDEX).fillna("")
    built = df[df["status"].astype(str) == "built"] if "status" in df.columns else df
    if len(built) < 10:
        errors.append(f"expected at least 10 pricing pages, found {len(built)}")

    sitemap_text = SITEMAP.read_text(encoding="utf-8", errors="ignore") if SITEMAP.exists() else ""
    if "/go/" in sitemap_text:
        errors.append("sitemap.xml contains /go/ tracking URLs")

    word_counts: list[int] = []
    for _, row in built.iterrows():
        slug = str(row.get("tool_slug", "")).strip()
        title = str(row.get("title", "")).strip()
        page = SITE / "pricing" / slug / "index.html"
        rel = f"pricing/{slug}/index.html"
        if not slug:
            errors.append("pricing_pages_index.csv has empty tool_slug")
            continue
        if not page.exists():
            errors.append(f"{rel}: missing generated HTML file")
            continue
        text = page.read_text(encoding="utf-8", errors="ignore")
        parser = LinkParser()
        parser.feed(text)

        words = word_count(text)
        word_counts.append(words)
        if words < 1200:
            errors.append(f"{rel}: word count below 1200 ({words})")
        if "<h1" not in text:
            errors.append(f"{rel}: missing H1")
        if 'name="description"' not in text:
            errors.append(f"{rel}: missing meta description")
        canonical = f'<link rel="canonical" href="{BASE}/pricing/{slug}/">'
        if canonical not in text:
            errors.append(f"{rel}: missing canonical {BASE}/pricing/{slug}/")
        if '"@type": "FAQPage"' not in text:
            errors.append(f"{rel}: missing FAQPage schema")
        if '"@type": "BreadcrumbList"' not in text:
            errors.append(f"{rel}: missing BreadcrumbList schema")
        if text.count("/go/") < 2:
            errors.append(f"{rel}: fewer than 2 /go/ CTAs")
        internal_links = {normalize_link(link) for link in parser.links if normalize_link(link)}
        if len(internal_links) < 3:
            errors.append(f"{rel}: fewer than 3 internal links")
        for section in REQUIRED_SECTIONS:
            if section not in text:
                errors.append(f"{rel}: missing section {section}")
        lower = text.lower()
        for pattern in PLACEHOLDER_PATTERNS:
            if pattern in lower:
                errors.append(f"{rel}: contains placeholder pattern {pattern}")
        if "Some links may be affiliate links" not in text:
            errors.append(f"{rel}: missing affiliate disclosure")
        if title and title not in text:
            errors.append(f"{rel}: index title not found in page")
        if f"<loc>{BASE}/pricing/{slug}/</loc>" not in sitemap_text:
            errors.append(f"{rel}: sitemap missing pricing URL")

    if errors:
        print("Pricing page validation failed:")
        for error in errors:
            print(f"- {error}")
        if word_counts:
            print(f"Checked {len(word_counts)} pricing pages | avg_word_count={sum(word_counts)//len(word_counts)}")
        return 1

    avg = sum(word_counts) // len(word_counts) if word_counts else 0
    print(f"Pricing page validation passed: {len(built)} pages | avg_word_count={avg}")
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


if __name__ == "__main__":
    sys.exit(main())
