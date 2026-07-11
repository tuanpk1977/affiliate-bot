from __future__ import annotations

from typing import Any


def analyze_gaps(clusters: list[dict[str, Any]], existing_slugs: set[str]) -> list[dict[str, Any]]:
    rows = []
    for cluster in clusters:
        slug = str(cluster["suggested_slug"])
        matches = list(cluster.get("cannibalization_matches") or [])
        decision = "update" if slug in existing_slugs else "merge" if matches else "create"
        rows.append({
            "cluster_id": cluster["cluster_id"], "keyword": cluster["primary_keyword"], "slug": slug,
            "decision": decision, "existing_matches": matches, "reason": "Exact local page exists." if decision == "update" else "Related local page overlaps." if decision == "merge" else "No matching local page found.",
            "source_status": "verified", "requires_human_review": True,
        })
    return rows
