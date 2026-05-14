from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

import pandas as pd


BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
SITE_OUTPUT = BASE_DIR / "site_output"
INDEX_PATH = DATA_DIR / "review_pages_index.csv"
SITEMAP_PATH = SITE_OUTPUT / "sitemap.xml"
DOMAIN = "https://review.mssmileenglish.com"

REQUIRED_COLUMNS = [
    "offer_id",
    "brand_name",
    "review_slug",
    "title",
    "output_path",
    "status",
    "affiliate_status",
]


def fail(message: str) -> None:
    print(f"Review page validation failed: {message}")
    raise SystemExit(1)


def main() -> None:
    if not INDEX_PATH.exists():
        fail(f"missing {INDEX_PATH}")
    if not SITEMAP_PATH.exists():
        fail("missing site_output/sitemap.xml")

    index = pd.read_csv(INDEX_PATH).fillna("")
    missing = [column for column in REQUIRED_COLUMNS if column not in index.columns]
    if missing:
        fail(f"missing index columns: {', '.join(missing)}")

    built = index[index["status"].astype(str).str.lower() == "built"].copy()
    if len(built) < 20:
        fail(f"expected at least 20 review pages, found {len(built)}")

    sitemap_text = SITEMAP_PATH.read_text(encoding="utf-8", errors="ignore")
    if "/go/" in sitemap_text:
        fail("sitemap.xml contains /go/")

    h1_values: list[str] = []
    meta_values: list[str] = []
    page_texts: dict[str, str] = {}
    for _, row in built.iterrows():
        slug = str(row.get("review_slug", "")).strip("/")
        page = SITE_OUTPUT / "review" / slug / "index.html"
        if page.exists():
            text = page.read_text(encoding="utf-8", errors="ignore")
            page_texts[slug] = text
            h1_values.append(extract_tag_text(text, "h1"))
            meta_values.append(extract_meta_description(text))

    duplicate_h1 = [value for value, count in Counter(h1_values).items() if value and count > 1]
    duplicate_meta = [value for value, count in Counter(meta_values).items() if value and count > 1]
    if duplicate_h1:
        fail(f"duplicate H1 found: {duplicate_h1[0]}")
    if duplicate_meta:
        fail(f"duplicate meta description found: {duplicate_meta[0]}")

    word_counts: list[int] = []
    for _, row in built.iterrows():
        word_counts.append(validate_page(row, sitemap_text, page_texts))

    average = sum(word_counts) / len(word_counts)
    print(f"Review page validation passed: {len(built)} pages | avg_word_count={average:.0f}")


def validate_page(row: pd.Series, sitemap_text: str, page_texts: dict[str, str]) -> int:
    slug = str(row.get("review_slug", "")).strip("/")
    if not slug:
        fail("row has empty review_slug")

    page = SITE_OUTPUT / "review" / slug / "index.html"
    if not page.exists():
        fail(f"missing review page: {page}")
    text = page_texts.get(slug) or page.read_text(encoding="utf-8", errors="ignore")
    lower = text.lower()

    if "<h1" not in lower:
        fail(f"{slug} missing H1")
    if 'name="description"' not in lower:
        fail(f"{slug} missing meta description")
    if "Some links may be affiliate links" not in text:
        fail(f"{slug} missing affiliate disclosure")
    if "Quick verdict" not in text:
        fail(f"{slug} missing Quick verdict")
    if "Best for / Not best for" not in text:
        fail(f"{slug} missing Best for / Not best for")
    if "Feature checklist" not in text:
        fail(f"{slug} missing Feature checklist")
    if "Real buying considerations" not in text:
        fail(f"{slug} missing Real buying considerations")
    if "Official site / affiliate pending" not in text:
        fail(f"{slug} missing affiliate pending status")
    if text.count("/go/") < 3:
        fail(f"{slug} has fewer than 3 /go/ CTAs")
    if len(internal_links(text)) < 3:
        fail(f"{slug} has fewer than 3 internal links")
    if '"@type": "FAQPage"' not in text and '"@type":"FAQPage"' not in text:
        fail(f"{slug} missing FAQPage schema")
    if '"@type": "BreadcrumbList"' not in text and '"@type":"BreadcrumbList"' not in text:
        fail(f"{slug} missing BreadcrumbList schema")
    canonical = f'<link rel="canonical" href="{DOMAIN}/review/{slug}/">'
    if canonical not in text:
        fail(f"{slug} missing canonical")

    words = word_count(text)
    if words < 1200:
        fail(f"{slug} is thin content: {words} words")
    if has_placeholder(text):
        fail(f"{slug} contains placeholder text")

    expected_url = f"{DOMAIN}/review/{slug}/"
    if expected_url not in sitemap_text:
        fail(f"{slug} missing from sitemap.xml")
    return words


def visible_text(html_text: str) -> str:
    without_scripts = re.sub(r"<(script|style)\b.*?</\1>", " ", html_text, flags=re.IGNORECASE | re.DOTALL)
    without_tags = re.sub(r"<[^>]+>", " ", without_scripts)
    return re.sub(r"\s+", " ", without_tags).strip()


def word_count(html_text: str) -> int:
    text = visible_text(html_text)
    return len(re.findall(r"[A-Za-z0-9]+(?:[-'][A-Za-z0-9]+)?", text))


def internal_links(text: str) -> set[str]:
    links = set()
    for link in re.findall(r"href=['\"]([^'\"]+)['\"]", text):
        if link.startswith("/") and not link.startswith(("/assets/", "/go/", "//")):
            normalized = link.split("#")[0].split("?")[0]
            if normalized:
                links.add(normalized)
    return links


def extract_tag_text(text: str, tag: str) -> str:
    match = re.search(rf"<{tag}\b[^>]*>(.*?)</{tag}>", text, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return ""
    return clean_text(match.group(1))


def extract_meta_description(text: str) -> str:
    match = re.search(r'<meta\s+name=["\']description["\']\s+content=["\']([^"\']+)["\']', text, flags=re.IGNORECASE)
    return clean_text(match.group(1)) if match else ""


def clean_text(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def has_placeholder(text: str) -> bool:
    lower = text.lower()
    patterns = [
        r"yourdomain\.com",
        r"example\.com",
        r"lorem ipsum",
        r"\btodo\b",
        r"\bundefined\b",
        r"placeholder text",
        r"placeholder image",
        r"404 not found",
    ]
    return any(re.search(pattern, lower, re.IGNORECASE) for pattern in patterns)


if __name__ == "__main__":
    main()
