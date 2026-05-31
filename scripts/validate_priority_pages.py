from __future__ import annotations

import sys
import re
from pathlib import Path

import pandas as pd


BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
SITE_OUTPUT = BASE_DIR / "site_output"
INDEX_PATH = DATA_DIR / "priority_pages_index.csv"
SITEMAP_PATH = SITE_OUTPUT / "sitemap.xml"
DOMAIN = "https://smileaireviewhub.com"


REQUIRED_INDEX_COLUMNS = [
    "keyword",
    "suggested_slug",
    "page_type",
    "title",
    "output_path",
    "status",
]


def fail(message: str) -> None:
    print(f"Priority page validation failed: {message}")
    raise SystemExit(1)


def read_index() -> pd.DataFrame:
    if not INDEX_PATH.exists():
        fail(f"missing {INDEX_PATH}")
    df = pd.read_csv(INDEX_PATH).fillna("")
    missing = [column for column in REQUIRED_INDEX_COLUMNS if column not in df.columns]
    if missing:
        fail(f"missing index columns: {', '.join(missing)}")
    if df.empty:
        fail("priority_pages_index.csv is empty")
    return df


def validate_page(row: pd.Series, sitemap_text: str) -> None:
    slug = str(row.get("suggested_slug", "")).strip("/")
    if not slug:
        fail("row has empty suggested_slug")

    page = SITE_OUTPUT / slug / "index.html"
    if not page.exists():
        fail(f"missing page for {slug}: {page}")

    text = page.read_text(encoding="utf-8", errors="ignore")
    lower = text.lower()
    if "<title>" not in lower:
        fail(f"{slug} missing title")
    if 'name="description"' not in lower:
        fail(f"{slug} missing meta description")
    if "<h1" not in lower:
        fail(f"{slug} missing H1")
    if "/go/" not in text:
        fail(f"{slug} missing tracking CTA /go/")
    if text.count("/go/") < 3:
        fail(f"{slug} has fewer than 3 tracking CTAs")
    if '"@type": "FAQPage"' not in text and '"@type":"FAQPage"' not in text:
        fail(f"{slug} missing FAQPage schema")
    if '"@type": "BreadcrumbList"' not in text and '"@type":"BreadcrumbList"' not in text:
        fail(f"{slug} missing BreadcrumbList schema")
    if "Some links may be affiliate links" not in text:
        fail(f"{slug} missing affiliate disclosure")

    words = word_count(text)
    if words < 800:
        fail(f"{slug} is thin content: {words} words")

    keyword = str(row.get("keyword", "")).strip().lower()
    if keyword:
        visible = visible_text(text).lower()
        occurrences = visible.count(keyword)
        if occurrences > 14:
            fail(f"{slug} may be keyword stuffing: '{keyword}' appears {occurrences} times")

    expected_url = f"{DOMAIN}/{slug}/"
    if expected_url not in sitemap_text:
        fail(f"{slug} missing from sitemap.xml")
    return words


def visible_text(html_text: str) -> str:
    without_scripts = re.sub(r"<(script|style)\b.*?</\1>", " ", html_text, flags=re.IGNORECASE | re.DOTALL)
    without_tags = re.sub(r"<[^>]+>", " ", without_scripts)
    return re.sub(r"\s+", " ", without_tags).strip()


def word_count(html_text: str) -> int:
    text = visible_text(html_text)
    return len(re.findall(r"[A-Za-z0-9À-ỹ]+(?:[-'][A-Za-z0-9À-ỹ]+)?", text))


def main() -> None:
    df = read_index()
    built = df[df["status"].astype(str).str.lower() == "built"].copy()
    if built.empty:
        fail("no built priority pages")
    if not SITEMAP_PATH.exists():
        fail("missing sitemap.xml")

    sitemap_text = SITEMAP_PATH.read_text(encoding="utf-8", errors="ignore")
    if "/go/" in sitemap_text:
        fail("sitemap.xml contains /go/")

    counts = []
    for _, row in built.iterrows():
        counts.append(validate_page(row, sitemap_text))

    average = sum(counts) / len(counts)
    print(f"Priority page validation passed: {len(built)} pages | avg_word_count={average:.0f}")


if __name__ == "__main__":
    main()
