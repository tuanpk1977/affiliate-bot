from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from modules.daily_content_factory import build_refresh_queue, build_today_selected_topics, REFRESH_QUEUE_FIELDS
from modules.performance_tracking import DATA_DIR, write_csv, write_json


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a refresh queue from selected topics. Does not modify articles unless a future --refresh workflow is added.")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--refresh", action="store_true", help="Currently records refresh candidates only; no publishing is performed.")
    args = parser.parse_args()

    selected = build_today_selected_topics(limit=args.limit)
    rows = build_refresh_queue(selected)
    write_csv(DATA_DIR / "refresh_queue.csv", rows, REFRESH_QUEUE_FIELDS)
    write_json(DATA_DIR / "refresh_queue.json", rows)
    print(f"Refresh queue rows: {len(rows)}")
    print("No article files were modified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
