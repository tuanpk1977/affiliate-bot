from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Any


DEFAULT_MAPPING = {
    "url": ("url", "page", "landing_page", "path"),
    "date": ("date", "day", "period"),
    "clicks": ("clicks",),
    "impressions": ("impressions",),
    "ctr": ("ctr",),
    "position": ("position", "average_position"),
    "affiliate_clicks": ("affiliate_clicks",),
    "conversions": ("conversions",),
    "bounce_rate": ("bounce_rate",),
    "time_on_page": ("time_on_page", "average_engagement_time"),
    "social_engagement": ("social_engagement",),
    "duplicate_group_size": ("duplicate_group_size", "duplicate_urls"),
    "distinct_intents": ("distinct_intents", "intent_count"),
}


def _number(value: Any) -> float:
    text = str(value or "").strip().replace(",", "").replace("%", "")
    if not text:
        return 0.0
    try:
        return float(text)
    except ValueError:
        return 0.0


class PerformanceEngine:
    """Analyze manually exported metrics without changing published content."""

    def __init__(self, *, root: Path, config: dict[str, Any] | None = None) -> None:
        self.root = root
        self.config = dict(config or {})

    def import_csv(self, paths: list[Path]) -> list[dict[str, Any]]:
        combined: dict[str, dict[str, Any]] = {}
        mapping = {**DEFAULT_MAPPING, **dict(self.config.get("metric_mapping") or {})}
        for path in paths:
            if not path.exists():
                raise FileNotFoundError(str(path))
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle)
                if not reader.fieldnames:
                    raise ValueError(f"CSV has no header: {path}")
                lowered = {name.lower().strip(): name for name in reader.fieldnames}
                url_column = next((lowered[name] for name in mapping["url"] if name in lowered), None)
                if not url_column:
                    raise ValueError(f"CSV missing URL/page column: {path}")
                metric_columns = {}
                for metric, aliases in mapping.items():
                    if metric in {"url", "date"}:
                        continue
                    normalized_aliases = (aliases,) if isinstance(aliases, str) else tuple(aliases)
                    metric_columns[metric] = next(
                        (lowered[name] for name in normalized_aliases if name in lowered), None
                    )
                if not any(metric_columns.values()):
                    raise ValueError(f"CSV has no supported metric columns: {path}")
                for row in reader:
                    url = str(row.get(url_column) or "").strip()
                    if not url:
                        continue
                    record = combined.setdefault(url, {"url": url})
                    date_aliases = mapping.get("date") or ()
                    date_aliases = (date_aliases,) if isinstance(date_aliases, str) else tuple(date_aliases)
                    date_column = next((lowered[name] for name in date_aliases if name in lowered), None)
                    if date_column and row.get(date_column):
                        record["date"] = str(row[date_column]).strip()
                    for metric, aliases in mapping.items():
                        if metric in {"url", "date"}:
                            continue
                        aliases = (aliases,) if isinstance(aliases, str) else tuple(aliases)
                        column = next((lowered[name] for name in aliases if name in lowered), None)
                        if column:
                            record[metric] = _number(row.get(column))
        return sorted(combined.values(), key=lambda item: item["url"])

    def classify(self, record: dict[str, Any]) -> str:
        thresholds = {
            "expand_conversions": 3,
            "expand_clicks": 100,
            "update_impressions": 500,
            "update_ctr": 2,
            "delete_impressions": 10,
            "merge_duplicate_group_size": 2,
            "split_distinct_intents": 2,
            **dict(self.config.get("thresholds") or {}),
        }
        conversions = _number(record.get("conversions"))
        clicks = _number(record.get("clicks"))
        impressions = _number(record.get("impressions"))
        ctr = _number(record.get("ctr"))
        duplicate_group_size = _number(record.get("duplicate_group_size"))
        distinct_intents = _number(record.get("distinct_intents"))
        if duplicate_group_size >= thresholds["merge_duplicate_group_size"]:
            return "MERGE"
        if distinct_intents >= thresholds["split_distinct_intents"]:
            return "SPLIT"
        if conversions >= thresholds["expand_conversions"] or clicks >= thresholds["expand_clicks"]:
            return "EXPAND"
        if impressions >= thresholds["update_impressions"] and ctr < thresholds["update_ctr"]:
            return "UPDATE"
        if impressions <= thresholds["delete_impressions"] and clicks == 0:
            return "DELETE"
        return "KEEP"

    def analyze(self, paths: list[Path], *, output_dir: Path) -> dict[str, Any]:
        rows = self.import_csv(paths)
        candidates = [{**row, "recommendation": self.classify(row)} for row in rows]
        counts: dict[str, int] = defaultdict(int)
        for item in candidates:
            counts[item["recommendation"]] += 1
        report = {
            "schema_version": 1,
            "source_files": [str(path) for path in paths],
            "article_count": len(candidates),
            "recommendation_counts": dict(sorted(counts.items())),
            "articles": candidates,
            "automatic_article_modification": False,
        }
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "performance_report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        (output_dir / "optimization_candidates.json").write_text(
            json.dumps(candidates, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        summary = [
            "# Performance Intelligence Summary",
            "",
            f"Articles analyzed: {len(candidates)}",
            "",
            "Recommendations are advisory only. No article was modified.",
            "",
        ]
        for name, count in sorted(counts.items()):
            summary.append(f"- {name}: {count}")
        (output_dir / "performance_summary.md").write_text("\n".join(summary) + "\n", encoding="utf-8")
        return report


def build_editorial_memory(records: list[dict[str, Any]], *, output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    high_ctr = sorted(records, key=lambda item: _number(item.get("ctr")), reverse=True)[:20]
    high_conversion = sorted(records, key=lambda item: _number(item.get("conversions")), reverse=True)[:20]
    dates = sorted(str(item.get("date") or "") for item in records if item.get("date"))
    date_range = {"start": dates[0] if dates else "", "end": dates[-1] if dates else ""}
    base = {
        "sample_size": len(records),
        "confidence": "low" if len(records) < 10 else ("medium" if len(records) < 50 else "high"),
        "date_range": date_range,
        "limitations": ["Patterns are correlations from manually imported data, not proof of causation."],
    }
    payloads = {
        "high_ctr_patterns.json": {**base, "records": high_ctr},
        "high_conversion_patterns.json": {**base, "records": high_conversion},
        "cta_patterns.json": {**base, "patterns": []},
        "heading_patterns.json": {**base, "patterns": []},
        "internal_link_patterns.json": {**base, "patterns": []},
        "writing_patterns.json": {**base, "patterns": []},
    }
    for filename, payload in payloads.items():
        (output_dir / filename).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = (
        "# Editorial Memory Summary\n\n"
        f"Sample size: {base['sample_size']}\n\n"
        f"Confidence: {base['confidence']}\n\n"
        "These files are evidence records for future writers. They do not modify the writing engine automatically.\n"
    )
    (output_dir / "editorial_memory_summary.md").write_text(summary, encoding="utf-8")
    return {"output_dir": str(output_dir), **base}
