from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from modules.performance_tracking import DATA_DIR, INTERNAL_LINK_FIELDS, build_content_lifecycle, recommend_internal_links, update_master_workbook, write_csv


def main() -> int:
    parser = argparse.ArgumentParser(description="Recommend internal links from lifecycle/topic data. Dry-run by default.")
    parser.add_argument("--apply", action="store_true", help="Reserved for future source edits. Current implementation still reports only.")
    args = parser.parse_args()

    rows = recommend_internal_links(build_content_lifecycle())
    if args.apply:
        for row in rows:
            row["status"] = "apply_requested_not_modified"
    write_csv(DATA_DIR / "internal_link_recommendations.csv", rows, INTERNAL_LINK_FIELDS)
    update_master_workbook({"Internal Link Ideas": (rows, INTERNAL_LINK_FIELDS)})
    print(f"Internal link recommendations: {len(rows)}")
    if args.apply:
        print("Apply mode is intentionally non-mutating in this safe integration. No article files were changed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
