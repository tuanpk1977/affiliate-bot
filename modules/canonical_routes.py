from __future__ import annotations

import html as html_lib
import json
import re
from pathlib import Path
from urllib.parse import urlparse, urlunparse

from config import settings
from modules.indexing_policy import is_redirect_page, rel_path_for_html, should_include_in_sitemap


BASE_URL = (settings.base_site_url or settings.site_domain or "https://smileaireviewhub.com").rstrip("/")
REDIRECT_BLOCK_START = "# BEGIN AUTO CANONICAL REDIRECTS"
REDIRECT_BLOCK_END = "# END AUTO CANONICAL REDIRECTS"
UTILITY_ROOT_FILES = {"yandex_265dcf14a6c419f2.html"}
ASSET_EXTENSIONS = {
    ".avif",
    ".css",
    ".gif",
    ".ico",
    ".jpeg",
    ".jpg",
    ".js",
    ".json",
    ".map",
    ".mp4",
    ".pdf",
    ".png",
    ".rss",
    ".svg",
    ".txt",
    ".webm",
    ".webp",
    ".xml",
}


def apply_canonical_routing(output: Path) -> dict[str, int]:
    canonical_map = discover_canonical_paths(output)
    canonical_pages = {path for path, info in canonical_map.items() if info["indexable"]}
    changed = 0
    for info in canonical_map.values():
        if normalize_page(info["file"], info["canonical"], canonical_pages):
            changed += 1
    redirects = write_canonical_redirects(output, canonical_map)
    return {
        "canonical_pages": len(canonical_map),
        "canonical_pages_changed": changed,
        "canonical_redirect_rules": redirects,
    }


def discover_canonical_paths(output: Path) -> dict[str, dict[str, object]]:
    pages: dict[str, dict[str, object]] = {}
    for page in sorted(output.rglob("*.html")):
        rel = page.relative_to(output).as_posix()
        if rel in UTILITY_ROOT_FILES or rel.startswith("go/"):
            continue
        if page.name != "index.html":
            index_page = output / rel.removesuffix(".html") / "index.html"
            if index_page.exists():
                continue
        path = rel_path_for_html(page, output)
        if is_redirect_page(path):
            continue
        text = page.read_text(encoding="utf-8", errors="ignore")
        indexable = should_include_in_sitemap(path) and "noindex" not in robots_meta(text).lower() and not has_meta_refresh(text)
        pages[path] = {
            "file": page,
            "canonical": f"{BASE_URL}{path}" if path != "/" else f"{BASE_URL}/",
            "indexable": indexable,
        }
    return pages


def normalize_page(path: Path, canonical: str, canonical_pages: set[str]) -> bool:
    source = path.read_text(encoding="utf-8", errors="ignore")
    updated = ensure_single_canonical(source, canonical)
    updated = replace_url_meta(updated, "property", "og:url", canonical)
    updated = replace_url_meta(updated, "name", "twitter:url", canonical)
    updated = normalize_hreflang(updated)
    updated = normalize_internal_links(updated, canonical_pages)
    updated = normalize_json_ld_urls(updated, canonical)
    if updated != source:
        path.write_text(updated, encoding="utf-8")
        return True
    return False


def ensure_single_canonical(source: str, canonical: str) -> str:
    tag = f'<link rel="canonical" href="{html_lib.escape(canonical, quote=True)}">'
    pattern = r"<link\b(?=[^>]*\brel=['\"]canonical['\"])[^>]*>\s*"
    if re.search(pattern, source, flags=re.I):
        inserted = False

        def replace(match: re.Match[str]) -> str:
            nonlocal inserted
            if inserted:
                return ""
            inserted = True
            return tag + "\n"

        return re.sub(pattern, replace, source, flags=re.I)
    return source.replace("</head>", f"{tag}\n</head>", 1)


def replace_url_meta(source: str, attr: str, name: str, value: str) -> str:
    escaped_name = re.escape(name)
    pattern = rf"(<meta\b(?=[^>]*\b{attr}=['\"]{escaped_name}['\"])[^>]*\bcontent=['\"])[^'\"]*(['\"][^>]*>)"
    if re.search(pattern, source, flags=re.I):
        return re.sub(pattern, rf"\g<1>{html_lib.escape(value, quote=True)}\g<2>", source, count=1, flags=re.I)
    return source


def normalize_hreflang(source: str) -> str:
    def replace(match: re.Match[str]) -> str:
        tag = match.group(0)
        href = html_lib.unescape(match.group(1))
        normalized = canonicalize_url(href)
        return tag.replace(match.group(1), html_lib.escape(normalized, quote=True))

    return re.sub(
        r"<link\b(?=[^>]*\brel=['\"]alternate['\"])(?=[^>]*\bhreflang=['\"][^'\"]+['\"])(?=[^>]*\bhref=['\"]([^'\"]+)['\"])[^>]*>",
        replace,
        source,
        flags=re.I,
    )


def normalize_internal_links(source: str, canonical_pages: set[str]) -> str:
    def replace(match: re.Match[str]) -> str:
        prefix, url, suffix = match.group(1), html_lib.unescape(match.group(2)), match.group(3)
        normalized = canonicalize_internal_href(url, canonical_pages)
        return f"{prefix}{html_lib.escape(normalized, quote=True)}{suffix}"

    return re.sub(r"(\b(?:href|src)=['\"])([^'\"]+)(['\"])", replace, source, flags=re.I)


def normalize_json_ld_urls(source: str, page_canonical: str) -> str:
    def replace(match: re.Match[str]) -> str:
        raw = match.group(1)
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return match.group(0)
        normalized = normalize_json_value(payload, page_canonical)
        return '<script type="application/ld+json">' + json.dumps(normalized, ensure_ascii=False, separators=(",", ":")) + "</script>"

    return re.sub(r"<script\b[^>]*type=['\"]application/ld\+json['\"][^>]*>(.*?)</script>", replace, source, flags=re.I | re.S)


def normalize_json_value(value: object, page_canonical: str) -> object:
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            if key in {"url", "@id", "mainEntityOfPage", "item", "contentUrl", "embedUrl"}:
                result[key] = normalize_schema_url(item, page_canonical)
            else:
                result[key] = normalize_json_value(item, page_canonical)
        return result
    if isinstance(value, list):
        return [normalize_json_value(item, page_canonical) for item in value]
    return value


def normalize_schema_url(value: object, page_canonical: str) -> object:
    if isinstance(value, str):
        return canonicalize_url(value)
    if isinstance(value, dict):
        return normalize_json_value(value, page_canonical)
    return value


def canonicalize_url(url: str) -> str:
    parsed = urlparse(str(url or "").strip())
    if parsed.scheme and parsed.netloc:
        host = parsed.netloc.lower()
        if host != urlparse(BASE_URL).netloc.lower():
            return url
        if should_skip_canonical_path(parsed.path):
            return normalize_asset_url(url)
        path = canonical_path(parsed.path)
        suffix = f"#{parsed.fragment}" if parsed.fragment else ""
        return f"{BASE_URL}{path}{suffix}"
    if str(url).startswith("/"):
        parsed_relative = urlparse(str(url))
        if should_skip_canonical_path(parsed_relative.path):
            return normalize_asset_url(url)
        return canonical_path(url)
    return url


def canonicalize_internal_href(url: str, canonical_pages: set[str]) -> str:
    value = str(url or "")
    if value.startswith(("mailto:", "tel:", "javascript:", "#")):
        return value
    parsed = urlparse(value)
    if parsed.scheme and parsed.netloc:
        if parsed.netloc.lower() != urlparse(BASE_URL).netloc.lower():
            return value
        if should_skip_canonical_path(parsed.path):
            return normalize_asset_url(value)
        path = canonical_path(parsed.path)
        suffix = f"#{parsed.fragment}" if parsed.fragment else ""
        return f"{BASE_URL}{path}{suffix}"
    if not value.startswith("/"):
        return value
    if should_skip_canonical_path(parsed.path):
        return normalize_asset_url(value)
    path = canonical_path(parsed.path)
    if path in canonical_pages or parsed.path.endswith((".html", "index.html")):
        suffix = f"#{parsed.fragment}" if parsed.fragment else ""
        return f"{path}{suffix}"
    return value


def should_skip_canonical_path(path: str) -> bool:
    value = "/" + str(path or "").lstrip("/")
    if value.startswith("/go/"):
        return True
    suffix = Path(value.rstrip("/")).suffix.lower()
    return bool(suffix and suffix != ".html" and suffix in ASSET_EXTENSIONS)


def normalize_asset_url(url: str) -> str:
    parsed = urlparse(str(url or ""))
    if parsed.path.endswith("/"):
        fixed = parsed._replace(path=parsed.path.rstrip("/"))
        return urlunparse(fixed)
    return url


def canonical_path(path: str) -> str:
    value = "/" + str(path or "/").split("?", 1)[0].split("#", 1)[0].strip("/")
    if value == "/":
        return "/"
    if value.endswith("/index.html"):
        value = value[: -len("index.html")]
    elif value.endswith(".html"):
        value = value[: -len(".html")] + "/"
    if not value.endswith("/"):
        value += "/"
    return value


def write_canonical_redirects(output: Path, canonical_map: dict[str, dict[str, object]]) -> int:
    redirects_path = output / "_redirects"
    existing = redirects_path.read_text(encoding="utf-8", errors="ignore") if redirects_path.exists() else ""
    preserved = remove_generated_block(existing).rstrip()
    rules: list[str] = []
    seen: set[str] = set()
    for canonical_path_value, info in sorted(canonical_map.items()):
        if not info["indexable"]:
            continue
        target = canonical_path_value
        alternates = alternate_paths(target)
        for source in alternates:
            if source == target or source in seen:
                continue
            seen.add(source)
            rules.append(f"{source} {target} 301")
    block = "\n".join([REDIRECT_BLOCK_START, *rules, REDIRECT_BLOCK_END])
    final = (preserved + "\n\n" + block + "\n").lstrip()
    redirects_path.write_text(final, encoding="utf-8")
    return len(rules)


def alternate_paths(canonical: str) -> list[str]:
    if canonical == "/":
        return ["/index.html", "/home", "/home/"]
    stem = canonical.rstrip("/")
    return [
        stem,
        f"{stem}.html",
        f"{stem}/index.html",
    ]


def remove_generated_block(text: str) -> str:
    pattern = rf"\n?{re.escape(REDIRECT_BLOCK_START)}.*?{re.escape(REDIRECT_BLOCK_END)}\n?"
    return re.sub(pattern, "\n", text, flags=re.S)


def robots_meta(text: str) -> str:
    match = re.search(r"<meta\b(?=[^>]*\bname=['\"]robots['\"])(?=[^>]*\bcontent=['\"]([^'\"]*)['\"])[^>]*>", text, flags=re.I)
    return match.group(1) if match else ""


def has_meta_refresh(text: str) -> bool:
    return bool(re.search(r"<meta\b[^>]*http-equiv=['\"]?refresh['\"]?", text, flags=re.I))
