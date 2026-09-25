from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
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
    trend.add_argument("--count", type=int, default=2, help="Number of topics to select.")
    trend.add_argument("--mode", choices=("standard", "advanced"), default="standard", help="Topic generation mode.")
    trend.add_argument("--date", default=today, help="Batch date in YYYY-MM-DD format. Defaults to today.")
    trend.add_argument("--dry-run", action="store_true", help="Preview topic selection without writing any queue, batch, dashboard, or state files.")
    trend.add_argument("--json", action="store_true", help="Also print the complete JSON diagnostic payload.")
    trend.add_argument("--confirm", action="store_true", help="Required for real topic queue creation.")
    trend.add_argument("--timeout", type=int, default=300, help="Outer timeout in seconds for real topic generation.")
    trend.add_argument("--retries", type=int, default=1, help="Bounded retry count for real topic generation.")

    daily_followup = subparsers.add_parser("daily-followup", help="Create Tue-Sun article angles from the current weekly root topics without discovery.")
    daily_followup.add_argument("--count", type=int, default=2, help="Maximum number of active weekly root topics to reuse.")
    daily_followup.add_argument("--date", default=today, help="Daily batch date in YYYY-MM-DD format. Defaults to today.")
    daily_followup.add_argument("--dry-run", action="store_true", help="Preview the daily angle queue without writing files or locks.")
    daily_followup.add_argument("--confirm", action="store_true", help="Required before creating a new daily queue.")
    daily_followup.add_argument("--timeout", type=int, default=300, help="Outer timeout in seconds for daily queue preparation.")
    daily_followup.add_argument("--retries", type=int, default=1, help="Bounded retry count for daily queue preparation.")

    morning = subparsers.add_parser("morning", help="Run trend discovery and draft generation, then build the review dashboard.")
    morning.add_argument("--count", type=int, default=2, help="Number of topics to select.")
    morning.add_argument("--mode", choices=("standard", "advanced"), default="standard", help="Topic generation mode.")
    morning.add_argument("--date", default=today, help="Batch date in YYYY-MM-DD format. Defaults to today.")
    morning.add_argument("--open", action="store_true", help="Open the daily review dashboard after generation.")
    morning.add_argument("--confirm", action="store_true", help="Required for real week-start generation.")
    morning.add_argument("--timeout", type=int, default=900, help="Outer timeout in seconds for real week-start generation.")
    morning.add_argument("--retries", type=int, default=1, help="Bounded retry count for real week-start generation.")

    draft = subparsers.add_parser("draft", help="Generate article drafts for a queued date.")
    draft.add_argument("--date", default=today, help="Batch date in YYYY-MM-DD format. Defaults to today.")

    prepare_research = subparsers.add_parser("prepare-research", help="Prepare topic research packages without generating drafts.")
    prepare_research.add_argument("--date", default=today, help="Batch date in YYYY-MM-DD format. Defaults to today.")
    prepare_research.add_argument("--open", action="store_true", help="Deprecated and ignored. Research preparation never opens the review dashboard.")

    comparator_candidates = subparsers.add_parser(
        "comparator-candidates",
        help="Show verified, ambiguous, and rejected comparator candidates for one comparison task.",
    )
    comparator_candidates.add_argument("--date", default=today)
    comparator_candidates.add_argument("--slug", required=True)

    confirm_comparators = subparsers.add_parser(
        "confirm-comparators",
        help="Confirm exactly two already-verifiable comparators and refresh research.",
    )
    confirm_comparators.add_argument("--date", default=today)
    confirm_comparators.add_argument("--slug", required=True)
    confirm_comparators.add_argument("--comparators", nargs=2, required=True)
    confirm_comparators.add_argument("--operator", default="editor")

    hold_comparators = subparsers.add_parser(
        "hold-comparators",
        help="Hold one unresolved comparison task without editing JSON manually.",
    )
    hold_comparators.add_argument("--date", default=today)
    hold_comparators.add_argument("--slug", required=True)
    hold_comparators.add_argument(
        "--reason",
        default="No verified comparator pair is available.",
    )
    hold_comparators.add_argument("--operator", default="editor")

    codex_write = subparsers.add_parser("codex-write", help="Use repository-local Codex writer to create drafts from queued topics and research.")
    codex_write.add_argument("--date", default=today, help="Batch date in YYYY-MM-DD format. Defaults to today.")
    codex_write.add_argument("--count", type=int, default=2, help="Maximum drafts to write.")
    codex_write.add_argument("--depth", choices=("deep", "standard"), default="deep", help="Draft depth profile.")
    codex_write.add_argument("--dry-run", action="store_true", help="Preview selected topics and outputs without writing files.")

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

    publish_exact = subparsers.add_parser("publish-exact-slug", help="Preflight or publish one operator-specified approved slug.")
    publish_exact.add_argument("--slug", required=True, help="Exact article slug. It is never selected automatically.")
    publish_exact.add_argument("--validation-mode", choices=("smart", "strict"), default="smart")
    publish_exact.add_argument("--dry-run", action="store_true", help="Run the exact-slug preflight without writing or publishing.")

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

    request_topic = subparsers.add_parser("request-topic", help="Create or prepare a custom affiliate/content topic outside the daily batch.")
    request_topic.add_argument("--topic", required=True, help="Requested topic title or keyword.")
    request_topic.add_argument("--category", default="", help="Optional category.")
    request_topic.add_argument("--intent", default="commercial research", help="Optional intent hint.")
    request_topic.add_argument("--source-url", default="", help="Optional official/source URL for the requested topic.")
    request_topic.add_argument("--official-url", default="", help="Official website URL.")
    request_topic.add_argument("--affiliate-url", default="", help="Affiliate program or tracking URL.")
    request_topic.add_argument("--pricing-url", default="", help="Pricing page URL.")
    request_topic.add_argument("--count", type=int, default=1, help="Number of drafts to generate for the custom topic cluster.")
    request_topic.add_argument(
        "--prepare-only",
        action="store_true",
        help="Prepare research for the external writer without creating a website draft.",
    )
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
    check_live.add_argument("--date", default="latest", help="Batch date in YYYY-MM-DD format. Defaults to the latest operational batch.")
    check_live.add_argument("--all", action="store_true", help="Check every article currently present in publish_queue.json, not only the selected batch date.")
    check_live.add_argument("--blocked-only", action="store_true", help="Show only blocked articles inside the live-status report.")
    check_live.add_argument("--open", action="store_true", help="Open the generated HTML live-status report.")

    diagnose = subparsers.add_parser("diagnose-article", help="Inspect one article publish-gate decision without modifying files.")
    diagnose.add_argument("--date", default=today, help="Batch date in YYYY-MM-DD format. Defaults to today.")
    diagnose.add_argument("--slug", required=True, help="Article slug.")

    diagnose_batch = subparsers.add_parser("diagnose-batch", help="Show deterministic publish selection diagnostics without changing state.")
    diagnose_batch.add_argument("--date", default=today)

    doctor = subparsers.add_parser("doctor", help="Compact read-only website and social workflow diagnostic.")
    doctor.add_argument("--date", default="latest")
    doctor.add_argument("--slug", default="", help="Optionally limit website output to one exact slug.")
    doctor.add_argument("--json", action="store_true", help="Print the complete compact JSON payload.")

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
    serve.add_argument("--background", action="store_true", help="Start or reuse the local dashboard server, then return immediately.")
    serve.add_argument("--require-drafts", action="store_true", help="Only start when the resolved batch contains reviewable drafts.")
    serve.add_argument("--code-signature", default="", help=argparse.SUPPRESS)

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
    print(f"EDITORIAL_WEEK: {payload.get('editorial_week_id', '')}")
    print(f"EVERGREEN_SELECTED: {payload.get('evergreen_selected', 0)}")
    print(f"CONFIRMED_HOT_SELECTED: {payload.get('confirmed_hot_selected', 0)}")
    print(f"FOUNDATION_ROOTS_SELECTED: {payload.get('selected_count', payload.get('count', 0))}")
    print(f"MAX_FOUNDATION_ROOTS: {payload.get('maximum_root_count', 5)}")
    print(f"FOUNDATION_ROOT_TARGET: {payload.get('foundation_root_target', payload.get('maximum_root_count', 5))}")
    print(f"WEEKLY_ROOTS_LOCKED: {'YES' if payload.get('weekly_roots_locked') else 'NO'}")
    print(f"QUALITY_LIMITED: {'YES' if payload.get('quality_limited') else 'NO'}")
    print(f"WATCHLIST_COUNT: {payload.get('watchlist_count', 0)}")
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
        domains = ", ".join(str(domain) for domain in list(item.get("unique_source_domains") or []))
        urls = list(item.get("source_urls") or [])
        print(f"    Domains: {domains or 'none'}")
        for url in urls:
            print(f"    - {url}")
        print(f"    Result: {item.get('pass_fail_reason', '')}")
    print("")
    print("would_create:")
    for path in payload.get("would_create", []):
        print(f"- {path}")
    print(f"Final decision: {payload.get('final_decision', 'FAIL')}")
    print(f"Passing topics: {payload.get('passing_topic_count', 0)}")
    print(f"Rejected candidates: {payload.get('rejected_candidate_count', 0)}")
    if payload.get("rejection_reasons"):
        print("Rejection reasons:")
        for reason, total in dict(payload.get("rejection_reasons") or {}).items():
            print(f"- {reason}: {total}")


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
    target = str(path).strip().strip('"')
    if not target:
        return
    candidate = Path(target)
    if candidate.exists():
        target = str(candidate.resolve())
    if sys.platform.startswith("win"):
        try:
            os.startfile(target)  # type: ignore[attr-defined]
        except OSError as exc:
            # Windows can reject an otherwise valid absolute path when the
            # selected shell/browser handler expects a URL.  A properly
            # encoded file URI avoids treating the drive colon as an invalid
            # argument while preserving the exact local file target.
            if exc.errno != 22 or not candidate.exists():
                raise
            webbrowser.open(candidate.resolve().as_uri())
        return
    subprocess.Popen(["xdg-open", target], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _dashboard_health_url(port: int) -> str:
    return f"http://127.0.0.1:{port}/health"


def _dashboard_url(*, port: int, batch_date: str) -> str:
    return f"http://127.0.0.1:{port}/?date={batch_date}"


def _dashboard_code_signature() -> str:
    """Identify the exact source set loaded by the interactive review server."""
    digest = hashlib.sha256()
    for path in (
        ROOT / "editorial_console.py",
        ROOT / "modules" / "review_dashboard_server.py",
        ROOT / "modules" / "editorial_operations_console.py",
        ROOT / "modules" / "daily_editorial_workflow.py",
        ROOT / "modules" / "human_approval.py",
        ROOT / "modules" / "publish_gate.py",
    ):
        digest.update(path.name.encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _dashboard_health(port: int) -> dict:
    try:
        with urllib.request.urlopen(_dashboard_health_url(port), timeout=1) as response:
            raw = response.read().decode("utf-8")
        try:
            payload = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return {"reachable": True, "incompatible": True}
        if isinstance(payload, dict) and payload.get("ok") is True:
            return {**payload, "reachable": True}
        return {"reachable": True, "incompatible": True}
    except Exception:
        return {}


def _server_is_healthy(port: int) -> bool:
    return _dashboard_health(port).get("ok") is True


def _shutdown_stale_dashboard(port: int) -> bool:
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{port}/shutdown", timeout=2).close()
    except Exception:
        return False
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if not _dashboard_health(port):
            return True
        time.sleep(0.1)
    return False


def _serve_dashboard_background(*, batch_date: str, port: int, open_browser: bool) -> int:
    url = _dashboard_url(port=port, batch_date=batch_date)
    expected_signature = _dashboard_code_signature()
    health = _dashboard_health(port)
    if health and health.get("code_signature") == expected_signature:
        if open_browser:
            _open_local_path(url)
        print(json.dumps({"status": "reused_existing_server", "url": url, "port": port}, indent=2, ensure_ascii=False))
        return 0
    if health:
        print("[INFO] Dashboard code changed. Restarting the stale local review server.", flush=True)
        if not _shutdown_stale_dashboard(port):
            print(f"[ERROR] A stale dashboard is still using port {port}. Close it, then open Menu 4 again.", flush=True)
            return 1

    log_dir = ROOT / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"dashboard_server_{port}.log"
    log_handle = log_path.open("a", encoding="utf-8")
    command = [
        sys.executable,
        str(ROOT / "editorial_console.py"),
        "serve",
        "--date",
        batch_date,
        "--port",
        str(port),
        "--code-signature",
        expected_signature,
    ]
    creationflags = 0
    if os.name == "nt":
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
    try:
        process = subprocess.Popen(
            command,
            cwd=ROOT,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            creationflags=creationflags,
        )
    except Exception:
        log_handle.close()
        raise

    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if process.poll() is not None:
            log_handle.close()
            print(f"[ERROR] Dashboard server exited early with code {process.returncode}. Log: {log_path}", flush=True)
            return 1
        health = _dashboard_health(port)
        if health and health.get("code_signature") == expected_signature:
            if open_browser:
                _open_local_path(url)
            print(json.dumps({"status": "started_background_server", "pid": process.pid, "url": url, "port": port, "log": str(log_path)}, indent=2, ensure_ascii=False))
            return 0
        time.sleep(0.25)

    print(f"[ERROR] Dashboard server did not become healthy on port {port}. Log: {log_path}", flush=True)
    return 1


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


def _print_daily_followup_summary(payload: dict) -> None:
    print("DAILY DEEP-DIVE", flush=True)
    print(f"Date: {payload.get('date', '')}", flush=True)
    print(f"Latest published article: {payload.get('latest_published_article') or 'None eligible'}", flush=True)
    print(f"Root source: {payload.get('root_source', '')}", flush=True)
    print(f"Root slug: {payload.get('root_slug', '')}", flush=True)
    print(f"Root live status: {payload.get('root_live_status', '')}", flush=True)
    print("", flush=True)
    print(f"Selected deep-dive angle: {payload.get('selected_deep_dive_angle', '')}", flush=True)
    print(f"Search intent: {payload.get('child_search_intent', '')}", flush=True)
    print(f"Relationship: {payload.get('relationship', '')}", flush=True)
    print(f"Duplicate risk: {payload.get('duplicate_risk', '')}", flush=True)
    print(f"Research readiness: {payload.get('research_readiness', '')}", flush=True)
    print(f"Decision: {payload.get('daily_decision', payload.get('final_decision', ''))}", flush=True)
    print("", flush=True)
    print("DETAILS:", flush=True)
    print(f"- week_start: {payload.get('week_start', '')}", flush=True)
    print(f"- root_topic_count: {payload.get('root_topic_count', 0)}", flush=True)
    print(f"- WEEKLY_APPROVED_ROOT_COUNT: {payload.get('weekly_approved_root_count', payload.get('root_topic_count', 0))}", flush=True)
    print(f"- TODAY_SELECTED_ROOT_COUNT: {payload.get('today_selected_root_count', payload.get('eligible_root_count', 0))}", flush=True)
    print(f"- active_root_topics: {payload.get('active_root_topics', 0)}", flush=True)
    print(f"- day_profile: {payload.get('day_profile', '')}", flush=True)
    print(f"- existing_daily_articles: {payload.get('existing_daily_articles', 0)}", flush=True)
    print(f"- new_angles_created: {payload.get('new_angles_created', 0)}", flush=True)
    print(f"- held_due_to_sources: {payload.get('held_due_to_sources', 0)}", flush=True)
    print(f"- skipped_duplicates: {payload.get('skipped_duplicates', 0)}", flush=True)
    print(f"- NEW_ROOTS_CREATED: {payload.get('new_roots_created', 0)}", flush=True)
    blockers = list(payload.get("root_validation_blockers") or [])
    if blockers:
        print("- root_validation_blockers:", flush=True)
        for blocker in blockers[:10]:
            print(f"  - {blocker}", flush=True)
    diagnostics = list(payload.get("blocked_diagnostics") or [])
    if diagnostics:
        print("", flush=True)
        print("BLOCKED_DIAGNOSTICS:", flush=True)
        for row in diagnostics:
            print(f"- slug: {row.get('slug', '')}", flush=True)
            print(f"  BLOCKED_STAGE: {row.get('BLOCKED_STAGE', '')}", flush=True)
            print(f"  BLOCKED_REASON: {row.get('BLOCKED_REASON', '')}", flush=True)
            print(f"  MISSING_EVIDENCE: {row.get('MISSING_EVIDENCE', '')}", flush=True)
            print(f"  TARGET_ENTITY_OR_TOPIC: {row.get('TARGET_ENTITY_OR_TOPIC', '')}", flush=True)
            print(f"  REQUIRED_SOURCE_TYPES: {row.get('REQUIRED_SOURCE_TYPES', '')}", flush=True)
            print(
                f"  REQUIRED_OPERATOR_ACTION: {row.get('REQUIRED_OPERATOR_ACTION', '')}",
                flush=True,
            )
    print(f"- daily_queue_path: {payload.get('daily_queue_path', '')}", flush=True)
    if payload.get("legacy_queue_requires_manual_review"):
        print("- status: existing legacy queue requires manual review; it was not overwritten", flush=True)
    evidence = list(payload.get("evidence_summary") or [])
    if evidence:
        print("", flush=True)
        print("RESEARCH_EVIDENCE:", flush=True)
        print(
            "slug | angle | entities resolved/required | paragraphs | "
            "candidates/accepted/rejected | section coverage | entity coverage | "
            "status | next action",
            flush=True,
        )
        for row in evidence:
            print(
                f"{row.get('slug', '')} | {row.get('angle_profile', '')} | "
                f"{row.get('resolved_entities', 0)}/{row.get('required_entities', 0)} | "
                f"{row.get('paragraphs', 0)} | "
                f"{row.get('candidate_claims', 0)}/"
                f"{row.get('claims', 0)}/{row.get('rejected_claims', 0)} | "
                f"{row.get('coverage', '0/0')} "
                f"({float(row.get('coverage_score') or 0):.2f}) | "
                f"{float(row.get('entity_coverage_score') or 0):.2f} | "
                f"{row.get('status', '')} | {row.get('next_action', '')}",
                flush=True,
            )
        print(
            f"ARTICLE_READY={payload.get('article_ready', 0)} | "
            f"BLOCKED_RESEARCH={payload.get('blocked_research', 0)}",
            flush=True,
        )
    print("", flush=True)
    print("Next action:", flush=True)
    print(payload.get("next_action") or "Review the daily deep-dive decision.", flush=True)
    decision = str(payload.get("daily_decision") or "")
    if decision == "BLOCKED_RESEARCH":
        print("[S] Open targeted Source Review (Menu S)", flush=True)
        print("[R] Retry research", flush=True)
        print("[E] Change deep-dive angle", flush=True)
        print("[X] Cancel", flush=True)
    elif decision == "READY_FOR_DAILY_QUEUE":
        print("[C] Create queue", flush=True)
        print("[V] View research", flush=True)
        print("[E] Edit angle", flush=True)
        print("[X] Cancel", flush=True)
    if payload.get("daily_decision") == "READY_FOR_DAILY_QUEUE" and payload.get("next_command"):
        print("", flush=True)
        print("NEXT_STEP:", flush=True)
        print(payload["next_command"], flush=True)


def _exact_slug_state(workflow: object, slug: str) -> dict:
    reader = getattr(workflow, "exact_slug_execution_state", None)
    if not callable(reader):
        return {"slug": slug, "artifacts": {}, "publish_status": "unknown", "git_head": "", "origin_main": ""}
    try:
        return dict(reader(slug) or {})
    except Exception as exc:
        return {"slug": slug, "artifacts": {}, "publish_status": "unknown", "git_head": "", "origin_main": "", "state_error": str(exc)}


def _exact_slug_failed_stage(reason: str) -> str:
    value = reason.casefold()
    if "exact_slug_preflight_blocked" in value or "canonical_state:" in value:
        return "ELIGIBILITY_PREFLIGHT"
    if "source_bytes_before_copy" in value or "approval_binding" in value or "content_hash_mismatch" in value:
        return "APPROVAL_BINDING_OR_SOURCE_BYTES"
    if "preflight" in value or "git fetch" in value or "git sync" in value:
        return "GIT_SYNC"
    if "targeted build" in value or "build_selected_output" in value:
        return "TARGETED_BUILD"
    if "source=published_static" in value or "source=site_output" in value or "source=docs" in value:
        return "POST_BUILD_HASH_CHECK"
    if "sync_site_output_to_docs" in value or "sync site_output" in value:
        return "DOCS_SYNC"
    if "publish validation" in value or "no publishable articles" in value:
        return "PUBLISH_VALIDATION"
    if "git add" in value:
        return "GIT_ADD"
    if "git commit" in value:
        return "GIT_COMMIT"
    if "git push" in value or "push_status" in value:
        return "GIT_PUSH"
    return "EXACT_SLUG_PUBLISH"


def _exact_slug_state_changed(before: dict, after: dict) -> bool:
    if str(before.get("publish_status") or "") != str(after.get("publish_status") or ""):
        return True
    before_artifacts = before.get("artifacts") if isinstance(before.get("artifacts"), dict) else {}
    after_artifacts = after.get("artifacts") if isinstance(after.get("artifacts"), dict) else {}
    for key in {*(before_artifacts or {}), *(after_artifacts or {})}:
        old = before_artifacts.get(key) if isinstance(before_artifacts.get(key), dict) else {}
        new = after_artifacts.get(key) if isinstance(after_artifacts.get(key), dict) else {}
        if (old.get("exists"), old.get("content_hash")) != (new.get("exists"), new.get("content_hash")):
            return True
    return False


def _build_exact_slug_outcome(
    *,
    slug: str,
    preflight: dict,
    before: dict,
    after: dict,
    result: dict | None = None,
    error: Exception | None = None,
) -> dict:
    if error is not None:
        reason = str(error)
        head_changed = bool(before.get("git_head") and after.get("git_head") and before.get("git_head") != after.get("git_head"))
        pushed = bool(head_changed and after.get("git_head") == after.get("origin_main"))
        return {
            "slug": slug,
            "result": "BLOCKED" if "BLOCKED" in reason.upper() or "PREFLIGHT" in reason.upper() else "FAILED",
            "approval_binding": str(preflight.get("approval_binding_status") or "UNKNOWN"),
            "local_publish": "PARTIAL_OR_CHANGED" if _exact_slug_state_changed(before, after) else "NOT_PERFORMED",
            "targeted_build": "UNKNOWN_OR_FAILED",
            "post_build_hash_check": "NOT_CONFIRMED",
            "git_sync": "FAILED" if _exact_slug_failed_stage(reason) == "GIT_SYNC" else "UNKNOWN",
            "commit": "PERFORMED" if head_changed else "NOT_PERFORMED",
            "push": "PERFORMED" if pushed else "NOT_PERFORMED",
            "deployment": str(after.get("deployment_state") or "NOT_CONFIRMED"),
            "final_publish_state": str(after.get("publish_status") or "unknown"),
            "failed_stage": _exact_slug_failed_stage(reason),
            "reason": reason,
            "production_mutation_before_failure": _exact_slug_state_changed(before, after),
            "safe_next_action": "Review this result and current hashes before retrying; do not assume publication succeeded.",
        }

    payload = dict(result or {})
    build = payload.get("build") if isinstance(payload.get("build"), dict) else {}
    commit = payload.get("git_commit") if isinstance(payload.get("git_commit"), dict) else {}
    push = payload.get("git_push") if isinstance(payload.get("git_push"), dict) else {}
    sync = payload.get("preflight_sync") if isinstance(payload.get("preflight_sync"), dict) else {}
    binding_checks = list(payload.get("source_binding_checks") or [])
    binding_matched = bool(binding_checks) and all(str(row.get("status") or "") == "MATCHED" for row in binding_checks)
    success = (
        int(payload.get("published_count") or 0) == 1
        and int(build.get("returncode", 1)) == 0
        and binding_matched
        and int(commit.get("returncode", 1)) == 0
        and str(push.get("status") or "") in {"pushed", "pushed_after_rebase"}
        and str(sync.get("status") or "") in {"preflight_in_sync", "preflight_ahead_only", "preflight_rebased"}
    )
    live = payload.get("post_push_live_check") if isinstance(payload.get("post_push_live_check"), dict) else {}
    return {
        "slug": slug,
        "result": "SUCCESS" if success else "FAILED",
        "approval_binding": str(preflight.get("approval_binding_status") or "UNKNOWN"),
        "local_publish": "SUCCESS" if int(payload.get("published_count") or 0) == 1 else "FAILED",
        "targeted_build": "SUCCESS" if int(build.get("returncode", 1)) == 0 else "FAILED",
        "post_build_hash_check": "MATCHED" if binding_matched else "FAILED",
        "git_sync": "SUCCESS" if str(sync.get("status") or "") in {"preflight_in_sync", "preflight_ahead_only", "preflight_rebased"} else "FAILED",
        "commit": "SUCCESS" if int(commit.get("returncode", 1)) == 0 else "FAILED",
        "push": "SUCCESS" if str(push.get("status") or "") in {"pushed", "pushed_after_rebase"} else "FAILED",
        "deployment": str(live.get("status") or "NOT_CONFIRMED"),
        "final_publish_state": str(after.get("publish_status") or "unknown"),
        "failed_stage": "" if success else "RESULT_VERIFICATION",
        "reason": "" if success else "One or more required publish stages did not report factual success.",
        "production_mutation_before_failure": False if success else _exact_slug_state_changed(before, after),
        "safe_next_action": "No retry is needed; inspect deployment status." if success else "Inspect stage results before retrying.",
    }


def _print_exact_slug_outcome(outcome: dict) -> None:
    print("", flush=True)
    print("========================================", flush=True)
    print("EXACT-SLUG PUBLISH RESULT", flush=True)
    print("========================================", flush=True)
    labels = (
        ("Slug", "slug"),
        ("Result", "result"),
        ("Approval binding", "approval_binding"),
        ("Local publish", "local_publish"),
        ("Targeted build", "targeted_build"),
        ("Post-build hash check", "post_build_hash_check"),
        ("Git sync", "git_sync"),
        ("Commit", "commit"),
        ("Push", "push"),
        ("Deployment", "deployment"),
        ("Final publish state", "final_publish_state"),
    )
    for label, key in labels:
        print(f"{label}: {outcome.get(key, '')}", flush=True)
    if outcome.get("failed_stage"):
        print(f"Failed stage: {outcome['failed_stage']}", flush=True)
    if outcome.get("reason"):
        print(f"Reason: {outcome['reason']}", flush=True)
    if outcome.get("result") != "SUCCESS":
        print(f"Production mutation before failure: {'YES' if outcome.get('production_mutation_before_failure') else 'NO'}", flush=True)
        print(f"Safe next action: {outcome.get('safe_next_action', '')}", flush=True)
    print("========================================", flush=True)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    workflow = DailyEditorialWorkflow()
    workflow.set_progress_reporter(_progress_print)
    publish_lock = PublishLock(ROOT / "data" / "publish.lock")

    if args.command == "trend":
        if args.dry_run:
            payload = workflow.trend_dry_run(count=args.count, mode=args.mode, batch_date=args.date)
            _print_trend_dry_run(payload)
            if args.json:
                print(json.dumps(payload, indent=2, ensure_ascii=False))
            else:
                print("Full diagnostics: rerun this command with --json")
            return 0 if payload.get("final_decision") == "PASS" else 2
        if not args.confirm:
            print("[ERROR] Real topic generation requires a successful dry-run and --confirm.", flush=True)
            print(f"[INFO] Preview first: python editorial_console.py trend --count {args.count} --mode {args.mode} --date {args.date} --dry-run", flush=True)
            return 2
        payload = _run_with_retries(lambda: workflow.trend(count=args.count, mode=args.mode, batch_date=args.date), retries=args.retries, timeout=args.timeout)
        _print_trend_summary(payload)
        print(json.dumps({"saved_to": f"data/editorial_queue/{payload['date']}/topics.json"}, ensure_ascii=False))
        return 0
    if args.command == "daily-followup":
        try:
            if args.dry_run:
                payload = workflow.daily_followup_dry_run(count=args.count, batch_date=args.date)
                _print_daily_followup_summary(payload)
                return 0 if payload.get("final_decision") == "PASS" else 2
            if not args.confirm:
                print("[ERROR] Daily queue creation requires preview plus --confirm.", flush=True)
                print(f"[INFO] Preview first: python editorial_console.py daily-followup --count {args.count} --date {args.date} --dry-run", flush=True)
                return 2
            payload = _run_with_retries(
                lambda: workflow.daily_followup(count=args.count, batch_date=args.date),
                retries=args.retries,
                timeout=args.timeout,
            )
            _print_daily_followup_summary(payload)
            return 0 if payload.get("final_decision") == "PASS" else 2
        except FileNotFoundError as exc:
            print(str(exc), flush=True)
            return 2
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
    if args.command == "prepare-research":
        payload = workflow.prepare_research(batch_date=args.date)
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0
    if args.command in {
        "comparator-candidates",
        "confirm-comparators",
        "hold-comparators",
    }:
        from modules.comparator_discovery import ComparatorDiscoveryEngine

        queue = workflow._load_queue(args.date)
        task = next(
            (
                row
                for row in queue.get("topics", [])
                if str(row.get("slug") or "") == args.slug
            ),
            None,
        )
        if not isinstance(task, dict):
            print(f"[ERROR] Comparator task not found: {args.slug}", flush=True)
            return 2
        plan_path = ROOT / "data" / "research" / args.slug / "ANGLE_RESEARCH_PLAN.json"
        try:
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            print(
                f"[ERROR] Research plan not found. Run: "
                f"python editorial_console.py prepare-research --date {args.date}",
                flush=True,
            )
            return 2
        root_entity = str(
            (plan.get("root_entity") or {}).get("canonical_name")
            or task.get("primary_entity")
            or task.get("root_title")
            or ""
        )
        engine = ComparatorDiscoveryEngine(root=ROOT)
        if args.command == "comparator-candidates":
            report_path = (
                ROOT / "data" / "research" / args.slug
                / "comparator_candidate_report.json"
            )
            report = json.loads(report_path.read_text(encoding="utf-8"))
            print(f"Comparator candidates for {root_entity}:")
            for index, row in enumerate(report.get("operator_candidates", []), start=1):
                print(
                    f"{index}. {row.get('canonical_name')} - "
                    f"{row.get('verification_status')} - "
                    f"{row.get('why_comparable')} "
                    f"(confidence {float(row.get('confidence') or 0):.2f})"
                )
                if row.get("rejection_reason"):
                    print(f"   Reason: {row['rejection_reason']}")
            verified = [
                row
                for row in report.get("operator_candidates", [])
                if str(row.get("verification_status") or "") == "VERIFIED"
            ]
            if len(verified) >= 2:
                names = [str(row.get("canonical_name") or "") for row in verified[:2]]
                print(
                    f"Next: python editorial_console.py confirm-comparators "
                    f"--date {args.date} --slug {args.slug} "
                    f"--comparators \"{names[0]}\" \"{names[1]}\""
                )
            else:
                print(
                    "No verified comparator pair is available. "
                    "Do not confirm these candidates yet."
                )
                print(
                    f"Hold: python editorial_console.py hold-comparators "
                    f"--date {args.date} --slug {args.slug}"
                )
            return 0
        if args.command == "hold-comparators":
            report_path = (
                ROOT / "data" / "research" / args.slug
                / "comparator_candidate_report.json"
            )
            report = json.loads(report_path.read_text(encoding="utf-8"))
            report["operator_decision"] = {
                "status": "HELD",
                "reason": args.reason,
                "operator": args.operator,
                "recorded_on": date.today().isoformat(),
            }
            report_path.write_text(
                json.dumps(report, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            print(
                json.dumps(
                    {
                        "status": "HELD",
                        "slug": args.slug,
                        "reason": args.reason,
                        "report": str(report_path),
                    },
                    indent=2,
                    ensure_ascii=False,
                )
            )
            return 0
        try:
            result = engine.confirm(
                root_entity=root_entity,
                comparator_names=list(args.comparators),
                article_slug=args.slug,
                operator=args.operator,
            )
            result["research_refresh"] = workflow.prepare_research(
                batch_date=args.date
            )
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 0
        except ValueError as exc:
            print(f"[ERROR] {exc}", flush=True)
            return 2
    if args.command == "codex-write":
        from modules.codex_writer_workflow import run_codex_daily_writer

        print(
            json.dumps(
                run_codex_daily_writer(batch_date=args.date, count=args.count, depth=args.depth, dry_run=args.dry_run),
                indent=2,
                ensure_ascii=False,
            )
        )
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
        requested_date = args.date
        publish_candidates = {}
        if str(requested_date or "").strip().lower() == "latest" and hasattr(workflow, "resolve_latest_publish_candidate_batch"):
            publish_candidates = workflow.resolve_latest_publish_candidate_batch()
            resolved_date = str(publish_candidates.get("batch_date") or "")
        else:
            resolved_date = workflow.resolve_batch_date(requested_date, require_activity=True) if hasattr(workflow, "resolve_batch_date") else requested_date
        print(f"Requested batch: {requested_date}", flush=True)
        if not resolved_date:
            print("Resolved batch: none (no non-terminal human-approved publish candidate)", flush=True)
            print("[INFO] Khong co bai da duyet nao dang cho publish. Khong co file nao duoc commit hoac push.", flush=True)
            return 2
        print(f"Resolved publish batch: {resolved_date}", flush=True)
        if publish_candidates:
            candidate_slugs = list(publish_candidates.get("candidate_slugs") or [])
            print(f"Active publish candidates: {len(candidate_slugs)}", flush=True)
            for slug in candidate_slugs:
                print(f"- {slug}", flush=True)
        asset_preparation = {}
        if hasattr(workflow, "prepare_required_images_for_publish"):
            asset_preparation = workflow.prepare_required_images_for_publish(batch_date=resolved_date, dry_run=False)
            print(
                "Image preparation: "
                f"inspected={asset_preparation.get('inspected', 0)} "
                f"missing={asset_preparation.get('missing', 0)} "
                f"generated={asset_preparation.get('generated', 0)} "
                f"failed={asset_preparation.get('failed', 0)}",
                flush=True,
            )
        diagnostic = workflow.diagnose_batch(batch_date=resolved_date) if hasattr(workflow, "diagnose_batch") else {"candidates": []}
        status_counts = workflow.status(batch_date=resolved_date) if hasattr(workflow, "status") else {}
        if status_counts:
            print(f"Human Approved: {status_counts.get('human_approved', 0)}", flush=True)
            print(f"Ready for Publish: {status_counts.get('ready_for_publish', 0)}", flush=True)
            print(f"Publish Blocked: {status_counts.get('publish_blocked', 0)}", flush=True)
        selected_slugs = [row["slug"] for row in diagnostic["candidates"] if row["selected_for_publish"]]
        _print_candidate_table(diagnostic)
        try:
            publish_lock.acquire(batch_date=resolved_date, slugs=selected_slugs, command="publish-ready")
        except RuntimeError as exc:
            print(f"[ERROR] {exc}", flush=True)
            return 3
        stop_event, watcher, started_at = _start_publish_watch(workflow)
        try:
            result = workflow.publish_ready(batch_date=resolved_date, validation_mode=args.validation_mode)
        except ValueError as exc:
            if _is_no_ready_publish_error(exc):
                _print_no_ready_publish_summary(workflow, batch_date=resolved_date)
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
        if asset_preparation:
            result.setdefault("asset_preparation", asset_preparation)
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
    if args.command == "publish-exact-slug":
        preflight = workflow.exact_slug_preflight(slug=args.slug, validation_mode=args.validation_mode)
        print(json.dumps(preflight, indent=2, ensure_ascii=False), flush=True)
        if args.dry_run:
            if not preflight.get("exact_slug_ready_for_publish"):
                state = _exact_slug_state(workflow, args.slug)
                outcome = _build_exact_slug_outcome(
                    slug=args.slug,
                    preflight=preflight,
                    before=state,
                    after=state,
                    error=ValueError("EXACT_SLUG_PREFLIGHT_BLOCKED: " + "; ".join(preflight.get("blockers") or [])),
                )
                _print_exact_slug_outcome(outcome)
            return 0 if preflight.get("exact_slug_ready_for_publish") else 2
        if not preflight.get("exact_slug_ready_for_publish"):
            state = _exact_slug_state(workflow, args.slug)
            outcome = _build_exact_slug_outcome(
                slug=args.slug,
                preflight=preflight,
                before=state,
                after=state,
                error=ValueError("EXACT_SLUG_PREFLIGHT_BLOCKED: " + "; ".join(preflight.get("blockers") or [])),
            )
            _print_exact_slug_outcome(outcome)
            return 2
        batch_date = str(preflight.get("batch_date") or "exact-slug")
        before = _exact_slug_state(workflow, args.slug)
        try:
            publish_lock.acquire(batch_date=batch_date, slugs=[args.slug], command="publish-exact-slug")
        except RuntimeError as exc:
            after = _exact_slug_state(workflow, args.slug)
            _print_exact_slug_outcome(
                _build_exact_slug_outcome(
                    slug=args.slug,
                    preflight=preflight,
                    before=before,
                    after=after,
                    error=exc,
                )
            )
            return 3
        stop_event, watcher, started_at = _start_publish_watch(workflow)
        result: dict = {}
        publish_error: Exception | None = None
        try:
            result = workflow.publish_exact_slug(slug=args.slug, validation_mode=args.validation_mode)
        except Exception as exc:
            publish_error = exc
        finally:
            stop_event.set()
            watcher.join(timeout=1)
            publish_lock.release()
        after = _exact_slug_state(workflow, args.slug)
        if result:
            print(json.dumps(result, indent=2, ensure_ascii=False), flush=True)
        outcome = _build_exact_slug_outcome(
            slug=args.slug,
            preflight=preflight,
            before=before,
            after=after,
            result=result,
            error=publish_error,
        )
        _print_exact_slug_outcome(outcome)
        return 0 if outcome.get("result") == "SUCCESS" else 1
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
    if args.command == "doctor":
        payload = workflow.daily_workflow_doctor(batch_date=args.date, slug=args.slug)
        print("DAILY WORKFLOW DOCTOR (READ ONLY)")
        print(f"Website batch: {payload['website_batch']}")
        for item in payload["website_items"]:
            blockers = ",".join(item["blockers"]) or "NONE"
            print(
                f"WEB {item['slug']} | state={item['state']} | quality={item['quality_review']} | "
                f"approval={item['human_approval_binding']} | gate={item['publish_gate_binding']} | "
                f"cta={item['cta']} | image={item['image']} | blockers={blockers}"
            )
        print(
            f"SOCIAL live_batch={payload['social_live_batch']} | live_candidates={payload['social_live_candidates']} | "
            f"review_batch={payload['social_review_batch']} | selected_articles={payload['social_selected_articles']} | "
            f"platform_records={payload['social_platform_records']}"
        )
        print(
            f"SOCIAL mode={payload.get('social_mode', 'UNKNOWN')} | roots={len(payload.get('social_root_topics') or [])} | "
            f"source_bound={payload.get('social_source_bound_records', 0)} | "
            f"unsupported_new_claims={payload.get('social_unsupported_new_claims', 0)} | "
            f"historical_loaded={payload.get('unrelated_historical_tasks_loaded', 0)}"
        )
        social_counts = payload.get("social_status_counts") or {}
        print("SOCIAL statuses=" + (", ".join(f"{key}:{value}" for key, value in sorted(social_counts.items())) or "NONE"))
        if args.json:
            print(json.dumps(payload, indent=2, ensure_ascii=False))
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
            prepare_only=args.prepare_only,
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
            for topic in result.get("topic_status", []):
                print("")
                print(f"Topic: {topic.get('slug', '')}")
                print(f"Research: {topic.get('research', 'UNKNOWN')}")
                print(f"Draft: {topic.get('draft', 'UNKNOWN')}")
                print(f"Human Approval: {topic.get('human_approval', 'UNKNOWN')}")
                print(f"Publish Gate: {topic.get('publish_gate', 'UNKNOWN')}")
                print(f"Deployment: {topic.get('deployment', 'UNKNOWN')}")
                print(f"Social: {topic.get('social', 'UNKNOWN')}")
                print(f"Next Action: {topic.get('next_action', '')}")
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
        if args.require_drafts:
            requested_date = args.date
            resolved_date = ""
            reviewable_slugs: list[str] = []
            if str(requested_date or "").strip().lower() == "latest":
                details = workflow.resolve_latest_reviewable_batch() if hasattr(workflow, "resolve_latest_reviewable_batch") else {}
                resolved_date = str(details.get("batch_date") or "")
                reviewable_slugs = list(details.get("reviewable_slugs") or [])
            elif hasattr(workflow, "reviewable_batch_details"):
                details = workflow.reviewable_batch_details(requested_date)
                reviewable_slugs = list(details.get("reviewable_slugs") or [])
                if reviewable_slugs:
                    resolved_date = requested_date
            if not resolved_date:
                print("No draft available. Run Codex Writer first.", flush=True)
                return 2
            args.date = resolved_date
            print(f"Requested date: {requested_date}", flush=True)
            print(f"Resolved review batch date: {resolved_date}", flush=True)
            if reviewable_slugs:
                print(f"Reviewable drafts: {len(reviewable_slugs)}", flush=True)
                for slug in reviewable_slugs:
                    print(f"- {slug}", flush=True)
        if args.background:
            return _serve_dashboard_background(batch_date=args.date, port=args.port, open_browser=args.open)
        url = _dashboard_url(port=args.port, batch_date=args.date)
        expected_signature = args.code_signature or _dashboard_code_signature()
        health = _dashboard_health(args.port)
        if health and health.get("code_signature") == expected_signature:
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
        if health:
            print(
                f"[ERROR] A different dashboard build is already using port {args.port}. "
                "Open Menu 4 to restart it safely.",
                flush=True,
            )
            return 1
        server = ReviewDashboardServer(workflow=workflow, code_signature=expected_signature).serve(
            batch_date=args.date,
            port=args.port,
            open_browser=args.open,
        )
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
