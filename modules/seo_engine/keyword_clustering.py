from __future__ import annotations

from collections import defaultdict
from typing import Any

from .search_intent import classify_intent


STOP = {"best", "for", "the", "and", "a", "an", "2026", "small", "business", "software", "tool", "tools"}


def _topic(keyword: str) -> str:
    words = [word for word in keyword.split() if word not in STOP]
    return " ".join(words[:2]) or keyword


def build_clusters(candidates: list[dict[str, Any]], existing_slugs: set[str] | None = None) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for candidate in candidates:
        grouped[_topic(str(candidate["keyword"]))].append(candidate)
    existing_slugs = existing_slugs or set()
    clusters = []
    for index, (topic, rows) in enumerate(sorted(grouped.items()), 1):
        primary = max(rows, key=lambda row: len(str(row["keyword"])))
        intent = classify_intent(str(primary["keyword"]))
        overlap = [row["slug"] for row in rows if row["slug"] in existing_slugs]
        clusters.append({
            "cluster_id": f"cluster-{index:04d}", "cluster_name": topic.title(), "primary_keyword": primary["keyword"],
            "secondary_keywords": [row["keyword"] for row in rows if row is not primary], **intent,
            "suggested_content_type": "comparison" if "vs" in primary["keyword"] else "buyer_guide" if intent["search_intent"] == "commercial" else "guide",
            "suggested_slug": primary["slug"], "cannibalization_risk": "high" if overlap else "low",
            "cannibalization_matches": overlap, "source_status": "inferred",
        })
    return clusters
