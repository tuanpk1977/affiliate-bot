from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from config import settings


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


class HumanApprovalWorkflow:
    def __init__(self, data_dir: Path | None = None, config: dict[str, Any] | None = None) -> None:
        self.data_dir = data_dir or settings.data_dir
        self.config = config or {}
        self.queue_path = self.data_dir / "human_approval_queue.json"

    def load_queue(self) -> list[dict[str, Any]]:
        return _read_json(self.queue_path, [])

    def save_queue(self, rows: list[dict[str, Any]]) -> None:
        _write_json(self.queue_path, rows)

    def sync_review(self, review: dict[str, Any]) -> dict[str, Any]:
        required = True
        if str(review.get("status", "")) not in {"ai_review_passed", "needs_human_review"}:
            status = "needs_revision" if str(review.get("status", "")) == "needs_revision" else "rejected"
        else:
            status = "needs_human_review"
        entry = {
            "slug": str(review.get("slug", "")),
            "topic": str(review.get("topic", "")),
            "status": status,
            "required": required,
            "reviewed_at": str(review.get("reviewed_at") or datetime.now(UTC).isoformat()),
            "approved_at": "",
            "approved_by": "",
            "reason": "" if status in {"needs_human_review", "human_approved"} else "; ".join(review.get("failures", [])),
        }
        rows = self.load_queue()
        replaced = False
        for index, row in enumerate(rows):
            if str(row.get("slug", "")) == entry["slug"]:
                rows[index] = entry
                replaced = True
                break
        if not replaced:
            rows.append(entry)
        self.save_queue(rows)
        return entry

    def approve(self, slug: str, *, approver: str = "human") -> dict[str, Any] | None:
        rows = self.load_queue()
        for row in rows:
            if str(row.get("slug", "")) != slug:
                continue
            row["status"] = "human_approved"
            row["approved_at"] = datetime.now(UTC).isoformat()
            row["approved_by"] = approver
            row["reason"] = ""
            self.save_queue(rows)
            return row
        return None

    def reject(self, slug: str, *, approver: str = "human", reason: str = "rejected during human review") -> dict[str, Any] | None:
        rows = self.load_queue()
        for row in rows:
            if str(row.get("slug", "")) != slug:
                continue
            row["status"] = "rejected"
            row["approved_at"] = datetime.now(UTC).isoformat()
            row["approved_by"] = approver
            row["reason"] = reason
            self.save_queue(rows)
            return row
        return None
