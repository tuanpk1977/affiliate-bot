from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from modules.performance_tracking import (
    COMPETITOR_GAP_FIELDS,
    COMPETITOR_TARGET_FIELDS,
    DATA_DIR,
    build_competitor_gap_rows,
    build_content_lifecycle,
    ensure_template,
    read_csv,
    update_master_workbook,
    write_csv,
)


def main() -> int:
    targets_path = DATA_DIR / "competitor_targets.csv"
    ensure_template(targets_path, COMPETITOR_TARGET_FIELDS)
    targets = read_csv(targets_path)
    rows = build_competitor_gap_rows(targets, build_content_lifecycle())
    write_csv(DATA_DIR / "competitor_gap_analysis.csv", rows, COMPETITOR_GAP_FIELDS)
    update_master_workbook({"Competitor Gaps": (rows, COMPETITOR_GAP_FIELDS)})
    print(f"Competitor targets: {len(targets)}")
    print(f"Competitor gap rows: {len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
