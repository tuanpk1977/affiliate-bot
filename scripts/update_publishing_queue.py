from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from modules.content_operations import PUBLISHING_QUEUE_FIELDS, build_publishing_queue
from modules.performance_tracking import DATA_DIR, write_csv, write_json


def main() -> int:
    rows = build_publishing_queue()
    write_csv(DATA_DIR / "publishing_queue.csv", rows, PUBLISHING_QUEUE_FIELDS)
    write_json(DATA_DIR / "publishing_queue.json", rows)
    print(f"Publishing queue rows: {len(rows)}")
    print("Output: data/publishing_queue.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
