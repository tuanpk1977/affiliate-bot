from __future__ import annotations

import re
from difflib import SequenceMatcher
from pathlib import Path

import pandas as pd


BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
SITE_OUTPUT = BASE_DIR / "site_output"
INDEX_PATH = DATA_DIR / "comparison_pages_index.csv"
SITEMAP_PATH = SITE_OUTPUT / "sitemap.xml"
DOMAIN = "https://smileaireviewhub.com"

REQUIRED_COLUMNS = [
    "comparison_slug",
    "tool_a_slug",
    "tool_a_name",
    "tool_b_slug",
    "tool_b_name",
    "title",
    "output_path",
    "status",
]


def fail(message: str) -> None:
    print(f"Comparison page validation failed: {message}")
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
    if len(built) < 10:
        fail(f"expected at least 10 comparison pages, found {len(built)}")

    sitemap_text = SITEMAP_PATH.read_text(encoding="utf-8", errors="ignore")
    if "/go/" in sitemap_text:
        fail("sitemap.xml contains /go/")
    if "/compare/" not in sitemap_text:
        fail("sitemap.xml does not contain /compare/ pages")

    page_data: list[dict] = []
    word_counts: list[int] = []
    for _, row in built.iterrows():
        result = validate_page(row, sitemap_text)
        word_counts.append(result["word_count"])
        page_data.append(result)

    similarity_errors = similarity_checks(page_data)
    if similarity_errors:
        fail("; ".join(similarity_errors[:3]))

    average = sum(word_counts) / len(word_counts)
    print(f"Comparison page validation passed: {len(built)} pages | avg_word_count={average:.0f}")


def validate_page(row: pd.Series, sitemap_text: str) -> dict:
    slug = str(row.get("comparison_slug", "")).strip("/")
    if not slug:
        fail("row has empty comparison_slug")
    page = SITE_OUTPUT / "compare" / slug / "index.html"
    if not page.exists():
        fail(f"missing comparison page: {page}")
    text = page.read_text(encoding="utf-8", errors="ignore")
    lower = text.lower()

    if "<h1" not in lower:
        fail(f"{slug} missing H1")
    if 'name="description"' not in lower:
        fail(f"{slug} missing meta description")
    if "<table" not in lower or "quick comparison table" not in lower:
        fail(f"{slug} missing comparison table")
    if "Quick verdict" not in text and "Quick decision verdict" not in text:
        fail(f"{slug} missing Quick verdict")
    if "Choose " not in text or " if..." not in text:
        fail(f"{slug} missing Choose A / Choose B section")
    if "scorecard" not in lower:
        fail(f"{slug} missing scoring table")
    if "Migration / switching" not in text and "Switching and migration" not in text:
        fail(f"{slug} missing migration/switching section")
    for required in ["Pricing and contract risk", "Team size recommendation", "Best alternative if neither fits"]:
        if required not in text:
            fail(f"{slug} missing {required}")
    for criterion in ["ease_of_use", "pricing_clarity", "feature_depth", "team_fit", "affiliate_confidence"]:
        if criterion not in text:
            fail(f"{slug} missing scoring criterion {criterion}")
    if text.count("/go/") < 3:
        fail(f"{slug} has fewer than 3 /go/ CTAs")
    if len(internal_links(text)) < 4:
        fail(f"{slug} has fewer than 4 internal links")
    if '"@type": "FAQPage"' not in text and '"@type":"FAQPage"' not in text:
        fail(f"{slug} missing FAQPage schema")
    if '"@type": "BreadcrumbList"' not in text and '"@type":"BreadcrumbList"' not in text:
        fail(f"{slug} missing BreadcrumbList schema")
    canonical = f'<link rel="canonical" href="{DOMAIN}/compare/{slug}/">'
    if canonical not in text:
        fail(f"{slug} missing canonical")
    if "Some links may be affiliate links" not in text:
        fail(f"{slug} missing affiliate disclosure")
    if has_placeholder(text):
        fail(f"{slug} contains placeholder text")

    words = word_count(text)
    if words < 1500:
        fail(f"{slug} is thin content: {words} words")

    expected_url = f"{DOMAIN}/compare/{slug}/"
    if expected_url not in sitemap_text:
        fail(f"{slug} missing from sitemap.xml")
    return {
        "slug": slug,
        "word_count": words,
        "intro": first_paragraph(text),
        "headings": " > ".join(extract_headings(text)[:16]),
    }


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


def first_paragraph(text: str) -> str:
    for match in re.findall(r"<p[^>]*>(.*?)</p>", text, flags=re.IGNORECASE | re.DOTALL):
        cleaned = clean_text(match)
        if len(cleaned) >= 90 and "Home /" not in cleaned and "Some links may be affiliate links" not in cleaned:
            return cleaned
    return ""


def extract_headings(text: str) -> list[str]:
    return [clean_text(match) for match in re.findall(r"<h[1-3]\b[^>]*>(.*?)</h[1-3]>", text, flags=re.IGNORECASE | re.DOTALL)]


def clean_text(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def similarity_checks(pages: list[dict]) -> list[str]:
    errors: list[str] = []
    for index, page in enumerate(pages):
        for other in pages[index + 1 :]:
            intro_similarity = SequenceMatcher(None, page["intro"], other["intro"]).ratio() if page["intro"] and other["intro"] else 0
            heading_similarity = SequenceMatcher(None, page["headings"], other["headings"]).ratio() if page["headings"] and other["headings"] else 0
            if intro_similarity >= 0.94:
                errors.append(f"intro similarity too high: {page['slug']} vs {other['slug']} ({intro_similarity:.2f})")
            if heading_similarity >= 0.985:
                errors.append(f"heading similarity too high: {page['slug']} vs {other['slug']} ({heading_similarity:.2f})")
    return errors


if __name__ == "__main__":
    main()
