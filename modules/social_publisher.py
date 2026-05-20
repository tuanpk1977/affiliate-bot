from __future__ import annotations

import csv
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

from config import settings
from modules.social_policy_checker import normalize_platform, policy_summary, validate_post


PLATFORMS = [
    "telegram",
    "linkedin",
    "reddit",
    "quora",
    "twitter",
    "facebook_page",
    "facebook_profile",
    "facebook_group",
]

ACCOUNT_COLUMNS = [
    "platform",
    "status",
    "posting_mode",
    "daily_limit",
    "scheduled_times",
    "last_publish_status",
    "error_message",
]

EXTENDED_QUEUE_COLUMNS = [
    "queue_id",
    "post_id",
    "draft_id",
    "platform",
    "channel_type",
    "community_id",
    "community_name",
    "title",
    "content",
    "article_url",
    "target_url",
    "tracked_url",
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_content",
    "status",
    "scheduled_time",
    "approved_at",
    "published_at",
    "last_attempt",
    "attempts",
    "error",
    "policy_status",
    "policy_warnings",
    "manual_export_path",
    "published_url",
    "notes",
]

LOG_COLUMNS = [
    "timestamp",
    "post_id",
    "queue_id",
    "platform",
    "action",
    "status",
    "message",
    "published_url",
]

DEFAULT_ACCOUNTS = {
    "telegram": {
        "enabled": True,
        "posting_mode": "approved_auto",
        "env_token": "TELEGRAM_BOT_TOKEN",
        "env_chat_id": "TELEGRAM_CHAT_ID",
        "daily_limit": 6,
        "scheduled_times": ["09:00", "20:00"],
    },
    "linkedin": {
        "enabled": True,
        "posting_mode": "export_only",
        "env_access_token": "LINKEDIN_ACCESS_TOKEN",
        "daily_limit": 2,
        "scheduled_times": ["10:00"],
    },
    "reddit": {
        "enabled": True,
        "posting_mode": "export_only",
        "env_client_id": "REDDIT_CLIENT_ID",
        "env_client_secret": "REDDIT_CLIENT_SECRET",
        "env_username": "REDDIT_USERNAME",
        "env_user_agent": "REDDIT_USER_AGENT",
        "daily_limit": 2,
        "scheduled_times": ["11:00"],
    },
    "quora": {
        "enabled": True,
        "posting_mode": "manual",
        "daily_limit": 2,
        "scheduled_times": ["12:00"],
        "note": "Quora stays manual/export-only. No unofficial scraping or auto-posting.",
    },
    "twitter": {
        "enabled": True,
        "posting_mode": "export_only",
        "env_api_key": "TWITTER_API_KEY",
        "env_api_secret": "TWITTER_API_SECRET",
        "env_access_token": "TWITTER_ACCESS_TOKEN",
        "env_access_secret": "TWITTER_ACCESS_SECRET",
        "daily_limit": 5,
        "scheduled_times": ["09:15", "14:00", "20:15"],
    },
    "facebook_page": {"enabled": True, "posting_mode": "manual", "daily_limit": 2, "scheduled_times": ["09:30", "20:30"]},
    "facebook_profile": {"enabled": True, "posting_mode": "manual", "daily_limit": 1, "scheduled_times": ["20:00"]},
    "facebook_group": {
        "enabled": True,
        "posting_mode": "manual",
        "daily_limit": 2,
        "scheduled_times": ["19:30"],
        "note": "External groups require explicit approval per group/post.",
    },
}


def platform_source(platform: str) -> str:
    platform = str(platform or "").strip().lower()
    if platform.startswith("facebook"):
        return "facebook"
    if platform in {"x", "twitter", "x_twitter"}:
        return "twitter"
    if platform in {"telegram", "linkedin", "quora", "reddit"}:
        return platform
    return platform or "social"


def slugish(value: object, fallback: str = "social_post") -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_") or fallback


def ensure_platform_utm(url: str, platform: str, campaign: object = "", content: object = "") -> str:
    raw = str(url or "").strip()
    if not raw:
        return ""
    parsed = urllib.parse.urlsplit(raw)
    query = dict(urllib.parse.parse_qsl(parsed.query, keep_blank_values=True))
    query.setdefault("utm_source", platform_source(platform))
    query.setdefault("utm_medium", "social")
    query.setdefault("utm_campaign", slugish(campaign, "social_campaign"))
    query.setdefault("utm_content", slugish(content, "post"))
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urllib.parse.urlencode(query), parsed.fragment))


def platform_hashtags(platform: str, text: str) -> str:
    platform_name = platform_source(platform)
    text_lower = f"{platform_name} {text}".lower()
    if "windsurf" in text_lower or "cursor" in text_lower or "codex" in text_lower or "coding" in text_lower:
        base = {
            "facebook": ["#AICoding", "#BuildInPublic", "#AIWorkflow"],
            "telegram": ["#AICoding", "#AIWorkflow"],
            "linkedin": ["#AICoding", "#BuildInPublic", "#AIWorkflow"],
            "twitter": ["#AICoding", "#BuildInPublic"],
            "reddit": [],
        }
    elif "seo" in text_lower:
        base = {
            "facebook": ["#AITools", "#SEO"],
            "telegram": ["#SEO", "#AITools"],
            "linkedin": ["#SEO", "#AITools", "#ContentStrategy"],
            "twitter": ["#SEO", "#AITools"],
            "reddit": [],
        }
    else:
        base = {
            "facebook": ["#AITools", "#AIWorkflow"],
            "telegram": ["#AITools"],
            "linkedin": ["#AITools", "#Workflow", "#BuildInPublic"],
            "twitter": ["#AITools"],
            "reddit": [],
        }
    return " ".join(base.get(platform_name, []))


def shorten_twitter_post(text: str, link: str, hashtags: str) -> str:
    candidates = [
        f"Most AI tool demos skip the hard part: what happens after the first failed fix?\n\n{link}\n{hashtags}",
        f"Hot take: speed matters less than cleanup after the first failure.\n\n{link}\n{hashtags}",
        f"The real AI workflow test is not the first draft. It is the repair loop.\n\n{link}\n{hashtags}",
    ]
    for candidate in candidates:
        if len(candidate) <= 280:
            return candidate
    tag = hashtags.split()[0] if hashtags else ""
    if link and len(link) + len(tag) + 6 >= 280:
        compact = "Hot take: the real AI workflow test is not the first draft. It is whether you can repair the second failure."
        with_tag = f"{compact}\n{tag}".strip()
        return with_tag[:280]
    if link:
        available = max(20, 280 - len(link) - len(tag) - 4)
        return f"{text[:available].rstrip()}...\n{link}\n{tag}".strip()
    return text[:277].rstrip() + "..."


def _context_label(title: str, topic: str, keyword: str = "") -> str:
    for value in (topic, keyword, title):
        cleaned = str(value or "").replace("_", " ").strip()
        if cleaned:
            return cleaned
    return "AI workflow"


def build_facebook_style(title: str, topic_text: str, link: str, hashtags: str, base_content: str = "") -> dict[str, str]:
    hook = f"I tested {topic_text} from the messy-project angle, not the demo angle."
    cta = "I wrote the practical breakdown here:"
    content = (
        f"{hook}\n\n"
        "The part that matters most is not whether the tool can create a clean first answer. "
        "Most tools can do that when the task is small.\n\n"
        "The useful question is what happens when the project has mixed context, a broken route, a rough prompt, "
        "or a feature that needs cleanup before anyone can publish it.\n\n"
        "My takeaway: choose the tool that helps you recover faster after the first mistake, not the one with the flashiest demo.\n\n"
        f"{cta} {link}\n\n"
        f"What have you seen in your own workflow?\n\n{hashtags}"
    )
    return {
        "content": content.strip(),
        "cta": cta,
        "hook": hook,
        "hook_style": "community discussion",
        "cta_style": "soft discussion link",
        "tone_profile": "Conversational, value-first, comment-friendly",
        "why": "Facebook works better when the post feels like a practical observation and invites replies instead of sounding like a polished announcement.",
    }


def build_linkedin_style(title: str, topic_text: str, link: str, hashtags: str, base_content: str = "") -> dict[str, str]:
    hook = "AI coding tools should be evaluated by repair cost, not demo speed."
    cta = "I documented the full workflow note here:"
    content = (
        f"{hook}\n\n"
        f"That is the lesson I keep seeing when comparing {topic_text}. A fast prototype is useful, but the operator cost appears later: "
        "debugging context drift, cleaning duplicated logic, fixing broken pages, and deciding whether the result is stable enough to ship.\n\n"
        "The workflow signal I look for:\n"
        "- Can the tool understand the repo after the first failure?\n"
        "- Can it repair a focused task without rewriting unrelated parts?\n"
        "- Does it make validation easier or create more review work?\n"
        "- Can a small builder use it without turning every fix into a new project?\n\n"
        "For me, the practical comparison is less about which tool feels smarter in a demo and more about which tool reduces cleanup time in a real project.\n\n"
        f"{cta} {link}\n\n{hashtags}"
    )
    return {
        "content": content.strip(),
        "cta": cta,
        "hook": hook,
        "hook_style": "operator thesis",
        "cta_style": "professional resource link",
        "tone_profile": "Professional, structured, workflow-focused",
        "why": "LinkedIn readers expect a business or operator lesson, so this version frames the topic around maintenance cost, validation, and team workflow.",
    }


def build_telegram_style(title: str, topic_text: str, link: str, hashtags: str, base_content: str = "") -> dict[str, str]:
    hook = f"{title}: practical note"
    cta = "Read:"
    tags = " ".join(hashtags.split()[:2])
    content = (
        f"{hook}\n\n"
        "Prototype speed is useful.\n"
        "Cleanup quality decides whether the project ships.\n"
        "Test the second fix, not only the first answer.\n"
        "Use the tool that keeps context stable.\n\n"
        f"{cta} {link}\n\n"
        f"{tags}"
    )
    return {
        "content": content.strip(),
        "cta": cta,
        "hook": hook,
        "hook_style": "compact practical note",
        "cta_style": "single clean link",
        "tone_profile": "Short, direct, channel-friendly",
        "why": "Telegram posts should be quick to scan, with one link and no export/debug metadata.",
    }


def build_twitter_style(title: str, topic_text: str, link: str, hashtags: str, base_content: str = "") -> dict[str, str]:
    hook = "Hot take: demo speed is a weak AI coding benchmark."
    cta = "Breakdown:"
    tag = hashtags.split()[0] if hashtags else ""
    candidates = [
        f"{hook}\n\nThe real test is what happens after the first failed fix.\n\n{cta} {link}\n{tag}".strip(),
        f"Most AI coding demos avoid the messy part: cleanup after failure.\n\nThat is where {topic_text} gets interesting.\n\n{link}\n{tag}".strip(),
        f"Prototype fast. Judge slowly.\n\nThe second failed fix reveals more than the first clean demo.\n\n{link}\n{tag}".strip(),
        "Hot take: the best AI coding tool is the one that helps you recover after the second failed fix.",
    ]
    content = next((candidate for candidate in candidates if len(candidate) <= 280), candidates[-1][:280])
    return {
        "content": content.strip(),
        "cta": cta,
        "hook": hook,
        "hook_style": "hot take",
        "cta_style": "short link or no-link fallback",
        "tone_profile": "Punchy, opinionated, reply-friendly",
        "why": "X/Twitter needs a sharp angle under 280 characters, so this version compresses the idea into a debate-friendly claim.",
    }


def build_quora_style(title: str, topic_text: str, link: str, hashtags: str, base_content: str = "") -> dict[str, str]:
    hook = f"Short answer: compare {topic_text} by workflow stage, not by hype."
    cta = "I documented a practical example here:"
    content = (
        f"{hook}\n\n"
        "The first question I would ask is: what kind of work are you trying to finish?\n\n"
        "If the job is a quick prototype, the best tool may be the one that turns a rough idea into files quickly. "
        "If the job is production cleanup, the better tool is usually the one that can follow a narrow repair prompt, keep context, and avoid breaking unrelated parts.\n\n"
        "In real projects, the hard part is often not creating the first screen. It is fixing routes, language issues, metadata, duplicated logic, and build errors after the first pass.\n\n"
        f"{cta} {link}"
    )
    return {
        "content": content.strip(),
        "cta": cta,
        "hook": hook,
        "hook_style": "direct answer",
        "cta_style": "soft reference link",
        "tone_profile": "Educational, nuanced, non-promotional",
        "why": "Quora works best as a helpful answer first, with the link positioned as an optional deeper reference.",
    }


def build_reddit_style(title: str, topic_text: str, link: str, hashtags: str, base_content: str = "") -> dict[str, str]:
    hook = f"I tested {topic_text} from a cleanup-workflow angle, not a benchmark-demo angle."
    cta = "I wrote a deeper breakdown here if useful:"
    content = (
        f"{hook}\n\n"
        "My honest take: I would not choose based on the fastest first answer. The more interesting signal is what happens when the generated project is already a bit messy.\n\n"
        "What I noticed:\n"
        "- OpenClaw-style workflows are useful for rough experimentation and seeing a first shape quickly.\n"
        "- Codex feels more useful when the task is narrow: fix this route, clean this schema, refactor this function, keep the rest unchanged.\n"
        "- The second failed fix tells you more than the first successful demo.\n\n"
        "So I would use one for exploration and the other for repair, then judge the total cleanup time.\n\n"
        f"{cta} {link}"
    )
    return {
        "content": content.strip(),
        "cta": cta,
        "hook": hook,
        "hook_style": "skeptical builder observation",
        "cta_style": "optional reference at the end",
        "tone_profile": "Honest, practical, discussion-oriented Reddit tone",
        "why": "Reddit posts should feel like a real experience note, with nuance and minimal promotion. The link is optional and placed at the end.",
    }


def rewrite_for_platform(
    base_content: str,
    platform: str,
    title: str,
    tracked_url: str,
    keyword: str = "",
    topic: str = "",
) -> dict[str, str]:
    platform_name = platform_source(platform)
    title = str(title or topic or keyword or "AI workflow note").strip()
    topic_text = _context_label(title, topic, keyword)
    link = ensure_platform_utm(
        tracked_url,
        platform_name,
        campaign=topic_text or title,
        content=title,
    )
    hashtags = platform_hashtags(platform_name, f"{title} {topic_text} {base_content}")

    builders = {
        "facebook": build_facebook_style,
        "telegram": build_telegram_style,
        "linkedin": build_linkedin_style,
        "twitter": build_twitter_style,
        "quora": build_quora_style,
        "reddit": build_reddit_style,
    }
    payload = builders.get(platform_name, build_telegram_style)(title, topic_text, link, hashtags, base_content)
    content = str(payload["content"]).strip()
    if platform_name == "twitter" and len(content) > 280:
        content = shorten_twitter_post(content, link, hashtags)

    return {
        "platform": platform_name,
        "content": content,
        "hashtags": hashtags.strip(),
        "tracked_url": link,
        "cta": payload.get("cta", "Read more:"),
        "hook": payload.get("hook", ""),
        "hook_style": payload.get("hook_style", ""),
        "cta_style": payload.get("cta_style", ""),
        "tone_profile": payload.get("tone_profile", ""),
        "why": payload.get("why", ""),
    }


def accounts_config_path() -> Path:
    return settings.base_dir / "config" / "social_accounts.json"


def queue_path() -> Path:
    return settings.data_dir / "social_publish_queue.csv"


def log_path() -> Path:
    return settings.data_dir / "social_publish_log.csv"


def status_path() -> Path:
    return settings.data_dir / "social_account_status.csv"


def export_dir() -> Path:
    return settings.base_dir / "draft_output" / "social_exports"


def ensure_social_accounts_config() -> dict[str, object]:
    path = accounts_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(json.dumps(DEFAULT_ACCOUNTS, indent=2, ensure_ascii=False), encoding="utf-8")
        return json.loads(json.dumps(DEFAULT_ACCOUNTS))
    try:
        current = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        current = {}
    changed = False
    for platform, defaults in DEFAULT_ACCOUNTS.items():
        if platform not in current or not isinstance(current.get(platform), dict):
            current[platform] = defaults
            changed = True
            continue
        for key, value in defaults.items():
            if key not in current[platform]:
                current[platform][key] = value
                changed = True
        for unsafe in ["password", "email"]:
            if unsafe in current[platform]:
                current[platform].pop(unsafe, None)
                changed = True
    if changed:
        path.write_text(json.dumps(current, indent=2, ensure_ascii=False), encoding="utf-8")
    return current


def token_configured(platform: str, config: dict[str, object]) -> bool:
    platform = normalize_platform(platform)
    if platform == "telegram":
        return bool(os.getenv("TELEGRAM_BOT_TOKEN", "").strip() and os.getenv("TELEGRAM_CHAT_ID", "").strip())
    if platform == "linkedin":
        return bool(os.getenv("LINKEDIN_ACCESS_TOKEN", "").strip())
    if platform == "reddit":
        return all(os.getenv(name, "").strip() for name in ["REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET", "REDDIT_USERNAME", "REDDIT_USER_AGENT"])
    if platform == "twitter":
        return all(os.getenv(name, "").strip() for name in ["TWITTER_API_KEY", "TWITTER_API_SECRET", "TWITTER_ACCESS_TOKEN", "TWITTER_ACCESS_SECRET"])
    return False


def build_account_status() -> pd.DataFrame:
    load_dotenv()
    accounts = ensure_social_accounts_config()
    existing = read_csv(status_path(), ACCOUNT_COLUMNS)
    last_by_platform = {}
    if not existing.empty:
        for _, row in existing.iterrows():
            last_by_platform[str(row.get("platform", ""))] = row.to_dict()
    rows = []
    for platform in PLATFORMS:
        config = accounts.get(platform, {}) if isinstance(accounts, dict) else {}
        configured = token_configured(platform, config if isinstance(config, dict) else {})
        mode = str(config.get("posting_mode", "manual")) if isinstance(config, dict) else "manual"
        enabled = bool(config.get("enabled", True)) if isinstance(config, dict) else False
        if not enabled:
            status = "disabled"
        elif configured:
            status = "token_configured"
        else:
            status = "manual_only"
        previous = last_by_platform.get(platform, {})
        rows.append({
            "platform": platform,
            "status": status,
            "posting_mode": mode,
            "daily_limit": str(config.get("daily_limit", "")) if isinstance(config, dict) else "",
            "scheduled_times": ", ".join(config.get("scheduled_times", [])) if isinstance(config, dict) else "",
            "last_publish_status": str(previous.get("last_publish_status", "")),
            "error_message": str(previous.get("error_message", "")),
        })
    df = pd.DataFrame(rows, columns=ACCOUNT_COLUMNS)
    df.to_csv(status_path(), index=False, encoding="utf-8-sig")
    return df


def ensure_queue() -> pd.DataFrame:
    df = read_csv(queue_path(), EXTENDED_QUEUE_COLUMNS)
    save_queue(df)
    return df


def load_queue() -> pd.DataFrame:
    return read_csv(queue_path(), EXTENDED_QUEUE_COLUMNS)


def save_queue(df: pd.DataFrame) -> pd.DataFrame:
    for column in EXTENDED_QUEUE_COLUMNS:
        if column not in df.columns:
            df[column] = ""
    df = df[EXTENDED_QUEUE_COLUMNS].fillna("").astype(str)
    df["platform"] = df["platform"].map(normalize_calendar_platform)
    queue_path().parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(queue_path(), index=False, encoding="utf-8-sig")
    return df


def ensure_log() -> pd.DataFrame:
    df = read_csv(log_path(), LOG_COLUMNS)
    if not log_path().exists() or any(column not in df.columns for column in LOG_COLUMNS):
        write_log("system", "system", "", "created", "ok", "social publish log initialized")
        return read_csv(log_path(), LOG_COLUMNS)
    # Normalize older zero-row log files that used an earlier schema.
    if len(df) == 0:
        log_path().write_text(",".join(LOG_COLUMNS) + "\n", encoding="utf-8-sig")
        return read_csv(log_path(), LOG_COLUMNS)
    return df


def write_log(post_id: str, platform: str, queue_id: str, action: str, status: str, message: str = "", published_url: str = "") -> None:
    log_path().parent.mkdir(parents=True, exist_ok=True)
    exists = log_path().exists()
    with log_path().open("a", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=LOG_COLUMNS)
        if not exists:
            writer.writeheader()
        writer.writerow({
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "post_id": post_id,
            "queue_id": queue_id,
            "platform": platform,
            "action": action,
            "status": status,
            "message": message,
            "published_url": published_url,
        })


def update_queue_status(queue_id: str, status: str, note: str = "") -> pd.DataFrame:
    df = ensure_queue()
    if df.empty:
        return df
    mask = df["queue_id"].astype(str) == str(queue_id)
    if not mask.any():
        mask = df["post_id"].astype(str) == str(queue_id)
    if not mask.any():
        return df
    now = datetime.now().isoformat(timespec="seconds")
    df.loc[mask, "status"] = status
    if status.lower() == "approved":
        df.loc[mask, "approved_at"] = now
    if status.lower() in {"published", "posted"}:
        df.loc[mask, "published_at"] = now
    if note:
        df.loc[mask, "notes"] = note
    row = df[mask].iloc[0].to_dict()
    write_log(str(row.get("post_id", "")), str(row.get("platform", "")), str(row.get("queue_id", "")), status.lower(), "ok", note)
    return save_queue(df)


def export_post(row: dict[str, object]) -> Path:
    export_dir().mkdir(parents=True, exist_ok=True)
    post_id = str(row.get("post_id", "") or row.get("queue_id", "post")).replace("/", "-")
    platform = normalize_platform(row.get("platform", ""))
    path = export_dir() / f"{post_id}-{platform}.txt"
    content = str(row.get("content", "") or row.get("title", ""))
    tracked = str(row.get("tracked_url", "") or row.get("target_url", "") or row.get("article_url", ""))
    path.write_text(
        f"Platform: {platform}\nPost ID: {post_id}\nTracked URL: {tracked}\n\n{content}\n",
        encoding="utf-8",
    )
    return path


def publish_row(row: dict[str, object], dry_run: bool = True) -> tuple[str, str, str]:
    load_dotenv()
    platform = normalize_platform(row.get("platform", ""))
    queue = load_queue()
    policy = validate_post(row, queue=queue)
    if not policy.valid:
        return "failed", "policy_failed: " + ",".join(policy.errors), ""
    accounts = ensure_social_accounts_config()
    config = accounts.get(platform, {}) if isinstance(accounts, dict) else {}
    mode = str(config.get("posting_mode", "manual")) if isinstance(config, dict) else "manual"
    if mode not in {"approved_auto", "auto"}:
        exported = export_post(row)
        return "manual_required", f"manual/export mode. Exported {exported}", ""
    if platform != "telegram":
        exported = export_post(row)
        return "manual_required", "auto publish is not enabled for this platform. Exported copy-ready post.", ""
    if dry_run:
        return "manual_required", "dry_run: Telegram would publish if token/chat_id are configured.", ""
    return send_telegram(row)


def send_telegram(row: dict[str, object]) -> tuple[str, str, str]:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        exported = export_post(row)
        return "manual_required", f"Telegram token/chat_id missing. Exported {exported}", ""
    message = str(row.get("content", "") or row.get("title", ""))
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
            return "published", body[:500], ""
    except urllib.error.URLError as exc:
        return "failed", str(exc), ""


def process_queue(dry_run: bool = True, publish_now_queue_id: str = "") -> dict[str, int]:
    build_account_status()
    queue = ensure_queue()
    if queue.empty:
        return {"processed": 0, "published": 0, "failed": 0, "manual_required": 0, "skipped": 0}
    now = datetime.now()
    processed = published = failed = manual_required = skipped = 0
    for idx, row in queue.iterrows():
        status = str(row.get("status", "")).lower()
        if publish_now_queue_id:
            if str(row.get("queue_id", "")) != publish_now_queue_id and str(row.get("post_id", "")) != publish_now_queue_id:
                continue
        elif status not in {"scheduled", "approved"}:
            continue
        scheduled_time = parse_time(str(row.get("scheduled_time", "")))
        if not publish_now_queue_id and scheduled_time and scheduled_time > now:
            skipped += 1
            continue
        processed += 1
        attempts = safe_int(row.get("attempts", "0")) + 1
        result, message, published_url = publish_row(row.to_dict(), dry_run=dry_run)
        queue.loc[idx, "last_attempt"] = now.isoformat(timespec="seconds")
        queue.loc[idx, "attempts"] = str(attempts)
        queue.loc[idx, "error"] = "" if result in {"published", "manual_required"} else message
        if result == "published":
            queue.loc[idx, "status"] = "Published"
            queue.loc[idx, "published_at"] = now.isoformat(timespec="seconds")
            queue.loc[idx, "published_url"] = published_url
            published += 1
        elif result == "manual_required":
            queue.loc[idx, "status"] = "manual_required"
            manual_required += 1
        else:
            queue.loc[idx, "status"] = "failed"
            failed += 1
        write_log(str(row.get("post_id", "")), str(row.get("platform", "")), str(row.get("queue_id", "")), "publish_attempt", result, message, published_url)
    save_queue(queue)
    build_account_status()
    return {"processed": processed, "published": published, "failed": failed, "manual_required": manual_required, "skipped": skipped}


def validate_queue() -> pd.DataFrame:
    queue = ensure_queue()
    if queue.empty:
        return queue
    summaries = []
    for _, row in queue.iterrows():
        summaries.append(policy_summary(row.to_dict(), queue=queue))
    queue["policy_warnings"] = summaries
    queue["policy_status"] = ["fail" if str(item).startswith("errors=") or "errors=" in str(item) else "pass" for item in summaries]
    return save_queue(queue)


def read_csv(path: Path, columns: list[str]) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=columns)
    try:
        df = pd.read_csv(path, encoding="utf-8-sig")
    except Exception:
        df = pd.DataFrame(columns=columns)
    for column in columns:
        if column not in df.columns:
            df[column] = ""
    extra = [column for column in df.columns if column not in columns]
    return df[columns + extra].fillna("").astype(str)


def parse_time(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value or ""))
    except ValueError:
        return None


def safe_int(value: object) -> int:
    try:
        return int(str(value or "0"))
    except ValueError:
        return 0


def ensure_social_publisher_assets() -> dict[str, int]:
    ensure_social_accounts_config()
    seed_queue_from_sources()
    queue = validate_queue()
    ensure_log()
    from modules.telegram_publisher import ensure_telegram_log

    ensure_telegram_log()
    status = build_account_status()
    return {"queue_rows": len(queue), "account_rows": len(status)}


def seed_queue_from_sources() -> pd.DataFrame:
    """Create pending-review publisher queue rows from existing local social drafts.

    This does not publish. It only converts already generated campaign/community
    copy into a single human-approved queue.
    """
    queue = ensure_queue()
    existing = set(queue["queue_id"].astype(str)) if not queue.empty else set()
    rows: list[dict[str, str]] = []
    changed_existing = False

    community_path = settings.data_dir / "community_post_drafts.csv"
    if community_path.exists():
        try:
            community = pd.read_csv(community_path, encoding="utf-8-sig").fillna("")
        except Exception:
            community = pd.DataFrame()
        for _, item in community.iterrows():
            post_id = str(item.get("post_id", "")).strip()
            if not post_id:
                continue
            platform = normalize_community_platform(str(item.get("platform", "")), str(item.get("community_name", "")))
            queue_id = f"mp-{post_id}"
            if queue_id in existing:
                mask = queue["queue_id"].astype(str) == queue_id
                if mask.any():
                    queue.loc[mask, "platform"] = platform
                    queue.loc[mask, "channel_type"] = "external_group" if platform in {"facebook_group", "reddit", "quora", "linkedin_group"} else "owned_or_manual"
                    queue.loc[mask, "community_id"] = str(item.get("community_id", ""))
                    queue.loc[mask, "community_name"] = str(item.get("community_name", ""))
                    pending_mask = mask & queue["status"].astype(str).str.lower().isin({"", "draft", "pending_review", "needs_edit"})
                    if pending_mask.any():
                        queue.loc[pending_mask, "content"] = str(item.get("content", ""))
                        queue.loc[pending_mask, "tracked_url"] = str(item.get("tracked_url", ""))
                        queue.loc[pending_mask, "article_url"] = str(item.get("source_url", ""))
                        queue.loc[pending_mask, "target_url"] = str(item.get("source_url", "")) or strip_query(str(item.get("tracked_url", "")))
                    changed_existing = True
                continue
            rows.append(make_queue_row(
                queue_id=queue_id,
                post_id=post_id,
                platform=platform,
                title=str(item.get("community_name", "")) or str(item.get("content_variant", "")),
                content=str(item.get("content", "")),
                tracked_url=str(item.get("tracked_url", "")),
                article_url=str(item.get("source_url", "")),
                community_id=str(item.get("community_id", "")),
                community_name=str(item.get("community_name", "")),
                status=str(item.get("status", "pending_review")) or "pending_review",
            ))
            existing.add(queue_id)

    calendar_path = settings.data_dir / "social_calendar.csv"
    if calendar_path.exists():
        try:
            calendar = pd.read_csv(calendar_path, encoding="utf-8-sig").fillna("")
        except Exception:
            calendar = pd.DataFrame()
        for _, item in calendar.iterrows():
            post_id = str(item.get("id", "")).strip()
            if not post_id:
                continue
            platform = normalize_calendar_platform(str(item.get("platform", "")))
            queue_id = f"mp-{post_id}"
            if queue_id in existing:
                continue
            rows.append(make_queue_row(
                queue_id=queue_id,
                post_id=post_id,
                platform=platform,
                title=str(item.get("post_title", "")),
                content=str(item.get("post_body", "")),
                tracked_url=str(item.get("target_url", "")),
                article_url=str(item.get("target_url", "")),
                status=str(item.get("status", "Pending Review")) or "Pending Review",
                scheduled_time=combine_schedule(str(item.get("scheduled_date", "")), str(item.get("scheduled_time", ""))),
            ))
            existing.add(queue_id)

    if rows:
        queue = pd.concat([queue, pd.DataFrame(rows)], ignore_index=True)
        save_queue(queue)
    elif changed_existing:
        save_queue(queue)
    return load_queue()


def make_queue_row(
    queue_id: str,
    post_id: str,
    platform: str,
    title: str,
    content: str,
    tracked_url: str,
    article_url: str = "",
    community_id: str = "",
    community_name: str = "",
    status: str = "pending_review",
    scheduled_time: str = "",
) -> dict[str, str]:
    parsed = parse_utm(tracked_url)
    return {
        "queue_id": queue_id,
        "post_id": post_id,
        "draft_id": post_id,
        "platform": platform,
        "channel_type": "external_group" if platform in {"facebook_group", "reddit", "quora", "linkedin_group"} else "owned_or_manual",
        "community_id": community_id,
        "community_name": community_name,
        "title": title,
        "content": content,
        "article_url": article_url,
        "target_url": article_url or strip_query(tracked_url),
        "tracked_url": tracked_url,
        "utm_source": parsed.get("utm_source", ""),
        "utm_medium": parsed.get("utm_medium", ""),
        "utm_campaign": parsed.get("utm_campaign", ""),
        "utm_content": parsed.get("utm_content", ""),
        "status": normalize_status(status),
        "scheduled_time": scheduled_time,
        "approved_at": "",
        "published_at": "",
        "last_attempt": "",
        "attempts": "0",
        "error": "",
        "policy_status": "",
        "policy_warnings": "",
        "manual_export_path": "",
        "published_url": "",
        "notes": "Human approval required before publishing.",
    }


def normalize_community_platform(platform: str, community_name: str = "") -> str:
    value = platform.lower()
    if "facebook" in value:
        return "facebook_group"
    if "linkedin" in value:
        return "linkedin_group"
    if "telegram" in value:
        return "telegram"
    if "reddit" in value:
        return "reddit"
    if "quora" in value:
        return "quora"
    if "twitter" in value or value == "x":
        return "twitter"
    return normalize_platform(platform)


def normalize_calendar_platform(platform: str) -> str:
    value = platform.lower()
    if "facebook_group" in value:
        return "facebook_group"
    if "facebook_profile" in value:
        return "facebook_profile"
    if "facebook_page" in value:
        return "facebook_page"
    if "linkedin_group" in value:
        return "linkedin_group"
    if "telegram" in value:
        return "telegram"
    if "linkedin" in value:
        return "linkedin"
    if "twitter" in value or value == "x":
        return "twitter"
    if "facebook" in value:
        return "facebook_page"
    return normalize_platform(platform)


def normalize_status(value: str) -> str:
    raw = str(value or "").strip().lower().replace("_", " ")
    if raw in {"approved"}:
        return "approved"
    if raw in {"scheduled"}:
        return "Scheduled"
    if raw in {"published", "posted"}:
        return "Published"
    if raw in {"rejected"}:
        return "Rejected"
    return "pending_review"


def combine_schedule(day: str, time_value: str) -> str:
    day = str(day or "").strip()
    time_value = str(time_value or "").strip()
    if not day or not time_value:
        return ""
    if "T" in day:
        return day
    return f"{day}T{time_value[:5]}"


def parse_utm(url: str) -> dict[str, str]:
    from urllib.parse import parse_qs, urlparse

    query = parse_qs(urlparse(str(url or "")).query)
    return {key: values[0] for key, values in query.items() if values}


def strip_query(url: str) -> str:
    from urllib.parse import urlunparse, urlparse

    parsed = urlparse(str(url or ""))
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))
