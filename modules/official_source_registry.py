from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


SOURCE_FAMILIES = (
    "official_website",
    "github",
    "readme",
    "docs",
    "pricing",
    "faq",
    "release_notes",
    "changelog",
    "blog",
    "api_docs",
    "marketplace",
    "examples",
    "tutorial",
    "support",
    "community",
)

FAMILY_ALIASES = {
    "official_docs": "docs",
    "documentation": "docs",
    "pricing_page": "pricing",
    "product_page": "official_website",
    "affiliate_program_page": "official_website",
    "validated_topic_source": "official_website",
    "official_blog": "blog",
}


def normalize_family(value: str) -> str:
    family = (value or "official_website").strip().casefold()
    return FAMILY_ALIASES.get(family, family)


def entity_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (value or "").casefold()).strip("-") or "unknown"


class OfficialSourceRegistry:
    """Repository-first memory of official source families discovered per entity."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> dict[str, Any]:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            payload = {"schema_version": 1, "entities": {}}
        if not isinstance(payload, dict):
            payload = {"schema_version": 1, "entities": {}}
        payload.setdefault("schema_version", 1)
        payload.setdefault("entities", {})
        return payload

    def sources_for(self, entity: str) -> list[dict[str, Any]]:
        record = self.load().get("entities", {}).get(entity_key(entity), {})
        families = record.get("source_families", {}) if isinstance(record, dict) else {}
        result: list[dict[str, Any]] = []
        for family, rows in families.items():
            for row in rows if isinstance(rows, list) else []:
                if not isinstance(row, dict) or row.get("status") not in {"verified", "approved"}:
                    continue
                result.append(
                    {
                        "source_id": str(row.get("source_id") or ""),
                        "title": str(row.get("title") or row.get("url") or ""),
                        "source_url": str(row.get("url") or ""),
                        "canonical_url": str(row.get("url") or ""),
                        "source_type": family,
                        "verification_status": row.get("status"),
                        "publication_date": row.get("publication_date", ""),
                        "registry_reused": True,
                    }
                )
        return result

    def remember(
        self,
        entity: str,
        sources: list[dict[str, Any]],
        *,
        checked_at: str | None = None,
    ) -> Path:
        payload = self.load()
        key = entity_key(entity)
        record = payload["entities"].setdefault(
            key,
            {
                "entity": entity,
                "source_families": {family: [] for family in SOURCE_FAMILIES},
                "created_at": checked_at or datetime.now(UTC).isoformat(),
            },
        )
        families = record.setdefault("source_families", {})
        for family in SOURCE_FAMILIES:
            families.setdefault(family, [])
        for source in sources:
            url = str(source.get("canonical_url") or source.get("source_url") or source.get("url") or "").strip()
            family = normalize_family(
                str(source.get("source_family") or source.get("source_type") or "official_website")
            )
            if not url or family not in SOURCE_FAMILIES:
                continue
            rows = families[family]
            existing = next(
                (row for row in rows if str(row.get("url") or "").casefold().rstrip("/") == url.casefold().rstrip("/")),
                None,
            )
            values = {
                "source_id": str(source.get("source_id") or ""),
                "title": str(source.get("title") or url),
                "url": url,
                "status": str(source.get("verification_status") or source.get("status") or "verified"),
                "last_checked": checked_at or datetime.now(UTC).isoformat(),
                "http_status": int(source.get("http_status") or 0),
                "content_hash": str(source.get("content_hash") or ""),
                "publication_date": str(source.get("publication_date") or ""),
            }
            if existing is None:
                rows.append(values)
            else:
                existing.update(values)
        record["last_checked"] = checked_at or datetime.now(UTC).isoformat()
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        temporary.replace(self.path)
        return self.path
