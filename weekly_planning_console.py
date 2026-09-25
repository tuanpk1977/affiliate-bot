from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from modules.weekly_content_planning import (
    WeeklyDeepDiveSelection,
    WeeklyTopicSelection,
    render_deep_dive,
    render_topic_selection,
)
from modules.editorial_topic_strategy import EditorialTopicStrategy


def _timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def parser() -> argparse.ArgumentParser:
    cli = argparse.ArgumentParser(description="Safe weekly content planning for one temporary or two approved root topics.")
    commands = cli.add_subparsers(dest="command", required=True)

    topic = commands.add_parser("topic-selection", help="Rank candidates and approve up to two weekly roots.")
    topic.add_argument("--seed", action="append", default=[])
    topic.add_argument("--file", action="append", type=Path, default=[])
    topic.add_argument("--select", nargs="+", type=int, metavar="INDEX")

    deep_dive = commands.add_parser("deep-dive-selection", help="Recommend deep dives under the two locked weekly roots.")
    deep_dive.add_argument("--decision", help="Operator decision: Y, YES, N, NO, E, EDIT, C, or Q.")
    for command in (topic, commands.choices["deep-dive-selection"]):
        command.add_argument("--date", help="ISO date or datetime; defaults to the current Asia/Bangkok operating date.")
        command.add_argument("--dry-run", action="store_true", help="Analyze and report without writing files.")
        command.add_argument("--yes", action="store_true", help="Approve the displayed default selection non-interactively.")
        command.add_argument("--json", action="store_true", help="Print the complete JSON report.")
    partner = commands.add_parser("partner-opportunities", help="Read-only local PartnerStack opportunity report.")
    partner.add_argument("--json", action="store_true", help="Print the complete JSON report.")
    return cli


def main() -> int:
    args = parser().parse_args()
    if args.command == "partner-opportunities":
        report = EditorialTopicStrategy(Path.cwd()).partner_report()
        if args.json:
            print(json.dumps(report, indent=2, ensure_ascii=False, default=str))
        else:
            print("PARTNER OPPORTUNITY REPORT (READ-ONLY)")
            print(f"Candidates: {report['candidate_count']}")
            print("Input: manual local JSON/CSV; paid API used: NO; weekly plan changed: NO")
            for row in report["candidates"]:
                print(f"- {row.get('program_name')} | tier={row.get('topic_tier')} | category={row.get('category')} | signal_eligible={row.get('eligible_as_signal')}")
        return 0
    now = _timestamp(args.date)
    if args.command == "topic-selection":
        workflow = WeeklyTopicSelection(Path.cwd(), now=now)
        previewed = False

        def show_topic_candidates(candidate_report: dict[str, object]) -> None:
            nonlocal previewed
            print(render_topic_selection(candidate_report))
            previewed = True

        report = workflow.run(
            seeds=args.seed or None,
            imports=args.file,
            dry_run=args.dry_run,
            yes=args.yes,
            selected_indexes=args.select,
            preview=None if args.json or args.dry_run or args.yes else show_topic_candidates,
        )
        rendered = render_topic_selection(report)
    else:
        workflow = WeeklyDeepDiveSelection(Path.cwd(), now=now)
        report = workflow.detect()
        if not args.json:
            print(render_deep_dive(report))
        if not args.dry_run and not report.get("blocked") and report.get("status") == "REVIEW":
            report = workflow.review(
                report,
                decision="Y" if args.yes else args.decision,
                interactive=sys.stdin.isatty() or bool(args.yes or args.decision),
            )
        rendered = render_deep_dive(report)
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False, default=str))
    elif args.command == "topic-selection":
        if not previewed:
            print(rendered)
        else:
            print(f"Result: {report.get('persistence_status') or report.get('status')} - {report.get('reason', '')}")
    elif report.get("status") not in {"REVIEW"}:
        print(f"Result: {report.get('status')} - {report.get('reason')}")
        if report.get("rerun_command"):
            print(f"Rerun: {report['rerun_command']}")
    for key in ("plan_path", "weekly_root_manifest", "deep_dive_plan_path"):
        if report.get(key):
            print(f"- {key}: {report[key]}")
    not_ready = report.get("blocked") or report.get("status") == "EDIT_REQUIRED"
    return 2 if not_ready else 0


if __name__ == "__main__":
    raise SystemExit(main())
