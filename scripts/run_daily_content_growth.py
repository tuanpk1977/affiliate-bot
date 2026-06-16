from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.content_growth_pipeline import run_daily_content_growth


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a daily AI content growth batch.")
    parser.add_argument("--limit", type=int, default=10, help="Number of topics to generate. Default: 10.")
    parser.add_argument("--discover", action="store_true", help="Run trend discovery before selecting topics.")
    parser.add_argument("--no-build", action="store_true", help="Skip build_site.py and docs sync.")
    parser.add_argument("--no-indexnow", action="store_true", help="Skip IndexNow submission.")
    parser.add_argument("--dry-run", action="store_true", help="Select topics and write report only; no articles or assets.")
    args = parser.parse_args()

    report = run_daily_content_growth(
        limit=args.limit,
        discover=args.discover,
        build=not args.no_build,
        submit_indexnow_enabled=not args.no_indexnow,
        dry_run=args.dry_run,
    )
    print(json.dumps({
        "generated": len(report.get("generated_pages", [])),
        "dry_run": report.get("dry_run"),
        "build": report.get("build"),
        "indexnow": report.get("indexnow"),
    }, indent=2, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
