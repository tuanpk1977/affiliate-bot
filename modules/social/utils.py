from __future__ import annotations

import json
import re
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


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def slug_from_url(url: str) -> str:
    return url.rstrip("/").split("/")[-1]


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def strip_html(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text)).strip()


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
        "# Social publishing is manual-only. Store credentials outside this file.",
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
        "  mode: browser_hook",
        "  credentials_profile: pinterest",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")

