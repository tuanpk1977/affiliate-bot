from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from config import settings
from modules.content_approval import create_draft, slugify


TOPIC_COLUMNS = ["group", "title", "slug", "tool", "keyword", "page_type", "status"]


def topics_config_path() -> Path:
    return settings.base_dir / "config" / "ai_coding_topics.json"


def load_topic_config() -> dict[str, list[dict[str, str]]]:
    path = topics_config_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return {str(group): [normalize_topic(group, item) for item in items if isinstance(item, dict)] for group, items in data.items() if isinstance(items, list)}


def topic_dataframe() -> pd.DataFrame:
    rows = []
    for group, items in load_topic_config().items():
        rows.extend(items)
    df = pd.DataFrame(rows, columns=TOPIC_COLUMNS)
    if df.empty:
        return pd.DataFrame(columns=TOPIC_COLUMNS)
    return df.fillna("")


def normalize_topic(group: str, item: dict[str, str]) -> dict[str, str]:
    title = str(item.get("title", "")).strip()
    slug = slugify(item.get("slug") or title)
    return {
        "group": group,
        "title": title,
        "slug": slug,
        "tool": str(item.get("tool", "")).strip(),
        "keyword": str(item.get("keyword", title)).strip(),
        "page_type": str(item.get("page_type", "Blog article")).strip(),
        "status": str(item.get("status", "idea")).strip() or "idea",
    }


def generate_topic_draft(topic: dict[str, str]) -> dict[str, str]:
    normalized = normalize_topic(str(topic.get("group", "topics")), topic)
    content = render_topic_draft(normalized)
    return create_draft(
        content_type=normalized["page_type"],
        target_channel="Website",
        title=normalized["title"],
        slug=normalized["slug"],
        topic=normalized["keyword"],
        draft_content=content,
        status="Pending Review",
        target_url=f"/{normalized['slug']}/",
        notes="Generated from AI coding topic expansion. Review before publishing.",
    )


def render_topic_draft(topic: dict[str, str]) -> str:
    title = topic["title"]
    tool = topic["tool"] or "the tool"
    keyword = topic["keyword"]
    return f"""# {title}

Affiliate disclosure: Some links may be affiliate links. We may earn a commission at no extra cost to you.

## Short answer

This page should be written from a real builder workflow angle, not from a vendor feature list. The core question behind "{keyword}" is whether {tool} helps when the project is messy: broken builds, repeated refactors, unclear context, and deployment errors.

## My current AI coding workflow

I would frame the article around a practical handoff: Windsurf for rough project structure, Codex-style reasoning for architecture repair and broken builds, Cursor for fast iteration inside a cleaner repo, and GitHub Copilot for lightweight autocomplete. The recommendation should explain where this stack saves time and where it creates review risk.

## What failed

Include concrete failure modes: Windsurf can generate duplicated logic during fast scaffolding, Cursor can repeat a small fix loop when the prompt is too broad, Copilot can miss the full project context, and Codex-style repair works best when the prompt includes logs, file paths, and the exact failure.

## Practical comparison table

Compare speed, context understanding, debugging ability, deployment help, large project stability, beginner friendliness, and pricing value. Do not make every tool look perfect.

## Internal links to include

- /review/cursor/
- /windsurf-review/
- /review/github-copilot/
- /comparisons/cursor-vs-windsurf/
- /comparisons/copilot-vs-cursor/
- /pricing/cursor/
- /category/ai-coding-tools/

## Soft CTA

Use tracking-safe CTA links such as /go/cursor/?src=topic-draft&cta=topic_page and /go/windsurf/?src=topic-draft&cta=topic_page only after the final page is approved.

## FAQ ideas

- Which AI coding tool actually fixes bugs faster?
- Is Cursor better than Windsurf for large projects?
- When should I use Codex after Windsurf?
- Why do AI coding tools fail on refactors?
- What should I do when Cursor cannot fix a bug?
- How should solo builders choose an AI coding stack?
"""
