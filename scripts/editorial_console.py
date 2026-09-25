from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.editorial_operations_console import EditorialOperationsConsole  # noqa: E402


def _load_daily_console():
    """Load the canonical root CLI without colliding with this legacy module.

    Some test runners and operator shells put ``scripts/`` before the project
    root on ``sys.path``.  In that situation ``import editorial_console`` used
    to select this legacy approval CLI and silently lose the daily commands.
    """
    module_name = "_affiliate_bot_daily_editorial_console"
    loaded = sys.modules.get(module_name)
    if loaded is not None:
        return loaded
    spec = importlib.util.spec_from_file_location(module_name, ROOT / "editorial_console.py")
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise RuntimeError("Canonical editorial_console.py could not be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


# Expose the canonical workflow dependency for callers/tests that imported the
# legacy path because of sys.path ordering.  main() propagates any patch of this
# symbol before delegating.
_CANONICAL_CONSOLE = _load_daily_console()
DailyEditorialWorkflow = _CANONICAL_CONSOLE.DailyEditorialWorkflow
PublishLock = _CANONICAL_CONSOLE.PublishLock
_start_publish_watch = _CANONICAL_CONSOLE._start_publish_watch


_DAILY_COMMANDS = {
    "trend", "daily-followup", "morning", "draft", "prepare-research",
    "comparator-candidates", "confirm-comparators", "hold-comparators",
    "codex-write", "approve", "reject", "publish", "publish-ready",
    "publish-exact-slug", "validate-batch", "prepare-article-output",
    "publish-dry-run", "autofix-batch", "request-topic", "partner-intake",
    "status", "check-live", "diagnose-article", "diagnose-batch",
    "build-selected", "publish-lock-status", "clear-stale-publish-lock",
    "clear-stale-weekly-lock", "recover-interrupted-preparation",
    "reset-unpublished", "serve",
}


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
    effective_argv = list(sys.argv[1:] if argv is None else argv)
    if effective_argv and effective_argv[0] in _DAILY_COMMANDS:
        daily_console = _load_daily_console()
        daily_console.DailyEditorialWorkflow = DailyEditorialWorkflow
        daily_console.PublishLock = PublishLock
        daily_console._start_publish_watch = _start_publish_watch
        return daily_console.main(effective_argv)
    parser = build_parser()
    args = parser.parse_args(effective_argv)
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
