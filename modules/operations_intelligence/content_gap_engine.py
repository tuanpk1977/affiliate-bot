from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from .inventory import article_inventory
from .storage import atomic_write_json, atomic_write_text


SCHEMA_VERSION = "content_gap_suggestions_v1"


class ContentGapEngine:
    def __init__(self, *, root: Path) -> None:
        self.root = root.resolve()

    def suggest(
        self,
        graph: dict[str, Any],
        records: list[dict[str, Any]] | None = None,
        *,
        weekly_root_ids: set[str] | None = None,
    ) -> dict[str, Any]:
        records = records if records is not None else article_inventory(self.root)
        weekly_root_ids = weekly_root_ids or {
            str(row.get("root_topic_id") or "")
            for row in records
            if str(row.get("root_topic_id") or "")
        }
        covered_entities = {
            str(relation.get("target_entity_id") or "")
            for relation in graph.get("relations", [])
            if isinstance(relation, dict)
            and str(relation.get("relation_type") or "") in {"ARTICLE_REVIEWS_ENTITY", "ARTICLE_COMPARES_ENTITY"}
        }
        suggestions: list[dict[str, Any]] = []
        for entity in graph.get("entities", []):
            if not isinstance(entity, dict):
                continue
            entity_type = str(entity.get("entity_type") or "")
            entity_id = str(entity.get("entity_id") or "")
            if entity_type not in {"product", "model", "developer_tool", "topic"}:
                continue
            if entity_id in covered_entities:
                continue
            suggestions.append(
                {
                    "suggestion_id": f"gap:{entity_id}",
                    "entity_id": entity_id,
                    "entity_name": str(entity.get("canonical_name") or ""),
                    "entity_type": entity_type,
                    "reason": "verified graph entity has no explicit review/compare relation",
                    "weekly_root_locked": bool(weekly_root_ids),
                    "action": "SUGGESTION_ONLY",
                    "queue_mutation": False,
                }
            )
        return {
            "schema_version": SCHEMA_VERSION,
            "suggestions": suggestions,
            "summary": {
                "count": len(suggestions),
                "by_entity_type": dict(Counter(row["entity_type"] for row in suggestions)),
            },
            "weekly_root_ids_observed": sorted(weekly_root_ids),
            "weekly_root_changed": False,
            "queue_modified": False,
        }

    def write(self, payload: dict[str, Any], output_dir: Path) -> dict[str, str]:
        json_path = output_dir / "content_gap_suggestions.json"
        md_path = output_dir / "content_gap_suggestions.md"
        atomic_write_json(json_path, payload, intelligence_root=self.root / "data")
        lines = ["# Content Gap Suggestions", "", "Suggestion only. Weekly roots and queues were not changed.", ""]
        lines.extend(
            f"- **{row['entity_name']}** ({row['entity_type']}): {row['reason']}"
            for row in payload["suggestions"]
        )
        atomic_write_text(md_path, "\n".join(lines) + "\n", intelligence_root=self.root / "data")
        return {"json": str(json_path), "markdown": str(md_path)}

