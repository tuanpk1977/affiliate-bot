from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from modules.daily_editorial_workflow import DailyEditorialWorkflow
from modules.publish_gate import PublishGate


class PublishGateTests(unittest.TestCase):
    def test_publish_gate_approves_and_marks_local_publish(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            data_dir = root / "data"
            site_output = root / "site_output"
            target = site_output / "reviews" / "index.html"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("<html></html>", encoding="utf-8")
            gate = PublishGate(
                data_dir=data_dir,
                site_output_dir=site_output,
                config={
                    "enabled": True,
                    "minimum_verified_source_score": 35,
                    "minimum_knowledge_freshness": 20,
                    "minimum_business_score": 35,
                    "minimum_readability_score": 30,
                },
            )
            result = gate.evaluate(
                topic={"topic": "cursor pricing", "slug": "cursor-pricing"},
                title="Cursor Pricing 2026: Pricing, Pros, Cons",
                description="Buyer-focused Cursor pricing review with internal links and disclosure.",
                url="https://example.com/cursor-pricing/",
                html="<html lang=\"en\"><head><title>Cursor Pricing</title><meta name=\"description\" content=\"Buyer-focused Cursor pricing review.\"><link rel=\"canonical\" href=\"https://example.com/cursor-pricing/\"></head><body><h2>Affiliate disclosure</h2><p>We may earn a commission.</p></body></html>",
                research={"quality": {"total_verified_source_score": 70, "source_confidence": 80}, "quality_gate": {"passed": True}},
                review={"status": "ai_review_passed", "business_value": 70, "readability": 62, "publish_readiness": 82, "requires_human_approval": False},
                human_approval={"status": "human_approved"},
                internal_links=[("/reviews/", "Reviews")],
            )

            self.assertEqual(result["status"], "approved_for_publish")
            article_file = data_dir / "published_static_pages" / "cursor-pricing" / "index.html"
            site_file = site_output / "cursor-pricing" / "index.html"
            article_file.parent.mkdir(parents=True, exist_ok=True)
            site_file.parent.mkdir(parents=True, exist_ok=True)
            article_file.write_text("<html></html>", encoding="utf-8")
            site_file.write_text("<html></html>", encoding="utf-8")
            published = gate.mark_published_local("cursor-pricing", url="https://example.com/cursor-pricing/", article_file=article_file, site_file=site_file)

            self.assertIsNotNone(published)
            self.assertEqual(published["status"], "published_local")
            self.assertTrue((data_dir / "publish_queue.json").exists())
            self.assertTrue((data_dir / "publish_gate_report.json").exists())
            self.assertTrue((data_dir / "publish_gate_report.csv").exists())
            self.assertTrue((data_dir / "publish_gate_report.md").exists())

    def test_publish_gate_requires_human_approval_without_blocking_when_required(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            data_dir = root / "data"
            site_output = root / "site_output"
            gate = PublishGate(
                data_dir=data_dir,
                site_output_dir=site_output,
                config={
                    "enabled": True,
                    "minimum_verified_source_score": 35,
                    "minimum_knowledge_freshness": 20,
                    "minimum_business_score": 35,
                    "minimum_readability_score": 30,
                    "require_human_approval": True,
                },
            )
            result = gate.evaluate(
                topic={"topic": "cursor pricing", "slug": "cursor-pricing"},
                title="Cursor Pricing 2026: Pricing, Pros, Cons",
                description="Buyer-focused Cursor pricing review with internal links and disclosure.",
                url="https://example.com/cursor-pricing/",
                html="<html lang=\"en\"><head><title>Cursor Pricing</title><meta name=\"description\" content=\"Buyer-focused Cursor pricing review.\"><link rel=\"canonical\" href=\"https://example.com/cursor-pricing/\"></head><body><h2>Affiliate disclosure</h2><p>We may earn a commission.</p></body></html>",
                research={"quality": {"total_verified_source_score": 70, "source_confidence": 80}, "quality_gate": {"passed": True}},
                review={"status": "needs_human_review", "business_value": 70, "readability": 62, "publish_readiness": 78, "requires_human_approval": True},
                human_approval={"status": "needs_human_review"},
                internal_links=[],
            )

            self.assertEqual(result["status"], "needs_human_review")
            self.assertIn("human approval missing", result["pending_reviews"])
            self.assertEqual(result["failures"], [])

    def test_warning_only_with_human_approval_is_ready(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            data_dir = root / "data"
            site_output = root / "site_output"
            gate = PublishGate(
                data_dir=data_dir,
                site_output_dir=site_output,
                config={"enabled": True, "minimum_verified_source_score": 35, "minimum_knowledge_freshness": 20},
            )
            result = gate.evaluate(
                topic={"topic": "cursor pricing", "slug": "cursor-pricing"},
                title="Cursor Pricing 2026: Pricing, Pros, Cons",
                description="Buyer-focused Cursor pricing review with internal links and disclosure.",
                url="https://example.com/cursor-pricing/",
                html="<html lang=\"en\"><head><title>Cursor Pricing</title><meta name=\"description\" content=\"Buyer-focused Cursor pricing review.\"><link rel=\"canonical\" href=\"https://example.com/cursor-pricing/\"></head><body><h2>Affiliate disclosure</h2><p>We may earn a commission.</p></body></html>",
                research={"quality": {"total_verified_source_score": 18, "source_confidence": 15}, "quality_gate": {"passed": True}},
                review={"status": "needs_revision", "business_value": 58, "readability": 58, "publish_readiness": 58, "requires_human_approval": True},
                human_approval={"status": "human_approved"},
                internal_links=[],
            )

            self.assertEqual(result["status"], "approved_for_publish")
            self.assertEqual(result["failures"], [])
            self.assertGreaterEqual(len(result["warnings"]), 1)

    def test_hard_blocker_remains_blocked_after_high_score_and_approval(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            data_dir = root / "data"
            site_output = root / "site_output"
            gate = PublishGate(data_dir=data_dir, site_output_dir=site_output, config={"enabled": True})
            result = gate.evaluate(
                topic={"topic": "cursor pricing", "slug": "cursor-pricing"},
                title="Cursor Pricing 2026: Pricing, Pros, Cons",
                description="Buyer-focused Cursor pricing review with internal links and disclosure.",
                url="https://example.com/cursor-pricing/",
                html="<html lang=\"en\"><head><title>Cursor Pricing</title><meta name=\"description\" content=\"Buyer-focused Cursor pricing review.\"><link rel=\"canonical\" href=\"https://example.com/cursor-pricing/\"></head><body><p>No disclosure.</p></body></html>",
                research={"quality": {"total_verified_source_score": 90, "source_confidence": 90}, "quality_gate": {"passed": True}},
                review={"status": "ai_review_passed", "business_value": 90, "readability": 90, "publish_readiness": 90, "requires_human_approval": True},
                human_approval={"status": "human_approved"},
                internal_links=[],
            )

            self.assertEqual(result["status"], "blocked")
            self.assertIn("affiliate disclosure missing", result["hard_blockers"])

    def test_missing_reviews_are_pending_not_hard_failures(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            data_dir = root / "data"
            site_output = root / "site_output"
            gate = PublishGate(data_dir=data_dir, site_output_dir=site_output, config={"enabled": True})
            result = gate.evaluate(
                topic={"topic": "cursor pricing", "slug": "cursor-pricing"},
                title="Cursor Pricing 2026: Pricing, Pros, Cons",
                description="Buyer-focused Cursor pricing review with internal links and disclosure.",
                url="https://example.com/cursor-pricing/",
                html="<html lang=\"en\"><head><title>Cursor Pricing</title><meta name=\"description\" content=\"Buyer-focused Cursor pricing review.\"><link rel=\"canonical\" href=\"https://example.com/cursor-pricing/\"></head><body><h2>Affiliate disclosure</h2><p>We may earn a commission.</p></body></html>",
                research={},
                review={},
                human_approval={},
                internal_links=[],
            )

            self.assertEqual(result["review_states"]["ai_review"], "not_run")
            self.assertEqual(result["review_states"]["source_review"], "not_run")
            self.assertIn("source review not_run", result["pending_reviews"])

    def test_legacy_warning_failures_normalize_without_duplicate_blockers(self) -> None:
        normalized = PublishGate.normalize_existing_row(
            {
                "status": "blocked",
                "human_approval_passed": True,
                "failures": [
                    "verified source score failed",
                    "verified source score failed",
                    "knowledge freshness failed",
                    "AI review failed",
                ],
            }
        )

        self.assertEqual(normalized["normalized_status"], "approved_for_publish")
        self.assertEqual(normalized["hard_blockers"], [])
        self.assertEqual(normalized["warnings"].count("verified source score failed"), 1)

    def test_legacy_hard_failure_stays_blocked_after_approval(self) -> None:
        normalized = PublishGate.normalize_existing_row(
            {
                "status": "blocked",
                "human_approval_passed": True,
                "failures": ["affiliate disclosure missing", "human approval missing"],
            }
        )

        self.assertEqual(normalized["normalized_status"], "blocked")
        self.assertIn("affiliate disclosure missing", normalized["hard_blockers"])

    def test_workflow_status_counts_legacy_warning_rows_as_ready_or_human_review(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            data_dir = root / "data"
            site_output = root / "site_output"
            queue_dir = data_dir / "editorial_queue" / "2026-07-11"
            queue_dir.mkdir(parents=True, exist_ok=True)
            (queue_dir / "topics.json").write_text(
                """{
  "date": "2026-07-11",
  "week_start": "2026-07-06",
  "week_end": "2026-07-12",
  "topics": [
    {"slug": "approved-warning", "status": "approved", "draft_file": ""},
    {"slug": "pending-warning", "status": "drafted", "draft_file": ""}
  ]
}
""",
                encoding="utf-8",
            )
            (data_dir / "publish_queue.json").write_text(
                """[
  {
    "slug": "approved-warning",
    "status": "blocked",
    "human_approval_passed": true,
    "failures": ["verified source score failed", "AI review failed"]
  },
  {
    "slug": "pending-warning",
    "status": "blocked",
    "human_approval_passed": false,
    "failures": ["human approval missing", "knowledge freshness failed"]
  }
]
""",
                encoding="utf-8",
            )
            workflow = DailyEditorialWorkflow(root=root, data_dir=data_dir, site_output_dir=site_output)

            summary = workflow.status(batch_date="2026-07-11")

            self.assertEqual(summary["ready_for_publish"], 1)
            self.assertEqual(summary["human_approval_required"], 1)
            self.assertEqual(summary["publish_blocked"], 0)


if __name__ == "__main__":
    unittest.main()
