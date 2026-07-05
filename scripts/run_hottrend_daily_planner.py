from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run_command(args: list[str]) -> None:
    print("Running:", " ".join(args))
    completed = subprocess.run(args, cwd=ROOT)
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)


def good_topic_count(min_score: float) -> int:
    path = ROOT / "data" / "topic_scores.json"
    if not path.exists():
        return 0
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        return 0
    return sum(1 for row in data if isinstance(row, dict) and float(row.get("total_score") or 0) >= min_score)


def run_planning_round(limit: int, max_per_source: int, timeout: int | None) -> None:
    discover = [
        sys.executable,
        "scripts/discover_ai_trends.py",
        "--limit",
        str(limit),
        "--max-per-source",
        str(max_per_source),
    ]
    if timeout is not None:
        discover.extend(["--timeout", str(timeout)])
    score = [
        sys.executable,
        "scripts/score_topics.py",
        "--input",
        "data/trending_topics.json",
        "--output",
        "data/topic_scores.json",
        "--dashboard-output",
        "data/topic_dashboard.json",
        "--plan-output",
        "data/topic_plan.json",
        "--rules",
        "data/topic_scoring_rules.json",
        "--update-history",
    ]
    ceo_dashboard = [sys.executable, "scripts/build_ceo_dashboard.py"]
    intelligence_dashboard = [sys.executable, "scripts/build_content_intelligence_dashboard.py"]
    business_dashboard = [sys.executable, "scripts/build_business_intelligence_dashboard.py"]
    today_write_plan = [sys.executable, "scripts/run_today_write_plan.py"]
    run_command(discover)
    run_command(score)
    run_command(ceo_dashboard)
    run_command(intelligence_dashboard)
    run_command(business_dashboard)
    run_command(today_write_plan)


def run_once(limit: int, max_per_source: int, timeout: int | None, target_good_topics: int, min_good_score: float, max_crawl_rounds: int) -> None:
    crawl_size = max_per_source
    for round_index in range(1, max_crawl_rounds + 1):
        run_planning_round(limit=limit, max_per_source=crawl_size, timeout=timeout)
        good_count = good_topic_count(min_good_score)
        print(f"Good topics found: {good_count}/{target_good_topics} with score >= {min_good_score}")
        if good_count >= target_good_topics:
            break
        if round_index >= max_crawl_rounds or crawl_size >= 300:
            print("Stopping crawl expansion: weak topics remain Monitor/Skip instead of being forced into today's winners.")
            break
        crawl_size = min(300, max(crawl_size + 40, crawl_size * 2))
        print(f"Expanding discovery crawl to max_per_source={crawl_size}")
    print("Hottrend daily planning complete. No articles, videos, social posts, deploys, or IndexNow submissions were run.")


def seconds_until(hour: int, minute: int) -> float:
    now = datetime.now()
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return max(1.0, (target - now).total_seconds())


def run_schedule(limit: int, max_per_source: int, timeout: int | None, hour: int, minute: int, target_good_topics: int, min_good_score: float, max_crawl_rounds: int) -> None:
    print(f"Hottrend planner scheduler started. Next runs are daily at {hour:02d}:{minute:02d} local time.")
    while True:
        wait_seconds = seconds_until(hour, minute)
        print(f"Waiting {round(wait_seconds / 60, 1)} minutes until next planning run.")
        time.sleep(wait_seconds)
        run_once(
            limit=limit,
            max_per_source=max_per_source,
            timeout=timeout,
            target_good_topics=target_good_topics,
            min_good_score=min_good_score,
            max_crawl_rounds=max_crawl_rounds,
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the safe daily hottrend planning workflow only.")
    parser.add_argument("--limit", type=int, default=10, help="Number of selected daily winners to keep in discovery output.")
    parser.add_argument("--max-per-source", type=int, default=80, help="Signals retained from each discovery source.")
    parser.add_argument("--timeout", type=int, default=None, help="HTTP timeout for discovery connectors.")
    parser.add_argument("--schedule", action="store_true", help="Keep running and execute daily at the configured local time.")
    parser.add_argument("--hour", type=int, default=6, help="Local hour for scheduled runs.")
    parser.add_argument("--minute", type=int, default=0, help="Local minute for scheduled runs.")
    parser.add_argument("--target-good-topics", type=int, default=10, help="Desired number of topics scoring at or above --min-good-score.")
    parser.add_argument("--min-good-score", type=float, default=75.0, help="Minimum score counted as a strong daily candidate.")
    parser.add_argument("--max-crawl-rounds", type=int, default=3, help="Maximum discovery/scoring retry rounds before stopping.")
    args = parser.parse_args()

    if args.schedule:
        run_schedule(args.limit, args.max_per_source, args.timeout, args.hour, args.minute, args.target_good_topics, args.min_good_score, args.max_crawl_rounds)
        return 0
    run_once(args.limit, args.max_per_source, args.timeout, args.target_good_topics, args.min_good_score, args.max_crawl_rounds)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
