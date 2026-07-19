from __future__ import annotations

import html
import re
from dataclasses import dataclass
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse


@dataclass(frozen=True)
class PublishedContent:
    title: str
    url: str
    excerpt: str
    content_type: str
    category: str
    published_date: str = ""
    image_url: str = ""


class _PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.h1 = ""
        self.description = ""
        self.canonical = ""
        self.image = ""
        self.published_date = ""
        self._capture = ""
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key.lower(): value or "" for key, value in attrs}
        lower_tag = tag.lower()
        if lower_tag in {"title", "h1", "p"}:
            self._capture = lower_tag
        if lower_tag == "meta":
            name = (values.get("name") or values.get("property") or "").lower()
            if name == "description":
                self.description = values.get("content", "").strip()
            elif name == "og:image":
                self.image = values.get("content", "").strip()
            elif name in {"article:published_time", "date"}:
                self.published_date = values.get("content", "").strip()
        elif lower_tag == "link" and "canonical" in values.get("rel", "").lower():
            self.canonical = values.get("href", "").strip()
        elif lower_tag == "time" and not self.published_date:
            self.published_date = values.get("datetime", "").strip()

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == self._capture:
            self._capture = ""

    def handle_data(self, data: str) -> None:
        value = " ".join(data.split())
        if not value:
            return
        if self._capture == "title" and not self.title:
            self.title = value
        elif self._capture == "h1" and not self.h1:
            self.h1 = value
        elif self._capture == "p":
            self._text.append(value)

    @property
    def first_paragraph(self) -> str:
        return next((item for item in self._text if len(item) >= 40), "")


def discover_published_content(
    published_root: Path,
    *,
    base_url: str,
) -> list[PublishedContent]:
    base = base_url.rstrip("/")
    host = urlparse(base).netloc.lower()
    records: list[PublishedContent] = []
    if not published_root.exists():
        return records

    for source in sorted(published_root.glob("*/index.html")):
        parser = _PageParser()
        try:
            parser.feed(source.read_text(encoding="utf-8"))
        except (OSError, UnicodeError):
            continue
        slug = source.parent.name
        canonical = parser.canonical or f"{base}/{slug}/"
        parsed = urlparse(canonical)
        if parsed.scheme not in {"http", "https"} or parsed.netloc.lower() != host:
            continue
        title = parser.h1 or parser.title.split(" - ")[0].strip() or slug.replace("-", " ").title()
        excerpt = parser.description or parser.first_paragraph
        content_type = classify_content_type(slug, title)
        category = classify_category(slug, title)
        records.append(
            PublishedContent(
                title=title,
                url=canonical,
                excerpt=_clip(excerpt, 180),
                content_type=content_type,
                category=category,
                published_date=_normalise_date(parser.published_date),
                image_url=parser.image,
            )
        )
    return _deduplicate(records)


def content_from_builder_pages(pages: list[dict], *, base_url: str) -> list[PublishedContent]:
    base = base_url.rstrip("/")
    records: list[PublishedContent] = []
    for page in pages:
        slug = str(page.get("slug") or "").strip("/")
        if not slug:
            continue
        title = str(page.get("brand_name") or slug.replace("-", " ").title()).strip()
        url = str(page.get("canonical") or f"{base}/{slug}/").strip()
        records.append(
            PublishedContent(
                title=title,
                url=url,
                excerpt=_clip(str(page.get("description") or ""), 180),
                content_type=classify_content_type(slug, title),
                category=classify_category(slug, title),
                published_date=str(page.get("published_date") or ""),
                image_url=str(page.get("image_url") or ""),
            )
        )
    return _deduplicate(records)


def merge_content(*groups: list[PublishedContent]) -> list[PublishedContent]:
    return _deduplicate([record for group in groups for record in group])


def render_homepage_content_hub(records: list[PublishedContent], *, base_url: str) -> str:
    if not records:
        return (
            "<div class='featured-homepage-sections'><section class='card'><h2>Latest Articles</h2>"
            "<p>New independent AI software reviews and guides are being prepared.</p></section></div>"
        )
    ordered = sorted(records, key=_recency_sort_key, reverse=True)
    sections = [
        ("Featured Reviews", _select(ordered, {"review"}, 6)),
        ("Best AI Tools", _select_best_tools(ordered, 6)),
        ("Latest Comparisons", _select(ordered, {"comparison"}, 6)),
        ("Practical Tutorials", _select(ordered, {"tutorial"}, 6)),
        ("Buying Guides", _select(ordered, {"buying_guide"}, 6)),
        ("Recently Published", ordered[:8]),
    ]
    sections_html = "".join(
        _render_section(title, items, base_url=base_url)
        for title, items in sections
        if items
    )
    return f"<div class='featured-homepage-sections'>{sections_html}</div>"


def available_navigation(records: list[PublishedContent]) -> list[tuple[str, str]]:
    items: list[tuple[str, str]] = [
        ("Reviews", "/reviews/"),
        ("Comparisons", "/comparisons/"),
    ]
    if any(item.content_type == "tutorial" for item in records):
        items.append(("Tutorials", "/blog/"))
    if any(item.content_type == "buying_guide" for item in records):
        items.append(("Buying Guides", "/best-ai-tools/"))
    category_routes = [
        ("Marketing Automation", "marketing_automation", "/category/automation/"),
        ("AI Video", "ai_video", "/category/ai-video-tools/"),
        ("Productivity", "productivity", "/category/automation-tools/"),
    ]
    items.extend(
        (label, route)
        for label, category, route in category_routes
        if any(item.category == category for item in records)
    )
    items.extend([("Latest Articles", "/blog/"), ("About", "/about/")])
    return items


def resolve_related_content(
    current_url: str,
    candidates: list[PublishedContent],
    *,
    max_links: int = 5,
) -> list[PublishedContent]:
    limit = max(0, min(int(max_links), 5))
    current = _normalise_url(current_url)
    current_tokens = _topic_tokens(current)
    current_record = next(
        (item for item in candidates if _normalise_url(item.url) == current),
        None,
    )

    scored: list[tuple[int, str, PublishedContent]] = []
    for item in _deduplicate(candidates):
        if _normalise_url(item.url) == current:
            continue
        parsed = urlparse(item.url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            continue
        tokens = _topic_tokens(f"{item.title} {parsed.path}")
        score = len(current_tokens & tokens) * 4
        if current_record and item.category == current_record.category:
            score += 6
        if current_record and item.content_type != current_record.content_type:
            score += 2
        if score <= 0:
            continue
        scored.append((-score, item.url, item))
    scored.sort(key=lambda row: (row[0], row[1]))
    return [row[2] for row in scored[:limit]]


def render_related_content(items: list[PublishedContent]) -> str:
    if not items:
        return ""
    labels = {
        "comparison": "Related Comparison",
        "tutorial": "Related Tutorial",
        "buying_guide": "Related Buying Guide",
        "review": "Related Article",
    }
    links = "".join(
        "<li><span class='muted'>{label}</span> "
        "<a href='{url}'>{title}</a></li>".format(
            label=html.escape(labels.get(item.content_type, "Related Article")),
            url=html.escape(item.url, quote=True),
            title=html.escape(item.title),
        )
        for item in items
    )
    return f"<section class='card related-content'><h2>Related reading</h2><ul>{links}</ul></section>"


def classify_content_type(slug: str, title: str) -> str:
    value = f"{slug} {title}".lower()
    if "-vs-" in slug.lower() or any(word in value for word in ("comparison", "alternatives")):
        return "comparison"
    if any(word in value for word in ("how to", "tutorial", "workflow", "use cases", "implementation")):
        return "tutorial"
    if any(word in value for word in ("best ", "top ", "buying guide", "pricing", "worth it")):
        return "buying_guide"
    return "review"


def classify_category(slug: str, title: str) -> str:
    value = f"{slug} {title}".lower()
    if any(word in value for word in ("marketing automation", "email marketing", "crm")):
        return "marketing_automation"
    if any(word in value for word in ("video", "synthesia", "runway")):
        return "ai_video"
    if any(word in value for word in ("productivity", "meeting", "workflow", "automation")):
        return "productivity"
    if any(word in value for word in ("coding", "developer", "github", "codex")):
        return "ai_coding"
    return "ai_tools"


def _render_section(title: str, items: list[PublishedContent], *, base_url: str) -> str:
    base_host = urlparse(base_url).netloc.lower()
    cards: list[str] = []
    for item in items:
        image = ""
        if item.image_url and urlparse(item.image_url).netloc.lower() == base_host:
            image = (
                f"<img src='{html.escape(item.image_url, quote=True)}' "
                f"alt='{html.escape(item.title)}' loading='lazy'>"
            )
        date_markup = (
            f"<time datetime='{html.escape(item.published_date, quote=True)}'>"
            f"{html.escape(item.published_date)}</time>"
            if item.published_date
            else ""
        )
        cards.append(
            "<article class='card content-card'>{image}<p class='muted'>{kind} {date}</p>"
            "<h3><a href='{url}'>{title}</a></h3><p>{excerpt}</p></article>".format(
                image=image,
                kind=html.escape(item.content_type.replace("_", " ").title()),
                date=date_markup,
                url=html.escape(item.url, quote=True),
                title=html.escape(item.title),
                excerpt=html.escape(item.excerpt),
            )
        )
    return f"<section class='content-hub-section'><h2>{html.escape(title)}</h2><div class='cards'>{''.join(cards)}</div></section>"


def _select(
    records: list[PublishedContent],
    content_types: set[str],
    limit: int,
) -> list[PublishedContent]:
    return [item for item in records if item.content_type in content_types][:limit]


def _select_best_tools(records: list[PublishedContent], limit: int) -> list[PublishedContent]:
    return [
        item
        for item in records
        if item.content_type in {"review", "buying_guide"}
    ][:limit]


def _deduplicate(records: list[PublishedContent]) -> list[PublishedContent]:
    result: list[PublishedContent] = []
    seen: set[str] = set()
    for record in records:
        key = _normalise_url(record.url)
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(record)
    return result


def _normalise_url(url: str) -> str:
    parsed = urlparse(url)
    path = re.sub(r"/+", "/", parsed.path or "/").rstrip("/") + "/"
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}{path}"


def _topic_tokens(value: str) -> set[str]:
    ignored = {
        "https", "smileaireviewhub", "com", "review", "reviews", "best",
        "2026", "small", "business", "tools", "tool", "software", "article",
    }
    return {
        token
        for token in re.findall(r"[a-z0-9]+", value.lower())
        if len(token) > 2 and token not in ignored
    }


def _normalise_date(value: str) -> str:
    text = value.strip()[:10]
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError:
        return ""


def _recency_sort_key(item: PublishedContent) -> tuple[str, str]:
    return (item.published_date or "0000-00-00", item.url)


def _clip(value: str, limit: int) -> str:
    compact = " ".join(value.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1].rstrip() + "…"
