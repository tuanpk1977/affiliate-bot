from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.editorial_automation import run_daily_editorial_content  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate only today's scheduled editorial content.")
    parser.add_argument("--date", default="", help="ISO date override. Defaults to today.")
    parser.add_argument("--build", action="store_true", help="Run incremental local build after generation.")
    args = parser.parse_args()

    target_date = date.fromisoformat(args.date) if args.date else None
    result = run_daily_editorial_content(target_date=target_date, build=args.build)
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    return 0 if result.get("generated_pages") else 1


if __name__ == "__main__":
    raise SystemExit(main())
