from __future__ import annotations

import unittest

from modules.opportunity_forecast import build_forecast_rows, estimated_monthly_traffic, money_score
from scripts.build_internal_link_plan import buyer_stage, tokens
from scripts.competitor_watch import classify_page
from scripts.keyword_gap_analysis import keyword_exists


class OpportunityForecastTests(unittest.TestCase):
    def sample_topic(self) -> dict[str, object]:
        return {
            "topic": "Surfer SEO Pricing Review 2026",
            "buyer_intent": 92,
            "affiliate_value": 88,
            "cpc_potential": 85,
            "search_intent": 90,
            "competition_level": 30,
            "seo_opportunity": 82,
            "trend_score": 55,
            "evergreen_potential": 78,
            "estimated_traffic": 65,
            "reason": "High buyer intent",
        }

    def test_money_score_rewards_commercial_affiliate_topics(self) -> None:
        self.assertGreaterEqual(money_score(self.sample_topic()), 70)

    def test_forecast_rows_include_required_decision_and_estimates(self) -> None:
        rows = build_forecast_rows(topic_rows=[self.sample_topic()], lifecycle_rows=[])
        self.assertEqual(rows[0]["decision"], "WRITE NOW")
        self.assertGreater(rows[0]["estimated_monthly_traffic"], 0)
        self.assertGreater(rows[0]["estimated_revenue"], 0)

    def test_high_competition_reduces_traffic_estimate(self) -> None:
        low_comp = {**self.sample_topic(), "competition_level": 25}
        high_comp = {**self.sample_topic(), "competition_level": 90}
        self.assertGreater(estimated_monthly_traffic(low_comp), estimated_monthly_traffic(high_comp))

    def test_competitor_page_classification(self) -> None:
        self.assertEqual(classify_page("https://example.com/surfer-seo-vs-frase", ""), "Comparison page")
        self.assertEqual(classify_page("https://example.com/pricing", "surfer seo pricing"), "Pricing page")

    def test_keyword_exists_matches_topic_or_slug(self) -> None:
        lifecycle = [{"topic": "Surfer SEO Free Trial", "slug": "surfer-seo-free-trial"}]
        self.assertTrue(keyword_exists("surfer seo free trial", lifecycle))
        self.assertFalse(keyword_exists("missing affiliate software", lifecycle))

    def test_internal_link_helpers(self) -> None:
        self.assertIn("surfer", tokens("surfer-seo-review-2026"))
        stage = buyer_stage({"slug": "surfer-seo-review"}, {"slug": "surfer-seo-pricing"})
        self.assertEqual(stage, "pricing validation")


if __name__ == "__main__":
    unittest.main()
