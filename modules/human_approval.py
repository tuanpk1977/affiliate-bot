from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from config import settings
from modules.revision_binding import approval_binding_status, binding_for_file


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
        current_hash = str(
            review.get("reviewed_content_hash") or review.get("content_hash") or ""
        ).strip().lower()
        current_revision = str(
            review.get("reviewed_revision_id")
            or review.get("revision_id")
            or review.get("task_revision")
            or ""
        ).strip()
        entry = {
            "slug": str(review.get("slug", "")),
            "topic": str(review.get("topic", "")),
            "status": status,
            "required": required,
            "reviewed_at": str(review.get("reviewed_at") or datetime.now(UTC).isoformat()),
            "approved_at": "",
            "approved_by": "",
            "reason": "" if status in {"needs_human_review", "human_approved"} else "; ".join(review.get("failures", [])),
            "canonical_task_id": str(review.get("canonical_task_id") or ""),
            "legacy_task_id": str(review.get("legacy_task_id") or review.get("task_id") or review.get("slug") or ""),
            "revision_id": current_revision,
            "content_hash": current_hash,
            "content_hash_version": str(review.get("content_hash_version") or ""),
            "approval_scope": str(review.get("approval_scope") or "website"),
        }
        rows = self.load_queue()
        replaced = False
        approval_superseded = False
        for index, row in enumerate(rows):
            if str(row.get("slug", "")) == entry["slug"]:
                history = list(row.get("approval_history") or [])
                if str(row.get("status") or "") == "human_approved":
                    binding_status = approval_binding_status(
                        row,
                        current_content_hash=current_hash,
                        current_revision_id=current_revision,
                    )
                    review_allows_approval = str(review.get("status") or "") in {
                        "ai_review_passed",
                        "needs_human_review",
                        "human_approved",
                    }
                    if binding_status == "MATCHED" and review_allows_approval:
                        entry.update(
                            {
                                "status": "human_approved",
                                "approved_at": str(row.get("approved_at") or ""),
                                "approved_by": str(row.get("approved_by") or ""),
                                "approved_content_hash": str(row.get("approved_content_hash") or row.get("content_hash") or ""),
                                "approved_revision_id": str(row.get("approved_revision_id") or row.get("revision_id") or ""),
                                "approval_binding_status": "MATCHED",
                            }
                        )
                    else:
                        superseded = {
                            "status": "human_approved",
                            "approved_at": str(row.get("approved_at") or ""),
                            "approved_by": str(row.get("approved_by") or ""),
                            "canonical_task_id": str(row.get("canonical_task_id") or ""),
                            "legacy_task_id": str(row.get("legacy_task_id") or row.get("slug") or ""),
                            "revision_id": str(row.get("approved_revision_id") or row.get("revision_id") or ""),
                            "content_hash": str(row.get("approved_content_hash") or row.get("content_hash") or ""),
                            "approval_scope": str(row.get("approval_scope") or "website"),
                            "binding_status": binding_status,
                            "superseded_at": entry["reviewed_at"],
                            "superseded_reason": entry["reason"] or "content revision changed or entered re-review",
                            "source_event": "sync_review",
                            "source_reference": entry["reviewed_at"],
                        }
                        identity = (
                            superseded["approved_at"],
                            superseded["content_hash"],
                            superseded["superseded_at"],
                        )
                        if not any(
                            (
                                str(item.get("approved_at") or ""),
                                str(item.get("content_hash") or ""),
                                str(item.get("superseded_at") or ""),
                            )
                            == identity
                            for item in history
                            if isinstance(item, dict)
                        ):
                            history.append(superseded)
                            approval_superseded = True
                        entry["approval_binding_status"] = binding_status
                if history:
                    entry["approval_history"] = history
                rows[index] = entry
                replaced = True
                break
        if not replaced:
            rows.append(entry)
        self.save_queue(rows)
        if approval_superseded:
            try:
                from modules.observation_hooks import observe_revision_safety_event_best_effort

                observe_revision_safety_event_best_effort(
                    root=self.data_dir.parent,
                    event_type="REVISION_APPROVAL_SUPERSEDED",
                    slug=entry["slug"],
                    canonical_task_id_value=entry["canonical_task_id"] or None,
                    artifact_paths=[self.queue_path],
                    details={
                        "legacy_task_id": entry["legacy_task_id"],
                        "revision_id": entry["revision_id"],
                        "content_hash": entry["content_hash"],
                        "approval_binding_status": entry.get("approval_binding_status", ""),
                    },
                )
            except Exception:
                pass
        return entry

    def approve(
        self,
        slug: str,
        *,
        approver: str = "human",
        canonical_task_id: str = "",
        legacy_task_id: str = "",
        revision_id: str = "",
        content_hash: str = "",
        approval_scope: str = "website",
    ) -> dict[str, Any] | None:
        rows = self.load_queue()
        for row in rows:
            if str(row.get("slug", "")) != slug:
                continue
            if not content_hash or not revision_id:
                draft = self.data_dir / "production_article_drafts" / slug / "index.html"
                if draft.is_file():
                    binding = binding_for_file(draft)
                    content_hash = content_hash or binding["content_hash"]
                    revision_id = revision_id or binding["revision_id"]
                    row["content_hash_version"] = binding["content_hash_version"]
                else:
                    content_hash = content_hash or str(row.get("content_hash") or "")
                    revision_id = revision_id or str(row.get("revision_id") or "")
            if str(row.get("status") or "") == "human_approved":
                prior_hash = str(row.get("approved_content_hash") or row.get("content_hash") or "")
                prior_revision = str(row.get("approved_revision_id") or row.get("revision_id") or "")
                if prior_hash != content_hash or prior_revision != revision_id:
                    history = list(row.get("approval_history") or [])
                    history.append(
                        {
                            "status": "human_approved",
                            "approved_at": str(row.get("approved_at") or ""),
                            "approved_by": str(row.get("approved_by") or ""),
                            "canonical_task_id": str(row.get("canonical_task_id") or ""),
                            "legacy_task_id": str(row.get("legacy_task_id") or slug),
                            "revision_id": prior_revision,
                            "content_hash": prior_hash,
                            "approval_scope": str(row.get("approval_scope") or "website"),
                            "binding_status": str(row.get("approval_binding_status") or "LEGACY_APPROVAL_UNBOUND"),
                            "superseded_at": datetime.now(UTC).isoformat(),
                            "superseded_reason": "new explicit human approval for a different revision",
                            "source_event": "explicit_human_approval",
                            "source_reference": slug,
                        }
                    )
                    row["approval_history"] = history
            row["status"] = "human_approved"
            row["approved_at"] = datetime.now(UTC).isoformat()
            row["approved_by"] = approver
            row["reason"] = ""
            row["canonical_task_id"] = canonical_task_id or str(row.get("canonical_task_id") or "")
            row["legacy_task_id"] = legacy_task_id or str(row.get("legacy_task_id") or slug)
            row["revision_id"] = revision_id
            row["approved_revision_id"] = revision_id
            row["content_hash"] = content_hash.lower()
            row["approved_content_hash"] = content_hash.lower()
            row["approval_scope"] = approval_scope
            row["approval_binding_status"] = "MATCHED" if content_hash and revision_id else "LEGACY_APPROVAL_UNBOUND"
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
