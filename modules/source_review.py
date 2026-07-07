from __future__ import annotations

import csv
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from config import settings
from modules.knowledge_registry import KnowledgeRegistry, _read_json, _source_family, _write_csv, _write_json


def _write_md(path: Path, lines: list[str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return path


class SourceReview:
    def __init__(self, data_dir: Path | None = None, config: dict[str, Any] | None = None, registry: KnowledgeRegistry | None = None) -> None:
        self.data_dir = data_dir or settings.data_dir
        self.config = config or {}
        self.registry = registry or KnowledgeRegistry(self.data_dir, self.config)
        self.queue_path = self.data_dir / "source_review_queue.json"
        self.report_json = self.data_dir / "source_review_report.json"
        self.report_csv = self.data_dir / "source_review_report.csv"
        self.report_md = self.data_dir / "source_review_report.md"

    def load_queue(self) -> list[dict[str, Any]]:
        return _read_json(self.queue_path, [])

    def save_queue(self, rows: list[dict[str, Any]]) -> None:
        _write_json(self.queue_path, rows)

    def sync_from_registry(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        queue = self.load_queue()
        index = {str(row.get("id", "")): row for row in queue}
        synced: list[dict[str, Any]] = []
        for row in rows:
            source_type = str(row.get("source_type", ""))
            if source_type not in {"official_docs", "pricing_page", "affiliate_program_page", "release_notes", "competitor_article"}:
                continue
            review_status = str(row.get("verification_status", "pending"))
            if review_status == "archived":
                continue
            current = index.get(str(row.get("id", "")), {})
            last_review = str(current.get("last_review") or row.get("verification_date") or row.get("last_seen") or "")
            next_review = self._schedule_next_review(last_review, source_type)
            entry = {
                "id": str(row.get("id", "")),
                "source": str(row.get("source_name", "")),
                "type": _source_family(source_type),
                "status": review_status,
                "priority": self._priority_for_row(row),
                "confidence": float(row.get("confidence", 0)),
                "reason": str(row.get("reason") or self._reason_for_status(review_status)),
                "last_review": last_review,
                "next_review": next_review,
                "review_count": int(float(current.get("review_count", 0))),
                "version": int(float(row.get("version", 1))),
            }
            synced.append(entry)
        synced.sort(key=lambda row: (str(row.get("priority", "")), str(row.get("type", "")), str(row.get("source", ""))))
        self.save_queue(synced)
        self._write_report(synced)
        return synced

    def approve_source(self, source_id: str, *, reviewer: str = "system", confidence: float | None = None) -> dict[str, Any] | None:
        updates: dict[str, Any] = {
            "verification_status": "verified",
            "verified_by": reviewer,
            "verification_date": datetime.now(UTC).isoformat(),
        }
        if confidence is not None:
            updates["confidence"] = confidence
        updated = self.registry.update_record(source_id, **updates)
        queue = self._update_queue_status(source_id, "verified")
        self._write_report(queue)
        return updated

    def reject_source(self, source_id: str, *, reviewer: str = "system", reason: str = "") -> dict[str, Any] | None:
        updated = self.registry.update_record(
            source_id,
            verification_status="rejected",
            verified_by=reviewer,
            reason=reason or "rejected during review",
        )
        queue = self._update_queue_status(source_id, "rejected", reason=reason or "rejected during review")
        self._write_report(queue)
        return updated

    def expire_source(self, source_id: str, *, reason: str = "") -> dict[str, Any] | None:
        updated = self.registry.update_record(source_id, verification_status="expired", reason=reason or "expired by review workflow")
        queue = self._update_queue_status(source_id, "expired", reason=reason or "expired by review workflow")
        self._write_report(queue)
        return updated

    def archive_source(self, source_id: str, *, reason: str = "") -> dict[str, Any] | None:
        updated = self.registry.update_record(source_id, verification_status="archived", reason=reason or "archived")
        queue = self._update_queue_status(source_id, "archived", reason=reason or "archived")
        self._write_report(queue)
        return updated

    def _update_queue_status(self, source_id: str, status: str, **extra: Any) -> list[dict[str, Any]]:
        queue = self.load_queue()
        for row in queue:
            if str(row.get("id", "")) != source_id:
                continue
            row["status"] = status
            row["last_review"] = datetime.now(UTC).isoformat()
            row["review_count"] = int(float(row.get("review_count", 0))) + 1
            row["next_review"] = self._schedule_next_review(row["last_review"], self._source_type_from_queue(row))
            row.update(extra)
            break
        self.save_queue(queue)
        return queue

    def _write_report(self, rows: list[dict[str, Any]]) -> None:
        summary = {
            "items": len(rows),
            "pending": sum(1 for row in rows if str(row.get("status", "")) == "pending"),
            "verified": sum(1 for row in rows if str(row.get("status", "")) == "verified"),
            "needs_review": sum(1 for row in rows if str(row.get("status", "")) == "needs_review"),
            "expired": sum(1 for row in rows if str(row.get("status", "")) == "expired"),
            "duplicate": sum(1 for row in rows if str(row.get("status", "")) == "duplicate"),
            "rejected": sum(1 for row in rows if str(row.get("status", "")) == "rejected"),
        }
        _write_json(self.report_json, {"summary": summary, "items": rows})
        _write_csv(self.report_csv, rows)
        _write_md(
            self.report_md,
            [
                "# Source Review Report",
                "",
                f"- Items: {summary['items']}",
                f"- Pending: {summary['pending']}",
                f"- Verified: {summary['verified']}",
                f"- Needs review: {summary['needs_review']}",
                f"- Expired: {summary['expired']}",
                f"- Duplicate: {summary['duplicate']}",
                f"- Rejected: {summary['rejected']}",
            ],
        )

    def _schedule_next_review(self, last_review: str, source_type: str) -> str:
        try:
            base = datetime.fromisoformat(last_review.replace("Z", "+00:00"))
            if base.tzinfo is None:
                base = base.replace(tzinfo=UTC)
        except ValueError:
            base = datetime.now(UTC)
        review_after_days = int(float(self.config.get("review_after_days", 90)))
        multiplier = {"official_docs": 1.5, "pricing": 1.0, "affiliate": 1.0, "release_notes": 0.75, "competitor": 0.75}.get(source_type, 1.0)
        return (base + timedelta(days=max(7, int(review_after_days * multiplier)))).astimezone(UTC).isoformat()

    def _priority_for_row(self, row: dict[str, Any]) -> str:
        status = str(row.get("verification_status", ""))
        freshness = int(float(row.get("freshness_score", 0)))
        if status in {"expired", "duplicate"} or freshness <= 15:
            return "high"
        if status in {"pending", "needs_review"} or freshness <= 45:
            return "medium"
        return "low"

    def _reason_for_status(self, status: str) -> str:
        mapping = {
            "verified": "verified source",
            "pending": "new source pending review",
            "needs_review": "source requires review",
            "expired": "source freshness expired",
            "duplicate": "source duplicates canonical record",
            "rejected": "source rejected",
        }
        return mapping.get(status, "source review required")

    def _source_type_from_queue(self, row: dict[str, Any]) -> str:
        value = str(row.get("type", "")).strip().lower()
        return value or "official_docs"
