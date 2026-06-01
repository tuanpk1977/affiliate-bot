from __future__ import annotations

import html
import re
from pathlib import Path

from config import settings


BASE_URL = (settings.base_site_url or settings.site_domain or "https://smileaireviewhub.com").rstrip("/")
OG_IMAGE_PATH = "/assets/og/site.png"
OG_IMAGE_URL = f"{BASE_URL}{OG_IMAGE_PATH}"


def post_process_facebook_meta(output: Path, base_url: str | None = None) -> dict[str, int]:
    base = (base_url or BASE_URL).rstrip("/")
    pages = 0
    changed = 0
    for page in output.rglob("index.html"):
        pages += 1
        url = canonical_url_for_page(page, output, base)
        text = page.read_text(encoding="utf-8", errors="ignore")
        updated = ensure_open_graph_tags(text, url)
        if updated != text:
            page.write_text(updated, encoding="utf-8")
            changed += 1
    return {"pages": pages, "changed": changed}


def canonical_url_for_page(page: Path, output: Path, base: str) -> str:
    rel = page.relative_to(output).as_posix()
    if rel == "index.html":
        return f"{base}/"
    if rel.endswith("/index.html"):
        rel = rel[: -len("index.html")]
    return f"{base}/{rel.lstrip('/')}"


def ensure_open_graph_tags(text: str, url: str) -> str:
    title = first_match(text, r"<title>(.*?)</title>") or "MS Smile AI Review Hub"
    title = re.sub(r"\s+", " ", html.unescape(strip_tags(title))).strip()
    description = first_match(text, r"<meta\s+name=['\"]description['\"]\s+content=['\"]([^'\"]*)['\"][^>]*>")
    description = html.unescape(description or "AI and SaaS tool reviews, comparisons, pricing research, and workflow guidance.")

    text = upsert_meta_property(text, "og:title", title)
    text = upsert_meta_property(text, "og:description", description)
    text = upsert_meta_property(text, "og:url", url)
    text = upsert_meta_property(text, "og:type", "website" if url.rstrip("/") == BASE_URL else "article")
    text = upsert_meta_property(text, "og:image", OG_IMAGE_URL)
    text = upsert_meta_property(text, "og:image:secure_url", OG_IMAGE_URL)
    text = upsert_meta_property(text, "og:image:type", "image/png")
    text = upsert_meta_property(text, "og:image:width", "1200")
    text = upsert_meta_property(text, "og:image:height", "630")
    text = upsert_meta_name(text, "twitter:card", "summary_large_image")
    text = upsert_meta_name(text, "twitter:image", OG_IMAGE_URL)
    return text


def upsert_meta_property(text: str, prop: str, content: str) -> str:
    escaped = html.escape(content, quote=True)
    pattern = re.compile(rf"<meta\s+property=['\"]{re.escape(prop)}['\"]\s+content=['\"][^'\"]*['\"]\s*/?>", re.I)
    tag = f'<meta property="{prop}" content="{escaped}">'
    if pattern.search(text):
        return pattern.sub(tag, text, count=1)
    return insert_before_head_end(text, tag)


def upsert_meta_name(text: str, name: str, content: str) -> str:
    escaped = html.escape(content, quote=True)
    pattern = re.compile(rf"<meta\s+name=['\"]{re.escape(name)}['\"]\s+content=['\"][^'\"]*['\"]\s*/?>", re.I)
    tag = f'<meta name="{name}" content="{escaped}">'
    if pattern.search(text):
        return pattern.sub(tag, text, count=1)
    return insert_before_head_end(text, tag)


def insert_before_head_end(text: str, tag: str) -> str:
    if "</head>" in text:
        return text.replace("</head>", f"  {tag}\n</head>", 1)
    return text + "\n" + tag + "\n"


def first_match(text: str, pattern: str) -> str:
    match = re.search(pattern, text, flags=re.I | re.S)
    return match.group(1) if match else ""


def strip_tags(value: str) -> str:
    return re.sub(r"<[^>]+>", "", value)
