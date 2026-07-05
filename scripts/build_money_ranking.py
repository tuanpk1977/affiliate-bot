from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from modules.content_operations import MONEY_RANKING_FIELDS, build_money_ranking
from modules.performance_tracking import DATA_DIR, write_csv, write_json


def main() -> int:
    rows = build_money_ranking()
    write_csv(DATA_DIR / "money_ranking.csv", rows, MONEY_RANKING_FIELDS)
    write_json(DATA_DIR / "money_ranking.json", rows)
    print(f"Money ranking rows: {len(rows)}")
    print("Output: data/money_ranking.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
