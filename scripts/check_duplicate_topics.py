from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from modules.content_operations import DUPLICATE_FIELDS, build_duplicate_report
from modules.performance_tracking import DATA_DIR, write_csv, write_json


def main() -> int:
    rows = build_duplicate_report()
    write_csv(DATA_DIR / "duplicate_report.csv", rows, DUPLICATE_FIELDS)
    write_json(DATA_DIR / "duplicate_report.json", rows)
    print(f"Duplicate report rows: {len(rows)}")
    print("Output: data/duplicate_report.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
