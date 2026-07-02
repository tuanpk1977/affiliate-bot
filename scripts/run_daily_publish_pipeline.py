from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

WORKFLOW_TZ = timezone(timedelta(hours=7))

from modules.ctr_title_engine import write_title_tests
from modules.content_operations import write_content_operations_outputs
from modules.daily_content_factory import write_daily_factory_outputs
from modules.morning_dashboard import write_morning_outputs
from modules.performance_tracking import DATA_DIR, read_csv
from modules.video_package_generator import generate_video_package
from modules.website_publisher import publish_selected_articles


def run_command(args: list[str]) -> int:
    print("Running:", " ".join(args))
    completed = subprocess.run(args, cwd=ROOT)
    if completed.returncode != 0:
        print(f"WARNING: command failed with exit code {completed.returncode}: {' '.join(args)}")
    return completed.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description="Daily AI Content Factory. Generates recommendations, article drafts/source, and video packages without deployment.")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--publish", action="store_true", help="Write approved local source pages to data/published_static_pages. Does not deploy.")
    parser.add_argument("--generate-video-packages", action="store_true", help="Create manual YouTube package files in video_output.")
    parser.add_argument("--submit-indexnow", action="store_true", help="Reserved explicit flag. No IndexNow is submitted by this pipeline before deployment.")
    parser.add_argument("--skip-discovery", "--skip-discover", dest="skip_discovery", action="store_true", help="Use existing topic_scores.json instead of running discovery/scoring.")
    parser.add_argument("--skip-competitor-scan", action="store_true", help="Skip the optional RSS/sitemap competitor trend scan.")
    parser.add_argument("--max-per-source", type=int, default=80)
    parser.add_argument("--timeout", type=int, default=None)
    args = parser.parse_args()

    if args.submit_indexnow:
        print("WARNING: --submit-indexnow was provided, but this pipeline does not submit IndexNow without deployment.")

    weekday = datetime.now(WORKFLOW_TZ).weekday()
    workflow_mode = "hottrend" if weekday == 0 else "weekly_cluster"
    if workflow_mode == "weekly_cluster":
        print("Workflow mode: weekly_cluster (Tuesday-Sunday). Using the current week's Weekly Topic Cluster.")
    else:
        print("Workflow mode: hottrend (Monday). Running discovery/scoring for fresh topics.")

    if not args.skip_discovery and workflow_mode == "hottrend":
        planner_args = [
            sys.executable,
            "scripts/run_hottrend_daily_planner.py",
            "--limit",
            str(args.limit),
            "--max-per-source",
            str(args.max_per_source),
        ]
        if args.timeout is not None:
            planner_args.extend(["--timeout", str(args.timeout)])
        run_command(planner_args)
        if not args.skip_competitor_scan:
            run_command(
                [
                    sys.executable,
                    "scripts/scan_competitor_trends.py",
                    "--max-items",
                    "8",
                    "--delay",
                    "1.0",
                ]
            )
    elif not args.skip_discovery and workflow_mode == "weekly_cluster":
        print("Skipping hottrend discovery because the daily guide says Tuesday-Sunday must use the current week's Weekly Topic Cluster.")

    operations = write_content_operations_outputs()
    factory = write_daily_factory_outputs(limit=args.limit, workflow_mode=workflow_mode)
    selected_rows = read_csv(DATA_DIR / "today_selected_topics.csv")
    title_result = write_title_tests(selected_rows)
    publish_reports = publish_selected_articles(DATA_DIR / "today_selected_topics.csv", limit=args.limit, publish=args.publish)
    video_reports = []
    if args.generate_video_packages:
        package_source_rows = publish_reports or selected_rows
        video_reports = [generate_video_package(row) for row in package_source_rows[: args.limit]]

    morning_result = write_morning_outputs(selected_rows[: args.limit], publish_reports, video_reports)

    validation_code = run_command([sys.executable, "scripts/validate_excel_workbook.py"])
    published_count = sum(1 for row in publish_reports if str(row.get("status", "")).startswith(("published", "refreshed")))
    print("Daily AI Content Factory complete.")
    print(f"Operations topics: {operations.get('topics', 0)}")
    print(f"Selected topics: {factory.get('selected_topics', 0)}")
    print(f"Title variants: {title_result.get('title_tests', 0)}")
    print(f"Articles written/refreshed locally: {len(publish_reports)}")
    print(f"Published local source pages: {published_count}")
    print(f"Video packages: {len(video_reports)}")
    print(f"Morning Command Center rows: {morning_result.get('morning_rows', 0)}")
    print(f"Workbook validation exit code: {validation_code}")
    print("No deploy, no commit, no push, no social post, no YouTube upload, no IndexNow submission.")
    return 0 if validation_code == 0 else validation_code


if __name__ == "__main__":
    raise SystemExit(main())
