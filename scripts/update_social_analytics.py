from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from modules.performance_tracking import DATA_DIR, SOCIAL_FIELDS, build_social_dashboard, ensure_template, read_csv, update_master_workbook, write_business_outputs, write_csv, write_json


def main() -> int:
    social_path = DATA_DIR / "social_analytics.csv"
    ensure_template(social_path, SOCIAL_FIELDS)
    rows = read_csv(social_path)
    dashboard = build_social_dashboard(rows)
    write_csv(DATA_DIR / "social_analytics_dashboard.csv", dashboard, ["platform", "posts", "views", "likes", "comments", "shares", "saves", "clicks", "click_potential"])
    write_json(DATA_DIR / "social_analytics_dashboard.json", dashboard)
    update_master_workbook({"Social Analytics": (rows, SOCIAL_FIELDS), "Social Summary": (dashboard, ["platform", "posts", "views", "likes", "comments", "shares", "saves", "clicks", "click_potential"])})
    result = write_business_outputs()
    print(f"Social rows: {len(rows)}")
    print(f"Social platform summaries: {len(dashboard)}")
    print(f"Master workbook updated: {result['excel']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
