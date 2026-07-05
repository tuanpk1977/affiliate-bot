from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from modules.content_intelligence import write_collector_output


def main() -> int:
    parser = argparse.ArgumentParser(description="Create/update Google News intelligence output from local CSV/JSON/RSS.")
    parser.add_argument("--input", default="", help="Optional CSV/JSON input.")
    parser.add_argument("--rss", default="", help="Optional local Google News RSS XML file.")
    args = parser.parse_args()
    rows = write_collector_output(
        "google_news",
        input_path=Path(args.input) if args.input else None,
        rss_path=Path(args.rss) if args.rss else None,
    )
    print(f"Google News rows: {len(rows)}")
    print("Output: data/google_news.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
