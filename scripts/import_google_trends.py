from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from modules.content_intelligence import write_collector_output


def main() -> int:
    parser = argparse.ArgumentParser(description="Create/update Google Trends intelligence output. Offline-safe by default.")
    parser.add_argument("--input", default="", help="Optional CSV/JSON export with keyword/growth/category columns.")
    parser.add_argument("--country", default="US")
    args = parser.parse_args()
    rows = write_collector_output("google_trends", input_path=Path(args.input) if args.input else None, country=args.country)
    print(f"Google Trends rows: {len(rows)}")
    print("Output: data/google_trends.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
