from __future__ import annotations

import re
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

from .utils import ROOT, now_iso


COPY_DIR = ROOT / "artifacts" / "social_clipboard"


@dataclass(frozen=True)
class CopyResult:
    copied_to_clipboard: bool
    file_path: Path
    text: str


def safe_filename(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "-", value.strip()).strip("-")
    return cleaned[:120] or "social-content"


def _clean_pinterest_description(value: Any) -> str:
    text = str(value or "").strip()
    text = re.sub(r"^#\s*Pinterest pin draft\s*", "", text, flags=re.IGNORECASE).strip()
    cleaned_lines: list[str] = []
    skip_prefixes = (
        "pin title:",
        "destination url:",
        "source link:",
        "website url:",
        "canonical url:",
        "canonical url note:",
        "image url:",
        "image path:",
        "local image file:",
        "suggested board:",
        "keywords:",
        "overlay text:",
        "alt text:",
        "reviewer notes:",
    )
    for raw_line in text.splitlines():
        line = raw_line.strip()
        lower = line.lower()
        if any(lower.startswith(prefix) for prefix in skip_prefixes):
            continue
        if lower.startswith("pin description:"):
            cleaned_lines.append(line.split(":", 1)[1].strip())
            continue
        cleaned_lines.append(raw_line.rstrip())
    text = "\n".join(cleaned_lines).strip()
    text = re.sub(
        r"read the full (?:guide|article|comparison|source article)[^\n]*https?://\S+",
        "Read the full article on Smile AI Review Hub.",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"https?://\S+", "", text).strip()
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def prepared_text(payload: dict[str, Any], field: str = "all") -> str:
    if payload.get("platform") == "blogger":
        labels = payload.get("labels") or []
        label_text = ", ".join(str(item) for item in labels) if isinstance(labels, list) else str(labels or "")
        if field in {"title", "blogger_title"}:
            return str(payload.get("blogger_title") or payload.get("title") or "")
        if field == "html_body":
            return str(payload.get("html_body") or "")
        if field in {"body", "plain_text_body", "post_text"}:
            return str(payload.get("plain_text_body") or payload.get("post_text") or "")
        if field == "labels":
            return label_text
        if field == "search_description":
            return str(payload.get("search_description") or "")
        if field in {"url", "website_url", "source_article_url"}:
            return str(payload.get("source_article_url") or payload.get("url") or payload.get("canonical_url") or "")
        if field in {"permalink_slug", "recommended_permalink_slug"}:
            return str(payload.get("recommended_permalink_slug") or "")
        if field in {"alt_text", "image_alt_text"}:
            return str(payload.get("image_alt_text") or payload.get("alt_text") or "")
        if field in {"image", "image_path"}:
            return str(payload.get("image_path") or payload.get("image_asset_path") or "")
        if field == "all":
            return "\n\n".join(
                part
                for part in [
                    str(payload.get("blogger_title") or payload.get("title") or ""),
                    str(payload.get("plain_text_body") or payload.get("post_text") or ""),
                    str(payload.get("source_article_url") or payload.get("url") or ""),
                    str(payload.get("disclosure") or ""),
                ]
                if part
            ).strip() + "\n"
    if payload.get("platform") == "bluesky":
        posts = payload.get("thread_posts") or []
        thread_text = "\n\n".join(str(post) for post in posts) if isinstance(posts, list) else str(posts or "")
        if field in {"body", "post", "post_body", "standalone_post"}:
            return str(payload.get("standalone_post") or payload.get("post_text") or "")
        if field == "full_thread":
            return thread_text
        if field.startswith("thread_post_"):
            try:
                index = int(field.replace("thread_post_", "")) - 1
                return str(posts[index]) if isinstance(posts, list) and 0 <= index < len(posts) else ""
            except ValueError:
                return ""
        if field in {"url", "website_url", "article_url"}:
            return str(payload.get("article_url") or payload.get("url") or payload.get("canonical_url") or "")
        if field in {"alt_text", "image_alt_text"}:
            return str(payload.get("image_alt_text") or payload.get("alt_text") or "")
        if field in {"image", "image_path"}:
            return str(payload.get("image_path") or payload.get("image_asset_path") or "")
        if field == "all":
            return "\n\n".join(part for part in [str(payload.get("standalone_post") or payload.get("post_text") or ""), thread_text] if part).strip() + "\n"
    if payload.get("platform") == "pinterest":
        pin_title = str(payload.get("pin_title") or payload.get("title") or "")
        pin_description = _clean_pinterest_description(payload.get("pin_description") or payload.get("post_text") or "")
        destination_url = str(payload.get("destination_url") or payload.get("url") or payload.get("canonical_url") or "")
        suggested_board = str(payload.get("suggested_board") or "")
        alt_text = str(payload.get("alt_text") or "")
        keywords = payload.get("keywords") or []
        keyword_text = "\n".join(str(item) for item in keywords) if isinstance(keywords, list) else str(keywords or "")
        if field == "title":
            return pin_title
        if field in {"body", "post_body", "post", "pin_description"}:
            return pin_description
        if field in {"url", "website_url", "destination_url"}:
            return destination_url
        if field == "suggested_board":
            return suggested_board
        if field == "keywords":
            return keyword_text
        if field == "alt_text":
            return alt_text
        if field in {"image", "image_path"}:
            return str(payload.get("image_asset_path") or "")
        if field == "all":
            return "\n\n".join(
                part
                for part in [
                    "PIN TITLE",
                    pin_title,
                    "PIN DESCRIPTION",
                    pin_description,
                    "DESTINATION URL",
                    destination_url,
                    "SUGGESTED BOARD",
                    suggested_board,
                    "ALT TEXT",
                    alt_text,
                    "KEYWORDS",
                    keyword_text,
                ]
                if part
            ).strip() + "\n"
    if field == "title":
        return str(payload.get("title") or "")
    if field in {"body", "post_body", "post"}:
        return str(payload.get("post_text") or "")
    if field in {"cta", "call_to_action"}:
        return str(payload.get("cta") or "")
    if field in {"hashtags", "tags"}:
        tags = payload.get("hashtags") or payload.get("tags") or []
        if isinstance(tags, list):
            return " ".join(str(tag) for tag in tags)
        return str(tags or "")
    if field in {"url", "website_url"}:
        return str(payload.get("url") or payload.get("canonical_url") or "")
    if field == "image":
        return str(payload.get("image_url") or payload.get("image") or "")
    if payload.get("clean_social_copy"):
        tags = payload.get("hashtags") or payload.get("tags") or []
        tag_text = " ".join(str(tag) for tag in tags) if isinstance(tags, list) else str(tags or "")
        return "\n\n".join(
            part for part in [
                str(payload.get("title") or ""),
                str(payload.get("post_text") or ""),
                str(payload.get("cta") or ""),
                str(payload.get("url") or payload.get("canonical_url") or ""),
                tag_text,
            ]
            if part
        ).strip() + "\n"
    lines = [
        f"Platform: {payload.get('platform') or ''}",
        f"Title: {payload.get('title') or ''}",
        "",
        "Post body:",
        str(payload.get("post_text") or ""),
        "",
        f"Website URL: {payload.get('url') or payload.get('canonical_url') or ''}",
        f"Canonical URL: {payload.get('canonical_url') or payload.get('url') or ''}",
        f"Image URL: {payload.get('image_url') or payload.get('image') or ''}",
        f"CTA: {payload.get('cta') or ''}",
    ]
    if payload.get("board"):
        lines.append(f"Suggested board: {payload.get('board')}")
    if payload.get("hashtags"):
        lines.append(f"Hashtags: {' '.join(str(tag) for tag in payload.get('hashtags') or [])}")
    if payload.get("tags"):
        lines.append(f"Tags: {', '.join(str(tag) for tag in payload.get('tags') or [])}")
    if payload.get("affiliate_disclosure"):
        lines.extend(["", f"Disclosure: {payload.get('affiliate_disclosure')}"])
    return "\n".join(lines).strip() + "\n"


def copy_or_write(
    payload: dict[str, Any],
    *,
    field: str = "all",
    root: Path = ROOT,
    use_clipboard: bool = True,
) -> CopyResult:
    text = prepared_text(payload, field)
    copy_dir = root / "artifacts" / "social_clipboard"
    copy_dir.mkdir(parents=True, exist_ok=True)
    stamp = now_iso().replace(":", "").replace("+", "Z")
    platform = safe_filename(str(payload.get("platform") or "platform"))
    title = safe_filename(str(payload.get("title") or "post"))
    path = copy_dir / f"{stamp}-{platform}-{field}-{title}.txt"
    path.write_text(text, encoding="utf-8")
    copied = False
    if use_clipboard:
        try:
            import tkinter  # type: ignore

            root_window = tkinter.Tk()
            root_window.withdraw()
            root_window.clipboard_clear()
            root_window.clipboard_append(text)
            root_window.update()
            root_window.destroy()
            copied = True
        except Exception:
            copied = False
    return CopyResult(copied_to_clipboard=copied, file_path=path, text=text)


def platform_target_url(platform: str, payload: dict[str, Any]) -> str:
    url = str(payload.get("url") or payload.get("canonical_url") or "")
    title = str(payload.get("title") or "")
    description = str(payload.get("description") or payload.get("post_text") or "")
    image = str(payload.get("image_url") or payload.get("image") or "")
    if platform == "facebook":
        return f"https://www.facebook.com/sharer/sharer.php?u={quote_plus(url)}"
    if platform == "linkedin":
        return f"https://www.linkedin.com/sharing/share-offsite/?url={quote_plus(url)}"
    if platform == "twitter":
        text = f"{title} {url}".strip()
        return f"https://twitter.com/intent/tweet?text={quote_plus(text)}"
    if platform == "pinterest":
        return (
            "https://www.pinterest.com/pin/create/button/"
            f"?url={quote_plus(url)}&media={quote_plus(image)}&description={quote_plus(description)}"
        )
    if platform == "bluesky":
        return "https://bsky.app/"
    if platform == "threads":
        return "https://www.threads.net/"
    if platform == "devto":
        return "https://dev.to/new"
    if platform == "medium":
        return "https://medium.com/new-story"
    if platform == "hashnode":
        return "https://hashnode.com/draft"
    if platform == "blogger":
        return "https://www.blogger.com/"
    if platform == "telegram":
        return f"https://t.me/share/url?url={quote_plus(url)}&text={quote_plus(title)}"
    return url


def open_platform_target(platform: str, payload: dict[str, Any], *, open_browser: bool = False) -> str:
    target = platform_target_url(platform, payload)
    if open_browser:
        webbrowser.open(target)
    return target
