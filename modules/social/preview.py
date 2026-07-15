from __future__ import annotations

from .utils import PublishedArticle


def format_preview(payload: dict[str, object]) -> str:
    post_text = str(payload.get("post_text") or "")
    lines = [
        "------------------------------------",
        f"PLATFORM: {payload.get('platform') or ''}",
        "",
        str(payload.get("title") or ""),
        "",
        str(payload.get("description") or ""),
        "",
        "POST TEXT:",
        post_text,
        "",
        f"CTA: {payload.get('cta') or ''}",
        f"IMAGE: {payload.get('image') or payload.get('image_url') or ''}",
        f"CANONICAL URL: {payload.get('canonical_url') or payload.get('url') or ''}",
        f"CHARACTERS: {payload.get('character_count') or len(post_text)}",
    ]
    if payload.get("board"):
        lines.append(f"BOARD: {payload.get('board')}")
    if payload.get("hashtags"):
        lines.append(f"HASHTAGS: {' '.join(str(tag) for tag in payload.get('hashtags') or [])}")
    if payload.get("tags"):
        lines.append(f"TAGS: {', '.join(str(tag) for tag in payload.get('tags') or [])}")
    if payload.get("affiliate_disclosure"):
        lines.append(f"DISCLOSURE: {payload.get('affiliate_disclosure')}")
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
