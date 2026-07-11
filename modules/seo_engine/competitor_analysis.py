from __future__ import annotations

from typing import Any


def analyze_competitors(clusters: list[dict[str, Any]], imported_rows: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    imported_rows = imported_rows or []
    by_keyword = {str(row.get("keyword", "")).lower(): row for row in imported_rows}
    results = []
    for cluster in clusters:
        evidence = by_keyword.get(str(cluster["primary_keyword"]).lower())
        results.append({
            "cluster_id": cluster["cluster_id"], "primary_keyword": cluster["primary_keyword"],
            "source_status": "verified" if evidence else "unavailable",
            "competitors": list(evidence.get("competitors", [])) if evidence and isinstance(evidence.get("competitors"), list) else [],
            "notes": "Imported competitor evidence." if evidence else "No verified competitor dataset supplied; no SERP facts inferred.",
        })
    return results
