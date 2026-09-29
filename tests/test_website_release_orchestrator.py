from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import MagicMock, patch

from modules.website_release_orchestrator import (
    RELEASE_STATE_DEPLOYED,
    RELEASE_STATE_DEPLOY_FAILED,
    RELEASE_STATE_DEPLOYING,
    RELEASE_STATE_NEEDS_HUMAN_REVIEW,
    RELEASE_STATE_PUBLISHING,
    RELEASE_STATE_PUBLISH_FAILED,
    RELEASE_STATE_READY_FOR_PUBLISH,
    RELEASE_STATE_VERIFY_FAILED,
    RELEASE_STATE_WEBSITE_VERIFIED,
    WebsiteReleaseOrchestrator,
)


class WebsiteReleaseOrchestratorTests(unittest.TestCase):
    def _make_workflow(self, *, root: Path, data_dir: Path, site_output_dir: Path, preflight: dict, publish_result: dict | None = None) -> MagicMock:
        workflow = MagicMock()
        workflow.exact_slug_preflight.return_value = preflight
        workflow.publish_exact_slug.return_value = publish_result or {}
        return workflow

    def test_not_human_approved_blocks_publish(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            data_dir = root / "data"
            site_output_dir = root / "site_output"
            upload_root = root / "upload"
            review_root = root / "review"
            for d in (data_dir, site_output_dir, upload_root, review_root):
                d.mkdir(parents=True, exist_ok=True)

            preflight = {
                "topic": {"task_id": "task-1"},
                "approved_by": "",
                "approval_binding_status": "MISSING",
                "publish_gate": "READY_FOR_PUBLISH",
                "blockers": ["current human approval is missing"],
                "warnings": [],
            }
            workflow = self._make_workflow(
                root=root,
                data_dir=data_dir,
                site_output_dir=site_output_dir,
                preflight=preflight,
            )
            orchestrator = WebsiteReleaseOrchestrator(
                root=root,
                data_dir=data_dir,
                site_output_dir=site_output_dir,
                upload_root=upload_root,
                review_root=review_root,
                workflow=workflow,
            )
            result = orchestrator.release_article(slug="target-slug")
            self.assertEqual(result.release_state, RELEASE_STATE_NEEDS_HUMAN_REVIEW)
            self.assertFalse(result.to_dict()["success"])

    def test_human_approved_but_binding_mismatch_blocks_publish(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            data_dir = root / "data"
            site_output_dir = root / "site_output"
            upload_root = root / "upload"
            review_root = root / "review"
            for d in (data_dir, site_output_dir, upload_root, review_root):
                d.mkdir(parents=True, exist_ok=True)

            preflight = {
                "topic": {"task_id": "task-1"},
                "approved_by": "editor",
                "approval_binding_status": "MISMATCH",
                "publish_gate": "READY_FOR_PUBLISH",
                "blockers": [],
                "warnings": [],
            }
            workflow = self._make_workflow(
                root=root,
                data_dir=data_dir,
                site_output_dir=site_output_dir,
                preflight=preflight,
            )
            orchestrator = WebsiteReleaseOrchestrator(
                root=root,
                data_dir=data_dir,
                site_output_dir=site_output_dir,
                upload_root=upload_root,
                review_root=review_root,
                workflow=workflow,
            )
            result = orchestrator.release_article(slug="target-slug")
            self.assertEqual(result.release_state, RELEASE_STATE_PUBLISH_FAILED)
            self.assertEqual(result.failure_stage, "approval_binding_gate")

    def test_publish_exact_slug_failure_returns_publish_failed(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            data_dir = root / "data"
            site_output_dir = root / "site_output"
            upload_root = root / "upload"
            review_root = root / "review"
            for d in (data_dir, site_output_dir, upload_root, review_root):
                d.mkdir(parents=True, exist_ok=True)

            preflight = {
                "topic": {"task_id": "task-1"},
                "approved_by": "editor",
                "approval_binding_status": "MATCHED",
                "publish_gate": "READY_FOR_PUBLISH",
                "blockers": [],
                "warnings": [],
            }
            workflow = self._make_workflow(
                root=root,
                data_dir=data_dir,
                site_output_dir=site_output_dir,
                preflight=preflight,
            )
            orchestrator = WebsiteReleaseOrchestrator(
                root=root,
                data_dir=data_dir,
                site_output_dir=site_output_dir,
                upload_root=upload_root,
                review_root=review_root,
                workflow=workflow,
            )
            workflow.publish_exact_slug.side_effect = RuntimeError("publish boom")
            result = orchestrator.release_article(slug="target-slug")
            self.assertEqual(result.release_state, RELEASE_STATE_PUBLISH_FAILED)
            self.assertEqual(result.failure_stage, "publish")

    def test_verification_failure_returns_verify_failed(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            data_dir = root / "data"
            site_output_dir = root / "site_output"
            upload_root = root / "upload"
            review_root = root / "review"
            for d in (data_dir, site_output_dir, upload_root, review_root):
                d.mkdir(parents=True, exist_ok=True)

            preflight = {
                "topic": {"task_id": "task-1"},
                "approved_by": "editor",
                "approval_binding_status": "MATCHED",
                "publish_gate": "READY_FOR_PUBLISH",
                "blockers": [],
                "warnings": [],
            }
            publish_result = {
                "published_count": 1,
                "published": [{"url": "https://example.com/target-slug/", "slug": "target-slug"}],
                "skipped_count": 0,
                "source_binding_checks": [],
                "post_push_live_check": {"status": "pages_pending", "message": "Pages pending", "items": [{"slug": "target-slug", "url": "https://example.com/target-slug/", "status": "pending", "http_status": 0}]},
            }
            workflow = self._make_workflow(
                root=root,
                data_dir=data_dir,
                site_output_dir=site_output_dir,
                preflight=preflight,
                publish_result=publish_result,
            )
            orchestrator = WebsiteReleaseOrchestrator(
                root=root,
                data_dir=data_dir,
                site_output_dir=site_output_dir,
                upload_root=upload_root,
                review_root=review_root,
                workflow=workflow,
            )
            result = orchestrator.release_article(slug="target-slug")
            self.assertEqual(result.release_state, RELEASE_STATE_VERIFY_FAILED)
            self.assertEqual(result.failure_stage, "verification")

    def test_successful_release_returns_website_verified(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            data_dir = root / "data"
            site_output_dir = root / "site_output"
            upload_root = root / "upload"
            review_root = root / "review"
            for d in (data_dir, site_output_dir, upload_root, review_root):
                d.mkdir(parents=True, exist_ok=True)

            preflight = {
                "topic": {"task_id": "task-1"},
                "approved_by": "editor",
                "approval_binding_status": "MATCHED",
                "publish_gate": "READY_FOR_PUBLISH",
                "blockers": [],
                "warnings": [],
            }
            publish_result = {
                "published_count": 1,
                "published": [{"url": "https://example.com/target-slug/", "slug": "target-slug"}],
                "skipped_count": 0,
                "source_binding_checks": [],
                "post_push_live_check": {"status": "live_ok", "message": "Live OK", "items": [{"slug": "target-slug", "url": "https://example.com/target-slug/", "status": "live", "http_status": 200}]},
            }
            workflow = self._make_workflow(
                root=root,
                data_dir=data_dir,
                site_output_dir=site_output_dir,
                preflight=preflight,
                publish_result=publish_result,
            )
            orchestrator = WebsiteReleaseOrchestrator(
                root=root,
                data_dir=data_dir,
                site_output_dir=site_output_dir,
                upload_root=upload_root,
                review_root=review_root,
                workflow=workflow,
            )
            result = orchestrator.release_article(slug="target-slug")
            self.assertEqual(result.release_state, RELEASE_STATE_WEBSITE_VERIFIED)
            self.assertTrue(result.to_dict()["success"])
            self.assertTrue(result.to_dict()["terminal"])

    def test_idempotent_successful_release_is_safe(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            data_dir = root / "data"
            site_output_dir = root / "site_output"
            upload_root = root / "upload"
            review_root = root / "review"
            for d in (data_dir, site_output_dir, upload_root, review_root):
                d.mkdir(parents=True, exist_ok=True)

            preflight = {
                "topic": {"task_id": "task-1"},
                "approved_by": "editor",
                "approval_binding_status": "MATCHED",
                "publish_gate": "READY_FOR_PUBLISH",
                "blockers": [],
                "warnings": [],
            }
            publish_result = {
                "published_count": 1,
                "published": [{"url": "https://example.com/target-slug/", "slug": "target-slug"}],
                "skipped_count": 0,
                "source_binding_checks": [],
                "post_push_live_check": {"status": "live_ok", "message": "Live OK", "items": [{"slug": "target-slug", "url": "https://example.com/target-slug/", "status": "live", "http_status": 200}]},
            }
            workflow = self._make_workflow(
                root=root,
                data_dir=data_dir,
                site_output_dir=site_output_dir,
                preflight=preflight,
                publish_result=publish_result,
            )
            orchestrator = WebsiteReleaseOrchestrator(
                root=root,
                data_dir=data_dir,
                site_output_dir=site_output_dir,
                upload_root=upload_root,
                review_root=review_root,
                workflow=workflow,
            )
            first = orchestrator.release_article(slug="target-slug")
            second = orchestrator.release_article(slug="target-slug")
            self.assertEqual(first.release_state, RELEASE_STATE_WEBSITE_VERIFIED)
            self.assertEqual(second.release_state, RELEASE_STATE_WEBSITE_VERIFIED)
            self.assertTrue(first.to_dict()["terminal"])
            self.assertTrue(second.to_dict()["terminal"])

    def test_current_release_state_helper_maps_publish_queue(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            data_dir = root / "data"
            data_dir.mkdir(parents=True, exist_ok=True)
            publish_queue = [
                {
                    "slug": "target-slug",
                    "status": "pushed",
                    "current_revision_id": "rev-1",
                    "current_content_hash": "HASH1",
                    "deployment_state": "",
                    "post_push_live_status": "",
                }
            ]
            (data_dir / "publish_queue.json").write_text(json.dumps(publish_queue, indent=2), encoding="utf-8")
            state = WebsiteReleaseOrchestrator.current_release_state_for_slug(slug="target-slug", data_dir=data_dir)
            self.assertEqual(state, RELEASE_STATE_DEPLOYED)

    def test_social_is_not_started_by_this_checkpoint(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            data_dir = root / "data"
            site_output_dir = root / "site_output"
            upload_root = root / "upload"
            review_root = root / "review"
            for d in (data_dir, site_output_dir, upload_root, review_root):
                d.mkdir(parents=True, exist_ok=True)

            preflight = {
                "topic": {"task_id": "task-1"},
                "approved_by": "editor",
                "approval_binding_status": "MATCHED",
                "publish_gate": "READY_FOR_PUBLISH",
                "blockers": [],
                "warnings": [],
            }
            publish_result = {
                "published_count": 1,
                "published": [{"url": "https://example.com/target-slug/", "slug": "target-slug"}],
                "skipped_count": 0,
                "source_binding_checks": [],
                "post_push_live_check": {"status": "live_ok", "message": "Live OK", "items": [{"slug": "target-slug", "url": "https://example.com/target-slug/", "status": "live", "http_status": 200}]},
            }
            workflow = self._make_workflow(
                root=root,
                data_dir=data_dir,
                site_output_dir=site_output_dir,
                preflight=preflight,
                publish_result=publish_result,
            )
            orchestrator = WebsiteReleaseOrchestrator(
                root=root,
                data_dir=data_dir,
                site_output_dir=site_output_dir,
                upload_root=upload_root,
                review_root=review_root,
                workflow=workflow,
            )
            result = orchestrator.release_article(slug="target-slug")
            self.assertEqual(result.release_state, RELEASE_STATE_WEBSITE_VERIFIED)
            social_calls = [call.args[0] for call in workflow.method_calls if call.args and str(call.args[0]).startswith("prepare_social")]
            self.assertEqual(social_calls, [])
            self.assertNotIn("social", {str(w) for w in result.warnings})


if __name__ == "__main__":
    unittest.main()
