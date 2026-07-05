from __future__ import annotations

import argparse
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from modules.opportunity_forecast import build_forecast
from modules.performance_tracking import COMPETITOR_TARGET_FIELDS, DATA_DIR, ensure_template, numeric, read_csv, slugify, write_csv, write_json


DEFAULT_COMPETITORS = [
    "futurepedia.io",
    "theresanaiforthat.com",
    "toolify.ai",
    "futuretools.io",
    "easywithai.com",
    "topai.tools",
]

FIELDS = [
    "competitor_domain",
    "competitor_url",
    "target_keyword",
    "page_type",
    "newest_pages",
    "newest_reviews",
    "comparison_pages",
    "pricing_pages",
    "alternative_pages",
    "publishing_frequency",
    "internal_link_notes",
    "target_keywords",
    "new_opportunity",
    "priority",
    "estimated_revenue",
    "difficulty",
    "suggested_response",
]

GAP_FIELDS = [
    "competitor_domain",
    "target_keyword",
    "missing_keyword",
    "missing_page_type",
    "priority",
    "estimated_revenue",
    "difficulty",
    "recommended_response",
]


def classify_page(url: str, keyword: str) -> str:
    text = f"{url} {keyword}".lower()
    if "pricing" in text or "cost" in text:
        return "Pricing page"
    if "alternative" in text or "alternatives" in text:
        return "Alternative page"
    if " vs " in text or "-vs-" in text or "compare" in text or "comparison" in text:
        return "Comparison page"
    if "review" in text:
        return "Review page"
    return "Newest page"


def build_competitor_watch(targets: list[dict[str, str]]) -> list[dict[str, object]]:
    forecast_by_slug = {row["slug"]: row for row in build_forecast().rows}
    rows = []
    source_targets = targets or [{"competitor_url": f"https://{domain}/", "target_keyword": "AI tools"} for domain in DEFAULT_COMPETITORS]
    for target in source_targets:
        url = target.get("competitor_url", "")
        keyword = target.get("target_keyword", "")
        slug = slugify(target.get("slug") or keyword or url)
        forecast = forecast_by_slug.get(slug, {})
        page_type = classify_page(url, keyword)
        revenue = numeric(forecast.get("estimated_revenue"), default=25 if any(term in page_type for term in ("Pricing", "Review", "Comparison")) else 10)
        difficulty = numeric(forecast.get("estimated_difficulty"), default=55)
        priority = "High" if revenue >= 40 and difficulty <= 65 else "Medium" if revenue >= 15 else "Low"
        rows.append(
            {
                "competitor_domain": urlparse(url).netloc or "manual-input-needed",
                "competitor_url": url,
                "target_keyword": keyword,
                "page_type": page_type,
                "newest_pages": target.get("newest_pages", ""),
                "newest_reviews": target.get("newest_reviews", ""),
                "comparison_pages": target.get("comparison_pages", ""),
                "pricing_pages": target.get("pricing_pages", ""),
                "alternative_pages": target.get("alternative_pages", ""),
                "publishing_frequency": target.get("publishing_frequency", "Manual review needed"),
                "internal_link_notes": target.get("internal_link_notes", "Manual review needed"),
                "target_keywords": target.get("target_keywords", keyword),
                "new_opportunity": f"Create or improve {page_type.lower()} for {keyword or slug}",
                "priority": priority,
                "estimated_revenue": revenue,
                "difficulty": difficulty,
                "suggested_response": "Write/refresh page" if priority == "High" else "Monitor and add internal links",
            }
        )
    return rows


def build_competitor_gap(watch_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    rows = []
    for row in watch_rows:
        keyword = str(row.get("target_keyword") or row.get("target_keywords") or "").strip()
        if not keyword:
            keyword = str(row.get("competitor_domain") or "").replace(".", " ") + " review"
        rows.append(
            {
                "competitor_domain": row.get("competitor_domain", ""),
                "target_keyword": row.get("target_keyword", ""),
                "missing_keyword": keyword,
                "missing_page_type": row.get("page_type", "Newest page"),
                "priority": row.get("priority", ""),
                "estimated_revenue": row.get("estimated_revenue", ""),
                "difficulty": row.get("difficulty", ""),
                "recommended_response": row.get("suggested_response", ""),
            }
        )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a manual competitor watch report. No scraping or network calls.")
    parser.add_argument("--input", default=str(DATA_DIR / "competitor_targets.csv"))
    parser.add_argument("--csv-output", default=str(DATA_DIR / "competitor_watch.csv"))
    parser.add_argument("--json-output", default=str(DATA_DIR / "competitor_watch.json"))
    parser.add_argument("--gap-output", default=str(DATA_DIR / "competitor_gap.csv"))
    parser.add_argument("--gap-json-output", default=str(DATA_DIR / "competitor_gap.json"))
    args = parser.parse_args()

    input_path = Path(args.input)
    ensure_template(input_path, COMPETITOR_TARGET_FIELDS)
    rows = build_competitor_watch(read_csv(input_path))
    gap_rows = build_competitor_gap(rows)
    write_csv(Path(args.csv_output), rows, FIELDS)
    write_json(Path(args.json_output), rows)
    write_csv(Path(args.gap_output), gap_rows, GAP_FIELDS)
    write_json(Path(args.gap_json_output), gap_rows)
    print(f"Competitor watch rows: {len(rows)}")
    print(f"Competitor gap rows: {len(gap_rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
