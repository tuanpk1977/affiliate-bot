from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.editorial_automation import WeeklyTrendIntelligenceEngine  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run weekly editorial intelligence, ranking, and calendar generation.")
    parser.add_argument("--candidate-limit", type=int, default=None, help="Maximum candidate topics to retain.")
    parser.add_argument("--top-topics", type=int, default=None, help="Number of weekly topics to select.")
    parser.add_argument("--max-per-source", type=int, default=None, help="Maximum signals per source.")
    args = parser.parse_args()

    engine = WeeklyTrendIntelligenceEngine(
        candidate_limit=args.candidate_limit,
        top_topics=args.top_topics,
        max_per_source=args.max_per_source,
    )
    result = engine.run_weekly_cycle()
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
