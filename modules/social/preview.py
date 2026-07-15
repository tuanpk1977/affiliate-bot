from __future__ import annotations

from .utils import PublishedArticle


def format_preview(payload: dict[str, object]) -> str:
    lines = [
        "------------------------------------",
        str(payload.get("title") or ""),
        "",
        str(payload.get("description") or ""),
        "",
        f"IMAGE: {payload.get('image') or ''}",
        f"URL: {payload.get('url') or payload.get('canonical_url') or ''}",
    ]
    if payload.get("board"):
        lines.append(f"BOARD: {payload.get('board')}")
    if payload.get("tags"):
        lines.append(f"TAGS: {', '.join(str(tag) for tag in payload.get('tags') or [])}")
    lines.append("------------------------------------")
    return "\n".join(lines)


def generic_article_preview(article: PublishedArticle) -> str:
    return format_preview(
        {
            "title": article.title,
            "description": article.description,
            "image": article.image,
            "url": article.url,
            "tags": article.tags,
        }
    )

