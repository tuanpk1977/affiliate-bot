from __future__ import annotations

import html
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from modules.article_style_comparator import analyze_article, compare_articles

from .inventory import WORKFLOW_MARKERS, article_inventory, schema_types
from .storage import atomic_write_json, atomic_write_text


SCHEMA_VERSION = "editorial_quality_dashboard_v1"
MOJIBAKE_PATTERNS = ("Ã", "Â", "â€", "â€™", "ï¿½", "\ufffd")


def _source_count(metadata: dict[str, Any]) -> int:
    values: set[str] = set()
    for key in ("source_urls", "verified_sources", "sources", "supporting_source_urls"):
        raw = metadata.get(key)
        if isinstance(raw, str) and raw.startswith(("http://", "https://")):
            values.add(raw)
        elif isinstance(raw, list):
            values.update(str(value) for value in raw if str(value).startswith(("http://", "https://")))
    return len(values)


def evaluate_record(record: dict[str, Any]) -> dict[str, Any]:
    page = record.get("html") if isinstance(record.get("html"), dict) else {}
    raw = str(page.get("raw") or "")
    metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
    metrics = analyze_article(raw) if raw else {
        "word_count": 0,
        "heading_count": 0,
        "faq_question_count": 0,
        "duplicate_paragraph_count": 0,
        "duplicate_heading_count": 0,
    }
    links = [row for row in page.get("links") or [] if isinstance(row, dict)]
    internal_links = [
        row for row in links
        if str(row.get("href") or "").startswith(("/", "https://smileaireviewhub.com/"))
    ]
    external_links = [
        row for row in links
        if str(row.get("href") or "").startswith(("http://", "https://"))
        and not str(row.get("href") or "").startswith("https://smileaireviewhub.com/")
    ]
    word_count = int(metrics.get("word_count", 0) or 0)
    metrics.update(
        {
            "estimated_reading_minutes": max(1, round(word_count / 220)) if word_count else 0,
            "internal_link_count": len(internal_links),
            "external_link_count": len(external_links),
        }
    )
    types = schema_types(page.get("schemas") or [])
    blockers: list[str] = []
    warnings: list[str] = []
    information: list[str] = []
    if not raw:
        blockers.append("rendered HTML is missing")
    if raw and not page.get("canonical"):
        blockers.append("canonical is missing")
    if raw and not any(row.get("level") == "h1" for row in page.get("headings") or []):
        blockers.append("H1 is missing")
    if raw and not page.get("images"):
        warnings.append("no image was detected")
    if raw and "Article" not in types:
        warnings.append("Article schema was not detected")
    if raw and "BreadcrumbList" not in types:
        warnings.append("Breadcrumb schema was not detected")
    if raw and not ({"Person", "Author"} & types):
        warnings.append("Person/Author schema was not detected")
    if metrics.get("faq_question_count", 0) and "FAQPage" not in types:
        warnings.append("FAQ headings exist without FAQPage schema")
    if metrics.get("duplicate_paragraph_count", 0):
        warnings.append("duplicate paragraphs detected")
    if metrics.get("duplicate_heading_count", 0):
        warnings.append("duplicate headings detected")
    if any(marker in raw.casefold() for marker in WORKFLOW_MARKERS):
        blockers.append("public workflow marker leakage")
    if any(pattern in raw for pattern in MOJIBAKE_PATTERNS):
        blockers.append("UTF-8 mojibake detected")
    sources = _source_count(metadata)
    if not sources:
        warnings.append("metadata has no source URL")
    if page.get("description"):
        information.append("meta description present")
    return {
        "slug": record["slug"],
        "title": record["title"],
        "canonical": record["canonical"],
        "metrics": metrics,
        "source_count": sources,
        "schema_types": sorted(types),
        "json_ld_status": "PASS" if types else "MISSING",
        "image_count": len(page.get("images") or []),
        "severity": "BLOCKING" if blockers else ("WARNING" if warnings else "INFORMATIONAL"),
        "blocking": blockers,
        "warnings": warnings,
        "informational": information,
        "approval_recommendation_only": True,
    }


class EditorialQualityEngine:
    def __init__(self, *, root: Path) -> None:
        self.root = root.resolve()

    def build(
        self,
        records: list[dict[str, Any]] | None = None,
        *,
        style_reference_html: str = "",
    ) -> dict[str, Any]:
        records = records if records is not None else article_inventory(self.root)
        items = [evaluate_record(record) for record in records]
        if style_reference_html:
            for record, item in zip(records, items):
                candidate = str((record.get("html") or {}).get("raw") or "")
                if candidate:
                    item["style_deviation"] = compare_articles(style_reference_html, candidate)
        counts = Counter(row["severity"] for row in items)
        return {
            "schema_version": SCHEMA_VERSION,
            "items": items,
            "summary": {
                "article_count": len(items),
                "blocking": counts["BLOCKING"],
                "warning": counts["WARNING"],
                "informational": counts["INFORMATIONAL"],
                "average_word_count": round(
                    sum(row["metrics"].get("word_count", 0) for row in items) / max(1, len(items)),
                    1,
                ),
            },
            "approval_changed": False,
            "content_modified": False,
        }

    def write(self, payload: dict[str, Any], output_dir: Path) -> dict[str, str]:
        json_path = output_dir / "editorial_quality_dashboard.json"
        html_path = output_dir / "editorial_quality_dashboard.html"
        atomic_write_json(json_path, payload, intelligence_root=self.root / "data")
        rows = []
        for item in payload["items"]:
            detail = "; ".join(item["blocking"] + item["warnings"] + item["informational"]) or "No findings"
            rows.append(
                "<tr>"
                f"<td>{html.escape(item['title'])}</td>"
                f"<td>{html.escape(item['severity'])}</td>"
                f"<td>{item['metrics'].get('word_count', 0)}</td>"
                f"<td>{item['metrics'].get('estimated_reading_minutes', 0)}</td>"
                f"<td>{item['metrics'].get('heading_count', 0)}</td>"
                f"<td>{item['metrics'].get('faq_question_count', 0)}</td>"
                f"<td>{item['metrics'].get('internal_link_count', 0)}</td>"
                f"<td>{item['metrics'].get('external_link_count', 0)}</td>"
                f"<td>{html.escape(item['json_ld_status'])}</td>"
                f"<td>{item['source_count']}</td>"
                f"<td>{html.escape(detail)}</td>"
                "</tr>"
            )
        document = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="robots" content="noindex,nofollow">
<title>Editorial Quality Dashboard</title>
<style>body{{font-family:Arial,sans-serif;margin:2rem;color:#152238}}table{{border-collapse:collapse;width:100%}}
th,td{{border:1px solid #ccd6e0;padding:.65rem;text-align:left;vertical-align:top}}th{{background:#eef3f8}}</style>
</head><body><h1>Editorial Quality Dashboard</h1>
<p>Recommendation only. This dashboard cannot approve or publish content.</p>
<pre>{html.escape(json.dumps(payload['summary'], ensure_ascii=False, indent=2))}</pre>
<table><thead><tr><th>Article</th><th>Severity</th><th>Words</th><th>Read min</th>
<th>Headings</th><th>FAQ</th><th>Internal links</th><th>External links</th>
<th>JSON-LD</th><th>Sources</th><th>Findings</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table></body></html>
"""
        atomic_write_text(html_path, document, intelligence_root=self.root / "data")
        return {"json": str(json_path), "html": str(html_path)}
