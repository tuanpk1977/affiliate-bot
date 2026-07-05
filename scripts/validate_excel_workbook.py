from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from modules.performance_tracking import DATA_DIR, validate_workbook_file

REQUIRED_MASTER_SHEETS = {
    "Today Write Plan",
    "Money Ranking",
    "AI Priority Dashboard",
    "Revenue Opportunity",
    "Daily Publishing Schedule",
    "Website Publishing Queue",
    "Executive Content Summary",
    "Publishing Queue",
    "Duplicate Risk",
    "Authority Score",
    "Content Gap",
    "Content Clusters",
    "Internal Link Cluster Plan",
    "AI Auto Editor Report",
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate an Excel workbook for safe Microsoft Excel opening.")
    parser.add_argument("workbook", nargs="?", default=str(DATA_DIR / "master_dashboard.xlsx"), help="Workbook path to validate.")
    args = parser.parse_args()

    path = Path(args.workbook)
    result = validate_workbook_file(path)
    print(f"Workbook: {result['path']}")
    print(f"Exists: {'YES' if result['exists'] else 'NO'}")
    print(f"File size: {result['file_size']} bytes")
    print(f"Worksheet count: {result['sheet_count']}")
    print("Worksheet names:")
    for name in result["worksheet_names"]:
        print(f"  - {name}")
    print("Row counts:")
    for name, count in result["row_counts"].items():
        print(f"  - {name}: {count}")
    if path.resolve() == (DATA_DIR / "master_dashboard.xlsx").resolve():
        missing = sorted(REQUIRED_MASTER_SHEETS - set(result["worksheet_names"]))
        if missing:
            result["errors"].append("Missing required AI CEO dashboard sheets: " + ", ".join(missing))
    if result["errors"]:
        print("Validation result: FAIL")
        for error in result["errors"]:
            print(f"ERROR: {error}")
        return 1
    print("Validation result: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
