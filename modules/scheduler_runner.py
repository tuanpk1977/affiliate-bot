from __future__ import annotations

import argparse
import logging
import threading
import time
from datetime import datetime

import pandas as pd

from modules.social_publisher import load_queue, save_queue, write_log
from modules.telegram_publisher import send_post, validate_telegram_config


LOGGER = logging.getLogger(__name__)
_SCHEDULER_THREAD: threading.Thread | None = None
_SCHEDULER_STARTED_AT: str = ""
_LAST_RUN_AT: str = ""
_LAST_PUBLISH_AT: str = ""
_LAST_ERROR: str = ""


def scheduler_status() -> dict[str, str | bool]:
    return {
        "running": bool(_SCHEDULER_THREAD and _SCHEDULER_THREAD.is_alive()),
        "started_at": _SCHEDULER_STARTED_AT,
        "last_run_at": _LAST_RUN_AT,
        "last_publish_at": _LAST_PUBLISH_AT,
        "last_error": _LAST_ERROR,
    }


def start_background_scheduler(interval_seconds: int = 30) -> bool:
    global _SCHEDULER_THREAD, _SCHEDULER_STARTED_AT
    if _SCHEDULER_THREAD and _SCHEDULER_THREAD.is_alive():
        return False
    _SCHEDULER_STARTED_AT = datetime.now().isoformat(timespec="seconds")
    _SCHEDULER_THREAD = threading.Thread(
        target=run_scheduler_loop,
        kwargs={"interval_seconds": interval_seconds},
        daemon=True,
        name="telegram-auto-post-scheduler",
    )
    _SCHEDULER_THREAD.start()
    LOGGER.info("Telegram auto-post scheduler started")
    return True


def run_scheduler_loop(interval_seconds: int = 30, max_cycles: int | None = None) -> None:
    cycles = 0
    while True:
        process_due_telegram_posts()
        cycles += 1
        if max_cycles is not None and cycles >= max_cycles:
            return
        time.sleep(max(5, int(interval_seconds)))


def process_due_telegram_posts(now: datetime | None = None) -> dict[str, int]:
    global _LAST_RUN_AT, _LAST_PUBLISH_AT, _LAST_ERROR
    now = now or datetime.now()
    _LAST_RUN_AT = now.isoformat(timespec="seconds")
    queue = load_queue()
    if queue.empty:
        return {"checked": 0, "published": 0, "failed": 0, "skipped": 0}

    ready, config_message = validate_telegram_config()
    checked = published = failed = skipped = 0
    for idx, row in queue.iterrows():
        platform = str(row.get("platform", "")).strip().lower()
        status = str(row.get("status", "")).strip().lower()
        if platform != "telegram" or status != "approved":
            continue
        scheduled = parse_time(str(row.get("scheduled_time", "")))
        if scheduled and scheduled > now:
            skipped += 1
            continue
        checked += 1
        post_id = str(row.get("post_id", "") or row.get("queue_id", ""))
        queue.loc[idx, "last_attempt"] = now.isoformat(timespec="seconds")
        queue.loc[idx, "attempts"] = str(safe_int(row.get("attempts", "0")) + 1)
        if not ready:
            queue.loc[idx, "status"] = "failed"
            queue.loc[idx, "error"] = config_message
            write_log(post_id, "telegram", str(row.get("queue_id", "")), "telegram_publish", "failed", config_message)
            _LAST_ERROR = config_message
            failed += 1
            continue
        result = send_post(row.to_dict())
        if result.get("ok"):
            queue.loc[idx, "status"] = "published"
            queue.loc[idx, "published_at"] = datetime.now().isoformat(timespec="seconds")
            queue.loc[idx, "error"] = ""
            message_ids = "|".join(result.get("message_ids", []))
            queue.loc[idx, "published_url"] = message_ids
            write_log(post_id, "telegram", str(row.get("queue_id", "")), "telegram_publish", "published", "sent", message_ids)
            _LAST_PUBLISH_AT = datetime.now().isoformat(timespec="seconds")
            published += 1
        else:
            error = str(result.get("error", "telegram_publish_failed"))
            queue.loc[idx, "status"] = "failed"
            queue.loc[idx, "error"] = error
            write_log(post_id, "telegram", str(row.get("queue_id", "")), "telegram_publish", "failed", error)
            _LAST_ERROR = error
            failed += 1
    save_queue(queue)
    return {"checked": checked, "published": published, "failed": failed, "skipped": skipped}


def published_count_today() -> int:
    queue = load_queue()
    if queue.empty or "published_at" not in queue.columns:
        return 0
    today = datetime.now().date().isoformat()
    rows = queue[
        (queue["platform"].astype(str).str.lower() == "telegram")
        & (queue["status"].astype(str).str.lower().isin(["published", "posted"]))
        & (queue["published_at"].astype(str).str.startswith(today))
    ]
    return int(len(rows))


def failed_count() -> int:
    queue = load_queue()
    if queue.empty:
        return 0
    rows = queue[
        (queue["platform"].astype(str).str.lower() == "telegram")
        & (queue["status"].astype(str).str.lower() == "failed")
    ]
    return int(len(rows))


def parse_time(value: str) -> datetime | None:
    value = str(value or "").strip()
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def safe_int(value: object) -> int:
    try:
        return int(str(value or "0"))
    except ValueError:
        return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Telegram auto-post scheduler.")
    parser.add_argument("--daemon", action="store_true", help="Keep checking the queue.")
    parser.add_argument("--interval-seconds", type=int, default=30)
    parser.add_argument("--max-cycles", type=int, default=0)
    args = parser.parse_args()
    if args.daemon:
        run_scheduler_loop(args.interval_seconds, max_cycles=args.max_cycles or None)
    else:
        result = process_due_telegram_posts()
        print(result)


if __name__ == "__main__":
    main()
