from __future__ import annotations

from typing import Any


DEFAULT_WEIGHTS = {"intent": 0.30, "gap": 0.25, "difficulty": 0.15, "freshness": 0.10, "affiliate": 0.20}


def score_opportunities(gaps: list[dict[str, Any]], clusters: list[dict[str, Any]], weights: dict[str, float] | None = None) -> list[dict[str, Any]]:
    weights = {**DEFAULT_WEIGHTS, **(weights or {})}
    cluster_map = {row["cluster_id"]: row for row in clusters}
    output = []
    for gap in gaps:
        cluster = cluster_map[gap["cluster_id"]]
        intent_score = {"transactional": 95, "commercial": 85, "informational": 60, "navigational": 40}.get(str(cluster["search_intent"]), 50)
        values = {"intent": intent_score, "gap": 90 if gap["decision"] == "create" else 60, "difficulty": 65, "freshness": 50, "affiliate": 80 if cluster["search_intent"] in {"commercial", "transactional"} else 35}
        breakdown = {name: round(values[name] * weight, 2) for name, weight in weights.items()}
        output.append({**gap, "search_intent": cluster["search_intent"], "suggested_content_type": cluster["suggested_content_type"], "opportunity_score": round(sum(breakdown.values()), 2), "score_breakdown": breakdown, "score_inputs": values, "score_weights": weights})
    return sorted(output, key=lambda row: (-row["opportunity_score"], row["slug"]))
