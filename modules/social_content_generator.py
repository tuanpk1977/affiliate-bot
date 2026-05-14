from __future__ import annotations

import csv
import io
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Iterable

import pandas as pd
from PIL import Image, ImageDraw, ImageFont

from config import settings


PLATFORMS = ["facebook", "telegram", "linkedin", "twitter"]
REPORT_COLUMNS = [
    "post_id",
    "draft_id",
    "article_slug",
    "platform",
    "title",
    "article_url",
    "status",
    "output_path",
    "created_at",
    "scheduled_time",
    "published_at",
    "error",
    "image_path",
]


def social_config_path() -> Path:
    return settings.base_dir / "config" / "social_accounts.json"


def social_posts_root() -> Path:
    return settings.base_dir / "draft_output" / "social_posts"


def social_images_root() -> Path:
    return settings.base_dir / "draft_output" / "social_images"


def report_path() -> Path:
    return settings.data_dir / "social_post_report.csv"


def load_social_accounts() -> dict[str, dict[str, object]]:
    path = social_config_path()
    if not path.exists():
        return {}
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    telegram = config.setdefault("telegram", {})
    telegram["bot_token"] = os.getenv("TELEGRAM_BOT_TOKEN", str(telegram.get("bot_token", ""))).strip()
    telegram["chat_id"] = os.getenv("TELEGRAM_CHAT_ID", str(telegram.get("chat_id", ""))).strip()
    return config


def article_url_from_draft(row: dict[str, str]) -> str:
    target_url = str(row.get("target_url", "") or "").strip()
    if target_url:
        return target_url
    base = (settings.base_site_url or settings.site_domain or "https://review.mssmileenglish.com").rstrip("/")
    slug = slugify(row.get("slug") or row.get("title") or "draft")
    return f"{base}/{slug}/"


def generate_social_pack(row: dict[str, str], platforms: Iterable[str] | None = None) -> list[dict[str, str]]:
    selected = [item for item in (platforms or PLATFORMS) if item in PLATFORMS]
    slug = slugify(row.get("slug") or row.get("title") or "draft")
    title = str(row.get("title", "") or slug.replace("-", " ").title()).strip()
    topic = str(row.get("topic", "") or title).strip()
    article_url = article_url_from_draft(row)
    content = str(row.get("draft_content", "") or "")
    excerpt = extract_excerpt(content, title)
    image_path = generate_social_image(title, topic, slug)
    output_dir = social_posts_root() / slug
    output_dir.mkdir(parents=True, exist_ok=True)

    records: list[dict[str, str]] = []
    created_at = datetime.now().isoformat(timespec="seconds")
    for platform in selected:
        post_id = f"{slug}-{platform}"
        body = render_platform_post(platform, title, topic, excerpt, article_url)
        output_file = output_dir / f"{platform}.txt"
        output_file.write_text(body, encoding="utf-8")
        records.append(
            {
                "post_id": post_id,
                "draft_id": str(row.get("draft_id", "")),
                "article_slug": slug,
                "platform": platform,
                "title": title,
                "article_url": article_url,
                "status": "Pending Review",
                "output_path": str(output_file),
                "created_at": created_at,
                "scheduled_time": "",
                "published_at": "",
                "error": "",
                "image_path": str(image_path),
            }
        )
    save_social_post_report(records)
    write_manifest(slug, records)
    return records


def render_platform_post(platform: str, title: str, topic: str, excerpt: str, article_url: str) -> str:
    tags = hashtags_for(topic)
    angle = coding_angle(title, topic, excerpt)
    if platform == "facebook":
        return (
            f"Mình ghi lại một bài ngắn về {title} theo góc nhìn build project thật, không phải chỉ nhìn danh sách tính năng.\n\n"
            f"Góc nhìn chính: {angle}\n\n"
            "Điều mình quan tâm nhất: công cụ này giúp debug nhanh hơn hay chỉ tạo thêm code phải dọn?\n\n"
            f"Đọc bài đầy đủ:\n{article_url}\n\n"
            f"{tags}\n\n"
            "Disclosure: Some links may be affiliate links."
        )
    if platform == "telegram":
        return (
            f"{title}\n\n"
            f"Takeaway: {angle}\n\n"
            f"Đọc tiếp: {article_url}\n\n"
            f"{tags}\n"
            "Disclosure: may include affiliate links."
        )
    if platform == "linkedin":
        return (
            f"{title}\n\n"
            "I stopped judging AI coding tools by how impressive the first generated answer looks.\n\n"
            "The better test is what happens after the project gets messy: failed builds, duplicated logic, unclear architecture, and half-working refactors.\n\n"
            f"My working note: {angle}\n\n"
            f"Full builder note: {article_url}\n\n"
            f"{tags}\n\n"
            "Affiliate disclosure: some links may be affiliate links."
        )
    if platform == "twitter":
        return (
            f"{strong_hook(title, topic)}\n\n"
            f"1/ {angle}\n"
            "2/ Fast code is not always cheaper if review time explodes.\n"
            "3/ My rule: scaffold fast, debug slowly, ship only small trusted diffs.\n"
            f"4/ Full note:\n{article_url}\n\n"
            f"{tags}"
        )
    return f"{title}\n\n{angle}\n\n{article_url}\n\n{tags}"


def coding_angle(title: str, topic: str, excerpt: str) -> str:
    text = f"{title} {topic} {excerpt}".lower()
    if "windsurf" in text and "cursor" in text:
        return "Cursor gives me tighter control once the repo is clean; Windsurf is faster when I need rough structure from zero."
    if "copilot" in text and "cursor" in text:
        return "Copilot is useful background autocomplete, but Cursor is stronger when the task needs editor-level context."
    if "windsurf" in text:
        return "Windsurf is fast for scaffolding, but I still review big refactors carefully because duplicated logic can slip in."
    if "cursor" in text:
        return "Cursor feels strongest when debugging inside an existing codebase, not when treated like simple autocomplete."
    if "copilot" in text:
        return "Copilot is comfortable for lightweight suggestions, but I would not ask it to own a large architecture repair."
    if "codex" in text:
        return "Codex-style reasoning is best when the project is already broken and the next move needs evidence, not more generated code."
    return excerpt or "The useful question is whether the tool improves a real workflow after debugging, review, and deployment checks."


def strong_hook(title: str, topic: str) -> str:
    text = f"{title} {topic}".lower()
    if "cursor" in text and "windsurf" in text:
        return "I stopped comparing Cursor vs Windsurf by demos."
    if "copilot" in text and "cursor" in text:
        return "Copilot vs Cursor is not just autocomplete vs chat."
    if "debug" in text or "bug" in text:
        return "Which AI coding tool actually fixes bugs faster?"
    if "workflow" in text:
        return "My current AI coding workflow is a handoff chain."
    return "AI coding tools only matter after the first draft breaks."


def generate_social_image(title: str, topic: str, slug: str) -> Path:
    output = social_images_root() / f"{slug}.png"
    output.parent.mkdir(parents=True, exist_ok=True)
    width, height = 1200, 630
    image = Image.new("RGB", (width, height), (12, 18, 28))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((54, 54, width - 54, height - 54), radius=34, fill=(22, 31, 45), outline=(77, 119, 255), width=2)
    badge = social_badge(title, topic)
    font_big = load_font(56)
    font_mid = load_font(32)
    font_small = load_font(24)
    draw.rounded_rectangle((92, 92, 92 + len(badge) * 18 + 44, 142), radius=20, fill=(46, 99, 255))
    draw.text((114, 104), badge, font=font_small, fill=(255, 255, 255))
    y = 184
    for line in wrap_text(title, 30)[:3]:
        draw.text((92, y), line, font=font_big, fill=(246, 248, 252))
        y += 68
    tool_line = tool_names_from_text(f"{title} {topic}") or "Cursor / Windsurf / Codex / Copilot"
    draw.text((92, 430), tool_line, font=font_mid, fill=(160, 196, 255))
    draw.text((92, 500), "AI Tool Review Hub - real workflow notes", font=font_small, fill=(197, 207, 224))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    output.write_bytes(buffer.getvalue())
    return output


def load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/segoeui.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            try:
                return ImageFont.truetype(candidate, size)
            except Exception:
                continue
    return ImageFont.load_default()


def wrap_text(text: str, max_chars: int) -> list[str]:
    words = str(text or "").split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) > max_chars and current:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines or ["AI coding workflow"]


def social_badge(title: str, topic: str) -> str:
    text = f"{title} {topic}".lower()
    if "failed" in text or "bug" in text or "debug" in text:
        return "What failed?"
    if " vs " in text or "comparison" in text:
        return "Comparison"
    if "workflow" in text:
        return "Real workflow test"
    return "Builder note"


def tool_names_from_text(text: str) -> str:
    tools = []
    lookup = [("cursor", "Cursor"), ("windsurf", "Windsurf"), ("codex", "Codex"), ("copilot", "GitHub Copilot"), ("replit", "Replit"), ("bolt", "Bolt"), ("lovable", "Lovable"), ("devin", "Devin")]
    lower = text.lower()
    for token, label in lookup:
        if token in lower and label not in tools:
            tools.append(label)
    return " / ".join(tools)


def save_social_post_report(records: list[dict[str, str]]) -> None:
    path = report_path()
    existing = read_report(path)
    by_id = {row.get("post_id", ""): row for row in existing}
    for record in records:
        by_id[record["post_id"]] = {**by_id.get(record["post_id"], {}), **record}
    write_rows(path, list(by_id.values()), REPORT_COLUMNS)


def read_social_post_report() -> pd.DataFrame:
    path = report_path()
    if not path.exists():
        ensure_report()
    try:
        df = pd.read_csv(path)
    except Exception:
        df = pd.DataFrame(columns=REPORT_COLUMNS)
    for column in REPORT_COLUMNS:
        if column not in df.columns:
            df[column] = ""
    return df[REPORT_COLUMNS].fillna("")


def ensure_report() -> None:
    write_rows(report_path(), [], REPORT_COLUMNS)


def write_distribution_summary(queue_df: pd.DataFrame | None = None) -> Path:
    posts = read_social_post_report()
    queue = queue_df if queue_df is not None else pd.DataFrame()
    lines = [
        "SOCIAL DISTRIBUTION SUMMARY",
        f"generated_posts: {len(posts)}",
        f"approved_posts: {count_status(posts, 'Approved')}",
        f"scheduled_posts: {count_queue_status(queue, 'Scheduled')}",
        f"published_posts: {count_queue_status(queue, 'Published')}",
        f"failed_posts: {count_queue_status(queue, 'Failed')}",
        "",
        "Platform stats:",
    ]
    if not posts.empty:
        for platform, count in posts["platform"].astype(str).value_counts().items():
            lines.append(f"- {platform}: {count}")
    else:
        lines.append("- no social posts generated yet")
    lines.extend(
        [
            "",
            "Safety:",
            "- No social post is published without approval and queue scheduling.",
            "- Facebook, LinkedIn, and X/Twitter are safe-copy mode only.",
            "- Telegram requires TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID before sending.",
        ]
    )
    path = settings.data_dir / "distribution_summary.txt"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def count_status(df: pd.DataFrame, status: str) -> int:
    if df is None or df.empty or "status" not in df.columns:
        return 0
    return int((df["status"].astype(str) == status).sum())


def count_queue_status(df: pd.DataFrame, status: str) -> int:
    return count_status(df, status)


def write_manifest(slug: str, records: list[dict[str, str]]) -> None:
    path = social_posts_root() / slug / "manifest.json"
    path.write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")


def extract_excerpt(content: str, fallback: str) -> str:
    text = re.sub(r"<[^>]+>", " ", str(content or ""))
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return f"{fallback} needs to be judged by use case, pricing risk, and real workflow fit."
    sentences = re.split(r"(?<=[.!?])\s+", text)
    for sentence in sentences:
        clean = sentence.strip()
        if 80 <= len(clean) <= 240 and not clean.lower().startswith(("title:", "meta ")):
            return clean
    return (text[:220].rstrip() + "...") if len(text) > 220 else text


def hashtags_for(topic: str) -> str:
    text = str(topic or "").lower()
    tags = ["#AITools", "#SaaS", "#AffiliateMarketing"]
    if any(word in text for word in ["coding", "cursor", "copilot", "codex", "windsurf", "replit", "bolt", "lovable", "devin"]):
        tags.append("#AICoding")
    if "seo" in text:
        tags.append("#SEO")
    if "marketing" in text:
        tags.append("#MarketingAutomation")
    return " ".join(dict.fromkeys(tags))


def read_report(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_rows(path: Path, rows: list[dict[str, str]], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in columns})


def slugify(text: object) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(text or "").lower()).strip("-") or "draft"
