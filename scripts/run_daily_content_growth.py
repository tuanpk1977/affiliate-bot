from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.content_growth_pipeline import run_daily_content_growth


def run_topic_scoring_dry_run() -> dict:
    from scripts.score_topics import score_topic_file

    input_path = "data/trending_topics.json"
    output_path = "data/topic_scores.json"
    dashboard_path = "data/topic_dashboard.json"
    plan_path = "data/topic_plan.json"
    rules_path = "data/topic_scoring_rules.json"

    scored = score_topic_file(input_path, output_path, dashboard_path, plan_path, rules_path)
    return {
        "enabled": True,
        "topics": len(scored),
        "input": input_path,
        "outputs": [output_path, dashboard_path, plan_path],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a daily AI content growth batch.")
    parser.add_argument("--limit", type=int, default=10, help="Number of topics to generate. Default: 10.")
    parser.add_argument("--discover", action="store_true", help="Run trend discovery before selecting topics.")
    parser.add_argument("--no-build", action="store_true", help="Skip build_site.py and docs sync.")
    parser.add_argument("--no-indexnow", action="store_true", help="Skip IndexNow submission.")
    parser.add_argument("--dry-run", action="store_true", help="Select topics and write report only; no articles or assets.")
    parser.add_argument("--score-topics", action="store_true", help="Dry-run only: score data/trending_topics.json and write data/topic_*.json outputs.")
    args = parser.parse_args()

    if args.score_topics and not args.dry_run:
        raise SystemExit("--score-topics is only available with --dry-run.")

    report = run_daily_content_growth(
        limit=args.limit,
        discover=args.discover,
        build=not args.no_build,
        submit_indexnow_enabled=not args.no_indexnow,
        dry_run=args.dry_run,
    )
    topic_scoring = run_topic_scoring_dry_run() if args.score_topics else {"enabled": False}
    print(json.dumps({
        "generated": len(report.get("generated_pages", [])),
        "dry_run": report.get("dry_run"),
        "build": report.get("build"),
        "indexnow": report.get("indexnow"),
        "topic_scoring": topic_scoring,
    }, indent=2, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
