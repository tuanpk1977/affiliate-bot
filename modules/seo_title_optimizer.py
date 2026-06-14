from __future__ import annotations

import html as html_lib
import re
from pathlib import Path


MAX_TITLE_LENGTH = 60
SITE_NAME_SUFFIXES = (
    " - MS Smile AI Review Hub",
    " | MS Smile AI Review Hub",
)
TRAILING_STOP_WORDS = {
    "a",
    "an",
    "and",
    "for",
    "in",
    "of",
    "or",
    "the",
    "to",
    "vs",
    "cho",
    "của",
    "hoặc",
    "năm",
    "trong",
    "và",
    "với",
}


def clean_text(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value or "")
    return re.sub(r"\s+", " ", html_lib.unescape(value)).strip()


def shorten_title(value: str, max_length: int = MAX_TITLE_LENGTH) -> str:
    title = clean_text(value)
    for suffix in SITE_NAME_SUFFIXES:
        if title.endswith(suffix):
            title = title[: -len(suffix)].rstrip()
            break
    title = title.replace("Which Tool Should You Choose in 2026?", "Which Is Better in 2026?")
    title = title.replace("Nên chọn công cụ nào trong năm 2026?", "Nên chọn công cụ nào năm 2026?")
    title = title.replace("Research-Style Review for", "Research Review:")
    if len(title) <= max_length:
        return title

    keep_year = title.rstrip("?!., ").endswith("2026") and "2026" not in title[:max_length]
    limit = max_length - 5 if keep_year else max_length
    shortened = title[: limit + 1].rsplit(" ", 1)[0].rstrip(" ,:;|-")
    while shortened and shortened.rstrip("?!., ").split()[-1].lower() in TRAILING_STOP_WORDS:
        shortened = shortened.rsplit(" ", 1)[0].rstrip(" ,:;|-")
    if len(shortened) < 30:
        shortened = title[:limit].rstrip(" ,:;|-")
    if keep_year:
        shortened = f"{shortened} 2026"
    return shortened


def has_trailing_stop_word(value: str) -> bool:
    words = clean_text(value).rstrip("?!., ").split()
    return bool(words and words[-1].lower() in TRAILING_STOP_WORDS)


def optimize_html_title(source: str, max_length: int = MAX_TITLE_LENGTH) -> tuple[str, bool]:
    title_match = re.search(r"<title\b[^>]*>(.*?)</title>", source, flags=re.I | re.S)
    if not title_match:
        return source, False

    current_title = clean_text(title_match.group(1))
    h1_match = re.search(r"<h1\b[^>]*>(.*?)</h1>", source, flags=re.I | re.S)
    h1 = clean_text(h1_match.group(1)) if h1_match else ""
    candidate = h1 if h1 and (len(current_title) > max_length or has_trailing_stop_word(current_title)) else current_title
    optimized = shorten_title(candidate, max_length)
    if not optimized:
        return source, False

    escaped = html_lib.escape(optimized, quote=False)
    updated = re.sub(
        r"(<title\b[^>]*>).*?(</title>)",
        rf"\g<1>{escaped}\g<2>",
        source,
        count=1,
        flags=re.I | re.S,
    )
    for property_name in ("og:title", "twitter:title"):
        updated = re.sub(
            rf"(<meta\b(?=[^>]*(?:property|name)=['\"]{re.escape(property_name)}['\"])[^>]*\bcontent=['\"])[^'\"]*(['\"][^>]*>)",
            rf"\g<1>{html_lib.escape(optimized, quote=True)}\g<2>",
            updated,
            count=1,
            flags=re.I,
        )
    return updated, updated != source


def optimize_site_titles(output: Path, max_length: int = MAX_TITLE_LENGTH) -> dict[str, int]:
    pages = 0
    changed = 0
    remaining_long = 0
    for page in sorted(output.rglob("*.html")):
        pages += 1
        source = page.read_text(encoding="utf-8", errors="ignore")
        updated, was_changed = optimize_html_title(source, max_length)
        if was_changed:
            page.write_text(updated, encoding="utf-8")
            changed += 1
        match = re.search(r"<title\b[^>]*>(.*?)</title>", updated, flags=re.I | re.S)
        if match and len(clean_text(match.group(1))) > max_length:
            remaining_long += 1
    return {"pages": pages, "changed": changed, "remaining_long": remaining_long}
