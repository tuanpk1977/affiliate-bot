from __future__ import annotations

from pathlib import Path
from urllib.parse import urlsplit


SITEMAP_EXCLUDED_PREFIXES = {
    "assets",
    "__pycache__",
    "dashboard",
    "dashboards",
    "go",
    "report",
    "reports",
}

SITEMAP_EXCLUDED_SEGMENTS = {
    "draft",
    "drafts",
    "review",
}

REDIRECT_PATHS = {
    "/semrush-vs-ahrefs-2026/",
    "/vi/semrush-vs-ahrefs-2026/",
}

INDEXABLE_ROBOTS_META = "index,follow,max-image-preview:large"
REDIRECT_ROBOTS_META = "noindex,follow"


def clean_url_path(path: str) -> str:
    value = str(path or "").split("#", 1)[0].split("?", 1)[0].strip()
    if not value:
        return "/"
    if not value.startswith("/"):
        value = "/" + value
    if value.endswith("index.html"):
        value = value[: -len("index.html")]
    if not value.endswith("/"):
        value += "/"
    return value


def rel_path_for_html(path: Path, output: Path) -> str:
    rel = path.relative_to(output).as_posix()
    if rel == "index.html":
        return "/"
    if rel.endswith("/index.html"):
        rel = rel[: -len("index.html")]
    elif rel.endswith(".html"):
        rel = rel[: -len(".html")]
    return clean_url_path(rel)


def is_redirect_page(path: str) -> bool:
    clean = clean_url_path(path)
    if clean in REDIRECT_PATHS:
        return True
    if clean.startswith("/go/"):
        return True
    return False


def is_article_page(path: str) -> bool:
    clean = clean_url_path(path)
    if is_redirect_page(clean):
        return False
    if clean in {"/robots.txt/", "/sitemap.xml/", "/rss.xml/", "/llms.txt/"}:
        return False
    return True


def robots_meta_for_path(path: str) -> str:
    return REDIRECT_ROBOTS_META if is_redirect_page(path) else INDEXABLE_ROBOTS_META


def should_include_in_sitemap(path: str) -> bool:
    if is_redirect_page(path):
        return False
    clean = clean_url_path(path).strip("/")
    first = clean.split("/", 1)[0] if clean else ""
    if first in SITEMAP_EXCLUDED_PREFIXES:
        return False
    if any(segment in SITEMAP_EXCLUDED_SEGMENTS for segment in clean.split("/") if segment):
        return False
    return True


def is_public_sitemap_base_url(base_url: str) -> bool:
    parsed = urlsplit(str(base_url or "").strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return False
    hostname = parsed.hostname.lower().rstrip(".")
    return hostname not in {"localhost", "127.0.0.1", "::1"}
