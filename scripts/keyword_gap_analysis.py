from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from modules.opportunity_forecast import build_forecast
from modules.performance_tracking import COMPETITOR_TARGET_FIELDS, DATA_DIR, build_content_lifecycle, ensure_template, numeric, read_csv, slugify, write_csv, write_json


FIELDS = ["missing_keyword", "slug", "competitor_url", "priority", "estimated_revenue", "difficulty", "reason"]


def keyword_exists(keyword: str, lifecycle: list[dict[str, object]]) -> bool:
    needle = keyword.lower().strip()
    if not needle:
        return False
    return any(needle in str(row.get("topic", "")).lower() or needle in str(row.get("slug", "")).replace("-", " ").lower() for row in lifecycle)


def build_keyword_gap(targets: list[dict[str, str]]) -> list[dict[str, object]]:
    lifecycle = build_content_lifecycle()
    forecast_by_slug = {row["slug"]: row for row in build_forecast().rows}
    rows = []
    for target in targets:
        keyword = target.get("target_keyword", "").strip()
        if not keyword or keyword_exists(keyword, lifecycle):
            continue
        slug = slugify(target.get("slug") or keyword)
        forecast = forecast_by_slug.get(slug, {})
        revenue = numeric(forecast.get("estimated_revenue"), default=20)
        difficulty = numeric(forecast.get("estimated_difficulty"), default=55)
        priority = "High" if revenue >= 40 and difficulty <= 65 else "Medium" if revenue >= 15 else "Low"
        rows.append(
            {
                "missing_keyword": keyword,
                "slug": slug,
                "competitor_url": target.get("competitor_url", ""),
                "priority": priority,
                "estimated_revenue": revenue,
                "difficulty": difficulty,
                "reason": "Competitor target keyword not found in current lifecycle/content index.",
            }
        )
    return sorted(rows, key=lambda row: (numeric(row.get("estimated_revenue")), -numeric(row.get("difficulty"))), reverse=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare manual competitor targets against current content and report missing keywords.")
    parser.add_argument("--input", default=str(DATA_DIR / "competitor_targets.csv"))
    parser.add_argument("--csv-output", default=str(DATA_DIR / "keyword_gap.csv"))
    parser.add_argument("--json-output", default=str(DATA_DIR / "keyword_gap.json"))
    args = parser.parse_args()

    input_path = Path(args.input)
    ensure_template(input_path, COMPETITOR_TARGET_FIELDS)
    rows = build_keyword_gap(read_csv(input_path))
    write_csv(Path(args.csv_output), rows, FIELDS)
    write_json(Path(args.json_output), rows)
    print(f"Keyword gap rows: {len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
