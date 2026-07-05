from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from modules.content_intelligence import write_collector_output


def main() -> int:
    parser = argparse.ArgumentParser(description="Create/update Product Hunt intelligence from a local CSV/JSON export.")
    parser.add_argument("--input", default="", help="Optional CSV/JSON with product/votes/comments/category.")
    args = parser.parse_args()
    rows = write_collector_output("producthunt", input_path=Path(args.input) if args.input else None)
    print(f"Product Hunt rows: {len(rows)}")
    print("Output: data/producthunt_dashboard.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
