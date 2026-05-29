from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

from config import settings
from modules.social_draft_generator import (
    load_all_social_drafts,
    move_draft_status,
    social_status_dir,
)
from modules.social_publisher import ensure_queue as ensure_publish_queue, save_queue as save_publish_queue


DEFAULT_AUTOMATION_SCHEDULE = {
    "timezone": "Asia/Ho_Chi_Minh",
    "daily_slots": ["07:30", "20:30"],
    "max_posts_per_day": 2,
    "require_approval": True,
    "auto_post_enabled": False,
}


def schedule_config_path() -> Path:
    return settings.base_dir / "config" / "social_schedule.json"


def load_automation_schedule() -> dict[str, object]:
    path = schedule_config_path()
    if not path.exists():
        save_automation_schedule(DEFAULT_AUTOMATION_SCHEDULE)
        return dict(DEFAULT_AUTOMATION_SCHEDULE)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        payload = {}
    config = dict(DEFAULT_AUTOMATION_SCHEDULE)
    if isinstance(payload, dict):
        for key in DEFAULT_AUTOMATION_SCHEDULE:
            if key in payload:
                config[key] = payload[key]
    config["daily_slots"] = normalize_daily_slots(config.get("daily_slots"))
    config["max_posts_per_day"] = max(1, int(config.get("max_posts_per_day") or 2))
    return config


def save_automation_schedule(config: dict[str, object]) -> None:
    path = schedule_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    existing: dict[str, object] = {}
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            existing = {}
    existing.update(config)
    path.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")


def ensure_automation_schedule_config() -> dict[str, object]:
    path = schedule_config_path()
    if not path.exists():
        save_automation_schedule(DEFAULT_AUTOMATION_SCHEDULE)
    else:
        config = load_automation_schedule()
        save_automation_schedule(config)
    return load_automation_schedule()


def normalize_daily_slots(value: object) -> list[str]:
    if isinstance(value, str):
        raw = [item.strip() for item in value.split(",")]
    elif isinstance(value, list):
        raw = [str(item).strip() for item in value]
    else:
        raw = []
    slots: list[str] = []
    for item in raw:
        try:
            parsed = datetime.strptime(item, "%H:%M")
            slots.append(parsed.strftime("%H:%M"))
        except ValueError:
            continue
    return slots or list(DEFAULT_AUTOMATION_SCHEDULE["daily_slots"])


def next_schedule_times(count: int, config: dict[str, object] | None = None, start: datetime | None = None) -> list[str]:
    config = config or load_automation_schedule()
    slots = normalize_daily_slots(config.get("daily_slots"))
    max_posts = min(max(1, int(config.get("max_posts_per_day") or 2)), len(slots))
    usable_slots = slots[:max_posts]
    cursor = (start or datetime.now()).date()
    results: list[str] = []
    while len(results) < count:
        for slot in usable_slots:
            if len(results) >= count:
                break
            scheduled = datetime.combine(cursor, datetime.strptime(slot, "%H:%M").time())
            if scheduled <= (start or datetime.now()):
                scheduled = scheduled + timedelta(days=1)
            results.append(scheduled.isoformat(timespec="minutes"))
        cursor = cursor + timedelta(days=1)
    return results


def schedule_approved_posts(limit: int | None = None, dry_run: bool = False) -> list[dict[str, str]]:
    ensure_automation_schedule_config()
    records = [
        row for row in load_all_social_drafts()
        if str(row.get("status", "")).lower() == "approved"
    ]
    if limit is not None:
        records = records[:limit]
    scheduled_times = next_schedule_times(len(records))
    scheduled: list[dict[str, str]] = []
    for record, scheduled_at in zip(records, scheduled_times):
        updated = dict(record)
        updated["scheduled_at"] = scheduled_at
        updated["status"] = "scheduled"
        scheduled.append(updated)
        if not dry_run:
            move_draft_status(str(record.get("id", "")), "scheduled", {"scheduled_at": scheduled_at})
    return scheduled


def scheduled_count() -> int:
    path = social_status_dir("scheduled")
    return len(list(path.glob("*.json"))) if path.exists() else 0


def schedule_approved_queue_posts(limit: int | None = None, dry_run: bool = False) -> list[dict[str, str]]:
    """Schedule approved rows in data/social_publish_queue.csv without publishing.

    This is the multi-platform queue scheduler used by the human-approved publisher.
    It only moves approved rows to Scheduled and assigns a time; platform publishing is
    handled later by modules.social_publisher in dry-run/manual-safe mode by default.
    """
    config = ensure_automation_schedule_config()
    queue = ensure_publish_queue()
    if queue.empty:
        return []
    mask = queue["status"].astype(str).str.lower().isin(["approved"])
    approved = queue[mask].copy()
    if limit is not None:
        approved = approved.head(limit)
    scheduled_times = next_schedule_times(len(approved), config=config)
    scheduled_rows: list[dict[str, str]] = []
    for (idx, row), scheduled_at in zip(approved.iterrows(), scheduled_times):
        updated = row.to_dict()
        updated["scheduled_time"] = scheduled_at
        updated["status"] = "Scheduled"
        scheduled_rows.append({key: str(value) for key, value in updated.items()})
        if not dry_run:
            queue.loc[idx, "scheduled_time"] = scheduled_at
            queue.loc[idx, "status"] = "Scheduled"
    if not dry_run:
        save_publish_queue(queue)
    return scheduled_rows
