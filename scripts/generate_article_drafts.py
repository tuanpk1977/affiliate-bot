from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from modules.content_writer import generate_drafts_from_today_plan


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate READY_FOR_REVIEW markdown drafts from Today Write Plan.")
    parser.add_argument("--limit", type=int, default=10, help="Maximum drafts to generate.")
    args = parser.parse_args()
    reports = generate_drafts_from_today_plan(limit=args.limit)
    print(f"Drafts generated: {len(reports)}")
    for row in reports:
        print(f"- {row['slug']}: {row['output_file']}")
    print("No website publish, deploy, commit, social post, YouTube upload, or IndexNow submit was run.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
