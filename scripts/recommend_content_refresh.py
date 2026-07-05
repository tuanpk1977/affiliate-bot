from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from modules.performance_tracking import DATA_DIR, REFRESH_FIELDS, build_content_lifecycle, recommend_refresh, update_master_workbook, write_csv, write_json


def main() -> int:
    lifecycle = build_content_lifecycle()
    rows = recommend_refresh(lifecycle)
    write_csv(DATA_DIR / "content_refresh_recommendations.csv", rows, REFRESH_FIELDS)
    write_json(DATA_DIR / "content_refresh_recommendations.json", rows)
    update_master_workbook({"Refresh Recommendations": (rows, REFRESH_FIELDS)})
    print(f"Refresh recommendations: {len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
