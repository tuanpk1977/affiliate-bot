from __future__ import annotations

import hashlib
import json
import os
import unittest
from datetime import UTC, date, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from modules.daily_editorial_workflow import (
    BATCH_STATE_DRAFT_READY,
    BATCH_STATE_HUMAN_APPROVED,
    BATCH_STATE_PUBLISHED,
    BATCH_STATE_QUEUE_CREATED,
    BATCH_STATE_READY_FOR_PUBLISH,
    BATCH_STATE_UNDER_REVIEW,
    BATCH_STATE_WRITING,
    DailyEditorialWorkflow,
)


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _tree_fingerprint(root: Path) -> list[tuple[str, str, int]]:
    if not root.exists():
        return []
    result: list[tuple[str, str, int]] = []
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
        relative = path.relative_to(root).as_posix()
        if path.is_dir():
            result.append((relative + "/", "directory", 0))
        else:
            payload = path.read_bytes()
            result.append((relative, hashlib.sha256(payload).hexdigest(), len(payload)))
    return result


class EditorialQueueResolutionCharacterizationTests(unittest.TestCase):
    def _workflow(self, root: Path) -> DailyEditorialWorkflow:
        return DailyEditorialWorkflow(
            root=root,
            data_dir=root / "data",
            site_output_dir=root / "site_output",
        )

    def _queue(self, root: Path, batch_date: str, topics: object) -> Path:
        path = root / "data" / "editorial_queue" / batch_date / "topics.json"
        _write_json(path, {"date": batch_date, "topics": topics})
        return path

    def _draft(self, root: Path, slug: str, *, text: str = "draft") -> Path:
        path = root / "data" / "production_article_drafts" / slug / "index.html"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def test_queue_dir_load_and_latest_date_contract(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workflow = self._workflow(root)
            self.assertEqual(workflow._queue_dir("2026-09-01"), root / "data" / "editorial_queue" / "2026-09-01")
            self.assertEqual(workflow.latest_queue_date(), "")

            with self.assertRaisesRegex(FileNotFoundError, r"Editorial queue not found for 2026-09-01"):
                workflow._load_queue("2026-09-01")

            self._queue(root, "2026-09-01", [])
            self._queue(root, "2026-09-03", [{"slug": "latest"}])
            (root / "data" / "editorial_queue" / "weeks").mkdir()
            (root / "data" / "editorial_queue" / "not-a-date").mkdir()
            (root / "data" / "editorial_queue" / "2026-09-04").mkdir()
            self.assertEqual(workflow.latest_queue_date(), "2026-09-03")
            self.assertEqual(workflow._load_queue("2026-09-03")["topics"], [{"slug": "latest"}])

    def test_load_queue_empty_and_invalid_json_raise_current_exception(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workflow = self._workflow(root)
            for batch_date, content in (("2026-09-01", "{}\n"), ("2026-09-02", ""), ("2026-09-03", "{bad")):
                path = root / "data" / "editorial_queue" / batch_date / "topics.json"
                path.parent.mkdir(parents=True)
                path.write_text(content, encoding="utf-8")
                with self.subTest(batch_date=batch_date):
                    with self.assertRaisesRegex(FileNotFoundError, f"Editorial queue not found for {batch_date}"):
                        workflow._load_queue(batch_date)

    def test_resolve_batch_date_explicit_missing_root_and_activity_fallbacks(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workflow = self._workflow(root)
            self.assertEqual(workflow.resolve_batch_date(" 2026-08-01 "), "2026-08-01")
            self.assertEqual(workflow.resolve_batch_date("latest"), "latest")
            self.assertEqual(workflow.resolve_batch_date(None), date.today().isoformat())

            self._queue(root, "2026-08-01", [{"slug": "active"}])
            self._queue(root, "2026-08-02", [])
            self._draft(root, "active")
            self.assertEqual(workflow.resolve_batch_date("latest", require_activity=True), "2026-08-01")
            self.assertEqual(workflow.resolve_batch_date("latest", require_activity=False), "2026-08-02")

            self._draft(root, "active").unlink()
            self.assertEqual(workflow.resolve_batch_date("latest", require_activity=True), "2026-08-02")

    def test_batch_state_precedence_and_empty_shapes(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workflow = self._workflow(root)
            self.assertEqual(workflow.batch_state("2026-08-01"), "")
            self._queue(root, "2026-08-01", [])
            self.assertEqual(workflow.batch_state("2026-08-01"), BATCH_STATE_QUEUE_CREATED)

            cases = [
                ("2026-08-02", {"slug": "writing", "status": "writing"}, None, None, BATCH_STATE_WRITING),
                ("2026-08-03", {"slug": "draft"}, "draft", None, BATCH_STATE_DRAFT_READY),
                ("2026-08-04", {"slug": "review", "status": "needs_review"}, None, None, BATCH_STATE_UNDER_REVIEW),
                ("2026-08-05", {"slug": "approved", "status": "approved"}, None, None, BATCH_STATE_HUMAN_APPROVED),
                ("2026-08-06", {"slug": "ready"}, None, "approved_for_publish", BATCH_STATE_READY_FOR_PUBLISH),
                ("2026-08-07", {"slug": "published", "status": "published"}, None, None, BATCH_STATE_PUBLISHED),
            ]
            publish_rows: list[dict[str, object]] = []
            for batch_date, item, draft, publish_status, expected in cases:
                self._queue(root, batch_date, [item])
                if draft:
                    self._draft(root, str(item["slug"]))
                if publish_status:
                    publish_rows.append({"slug": item["slug"], "status": publish_status})
                _write_json(root / "data" / "publish_queue.json", publish_rows)
                with self.subTest(batch_date=batch_date):
                    self.assertEqual(workflow.batch_state(batch_date), expected)

            self._queue(
                root,
                "2026-08-08",
                [{"slug": "review", "status": "needs_review"}, {"slug": "published", "status": "published"}],
            )
            self.assertEqual(workflow.batch_state("2026-08-08"), BATCH_STATE_PUBLISHED)

    def test_resolve_latest_batch_by_state_ignores_invalid_directories(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workflow = self._workflow(root)
            self.assertEqual(workflow.resolve_latest_batch_by_state({BATCH_STATE_QUEUE_CREATED}), "")
            self._queue(root, "2026-08-01", [])
            self._queue(root, "2026-08-03", [])
            (root / "data" / "editorial_queue" / "invalid").mkdir()
            (root / "data" / "editorial_queue" / "weeks").mkdir()
            self.assertEqual(workflow.resolve_latest_batch_by_state({BATCH_STATE_QUEUE_CREATED}), "2026-08-03")
            self.assertEqual(workflow.resolve_latest_batch_by_state({BATCH_STATE_PUBLISHED}), "")

    def test_activity_timestamp_contract(self) -> None:
        workflow_type = DailyEditorialWorkflow
        self.assertEqual(workflow_type._activity_timestamp(None), 0.0)
        self.assertEqual(workflow_type._activity_timestamp("bad"), 0.0)
        expected = datetime(2026, 8, 1, 12, 30, tzinfo=UTC).timestamp()
        self.assertEqual(workflow_type._activity_timestamp("2026-08-01T12:30:00Z"), expected)
        self.assertEqual(workflow_type._activity_timestamp("2026-08-01T12:30:00"), expected)
        self.assertIsInstance(workflow_type._activity_timestamp("2026-08-01T12:30:00+00:00"), float)

    def test_reviewable_details_are_item_level_ordered_and_read_only(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workflow = self._workflow(root)
            batch_date = "2026-08-15"
            self._queue(
                root,
                batch_date,
                [
                    {"slug": "zeta", "status": "drafted", "updated_at": "2026-08-20T10:00:00Z"},
                    {"slug": "terminal", "status": "published"},
                    {"slug": "alpha", "status": "drafted"},
                    {"slug": "zeta", "status": "drafted"},
                    "invalid",
                ],
            )
            self._draft(root, "zeta")
            self._draft(root, "alpha")
            _write_json(root / "data" / "publish_queue.json", [{"slug": "terminal", "status": "live"}])
            before = _tree_fingerprint(root)

            result = workflow.reviewable_batch_details(batch_date)

            self.assertEqual(result["batch_date"], batch_date)
            self.assertEqual(result["reviewable_slugs"], ["zeta", "alpha", "zeta"])
            self.assertGreaterEqual(result["activity_timestamp"], workflow._activity_timestamp("2026-08-20T10:00:00Z"))
            self.assertIsInstance(result["activity_at"], str)
            self.assertEqual(_tree_fingerprint(root), before)

    def test_latest_reviewable_uses_activity_then_date_tie_break(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workflow = self._workflow(root)
            for batch_date, slug in (("2026-08-10", "old"), ("2026-08-20", "new")):
                self._queue(root, batch_date, [{"slug": slug, "status": "drafted"}])
                draft = self._draft(root, slug)
                os.utime(draft, (1_700_000_000, 1_700_000_000))
            self.assertEqual(workflow.resolve_latest_reviewable_batch()["batch_date"], "2026-08-20")

            _write_json(
                root / "data" / "human_approval_queue.json",
                [{"slug": "old", "status": "needs_human_review", "reviewed_at": "2026-09-01T00:00:00Z"}],
            )
            self.assertEqual(workflow.resolve_latest_reviewable_batch()["batch_date"], "2026-08-10")

    def test_publish_candidate_details_normalize_deduplicate_and_sort(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workflow = self._workflow(root)
            batch_date = "2026-08-15"
            self._queue(
                root,
                batch_date,
                [
                    {"slug": "zeta", "status": "approved"},
                    {"slug": "alpha", "status": "drafted"},
                    {"slug": "zeta", "status": "approved"},
                    {"slug": "ignored", "status": "drafted"},
                ],
            )
            for slug in ("zeta", "alpha", "ignored"):
                self._draft(root, slug)
            _write_json(root / "data" / "human_approval_queue.json", [{"slug": "zeta", "status": "human_approved"}])
            _write_json(
                root / "data" / "publish_queue.json",
                [{"slug": "alpha", "status": "blocked", "hard_blockers": ["current blocker"]}],
            )

            result = workflow.publish_candidate_batch_details(batch_date)

            self.assertEqual(result["candidate_slugs"], ["alpha", "zeta"])
            self.assertGreater(result["activity_timestamp"], 0.0)

    def test_latest_publish_candidate_skips_newer_terminal_batch(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workflow = self._workflow(root)
            self._queue(root, "2026-08-15", [{"slug": "approved", "status": "approved"}])
            self._queue(root, "2026-08-26", [{"slug": "live", "status": "published"}])
            self._draft(root, "approved")
            self._draft(root, "live")
            _write_json(root / "data" / "human_approval_queue.json", [{"slug": "approved", "status": "human_approved"}])
            _write_json(root / "data" / "publish_queue.json", [{"slug": "live", "status": "live"}])
            self.assertEqual(workflow.resolve_latest_publish_candidate_batch()["batch_date"], "2026-08-15")

    def test_missing_detail_shapes_and_legacy_access(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workflow = self._workflow(root)
            self.assertEqual(
                workflow.reviewable_batch_details("2026-08-01"),
                {"batch_date": "2026-08-01", "reviewable_slugs": [], "activity_timestamp": 0.0, "activity_at": ""},
            )
            self.assertEqual(
                workflow.resolve_latest_reviewable_batch(),
                {"batch_date": "", "reviewable_slugs": [], "activity_timestamp": 0.0, "activity_at": ""},
            )
            self.assertEqual(
                workflow.resolve_latest_publish_candidate_batch(),
                {"batch_date": "", "candidate_slugs": [], "activity_timestamp": 0.0, "activity_at": ""},
            )
            for name in (
                "_queue_dir",
                "_load_queue",
                "latest_queue_date",
                "resolve_batch_date",
                "batch_state",
                "resolve_latest_batch_by_state",
                "_activity_timestamp",
                "reviewable_batch_details",
                "resolve_latest_reviewable_batch",
                "publish_candidate_batch_details",
                "resolve_latest_publish_candidate_batch",
            ):
                self.assertTrue(callable(getattr(workflow, name)))


if __name__ == "__main__":
    unittest.main()
