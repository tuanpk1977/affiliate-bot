from __future__ import annotations

from pathlib import Path


SITEMAP_EXCLUDED_PREFIXES = {
    "assets",
    "__pycache__",
    "go",
}


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
    localized = clean[3:] if clean.startswith("/vi/") else clean
    if clean.startswith("/go/"):
        return True
    if localized.startswith("/reviews/") and localized.count("/") >= 3:
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
    return "noindex,follow" if is_redirect_page(path) else "index,follow"


def should_include_in_sitemap(path: str) -> bool:
    if is_redirect_page(path):
        return False
    clean = clean_url_path(path).strip("/")
    first = clean.split("/", 1)[0] if clean else ""
    if first in SITEMAP_EXCLUDED_PREFIXES:
        return False
    return True
