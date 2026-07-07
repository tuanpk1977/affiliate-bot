from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

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
                html="<html><body><h2>Affiliate disclosure</h2><p>We may earn a commission.</p></body></html>",
                research={"quality": {"total_verified_source_score": 70, "source_confidence": 80}, "quality_gate": {"passed": True}},
                review={"status": "ai_review_passed", "business_value": 70, "readability": 62, "requires_human_approval": False},
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

    def test_publish_gate_blocks_without_human_approval_when_required(self) -> None:
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
                html="<html><body><h2>Affiliate disclosure</h2><p>We may earn a commission.</p></body></html>",
                research={"quality": {"total_verified_source_score": 70, "source_confidence": 80}, "quality_gate": {"passed": True}},
                review={"status": "needs_human_review", "business_value": 70, "readability": 62, "requires_human_approval": True},
                human_approval={"status": "needs_human_review"},
                internal_links=[],
            )

            self.assertEqual(result["status"], "blocked")
            self.assertIn("human approval missing", result["failures"])


if __name__ == "__main__":
    unittest.main()
