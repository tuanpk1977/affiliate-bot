from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from config import settings


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write_json(path: Path, payload: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return path
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        for row in rows:
            writer.writerow({key: json.dumps(value, ensure_ascii=False) if isinstance(value, (list, dict)) else value for key, value in row.items()})
    return path


@dataclass(frozen=True)
class ContentPerformanceRecord:
    slug: str
    topic: str
    impressions: int
    clicks: int
    ctr: float
    ranking_estimate: float
    affiliate_clicks: int
    conversion_estimate: int
    revenue_estimate: float
    freshness_decay: float
    topic_roi_score: float
    update_priority: str
    next_recommended_action: str


class ContentAnalytics:
    def __init__(self, data_dir: Path | None = None, tracking_csv: Path | None = None, config: dict[str, Any] | None = None) -> None:
        self.data_dir = data_dir or settings.data_dir
        self.tracking_csv = tracking_csv or self.data_dir / "content_growth_performance_log.csv"
        self.config = config or {}
        self.performance_json = self.data_dir / "content_performance.json"
        self.performance_csv = self.data_dir / "content_performance.csv"
        self.feedback_history = self.data_dir / "topic_feedback_history.jsonl"

    def build_performance_report(self) -> list[dict[str, Any]]:
        rows = self._load_tracking_rows()
        performance = [asdict(self._record_from_tracking(row)) for row in rows]
        _write_json(self.performance_json, performance)
        _write_csv(self.performance_csv, performance)
        self._append_feedback_history(performance)
        return performance

    def score_adjustments(self) -> dict[str, dict[str, Any]]:
        rows = _read_json(self.performance_json, None)
        if not isinstance(rows, list):
            rows = self.build_performance_report()
        adjustments: dict[str, dict[str, Any]] = {}
        for row in rows:
            slug = str(row.get("slug", "")).strip()
            if not slug:
                continue
            roi = float(row.get("topic_roi_score", 0))
            action = str(row.get("next_recommended_action", "hold / do nothing"))
            if roi >= 70:
                delta = 10
            elif roi >= 50:
                delta = 4
            elif roi < 25:
                delta = -8
            else:
                delta = 0
            adjustments[slug] = {
                "score_delta": delta,
                "next_recommended_action": action,
                "update_priority": str(row.get("update_priority", "low")),
                "topic_roi_score": roi,
            }
        return adjustments

    def _load_tracking_rows(self) -> list[dict[str, Any]]:
        if not self.tracking_csv.exists():
            return self._sample_rows()
        with self.tracking_csv.open("r", encoding="utf-8", newline="") as handle:
            return [dict(row) for row in csv.DictReader(handle)]

    def _record_from_tracking(self, row: dict[str, Any]) -> ContentPerformanceRecord:
        slug = self._slug_from_url(str(row.get("url") or ""))
        topic = str(row.get("topic") or slug.replace("-", " ")).strip()
        impressions = int(float(row.get("impressions") or 0))
        clicks = int(float(row.get("clicks") or 0))
        ctr = round((clicks / impressions) * 100, 2) if impressions > 0 else float(row.get("ctr") or 0)
        ranking_estimate = float(row.get("average_position") or 35 or 0)
        affiliate_clicks = int(float(row.get("affiliate_clicks") or 0))
        conversion_estimate = max(0, round(affiliate_clicks * float(self.config.get("conversion_rate_estimate", 0.08))))
        revenue_estimate = round(float(row.get("revenue") or 0) + conversion_estimate * float(self.config.get("average_conversion_value", 12.5)), 2)
        freshness_decay = self._freshness_decay(str(row.get("publish_date") or ""))
        roi = round(min(100, impressions * 0.04 + clicks * 0.5 + affiliate_clicks * 1.5 + revenue_estimate * 0.35 - freshness_decay * 0.25), 2)
        if roi >= 70:
            update_priority = "high"
            action = "write new article"
        elif revenue_estimate > 0 and affiliate_clicks < 5:
            update_priority = "medium"
            action = "improve affiliate section"
        elif freshness_decay >= 40:
            update_priority = "high"
            action = "refresh pricing"
        elif ctr < 2 and impressions > 50:
            update_priority = "medium"
            action = "add internal links"
        elif clicks < 5 and impressions < 25:
            update_priority = "low"
            action = "hold / do nothing"
        else:
            update_priority = "medium"
            action = "update old article"
        return ContentPerformanceRecord(
            slug=slug,
            topic=topic,
            impressions=impressions,
            clicks=clicks,
            ctr=ctr,
            ranking_estimate=ranking_estimate,
            affiliate_clicks=affiliate_clicks,
            conversion_estimate=conversion_estimate,
            revenue_estimate=revenue_estimate,
            freshness_decay=freshness_decay,
            topic_roi_score=roi,
            update_priority=update_priority,
            next_recommended_action=action,
        )

    def _append_feedback_history(self, rows: list[dict[str, Any]]) -> None:
        self.feedback_history.parent.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(UTC).isoformat()
        with self.feedback_history.open("a", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps({"captured_at": stamp, **row}, ensure_ascii=False) + "\n")

    def _sample_rows(self) -> list[dict[str, Any]]:
        return [
            {
                "publish_date": date.today().isoformat(),
                "url": "https://example.com/sample-ai-topic/",
                "topic": "sample ai topic",
                "article_type": "comparison",
                "source_keyword": "sample ai topic",
                "impressions": 120,
                "clicks": 9,
                "ctr": 7.5,
                "average_position": 18,
                "affiliate_clicks": 4,
                "revenue": 24,
            }
        ]

    def _slug_from_url(self, url: str) -> str:
        clean = url.split("://", 1)[-1].split("/", 1)[-1].strip("/")
        return clean or "topic"

    def _freshness_decay(self, publish_date: str) -> float:
        try:
            published = date.fromisoformat(str(publish_date)[:10])
        except ValueError:
            return 50.0
        days = max(0, (date.today() - published).days)
        return round(min(100, days / 3), 2)
