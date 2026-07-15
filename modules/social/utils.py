from __future__ import annotations

import json
import re
from html import unescape
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
CONFIG_PATH = ROOT / "config" / "social_publish.yaml"
STATUS_PATH = DATA_DIR / "social_publish_status.csv"
LOG_DIR = ROOT / "logs" / "social"


PLATFORMS = [
    "pinterest",
    "facebook",
    "linkedin",
    "twitter",
    "bluesky",
    "threads",
    "devto",
    "medium",
    "hashnode",
    "blogger",
    "telegram",
]


@dataclass(frozen=True)
class PublishedArticle:
    article_id: str
    title: str
    url: str
    description: str
    image: str
    tags: list[str]
    publish_date: str
    canonical_url: str = ""
    og_title: str = ""
    og_description: str = ""
    og_image: str = ""
    summary: str = ""
    headings: list[str] | None = None
    key_points: list[str] | None = None
    affiliate_disclosure: str = ""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def slug_from_url(url: str) -> str:
    return url.rstrip("/").split("/")[-1]


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def strip_html(text: str) -> str:
    return unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text)).strip())


def extract_meta(html: str, name: str) -> str:
    patterns = [
        rf'<meta\s+name=["\']{re.escape(name)}["\']\s+content=["\']([^"\']+)["\']',
        rf'<meta\s+property=["\']{re.escape(name)}["\']\s+content=["\']([^"\']+)["\']',
        rf'<meta\s+content=["\']([^"\']+)["\']\s+(?:name|property)=["\']{re.escape(name)}["\']',
    ]
    for pattern in patterns:
        match = re.search(pattern, html, flags=re.I)
        if match:
            return match.group(1).strip()
    return ""


def extract_title(html: str) -> str:
    og_title = extract_meta(html, "og:title")
    if og_title:
        return og_title
    match = re.search(r"<title[^>]*>(.*?)</title>", html, flags=re.I | re.S)
    return strip_html(match.group(1)) if match else ""


def extract_canonical(html: str) -> str:
    match = re.search(r'<link\s+[^>]*rel=["\']canonical["\'][^>]*href=["\']([^"\']+)["\']', html, flags=re.I)
    if not match:
        match = re.search(r'<link\s+[^>]*href=["\']([^"\']+)["\'][^>]*rel=["\']canonical["\']', html, flags=re.I)
    return match.group(1).strip() if match else ""


def extract_publish_date(html: str) -> str:
    for key in ("article:published_time", "datePublished", "publish_date", "pubdate"):
        value = extract_meta(html, key)
        if value:
            return value
    match = re.search(r'"datePublished"\s*:\s*"([^"]+)"', html, flags=re.I)
    return match.group(1).strip() if match else ""


def extract_headings(html: str, limit: int = 8) -> list[str]:
    headings = []
    for match in re.finditer(r"<h[2-3][^>]*>(.*?)</h[2-3]>", html, flags=re.I | re.S):
        text = strip_html(match.group(1))
        if text and text not in headings:
            headings.append(text)
        if len(headings) >= limit:
            break
    return headings


def extract_paragraphs(html: str, limit: int = 12) -> list[str]:
    paragraphs = []
    for match in re.finditer(r"<p[^>]*>(.*?)</p>", html, flags=re.I | re.S):
        text = strip_html(match.group(1))
        if len(text) < 40:
            continue
        if text not in paragraphs:
            paragraphs.append(text)
        if len(paragraphs) >= limit:
            break
    return paragraphs


def extract_article_summary(html: str, description: str) -> str:
    paragraphs = extract_paragraphs(html, limit=3)
    if paragraphs:
        return " ".join(paragraphs)[:900].strip()
    return description


def extract_affiliate_disclosure(html: str) -> str:
    lowered = html.lower()
    if "affiliate disclosure" not in lowered and "affiliate links" not in lowered:
        return ""
    paragraphs = extract_paragraphs(html, limit=20)
    for paragraph in paragraphs:
        if "affiliate" in paragraph.lower():
            return paragraph[:500].strip()
    return "Some links may be affiliate links. The article remains independent research."


def extract_tags(title: str, description: str) -> list[str]:
    text = f"{title} {description}".lower()
    tags = ["AI Tools"]
    for keyword, tag in [
        ("coding", "AI Coding"),
        ("agent", "AI Agents"),
        ("automation", "AI Automation"),
        ("openai", "OpenAI"),
        ("claude", "Claude AI"),
        ("cursor", "Cursor AI"),
        ("windsurf", "Windsurf IDE"),
        ("comparison", "AI Tools Comparison"),
        ("alternative", "AI Tools Comparison"),
    ]:
        if keyword in text and tag not in tags:
            tags.append(tag)
    return tags[:6]


def load_simple_yaml(path: Path = CONFIG_PATH) -> dict[str, Any]:
    if not path.exists():
        return {}
    result: dict[str, Any] = {}
    stack: list[tuple[int, dict[str, Any]]] = [(-1, result)]
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(" "))
        if ":" not in line:
            continue
        key, value = line.strip().split(":", 1)
        value = value.strip()
        while stack and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]
        if not value:
            child: dict[str, Any] = {}
            parent[key] = child
            stack.append((indent, child))
            continue
        lowered = value.lower()
        if lowered in {"true", "false"}:
            parsed: Any = lowered == "true"
        else:
            parsed = value.strip('"\'')
        parent[key] = parsed
    return result


def ensure_default_config(path: Path = CONFIG_PATH) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Social publishing is manual-only. Do not store secrets in this file.",
        "platforms:",
        "  pinterest: true",
        "  facebook: false",
        "  linkedin: false",
        "  twitter: false",
        "  bluesky: false",
        "  threads: false",
        "  devto: false",
        "  medium: false",
        "  hashnode: false",
        "  blogger: false",
        "  telegram: false",
        "pinterest:",
        "  mode: manual_assisted",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
