from __future__ import annotations

import unittest

from modules.pre_publish_quality_gate import PrePublishQualityGate


class ContentQualityGateTest(unittest.TestCase):
    def test_gate_scores_high_quality_article_as_report_only(self) -> None:
        gate = PrePublishQualityGate(minimum_score=85)
        content = """
        # Best AI Coding Tools for Startups
        This review compares the best AI coding tools for startups with a practical buying guide.
        We explain pricing, speed, and workflow fit for early-stage teams.
        The article includes a clear affiliate disclosure and a direct CTA to verify pricing before buying.
        
        ## Why this matters
        Startups need tools that support fast iteration and reliable collaboration.
        
        ### FAQ
        What is the best AI coding tool for startups?
        
        [Read the full review](/review/github-copilot/)
        [Compare Cursor and Windsurf](/comparisons/cursor-vs-windsurf/)
        """
        result = gate.evaluate_article(
            title="Best AI Coding Tools for Startups",
            content=content,
            meta_description="Compare the best AI coding tools for startups and see which tool fits your workflow, pricing, and speed needs.",
            slug="best-ai-coding-tools-startups",
            topic="AI coding tools",
            existing_titles=["Best AI Coding Tools for 2024"],
            existing_h1s=["AI Coding Tools for Teams"],
            existing_keywords=["AI coding tools"],
            internal_links=["/review/github-copilot/", "/comparisons/cursor-vs-windsurf/"],
            schema_hints=["Article", "FAQPage"],
        )

        self.assertTrue(result.report_only)
        self.assertFalse(result.publish_blocked)
        self.assertGreaterEqual(result.overall_score, 85)
        self.assertGreaterEqual(result.title_quality, 80)
        self.assertGreaterEqual(result.meta_description_quality, 80)
        self.assertGreaterEqual(result.search_intent_match, 80)
        self.assertGreaterEqual(result.duplicate_keyword_risk, 80)
        self.assertGreaterEqual(result.duplicate_h1_title_risk, 80)
        self.assertGreaterEqual(result.thin_content, 80)
        self.assertGreaterEqual(result.eeat_signals, 80)
        self.assertGreaterEqual(result.internal_links, 80)
        self.assertGreaterEqual(result.schema_hints, 80)
        self.assertGreaterEqual(result.affiliate_cta_quality, 80)
        self.assertTrue(result.passed)

    def test_gate_flags_low_quality_article_without_blocking(self) -> None:
        gate = PrePublishQualityGate(minimum_score=85)
        result = gate.evaluate_article(
            title="Untitled",
            content="Short article with no useful details and no links.",
            meta_description="",
            slug="untitled",
            topic="AI tools",
            existing_titles=["Untitled"],
            existing_h1s=["Untitled"],
            existing_keywords=["AI tools"],
            internal_links=[],
            schema_hints=[],
        )

        self.assertTrue(result.report_only)
        self.assertFalse(result.publish_blocked)
        self.assertLess(result.overall_score, 85)
        self.assertFalse(result.passed)
        self.assertTrue(any("thin content" in issue.lower() for issue in result.issues))


if __name__ == "__main__":
    unittest.main()
