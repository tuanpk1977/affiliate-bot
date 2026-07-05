from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from modules.performance_tracking import DATA_DIR, YOUTUBE_FIELDS, ensure_template, parse_youtube_export, write_business_outputs, write_csv


def main() -> int:
    parser = argparse.ArgumentParser(description="Import a manual YouTube Analytics CSV export.")
    parser.add_argument("--input", help="Path to YouTube Analytics CSV export. If omitted, an empty template is created.")
    parser.add_argument("--output", default=str(DATA_DIR / "youtube_analytics.csv"))
    args = parser.parse_args()

    output = Path(args.output)
    if not args.input:
        ensure_template(output, YOUTUBE_FIELDS)
        print("YouTube analytics template verified. No input CSV was imported.")
    else:
        rows = parse_youtube_export(Path(args.input))
        write_csv(output, rows, YOUTUBE_FIELDS)
        print(f"Imported YouTube analytics rows: {len(rows)}")

    result = write_business_outputs()
    print(f"Lifecycle rows: {result['lifecycle']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
