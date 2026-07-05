from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from modules.website_publisher import publish_selected_articles


def main() -> int:
    parser = argparse.ArgumentParser(description="Create local article previews or write local website source pages from selected topics.")
    parser.add_argument("--selected", default="data/today_selected_topics.csv", help="Selected topics CSV.")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--dry-run", action="store_true", help="Write preview HTML only.")
    parser.add_argument("--publish", action="store_true", help="Write to data/published_static_pages local website source.")
    parser.add_argument("--submit-indexnow", action="store_true", help="Reserved explicit flag. This script does not submit before deployment.")
    args = parser.parse_args()

    if args.submit_indexnow:
        print("WARNING: --submit-indexnow was provided, but this local publisher does not submit IndexNow before deployment.")
    reports = publish_selected_articles(Path(args.selected), limit=args.limit, publish=args.publish and not args.dry_run)
    print(f"Article publish report rows: {len(reports)}")
    print("Report: data/website_publish_report.csv")
    for row in reports:
        print(f"- {row.get('slug')}: {row.get('status')} -> {row.get('output_path')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
