from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from modules.content_operations import write_content_operations_outputs


def main() -> int:
    result = write_content_operations_outputs()
    print("Content operations dashboard updated.")
    print(f"Topics scored: {result['topics']}")
    print(f"Duplicate checks: {result['duplicates']}")
    print(f"Money ranking rows: {result['money']}")
    print(f"Publishing queue rows: {result['queue']}")
    print(f"AI priority rows: {result['priority']}")
    print(f"Revenue opportunity rows: {result['revenue_opportunity']}")
    print(f"Daily publishing schedule rows: {result['daily_schedule']}")
    print(f"Website publishing queue rows: {result['website_queue']}")
    print(f"Authority rows: {result['authority']}")
    print(f"Content gap rows: {result['content_gap']}")
    print(f"Content cluster rows: {result['clusters']}")
    print(f"Internal link cluster rows: {result['internal_links']}")
    print(f"Today write plan rows: {result['today_write_plan']}")
    print("Workbook: data/master_dashboard.xlsx")
    print("No articles, videos, deploys, commits, or IndexNow submissions were run.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
