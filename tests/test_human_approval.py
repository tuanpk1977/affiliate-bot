from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from modules.human_approval import HumanApprovalWorkflow


class HumanApprovalTests(unittest.TestCase):
    def test_optional_human_approval_still_requires_manual_review(self) -> None:
        with TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir) / "data"
            workflow = HumanApprovalWorkflow(data_dir=data_dir, config={"required": False})
            entry = workflow.sync_review(
                {
                    "slug": "cursor-pricing",
                    "topic": "cursor pricing",
                    "status": "ai_review_passed",
                    "reviewed_at": "2026-07-07T00:00:00+00:00",
                    "requires_human_approval": False,
                    "failures": [],
                }
            )

            self.assertEqual(entry["status"], "needs_human_review")
            self.assertTrue(entry["required"])
            self.assertEqual(entry["approved_by"], "")
            self.assertTrue((data_dir / "human_approval_queue.json").exists())

    def test_required_human_approval_supports_approve_and_reject(self) -> None:
        with TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir) / "data"
            workflow = HumanApprovalWorkflow(data_dir=data_dir, config={"required": True})
            entry = workflow.sync_review(
                {
                    "slug": "cursor-pricing",
                    "topic": "cursor pricing",
                    "status": "needs_human_review",
                    "reviewed_at": "2026-07-07T00:00:00+00:00",
                    "requires_human_approval": True,
                    "failures": [],
                }
            )
            self.assertEqual(entry["status"], "needs_human_review")

            approved = workflow.approve("cursor-pricing", approver="editor")
            self.assertIsNotNone(approved)
            self.assertEqual(approved["status"], "human_approved")

            rejected = workflow.reject("cursor-pricing", approver="editor", reason="needs revision")
            self.assertIsNotNone(rejected)
            self.assertEqual(rejected["status"], "rejected")


if __name__ == "__main__":
    unittest.main()
