from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.worker_bot.runner import run_worker_bot


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate draft-only content assistant bot output.")
    parser.add_argument("--config", default=None, help="Path to worker bot config JSON.")
    parser.add_argument("--limit", type=int, default=None, help="Maximum topics to generate.")
    parser.add_argument("--date", default=None, help="Run date folder, YYYY-MM-DD. Defaults to today.")
    parser.add_argument("--dry-run", action="store_true", help="Safety label only; worker always writes drafts only.")
    parser.add_argument("--skip-video", action="store_true", help="Skip draft MP4 rendering.")
    parser.add_argument("--force-one-test", action="store_true", help="Generate one draft even if all candidates are duplicates.")
    args = parser.parse_args()

    summary = run_worker_bot(
        config_path=args.config,
        limit=args.limit,
        run_date=args.date,
        skip_video=args.skip_video,
        force_one_test=args.force_one_test,
    )
    print("Content Assistant Bot complete")
    print(f"Output: {summary['output_root']}")
    print(f"Candidates: {summary['candidates']}")
    print(f"Selected: {summary['selected']}")
    print(f"Generated: {summary['generated']}")
    print("Safety: no publish, no deploy, no YouTube upload, no social post, no IndexNow")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
