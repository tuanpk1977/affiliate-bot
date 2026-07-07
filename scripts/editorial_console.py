from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.editorial_operations_console import EditorialOperationsConsole  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Local editorial operations console for human approval and safe local publish.")
    parser.add_argument("--list", action="store_true", help="List all pending human approvals.")
    parser.add_argument("--build", action="store_true", help="Rebuild the editorial operations console and dashboard outputs.")
    parser.add_argument("--approve", metavar="SLUG", help="Approve one slug for human review.")
    parser.add_argument("--reject", metavar="SLUG", help="Reject one slug for human review.")
    parser.add_argument("--reason", default="", help="Reason to store when rejecting a slug.")
    parser.add_argument("--publish", metavar="SLUG", help="Publish one locally approved slug to local output only.")
    parser.add_argument("--publish-all", action="store_true", help="Publish all slugs already approved for local publish.")
    parser.add_argument("--request-topic", metavar="TOPIC", help="Create a research package and draft for a custom requested topic.")
    parser.add_argument("--category", default="", help="Optional category for a custom requested topic.")
    parser.add_argument("--intent", default="", help="Optional intent hint for a custom requested topic.")
    parser.add_argument("--approver", default="editor", help="Name to record for approval or rejection actions.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    console = EditorialOperationsConsole()

    if args.list:
        print(json.dumps({"pending_approvals": console.list_pending_approvals()}, indent=2, ensure_ascii=False))
        return 0

    if args.approve:
        print(json.dumps(console.approve_slug(args.approve, approver=args.approver), indent=2, ensure_ascii=False))
        return 0

    if args.reject:
        if not args.reason.strip():
            parser.error("--reason is required with --reject")
        print(json.dumps(console.reject_slug(args.reject, reason=args.reason.strip(), approver=args.approver), indent=2, ensure_ascii=False))
        return 0

    if args.publish:
        print(json.dumps(console.publish_slug(args.publish), indent=2, ensure_ascii=False))
        return 0

    if args.publish_all:
        print(json.dumps(console.publish_all_approved(), indent=2, ensure_ascii=False))
        return 0

    if args.request_topic:
        print(
            json.dumps(
                console.request_custom_topic(args.request_topic, category=args.category, intent=args.intent),
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0

    if args.build or not any((args.list, args.approve, args.reject, args.publish, args.publish_all, args.request_topic)):
        print(json.dumps(console.rebuild_outputs(), indent=2, ensure_ascii=False))
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
