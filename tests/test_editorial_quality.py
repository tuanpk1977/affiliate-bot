from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from modules.content_review import ContentReviewEngine
from modules.editorial_quality import (
    CapacityManager,
    EditorialJudge,
    FactVerificationEngine,
    PublishingConfidenceEngine,
    SourceQualityRanker,
    StructuredReviewBuilder,
    TargetedRewriteLoop,
    build_learning_feedback_record,
)
from modules.publish_gate import PublishGate


ARTICLE_HTML = """
<html><head><link rel="canonical" href="https://example.com/pydantic-ai-review-2026/">
<meta name="description" content="Practical buyer review."></head><body>
<h1>Pydantic AI Review 2026</h1>
<section><h2>Affiliate disclosure</h2><p>We may earn a commission.</p></section>
<p>Pydantic AI launched for typed Python agent workflows in 2026 and teams compare it with other agent frameworks.</p>
<p>This review explains pricing checks, integration tradeoffs, source-backed use cases, and implementation workflow guidance.</p>
<p>It includes enough supporting body copy for editors to judge whether the draft should move to human review.</p>
</body></html>
"""


class EditorialQualityFoundationTests(unittest.TestCase):
    def test_source_ranking_keeps_low_tier_context_but_scores_primary_sources_higher(self) -> None:
        ranker = SourceQualityRanker()
        rows = ranker.rank(
            [
                "https://reddit.com/r/example/comments/abc",
                "https://pydantic.dev/docs/ai/overview/",
                "https://github.com/pydantic/pydantic-ai",
            ]
        )

        self.assertEqual(rows[0]["source_type"], "official_docs")
        self.assertTrue(rows[0]["primary_source"])
        self.assertTrue(any(row["source_type"] == "forum" for row in rows))

    def test_fact_verification_blocks_critical_claim_without_sources(self) -> None:
        result = FactVerificationEngine().verify(html=ARTICLE_HTML, sources=[])

        self.assertIn("critical claim unsupported", result["hard_blockers"])
        self.assertTrue(any(claim["requires_human_review"] for claim in result["claims"]))

    def test_fact_verification_warns_when_single_domain_partially_supports_claim(self) -> None:
        result = FactVerificationEngine().verify(html=ARTICLE_HTML, sources=["https://pydantic.dev/docs/ai/overview/"])

        self.assertEqual(result["hard_blockers"], [])
        self.assertIn("critical claim needs stronger source support", result["warnings"])

    def test_publishing_confidence_blocks_on_hard_blocker_even_with_high_score(self) -> None:
        confidence = PublishingConfidenceEngine().calculate(
            review={"publish_readiness": 96, "seo_title_meta_quality": 96, "readability": 96, "business_value": 96, "duplicate_content_risk": 0},
            research={"quality": {"overall_score": 96, "entity_coverage_score": 96}},
            fact_verification={"claim_count": 1, "claims": [{"support_status": "supported"}]},
            source_quality=[{"overall_source_score": 96}],
            hard_blockers=["critical claim unsupported"],
            warnings=[],
        )

        self.assertEqual(confidence["status"], "blocked")
        self.assertEqual(confidence["recommended_action"], "block_until_critical_issues_resolved")

    def test_warning_only_judge_passes_to_human_review(self) -> None:
        confidence = {"score": 78, "status": "warning"}
        decision = EditorialJudge().evaluate(
            structured_review={"hard_blockers": [], "warnings": ["readability below threshold"]},
            fact_verification={"hard_blockers": [], "warnings": []},
            publishing_confidence=confidence,
        )

        self.assertEqual(decision["decision"], "warning_to_human")
        self.assertEqual(decision["hard_blockers"], [])

    def test_targeted_rewrite_only_targets_fixable_sections_and_keeps_better_version(self) -> None:
        review = {
            "issues": [
                {"section_id": "pricing", "auto_fixable": True, "hard_blocker": False},
                {"section_id": "sources", "auto_fixable": False, "hard_blocker": True},
            ]
        }
        loop = TargetedRewriteLoop({"max_rewrite_attempts": 2, "max_review_cycles": 3})

        plan = loop.plan(structured_review=review)
        selected = loop.choose_better_section(previous_text="good", rewritten_text="bad", previous_score=80, rewritten_score=70)

        self.assertEqual(plan["target_sections"], ["pricing"])
        self.assertEqual(selected["selected"], "previous")

    def test_capacity_manager_counts_warning_ready_drafts_without_bypassing_blocks(self) -> None:
        snapshot = CapacityManager({"minimum_daily_review_ready": 5, "target_daily_review_ready": 10, "maximum_daily_drafts": 15}).summarize(
            [
                {"status": "drafted", "research_quality_gate": {"status": "warning"}},
                {"status": "needs_enrichment"},
                {"status": "blocked"},
            ]
        )

        self.assertEqual(snapshot["review_ready"], 1)
        self.assertEqual(snapshot["blocked"], 2)
        self.assertEqual(snapshot["minimum"], 5)

    def test_capacity_manager_demonstrates_minimum_five_review_ready_with_warning_fixtures(self) -> None:
        rows = [{"status": "drafted", "research_quality_gate": {"status": "warning"}} for _ in range(5)]
        rows.extend({"status": "needs_enrichment"} for _ in range(2))

        snapshot = CapacityManager({"minimum_daily_review_ready": 5, "target_daily_review_ready": 10, "maximum_daily_drafts": 15}).summarize(rows)

        self.assertEqual(snapshot["review_ready"], 5)
        self.assertEqual(snapshot["blocked"], 2)
        self.assertEqual(snapshot["bottleneck"], "none")

    def test_learning_feedback_record_never_auto_applies_policy_adjustments(self) -> None:
        record = build_learning_feedback_record(
            article_id="one",
            topic_cluster="agent frameworks",
            content_type="review",
            pre_publish_scores={"warning_count": 2},
            post_publish_metrics={"ctr": 1.1},
        )

        self.assertEqual(record["recommended_policy_adjustments"], [])
        self.assertTrue(record["lessons"])


class EditorialQualityIntegrationTests(unittest.TestCase):
    def test_warning_level_review_is_human_review_ready(self) -> None:
        with TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir) / "data"
            engine = ContentReviewEngine(
                data_dir=data_dir,
                config={
                    "minimum_word_count": 300,
                    "minimum_publish_readiness": 80,
                    "minimum_source_quality": 70,
                    "minimum_factual_quality": 70,
                    "minimum_seo_quality": 70,
                    "minimum_business_value": 70,
                    "minimum_readability_score": 70,
                    "require_human_approval": True,
                },
            )
            result = engine.review_content(
                topic={"topic": "pydantic ai review", "slug": "pydantic-ai-review-2026", "content_type": "review"},
                html=ARTICLE_HTML,
                title="Pydantic AI Review",
                description="Short buyer review.",
                url="https://example.com/pydantic-ai-review-2026/",
                internal_links=[],
                warnings=[],
                research={
                    "quality": {"overall_score": 55, "source_quality": 55, "total_verified_source_score": 55, "affiliate_readiness": 40, "entity_coverage_score": 45},
                    "sources": {
                        "verified_sources": [
                            {"url": "https://pydantic.dev/docs/ai/overview/", "status": "verified"},
                            {"url": "https://github.com/pydantic/pydantic-ai", "status": "verified"},
                        ]
                    },
                    "quality_gate": {"passed": True, "score": 55},
                },
                planning={"coverage_score": 45, "keyword": "pydantic ai review"},
            )

            self.assertEqual(result["status"], "needs_human_review")
            self.assertTrue(result["publishable"])
            self.assertTrue(result["warnings"])
            self.assertEqual(result["structured_review"]["status"], "warning")
            self.assertIn(result["ai_judge"]["decision"], {"warning_to_human", "pass_to_human"})

    def test_zero_source_review_remains_blocked(self) -> None:
        with TemporaryDirectory() as temp_dir:
            result = ContentReviewEngine(data_dir=Path(temp_dir) / "data").review_content(
                topic={"topic": "unsupported pricing claim", "slug": "unsupported-pricing-claim"},
                html="<html><body><h1>Unsupported</h1><p>Pricing is $10 in 2026.</p></body></html>",
                title="Unsupported Pricing Claim",
                description="Unsupported claim.",
                url="https://example.com/unsupported-pricing-claim/",
                internal_links=[],
                warnings=[],
                research={"quality": {"overall_score": 10, "source_quality": 0, "total_verified_source_score": 0}},
                planning={"coverage_score": 10, "keyword": "unsupported pricing claim"},
            )

            self.assertEqual(result["status"], "needs_revision")
            self.assertIn("zero usable sources", result["hard_blockers"])

    def test_publish_gate_still_requires_human_approval_for_warning_ready_article(self) -> None:
        with TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir) / "data"
            gate = PublishGate(
                data_dir=data_dir,
                config={
                    "enabled": True,
                    "minimum_verified_source_score": 35,
                    "minimum_knowledge_freshness": 40,
                    "require_human_approval": True,
                    "minimum_business_score": 35,
                    "minimum_readability_score": 30,
                },
            )
            result = gate.evaluate(
                topic={"topic": "Pydantic AI Review", "slug": "pydantic-ai-review-2026"},
                title="Pydantic AI Review",
                description="Buyer review.",
                url="https://example.com/pydantic-ai-review-2026/",
                html=ARTICLE_HTML,
                research={"quality": {"total_verified_source_score": 55, "source_confidence": 35, "overall_score": 55}, "quality_gate": {"passed": True, "score": 55}},
                review={"status": "needs_human_review", "business_value": 75, "readability": 75, "publish_readiness": 78, "requires_human_approval": True},
                human_approval={"status": "needs_human_review"},
                internal_links=[],
            )

            self.assertEqual(result["status"], "needs_human_review")
            self.assertIn("human approval missing", result["pending_reviews"])
            self.assertFalse(result["publish_ready"])


if __name__ == "__main__":
    unittest.main()
