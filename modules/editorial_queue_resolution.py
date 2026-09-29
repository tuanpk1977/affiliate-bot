from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Callable


BATCH_STATE_QUEUE_CREATED = "QUEUE_CREATED"
BATCH_STATE_WRITING = "WRITING"
BATCH_STATE_DRAFT_READY = "DRAFT_READY"
BATCH_STATE_UNDER_REVIEW = "UNDER_REVIEW"
BATCH_STATE_HUMAN_APPROVED = "HUMAN_APPROVED"
BATCH_STATE_READY_FOR_PUBLISH = "READY_FOR_PUBLISH"
BATCH_STATE_PUBLISHED = "PUBLISHED"
_DASHBOARD_REVIEWABLE_BATCH_STATES = {
    BATCH_STATE_DRAFT_READY,
    BATCH_STATE_UNDER_REVIEW,
    BATCH_STATE_HUMAN_APPROVED,
    BATCH_STATE_READY_FOR_PUBLISH,
    BATCH_STATE_PUBLISHED,
}


class EditorialQueueResolution:
    """Read-only editorial queue and batch resolution."""

    def __init__(
        self,
        *,
        queue_root: Path,
        data_dir: Path,
        review_root: Path,
        site_output_dir: Path,
        read_json: Callable[[Path, Any], Any],
        normalize_publish_row: Callable[[dict[str, Any]], dict[str, Any]],
    ) -> None:
        self.queue_root = queue_root
        self.data_dir = data_dir
        self.review_root = review_root
        self.site_output_dir = site_output_dir
        self._read_json = read_json
        self._normalize_publish_row = normalize_publish_row

    def _queue_dir(self, batch_date: str) -> Path:
        return self.queue_root / batch_date

    def _load_queue(self, batch_date: str) -> dict[str, Any]:
        path = self._queue_dir(batch_date) / "topics.json"
        payload = self._read_json(path, {})
        if not payload:
            raise FileNotFoundError(f"Editorial queue not found for {batch_date}: {path}")
        return payload

    def latest_queue_date(self) -> str:
        if not self.queue_root.exists():
            return ""
        candidates: list[str] = []
        for path in self.queue_root.iterdir():
            if not path.is_dir():
                continue
            if path.name == "weeks":
                continue
            try:
                date.fromisoformat(path.name)
            except ValueError:
                continue
            if (path / "topics.json").exists():
                candidates.append(path.name)
        return max(candidates) if candidates else ""

    def resolve_batch_date(self, batch_date: str | None, *, require_activity: bool = False) -> str:
        requested = str(batch_date or "").strip()
        if requested and requested.lower() != "latest":
            return requested
        if not self.queue_root.exists():
            return requested or date.today().isoformat()
        candidates: list[tuple[str, int]] = []
        human_rows = {
            str(row.get("slug") or ""): row
            for row in self._read_json(self.data_dir / "human_approval_queue.json", [])
        }
        for path in self.queue_root.iterdir():
            if not path.is_dir() or path.name == "weeks":
                continue
            try:
                date.fromisoformat(path.name)
            except ValueError:
                continue
            queue_path = path / "topics.json"
            if not queue_path.exists():
                continue
            payload = self._read_json(queue_path, {})
            topics = list(payload.get("topics") or []) if isinstance(payload, dict) else []
            activity = 0
            for item in topics:
                slug = str(item.get("slug") or "")
                if (self.data_dir / "production_article_drafts" / slug / "index.html").exists():
                    activity += 1
                if str((human_rows.get(slug) or {}).get("status") or "") == "human_approved":
                    activity += 2
            if require_activity and activity <= 0:
                continue
            candidates.append((path.name, activity))
        if not candidates:
            return self.latest_queue_date() or requested or date.today().isoformat()
        candidates.sort(key=lambda row: (row[0], row[1]))
        return candidates[-1][0]

    def batch_state(self, batch_date: str) -> str:
        queue_path = self._queue_dir(batch_date) / "topics.json"
        payload = self._read_json(queue_path, {})
        if not isinstance(payload, dict) or not queue_path.exists():
            return ""
        topics = list(payload.get("topics") or [])
        if not topics:
            return BATCH_STATE_QUEUE_CREATED
        publish_rows = {
            str(row.get("slug") or ""): row
            for row in self._read_json(self.data_dir / "publish_queue.json", [])
        }
        human_rows = {
            str(row.get("slug") or ""): row
            for row in self._read_json(self.data_dir / "human_approval_queue.json", [])
        }
        has_draft = False
        has_under_review = False
        has_human_approved = False
        has_ready = False
        has_published = False
        has_writing = False
        for item in topics:
            slug = str(item.get("slug") or "")
            status = str(item.get("status") or "").strip().lower()
            if status in {"writing", "drafting"}:
                has_writing = True
            draft_file = (
                Path(str(item.get("draft_file") or ""))
                if str(item.get("draft_file") or "")
                else self.data_dir / "production_article_drafts" / slug / "index.html"
            )
            review_preview = (
                Path(str(item.get("review_preview") or ""))
                if str(item.get("review_preview") or "")
                else self.site_output_dir / "review" / batch_date / slug / "index.html"
            )
            if slug and (draft_file.exists() or review_preview.exists()):
                has_draft = True
            if status in {"drafted", "needs_review"} or str(
                (human_rows.get(slug) or {}).get("status") or ""
            ) == "needs_human_review":
                has_under_review = True
            if status == "approved" or str(
                (human_rows.get(slug) or {}).get("status") or ""
            ) == "human_approved":
                has_human_approved = True
            publish_row = publish_rows.get(slug) or {}
            normalized = self._normalize_publish_row(publish_row)
            publish_status = str(
                normalized.get("normalized_status") or publish_row.get("status") or ""
            ).strip().lower()
            if publish_status == "approved_for_publish" or normalized.get("final_gate") == "Ready for Publish":
                has_ready = True
            if status == "published" or publish_status in {"published_local", "published"}:
                has_published = True
        if has_published:
            return BATCH_STATE_PUBLISHED
        if has_ready:
            return BATCH_STATE_READY_FOR_PUBLISH
        if has_human_approved:
            return BATCH_STATE_HUMAN_APPROVED
        if has_under_review:
            return BATCH_STATE_UNDER_REVIEW
        if has_draft:
            return BATCH_STATE_DRAFT_READY
        if has_writing:
            return BATCH_STATE_WRITING
        return BATCH_STATE_QUEUE_CREATED

    def resolve_latest_batch_by_state(self, states: set[str]) -> str:
        if not self.queue_root.exists():
            return ""
        matches: list[str] = []
        for path in self.queue_root.iterdir():
            if not path.is_dir() or path.name == "weeks":
                continue
            try:
                date.fromisoformat(path.name)
            except ValueError:
                continue
            if self.batch_state(path.name) in states:
                matches.append(path.name)
        return max(matches) if matches else ""

    @staticmethod
    def _activity_timestamp(value: Any) -> float:
        text = str(value or "").strip()
        if not text:
            return 0.0
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return 0.0
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.timestamp()

    def reviewable_batch_details(self, batch_date: str) -> dict[str, Any]:
        """Describe operator-actionable drafts in one batch."""
        queue_path = self._queue_dir(batch_date) / "topics.json"
        payload = self._read_json(queue_path, {})
        if not isinstance(payload, dict) or not queue_path.exists():
            return {
                "batch_date": batch_date,
                "reviewable_slugs": [],
                "activity_timestamp": 0.0,
                "activity_at": "",
            }

        batch_state = str(payload.get("batch_state") or "").strip()
        if batch_state and batch_state not in _DASHBOARD_REVIEWABLE_BATCH_STATES:
            return {
                "batch_date": batch_date,
                "reviewable_slugs": [],
                "activity_timestamp": 0.0,
                "activity_at": "",
            }

        human_rows = {
            str(row.get("slug") or ""): row
            for row in self._read_json(self.data_dir / "human_approval_queue.json", [])
            if isinstance(row, dict)
        }
        publish_rows = {
            str(row.get("slug") or ""): row
            for row in self._read_json(self.data_dir / "publish_queue.json", [])
            if isinstance(row, dict)
        }
        terminal_queue_states = {"published", "rejected", "archived", "removed"}
        terminal_publish_states = {
            "published_local",
            "published",
            "committed_local",
            "awaiting_push",
            "push_blocked",
            "rebase_conflict",
            "pushed",
            "live",
        }
        reviewable_slugs: list[str] = []
        latest_activity = 0.0
        for item in list(payload.get("topics") or []):
            if not isinstance(item, dict):
                continue
            slug = str(item.get("slug") or "").strip()
            if not slug or str(item.get("status") or "").strip().lower() in terminal_queue_states:
                continue
            publish_row = publish_rows.get(slug) or {}
            normalized = self._normalize_publish_row(publish_row)
            publish_status = str(
                normalized.get("normalized_status") or publish_row.get("status") or ""
            ).strip().lower()
            if publish_status in terminal_publish_states:
                continue
            draft_dir = self.data_dir / "production_article_drafts" / slug
            configured_draft = (
                Path(str(item.get("draft_file") or ""))
                if str(item.get("draft_file") or "").strip()
                else draft_dir / "index.html"
            )
            review_preview = (
                Path(str(item.get("review_preview") or ""))
                if str(item.get("review_preview") or "").strip()
                else self.review_root / batch_date / slug / "index.html"
            )
            candidate_paths = [
                configured_draft,
                review_preview,
                draft_dir / "article.md",
                draft_dir / "metadata.json",
                draft_dir / "review.json",
            ]
            existing_paths = [path for path in candidate_paths if path.exists()]
            if not existing_paths:
                continue
            reviewable_slugs.append(slug)
            latest_activity = max(latest_activity, *(path.stat().st_mtime for path in existing_paths))
            human_row = human_rows.get(slug) or {}
            for row in (item, human_row, publish_row):
                for key in (
                    "updated_at",
                    "imported_at",
                    "generated_at",
                    "reviewed_at",
                    "approved_at",
                    "checked_at",
                ):
                    latest_activity = max(latest_activity, self._activity_timestamp(row.get(key)))

        activity_at = ""
        if latest_activity:
            activity_at = datetime.fromtimestamp(latest_activity, tz=UTC).isoformat()
        return {
            "batch_date": batch_date,
            "reviewable_slugs": reviewable_slugs,
            "activity_timestamp": latest_activity,
            "activity_at": activity_at,
        }

    def resolve_latest_reviewable_batch(self) -> dict[str, Any]:
        """Resolve the most recently acted-on batch that still needs review."""
        if not self.queue_root.exists():
            return {
                "batch_date": "",
                "reviewable_slugs": [],
                "activity_timestamp": 0.0,
                "activity_at": "",
            }
        candidates: list[dict[str, Any]] = []
        for path in self.queue_root.iterdir():
            if not path.is_dir() or path.name == "weeks":
                continue
            try:
                date.fromisoformat(path.name)
            except ValueError:
                continue
            details = self.reviewable_batch_details(path.name)
            if details["reviewable_slugs"]:
                candidates.append(details)
        if not candidates:
            return {
                "batch_date": "",
                "reviewable_slugs": [],
                "activity_timestamp": 0.0,
                "activity_at": "",
            }
        candidates.sort(key=lambda row: (float(row["activity_timestamp"]), str(row["batch_date"])))
        return candidates[-1]

    def publish_candidate_batch_details(self, batch_date: str) -> dict[str, Any]:
        """Describe non-terminal, human-approved publish candidates in a batch."""
        reviewable = self.reviewable_batch_details(batch_date)
        reviewable_slugs = set(reviewable.get("reviewable_slugs") or [])
        if not reviewable_slugs:
            return {
                "batch_date": batch_date,
                "candidate_slugs": [],
                "activity_timestamp": 0.0,
                "activity_at": "",
            }

        human_rows = {
            str(row.get("slug") or ""): row
            for row in self._read_json(self.data_dir / "human_approval_queue.json", [])
            if isinstance(row, dict)
        }
        publish_rows = {
            str(row.get("slug") or ""): row
            for row in self._read_json(self.data_dir / "publish_queue.json", [])
            if isinstance(row, dict)
        }
        candidate_slugs: list[str] = []
        for slug in sorted(reviewable_slugs):
            human_approved = (
                str((human_rows.get(slug) or {}).get("status") or "").strip().lower()
                == "human_approved"
            )
            publish_row = publish_rows.get(slug) or {}
            normalized = self._normalize_publish_row(publish_row)
            publish_status = str(
                normalized.get("normalized_status") or publish_row.get("status") or ""
            ).strip().lower()
            if human_approved or publish_status in {"approved_for_publish", "blocked"}:
                candidate_slugs.append(slug)

        return {
            "batch_date": batch_date,
            "candidate_slugs": candidate_slugs,
            "activity_timestamp": float(reviewable.get("activity_timestamp") or 0.0)
            if candidate_slugs
            else 0.0,
            "activity_at": str(reviewable.get("activity_at") or "") if candidate_slugs else "",
        }

    def resolve_latest_publish_candidate_batch(self) -> dict[str, Any]:
        """Resolve the most recently acted-on batch relevant to Menu 8."""
        if not self.queue_root.exists():
            return {
                "batch_date": "",
                "candidate_slugs": [],
                "activity_timestamp": 0.0,
                "activity_at": "",
            }
        candidates: list[dict[str, Any]] = []
        for path in self.queue_root.iterdir():
            if not path.is_dir() or path.name == "weeks":
                continue
            try:
                date.fromisoformat(path.name)
            except ValueError:
                continue
            details = self.publish_candidate_batch_details(path.name)
            if details["candidate_slugs"]:
                candidates.append(details)
        if not candidates:
            return {
                "batch_date": "",
                "candidate_slugs": [],
                "activity_timestamp": 0.0,
                "activity_at": "",
            }
        candidates.sort(key=lambda row: (float(row["activity_timestamp"]), str(row["batch_date"])))
        return candidates[-1]
