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


def prepared_text(payload: dict[str, Any], field: str = "all") -> str:
    if field == "title":
        return str(payload.get("title") or "")
    if field in {"body", "post_body", "post"}:
        return str(payload.get("post_text") or "")
    if field in {"url", "website_url"}:
        return str(payload.get("url") or payload.get("canonical_url") or "")
    if field == "image":
        return str(payload.get("image_url") or payload.get("image") or "")
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
