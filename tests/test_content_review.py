from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from modules.content_review import ContentReviewEngine


class ContentReviewTests(unittest.TestCase):
    def test_ai_review_passes_for_complete_content(self) -> None:
        with TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir) / "data"
            engine = ContentReviewEngine(
                data_dir=data_dir,
                config={
                    "minimum_word_count": 50,
                    "minimum_publish_readiness": 50,
                    "manual_approval_article_types": [],
                    "manual_approval_title_markers": [],
                },
            )
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

    def test_pricing_and_comparison_content_require_human_review_when_ai_passes(self) -> None:
        with TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir) / "data"
            engine = ContentReviewEngine(
                data_dir=data_dir,
                config={
                    "minimum_word_count": 40,
                    "minimum_publish_readiness": 50,
                    "minimum_source_quality": 0,
                    "minimum_factual_quality": 0,
                    "minimum_seo_quality": 0,
                    "minimum_business_value": 0,
                    "minimum_readability_score": 0,
                    "minimum_publish_readiness": 40,
                    "manual_approval_article_types": ["pricing", "comparison", "review", "product_recommendation"],
                    "manual_approval_title_markers": [],
                },
            )
            html = """
            <html><body>
            <section><h2>Affiliate disclosure</h2><p>We may earn a commission.</p></section>
            <p>Comprehensive comparison with enough text to pass all local review thresholds for this test fixture.</p>
            <p>Additional content about pricing, alternatives, and buying decisions to ensure the draft is reviewable.</p>
            <p>Internal link context and source verification notes are present for the review engine.</p>
            </body></html>
            """
            result = engine.review_content(
                topic={"topic": "cursor vs windsurf pricing comparison", "slug": "cursor-vs-windsurf-pricing-comparison", "content_type": "comparison", "estimated_business_value": "high"},
                html=html,
                title="Cursor vs Windsurf Pricing Comparison 2026",
                description="Comparison of Cursor and Windsurf pricing, workflow fit, and internal links for buyers.",
                url="https://example.com/cursor-vs-windsurf-pricing-comparison/",
                internal_links=[("/comparisons/", "Comparisons")],
                warnings=[],
                research={"quality": {"overall_score": 82, "source_quality": 76, "total_verified_source_score": 72, "affiliate_readiness": 80}},
                planning={"coverage_score": 78, "keyword": "cursor vs windsurf pricing comparison"},
            )

            self.assertEqual(result["status"], "needs_human_review")
            self.assertTrue(result["requires_human_approval"])

    def test_same_slug_is_not_treated_as_duplicate_content(self) -> None:
        with TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir) / "data"
            engine = ContentReviewEngine(
                data_dir=data_dir,
                config={
                    "minimum_word_count": 20,
                    "minimum_publish_readiness": 40,
                    "minimum_source_quality": 0,
                    "minimum_factual_quality": 0,
                    "minimum_seo_quality": 0,
                    "minimum_business_value": 0,
                    "minimum_readability_score": 0,
                    "manual_approval_article_types": [],
                    "manual_approval_title_markers": [],
                },
            )
            html = """
            <html><body>
            <section><h2>Affiliate disclosure</h2><p>We may earn a commission.</p></section>
            <p>This draft has enough substance to pass local review checks and should not fail for duplicating itself.</p>
            <p>It includes workflow guidance, internal link context, and pricing verification reminders.</p>
            </body></html>
            """
            first = engine.review_content(
                topic={"topic": "best ai productivity software", "slug": "best-ai-productivity-software", "estimated_business_value": "high"},
                html=html,
                title="Best AI Productivity Software 2026",
                description="Guide to evaluating AI productivity software with pricing checks and workflow notes.",
                url="https://example.com/best-ai-productivity-software/",
                internal_links=[("/reviews/", "Reviews")],
                warnings=[],
                research={"quality": {"overall_score": 82, "source_quality": 76, "total_verified_source_score": 72, "affiliate_readiness": 80}},
                planning={"coverage_score": 78, "keyword": "best ai productivity software"},
            )
            second = engine.review_content(
                topic={"topic": "best ai productivity software", "slug": "best-ai-productivity-software", "estimated_business_value": "high"},
                html=html,
                title="Best AI Productivity Software 2026",
                description="Guide to evaluating AI productivity software with pricing checks and workflow notes.",
                url="https://example.com/best-ai-productivity-software/",
                internal_links=[("/reviews/", "Reviews")],
                warnings=[],
                research={"quality": {"overall_score": 82, "source_quality": 76, "total_verified_source_score": 72, "affiliate_readiness": 80}},
                planning={"coverage_score": 78, "keyword": "best ai productivity software"},
            )

            self.assertEqual(first["status"], "ai_review_passed")
            self.assertEqual(second["status"], "ai_review_passed")
            self.assertEqual(second["duplicate_content_risk"], 10.0)


if __name__ == "__main__":
    unittest.main()
