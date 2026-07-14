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
from modules.daily_editorial_workflow import BATCH_STATE_QUEUE_CREATED, BATCH_STATE_WRITING, DailyEditorialWorkflow


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write daily article drafts from queued topics using the repository-local Codex writer.")
    parser.add_argument("--date", default=date.today().isoformat(), help="Batch date in YYYY-MM-DD format.")
    parser.add_argument("--count", type=int, default=10, help="Maximum number of drafts to write.")
    parser.add_argument("--depth", choices=("deep", "standard"), default="deep", help="Draft depth profile.")
    parser.add_argument("--dry-run", action="store_true", help="Preview topic selection and file targets without writing.")
    args = parser.parse_args(argv)
    batch_date = args.date
    if str(batch_date or "").strip().lower() == "latest":
        workflow = DailyEditorialWorkflow()
        batch_date = workflow.resolve_latest_batch_by_state({BATCH_STATE_QUEUE_CREATED, BATCH_STATE_WRITING}) or workflow.latest_queue_date()
        if not batch_date:
            print("No topic queue available. Run Menu 1 or Menu 2 first.", flush=True)
            return 2
    payload = run_codex_daily_writer(batch_date=batch_date, count=args.count, depth=args.depth, dry_run=args.dry_run)
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if payload.get("selected", 0) > 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
