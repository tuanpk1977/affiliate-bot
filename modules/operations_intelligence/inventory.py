from __future__ import annotations

import json
import re
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse


PUBLIC_BASE_URL = "https://smileaireviewhub.com/"
WORKFLOW_MARKERS = {
    "approved_for_publish",
    "human_approved",
    "needs_human_review",
    "publish blocked",
    "published_local",
    "ready for publish",
}


def read_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return default


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", unescape(value or "")).strip()


def canonical_for_slug(slug: str) -> str:
    return urljoin(PUBLIC_BASE_URL, f"{slug.strip('/')}/")


class ArticleHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.canonical = ""
        self.description = ""
        self.robots = ""
        self.headings: list[dict[str, str]] = []
        self.paragraphs: list[str] = []
        self.links: list[dict[str, str]] = []
        self.images: list[dict[str, str]] = []
        self.schemas: list[dict[str, Any]] = []
        self._skip_depth = 0
        self._capture = ""
        self._buffer: list[str] = []
        self._href = ""
        self._schema_buffer: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {key.casefold(): value or "" for key, value in attrs}
        if tag in {"nav", "footer", "script", "style"}:
            if tag == "script" and attributes.get("type", "").casefold() == "application/ld+json":
                self._capture = "schema"
                self._schema_buffer = []
                return
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if tag == "link" and attributes.get("rel", "").casefold() == "canonical":
            self.canonical = attributes.get("href", "").strip()
        elif tag == "meta":
            name = attributes.get("name", "").casefold()
            if name == "description":
                self.description = attributes.get("content", "").strip()
            elif name == "robots":
                self.robots = attributes.get("content", "").strip()
        elif tag in {"title", "h1", "h2", "h3", "p"}:
            self._capture = tag
            self._buffer = []
        elif tag == "a":
            self._capture = "a"
            self._buffer = []
            self._href = attributes.get("href", "").strip()
        elif tag == "img":
            self.images.append(
                {
                    key: attributes.get(key, "")
                    for key in ("src", "alt", "width", "height", "decoding")
                }
            )

    def handle_data(self, data: str) -> None:
        if self._capture == "schema":
            self._schema_buffer.append(data)
        elif not self._skip_depth and self._capture:
            self._buffer.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self._capture == "schema" and tag == "script":
            try:
                payload = json.loads("".join(self._schema_buffer))
                if isinstance(payload, dict):
                    self.schemas.append(payload)
                elif isinstance(payload, list):
                    self.schemas.extend(item for item in payload if isinstance(item, dict))
            except json.JSONDecodeError:
                pass
            self._capture = ""
            self._schema_buffer = []
            return
        if tag in {"nav", "footer", "script", "style"}:
            self._skip_depth = max(0, self._skip_depth - 1)
            return
        if self._skip_depth or tag != self._capture:
            return
        text = normalize_space("".join(self._buffer))
        if tag == "title":
            self.title = text
        elif tag in {"h1", "h2", "h3"} and text:
            self.headings.append({"level": tag, "text": text})
        elif tag == "p" and text:
            self.paragraphs.append(text)
        elif tag == "a" and self._href:
            self.links.append({"href": self._href, "text": text})
        self._capture = ""
        self._buffer = []
        self._href = ""


def parse_html(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return {"path": str(path), "read_error": True}
    parser = ArticleHTMLParser()
    try:
        parser.feed(raw)
    except Exception:
        return {"path": str(path), "parse_error": True, "raw": raw}
    return {
        "path": str(path),
        "raw": raw,
        "title": parser.title,
        "canonical": parser.canonical,
        "description": parser.description,
        "robots": parser.robots,
        "headings": parser.headings,
        "paragraphs": parser.paragraphs,
        "links": parser.links,
        "images": parser.images,
        "schemas": parser.schemas,
    }


def schema_types(schemas: list[dict[str, Any]]) -> set[str]:
    output: set[str] = set()
    stack: list[Any] = list(schemas)
    while stack:
        item = stack.pop()
        if isinstance(item, dict):
            raw_type = item.get("@type")
            if isinstance(raw_type, str):
                output.add(raw_type)
            elif isinstance(raw_type, list):
                output.update(str(value) for value in raw_type)
            stack.extend(item.values())
        elif isinstance(item, list):
            stack.extend(item)
    return output


def internal_slug(url: str) -> str:
    parsed = urlparse(urljoin(PUBLIC_BASE_URL, url))
    if (parsed.hostname or "").casefold().removeprefix("www.") != "smileaireviewhub.com":
        return ""
    path = parsed.path.strip("/")
    if not path or path.startswith(("review/", "draft/", "dashboard/", "reports/")):
        return ""
    return path.split("/")[0] if not path.startswith("vi/") else "/".join(path.split("/")[:2])


def article_inventory(root: Path) -> list[dict[str, Any]]:
    root = root.resolve()
    draft_root = root / "data" / "production_article_drafts"
    published_root = root / "data" / "published_static_pages"
    docs_root = root / "docs"
    slugs: set[str] = set()
    for base in (draft_root, published_root):
        if base.exists():
            slugs.update(path.parent.name for path in base.glob("*/metadata.json"))
            slugs.update(path.parent.name for path in base.glob("*/index.html"))
    if docs_root.exists():
        slugs.update(
            path.parent.name
            for path in docs_root.glob("*/index.html")
            if path.parent.name not in {"review", "draft", "dashboard", "reports", "assets"}
        )

    records: list[dict[str, Any]] = []
    for slug in sorted(slugs):
        draft_dir = draft_root / slug
        published_dir = published_root / slug
        metadata = read_json(draft_dir / "metadata.json", {})
        if not isinstance(metadata, dict) or not metadata:
            metadata = read_json(published_dir / "metadata.json", {})
        if not isinstance(metadata, dict):
            metadata = {}
        docs_html = docs_root / slug / "index.html"
        public_html = docs_html if docs_html.is_file() else published_dir / "index.html"
        parsed = parse_html(public_html) if public_html.is_file() else {}
        records.append(
            {
                "slug": slug,
                "title": str(metadata.get("title") or parsed.get("title") or slug),
                "canonical": str(
                    metadata.get("canonical_url")
                    or metadata.get("canonical")
                    or parsed.get("canonical")
                    or canonical_for_slug(slug)
                ),
                "batch_date": str(
                    metadata.get("batch_date")
                    or metadata.get("date")
                    or metadata.get("published_at")
                    or ""
                ),
                "root_topic_id": str(metadata.get("root_topic_id") or ""),
                "daily_angle": str(metadata.get("daily_angle") or metadata.get("article_type") or ""),
                "editorial_state": str(
                    metadata.get("editorial_state")
                    or metadata.get("editorial_status")
                    or metadata.get("status")
                    or ""
                ),
                "metadata": metadata,
                "draft_dir": str(draft_dir),
                "published_dir": str(published_dir),
                "docs_path": str(docs_html),
                "is_published_local": docs_html.is_file() and public_html.is_file(),
                "html": parsed,
            }
        )
    return records

