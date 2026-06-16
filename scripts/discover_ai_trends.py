from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from modules.ai_trend_discovery import TrendDiscoveryEngine, save_discovery_result  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Discover and score AI/SaaS topics without generating articles.")
    parser.add_argument("--limit", type=int, default=10, help="Number of topics to select.")
    parser.add_argument("--max-per-source", type=int, default=40, help="Maximum signals retained from each source.")
    parser.add_argument("--timeout", type=int, default=None, help="HTTP timeout in seconds.")
    args = parser.parse_args()

    engine = TrendDiscoveryEngine(timeout=args.timeout, max_per_source=args.max_per_source)
    result = engine.run(limit=max(1, args.limit))
    json_path, report_path = save_discovery_result(result)
    print(f"AI trend discovery complete: selected={len(result.selected_topics)} candidates={result.candidates_evaluated}")
    for rank, topic in enumerate(result.selected_topics, 1):
        print(f"{rank:02d}. {topic.topic} | score={topic.total_score} | confidence={topic.confidence}")
    print(f"JSON: {json_path}")
    print(f"Daily report: {report_path}")
    print("Articles generated: 0")
    return 0 if result.selected_topics else 1


if __name__ == "__main__":
    raise SystemExit(main())
