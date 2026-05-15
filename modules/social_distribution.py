from __future__ import annotations

import csv
import argparse
import json
import mimetypes
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont

from config import settings


CALENDAR_COLUMNS = [
    "id",
    "platform",
    "post_title",
    "post_body",
    "target_url",
    "status",
    "scheduled_date",
    "scheduled_time",
    "approved_by_user",
    "posted_at",
    "notes",
    "retry_count",
    "next_retry_time",
    "priority",
    "content_style",
    "topic",
    "angle",
]

VALID_STATUSES = [
    "Draft",
    "Pending approval",
    "Pending Review",
    "Approved",
    "Scheduled",
    "Ready to Post",
    "Published",
    "Posted",
    "Needs Edit",
    "Rejected",
    "Failed",
]

PUBLISH_LOG_COLUMNS = ["post_id", "platform", "mode", "scheduled_time", "action", "status", "error"]
DEFAULT_PUBLISH_MODE = {
    "telegram": "manual",
    "facebook": "manual",
    "linkedin": "manual",
    "twitter": "manual",
}
DEFAULT_SOCIAL_LIMITS = {
    "telegram": {"daily_limit": 10, "cooldown_minutes": 30},
    "facebook": {"daily_limit": 2, "cooldown_minutes": 180},
    "linkedin": {"daily_limit": 2, "cooldown_minutes": 360},
    "twitter": {"daily_limit": 5, "cooldown_minutes": 60},
}
X_THREAD_MODES = [
    "Quick tips",
    "Short post",
    "Viral thread",
    "Authority style",
    "Comparison review",
    "Founder story style",
    "Educational",
]
CONTENT_ANGLE_HISTORY_COLUMNS = [
    "created_at",
    "topic",
    "angle",
    "platform",
    "content_style",
    "post_id",
    "hook",
    "opening",
    "cta",
    "target_url",
    "status",
]
MAX_RETRY_COUNT = 3
RETRY_DELAY_MINUTES = 15


@dataclass(frozen=True)
class SocialSeed:
    platform: str
    title: str
    url_path: str
    hook: str
    bullets: tuple[str, str, str]
    cta: str
    hashtags: str
    schedule_time: str
    content_style: str = "practical_review"


def calendar_path() -> Path:
    return settings.data_dir / "social_calendar.csv"


def social_queue_dir() -> Path:
    return settings.base_dir / "draft_output" / "social_queue"


def social_assets_dir() -> Path:
    return settings.base_dir / "social_assets"


def accounts_example_path() -> Path:
    return settings.data_dir / "social_accounts.example.json"


def accounts_config_path() -> Path:
    return settings.base_dir / "config" / "social_accounts.json"


def publish_log_path() -> Path:
    return settings.data_dir / "social_publish_log.csv"


def publish_mode_path() -> Path:
    return settings.base_dir / "config" / "social_publish_mode.json"


def social_limits_path() -> Path:
    return settings.base_dir / "config" / "social_limits.json"


def ai_coding_topics_path() -> Path:
    return settings.base_dir / "config" / "ai_coding_topics.json"


def ai_coding_topic_suggestions_path() -> Path:
    return settings.data_dir / "ai_coding_topic_suggestions.csv"


def content_angle_history_path() -> Path:
    return settings.data_dir / "content_angle_history.csv"


def deep_dive_output_dir() -> Path:
    return settings.base_dir / "draft_output" / "content_angles"


def ensure_social_distribution_assets() -> pd.DataFrame:
    social_queue_dir().mkdir(parents=True, exist_ok=True)
    social_assets_dir().mkdir(parents=True, exist_ok=True)
    ensure_accounts_example()
    ensure_social_accounts_config()
    ensure_publish_mode_config()
    ensure_social_limits_config()
    ensure_publish_log()
    ensure_ai_coding_campaign_topics()
    if not content_angle_history_path().exists():
        save_content_angle_history(pd.DataFrame(columns=CONTENT_ANGLE_HISTORY_COLUMNS))
    existing = load_social_calendar()
    seeds = seed_posts()
    existing_by_id = {
        str(row.get("id", "")): row
        for row in existing.to_dict("records")
        if str(row.get("id", "")).strip()
    } if not existing.empty else {}
    rows = existing.to_dict("records") if not existing.empty else []
    rows_by_id = {str(row.get("id", "")): row for row in rows}
    start = date.today()
    for index, seed in enumerate(seeds, start=1):
        post_id = f"social-seed-{index:02d}-{seed.platform.lower().replace('/', 'x')}"
        scheduled = start + timedelta(days=(index - 1) // 2)
        body = render_post_body(seed)
        target_url = full_url(seed.url_path, seed.platform)
        if post_id in rows_by_id:
            row = rows_by_id[post_id]
            row["platform"] = seed.platform
            row["post_title"] = seed.title
            row["post_body"] = body
            row["target_url"] = target_url
            row["content_style"] = seed.content_style
            row["topic"] = row.get("topic", "")
            row["angle"] = row.get("angle", "")
            row["scheduled_date"] = str(row.get("scheduled_date", "") or scheduled.isoformat())
            row["scheduled_time"] = seed.schedule_time
            row["notes"] = str(row.get("notes", "") or "Copy-ready seed. Review before posting manually.")
        else:
            rows.append({
                "id": post_id,
                "platform": seed.platform,
                "post_title": seed.title,
                "post_body": body,
                "target_url": target_url,
                "status": "Pending Review",
                "scheduled_date": scheduled.isoformat(),
                "scheduled_time": seed.schedule_time,
                "approved_by_user": "false",
                "posted_at": "",
                "notes": "Copy-ready seed. Review before posting manually.",
                "retry_count": "0",
                "next_retry_time": "",
                "priority": default_priority(seed),
                "content_style": seed.content_style,
                "topic": "",
                "angle": "",
            })
        write_queue_markdown(post_id, seed, body, target_url, scheduled.isoformat())
        ensure_social_asset(post_id, seed)
    df = pd.DataFrame(rows, columns=CALENDAR_COLUMNS).fillna("")
    save_social_calendar(df)
    return df


def load_social_calendar() -> pd.DataFrame:
    path = calendar_path()
    if not path.exists():
        return pd.DataFrame(columns=CALENDAR_COLUMNS)
    try:
        df = pd.read_csv(path)
    except Exception:
        df = pd.DataFrame(columns=CALENDAR_COLUMNS)
    for column in CALENDAR_COLUMNS:
        if column not in df.columns:
            df[column] = ""
    df = df[CALENDAR_COLUMNS].fillna("").astype(str)
    df["status"] = df["status"].replace({"Needs edit": "Needs Edit"})
    df["retry_count"] = df["retry_count"].replace({"": "0"})
    df["priority"] = df["priority"].replace({"": "medium"})
    df["content_style"] = df["content_style"].replace({"": "practical_review"})
    return df


def save_social_calendar(df: pd.DataFrame) -> pd.DataFrame:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    for column in CALENDAR_COLUMNS:
        if column not in df.columns:
            df[column] = ""
    df = df[CALENDAR_COLUMNS].fillna("")
    df["retry_count"] = df["retry_count"].replace({"": "0"})
    df["priority"] = df["priority"].replace({"": "medium"})
    df["content_style"] = df["content_style"].replace({"": "practical_review"})
    df.to_csv(calendar_path(), index=False, quoting=csv.QUOTE_MINIMAL)
    return df


def update_calendar_status(post_id: str, status: str, note: str = "") -> pd.DataFrame:
    df = load_social_calendar()
    if df.empty or post_id not in set(df["id"].astype(str)):
        return df
    if status not in VALID_STATUSES:
        status = "Needs Edit"
    mask = df["id"].astype(str) == str(post_id)
    df.loc[mask, "status"] = status
    if status == "Approved":
        df.loc[mask, "approved_by_user"] = "true"
    elif status == "Rejected":
        df.loc[mask, "approved_by_user"] = "false"
    if status == "Posted":
        df.loc[mask, "posted_at"] = datetime.now().isoformat(timespec="seconds")
    if note:
        df.loc[mask, "notes"] = note
    return save_social_calendar(df)


def ensure_accounts_example() -> None:
    path = accounts_example_path()
    if path.exists():
        return
    payload = {
        "telegram": {
            "enabled": False,
            "bot_token_env": "TELEGRAM_BOT_TOKEN",
            "chat_id_env": "TELEGRAM_CHAT_ID",
            "mode": "manual_or_future_api",
        },
        "facebook": {
            "enabled": False,
            "page_name": "",
            "mode": "manual_copy_ready",
        },
        "linkedin": {
            "enabled": False,
            "profile_or_page": "",
            "mode": "manual_copy_ready",
        },
        "twitter": {
            "enabled": False,
            "username": "",
            "mode": "manual_copy_ready",
        },
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def ensure_social_accounts_config() -> None:
    path = accounts_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            payload = {}
    else:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    telegram = payload.setdefault("telegram", {})
    if isinstance(telegram, dict):
        telegram.setdefault("enabled", False)
        telegram.setdefault("telegram_bot_token", str(telegram.get("bot_token", "")))
        telegram.setdefault("telegram_chat_id", str(telegram.get("chat_id", "")))
        telegram.setdefault("note", "Do not commit real tokens. Prefer .env TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID.")
    payload.setdefault("facebook", {"enabled": False, "mode": "copy_ready_only"})
    payload.setdefault("linkedin", {"enabled": False, "mode": "copy_ready_only"})
    payload.setdefault("twitter", {"enabled": False, "mode": "copy_ready_only"})
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def ai_coding_campaign_topics() -> list[dict[str, str]]:
    return [
        {
            "title": "Copilot vs Codex",
            "slug": "copilot-vs-codex",
            "page_type": "Comparison page",
            "topic": "Copilot vs Codex",
            "target_path": "best-ai-coding-tools-2026",
            "content_style": "comparison",
            "hook": "Copilot writes faster. Codex cleans up better.",
            "angle": "Copilot is useful for lightweight autocomplete, but Codex is where I usually go when the repo needs deeper repair.",
        },
        {
            "title": "Cursor vs Codex",
            "slug": "cursor-vs-codex",
            "page_type": "Comparison page",
            "topic": "Cursor vs Codex",
            "target_path": "review/cursor",
            "content_style": "comparison",
            "hook": "Cursor is fast inside a clean repo. Codex is better when the project is already broken.",
            "angle": "Cursor helps me iterate in context, while Codex is stronger when the fix requires architecture-level reasoning.",
        },
        {
            "title": "Windsurf + Codex workflow",
            "slug": "windsurf-codex-workflow",
            "page_type": "Workflow article",
            "topic": "Windsurf + Codex workflow",
            "target_path": "windsurf-review",
            "content_style": "workflow_tip",
            "hook": "Windsurf is fast for scaffolding, but Codex is where I usually repair the mess.",
            "angle": "The workflow that works best for me is rough structure first, then logic repair, build fixes, and final cleanup.",
        },
        {
            "title": "When Codex fixes what Cursor breaks",
            "slug": "when-codex-fixes-what-cursor-breaks",
            "page_type": "Failure case article",
            "topic": "When Codex fixes what Cursor breaks",
            "target_path": "review/cursor",
            "content_style": "failure_case",
            "hook": "The second failed fix is the real AI coding benchmark.",
            "angle": "Cursor is useful for fast repo edits, but repeated small fixes can loop. That is when I move the problem to Codex.",
        },
        {
            "title": "Why I stopped using only one AI coding tool",
            "slug": "why-i-stopped-using-one-ai-coding-tool",
            "page_type": "Workflow article",
            "topic": "Why I stopped using only one AI coding tool",
            "target_path": "best-ai-coding-tools-2026",
            "content_style": "hot_take",
            "hook": "I stopped asking which AI coding tool is best. I started asking which one fits each stage.",
            "angle": "One tool rarely wins every stage: bootstrapping, debugging, refactoring, deployment, and final review behave differently.",
        },
        {
            "title": "My actual AI coding workflow in 2026",
            "slug": "my-actual-ai-coding-workflow-2026",
            "page_type": "Workflow article",
            "topic": "My actual AI coding workflow in 2026",
            "target_path": "best-ai-coding-tools-2026",
            "content_style": "builder_note",
            "hook": "My current workflow: Windsurf for rough structure, Codex for repair, Cursor for iteration, Copilot for light autocomplete.",
            "angle": "The stack only works when each tool has a job. If every tool is asked to do everything, cleanup gets expensive.",
        },
        {
            "title": "Which AI survives the second failed fix?",
            "slug": "which-ai-survives-the-second-failed-fix",
            "page_type": "Problem-based SEO article",
            "topic": "Which AI survives the second failed fix?",
            "target_path": "comparisons/cursor-vs-copilot",
            "content_style": "failure_case",
            "hook": "Most AI coding demos collapse when the repo gets messy.",
            "angle": "The real benchmark is not the first generated answer. It is what happens after two fixes fail and the build is still red.",
        },
    ]


def content_angle_definitions() -> list[dict[str, object]]:
    return [
        {
            "angle": "beginner_guide",
            "content_style": "practical_review",
            "title": "Beginner guide",
            "hook": "The mistake beginners make is asking one AI coding tool to do every stage.",
            "summary": "Use the topic to explain the first practical decision: which tool handles setup, which one handles repair, and which one should stay in autocomplete mode.",
            "cta": "Read the practical guide",
            "suggested_social_styles": ["practical_review", "workflow_tip"],
        },
        {
            "angle": "advanced_debugging",
            "content_style": "failure_case",
            "title": "Advanced debugging",
            "hook": "The second failed fix is where AI coding tools stop looking equal.",
            "summary": "Focus on repo context, build errors, duplicated logic, and how the tool behaves after the first confident answer fails.",
            "cta": "See the debugging breakdown",
            "suggested_social_styles": ["failure_case", "builder_note"],
        },
        {
            "angle": "workflow_tip",
            "content_style": "workflow_tip",
            "title": "Workflow tip",
            "hook": "The best AI coding workflow is usually a handoff, not a single-tool bet.",
            "summary": "Show a practical sequence: scaffold, repair, iterate, review, then deploy.",
            "cta": "Read the workflow note",
            "suggested_social_styles": ["workflow_tip", "builder_note"],
        },
        {
            "angle": "failure_case",
            "content_style": "failure_case",
            "title": "Failure case",
            "hook": "Most AI coding demos hide the cleanup step.",
            "summary": "Use a realistic failure: repeated patches, broken build, weak context, or architecture drift.",
            "cta": "Read what failed",
            "suggested_social_styles": ["failure_case", "hot_take"],
        },
        {
            "angle": "hot_take",
            "content_style": "hot_take",
            "title": "Hot take",
            "hook": "Autocomplete speed is not the same as engineering leverage.",
            "summary": "Challenge the usual tool ranking and explain why the winner changes by project stage.",
            "cta": "Read the take",
            "suggested_social_styles": ["hot_take", "comparison"],
        },
        {
            "angle": "pricing_reality",
            "content_style": "practical_review",
            "title": "Pricing reality",
            "hook": "The expensive part of AI coding tools is not always the monthly plan.",
            "summary": "Talk about cleanup time, review cost, team adoption, and when a cheaper tool becomes expensive.",
            "cta": "See the pricing reality",
            "suggested_social_styles": ["practical_review", "builder_note"],
        },
        {
            "angle": "architecture_scaling",
            "content_style": "builder_note",
            "title": "Architecture scaling",
            "hook": "AI coding tools are easy to like until the architecture starts drifting.",
            "summary": "Frame the topic around module boundaries, repeated logic, and what happens when the repo grows.",
            "cta": "Read the architecture notes",
            "suggested_social_styles": ["builder_note", "failure_case"],
        },
        {
            "angle": "repo_context",
            "content_style": "comparison",
            "title": "Repo context",
            "hook": "Repo context beats demo speed once the project stops being clean.",
            "summary": "Compare how tools read existing files, keep context, and avoid repeating failed fixes.",
            "cta": "Compare repo context",
            "suggested_social_styles": ["comparison", "hot_take"],
        },
        {
            "angle": "startup_team",
            "content_style": "workflow_tip",
            "title": "Startup team",
            "hook": "For small teams, the best AI coding tool is the one that does not create review debt.",
            "summary": "Focus on adoption, code review, handoff, and risk for lean teams.",
            "cta": "Read the startup workflow",
            "suggested_social_styles": ["workflow_tip", "practical_review"],
        },
        {
            "angle": "solo_builder",
            "content_style": "builder_note",
            "title": "Solo builder",
            "hook": "Solo builders do not need the flashiest AI tool. They need the least cleanup drag.",
            "summary": "Discuss speed, mental load, debugging fatigue, and shipping alone.",
            "cta": "Read the solo builder note",
            "suggested_social_styles": ["builder_note", "workflow_tip"],
        },
        {
            "angle": "productivity_myth",
            "content_style": "hot_take",
            "title": "Productivity myth",
            "hook": "AI coding productivity is not measured by how much code appears on screen.",
            "summary": "Separate generation speed from shipped, reviewed, working code.",
            "cta": "Read the productivity myth",
            "suggested_social_styles": ["hot_take", "failure_case"],
        },
        {
            "angle": "second_failed_fix",
            "content_style": "failure_case",
            "title": "Second failed fix",
            "hook": "The second failed fix is my favorite AI coding benchmark.",
            "summary": "Make the repeated-fix moment the main test for reasoning, context, and tool limits.",
            "cta": "See the second-fix test",
            "suggested_social_styles": ["failure_case", "comparison"],
        },
        {
            "angle": "ai_limitations",
            "content_style": "practical_review",
            "title": "AI limitations",
            "hook": "The more I use AI coding tools, the more I respect their limits.",
            "summary": "Discuss what should stay human-reviewed: architecture, security, policy, deployment, and final judgment.",
            "cta": "Read the limitations",
            "suggested_social_styles": ["practical_review", "builder_note"],
        },
        {
            "angle": "real_world_tradeoff",
            "content_style": "comparison",
            "title": "Real-world tradeoff",
            "hook": "Every AI coding tool tradeoff shows up after the first clean demo.",
            "summary": "Compare speed, context, stability, adoption, and debugging cost without making any tool perfect.",
            "cta": "Read the tradeoff",
            "suggested_social_styles": ["comparison", "practical_review"],
        },
        {
            "angle": "migration_story",
            "content_style": "workflow_tip",
            "title": "Migration story",
            "hook": "Switching AI coding tools only helps if the workflow changes too.",
            "summary": "Explain what changes when moving from one tool to a staged workflow across Cursor, Windsurf, Codex, and Copilot.",
            "cta": "Read the migration story",
            "suggested_social_styles": ["workflow_tip", "builder_note"],
        },
    ]


def content_angle_dataframe() -> pd.DataFrame:
    rows = []
    for topic in ai_coding_campaign_topics():
        for definition in content_angle_definitions():
            rows.append({
                "topic": topic["topic"],
                "topic_slug": topic["slug"],
                "target_path": topic["target_path"],
                "angle": definition["angle"],
                "angle_title": definition["title"],
                "content_style": definition["content_style"],
                "hook": specialize_hook(topic, definition),
                "summary": definition["summary"],
                "cta": definition["cta"],
                "suggested_social_styles": ", ".join(definition["suggested_social_styles"]),
            })
    return pd.DataFrame(rows)


def specialize_hook(topic: dict[str, str], definition: dict[str, object]) -> str:
    topic_name = topic["topic"]
    base = str(definition["hook"])
    if "Codex" in topic_name and "Cursor" in topic_name:
        return base.replace("AI coding tools", "Cursor and Codex").replace("AI tool", "Cursor or Codex")
    if "Windsurf" in topic_name and "Codex" in topic_name:
        return base.replace("AI coding tools", "Windsurf and Codex").replace("AI tool", "Windsurf or Codex")
    if "Copilot" in topic_name:
        return base.replace("AI coding tools", "Copilot and Codex").replace("AI tool", "Copilot or Codex")
    return base


def load_content_angle_history() -> pd.DataFrame:
    path = content_angle_history_path()
    if not path.exists():
        return pd.DataFrame(columns=CONTENT_ANGLE_HISTORY_COLUMNS)
    try:
        df = pd.read_csv(path)
    except Exception:
        df = pd.DataFrame(columns=CONTENT_ANGLE_HISTORY_COLUMNS)
    for column in CONTENT_ANGLE_HISTORY_COLUMNS:
        if column not in df.columns:
            df[column] = ""
    return df[CONTENT_ANGLE_HISTORY_COLUMNS].fillna("").astype(str)


def save_content_angle_history(df: pd.DataFrame) -> pd.DataFrame:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    for column in CONTENT_ANGLE_HISTORY_COLUMNS:
        if column not in df.columns:
            df[column] = ""
    df = df[CONTENT_ANGLE_HISTORY_COLUMNS].fillna("")
    df.to_csv(content_angle_history_path(), index=False)
    return df


def generate_more_variations(topic_slug: str, angle: str, status: str = "Pending Review") -> pd.DataFrame:
    ensure_social_distribution_assets()
    angles = content_angle_dataframe()
    selected = angles[
        (angles["topic_slug"].astype(str) == str(topic_slug))
        & (angles["angle"].astype(str) == str(angle))
    ]
    if selected.empty:
        return pd.DataFrame(columns=CALENDAR_COLUMNS)
    meta = selected.iloc[0].to_dict()
    calendar = load_social_calendar()
    history = load_content_angle_history()
    existing_ids = set(calendar["id"].astype(str).tolist()) if not calendar.empty else set()
    rows = calendar.to_dict("records") if not calendar.empty else []
    history_rows = history.to_dict("records") if not history.empty else []
    platforms = [("X/Twitter", 3), ("LinkedIn", 2), ("Telegram", 2), ("Facebook", 2)]
    created: list[dict[str, str]] = []
    now_stamp = datetime.now().isoformat(timespec="seconds")
    day = date.today()
    for platform, count in platforms:
        for variant in range(1, count + 1):
            post_id = f"angle-{topic_slug}-{angle}-{normalize_platform_key(platform)}-{variant}"
            if post_id in existing_ids:
                continue
            seed = build_angle_seed(meta, platform, variant)
            body = render_post_body(seed)
            target_url = full_url(seed.url_path, seed.platform)
            scheduled = day + timedelta(days=max(0, len(rows) // 2))
            row = {
                "id": post_id,
                "platform": platform,
                "post_title": seed.title,
                "post_body": body,
                "target_url": target_url,
                "status": status,
                "scheduled_date": scheduled.isoformat(),
                "scheduled_time": seed.schedule_time,
                "approved_by_user": "false",
                "posted_at": "",
                "notes": f"Generated variation: {meta['topic']} / {meta['angle']}. Review before posting.",
                "retry_count": "0",
                "next_retry_time": "",
                "priority": "medium",
                "content_style": seed.content_style,
                "topic": str(meta["topic"]),
                "angle": str(meta["angle"]),
            }
            rows.append(row)
            created.append(row)
            write_queue_markdown(post_id, seed, body, target_url, scheduled.isoformat())
            ensure_social_asset(post_id, seed)
            opening = body.splitlines()[0].strip() if body else seed.hook
            history_rows.append({
                "created_at": now_stamp,
                "topic": str(meta["topic"]),
                "angle": str(meta["angle"]),
                "platform": platform,
                "content_style": seed.content_style,
                "post_id": post_id,
                "hook": seed.hook,
                "opening": opening,
                "cta": seed.cta,
                "target_url": target_url,
                "status": status,
            })
    save_social_calendar(pd.DataFrame(rows, columns=CALENDAR_COLUMNS))
    save_content_angle_history(pd.DataFrame(history_rows, columns=CONTENT_ANGLE_HISTORY_COLUMNS))
    return pd.DataFrame(created, columns=CALENDAR_COLUMNS)


def generate_deep_dive_outline(topic_slug: str, angle: str) -> Path | None:
    angles = content_angle_dataframe()
    selected = angles[
        (angles["topic_slug"].astype(str) == str(topic_slug))
        & (angles["angle"].astype(str) == str(angle))
    ]
    if selected.empty:
        return None
    meta = selected.iloc[0].to_dict()
    output_dir = deep_dive_output_dir()
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{topic_slug}-{angle}-deep-dive.md"
    topic = str(meta["topic"])
    title = f"{topic}: {meta['angle_title']} Deep Dive"
    content = f"""# {title}

Target length: 1500-3000 words

## Core angle
{meta['summary']}

## Opening hook
{meta['hook']}

## Suggested structure
1. Short answer for readers who are deciding quickly
2. Real workflow context: what project stage this applies to
3. What usually works well
4. What fails in a messy repo
5. Practical comparison table
6. Pricing and cleanup-time reality
7. Builder notes and mistakes to avoid
8. Recommended workflow
9. Alternatives and internal links
10. Final recommendation

## FAQ ideas
- Is this workflow better for beginners or experienced builders?
- What happens after the first AI-generated fix fails?
- Which tool is better for repo context?
- How should a solo builder test this setup?
- What pricing or review-time risk should teams consider?
- When should I avoid this workflow?

## Comparison table ideas
| Criterion | Tool/workflow A | Tool/workflow B | Practical note |
|---|---|---|---|
| Speed | Fast first draft | Slower repair | Measure cleanup, not only output |
| Repo context | Depends on setup | Stronger on messy tasks | Test on real files |
| Debugging | Good for small fixes | Better for deeper repair | Use after failed patch |
| Team fit | Easy to adopt | Needs clearer prompts | Review process matters |

## Internal link suggestions
- /best-ai-coding-tools-2026/
- /review/cursor/
- /review/github-copilot/
- /comparisons/cursor-vs-copilot/
- /windsurf-review/

## CTA
{meta['cta']}

Disclosure: Some links may be affiliate links. Reviews should stay practical, honest, and based on workflow evaluation.
"""
    path.write_text(content, encoding="utf-8")
    return path


def build_angle_seed(meta: dict[str, object], platform: str, variant: int) -> SocialSeed:
    topic = str(meta["topic"])
    angle = str(meta["angle"])
    target_path = str(meta["target_path"])
    style = str(meta["content_style"])
    title = f"{topic}: {meta['angle_title']} #{variant}"
    hook = angle_hook(topic, angle, platform, variant)
    bullets = angle_bullets(topic, angle, variant)
    cta = angle_cta(topic, angle, platform, variant)
    hashtags = "#AICoding #BuilderNotes #DeveloperTools"
    if normalize_platform_key(platform) == "linkedin":
        schedule_time = ["09:20", "14:40"][min(variant - 1, 1)]
    elif normalize_platform_key(platform) == "facebook":
        schedule_time = ["19:20", "20:40"][min(variant - 1, 1)]
    elif normalize_platform_key(platform) == "telegram":
        schedule_time = ["09:10", "20:10"][min(variant - 1, 1)]
    else:
        schedule_time = ["09:05", "13:15", "20:25"][min(variant - 1, 2)]
    return SocialSeed(platform, title, target_path, hook, bullets, cta, hashtags, schedule_time, style)


def angle_hook(topic: str, angle: str, platform: str, variant: int) -> str:
    options = {
        "beginner_guide": [
            f"If you are new to {topic}, do not start by asking which tool is smartest.",
            f"The beginner mistake with {topic}: treating every assistant like the same product.",
            f"{topic} gets easier when you split the workflow before choosing tools.",
        ],
        "advanced_debugging": [
            "The second failed fix is where AI coding tools get exposed.",
            f"{topic} only becomes interesting when the repo is already messy.",
            "The real debugging benchmark starts after the confident patch fails.",
        ],
        "workflow_tip": [
            f"My practical {topic} workflow is a handoff, not a loyalty test.",
            "I stopped forcing one AI coding tool to own the whole repo.",
            f"The useful way to think about {topic}: assign each tool a job.",
        ],
        "failure_case": [
            "The first AI fix looked clean. The build still failed.",
            "Most demos skip the part where generated code creates cleanup debt.",
            f"{topic} becomes real when duplicated logic starts spreading.",
        ],
        "hot_take": [
            "Hot take: autocomplete speed is overrated after the repo gets messy.",
            "Most AI coding rankings optimize for demos, not recovery.",
            f"{topic} is not a winner-takes-all decision.",
        ],
        "pricing_reality": [
            "The monthly price is not the real cost of an AI coding workflow.",
            "Cheap autocomplete gets expensive when it creates review debt.",
            f"Pricing for {topic} only makes sense after you count cleanup time.",
        ],
        "architecture_scaling": [
            "AI coding tools are easy to like until architecture starts drifting.",
            f"{topic} should be judged by how it handles boundaries, not snippets.",
            "The hard part is not generating code. It is keeping the shape of the system.",
        ],
        "repo_context": [
            "Repo context beats demo speed once the project stops being clean.",
            f"{topic} comes down to which tool remembers why the first fix failed.",
            "A tool that ignores surrounding files turns every bug into guesswork.",
        ],
        "startup_team": [
            "For startup teams, the best AI coding tool is the one that reduces review debt.",
            f"{topic} matters more when two people have to maintain the result.",
            "Small teams should optimize for handoff clarity, not just code volume.",
        ],
        "solo_builder": [
            "Solo builders need less cleanup drag, not more generated code.",
            f"{topic} looks different when you are the reviewer, deployer, and maintainer.",
            "The best solo workflow is the one that does not exhaust you at review time.",
        ],
        "productivity_myth": [
            "AI coding productivity is not measured by how much code appears on screen.",
            f"{topic} exposes the gap between output speed and shipped software.",
            "The productivity myth breaks when the second hour becomes cleanup.",
        ],
        "second_failed_fix": [
            "The second failed fix is my favorite AI coding benchmark.",
            f"{topic} should be tested after two wrong patches, not one perfect demo.",
            "A tool that survives the second failed fix earns more trust from me.",
        ],
        "ai_limitations": [
            "The more I use AI coding tools, the more I respect their limits.",
            f"{topic} is useful, but it still needs human boundaries.",
            "AI coding tools are assistants, not architecture owners.",
        ],
        "real_world_tradeoff": [
            f"The tradeoff in {topic} is speed now vs cleanup later.",
            "No AI coding tool wins every stage of a real project.",
            "The practical question is not best. It is best for which failure mode.",
        ],
        "migration_story": [
            "Switching AI coding tools only helps if the workflow changes too.",
            f"My {topic} migration lesson: do not move tools without changing prompts.",
            "The tool switch matters less than the handoff between drafting and repair.",
        ],
    }
    return options.get(angle, options["workflow_tip"])[(variant - 1) % 3]


def angle_bullets(topic: str, angle: str, variant: int) -> tuple[str, str, str]:
    pools = {
        "failure_case": (
            "The generated fix looked plausible but patched the symptom, not the cause.",
            "The build error forced me to inspect module boundaries instead of asking for another tiny patch.",
            "The cleanup was faster once I moved from broad prompts to a specific repair task.",
        ),
        "pricing_reality": (
            "A cheaper plan can still be expensive if every output needs heavy review.",
            "I compare tools by cleanup time, not just subscription price.",
            "The right tool should reduce the number of review loops, not create more of them.",
        ),
        "repo_context": (
            "Context matters more when the repo already has conventions and edge cases.",
            "The weaker tool repeats fixes because it misses why the last patch failed.",
            "The stronger workflow keeps the history of the problem visible.",
        ),
        "architecture_scaling": (
            "Scaffolding speed is useful, but architecture drift compounds quietly.",
            "Large refactors need boundaries, tests, and a tool that can explain tradeoffs.",
            "I trust smaller, reviewable changes more than one giant generated patch.",
        ),
        "startup_team": (
            "Fast code is not helpful if teammates cannot review it.",
            "Small teams need naming, structure, and deployment notes to stay readable.",
            "The tool should make handoff easier, not just output more files.",
        ),
        "solo_builder": (
            "When you are solo, every generated mistake comes back to you.",
            "The best workflow protects your focus during debugging and deployment.",
            "I prefer tools that help me finish cleanly over tools that only start quickly.",
        ),
    }
    default = (
        "Windsurf is useful for rough structure when I need speed at the start.",
        "Codex is where I move deeper repair, logic cleanup, and build failures.",
        "Cursor helps with fast iteration once the repo shape is already stable.",
    )
    selected = pools.get(angle, default)
    if variant % 2 == 0:
        return (selected[1], selected[2], selected[0])
    return selected


def angle_cta(topic: str, angle: str, platform: str, variant: int) -> str:
    options = [
        "Read the practical breakdown",
        "See the workflow note",
        "Compare the tradeoffs",
        "Read the full builder note",
    ]
    return options[(variant - 1) % len(options)]


def ensure_ai_coding_campaign_topics() -> None:
    path = ai_coding_topics_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        payload = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    payload["social_campaign_topics"] = ai_coding_campaign_topics()
    payload["content_angles"] = content_angle_definitions()
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    rows = []
    for topic in ai_coding_campaign_topics():
        output_path = settings.site_output_dir / topic["slug"] / "index.html"
        rows.append({
            "topic": topic["topic"],
            "suggested_slug": topic["slug"],
            "page_type": topic["page_type"],
            "content_style": topic["content_style"],
            "target_path_used_for_social": topic["target_path"],
            "page_exists": str(output_path.exists()).lower(),
            "status": "published" if output_path.exists() else "draft_topic_suggestion",
            "note": "Create this page before linking social directly to the suggested slug." if not output_path.exists() else "Page exists.",
        })
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(ai_coding_topic_suggestions_path(), index=False)


def load_social_accounts_config() -> dict[str, object]:
    ensure_social_accounts_config()
    try:
        return json.loads(accounts_config_path().read_text(encoding="utf-8"))
    except Exception:
        return {}


def ensure_publish_log() -> pd.DataFrame:
    path = publish_log_path()
    if not path.exists():
        df = pd.DataFrame(columns=PUBLISH_LOG_COLUMNS)
        df.to_csv(path, index=False, encoding="utf-8-sig")
        return df
    try:
        df = pd.read_csv(path)
    except Exception:
        df = pd.DataFrame(columns=PUBLISH_LOG_COLUMNS)
    for column in PUBLISH_LOG_COLUMNS:
        if column not in df.columns:
            df[column] = ""
    df = df[PUBLISH_LOG_COLUMNS].fillna("")
    df.to_csv(path, index=False, encoding="utf-8-sig")
    return df


def ensure_publish_mode_config() -> dict[str, str]:
    path = publish_mode_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(json.dumps(DEFAULT_PUBLISH_MODE, indent=2), encoding="utf-8")
        return dict(DEFAULT_PUBLISH_MODE)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    modes = dict(DEFAULT_PUBLISH_MODE)
    for platform, value in data.items() if isinstance(data, dict) else []:
        normalized_platform = normalize_platform_key(platform)
        normalized_mode = str(value).strip().lower()
        if normalized_platform in modes and normalized_mode in {"manual", "auto"}:
            modes[normalized_platform] = normalized_mode
    path.write_text(json.dumps(modes, indent=2), encoding="utf-8")
    return modes


def load_publish_modes() -> dict[str, str]:
    return ensure_publish_mode_config()


def ensure_social_limits_config() -> dict[str, dict[str, int]]:
    path = social_limits_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(json.dumps(DEFAULT_SOCIAL_LIMITS, indent=2), encoding="utf-8")
        return json.loads(json.dumps(DEFAULT_SOCIAL_LIMITS))
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    limits = json.loads(json.dumps(DEFAULT_SOCIAL_LIMITS))
    if isinstance(data, dict):
        for platform, config in data.items():
            key = normalize_platform_key(platform)
            if key not in limits or not isinstance(config, dict):
                continue
            limits[key] = {
                "daily_limit": max(0, safe_int(config.get("daily_limit"), limits[key]["daily_limit"])),
                "cooldown_minutes": max(0, safe_int(config.get("cooldown_minutes"), limits[key]["cooldown_minutes"])),
            }
    path.write_text(json.dumps(limits, indent=2), encoding="utf-8")
    return limits


def load_social_limits() -> dict[str, dict[str, int]]:
    return ensure_social_limits_config()


def save_publish_modes(modes: dict[str, str]) -> dict[str, str]:
    cleaned = dict(DEFAULT_PUBLISH_MODE)
    for platform, mode in modes.items():
        key = normalize_platform_key(platform)
        value = str(mode).strip().lower()
        if key in cleaned and value in {"manual", "auto"}:
            cleaned[key] = value
    publish_mode_path().parent.mkdir(parents=True, exist_ok=True)
    publish_mode_path().write_text(json.dumps(cleaned, indent=2), encoding="utf-8")
    return cleaned


def normalize_platform_key(platform: str) -> str:
    value = str(platform or "").strip().lower()
    if value in {"x/twitter", "x", "twitter/x"}:
        return "twitter"
    return value


def safe_int(value: object, default: int = 0) -> int:
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return default


def append_publish_log(post_id: str, platform: str, mode: str, scheduled_time: str, action: str, status: str, error: str = "") -> None:
    log = ensure_publish_log()
    row = {
        "post_id": post_id,
        "platform": platform,
        "mode": mode,
        "scheduled_time": scheduled_time,
        "action": action,
        "status": status,
        "error": error,
    }
    log = pd.concat([log, pd.DataFrame([row])], ignore_index=True)
    log.to_csv(publish_log_path(), index=False)


def scheduled_datetime(row: dict[str, str]) -> datetime | None:
    scheduled_date = str(row.get("scheduled_date", "")).strip()
    scheduled_time = str(row.get("scheduled_time", "")).strip()
    if not scheduled_date or not scheduled_time:
        return None
    try:
        return datetime.fromisoformat(f"{scheduled_date}T{scheduled_time}")
    except ValueError:
        return None


def retry_datetime(row: dict[str, str]) -> datetime | None:
    value = str(row.get("next_retry_time", "")).strip()
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def run_scheduler(now: datetime | None = None, dry_run: bool = False) -> dict[str, int]:
    load_dotenv()
    ensure_social_distribution_assets()
    now = now or datetime.now()
    calendar = load_social_calendar()
    publish_modes = load_publish_modes()
    limits = load_social_limits()
    result = {"loaded": len(calendar), "due": 0, "posted": 0, "ready": 0, "failed": 0, "skipped": 0}
    if calendar.empty:
        print("Loaded social calendar rows: 0")
        return result

    print(f"Loaded social calendar rows: {len(calendar)}")
    calendar = sort_calendar_for_scheduler(calendar)
    for idx, row in calendar.iterrows():
        status = str(row.get("status", ""))
        if status not in {"Approved", "Scheduled", "Failed"}:
            result["skipped"] += 1
            continue
        retry_count = safe_int(row.get("retry_count"), 0)
        if status == "Failed":
            if retry_count >= MAX_RETRY_COUNT:
                result["skipped"] += 1
                continue
            next_retry = retry_datetime(row.to_dict())
            if next_retry and next_retry > now:
                result["skipped"] += 1
                continue
        due_at = scheduled_datetime(row.to_dict())
        if status != "Failed" and due_at and due_at > now:
            result["skipped"] += 1
            continue
        result["due"] += 1
        post_id = str(row.get("id", ""))
        platform = str(row.get("platform", "")).strip()
        platform_key = normalize_platform_key(platform)
        mode = publish_modes.get(platform_key, "manual")
        scheduled_label = f"{row.get('scheduled_date', '')} {row.get('scheduled_time', '')}".strip()
        print(f"- Due: {post_id} | {platform} | mode={mode} | {scheduled_label}")
        allowed, reason = platform_can_process(calendar, platform_key, now, limits)
        if not allowed:
            result["skipped"] += 1
            print(f"  skipped: {reason}")
            continue

        if platform_key == "telegram" and mode == "auto":
            if dry_run:
                print("  dry-run: Telegram would be posted")
                append_publish_log(post_id, platform, mode, scheduled_label, "telegram_auto_post", "Dry Run", "")
                continue
            ok, message = send_telegram_post(str(row.get("post_body", "")), post_id=post_id)
            if ok:
                calendar.loc[idx, "status"] = "Posted"
                calendar.loc[idx, "posted_at"] = now.isoformat(timespec="seconds")
                calendar.loc[idx, "next_retry_time"] = ""
                append_publish_log(post_id, platform, mode, scheduled_label, "telegram_auto_post", "Posted", "")
                result["posted"] += 1
                print("  Telegram posted")
            else:
                calendar.loc[idx, "status"] = "Failed"
                calendar.loc[idx, "notes"] = message
                calendar.loc[idx, "retry_count"] = str(retry_count + 1)
                calendar.loc[idx, "next_retry_time"] = (now + timedelta(minutes=RETRY_DELAY_MINUTES)).isoformat(timespec="seconds")
                append_publish_log(post_id, platform, mode, scheduled_label, "telegram_auto_post", "Failed", message)
                result["failed"] += 1
                print(f"  Telegram failed: {message}")
            continue

        calendar.loc[idx, "status"] = "Ready to Post"
        if platform_key == "telegram":
            note = "Telegram is in manual mode. Copy-ready reminder created."
            action = "manual_ready"
        elif mode == "auto":
            note = "Auto-post for this platform is not enabled yet. Manual copy-ready mode is safer."
            action = "auto_not_enabled_manual_ready"
        else:
            note = "Manual copy-ready. This platform is not auto-posted."
            action = "manual_ready"
        calendar.loc[idx, "notes"] = note
        append_publish_log(post_id, platform, mode, scheduled_label, action, "Ready to Post", "")
        result["ready"] += 1
        print(f"  Copy-ready reminder created: {note}")

    save_social_calendar(calendar)
    print(f"Scheduler result: {result}")
    return result


def telegram_credentials() -> tuple[str, str]:
    config = load_social_accounts_config()
    telegram = config.get("telegram", {}) if isinstance(config, dict) else {}
    if not isinstance(telegram, dict):
        telegram = {}
    token_default = str(telegram.get("telegram_bot_token", "") or telegram.get("bot_token", ""))
    chat_default = str(telegram.get("telegram_chat_id", "") or telegram.get("chat_id", ""))
    token = os.getenv("TELEGRAM_BOT_TOKEN", token_default).strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", chat_default).strip()
    return token, chat_id


def telegram_config_status() -> tuple[bool, str]:
    token, chat_id = telegram_credentials()
    if not token and not chat_id:
        return False, "Telegram chưa cấu hình TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID hoặc config/social_accounts.json."
    if not token:
        return False, "Thiếu telegram_bot_token."
    if not chat_id:
        return False, "Thiếu telegram_chat_id."
    return True, "Telegram đã có token và chat/channel id."


def send_telegram_post(message: str, post_id: str = "") -> tuple[bool, str]:
    token, chat_id = telegram_credentials()
    if not token or not chat_id:
        return False, telegram_config_status()[1]
    image_path = social_asset_path(post_id) if post_id else Path()
    if image_path.exists():
        return send_telegram_photo(token, chat_id, image_path, message)
    payload = json.dumps({"chat_id": chat_id, "text": message, "parse_mode": "HTML", "disable_web_page_preview": False}).encode("utf-8")
    request = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return 200 <= response.status < 300, response.read().decode("utf-8", errors="ignore")[:500]
    except urllib.error.URLError as exc:
        return False, str(exc)


def send_telegram_photo(token: str, chat_id: str, image_path: Path, caption: str) -> tuple[bool, str]:
    boundary = f"----AffiliateBot{int(datetime.now().timestamp())}"
    caption = trim_telegram_caption(caption, extract_last_url(caption))
    mime_type = mimetypes.guess_type(str(image_path))[0] or "image/png"
    parts: list[bytes] = []
    fields = {
        "chat_id": chat_id,
        "caption": caption,
        "parse_mode": "HTML",
    }
    for name, value in fields.items():
        parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n".encode("utf-8"))
    header = (
        f"--{boundary}\r\n"
        f"Content-Disposition: form-data; name=\"photo\"; filename=\"{image_path.name}\"\r\n"
        f"Content-Type: {mime_type}\r\n\r\n"
    ).encode("utf-8")
    parts.append(header + image_path.read_bytes() + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode("utf-8"))
    request = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendPhoto",
        data=b"".join(parts),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return 200 <= response.status < 300, response.read().decode("utf-8", errors="ignore")[:500]
    except urllib.error.URLError as exc:
        return False, str(exc)


def extract_last_url(text: str) -> str:
    matches = [part.strip() for part in str(text).split() if part.startswith(("http://", "https://"))]
    return matches[-1] if matches else ""


def build_x_thread_preview(
    content: str,
    target_url: str,
    title: str = "",
    content_style: str = "practical_review",
    mode: str = "Viral thread",
    hashtags: str = "#AICoding #BuilderNotes",
) -> list[str]:
    """Build a copy-ready X/Twitter thread without calling external APIs."""
    clean_url = str(target_url or extract_last_url(content) or "").strip()
    source = remove_urls(str(content or ""))
    sentences = sentence_units(source)
    topic = str(title or "AI coding workflow").strip()
    mode = mode if mode in X_THREAD_MODES else "Viral thread"
    if mode == "Comparison review":
        mode = "Comparison style"
    hook = x_mode_hook(topic, content_style, mode, sentences)

    if mode == "Short post":
        posts = [
            hook,
            "The practical check is simple: does the tool reduce cleanup time after a real bug, or only create a fast first draft?",
            f"{cta_for_x(mode)} {clean_url} {hashtags}".strip(),
        ]
        total = len(posts)
        return [
            f"{index}/{total} " + smart_trim_sentence(post, 279 - len(f"{index}/{total} "))
            for index, post in enumerate(posts, start=1)
        ]

    body_candidates = [
        sentence
        for sentence in sentences
        if len(sentence) > 28 and not sentence.lower().startswith(("http", "#"))
    ]
    if not body_candidates:
        body_candidates = [
            "The real test is not the first generated answer. It is what happens when the repo gets messy.",
            "I care more about cleanup time, debugging quality, and context handling than demo speed.",
            "A good AI coding workflow assigns each tool a job instead of forcing one assistant to do everything.",
        ]
    target_count = 5 if mode in {"Viral thread", "Founder story style", "Educational", "Quick tips"} else 4
    posts: list[str] = [hook]
    for sentence in body_candidates:
        if len(posts) >= target_count - 1:
            break
        posts.append(sentence)
    while len(posts) < target_count - 1:
        posts.append(f"Builder note: {fallback_x_point(mode, len(posts))}")
    final = f"{cta_for_x(mode)}\n{clean_url}\n\n{hashtags}".strip()
    posts.append(final)
    total = len(posts)
    numbered = []
    for index, post in enumerate(posts, start=1):
        prefix = f"{index}/{total} "
        numbered.append(prefix + smart_trim_sentence(post, 279 - len(prefix)))
    return numbered


def remove_urls(text: str) -> str:
    parts = [part for part in str(text or "").replace("\r", "\n").split() if not part.startswith(("http://", "https://"))]
    return " ".join(parts)


def sentence_units(text: str) -> list[str]:
    normalized = " ".join(str(text or "").replace("\r", "\n").split())
    chunks: list[str] = []
    current = []
    for token in normalized.split(" "):
        stripped = token.strip()
        if not stripped:
            continue
        if stripped[:2] in {"1/", "2/", "3/", "4/", "5/", "6/", "7/", "8/", "9/"}:
            stripped = stripped[2:].strip()
        current.append(stripped)
        if stripped.endswith((".", "?", "!")) and len(" ".join(current)) > 34:
            chunks.append(" ".join(current).strip())
            current = []
    if current:
        chunks.append(" ".join(current).strip())
    cleaned = []
    for chunk in chunks:
        if chunk and chunk not in cleaned and not chunk.startswith("#"):
            cleaned.append(chunk)
    return cleaned


def x_mode_hook(topic: str, content_style: str, mode: str, sentences: list[str]) -> str:
    if mode == "Quick tips":
        return f"Quick tips for {topic}: judge the workflow after the first failed fix."
    if mode == "Educational":
        return f"Educational note: {topic} is easier to evaluate when you separate drafting, repair, and review."
    if mode == "Founder story style":
        return f"I changed how I use AI coding tools after {topic} exposed the cleanup problem."
    if mode == "Comparison style":
        return f"{topic}: the useful question is not which tool is faster. It is which one fails cheaper."
    if mode == "Authority style":
        return f"After using AI coding tools on real projects, I judge {topic} by the second failed fix."
    if mode == "Short post":
        base = sentences[0] if sentences else "AI coding tools should be judged by cleanup time, not demo speed."
        return smart_trim_sentence(base, 170)
    if content_style == "hot_take":
        return "Hot take: most AI coding demos collapse when the repo gets messy."
    if content_style == "failure_case":
        return "The second failed fix is where AI coding tools get exposed."
    if content_style == "comparison":
        return f"{topic}: speed is not the same as lower cleanup cost."
    return "Builder note: the best AI coding workflow is usually a handoff, not a single-tool bet."


def cta_for_x(mode: str) -> str:
    return {
        "Short post": "Full note:",
        "Quick tips": "Save the full checklist:",
        "Viral thread": "Read the practical breakdown:",
        "Authority style": "Full workflow note:",
        "Comparison style": "Compare the tradeoffs:",
        "Comparison review": "Compare the tradeoffs:",
        "Founder story style": "I wrote the full builder note here:",
        "Educational": "Read the full explainer:",
    }.get(mode, "Read more:")


def fallback_x_point(mode: str, index: int) -> str:
    points = {
        "Viral thread": [
            "The tool that looks fastest in a demo can still be slower after review.",
            "Repo context matters more than a clean first answer.",
            "The best workflow reduces cleanup, not just keystrokes.",
        ],
        "Authority style": [
            "I separate scaffolding, repair, iteration, and autocomplete into different jobs.",
            "That makes tool choice easier and reduces repeated failed patches.",
            "This is why I avoid ranking every tool with one generic score.",
        ],
        "Comparison style": [
            "One tool can win first drafts while another wins messy repair.",
            "Pricing only makes sense after counting cleanup time.",
            "Context handling is the difference between a patch and a fix.",
        ],
        "Founder story style": [
            "The first week was about speed. The second week was about cleanup.",
            "That changed how I choose between Cursor, Windsurf, Codex, and Copilot.",
            "Now each tool gets a narrower job.",
        ],
        "Educational": [
            "Separate generation speed from reviewed, working output.",
            "Test the tool on an existing repo, not only a blank demo.",
            "Track how many fix loops it takes before the build passes.",
        ],
        "Quick tips": [
            "Use one tool for scaffolding and another for repair.",
            "Keep the final review human-led.",
            "Measure cleanup time before you call a workflow productive.",
        ],
    }
    if mode == "Comparison review":
        mode = "Comparison style"
    selected = points.get(mode, points["Viral thread"])
    return selected[index % len(selected)]


def smart_trim_sentence(text: str, limit: int = 279) -> str:
    value = " ".join(str(text or "").split())
    if len(value) <= limit:
        return value
    sentence_parts = []
    current = ""
    for token in value.split(" "):
        candidate = f"{current} {token}".strip()
        if len(candidate) > limit - 3:
            break
        current = candidate
        if token.endswith((".", "?", "!")):
            sentence_parts.append(current)
    if sentence_parts:
        return sentence_parts[-1]
    return current.rstrip(".,;:") + "..."


def sort_calendar_for_scheduler(calendar: pd.DataFrame) -> pd.DataFrame:
    priority_rank = {"high": 0, "medium": 1, "low": 2}
    status_rank = {"Failed": 0, "Approved": 1, "Scheduled": 2}
    ranked = calendar.copy()
    ranked["_priority_rank"] = ranked["priority"].astype(str).str.lower().map(priority_rank).fillna(1)
    ranked["_status_rank"] = ranked["status"].astype(str).map(status_rank).fillna(9)
    ranked["_scheduled_sort"] = ranked.apply(lambda row: scheduled_datetime(row.to_dict()) or datetime.max, axis=1)
    ranked = ranked.sort_values(["_priority_rank", "_status_rank", "_scheduled_sort"])
    return ranked.drop(columns=["_priority_rank", "_status_rank", "_scheduled_sort"])


def platform_can_process(calendar: pd.DataFrame, platform: str, now: datetime, limits: dict[str, dict[str, int]]) -> tuple[bool, str]:
    config = limits.get(platform, DEFAULT_SOCIAL_LIMITS.get(platform, {"daily_limit": 1, "cooldown_minutes": 60}))
    daily_limit = int(config.get("daily_limit", 1))
    cooldown_minutes = int(config.get("cooldown_minutes", 0))
    if daily_limit <= 0:
        return False, f"{platform} daily limit is 0"
    posted_count = posted_today_count(calendar, platform, now)
    if posted_count >= daily_limit:
        return False, f"{platform} daily limit reached ({posted_count}/{daily_limit})"
    latest = latest_platform_action_time(calendar, platform)
    if latest and cooldown_minutes > 0:
        ready_at = latest + timedelta(minutes=cooldown_minutes)
        if ready_at > now:
            return False, f"{platform} cooldown active until {ready_at.isoformat(timespec='minutes')}"
    return True, "ok"


def posted_today_count(calendar: pd.DataFrame, platform: str, now: datetime | None = None) -> int:
    now = now or datetime.now()
    key = normalize_platform_key(platform)
    count = 0
    for _, row in calendar.iterrows():
        if normalize_platform_key(str(row.get("platform", ""))) != key:
            continue
        if str(row.get("status", "")) not in {"Posted", "Ready to Post"}:
            continue
        value = parse_datetime(str(row.get("posted_at", ""))) or scheduled_datetime(row.to_dict())
        if value and value.date() == now.date():
            count += 1
    return count


def latest_platform_action_time(calendar: pd.DataFrame, platform: str) -> datetime | None:
    key = normalize_platform_key(platform)
    values: list[datetime] = []
    for _, row in calendar.iterrows():
        if normalize_platform_key(str(row.get("platform", ""))) != key:
            continue
        if str(row.get("status", "")) not in {"Posted", "Ready to Post"}:
            continue
        value = parse_datetime(str(row.get("posted_at", ""))) or scheduled_datetime(row.to_dict())
        if value:
            values.append(value)
    return max(values) if values else None


def parse_datetime(value: str) -> datetime | None:
    value = str(value or "").strip()
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def default_priority(seed: SocialSeed) -> str:
    text = f"{seed.title} {seed.url_path}".lower()
    if "cursor" in text or "copilot" in text or "seo" in text:
        return "high"
    if "automation" in text or "writing" in text:
        return "medium"
    return "low"


def run_daemon(interval_minutes: int = 5, dry_run: bool = False, max_cycles: int | None = None) -> None:
    interval_seconds = max(1, int(interval_minutes)) * 60
    cycles = 0
    print(f"Social scheduler daemon started. interval_minutes={interval_minutes} dry_run={dry_run}")
    while True:
        cycles += 1
        print(f"\nCycle {cycles} at {datetime.now().isoformat(timespec='seconds')}")
        run_scheduler(dry_run=dry_run)
        if max_cycles is not None and cycles >= max_cycles:
            print("Max cycles reached. Exiting daemon.")
            return
        time.sleep(interval_seconds)


def full_url(path: str, platform: str = "") -> str:
    base = (settings.base_site_url or settings.site_domain or "https://review.mssmileenglish.com").rstrip("/")
    url = f"{base}/{path.strip('/')}/"
    source = utm_source(platform)
    return f"{url}?utm_source={source}" if source else url


def utm_source(platform: str) -> str:
    key = normalize_platform_key(platform)
    return {
        "telegram": "telegram",
        "facebook": "facebook",
        "linkedin": "linkedin",
        "twitter": "twitter",
    }.get(key, "")


def render_post_body(seed: SocialSeed) -> str:
    url = full_url(seed.url_path, seed.platform)
    bullets = "\n".join(f"- {item}" for item in seed.bullets)
    platform = seed.platform.lower()
    if platform == "linkedin":
        return (
            f"{seed.hook}\n\n"
            "I started noticing this while working through real AI coding, SEO, and affiliate content workflows. The first draft from a tool is rarely the part that decides whether it is useful. The real test starts when the project gets messy: duplicated logic, weak context, confusing pricing, or a workflow that looks good in a demo but slows down during cleanup.\n\n"
            "My experience note: I trust tools more when they reduce review time, not when they only generate output quickly. Fast output is helpful, but if the second hour becomes debugging generated mistakes, the tool is not really saving much time.\n\n"
            "The problem I keep seeing is that people compare software by feature lists. That misses the practical question: what happens after the first fix fails?\n\n"
            f"{bullets}\n\n"
            "A few practical checks I now use before recommending any tool:\n"
            "- Does it handle existing project context, or only clean demos?\n"
            "- Does it make debugging easier after the first attempt fails?\n"
            "- Is the pricing reasonable for a solo builder or small team?\n"
            "- Does the workflow still feel stable when the project grows?\n\n"
            "I wrote the fuller practical breakdown here. It is not a hype piece; it is a workflow-first note for builders who care about speed, cleanup cost, and realistic adoption.\n\n"
            f"{url}\n\n"
            f"{seed.hashtags}"
        )
    if platform == "facebook":
        return (
            f"{seed.hook}\n\n"
            "Minh cang dung AI tools de build site, sua loi, lam SEO content va chuan bi affiliate workflow thi cang thay mot dieu: demo dep chua du.\n\n"
            "Cau hoi that su la khi project bat dau roi, tool do co giup minh xu ly nhanh hon khong, hay chi tao them viec phai don?\n\n"
            f"{bullets}\n\n"
            "Kinh nghiem cua minh la dung chi nhin tool nao tao nhanh hon trong 5 phut dau. Hay nhin vao phan sau do:\n"
            "- sua bug co nhanh khong\n"
            "- co hieu context project khong\n"
            "- co tao logic lap lai khong\n"
            "- pricing co hop voi cach minh dung hang ngay khong\n\n"
            "Minh viet lai goc nhin thuc te o bai nay. Neu ban dang chon tool de build project, lam SEO hoac chuan bi he thong affiliate, bai nay se giup loc bot phan quang cao va nhin vao workflow that.\n\n"
            f"{url}\n\n"
            f"{seed.hashtags}"
        )
    if platform == "telegram":
        body = (
            f"{seed.hook}\n\n"
            "Quick field note from building and reviewing AI/SaaS tools:\n\n"
            f"{bullets}\n\n"
            "The useful question is not which tool looks impressive in a demo. It is which one still helps when the repo, page structure, pricing decision, or workflow gets messy.\n\n"
            "My current filter: use the tool that reduces cleanup time. If it only creates faster first drafts but leaves more review work, I treat it carefully.\n\n"
            "Before posting or recommending a tool, I check the same things every time: does it help with the second fix, does it reduce context switching, and does the pricing still make sense after the trial period ends?\n\n"
            f"Read more:\n{url}\n\n"
            f"{seed.hashtags}"
        )
        return trim_telegram_caption(body, url)
    if platform == "x/twitter":
        return render_x_thread(seed, url)
    return f"{seed.hook}\n\n{bullets}\n\n{url}\n\n{seed.hashtags}"


def render_x_thread(seed: SocialSeed, url: str) -> str:
    style_hooks = {
        "hot_take": "Hot take: most AI demos collapse under repo complexity.",
        "builder_note": "Builder note: the second failed fix is where AI tools get exposed.",
        "comparison": "Unpopular comparison: speed is not the same as lower cleanup cost.",
        "practical_review": "Practical review: judge the tool after the first mistake, not the first answer.",
        "workflow_tip": "Workflow tip: use the tool where it reduces review time, not where it looks flashy.",
    }
    opener = style_hooks.get(seed.content_style, style_hooks["practical_review"])
    posts = [
        f"1/ {opener}",
        f"2/ {seed.hook}",
        f"3/ {seed.bullets[0]} But I would still test it on a messy real task, not a clean demo.",
        f"4/ {seed.bullets[1]} This is where context, pricing, and team workflow start to matter.",
        f"5/ Full practical note: {url} {seed.hashtags}",
    ]
    return "\n\n".join(trim_x_post(post) for post in posts)


def trim_x_post(post: str, limit: int = 259) -> str:
    if len(post) <= limit:
        return post
    return post[: limit - 3].rsplit(" ", 1)[0].rstrip(".,;:") + "..."

def trim_telegram_caption(text: str, url: str, limit: int = 980) -> str:
    if len(text) <= limit:
        return text
    suffix = f"\n\nRead more:\n{url}"
    soft_limit = max(120, limit - len(suffix))
    trimmed = text[:soft_limit].rsplit("\n", 1)[0].strip()
    return f"{trimmed}{suffix}"


def write_queue_markdown(post_id: str, seed: SocialSeed, body: str, target_url: str, scheduled_date: str) -> None:
    path = social_queue_dir() / f"{post_id}.md"
    content = (
        f"# {seed.title}\n\n"
        f"- Platform: {seed.platform}\n"
        f"- Status: Pending Review\n"
        f"- Suggested time: {scheduled_date} {seed.schedule_time}\n"
        f"- Target URL: {target_url}\n\n"
        "## Copy\n\n"
        f"{body}\n"
    )
    path.write_text(content, encoding="utf-8")


def social_asset_path(post_id: str) -> Path:
    return social_assets_dir() / f"{post_id}.png"


def ensure_social_asset(post_id: str, seed: SocialSeed) -> Path:
    output = social_asset_path(post_id)
    render_social_asset(output, seed, theme="dark")
    render_social_asset(social_assets_dir() / f"{post_id}-light.png", seed, theme="light")
    return output


def render_social_asset(output: Path, seed: SocialSeed, theme: str = "dark") -> None:
    width, height = 1200, 630
    if theme == "light":
        bg, card, outline, title_color, sub_color, foot_color = (242, 246, 252), (255, 255, 255), (70, 120, 235), (16, 24, 36), (45, 75, 125), (75, 85, 100)
    else:
        bg, card, outline, title_color, sub_color, foot_color = (12, 18, 28), (24, 36, 54), (85, 135, 255), (246, 248, 252), (170, 205, 255), (210, 220, 235)
    image = Image.new("RGB", (width, height), bg)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((52, 52, width - 52, height - 52), radius=38, fill=card, outline=outline, width=3)
    font_title = load_font(60)
    font_mid = load_font(30)
    font_small = load_font(24)
    badge = seed.platform
    draw.rounded_rectangle((92, 88, 92 + len(badge) * 18 + 58, 144), radius=24, fill=outline)
    draw.text((121, 103), badge, font=font_small, fill=(255, 255, 255))
    y = 182
    for line in wrap(seed.title, 27)[:4]:
        draw.text((92, y), line, font=font_title, fill=title_color)
        y += 68
    subtitle = "Practical workflow notes, comparisons, pricing reality, and limitations"
    for line in wrap(subtitle, 56)[:2]:
        draw.text((94, min(y + 12, 455)), line, font=font_mid, fill=sub_color)
        y += 38
    draw.text((94, 526), "review.mssmileenglish.com", font=font_small, fill=foot_color)
    draw.text((820, 526), "MS Smile AI Review Hub", font=font_small, fill=foot_color)
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output)


def load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for candidate in ["C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/arial.ttf"]:
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            continue
    return ImageFont.load_default()


def wrap(text: str, max_chars: int) -> list[str]:
    words = str(text).split()
    lines: list[str] = []
    current: list[str] = []
    for word in words:
        candidate = " ".join(current + [word])
        if len(candidate) > max_chars and current:
            lines.append(" ".join(current))
            current = [word]
        else:
            current.append(word)
    if current:
        lines.append(" ".join(current))
    return lines


def seed_posts() -> list[SocialSeed]:
    linkedin = [
        seed("LinkedIn", "Cursor vs Copilot: debugging speed", "comparisons/cursor-vs-copilot", "I stopped comparing Cursor and Copilot as autocomplete tools.", ("Cursor is stronger when I need repo-level editing context.", "Copilot is still useful for lightweight suggestions inside an existing workflow.", "The deciding factor is how each tool behaves after the first fix fails."), "Read the comparison", "#AICoding #Cursor #GitHubCopilot", "09:00"),
        seed("LinkedIn", "Windsurf vs Copilot workflow note", "comparisons/windsurf-vs-copilot", "Windsurf and Copilot solve different parts of the coding workflow.", ("Windsurf feels faster for scaffolding rough structure.", "Copilot is easier to adopt in conservative engineering teams.", "Neither should own a large refactor without review."), "Read the workflow comparison", "#AIDevTools #Windsurf #Copilot", "10:00"),
        seed("LinkedIn", "Best AI SEO tools for practical teams", "best-ai-seo-tools-2026", "AI SEO tools are useful only if the team still checks the SERP manually.", ("Good tools speed up briefs and content audits.", "Bad workflows publish unchecked AI recommendations.", "The best setup combines software with editorial judgment."), "See the shortlist", "#SEO #AITools #ContentStrategy", "09:30"),
        seed("LinkedIn", "AI writing tools need editors", "best-ai-writing-tools-2026", "The biggest risk with AI writing tools is not quality. It is sameness.", ("Use AI for outlines, repurposing, and consistency.", "Keep human review for claims, examples, and positioning.", "Avoid publishing generic drafts just because they are fast."), "Read the guide", "#AIWriting #ContentMarketing #SaaS", "10:30"),
        seed("LinkedIn", "AI automation tools and failure states", "best-ai-automation-tools-2026", "Automation only saves time when failure states are visible.", ("Make and Zapier are powerful, but silent errors are expensive.", "Teams should document handoffs and fallback checks.", "Start with one workflow before automating everything."), "Compare automation tools", "#Automation #NoCode #Operations", "09:00"),
        seed("LinkedIn", "AI video tools for realistic workflows", "best-ai-video-tools-2026", "AI video tools are not one category anymore.", ("Avatar explainers, editing, creative generation, and social clips need different tools.", "Pricing and export limits matter more than demo quality.", "Teams should test one real campaign before committing."), "See AI video tools", "#AIVideo #MarketingTools #CreatorTools", "11:00"),
        seed("LinkedIn", "Canva vs Adobe Express", "comparisons/canva-vs-adobe-express", "Canva vs Adobe Express is really a workflow decision.", ("Canva is often quicker for marketing teams.", "Adobe Express makes more sense inside an Adobe-heavy stack.", "The best choice depends on templates, collaboration, and brand control."), "Read the comparison", "#DesignTools #Canva #AdobeExpress", "14:00"),
        seed("LinkedIn", "Cursor review for builders", "review/cursor", "Cursor becomes much more valuable after the repo has structure.", ("It helps me move faster during small refactors.", "It still needs careful review on architecture changes.", "The best use case is iteration, debugging, and cleanup."), "Read the Cursor review", "#CursorAI #AICoding #DeveloperTools", "15:00"),
        seed("LinkedIn", "Semrush review angle", "review/semrush", "SEO tools do not replace strategy. They expose questions faster.", ("Semrush is strongest when used for research and validation.", "Do not treat volume estimates as exact truth.", "Use it to prioritize, then verify manually."), "Read the Semrush review", "#Semrush #SEOResearch #AffiliateSEO", "09:00"),
        seed("LinkedIn", "Make review note", "review/make", "Make is powerful when the workflow is mapped before automation starts.", ("Visual automation helps teams see logic clearly.", "Complex scenarios can become hard to maintain.", "Start small and document every error path."), "Read the Make review", "#Make #Automation #NoCode", "10:00"),
    ]
    facebook = [
        seed("Facebook", "Cursor hay Copilot?", "comparisons/cursor-vs-copilot", "Mình thấy Cursor và Copilot không nên so theo kiểu công cụ nào thông minh hơn.", ("Cursor hợp hơn khi cần sửa trong repo có context.", "Copilot hợp khi muốn autocomplete nhẹ nhàng.", "Nếu project đang rối, phải test bằng lỗi thật chứ không xem demo."), "Đọc bài so sánh", "#Cursor #Copilot #AICoding", "20:00"),
        seed("Facebook", "Windsurf vs Copilot thực tế", "comparisons/windsurf-vs-copilot", "Nếu bắt đầu project từ con số 0, Windsurf tạo khung rất nhanh.", ("Nhưng refactor lớn vẫn cần kiểm kỹ.", "Copilot dễ dùng hơn cho team đang quen IDE cũ.", "Mình sẽ không để tool nào tự sửa production mà không review."), "Xem bài so sánh", "#Windsurf #Copilot #AITools", "20:30"),
        seed("Facebook", "AI SEO tools 2026", "best-ai-seo-tools-2026", "Dùng AI SEO tool mà không kiểm SERP thủ công rất dễ đi sai hướng.", ("Tool tốt giúp tiết kiệm thời gian research.", "Nhưng insight vẫn phải kiểm chứng.", "Bài này gom các lựa chọn đáng xem trước khi mua."), "Xem danh sách", "#SEO #AITools #Affiliate", "19:30"),
        seed("Facebook", "AI writing tools", "best-ai-writing-tools-2026", "AI viết nhanh, nhưng nhanh quá cũng dễ thành nội dung na ná nhau.", ("Nên dùng AI để lên outline và repurpose.", "Nội dung bán hàng vẫn cần góc nhìn thật.", "Đừng publish bản nháp nếu chưa biên tập."), "Đọc bài hướng dẫn", "#AIWriting #ContentCreator #SaaS", "20:00"),
        seed("Facebook", "AI automation tools", "best-ai-automation-tools-2026", "Automation không phải cứ nối app là xong.", ("Quan trọng nhất là biết lỗi xảy ra ở đâu.", "Make/Zapier đều mạnh, nhưng cần workflow rõ.", "Bắt đầu bằng một quy trình nhỏ trước."), "Xem bài tổng hợp", "#Automation #Make #Zapier", "19:00"),
        seed("Facebook", "AI video tools", "best-ai-video-tools-2026", "AI video tool mỗi loại mạnh một kiểu.", ("Có tool làm avatar tốt.", "Có tool edit nhanh hơn.", "Có tool hợp social clip hơn là video dài."), "Xem danh sách AI video", "#AIVideo #Marketing #Creator", "20:30"),
        seed("Facebook", "Canva vs Adobe Express", "comparisons/canva-vs-adobe-express", "Canva và Adobe Express khác nhau ở workflow nhiều hơn là tính năng.", ("Canva nhanh và dễ cho team marketing.", "Adobe Express hợp nếu bạn đã dùng hệ Adobe.", "Nên test bằng asset thật của team."), "Đọc bài so sánh", "#Canva #AdobeExpress #Design", "19:30"),
        seed("Facebook", "Cursor review", "review/cursor", "Cursor mạnh nhất khi project đã có cấu trúc tương đối sạch.", ("Sửa nhanh, iterate nhanh.", "Nhưng refactor lớn vẫn phải chia nhỏ.", "Đừng kỳ vọng một prompt sửa hết mọi thứ."), "Đọc review Cursor", "#CursorAI #Developer #AICoding", "20:00"),
        seed("Facebook", "Zapier review", "review/zapier", "Zapier dễ bắt đầu hơn nhiều automation tool khác.", ("Phù hợp quy trình đơn giản.", "Chi phí có thể tăng khi workflow nhiều bước.", "Nên kiểm limit trước khi scale."), "Đọc review Zapier", "#Zapier #Automation #NoCode", "19:00"),
        seed("Facebook", "ElevenLabs review", "review/elevenlabs", "AI voice nghe demo thì rất hay, nhưng dùng thật cần kiểm nhiều thứ hơn.", ("Voice quality chỉ là một phần.", "Licensing và use case phải rõ.", "Test bằng script thật trước khi mua."), "Đọc review ElevenLabs", "#ElevenLabs #AIVoice #CreatorTools", "20:30"),
    ]
    telegram = [
        seed("Telegram", "Cursor vs Copilot", "comparisons/cursor-vs-copilot", "Takeaway nhanh: Cursor hợp debugging có context, Copilot hợp autocomplete nhẹ.", ("Nếu project lớn, đừng chỉ xem demo.", "Test bằng bug thật.", "CTA đi về bài review, không affiliate trực tiếp."), "Đọc bài", "#AICoding #Cursor #Copilot", "09:00"),
        seed("Telegram", "AI SEO tools", "best-ai-seo-tools-2026", "AI SEO tool tốt giúp research nhanh hơn, không thay thế judgment.", ("Check SERP thật.", "So sánh workflow.", "Đừng mua chỉ vì demo đẹp."), "Xem shortlist", "#SEO #AITools", "20:00"),
        seed("Telegram", "Automation tools", "best-ai-automation-tools-2026", "Automation mạnh nhất khi lỗi được nhìn thấy rõ.", ("Map workflow trước.", "Test nhỏ.", "Theo dõi lỗi sau khi chạy."), "Đọc bài", "#Automation #NoCode", "09:00"),
        seed("Telegram", "Windsurf vs Copilot", "comparisons/windsurf-vs-copilot", "Windsurf nhanh cho scaffold, Copilot dễ dùng trong IDE quen thuộc.", ("Không tool nào hoàn hảo.", "Refactor lớn cần review.", "Chọn theo workflow."), "Xem so sánh", "#Windsurf #Copilot", "20:00"),
        seed("Telegram", "Cursor review", "review/cursor", "Cursor tốt nhất khi bạn dùng nó như editor có context, không phải autocomplete.", ("Chia nhỏ task.", "Review diff.", "Dùng cho debug/iteration."), "Đọc review", "#CursorAI #DevTools", "09:00"),
    ]
    twitter = [
        seed("X/Twitter", "Cursor vs Copilot", "comparisons/cursor-vs-copilot", "Cursor vs Copilot is not a demo contest.", ("Cursor: better repo-level iteration.", "Copilot: better lightweight IDE assistance.", "The real test is the second failed fix."), "Full comparison", "#AICoding #Cursor #Copilot", "09:15"),
        seed("X/Twitter", "Windsurf vs Copilot", "comparisons/windsurf-vs-copilot", "Windsurf feels fast from zero. Copilot feels safer inside old workflows.", ("Speed is not always lower cost.", "Large refactors still need review.", "Choose by workflow, not hype."), "Read more", "#Windsurf #Copilot", "14:00"),
        seed("X/Twitter", "Best AI SEO tools", "best-ai-seo-tools-2026", "AI SEO tools are only useful when humans still verify the SERP.", ("Use tools for briefs.", "Use judgment for publishing.", "Avoid generic AI content."), "See picks", "#SEO #AITools", "20:15"),
        seed("X/Twitter", "AI automation", "best-ai-automation-tools-2026", "Automation without error handling creates hidden work.", ("Start small.", "Log failures.", "Scale only after the workflow survives real usage."), "Read guide", "#Automation #NoCode", "09:15"),
        seed("X/Twitter", "AI writing tools", "best-ai-writing-tools-2026", "AI writing tools do not fix weak positioning.", ("They help outline.", "They help repurpose.", "They still need an editor."), "Read guide", "#AIWriting #ContentMarketing", "14:00"),
    ]
    return linkedin + facebook + telegram + twitter + ai_coding_workflow_social_seeds()


def ai_coding_workflow_social_seeds() -> list[SocialSeed]:
    rows: list[SocialSeed] = []
    for index, topic in enumerate(ai_coding_campaign_topics(), start=1):
        title = topic["title"]
        target = topic["target_path"]
        hook = topic["hook"]
        angle = topic["angle"]
        style = topic["content_style"]
        bullets = (
            "Windsurf is fastest when I need a rough project shape quickly.",
            "Codex is where I move broken logic, build failures, and architecture cleanup.",
            "Cursor is best for fast repo iteration; Copilot stays useful for lightweight autocomplete.",
        )
        if style == "failure_case":
            bullets = (
                "The first generated fix looked plausible, but the build still failed.",
                "The second attempt exposed whether the tool understood the repo or just patched symptoms.",
                "The useful tool is the one that reduces cleanup, not the one that sounds most confident.",
            )
        elif style == "comparison":
            bullets = (
                "Autocomplete speed matters less than how the tool handles context after a failed fix.",
                "One tool can be better for writing while another is better for repair.",
                "The winner changes depending on bootstrap, debugging, refactor, or deploy work.",
            )
        elif style == "workflow_tip":
            bullets = (
                "Use Windsurf to draft the structure, then stop before it owns the whole repo.",
                "Move messy logic and build failures into Codex with a clear task boundary.",
                "Use Cursor for tight iteration once the project shape is stable.",
            )
        elif style == "hot_take":
            bullets = (
                "The best-tool question is usually too broad to be useful.",
                "Each stage of a real project breaks AI tools in a different way.",
                "A mixed workflow often beats forcing one assistant to do everything.",
            )
        elif style == "builder_note":
            bullets = (
                "Windsurf gives me speed at the start.",
                "Codex gives me deeper repair when the project is already messy.",
                "Cursor keeps day-to-day editing fast once the architecture is stable.",
            )
        schedule_offset = index % 5
        rows.extend([
            seed("X/Twitter", title, target, hook, bullets, "Read the workflow note", "#AICoding #Codex #Cursor #Windsurf", ["10:15", "13:30", "16:45", "19:15", "21:00"][schedule_offset], style),
            seed("LinkedIn", title, target, hook, bullets, "Read the practical note", "#AICoding #DeveloperTools #BuildInPublic", ["09:30", "11:00", "14:30", "16:00", "18:30"][schedule_offset], style),
            seed("Facebook", title, target, hook, bullets, "Doc bai phan tich", "#AICoding #Cursor #Codex", ["19:00", "19:30", "20:00", "20:30", "21:00"][schedule_offset], style),
            seed("Telegram", title, target, hook, bullets, "Read note", "#AICoding #BuilderNotes", ["09:00", "12:00", "15:00", "18:00", "20:00"][schedule_offset], style),
        ])
    return rows


def seed(platform: str, title: str, url_path: str, hook: str, bullets: tuple[str, str, str], cta: str, hashtags: str, schedule_time: str, content_style: str = "") -> SocialSeed:
    return SocialSeed(platform, title, url_path, hook, bullets, cta, hashtags, schedule_time, content_style or infer_content_style(title, url_path, hook))


def infer_content_style(title: str, url_path: str, hook: str) -> str:
    text = f"{title} {url_path} {hook}".lower()
    if " vs " in text or "comparisons/" in text:
        return "comparison"
    if "workflow" in text or "automation" in text:
        return "workflow_tip"
    if "review" in text:
        return "practical_review"
    if "stopped" in text or "not a demo" in text or "risk" in text:
        return "hot_take"
    return "builder_note"


def main() -> None:
    parser = argparse.ArgumentParser(description="Local-safe social distribution scheduler")
    parser.add_argument("--run-scheduler", action="store_true", help="Process due Approved posts.")
    parser.add_argument("--daemon", action="store_true", help="Run scheduler continuously.")
    parser.add_argument("--dry-run", action="store_true", help="Show due posts without posting Telegram.")
    parser.add_argument("--interval-minutes", type=int, default=5, help="Daemon check interval in minutes.")
    parser.add_argument("--max-cycles", type=int, default=0, help="Optional daemon cycle limit for local tests.")
    args = parser.parse_args()
    if args.daemon:
        run_daemon(interval_minutes=args.interval_minutes, dry_run=args.dry_run, max_cycles=args.max_cycles or None)
    elif args.run_scheduler:
        run_scheduler(dry_run=args.dry_run)
    else:
        ensure_social_distribution_assets()
        print("Social distribution assets are ready.")
        print("Use: python -m modules.social_distribution --run-scheduler")


if __name__ == "__main__":
    main()
