from __future__ import annotations

from typing import Any


def build_entity_graph_report(payload: dict[str, Any]) -> str:
    summary = payload["summary"]
    lines = [
        "# Entity Knowledge Graph Report",
        "",
        f"- Schema: `{payload['schema_version']}`",
        f"- Generated at: `{payload['generated_at']}`",
        f"- Mode: `{payload['mode']}`",
        f"- Entities: {summary['entity_count']}",
        f"- Relations: {summary['relation_count']}",
        f"- Suggested merges: {summary['suggested_merge_count']}",
        f"- Unresolved entities: {summary['unresolved_count']}",
        f"- Missing official source: {summary['missing_official_source_count']}",
        f"- Orphan entities: {summary['orphan_count']}",
        "",
        "## Safety",
        "",
        "- Recommendation only: YES",
        "- Production content modified: NO",
        "- Approval state modified: NO",
        "- Publish state modified: NO",
        "",
        "## Limitations",
        "",
    ]
    lines.extend(f"- {item}" for item in payload.get("limitations", []))
    if payload.get("merge_suggestions"):
        lines.extend(["", "## Merge Suggestions", ""])
        for item in payload["merge_suggestions"]:
            lines.append(
                f"- `{item['left_entity_id']}` <-> `{item['right_entity_id']}`: "
                f"{item['reason']} ({item['confidence']:.2f}); human review required."
            )
    return "\n".join(lines).rstrip() + "\n"
