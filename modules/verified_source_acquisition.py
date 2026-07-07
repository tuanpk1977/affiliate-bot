from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from config import settings


SOURCE_TYPES = (
    "official_docs",
    "pricing_page",
    "affiliate_program_page",
    "release_notes",
    "competitor_article",
    "api_docs",
    "product_page",
)
SOURCE_STATUSES = {"verified", "estimated", "missing", "needs_review"}


def _slugify(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", (value or "").lower()).strip("-")
    return cleaned or "topic"


def _coerce_list(value: Any) -> list[str]:
    if isinstance(value, str):
        raw = re.split(r"[,;\n]", value)
    elif isinstance(value, (list, tuple, set)):
        raw = list(value)
    else:
        raw = []
    seen: set[str] = set()
    result: list[str] = []
    for item in raw:
        text = str(item).strip()
        norm = text.lower()
        if not text or norm in seen:
            continue
        seen.add(norm)
        result.append(text)
    return result


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


@dataclass(frozen=True)
class VerifiedSourceRecord:
    brand: str
    slug: str
    source_type: str
    source_name: str
    source_url: str
    source_status: str
    confidence: float
    notes: str
    last_verified_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "brand": self.brand,
            "slug": self.slug,
            "source_type": self.source_type,
            "source_name": self.source_name,
            "source_url": self.source_url,
            "source_status": self.source_status,
            "verification_status": self.source_status,
            "confidence": self.confidence,
            "notes": self.notes,
            "last_verified_at": self.last_verified_at,
            "verification_date": self.last_verified_at,
        }


class VerifiedSourceAcquisition:
    def __init__(
        self,
        *,
        registry_json: Path | None = None,
        registry_csv: Path | None = None,
    ) -> None:
        self.registry_json = registry_json or settings.data_dir / "source_registry.json"
        self.registry_csv = registry_csv or settings.data_dir / "source_registry.csv"

    def load_registry(self) -> list[VerifiedSourceRecord]:
        json_rows = _read_json(self.registry_json, [])
        if isinstance(json_rows, list) and json_rows:
            return [self._normalize_record(row) for row in json_rows if isinstance(row, dict)]
        if not self.registry_csv.exists():
            return []
        with self.registry_csv.open("r", encoding="utf-8", newline="") as handle:
            return [self._normalize_record(dict(row)) for row in csv.DictReader(handle)]

    def acquire(self, keyword: str, entities: dict[str, Any]) -> dict[str, Any]:
        records = self.load_registry()
        matched_brands = self._brands_for_entities(keyword, entities)
        relevant = [record for record in records if record.slug in matched_brands or record.brand.lower() in matched_brands]
        grouped = {source_type: [] for source_type in SOURCE_TYPES}
        for record in relevant:
            grouped.setdefault(record.source_type, []).append(record.to_dict())
        verified_sources = [row for rows in grouped.values() for row in rows if str(row.get("source_status", "")) == "verified"]
        missing_verified_sources = [
            source_type
            for source_type in ("official_docs", "pricing_page", "affiliate_program_page", "release_notes")
            if not any(str(row.get("source_status", "")) == "verified" for row in grouped.get(source_type, []))
        ]
        source_scores = self._score(grouped)
        confidence = round(
            sum(float(row.get("confidence", 0)) for row in verified_sources) / max(1, len(verified_sources)),
            2,
        )
        if source_scores["total_verified_source_score"] >= 70:
            status = "verified"
        elif verified_sources:
            status = "needs_review"
        else:
            status = "missing"
        return {
            "keyword": keyword,
            "matched_brands": sorted(matched_brands),
            "registry_records": grouped,
            "verified_sources": verified_sources,
            "missing_verified_sources": missing_verified_sources,
            "source_confidence": confidence,
            "source_status": status,
            **source_scores,
        }

    def normalize_rows(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        seen: set[tuple[str, str, str]] = set()
        normalized: list[dict[str, Any]] = []
        for row in rows:
            record = self._normalize_record(row)
            key = (record.slug, record.source_type, record.source_url.lower())
            if key in seen:
                continue
            seen.add(key)
            normalized.append(record.to_dict())
        normalized.sort(key=lambda row: (str(row.get("slug", "")), str(row.get("source_type", "")), str(row.get("source_name", ""))))
        return normalized

    def _normalize_record(self, row: dict[str, Any]) -> VerifiedSourceRecord:
        brand = str(row.get("brand") or row.get("tool_name") or row.get("brand_name") or "").strip()
        slug = str(row.get("slug") or _slugify(brand)).strip() or _slugify(brand)
        source_type = str(row.get("source_type") or "").strip().lower()
        if source_type not in SOURCE_TYPES:
            source_type = "product_page"
        source_status = str(row.get("verification_status") or row.get("source_status") or row.get("status") or "needs_review").strip().lower()
        if source_status not in SOURCE_STATUSES:
            source_status = "needs_review"
        confidence_raw = row.get("confidence", 0)
        try:
            confidence = float(confidence_raw)
        except (TypeError, ValueError):
            confidence = 0.0
        confidence = max(0.0, min(100.0, confidence))
        return VerifiedSourceRecord(
            brand=brand,
            slug=slug,
            source_type=source_type,
            source_name=str(row.get("source_name") or row.get("label") or f"{brand} {source_type}").strip(),
            source_url=str(row.get("source_url") or row.get("url") or "").strip(),
            source_status=source_status,
            confidence=confidence,
            notes=str(row.get("notes") or row.get("evidence") or "").strip(),
            last_verified_at=str(row.get("verification_date") or row.get("last_verified_at") or row.get("last_checked") or "").strip(),
        )

    def _brands_for_entities(self, keyword: str, entities: dict[str, Any]) -> set[str]:
        brands: list[str] = []
        for key in ("products", "companies", "ai_tools", "competitors", "alternatives"):
            brands.extend(_coerce_list(entities.get(key)))
        tokens = re.findall(r"[a-z0-9]+", keyword.lower())
        brands.extend(tokens[:6])
        return {item.lower() for item in brands if item}

    def _score(self, grouped: dict[str, list[dict[str, Any]]]) -> dict[str, int]:
        def score_for(source_type: str, verified_weight: int, estimated_weight: int = 8) -> int:
            rows = grouped.get(source_type, [])
            verified = sum(1 for row in rows if str(row.get("source_status", "")) == "verified")
            estimated = sum(1 for row in rows if str(row.get("source_status", "")) == "estimated")
            review = sum(1 for row in rows if str(row.get("source_status", "")) == "needs_review")
            return min(100, verified * verified_weight + estimated * estimated_weight + review * 4)

        scores = {
            "official_docs_score": score_for("official_docs", 40),
            "pricing_source_score": score_for("pricing_page", 40),
            "affiliate_source_score": score_for("affiliate_program_page", 30),
            "changelog_source_score": score_for("release_notes", 25),
            "competitor_source_score": score_for("competitor_article", 20),
        }
        scores["total_verified_source_score"] = min(
            100,
            scores["official_docs_score"]
            + scores["pricing_source_score"]
            + scores["affiliate_source_score"]
            + round(scores["changelog_source_score"] * 0.5)
            + round(scores["competitor_source_score"] * 0.5),
        )
        return scores
