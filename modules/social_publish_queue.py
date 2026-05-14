from __future__ import annotations

import csv
import json
import logging
import os
import random
import argparse
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

from config import settings
from modules.social_content_generator import load_social_accounts, read_social_post_report


logger = logging.getLogger(__name__)

QUEUE_COLUMNS = [
    "queue_id",
    "post_id",
    "draft_id",
    "platform",
    "title",
    "article_url",
    "post_file",
    "status",
    "scheduled_time",
    "approved_at",
    "published_at",
    "last_attempt",
    "attempts",
    "error",
]

PLATFORM_LIMITS = {
    "facebook": 3,
    "telegram": 6,
    "linkedin": 2,
    "twitter": 12,
}

DEFAULT_SCHEDULE = {
    "telegram": {"enabled": True, "daily_times": ["09:00", "20:00"], "max_posts_per_day": 2},
    "facebook": {"enabled": False, "daily_times": ["09:30", "20:30"], "max_posts_per_day": 2},
    "linkedin": {"enabled": False, "daily_times": ["10:00"], "max_posts_per_day": 1},
    "twitter": {"enabled": False, "daily_times": ["09:15", "14:00", "20:15"], "max_posts_per_day": 3},
}


def queue_path() -> Path:
    return settings.data_dir / "social_publish_queue.csv"


def schedule_config_path() -> Path:
    return settings.base_dir / "config" / "social_schedule.json"


def load_social_schedule() -> dict[str, dict[str, object]]:
    path = schedule_config_path()
    if not path.exists():
        save_social_schedule(DEFAULT_SCHEDULE)
        return json.loads(json.dumps(DEFAULT_SCHEDULE))
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    merged = json.loads(json.dumps(DEFAULT_SCHEDULE))
    for platform, config in data.items():
        if platform not in merged or not isinstance(config, dict):
            continue
        merged[platform].update(config)
        merged[platform]["daily_times"] = normalize_daily_times(merged[platform].get("daily_times", []))
        merged[platform]["max_posts_per_day"] = max(1, int(merged[platform].get("max_posts_per_day", 1) or 1))
    return merged


def save_social_schedule(schedule: dict[str, dict[str, object]]) -> None:
    path = schedule_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    cleaned = {}
    for platform, config in schedule.items():
        cleaned[platform] = {
            "enabled": bool(config.get("enabled", False)),
            "daily_times": normalize_daily_times(config.get("daily_times", [])),
            "max_posts_per_day": max(1, int(config.get("max_posts_per_day", 1) or 1)),
        }
    path.write_text(json.dumps(cleaned, indent=2, ensure_ascii=False), encoding="utf-8")


def ensure_queue() -> pd.DataFrame:
    path = queue_path()
    if not path.exists():
        write_rows(path, [], QUEUE_COLUMNS)
    return load_queue()


def load_queue() -> pd.DataFrame:
    path = queue_path()
    if not path.exists():
        return pd.DataFrame(columns=QUEUE_COLUMNS)
    try:
        df = pd.read_csv(path)
    except Exception:
        df = pd.DataFrame(columns=QUEUE_COLUMNS)
    for column in QUEUE_COLUMNS:
        if column not in df.columns:
            df[column] = ""
    return df[QUEUE_COLUMNS].fillna("").astype(str)


def save_queue(df: pd.DataFrame) -> pd.DataFrame:
    for column in QUEUE_COLUMNS:
        if column not in df.columns:
            df[column] = ""
    df = df[QUEUE_COLUMNS].fillna("")
    df.to_csv(queue_path(), index=False)
    return df


def remove_queue_items(ids: list[str]) -> tuple[pd.DataFrame, int]:
    queue = ensure_queue()
    if queue.empty or not ids:
        return queue, 0
    id_set = {str(item) for item in ids}
    mask = queue["queue_id"].astype(str).isin(id_set) | queue["post_id"].astype(str).isin(id_set)
    removed = int(mask.sum())
    queue = queue[~mask].reset_index(drop=True)
    save_queue(queue)
    return queue, removed


def enqueue_posts(post_ids: list[str], platforms: list[str], scheduled_time: str = "", random_delay_minutes: int = 0) -> pd.DataFrame:
    posts = read_social_post_report()
    queue = ensure_queue()
    existing_ids = set(queue["queue_id"].astype(str)) if not queue.empty else set()
    existing_post_platforms = set()
    if not queue.empty:
        existing_post_platforms = {
            (str(row.get("post_id", "")), str(row.get("platform", "")))
            for _, row in queue.iterrows()
            if str(row.get("status", "")).lower() not in {"rejected", "removed", "deleted"}
        }
    rows = []
    schedule = load_social_schedule()
    slot_counters: dict[str, int] = {}
    manual_base_time = parse_time(scheduled_time)
    for _, post in posts.iterrows():
        if str(post.get("post_id", "")) not in post_ids:
            continue
        platform = str(post.get("platform", ""))
        if platforms and platform not in platforms:
            continue
        if (str(post.get("post_id", "")), platform) in existing_post_platforms:
            continue
        queue_id = f"{post.get('post_id', '')}-{len(existing_ids) + len(rows) + 1}"
        if queue_id in existing_ids:
            continue
        if manual_base_time:
            delay = random.randint(0, max(0, random_delay_minutes)) if random_delay_minutes else 0
            scheduled = manual_base_time + timedelta(minutes=delay + len(rows) * 15)
        else:
            index = slot_counters.get(platform, 0)
            scheduled = next_schedule_slot(platform, index, schedule, queue, random_delay_minutes=random_delay_minutes)
            slot_counters[platform] = index + 1
        rows.append(
            {
                "queue_id": queue_id,
                "post_id": str(post.get("post_id", "")),
                "draft_id": str(post.get("draft_id", "")),
                "platform": platform,
                "title": str(post.get("title", "")),
                "article_url": str(post.get("article_url", "")),
                "post_file": str(post.get("output_path", "")),
                "status": "Scheduled",
                "scheduled_time": scheduled.isoformat(timespec="seconds"),
                "approved_at": datetime.now().isoformat(timespec="seconds"),
                "published_at": "",
                "last_attempt": "",
                "attempts": "0",
                "error": "",
            }
        )
    if rows:
        queue = pd.concat([queue, pd.DataFrame(rows)], ignore_index=True)
        save_queue(queue)
    return queue


def clear_duplicate_scheduled_posts() -> tuple[pd.DataFrame, int]:
    queue = ensure_queue()
    if queue.empty:
        return queue, 0
    before = len(queue)
    scheduled = queue["status"].astype(str).str.lower() == "scheduled"
    dedupe_cols = ["draft_id", "article_url", "platform", "post_id"]
    queue = pd.concat(
        [
            queue[~scheduled],
            queue[scheduled].drop_duplicates(subset=dedupe_cols, keep="first"),
        ],
        ignore_index=True,
    )
    removed = before - len(queue)
    save_queue(queue)
    return queue, removed


def process_due_queue(dry_run: bool = True) -> dict[str, int]:
    queue = ensure_queue()
    if queue.empty:
        return {"processed": 0, "published": 0, "failed": 0, "skipped": 0}
    now = datetime.now()
    processed = published = failed = skipped = 0
    for idx, row in queue.iterrows():
        if str(row.get("status", "")) not in {"Scheduled", "Approved"}:
            continue
        scheduled = parse_time(str(row.get("scheduled_time", ""))) or now
        if scheduled > now:
            skipped += 1
            continue
        platform = str(row.get("platform", ""))
        if over_daily_limit(queue, platform):
            skipped += 1
            continue
        processed += 1
        if dry_run:
            queue.loc[idx, "last_attempt"] = now.isoformat(timespec="seconds")
            queue.loc[idx, "error"] = "dry_run_only"
            skipped += 1
            continue
        ok, message = publish_row(row.to_dict())
        queue.loc[idx, "last_attempt"] = now.isoformat(timespec="seconds")
        queue.loc[idx, "attempts"] = str(int(str(row.get("attempts", "0") or "0")) + 1)
        if ok:
            queue.loc[idx, "status"] = "Published"
            queue.loc[idx, "published_at"] = now.isoformat(timespec="seconds")
            queue.loc[idx, "error"] = ""
            published += 1
        else:
            queue.loc[idx, "status"] = "Failed"
            queue.loc[idx, "error"] = message
            failed += 1
    save_queue(queue)
    return {"processed": processed, "published": published, "failed": failed, "skipped": skipped}


def process_due_queue_cli(dry_run: bool = False) -> dict[str, int]:
    load_dotenv()
    queue = ensure_queue()
    now = datetime.now()
    print(f"Loaded queue rows: {len(queue)}")
    if queue.empty:
        print(f"Queue file: {queue_path()}")
        return {"processed": 0, "published": 0, "failed": 0, "skipped": 0, "due": 0}

    scheduled_mask = queue["status"].astype(str).str.lower() == "scheduled"
    due_mask = scheduled_mask & queue["scheduled_time"].astype(str).apply(lambda value: is_due_now(value, now))
    due_count = int(due_mask.sum())
    print(f"Scheduled rows: {int(scheduled_mask.sum())}")
    print(f"Due now: {due_count}")

    processed = published = failed = skipped = 0
    for idx, row in queue[due_mask].iterrows():
        platform = str(row.get("platform", "")).strip().lower()
        queue_id = str(row.get("queue_id", "") or row.get("post_id", ""))
        print(f"- Queue {queue_id}: platform={platform or 'unknown'}")
        if platform != "telegram":
            print(f"  skipped: {platform} is copy-ready/safe mode only")
            skipped += 1
            continue
        if over_daily_limit(queue, platform):
            print("  skipped: telegram daily limit reached")
            skipped += 1
            continue

        processed += 1
        attempt_time = now.isoformat(timespec="seconds")
        queue.loc[idx, "last_attempt"] = attempt_time
        queue.loc[idx, "attempts"] = str(safe_int(row.get("attempts", "0")) + 1)

        if dry_run:
            print("  dry-run: Telegram message would be sent")
            queue.loc[idx, "error"] = "dry_run_only"
            skipped += 1
            continue

        ok, message = publish_row(row.to_dict())
        if ok:
            print("  Telegram send success")
            queue.loc[idx, "status"] = "Published"
            queue.loc[idx, "published_at"] = attempt_time
            queue.loc[idx, "error"] = ""
            published += 1
        else:
            print(f"  Telegram send error: {message}")
            queue.loc[idx, "error"] = message
            failed += 1

    save_queue(queue)
    result = {"processed": processed, "published": published, "failed": failed, "skipped": skipped, "due": due_count}
    print(f"Result: {result}")
    return result


def publish_row(row: dict[str, str]) -> tuple[bool, str]:
    platform = str(row.get("platform", ""))
    post_file = Path(str(row.get("post_file", "")))
    message = post_file.read_text(encoding="utf-8") if post_file.exists() else str(row.get("title", ""))
    if platform == "telegram":
        return send_telegram_message(message)
    return False, f"{platform} is safe-copy mode only. No automatic posting configured."


def send_telegram_message(message: str) -> tuple[bool, str]:
    config = load_social_accounts().get("telegram", {})
    token = os.getenv("TELEGRAM_BOT_TOKEN", str(config.get("bot_token", ""))).strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", str(config.get("chat_id", ""))).strip()
    if not token or not chat_id:
        return False, "Telegram token/chat_id is not configured."
    payload = json.dumps({"chat_id": chat_id, "text": message, "parse_mode": "HTML", "disable_web_page_preview": False}).encode("utf-8")
    request = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            body = response.read().decode("utf-8", errors="ignore")
            logger.info("telegram_post_sent %s", body[:300])
            return True, body
    except urllib.error.URLError as exc:
        logger.warning("telegram_post_failed %s", exc)
        return False, str(exc)


def over_daily_limit(queue: pd.DataFrame, platform: str) -> bool:
    schedule = load_social_schedule()
    limit = int(schedule.get(platform, {}).get("max_posts_per_day", PLATFORM_LIMITS.get(platform, 6)) or PLATFORM_LIMITS.get(platform, 6))
    today = datetime.now().date().isoformat()
    if queue.empty:
        return False
    published_today = queue[
        (queue["platform"].astype(str) == platform)
        & (queue["status"].astype(str) == "Published")
        & (queue["published_at"].astype(str).str.startswith(today))
    ]
    return len(published_today) >= limit


def parse_time(value: str) -> datetime | None:
    value = str(value or "").strip()
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def normalize_daily_times(value: object) -> list[str]:
    if isinstance(value, str):
        raw_items = [item.strip() for item in value.split(",")]
    elif isinstance(value, list):
        raw_items = [str(item).strip() for item in value]
    else:
        raw_items = []
    result = []
    for item in raw_items:
        if not item:
            continue
        if len(item) == 4 and item[1] == ":":
            item = f"0{item}"
        if len(item) == 5 and item[2] == ":":
            hh, mm = item.split(":", 1)
            if hh.isdigit() and mm.isdigit() and 0 <= int(hh) <= 23 and 0 <= int(mm) <= 59:
                normalized = f"{int(hh):02d}:{int(mm):02d}"
                if normalized not in result:
                    result.append(normalized)
    return result or ["09:00"]


def next_schedule_slot(
    platform: str,
    offset: int,
    schedule: dict[str, dict[str, object]] | None = None,
    queue: pd.DataFrame | None = None,
    random_delay_minutes: int = 0,
) -> datetime:
    schedule = schedule or load_social_schedule()
    config = schedule.get(platform, DEFAULT_SCHEDULE.get(platform, DEFAULT_SCHEDULE["telegram"]))
    times = normalize_daily_times(config.get("daily_times", []))
    max_per_day = max(1, int(config.get("max_posts_per_day", len(times)) or len(times)))
    usable_times = times[:max_per_day]
    now = datetime.now()
    existing_counts = scheduled_counts_by_day(queue, platform) if queue is not None else {}
    candidates: list[datetime] = []
    for day_offset in range(90):
        target_day = now.date() + timedelta(days=day_offset)
        day_key = target_day.isoformat()
        already = existing_counts.get(day_key, 0)
        capacity = max(0, max_per_day - already)
        if capacity <= 0:
            continue
        for time_value in usable_times[already : already + capacity]:
            hour, minute = [int(part) for part in time_value.split(":")]
            scheduled = datetime.combine(target_day, datetime.min.time()).replace(hour=hour, minute=minute)
            if scheduled > now:
                candidates.append(scheduled)
        if len(candidates) > offset:
            delay = random.randint(0, max(0, random_delay_minutes)) if random_delay_minutes else 0
            return candidates[offset] + timedelta(minutes=delay)
    fallback = now + timedelta(days=max(1, offset // max_per_day), minutes=15 * offset)
    return fallback


def scheduled_counts_by_day(queue: pd.DataFrame | None, platform: str) -> dict[str, int]:
    if queue is None or queue.empty:
        return {}
    rows = queue[
        (queue["platform"].astype(str) == platform)
        & (queue["status"].astype(str).str.lower().isin(["scheduled", "published"]))
    ]
    counts: dict[str, int] = {}
    for value in rows["scheduled_time"].astype(str):
        parsed = parse_time(value)
        if not parsed:
            continue
        key = parsed.date().isoformat()
        counts[key] = counts.get(key, 0) + 1
    return counts


def is_due_now(value: str, now: datetime) -> bool:
    scheduled = parse_time(value)
    if scheduled is None:
        return True
    return scheduled <= now


def safe_int(value: object) -> int:
    try:
        return int(str(value or "0"))
    except ValueError:
        return 0


def write_rows(path: Path, rows: list[dict[str, str]], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in columns})


def main() -> None:
    parser = argparse.ArgumentParser(description="Process local-safe social publish queue.")
    parser.add_argument("--dry-run", action="store_true", help="Print due Telegram posts without sending.")
    args = parser.parse_args()
    process_due_queue_cli(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
