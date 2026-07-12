from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
import time
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.daily_editorial_workflow import DailyEditorialWorkflow  # noqa: E402
from modules.review_dashboard_server import ReviewDashboardServer  # noqa: E402
from modules.publish_lock import PublishLock  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Daily editorial automation workflow.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    today = date.today().isoformat()

    trend = subparsers.add_parser("trend", help="Find, score, and queue trending editorial topics.")
    trend.add_argument("--count", type=int, default=10, help="Number of topics to select.")
    trend.add_argument("--mode", choices=("standard", "advanced"), default="standard", help="Topic generation mode.")
    trend.add_argument("--date", default=today, help="Batch date in YYYY-MM-DD format. Defaults to today.")
    trend.add_argument("--dry-run", action="store_true", help="Preview topic selection without writing any queue, batch, dashboard, or state files.")
    trend.add_argument("--confirm", action="store_true", help="Required for real topic queue creation.")
    trend.add_argument("--timeout", type=int, default=300, help="Outer timeout in seconds for real topic generation.")
    trend.add_argument("--retries", type=int, default=1, help="Bounded retry count for real topic generation.")

    morning = subparsers.add_parser("morning", help="Run trend discovery and draft generation, then build the review dashboard.")
    morning.add_argument("--count", type=int, default=10, help="Number of topics to select.")
    morning.add_argument("--mode", choices=("standard", "advanced"), default="standard", help="Topic generation mode.")
    morning.add_argument("--date", default=today, help="Batch date in YYYY-MM-DD format. Defaults to today.")
    morning.add_argument("--open", action="store_true", help="Open the daily review dashboard after generation.")
    morning.add_argument("--confirm", action="store_true", help="Required for real week-start generation.")
    morning.add_argument("--timeout", type=int, default=900, help="Outer timeout in seconds for real week-start generation.")
    morning.add_argument("--retries", type=int, default=1, help="Bounded retry count for real week-start generation.")

    draft = subparsers.add_parser("draft", help="Generate article drafts for a queued date.")
    draft.add_argument("--date", default=today, help="Batch date in YYYY-MM-DD format. Defaults to today.")

    approve = subparsers.add_parser("approve", help="Approve one draft inside a daily batch.")
    approve.add_argument("--slug", required=True, help="Article slug.")
    approve.add_argument("--date", default=today, help="Batch date in YYYY-MM-DD format. Defaults to today.")
    approve.add_argument("--approver", default="editor", help="Recorded approver name.")

    reject = subparsers.add_parser("reject", help="Reject one draft inside a daily batch.")
    reject.add_argument("--slug", required=True, help="Article slug.")
    reject.add_argument("--date", default=today, help="Batch date in YYYY-MM-DD format. Defaults to today.")
    reject.add_argument("--reason", required=True, help="Rejection reason.")
    reject.add_argument("--approver", default="editor", help="Recorded approver name.")

    publish = subparsers.add_parser("publish", help="Publish one approved daily batch.")
    publish.add_argument("--date", default=today, help="Batch date in YYYY-MM-DD format. Defaults to today.")

    publish_ready = subparsers.add_parser("publish-ready", help="Publish only articles that already passed the publish gate.")
    publish_ready.add_argument("--date", default=today, help="Batch date in YYYY-MM-DD format. Defaults to today.")
    publish_ready.add_argument("--validation-mode", choices=("smart", "strict"), default="smart", help="Validation mode. Smart validates only today's selected articles; strict validates the full site.")

    validate_batch = subparsers.add_parser("validate-batch", help="Validate a batch without pushing GitHub.")
    validate_batch.add_argument("--date", default=today, help="Batch date in YYYY-MM-DD format. Defaults to today.")
    validate_batch.add_argument("--mode", choices=("smart", "strict"), default="smart", help="Validation mode.")

    prepare_article_output = subparsers.add_parser("prepare-article-output", help="Build public output files for one Ready for Publish article without publishing it.")
    prepare_article_output.add_argument("--date", default=today, help="Batch date in YYYY-MM-DD format. Defaults to today.")
    prepare_article_output.add_argument("--slug", required=True, help="Article slug.")

    publish_dry_run = subparsers.add_parser("publish-dry-run", help="Show the exact publish plan for one Ready for Publish article without committing or pushing.")
    publish_dry_run.add_argument("--date", default=today, help="Batch date in YYYY-MM-DD format. Defaults to today.")
    publish_dry_run.add_argument("--slug", help="Optional article slug. Without it, report every exact candidate in the batch.")
    publish_dry_run.add_argument("--validation-mode", choices=("smart", "strict"), default="smart", help="Validation mode for the dry run.")

    autofix_batch = subparsers.add_parser("autofix-batch", help="Auto-fix simple publish validation issues for the batch.")
    autofix_batch.add_argument("--date", default=today, help="Batch date in YYYY-MM-DD format. Defaults to today.")

    request_topic = subparsers.add_parser("request-topic", help="Create a custom affiliate/content topic draft outside the daily batch.")
    request_topic.add_argument("--topic", required=True, help="Requested topic title or keyword.")
    request_topic.add_argument("--category", default="", help="Optional category.")
    request_topic.add_argument("--intent", default="commercial research", help="Optional intent hint.")
    request_topic.add_argument("--source-url", default="", help="Optional official/source URL for the requested topic.")
    request_topic.add_argument("--official-url", default="", help="Official website URL.")
    request_topic.add_argument("--affiliate-url", default="", help="Affiliate program or tracking URL.")
    request_topic.add_argument("--pricing-url", default="", help="Pricing page URL.")
    request_topic.add_argument("--count", type=int, default=1, help="Number of drafts to generate for the custom topic cluster.")
    request_topic.add_argument("--open", action="store_true", help="Open the operator console after generating the draft.")

    partner_intake = subparsers.add_parser("partner-intake", help="Create an affiliate partner profile and generate a content cluster for review.")
    partner_intake.add_argument("--name", required=True, help="Partner or product name.")
    partner_intake.add_argument("--official-url", default="", help="Official website URL.")
    partner_intake.add_argument("--affiliate-url", default="", help="Affiliate program URL.")
    partner_intake.add_argument("--pricing-url", default="", help="Pricing page URL.")
    partner_intake.add_argument("--contact-note", default="", help="Optional contact or outreach note.")
    partner_intake.add_argument("--commission-note", default="", help="Optional commission note.")
    partner_intake.add_argument("--payout-note", default="", help="Optional payout note.")
    partner_intake.add_argument("--count", type=int, default=8, help="Number of cluster articles to generate.")
    partner_intake.add_argument("--date", default=today, help="Batch date in YYYY-MM-DD format. Defaults to today.")
    partner_intake.add_argument("--open", action="store_true", help="Open the operator console after generating the cluster.")

    status = subparsers.add_parser("status", help="Show daily batch status.")
    status.add_argument("--date", default=today, help="Batch date in YYYY-MM-DD format. Defaults to today.")
    status.add_argument("--json", action="store_true", help="Print the complete status payload.")

    check_live = subparsers.add_parser("check-live", help="Check whether articles are only local, synced to docs, pushed to GitHub, or likely live on the domain.")
    check_live.add_argument("--date", default=today, help="Batch date in YYYY-MM-DD format. Defaults to today.")
    check_live.add_argument("--all", action="store_true", help="Check every article currently present in publish_queue.json, not only the selected batch date.")
    check_live.add_argument("--blocked-only", action="store_true", help="Show only blocked articles inside the live-status report.")
    check_live.add_argument("--open", action="store_true", help="Open the generated HTML live-status report.")

    diagnose = subparsers.add_parser("diagnose-article", help="Inspect one article publish-gate decision without modifying files.")
    diagnose.add_argument("--date", default=today, help="Batch date in YYYY-MM-DD format. Defaults to today.")
    diagnose.add_argument("--slug", required=True, help="Article slug.")

    diagnose_batch = subparsers.add_parser("diagnose-batch", help="Show deterministic publish selection diagnostics without changing state.")
    diagnose_batch.add_argument("--date", default=today)

    build_selected = subparsers.add_parser("build-selected", help="Prepare and run one bounded targeted build for an exact Ready for Publish slug.")
    build_selected.add_argument("--date", default=today)
    build_selected.add_argument("--slug", required=True)
    build_selected.add_argument("--timeout", type=int, default=180)

    subparsers.add_parser("publish-lock-status", help="Show the current publish process lock.")
    clear_lock = subparsers.add_parser("clear-stale-publish-lock", help="Clear a stale publish lock after PID verification.")
    clear_lock.add_argument("--confirm", action="store_true")

    clear_weekly_lock = subparsers.add_parser("clear-stale-weekly-lock", help="Clear a stale weekly generation lock after PID verification.")
    clear_weekly_lock.add_argument("--week-start", required=True, help="Monday week start in YYYY-MM-DD format.")
    clear_weekly_lock.add_argument("--confirm", action="store_true")

    recover = subparsers.add_parser("recover-interrupted-preparation", help="Restore a non-live, docs-missing interrupted preparation to Ready for Publish.")
    recover.add_argument("--date", default=today)
    recover.add_argument("--slug", required=True)
    recover.add_argument("--confirm", action="store_true")

    reset_unpublished = subparsers.add_parser("reset-unpublished", help="Archive stale unpublished editorial records while preserving live/current content.")
    reset_unpublished.add_argument("--before-date", help="Archive eligible items older than this YYYY-MM-DD date. Defaults to the active batch date.")
    reset_unpublished.add_argument("--apply", action="store_true", help="Apply the reset. Without this flag the command is a dry-run.")
    reset_unpublished.add_argument("--dry-run", action="store_true", help="Explicitly request the default non-mutating preview.")
    reset_unpublished.add_argument("--json", action="store_true", help="Print the complete machine-readable reset plan.")

    open_cmd = subparsers.add_parser("open", help="Show or open the daily dashboard paths.")
    open_cmd.add_argument("--date", default=today, help="Batch date in YYYY-MM-DD format. Defaults to today.")
    open_cmd.add_argument("--master", action="store_true", help="Open upload/dashboard.html instead of the daily review dashboard.")
    open_cmd.add_argument("--operator", action="store_true", help="Open the operator console instead of the daily review dashboard.")
    open_cmd.add_argument("--run", action="store_true", help="Open the selected dashboard file with Explorer.")

    serve = subparsers.add_parser("serve", help="Run the interactive local review dashboard with approve/reject/publish buttons.")
    serve.add_argument("--date", default=today, help="Batch date in YYYY-MM-DD format. Defaults to today.")
    serve.add_argument("--port", type=int, default=8765, help="Local HTTP port.")
    serve.add_argument("--open", action="store_true", help="Open the browser automatically.")

    return parser


def _print_trend_summary(payload: dict) -> None:
    print(f"Date: {payload['date']} | Mode: {payload['mode']} | Topics: {payload['count']}")
    print(f"{'#':<3} {'Keyword':<50} {'Intent':<24} {'Affiliate':>10} {'Comp':>8} {'Avail':>8} {'Fresh':>8} {'Total':>8}")
    for item in payload.get("topics", []):
        raw_score = float(item.get("raw_total_score", item.get("total_score", 0)) or 0)
        final_score = float(item.get("total_score", 0) or 0)
        penalty = float(item.get("duplicate_penalty_applied", 0) or 0)
        total_display = f"{final_score:>8.1f}"
        if penalty > 0:
            total_display = f"{final_score:>4.1f}(-{penalty:.0f})"
        print(
            f"{int(item.get('rank', 0)):<3} "
            f"{str(item.get('keyword', ''))[:50]:<50} "
            f"{str(item.get('search_intent', ''))[:24]:<24} "
            f"{int(item.get('affiliate_monetization_score', 0)):>10} "
            f"{int(item.get('competition_difficulty_score', 0)):>8} "
            f"{int(item.get('product_availability_score', 0)):>8} "
            f"{int(item.get('content_freshness_score', 0)):>8} "
            f"{total_display:>8}"
        )
    warnings = [item for item in payload.get("topics", []) if str(item.get("published_live_duplicate_warning") or "").strip()]
    if warnings:
        print("")
        print("[Duplicate warnings vs published_live_urls.jsonl]")
        for item in warnings:
            warning = str(item.get("published_live_duplicate_warning") or "")
            matched = item.get("published_live_duplicate_match") or {}
            matched_url = str(matched.get("matched_url") or "").strip()
            penalty = float(item.get("duplicate_penalty_applied", 0) or 0)
            raw_score = float(item.get("raw_total_score", item.get("total_score", 0)) or 0)
            final_score = float(item.get("total_score", 0) or 0)
            print(f"- {item.get('slug', '')}: {warning}")
            print(f"  Score: {raw_score:.1f} -> {final_score:.1f} (penalty {penalty:.1f})")
            if matched_url:
                print(f"  URL: {matched_url}")


def _print_trend_dry_run(payload: dict) -> None:
    print(f"Dry-run date: {payload['date']} | Week: {payload['week_start']} | Mode: {payload['mode']} | Topics: {payload['count']}")
    print(f"{'#':<3} {'Primary keyword':<48} {'Intent':<24} {'Slug':<46} {'Src':>3} {'Source':<28} {'Fresh':<10} Collision")
    for index, item in enumerate(payload.get("topics", []), start=1):
        collision = item.get("collision_result") or {}
        collision_text = "collision" if collision.get("has_collision") else "clear"
        print(
            f"{index:<3} "
            f"{str(item.get('primary_keyword', ''))[:48]:<48} "
            f"{str(item.get('search_intent', ''))[:24]:<24} "
            f"{str(item.get('slug', ''))[:46]:<46} "
            f"{int(item.get('source_count', 0)):>3} "
            f"{str(item.get('source_verification_status', ''))[:28]:<28} "
            f"{str(item.get('freshness_status', ''))[:10]:<10} "
            f"{collision_text}"
        )
    print("")
    print("would_create:")
    for path in payload.get("would_create", []):
        print(f"- {path}")
    print(f"Final decision: {payload.get('final_decision', 'FAIL')}")


def _run_with_retries(callable_obj, *, retries: int, timeout: int):
    attempts = max(1, min(int(retries or 0) + 1, 3))
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        started = time.monotonic()
        try:
            result = callable_obj()
            elapsed = time.monotonic() - started
            if elapsed > timeout:
                raise TimeoutError(f"Operation exceeded timeout after completion: {int(elapsed)}s > {timeout}s")
            return result
        except Exception as exc:
            last_error = exc
            if attempt >= attempts:
                break
            print(f"[WARN] Attempt {attempt} failed: {exc}. Retrying once...", flush=True)
    assert last_error is not None
    raise last_error


def _progress_print(message: str) -> None:
    print(message, flush=True)


def _print_candidate_table(diagnostic: dict) -> None:
    print("Publish candidate resolution:")
    print(f"{'Slug':<58} {'Gate':<24} {'Deploy':<14} {'Selected':<8} Reason")
    for row in diagnostic.get("candidates", []):
        print(f"{str(row.get('slug', ''))[:58]:<58} {str(row.get('publish_gate', ''))[:24]:<24} {str(row.get('deployment_status', ''))[:14]:<14} {str(bool(row.get('selected_for_publish'))):<8} {row.get('exclusion_reason', '')}")
    print(f"Selected exactly Ready for Publish: {diagnostic.get('selected_count', 0)}")


def _open_local_path(path: str) -> None:
    target = str(path).strip()
    if not target:
        return
    if sys.platform.startswith("win"):
        os.startfile(target)  # type: ignore[attr-defined]
        return
    subprocess.Popen(["xdg-open", target], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _start_publish_watch(workflow: DailyEditorialWorkflow) -> tuple[threading.Event, threading.Thread, float]:
    stop_event = threading.Event()
    started_at = time.monotonic()

    def _watch() -> None:
        warned_five = False
        warned_ten = False
        while not stop_event.wait(60):
            elapsed = int(time.monotonic() - started_at)
            minutes = max(1, elapsed // 60)
            current = workflow.current_progress_message or "Dang publish..."
            print(f"[INFO] Da chay {minutes} phut - {current}", flush=True)
            if elapsed >= 300 and not warned_five:
                print(f"[INFO] Moc 5 phut - buoc hien tai: {current}", flush=True)
                warned_five = True
            if elapsed >= 600 and not warned_ten:
                print(f"[WARN] Qua 10 phut - van dang o buoc: {current}", flush=True)
                warned_ten = True

    watcher = threading.Thread(target=_watch, daemon=True)
    watcher.start()
    return stop_event, watcher, started_at


def _is_no_ready_publish_error(exc: Exception) -> bool:
    message = str(exc)
    return message.startswith("No articles are ready for publish in batch ")


def _print_no_ready_publish_summary(workflow: DailyEditorialWorkflow, *, batch_date: str) -> None:
    try:
        summary = workflow.status(batch_date=batch_date)
    except Exception as exc:
        print("[INFO] Hôm nay chưa có bài nào đủ điều kiện Ready for Publish.", flush=True)
        print("[INFO] Hãy mở menu 4 để xem Publish Gate và lý do bị chặn.", flush=True)
        print("[INFO] Không có file nào được commit hoặc push.", flush=True)
        print(f"[INFO] Không đọc được tóm tắt batch: {exc}", flush=True)
        return
    top_reasons = list(summary.get("top_block_reasons") or [])[:3]
    print("[INFO] Hôm nay chưa có bài nào đủ điều kiện Ready for Publish.", flush=True)
    print("[INFO] Hãy mở menu 4 để xem Publish Gate và lý do bị chặn.", flush=True)
    print("[INFO] Không có file nào được commit hoặc push.", flush=True)
    print("", flush=True)
    print(f"Batch {summary.get('date', batch_date)}", flush=True)
    print(f"Total articles: {summary.get('total_topics', 0)}", flush=True)
    print(f"Human Approved: {summary.get('human_approved', summary.get('approved', 0))}", flush=True)
    print(f"Ready for Publish: {summary.get('ready_for_publish', 0)}", flush=True)
    print(f"Publish Blocked: {summary.get('publish_blocked', 0)}", flush=True)
    print("", flush=True)
    print("Top reasons:", flush=True)
    if top_reasons:
        for reason in top_reasons:
            print(f"- {reason}", flush=True)
    else:
        print("- No publish-gate block reasons found.", flush=True)
    print("", flush=True)
    print("Next action:", flush=True)
    print("Open menu 4 and review the blocked articles.", flush=True)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    workflow = DailyEditorialWorkflow()
    workflow.set_progress_reporter(_progress_print)
    publish_lock = PublishLock(ROOT / "data" / "publish.lock")

    if args.command == "trend":
        if args.dry_run:
            payload = workflow.trend_dry_run(count=args.count, mode=args.mode, batch_date=args.date)
            _print_trend_dry_run(payload)
            print(json.dumps(payload, indent=2, ensure_ascii=False))
            return 0 if payload.get("final_decision") == "PASS" else 2
        if not args.confirm:
            print("[ERROR] Real topic generation requires a successful dry-run and --confirm.", flush=True)
            print(f"[INFO] Preview first: python editorial_console.py trend --count {args.count} --mode {args.mode} --date {args.date} --dry-run", flush=True)
            return 2
        payload = _run_with_retries(lambda: workflow.trend(count=args.count, mode=args.mode, batch_date=args.date), retries=args.retries, timeout=args.timeout)
        _print_trend_summary(payload)
        print(json.dumps({"saved_to": f"data/editorial_queue/{payload['date']}/topics.json"}, ensure_ascii=False))
        return 0
    if args.command == "morning":
        if not args.confirm:
            print("[ERROR] Real week-start generation requires preview plus --confirm.", flush=True)
            print(f"[INFO] Preview first: python editorial_console.py trend --count {args.count} --mode {args.mode} --date {args.date} --dry-run", flush=True)
            return 2
        payload = _run_with_retries(lambda: workflow.morning_run(count=args.count, mode=args.mode, batch_date=args.date), retries=args.retries, timeout=args.timeout)
        _print_trend_summary(payload["trend"])
        if args.open:
            popen_kwargs: dict[str, object] = {"cwd": ROOT, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
            if sys.platform.startswith("win"):
                popen_kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
            subprocess.Popen([sys.executable, str(ROOT / "editorial_console.py"), "serve", "--date", args.date, "--open"], **popen_kwargs)
        print(
            json.dumps(
                {
                    "dashboard_file": payload["dashboard_file"],
                    "operator_console": payload["operator_console"],
                    "upload_dir": payload["upload_dir"],
                    "master_dashboard": payload["master_dashboard"],
                },
                ensure_ascii=False,
            )
        )
        return 0
    if args.command == "draft":
        print(json.dumps(workflow.draft(batch_date=args.date), indent=2, ensure_ascii=False))
        return 0
    if args.command == "approve":
        print(json.dumps(workflow.approve(slug=args.slug, batch_date=args.date, approver=args.approver), indent=2, ensure_ascii=False))
        return 0
    if args.command == "reject":
        print(
            json.dumps(
                workflow.reject(slug=args.slug, batch_date=args.date, reason=args.reason, approver=args.approver),
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0
    if args.command == "publish":
        stop_event, watcher, started_at = _start_publish_watch(workflow)
        try:
            result = workflow.publish(batch_date=args.date)
        finally:
            stop_event.set()
            watcher.join(timeout=1)
        total_seconds = int(time.monotonic() - started_at)
        print(f"[OK] Publish hoan tat sau {total_seconds} giay.", flush=True)
        post_push = result.get("post_push_live_check") or {}
        if post_push:
            print(f"[POST-PUSH] {post_push.get('message', '')}", flush=True)
            live_items = [item for item in list(post_push.get("items") or []) if str(item.get("status") or "") == "live" and str(item.get("url") or "").strip()]
            if live_items:
                print("[LIVE URLS]", flush=True)
                for item in live_items:
                    print(f"- {item['url']}", flush=True)
        history = result.get("live_url_history") or {}
        if history:
            print(f"[LIVE HISTORY] {history.get('history_jsonl', '')}", flush=True)
            print(f"[LIVE LATEST] {history.get('latest_json', '')}", flush=True)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    if args.command == "publish-ready":
        diagnostic = workflow.diagnose_batch(batch_date=args.date) if hasattr(workflow, "diagnose_batch") else {"candidates": []}
        selected_slugs = [row["slug"] for row in diagnostic["candidates"] if row["selected_for_publish"]]
        _print_candidate_table(diagnostic)
        try:
            publish_lock.acquire(batch_date=args.date, slugs=selected_slugs, command="publish-ready")
        except RuntimeError as exc:
            print(f"[ERROR] {exc}", flush=True)
            return 3
        stop_event, watcher, started_at = _start_publish_watch(workflow)
        try:
            result = workflow.publish_ready(batch_date=args.date, validation_mode=args.validation_mode)
        except ValueError as exc:
            if _is_no_ready_publish_error(exc):
                _print_no_ready_publish_summary(workflow, batch_date=args.date)
                return 2
            print(f"[ERROR] Publish-ready failed: {exc}", flush=True)
            return 1
        except Exception as exc:
            print(f"[ERROR] Publish-ready failed: {exc}", flush=True)
            return 1
        finally:
            stop_event.set()
            watcher.join(timeout=1)
            publish_lock.release()
        total_seconds = int(time.monotonic() - started_at)
        print(f"[OK] Publish-ready hoan tat sau {total_seconds} giay.", flush=True)
        post_push = result.get("post_push_live_check") or {}
        if post_push:
            print(f"[POST-PUSH] {post_push.get('message', '')}", flush=True)
            live_items = [item for item in list(post_push.get("items") or []) if str(item.get("status") or "") == "live" and str(item.get("url") or "").strip()]
            if live_items:
                print("[LIVE URLS]", flush=True)
                for item in live_items:
                    print(f"- {item['url']}", flush=True)
        history = result.get("live_url_history") or {}
        if history:
            print(f"[LIVE HISTORY] {history.get('history_jsonl', '')}", flush=True)
            print(f"[LIVE LATEST] {history.get('latest_json', '')}", flush=True)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    if args.command == "validate-batch":
        print(json.dumps(workflow.validate_batch(batch_date=args.date, mode=args.mode), indent=2, ensure_ascii=False))
        return 0
    if args.command == "prepare-article-output":
        print(json.dumps(workflow.prepare_article_output(batch_date=args.date, slug=args.slug), indent=2, ensure_ascii=False))
        return 0
    if args.command == "publish-dry-run":
        if args.slug:
            result = workflow.publish_dry_run(batch_date=args.date, slug=args.slug, validation_mode=args.validation_mode)
        else:
            diagnostic = workflow.diagnose_batch(batch_date=args.date)
            selected = [row["slug"] for row in diagnostic["candidates"] if row["selected_for_publish"]]
            result = {"date": args.date, "dry_run": True, "candidate_diagnostics": diagnostic, "selected_slugs": selected, "results": [workflow.publish_dry_run(batch_date=args.date, slug=slug, validation_mode=args.validation_mode) for slug in selected], "note": "No build, output write, queue mutation, git action, approval, publish, or indexing submission was performed."}
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    if args.command == "diagnose-batch":
        print(json.dumps(workflow.diagnose_batch(batch_date=args.date), indent=2, ensure_ascii=False))
        return 0
    if args.command == "build-selected":
        print(json.dumps(workflow.build_selected(batch_date=args.date, slug=args.slug, timeout=args.timeout), indent=2, ensure_ascii=False))
        return 0
    if args.command == "publish-lock-status":
        print(json.dumps(publish_lock.read(), indent=2, ensure_ascii=False))
        return 0
    if args.command == "clear-stale-publish-lock":
        try:
            print(json.dumps(publish_lock.clear_stale(confirm=args.confirm), indent=2, ensure_ascii=False))
            return 0
        except (ValueError, RuntimeError) as exc:
            print(f"[ERROR] {exc}")
            return 2
    if args.command == "clear-stale-weekly-lock":
        try:
            print(json.dumps(workflow.clear_stale_weekly_lock(week_start=args.week_start, confirm=args.confirm), indent=2, ensure_ascii=False))
            return 0
        except (ValueError, RuntimeError) as exc:
            print(f"[ERROR] {exc}")
            return 2
    if args.command == "recover-interrupted-preparation":
        try:
            print(json.dumps(workflow.recover_interrupted_preparation(batch_date=args.date, slug=args.slug, confirm=args.confirm), indent=2, ensure_ascii=False))
            return 0
        except ValueError as exc:
            print(f"[ERROR] {exc}")
            return 2
    if args.command == "autofix-batch":
        print(json.dumps(workflow.autofix_batch(batch_date=args.date), indent=2, ensure_ascii=False))
        return 0
    if args.command == "request-topic":
        result = workflow.request_custom_topic(
            topic_name=args.topic,
            official_url=args.official_url or args.source_url,
            affiliate_url=args.affiliate_url,
            pricing_url=args.pricing_url,
            category=args.category,
            intent=args.intent,
            count=args.count,
            batch_date=today if not hasattr(args, "date") else getattr(args, "date", today),
        )
        if args.open:
            _open_local_path(str(workflow.console.console_html))
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    if args.command == "partner-intake":
        result = workflow.partner_intake(
            partner_name=args.name,
            official_url=args.official_url,
            affiliate_url=args.affiliate_url,
            pricing_url=args.pricing_url,
            contact_note=args.contact_note,
            commission_note=args.commission_note,
            payout_note=args.payout_note,
            count=args.count,
            batch_date=args.date,
        )
        if args.open:
            _open_local_path(str(workflow.console.console_html))
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    if args.command == "status":
        result = workflow.status(batch_date=args.date)
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print("Dashboard refreshed once.")
            print(f"Published: {result.get('published', 0)}")
            print(f"Ready for Publish: {result.get('ready_for_publish', 0)}")
            print(f"Publish Blocked: {result.get('publish_blocked', 0)}")
            print(f"Human Approval Required: {result.get('human_approval_required', 0)}")
            print(f"Needs Enrichment: {result.get('needs_enrichment', 0)}")
            print(f"Dashboard HTML: {result.get('dashboard_file', '')}")
            print(f"Master dashboard XLSX: {workflow.data_dir / 'master_dashboard.xlsx'}")
        return 0
    if args.command == "check-live":
        payload = workflow.check_live(batch_date=args.date, include_all=args.all, blocked_only=args.blocked_only)
        if args.open:
            _open_local_path(payload["html_report"])
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0
    if args.command == "diagnose-article":
        print(json.dumps(workflow.diagnose_article(batch_date=args.date, slug=args.slug), indent=2, ensure_ascii=False))
        return 0
    if args.command == "reset-unpublished":
        if args.apply and args.dry_run:
            print("[ERROR] Choose either --apply or --dry-run, not both.", flush=True)
            return 2
        result = workflow.reset_unpublished(before_date=args.before_date, apply=args.apply)
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            protected = len(result.get("excluded_candidates") or {})
            print("Reset applied." if args.apply else "Reset dry-run complete.")
            print(f"Candidates examined: {result.get('stale_candidate_count', 0)}")
            print(f"Protected: {protected}")
            print(f"Stale to archive: {result.get('stale_count', 0)}")
            print(f"Queue rows to remove: {result.get('queue_row_count', 0)}")
            print("Changes archived safely." if args.apply else "No changes applied.")
        return 0
    if args.command == "open":
        payload = workflow.get_dashboard_paths(batch_date=args.date)
        target = payload["review_dashboard"]
        if args.master:
            target = payload["master_dashboard"]
        elif args.operator:
            target = payload["operator_console"]
        if args.run:
            _open_local_path(target)
        print(json.dumps({**payload, "target": target}, indent=2, ensure_ascii=False))
        return 0
    if args.command == "serve":
        url = f"http://127.0.0.1:{args.port}/?date={args.date}"
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{args.port}/health", timeout=1).close()
            if args.open:
                _open_local_path(url)
            print(
                json.dumps(
                    {
                        "url": url,
                        "date": args.date,
                        "status": "reused_existing_server",
                        "note": f"Local dashboard server is already running on 127.0.0.1:{args.port}.",
                    },
                    ensure_ascii=False,
                )
            )
            return 0
        except Exception:
            pass
        server = ReviewDashboardServer(workflow=workflow).serve(batch_date=args.date, port=args.port, open_browser=args.open)
        print(
            json.dumps(
                {
                    "url": url,
                    "date": args.date,
                    "note": "Local dashboard server is running. Keep this PowerShell window open while reviewing articles.",
                },
                ensure_ascii=False,
            )
        )
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
