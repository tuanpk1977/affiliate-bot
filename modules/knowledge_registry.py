from __future__ import annotations

import csv
import json
import re
from datetime import UTC, datetime, timedelta
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

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
REVIEWABLE_TYPES = (
    "official_docs",
    "pricing_page",
    "affiliate_program_page",
    "release_notes",
    "competitor_article",
)
ACTIVE_VERIFICATION_STATES = {"verified", "pending", "needs_review"}
INACTIVE_VERIFICATION_STATES = {"expired", "duplicate", "rejected", "archived"}


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write_json(path: Path, payload: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return path
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    key: (
                        json.dumps(value, ensure_ascii=False)
                        if isinstance(value, (list, dict))
                        else value
                    )
                    for key, value in row.items()
                }
            )
    return path


def _slugify(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", (value or "").lower()).strip("-")
    return cleaned or "source"


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _parse_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        normalized = text.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)
    except ValueError:
        return None


def _source_family(source_type: str) -> str:
    mapping = {
        "official_docs": "official_docs",
        "pricing_page": "pricing",
        "affiliate_program_page": "affiliate",
        "release_notes": "release_notes",
        "competitor_article": "competitor",
        "api_docs": "official_docs",
        "product_page": "official_docs",
    }
    return mapping.get(source_type, source_type)


class KnowledgeRegistry:
    def __init__(self, data_dir: Path | None = None, config: dict[str, Any] | None = None) -> None:
        self.data_dir = data_dir or settings.data_dir
        self.config = config or {}
        self.registry_json = self.data_dir / "source_registry.json"
        self.registry_csv = self.data_dir / "source_registry.csv"
        self.history_path = self.data_dir / "source_registry_history.jsonl"

    def load_registry(self) -> list[dict[str, Any]]:
        rows = _read_json(self.registry_json, [])
        if isinstance(rows, list) and rows:
            return [self._normalize_record(row) for row in rows if isinstance(row, dict)]
        if not self.registry_csv.exists():
            return []
        with self.registry_csv.open("r", encoding="utf-8", newline="") as handle:
            return [self._normalize_record(dict(row)) for row in csv.DictReader(handle)]

    def save_registry(self, rows: list[dict[str, Any]]) -> None:
        persisted = [self._serialize_record(row) for row in rows]
        _write_json(self.registry_json, persisted)
        _write_csv(self.registry_csv, persisted)

    def normalize_rows(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        normalized = [self._normalize_record(row) for row in rows]
        exact_seen: set[tuple[str, str, str, str]] = set()
        deduped_exact: list[dict[str, Any]] = []
        for row in normalized:
            key = (
                str(row.get("slug", "")),
                str(row.get("source_type", "")),
                str(row.get("canonical_source", "")),
                str(row.get("source_name", "")).lower(),
            )
            if key in exact_seen:
                continue
            exact_seen.add(key)
            deduped_exact.append(row)
        deduped = self._apply_duplicate_detection(deduped_exact)
        governed = [self._apply_governance(row) for row in deduped]
        governed.sort(key=lambda row: (str(row.get("slug", "")), str(row.get("source_type", "")), str(row.get("source_name", ""))))
        return governed

    def sync_acquisition(self, keyword: str, acquisition_result: dict[str, Any]) -> dict[str, Any]:
        existing = self.load_registry()
        grouped = acquisition_result.get("registry_records", {}) if isinstance(acquisition_result, dict) else {}
        incoming_rows = [
            row
            for rows in grouped.values()
            if isinstance(rows, list)
            for row in rows
            if isinstance(row, dict)
        ]
        if not incoming_rows:
            evaluated = self.normalize_rows(existing)
            self.save_registry(evaluated)
            return self._evaluation_result(keyword, evaluated, [])

        seen_at = _now_iso()
        index = {
            (str(row.get("slug", "")), str(row.get("source_type", "")), str(row.get("canonical_source", ""))): row
            for row in existing
        }
        matched_ids: list[str] = []
        rows = list(existing)
        for row in incoming_rows:
            normalized = self._normalize_record({**row, "last_seen": seen_at})
            key = (normalized["slug"], normalized["source_type"], normalized["canonical_source"])
            current = index.get(key)
            if current is None:
                created = self._with_history(normalized, action="created", changed_fields=["id"])
                rows.append(created)
                index[key] = created
                matched_ids.append(created["id"])
                continue
            merged = self._merge_record(current, normalized, seen_at=seen_at)
            matched_ids.append(merged["id"])
            index[key] = merged
            for idx, candidate in enumerate(rows):
                if str(candidate.get("id", "")) == merged["id"]:
                    rows[idx] = merged
                    break

        governed = self.normalize_rows(rows)
        self.save_registry(governed)
        return self._evaluation_result(keyword, governed, matched_ids)

    def update_record(self, source_id: str, **updates: Any) -> dict[str, Any] | None:
        rows = self.load_registry()
        for index, row in enumerate(rows):
            if str(row.get("id", "")) != source_id:
                continue
            merged = self._normalize_record({**row, **updates})
            rows[index] = self._with_history(merged, action="updated", changed_fields=list(updates.keys()), previous=row)
            governed = self.normalize_rows(rows)
            self.save_registry(governed)
            for candidate in governed:
                if str(candidate.get("id", "")) == source_id:
                    return candidate
            return None
        return None

    def _normalize_record(self, row: dict[str, Any]) -> dict[str, Any]:
        brand = str(row.get("brand") or row.get("tool_name") or row.get("brand_name") or "").strip()
        source_type = str(row.get("source_type") or "").strip().lower()
        if source_type not in SOURCE_TYPES:
            source_type = "product_page"
        source_url = str(row.get("source_url") or row.get("url") or "").strip()
        verification_status = str(row.get("verification_status") or row.get("source_status") or row.get("status") or "pending").strip().lower()
        if verification_status == "estimated":
            verification_status = "pending"
        if verification_status not in ACTIVE_VERIFICATION_STATES | INACTIVE_VERIFICATION_STATES:
            verification_status = "pending"
        confidence = self._clamp_number(row.get("confidence", 0))
        slug = str(row.get("slug") or _slugify(brand)).strip() or _slugify(brand)
        first_seen = str(row.get("first_seen") or row.get("last_seen") or row.get("verification_date") or row.get("last_verified_at") or _now_iso())
        last_seen = str(row.get("last_seen") or row.get("verification_date") or row.get("last_verified_at") or first_seen)
        verification_date = str(row.get("verification_date") or row.get("last_verified_at") or last_seen)
        canonical_source = str(row.get("canonical_source") or self._canonical_source(source_url, slug, source_type)).strip()
        source_id = str(row.get("id") or f"{slug}:{source_type}:{_slugify(canonical_source)}").strip()
        history = row.get("history", [])
        return {
            "id": source_id,
            "brand": brand,
            "slug": slug,
            "source_type": source_type,
            "source_name": str(row.get("source_name") or row.get("label") or f"{brand} {source_type}").strip(),
            "source_url": source_url,
            "canonical_source": canonical_source,
            "verification_status": verification_status,
            "verification_date": verification_date,
            "verified_by": str(row.get("verified_by") or "system").strip(),
            "confidence": confidence,
            "freshness_score": int(self._clamp_number(row.get("freshness_score", 0))),
            "trust_score": int(self._clamp_number(row.get("trust_score", 0))),
            "official_score": int(self._clamp_number(row.get("official_score", 0))),
            "pricing_score": int(self._clamp_number(row.get("pricing_score", 0))),
            "affiliate_score": int(self._clamp_number(row.get("affiliate_score", 0))),
            "release_notes_score": int(self._clamp_number(row.get("release_notes_score", 0))),
            "competitor_score": int(self._clamp_number(row.get("competitor_score", 0))),
            "duplicate_of": str(row.get("duplicate_of") or "").strip(),
            "last_seen": last_seen,
            "first_seen": first_seen,
            "version": int(self._clamp_number(row.get("version", 1))),
            "history": history if isinstance(history, list) else [],
            "notes": str(row.get("notes") or row.get("evidence") or "").strip(),
            "reason": str(row.get("reason") or "").strip(),
        }

    def _serialize_record(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            key: row.get(key)
            for key in (
                "id",
                "brand",
                "slug",
                "source_type",
                "source_name",
                "source_url",
                "canonical_source",
                "verification_status",
                "verification_date",
                "verified_by",
                "confidence",
                "freshness_score",
                "trust_score",
                "official_score",
                "pricing_score",
                "affiliate_score",
                "release_notes_score",
                "competitor_score",
                "duplicate_of",
                "last_seen",
                "first_seen",
                "version",
                "history",
                "notes",
                "reason",
            )
        }

    def _merge_record(self, current: dict[str, Any], incoming: dict[str, Any], *, seen_at: str) -> dict[str, Any]:
        changed_fields: list[str] = []
        merged = dict(current)
        merged["last_seen"] = seen_at
        for key in ("source_name", "source_url", "notes", "confidence", "verification_status", "verification_date", "verified_by"):
            if incoming.get(key) and incoming.get(key) != current.get(key):
                merged[key] = incoming[key]
                changed_fields.append(key)
        if not str(current.get("first_seen", "")).strip():
            merged["first_seen"] = incoming.get("first_seen", seen_at)
            changed_fields.append("first_seen")
        if not changed_fields:
            return current
        return self._with_history(merged, action="updated", changed_fields=changed_fields, previous=current)

    def _with_history(
        self,
        row: dict[str, Any],
        *,
        action: str,
        changed_fields: list[str],
        previous: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        history = list(previous.get("history", [])) if isinstance(previous, dict) else list(row.get("history", []))
        version = int(previous.get("version", 1)) if isinstance(previous, dict) else int(row.get("version", 1))
        if action != "touched":
            version += 1 if previous is not None else 0
        history.append(
            {
                "at": _now_iso(),
                "action": action,
                "version": version,
                "changed_fields": changed_fields,
            }
        )
        updated = {**row, "version": version, "history": history}
        self.history_path.parent.mkdir(parents=True, exist_ok=True)
        with self.history_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"id": row.get("id"), "action": action, "version": version, "changed_fields": changed_fields}, ensure_ascii=False) + "\n")
        return updated

    def _apply_duplicate_detection(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for row in rows:
            key = (str(row.get("source_type", "")), str(row.get("canonical_source", "")))
            grouped.setdefault(key, []).append(row)
        duplicate_similarity = float(self.config.get("duplicate_similarity", 0.88))
        for key_rows in grouped.values():
            key_rows.sort(key=lambda row: str(row.get("id", "")))
            canonical = key_rows[0] if key_rows else None
            if canonical is None:
                continue
            canonical["duplicate_of"] = ""
            for row in key_rows[1:]:
                row["duplicate_of"] = str(canonical.get("id", ""))
        for row in rows:
            if row.get("duplicate_of"):
                continue
            for candidate in rows:
                if row is candidate or row.get("source_type") != candidate.get("source_type"):
                    continue
                if row.get("slug") != candidate.get("slug"):
                    continue
                similarity = SequenceMatcher(None, str(row.get("source_name", "")).lower(), str(candidate.get("source_name", "")).lower()).ratio()
                if similarity >= duplicate_similarity:
                    if str(row.get("id", "")) > str(candidate.get("id", "")):
                        row["duplicate_of"] = str(candidate.get("id", ""))
                    break
        return rows

    def _apply_governance(self, row: dict[str, Any]) -> dict[str, Any]:
        source_type = str(row.get("source_type", ""))
        freshness = self._freshness_score(row)
        trust = self._trust_score(row, freshness)
        verification_status = str(row.get("verification_status", "pending"))
        if str(row.get("duplicate_of", "")).strip():
            verification_status = "duplicate"
        elif verification_status not in {"rejected", "archived"}:
            if freshness <= 0:
                verification_status = "expired"
            elif verification_status == "verified" and freshness < float(self.config.get("minimum_freshness", 35)):
                verification_status = "needs_review"
            elif verification_status in {"pending", "needs_review"}:
                verification_status = "needs_review"
        family = _source_family(source_type)
        row_scores = {
            "official_score": trust if family == "official_docs" and verification_status == "verified" else 0,
            "pricing_score": trust if family == "pricing" and verification_status == "verified" else 0,
            "affiliate_score": trust if family == "affiliate" and verification_status == "verified" else 0,
            "release_notes_score": trust if family == "release_notes" and verification_status == "verified" else 0,
            "competitor_score": trust if family == "competitor" and verification_status == "verified" else 0,
        }
        return {
            **row,
            "verification_status": verification_status,
            "freshness_score": freshness,
            "trust_score": trust,
            **row_scores,
        }

    def _evaluation_result(self, keyword: str, rows: list[dict[str, Any]], matched_ids: list[str]) -> dict[str, Any]:
        matched = [row for row in rows if str(row.get("id", "")) in set(matched_ids)] if matched_ids else []
        verified = [row for row in matched if str(row.get("verification_status", "")) == "verified"]
        pending = [row for row in matched if str(row.get("verification_status", "")) in {"pending", "needs_review"}]
        expired = [row for row in matched if str(row.get("verification_status", "")) == "expired"]
        duplicates = [row for row in matched if str(row.get("verification_status", "")) == "duplicate"]
        missing_types = [
            source_type
            for source_type in REVIEWABLE_TYPES
            if not any(str(row.get("source_type", "")) == source_type and str(row.get("verification_status", "")) == "verified" for row in matched)
        ]
        scores = {
            "official_docs_score": max((int(row.get("official_score", 0)) for row in matched), default=0),
            "pricing_source_score": max((int(row.get("pricing_score", 0)) for row in matched), default=0),
            "affiliate_source_score": max((int(row.get("affiliate_score", 0)) for row in matched), default=0),
            "changelog_source_score": max((int(row.get("release_notes_score", 0)) for row in matched), default=0),
            "competitor_source_score": max((int(row.get("competitor_score", 0)) for row in matched), default=0),
        }
        scores["total_verified_source_score"] = round(sum(scores.values()) / max(1, len(scores)))
        confidence_values = []
        for row in matched:
            status = str(row.get("verification_status", ""))
            if status == "verified":
                multiplier = 1.0
            elif status in {"pending", "needs_review"}:
                multiplier = 0.45
            else:
                multiplier = 0.0
            confidence_values.append(float(row.get("confidence", 0)) * multiplier)
        source_confidence = round(sum(confidence_values) / max(1, len(confidence_values)), 2)
        if verified and not pending and not expired and not duplicates:
            source_status = "verified"
        elif matched:
            source_status = "needs_review"
        else:
            source_status = "missing"
        return {
            "keyword": keyword,
            "registry_rows": matched,
            "verified_sources": verified,
            "pending_sources": pending,
            "expired_sources": expired,
            "duplicate_sources": duplicates,
            "missing_verified_sources": missing_types,
            "source_confidence": source_confidence,
            "source_status": source_status,
            **scores,
        }

    def _freshness_score(self, row: dict[str, Any]) -> int:
        verification_status = str(row.get("verification_status", "pending"))
        if verification_status in {"rejected", "archived"}:
            return 0
        source_type = str(row.get("source_type", ""))
        timestamp = (
            _parse_datetime(row.get("last_seen"))
            or _parse_datetime(row.get("verification_date"))
            or _parse_datetime(row.get("first_seen"))
        )
        if timestamp is None:
            return 0
        age_days = max(0, int((datetime.now(UTC) - timestamp).total_seconds() // 86400))
        expire_after = self._effective_expire_days(source_type)
        if age_days >= expire_after:
            return 0
        review_after = self._effective_review_days(source_type)
        if age_days <= 1:
            return 100
        if age_days <= review_after:
            ratio = age_days / max(1, review_after)
            return max(70, int(round(100 - ratio * 25)))
        ratio = (age_days - review_after) / max(1, expire_after - review_after)
        return max(1, int(round(70 - ratio * 70)))

    def _trust_score(self, row: dict[str, Any], freshness: int) -> int:
        verification_status = str(row.get("verification_status", "pending"))
        if verification_status in {"expired", "duplicate", "rejected", "archived"}:
            return 0
        confidence = float(row.get("confidence", 0))
        verification_bonus = {"verified": 18, "needs_review": 6, "pending": 3}.get(verification_status, 0)
        trust = round(confidence * 0.55 + freshness * 0.30 + verification_bonus)
        return max(0, min(100, trust))

    def _effective_review_days(self, source_type: str) -> int:
        base = int(self._clamp_number(self.config.get("review_after_days", 90)))
        multiplier = {
            "official_docs": 1.5,
            "pricing_page": 1.0,
            "affiliate_program_page": 1.0,
            "release_notes": 0.75,
            "competitor_article": 0.75,
            "api_docs": 1.25,
            "product_page": 1.25,
        }.get(source_type, 1.0)
        return max(7, int(base * multiplier))

    def _effective_expire_days(self, source_type: str) -> int:
        base = int(self._clamp_number(self.config.get("expire_after_days", 365)))
        multiplier = {
            "official_docs": 1.5,
            "pricing_page": 1.0,
            "affiliate_program_page": 1.0,
            "release_notes": 0.6,
            "competitor_article": 0.5,
            "api_docs": 1.25,
            "product_page": 1.25,
        }.get(source_type, 1.0)
        return max(30, int(base * multiplier))

    def _canonical_source(self, source_url: str, slug: str, source_type: str) -> str:
        parsed = urlparse(source_url)
        if parsed.netloc:
            path = parsed.path.rstrip("/") or "/"
            return f"{parsed.netloc.lower()}{path.lower()}"
        return f"{slug}:{source_type}"

    def _clamp_number(self, value: Any, default: float = 0) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError):
            number = float(default)
        return max(0.0, min(100.0, number))
