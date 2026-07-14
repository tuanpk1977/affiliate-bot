from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.codex_writer_workflow import run_codex_daily_writer


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write daily article drafts from queued topics using the repository-local Codex writer.")
    parser.add_argument("--date", default=date.today().isoformat(), help="Batch date in YYYY-MM-DD format.")
    parser.add_argument("--count", type=int, default=10, help="Maximum number of drafts to write.")
    parser.add_argument("--depth", choices=("deep", "standard"), default="deep", help="Draft depth profile.")
    parser.add_argument("--dry-run", action="store_true", help="Preview topic selection and file targets without writing.")
    args = parser.parse_args(argv)
    payload = run_codex_daily_writer(batch_date=args.date, count=args.count, depth=args.depth, dry_run=args.dry_run)
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if payload.get("selected", 0) > 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
