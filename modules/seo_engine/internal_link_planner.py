from __future__ import annotations

from typing import Any


def plan_internal_links(gaps: list[dict[str, Any]], site_pages: list[dict[str, str]]) -> list[dict[str, Any]]:
    suggestions = []
    for gap in gaps:
        target_tokens = set(str(gap["keyword"]).split())
        ranked = sorted(site_pages, key=lambda page: len(target_tokens & set(page.get("title", "").lower().split())), reverse=True)
        for page in ranked[:3]:
            if page.get("slug") == gap["slug"]:
                continue
            suggestions.append({
                "source_slug": page.get("slug", ""), "target_slug": gap["slug"], "anchor_text": gap["keyword"],
                "placement": "contextual body section", "reason": "Topical term overlap", "confidence": "medium",
                "source_status": "inferred",
            })
    return suggestions
