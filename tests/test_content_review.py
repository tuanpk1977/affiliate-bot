from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from modules.content_review import ContentReviewEngine


class ContentReviewTests(unittest.TestCase):
    def test_ai_review_passes_for_complete_content(self) -> None:
        with TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir) / "data"
            engine = ContentReviewEngine(data_dir=data_dir, config={"minimum_word_count": 50, "minimum_publish_readiness": 50})
            html = """
            <html><body>
            <section><h2>Affiliate disclosure</h2><p>We may earn a commission.</p></section>
            <p>Cursor pricing review for teams helps buyers compare pricing, integrations, workflows, and alternatives.</p>
            <p>This guide includes multiple verification notes, feature tradeoffs, and internal link references for practical buying decisions.</p>
            <p>More details help the article stay readable and useful for software comparisons across several categories and buyer needs.</p>
            </body></html>
            """
            result = engine.review_content(
                topic={"topic": "cursor pricing review", "slug": "cursor-pricing-review", "estimated_business_value": "high"},
                html=html,
                title="Cursor Pricing Review 2026: Pricing, Pros, Cons",
                description="Buyer-focused review of Cursor pricing, alternatives, internal links, and affiliate disclosure for software teams.",
                url="https://example.com/cursor-pricing-review/",
                internal_links=[("/reviews/", "Reviews"), ("/comparisons/", "Comparisons")],
                warnings=[],
                research={"quality": {"overall_score": 82, "source_quality": 76, "total_verified_source_score": 72, "affiliate_readiness": 80}},
                planning={"coverage_score": 78, "keyword": "cursor pricing review"},
            )

            self.assertEqual(result["status"], "ai_review_passed")
            self.assertTrue(result["publishable"])
            self.assertTrue((data_dir / "content_review_queue.json").exists())
            self.assertTrue((data_dir / "content_review_report.json").exists())
            self.assertTrue((data_dir / "content_review_report.csv").exists())
            self.assertTrue((data_dir / "content_review_report.md").exists())

    def test_ai_review_flags_revision_for_thin_content(self) -> None:
        with TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir) / "data"
            engine = ContentReviewEngine(data_dir=data_dir)
            result = engine.review_content(
                topic={"topic": "thin draft", "slug": "thin-draft", "estimated_business_value": "low"},
                html="<html><body><p>Short draft.</p></body></html>",
                title="Thin Draft",
                description="Short.",
                url="https://example.com/thin-draft/",
                internal_links=[],
                warnings=["manual verification required"],
                research={"quality": {"overall_score": 20, "source_quality": 10, "total_verified_source_score": 5, "affiliate_readiness": 15}},
                planning={"coverage_score": 15, "keyword": "thin draft"},
            )

            self.assertEqual(result["status"], "needs_revision")
            self.assertFalse(result["publishable"])
            self.assertTrue(result["failures"])


if __name__ == "__main__":
    unittest.main()
