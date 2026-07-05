from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .config import WorkerBotConfig
from .utils import read_csv, read_json, rows_from_json_payload, slugify


@dataclass(frozen=True)
class TopicCandidate:
    topic: str
    slug: str
    score: float
    source: str
    raw: dict[str, Any]


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _score(row: dict[str, Any]) -> float:
    if row.get("total_score") is not None:
        return _float(row.get("total_score"))
    weighted = (
        _float(row.get("money_score")) * 0.25
        + _float(row.get("trend_score")) * 0.2
        + _float(row.get("seo_score")) * 0.2
        + _float(row.get("revenue_score")) * 0.2
        + _float(row.get("traffic_score")) * 0.15
    )
    return weighted or _float(row.get("score"))


def load_topic_candidates(config: WorkerBotConfig) -> list[TopicCandidate]:
    for path in (config.topic_scores_path, config.topic_dashboard_path, config.trending_topics_path):
        rows = rows_from_json_payload(read_json(path, []))
        if rows:
            return normalize_topic_rows(rows, source_path=str(path))
    return []


def normalize_topic_rows(rows: list[dict[str, Any]], source_path: str = "") -> list[TopicCandidate]:
    candidates: list[TopicCandidate] = []
    seen: set[str] = set()
    for row in rows:
        topic = str(row.get("topic") or row.get("title") or row.get("keyword") or "").strip()
        if not topic:
            continue
        slug = slugify(row.get("slug") or topic)
        if not slug or slug in seen:
            continue
        seen.add(slug)
        raw = dict(row)
        raw.setdefault("slug", slug)
        raw.setdefault("topic", topic)
        candidates.append(
            TopicCandidate(
                topic=topic,
                slug=slug,
                score=_score(raw),
                source=str(raw.get("source") or source_path or "topic_scores"),
                raw=raw,
            )
        )
    return candidates


def load_topic_history(config: WorkerBotConfig) -> list[dict[str, str]]:
    return read_csv(config.topic_history_path)
