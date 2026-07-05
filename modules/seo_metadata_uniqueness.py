from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import html as html_lib
import re
from pathlib import Path

from modules.facebook_meta import upsert_meta_name, upsert_meta_property
from modules.seo_title_optimizer import shorten_title


GENERIC_TITLES = {
    "",
    "MS Smile AI Review Hub",
    "Home",
    "Untitled",
    "Thông tin cần kiểm tra",
    "Ghi chú đánh giá",
    "Bản dịch tiếng Việt",
    "Tóm tắt bài viết",
    "Bài viết",
    "Trang",
}

GENERIC_DESCRIPTION_FRAGMENTS = (
    "ai and saas tool reviews",
    "research purposes only",
    "bản tiếng việt",
    "thông tin cần kiểm tra",
    "ghi chú đánh giá",
    "placeholder",
    "read the full review",
    "visit official website",
    "verify current pricing",
    "no content yet",
)

ACRONYM_MAP = {
    "ai": "AI",
    "seo": "SEO",
    "api": "API",
    "ui": "UI",
    "ux": "UX",
    "llm": "LLM",
    "gsc": "GSC",
    "rss": "RSS",
    "url": "URL",
    "csv": "CSV",
    "json": "JSON",
    "youtube": "YouTube",
    "github": "GitHub",
    "google": "Google",
    "bing": "Bing",
    "yandex": "Yandex",
}


@dataclass(slots=True)
class PageRecord:
    path: Path
    rel_url: str
    lang: str
    title: str
    description: str
    h1: str
    text: str


def rewrite_duplicate_metadata(output: Path) -> dict[str, int]:
    pages = [page for page in sorted(output.rglob("*.html")) if not should_skip(page)]
    records = [read_record(output, page) for page in pages]
    title_counts = Counter(normalize_value(record.title) for record in records if record.title)
    desc_counts = Counter(normalize_value(record.description) for record in records if record.description)

    used_titles: set[str] = set()
    used_descriptions: set[str] = set()
    pages_changed = 0
    titles_changed = 0
    descriptions_changed = 0

    for record in records:
        original_text = record.text
        title = record.title
        description = record.description

        title_key = normalize_value(title)
        desc_key = normalize_value(description)
        needs_title = is_generic_title(title) or not title or title_counts[title_key] > 1
        needs_description = is_generic_description(description) or not description or desc_counts[desc_key] > 1

        if needs_title:
            title = build_unique_title(record, used_titles)
            if title != record.title:
                titles_changed += 1
        else:
            used_titles.add(title)

        if needs_description:
            description = build_unique_description(record, title, used_descriptions)
            if description != record.description:
                descriptions_changed += 1
        else:
            used_descriptions.add(description)

        updated_text = apply_metadata(record.text, title, description)
        if updated_text != original_text:
            record.path.write_text(updated_text, encoding="utf-8")
            pages_changed += 1

    return {
        "pages": len(records),
        "pages_changed": pages_changed,
        "titles_changed": titles_changed,
        "descriptions_changed": descriptions_changed,
    }


def should_skip(page: Path) -> bool:
    rel_parts = page.parts
    skip_prefixes = {"assets", "go", "__pycache__"}
    for part in rel_parts:
        if part in skip_prefixes:
            return True
    return False


def read_record(output: Path, page: Path) -> PageRecord:
    text = page.read_text(encoding="utf-8", errors="ignore")
    rel_url = page.relative_to(output).as_posix()
    if rel_url == "index.html":
        rel_path = "/"
    elif rel_url.endswith("/index.html"):
        rel_path = "/" + rel_url[: -len("index.html")].rstrip("/")
        rel_path = rel_path + "/"
    else:
        rel_path = "/" + rel_url.lstrip("/")
    title = extract_title(text)
    description = extract_description(text)
    h1 = extract_h1(text)
    lang = "vi" if "/vi/" in rel_path else "en"
    return PageRecord(page, rel_path, lang, title, description, h1, text)


def apply_metadata(text: str, title: str, description: str) -> str:
    updated = upsert_title(text, title)
    updated = upsert_meta_name(updated, "description", description)
    updated = upsert_meta_property(updated, "og:title", title)
    updated = upsert_meta_property(updated, "og:description", description)
    updated = upsert_meta_name(updated, "twitter:title", title)
    updated = upsert_meta_name(updated, "twitter:description", description)
    return updated


def build_unique_title(record: PageRecord, used_titles: set[str]) -> str:
    base = clean_text(record.h1) or clean_text(record.title) or humanize_url(record.rel_url)
    if record.lang == "vi" and "tiếng việt" not in base.lower():
        base = f"{base} | Tiếng Việt"
    base = shorten_title(base, 60)
    candidate = unique_value(base, used_titles, record.rel_url, record.lang, is_title=True)
    used_titles.add(candidate)
    return candidate


def build_unique_description(record: PageRecord, title: str, used_descriptions: set[str]) -> str:
    title_base = clean_text(title).replace(" | Tiếng Việt", "").replace(" - Tiếng Việt", "")
    if record.lang == "vi":
        base = (
            f"Đọc {title_base}. So sánh tính năng, giá, ưu điểm, nhược điểm, lựa chọn thay thế và liên kết chính thức."
        )
    else:
        base = (
            f"Read {title_base}. Compare features, pricing, pros, cons, alternatives, and official links."
        )
    base = shorten_description(base)
    candidate = unique_value(base, used_descriptions, record.rel_url, record.lang, is_title=False)
    used_descriptions.add(candidate)
    return candidate


def unique_value(base: str, used: set[str], rel_url: str, lang: str, is_title: bool) -> str:
    candidate = base.strip()
    if candidate and candidate not in used:
        return candidate
    hint = page_hint(rel_url)
    suffix = " | Tiếng Việt" if lang == "vi" and is_title else ""
    if candidate and suffix and not candidate.endswith(suffix):
        candidate = shorten_title(f"{candidate}{suffix}", 60) if is_title else f"{candidate} Bản tiếng Việt."
    if candidate and candidate not in used:
        return candidate
    if is_title:
        candidate = shorten_title(f"{base} | {hint}", 60)
    else:
        candidate = shorten_description(f"{base} ({hint}).")
    if candidate not in used:
        return candidate
    index = 2
    while True:
        if is_title:
            candidate = shorten_title(f"{base} | {hint} {index}", 60)
        else:
            candidate = shorten_description(f"{base} ({hint} {index}).")
        if candidate not in used:
            return candidate
        index += 1


def page_hint(rel_url: str) -> str:
    parts = [part for part in rel_url.strip("/").split("/") if part and part != "vi"]
    if not parts:
        return "Home"
    hint = humanize_slug(parts[-1])
    return hint or "Page"


def extract_title(text: str) -> str:
    match = re.search(r"<title\b[^>]*>(.*?)</title>", text, flags=re.I | re.S)
    return clean_text(match.group(1) if match else "")


def extract_description(text: str) -> str:
    match = re.search(r"<meta\b(?=[^>]*\bname=['\"]description['\"])[^>]*\bcontent=['\"]([^'\"]*)['\"][^>]*>", text, flags=re.I | re.S)
    return clean_text(match.group(1) if match else "")


def extract_h1(text: str) -> str:
    match = re.search(r"<h1\b[^>]*>(.*?)</h1>", text, flags=re.I | re.S)
    return clean_text(match.group(1) if match else "")


def is_generic_title(value: str) -> bool:
    cleaned = clean_text(value)
    return cleaned in GENERIC_TITLES or len(cleaned) < 8


def is_generic_description(value: str) -> bool:
    cleaned = normalize_value(value)
    if not cleaned or len(cleaned) < 25:
        return True
    return any(fragment in cleaned for fragment in GENERIC_DESCRIPTION_FRAGMENTS)


def normalize_value(value: str) -> str:
    return re.sub(r"\s+", " ", clean_text(value)).strip().lower()


def clean_text(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value or "")
    value = html_lib.unescape(value)
    return re.sub(r"\s+", " ", value).strip()


def humanize_url(value: str) -> str:
    parts = [part for part in value.strip("/").split("/") if part and part != "vi"]
    if not parts:
        return "MS Smile AI Review Hub"
    return humanize_slug(parts[-1])


def humanize_slug(value: str) -> str:
    words = [word for word in re.split(r"[-_]+", value) if word]
    if not words:
        return "Page"
    normalized = []
    for word in words:
        lower = word.lower()
        if lower in ACRONYM_MAP:
            normalized.append(ACRONYM_MAP[lower])
        elif lower == "vs":
            normalized.append("vs")
        else:
            normalized.append(word[:1].upper() + word[1:])
    return " ".join(normalized)


def shorten_description(value: str, max_length: int = 155) -> str:
    text = clean_text(value)
    if len(text) <= max_length:
        return text
    shortened = text[: max_length + 1].rsplit(" ", 1)[0].rstrip(" ,:;|-")
    if len(shortened) < 40:
        shortened = text[:max_length].rstrip(" ,:;|-")
    return shortened


def upsert_title(text: str, title: str) -> str:
    escaped = html_lib.escape(title, quote=False)
    pattern = r"(<title\b[^>]*>).*?(</title>)"
    if re.search(pattern, text, flags=re.I | re.S):
        return re.sub(pattern, rf"\g<1>{escaped}\g<2>", text, count=1, flags=re.I | re.S)
    if "</head>" in text:
        return text.replace("</head>", f"<title>{escaped}</title>\n</head>", 1)
    return f"<title>{escaped}</title>\n{text}"
