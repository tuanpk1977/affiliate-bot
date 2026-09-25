from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from .inventory import article_inventory
from .storage import atomic_write_json, atomic_write_text


SCHEMA_VERSION = "evergreen_recommendations_v1"
ACTIONS = {
    "KEEP",
    "VERIFY",
    "UPDATE_FACTS",
    "UPDATE_PRICING",
    "UPDATE_LINKS",
    "UPDATE_SCHEMA",
    "UPDATE_IMAGE",
    "REWRITE",
}


def _as_date(value: str) -> date | None:
    raw = (value or "")[:10]
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


class EvergreenEngine:
    def __init__(
        self,
        *,
        root: Path,
        now: datetime | None = None,
        cycles: tuple[int, ...] = (30, 90, 180, 365),
    ) -> None:
        self.root = root.resolve()
        self.now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        self.cycles = tuple(sorted(cycles))

    def scan(self, records: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        records = records if records is not None else article_inventory(self.root)
        items: list[dict[str, Any]] = []
        for record in records:
            html = record.get("html") if isinstance(record.get("html"), dict) else {}
            metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
            observed = _as_date(
                str(
                    metadata.get("last_verified_at")
                    or metadata.get("updated_at")
                    or record.get("batch_date")
                    or ""
                )
            )
            age_days = (self.now.date() - observed).days if observed else None
            due_cycle = next((cycle for cycle in self.cycles if age_days is not None and age_days >= cycle), None)
            action = "KEEP"
            reasons: list[str] = []
            title = str(record.get("title") or "")
            if observed is None:
                action = "VERIFY"
                reasons.append("no reliable verification date")
            elif age_days is not None and age_days >= 365:
                action = "REWRITE"
                reasons.append("content exceeds the 365-day editorial cycle")
            elif age_days is not None and age_days >= 180:
                action = "UPDATE_FACTS"
                reasons.append("facts require a 180-day review")
            elif age_days is not None and age_days >= 90:
                action = "VERIFY"
                reasons.append("article reached the 90-day verification cycle")
            elif age_days is not None and age_days >= 30:
                action = "VERIFY"
                reasons.append("article reached the 30-day check cycle")
            if "pricing" in title.casefold() and age_days is not None and age_days >= 90:
                action = "UPDATE_PRICING"
                reasons.append("pricing content is older than 90 days")
            if record.get("is_published_local") and not html.get("images"):
                action = "UPDATE_IMAGE"
                reasons.append("published local page has no detectable image")
            if record.get("is_published_local") and not html.get("schemas"):
                action = "UPDATE_SCHEMA"
                reasons.append("published local page has no detectable structured data")
            items.append(
                {
                    "slug": record["slug"],
                    "canonical": record["canonical"],
                    "age_days": age_days,
                    "review_cycle_days": due_cycle,
                    "action": action,
                    "reasons": sorted(set(reasons)),
                    "recommendation_only": True,
                }
            )
        return {
            "schema_version": SCHEMA_VERSION,
            "generated_at": self.now.isoformat(),
            "cycles_days": list(self.cycles),
            "items": items,
            "summary": {
                action: sum(row["action"] == action for row in items)
                for action in sorted(ACTIONS)
            },
            "content_modified": False,
        }

    def write(self, payload: dict[str, Any], output_dir: Path) -> dict[str, str]:
        json_path = output_dir / "evergreen_recommendations.json"
        md_path = output_dir / "evergreen_recommendations.md"
        atomic_write_json(payload, path=json_path, intelligence_root=self.root / "data")
        lines = ["# Evergreen Recommendations", "", "Recommendation only. No content was changed.", ""]
        for item in payload["items"]:
            lines.append(f"- `{item['slug']}`: **{item['action']}** - {'; '.join(item['reasons']) or 'current'}")
        atomic_write_text(md_path, "\n".join(lines) + "\n", intelligence_root=self.root / "data")
        return {"json": str(json_path), "markdown": str(md_path)}
