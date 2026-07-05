from __future__ import annotations

import html
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from modules.content_writer import generate_article_package, generate_article_markdown
from modules.morning_dashboard import ARTICLE_DRAFT_DAILY_FIELDS, PUBLISHED_TODAY_FIELDS
from modules.performance_tracking import BASE_URL, DATA_DIR, ROOT, read_csv, slugify, write_csv, write_json
from modules.site_builder import page_shell


PUBLISHED_SOURCE_DIR = DATA_DIR / "published_static_pages"
PREVIEW_DIR = ROOT / "draft_output" / "article_previews"

PUBLISH_REPORT_FIELDS = PUBLISHED_TODAY_FIELDS


def _inline_markdown(text: str) -> str:
    text = html.escape(text)
    text = re.sub(r"\*\*(.*?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"\[(.*?)\]\((.*?)\)", r'<a href="\2">\1</a>', text)
    return text


def _image_markdown(line: str) -> str | None:
    match = re.match(r"^!\[(.*?)\]\((.*?)\)$", line.strip())
    if not match:
        return None
    alt = html.escape(match.group(1).strip())
    src = html.escape(match.group(2).strip(), quote=True)
    return (
        "<figure class='card'>"
        f"<img src='{src}' alt='{alt}' loading='lazy' decoding='async' "
        "style='display:block;width:100%;height:auto;border-radius:8px;border:1px solid #dbe3ef'>"
        f"<figcaption>{alt}</figcaption>"
        "</figure>"
    )


def markdown_to_html(markdown: str, internal_links: list[dict[str, Any]] | None = None) -> str:
    lines = markdown.splitlines()
    body: list[str] = []
    in_list = False
    in_table = False
    table_rows: list[str] = []

    def close_list() -> None:
        nonlocal in_list
        if in_list:
            body.append("</ul>")
            in_list = False

    def close_table() -> None:
        nonlocal in_table, table_rows
        if in_table:
            body.append("<table>" + "".join(table_rows) + "</table>")
            in_table = False
            table_rows = []

    for raw in lines:
        line = raw.rstrip()
        if not line or line == "---" or re.match(r"^(title|slug|date|status|canonical):\s+", line, re.I):
            continue
        if line.startswith("|") and line.endswith("|"):
            close_list()
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            if all(set(cell) <= {"-"} for cell in cells):
                continue
            tag = "th" if not in_table else "td"
            table_rows.append("<tr>" + "".join(f"<{tag}>{_inline_markdown(cell)}</{tag}>" for cell in cells) + "</tr>")
            in_table = True
            continue
        close_table()
        image_html = _image_markdown(line)
        if image_html:
            close_list()
            body.append(image_html)
            continue
        if line.startswith("# "):
            close_list()
            body.append(f"<h1>{_inline_markdown(line[2:].strip())}</h1>")
        elif line.startswith("## "):
            close_list()
            body.append(f"<h2>{_inline_markdown(line[3:].strip())}</h2>")
        elif line.startswith("### "):
            close_list()
            body.append(f"<h3>{_inline_markdown(line[4:].strip())}</h3>")
        elif line.startswith("- "):
            if not in_list:
                body.append("<ul>")
                in_list = True
            body.append(f"<li>{_inline_markdown(line[2:].strip())}</li>")
        else:
            close_list()
            body.append(f"<p>{_inline_markdown(line)}</p>")
    close_list()
    close_table()

    if internal_links:
        body.append("<section class='card'><h2>Related reading</h2><ul>")
        for link in internal_links[:12]:
            target = html.escape(str(link.get("target_url", "")), quote=True)
            anchor = html.escape(str(link.get("anchor_text", "")))
            if target and anchor:
                body.append(f"<li><a href='{target}'>{anchor}</a></li>")
        body.append("</ul></section>")
    return "\n".join(body)


def article_schema(row: dict[str, Any]) -> str:
    title = str(row.get("topic") or row.get("suggested_title") or "").strip()
    slug = slugify(row.get("slug") or title)
    schema = {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": title,
        "description": f"Independent guide to {title}, pricing, pros, cons, alternatives, and buyer fit.",
        "author": {"@type": "Person", "name": "Tuan Nguyen Quoc"},
        "publisher": {"@type": "Organization", "name": "Smile AI Review Hub"},
        "mainEntityOfPage": f"{BASE_URL}/{slug}/",
    }
    return f'<script type="application/ld+json">{json.dumps(schema, ensure_ascii=False)}</script>'


def _links_for_slug(slug: str) -> list[dict[str, Any]]:
    return [row for row in read_csv(DATA_DIR / "internal_link_insertions.csv") if row.get("source_slug") == slug and row.get("target_slug") != slug]


def publish_article(row: dict[str, Any], publish: bool = False) -> dict[str, Any]:
    decision = str(row.get("decision") or row.get("action") or "")
    topic = str(row.get("topic") or row.get("suggested_title") or "")
    slug = slugify(row.get("slug") or topic)
    run_timestamp = datetime.now().isoformat(timespec="seconds")
    if not slug:
        return {
            "run_timestamp": run_timestamp,
            "slug": "",
            "topic": topic,
            "article_type": row.get("article_type", ""),
            "status": "skipped",
            "published_url": "",
            "source_file": "",
            "word_count": "",
            "internal_links_added": 0,
            "affiliate_links_added": 0,
            "video_package_path": "",
            "error": "Missing slug.",
        }
    try:
        package = generate_article_package(row)
        markdown = Path(package["markdown_path"]).read_text(encoding="utf-8")
        links = _links_for_slug(slug)
        body = markdown_to_html(markdown, links) + "\n" + article_schema(row)
        description = f"Independent guide to {topic}, covering pricing, pros, cons, alternatives, and practical buyer fit."
        page = page_shell(topic[:60], description[:155], body, f"/{slug}/")
        if publish:
            output_dir = PUBLISHED_SOURCE_DIR / slug
            status = "refreshed_source" if decision == "REFRESH_EXISTING" else "published_source"
        else:
            output_dir = PREVIEW_DIR / slug
            status = "preview"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / "index.html"
        output_path.write_text(page, encoding="utf-8")
        return {
            "run_timestamp": run_timestamp,
            "topic": topic,
            "slug": slug,
            "decision": decision,
            "article_type": row.get("article_type", ""),
            "status": status,
            "published_url": f"{BASE_URL}/{slug}/",
            "article_url": f"{BASE_URL}/{slug}/",
            "source_file": str(output_path),
            "output_path": str(output_path),
            "word_count": package.get("word_count_estimate", ""),
            "internal_links_added": len(links),
            "affiliate_links_added": 1 if "affiliate disclosure" in markdown.lower() else 0,
            "video_package_path": "",
            "error": "",
            "reason": "Wrote local website source." if publish else "Dry-run preview only.",
            "markdown_path": package["markdown_path"],
            "json_path": package["json_path"],
            "youtube_embed_position": package.get("youtube_embed_position", ""),
        }
    except Exception as exc:
        return {
            "run_timestamp": run_timestamp,
            "topic": topic,
            "slug": slug,
            "article_type": row.get("article_type", ""),
            "status": "error",
            "published_url": f"{BASE_URL}/{slug}/" if slug else "",
            "source_file": "",
            "word_count": "",
            "internal_links_added": 0,
            "affiliate_links_added": 0,
            "video_package_path": "",
            "error": str(exc),
        }


def publish_selected_articles(selected_path: Path = DATA_DIR / "today_selected_topics.csv", limit: int = 10, publish: bool = False) -> list[dict[str, Any]]:
    rows = read_csv(selected_path)
    candidates = [row for row in rows if row.get("decision") in {"WRITE_NOW", "REFRESH_EXISTING"}]
    reports = [publish_article(row, publish=publish) for row in candidates[:limit]]
    write_csv(DATA_DIR / "website_publish_report.csv", reports, PUBLISH_REPORT_FIELDS)
    write_json(DATA_DIR / "website_publish_report.json", reports)
    write_csv(DATA_DIR / "published_today.csv", reports, PUBLISHED_TODAY_FIELDS)
    write_json(DATA_DIR / "published_today.json", reports)
    article_reports = [
        {
            "run_timestamp": row.get("run_timestamp", ""),
            "topic": row.get("topic", ""),
            "slug": row.get("slug", ""),
            "article_type": row.get("article_type", ""),
            "status": row.get("status", ""),
            "markdown_path": row.get("markdown_path", ""),
            "json_path": row.get("json_path", ""),
            "word_count": row.get("word_count", ""),
            "youtube_embed_position": row.get("youtube_embed_position", ""),
            "error": row.get("error", ""),
        }
        for row in reports
    ]
    write_csv(DATA_DIR / "article_draft_report.csv", article_reports, ARTICLE_DRAFT_DAILY_FIELDS)
    write_json(DATA_DIR / "article_draft_report.json", article_reports)
    return reports
