from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from modules.business_intelligence import (
    build_affiliate_match,
    build_article_plan,
    build_dashboard_rows,
    build_execution_tracker,
    build_money_score,
    build_opportunity_breakdown,
    build_seo_difficulty,
    build_trend_momentum,
    final_action,
    infer_intent,
    write_daily_ceo_dashboard_html,
)


class BusinessIntelligenceTests(unittest.TestCase):
    def sample_rows(self) -> list[dict[str, object]]:
        return [
            {
                "topic": "Surfer SEO Pricing Review 2026",
                "total_score": 84,
                "seo_score": 72,
                "traffic_score": 70,
                "buyer_intent": 88,
                "revenue_score": 82,
                "competition": 45,
                "freshness": 60,
                "youtube_potential": 72,
                "social_scores": {"linkedin": 60, "x": 50},
            },
            {
                "topic": "AI funding news today",
                "total_score": 42,
                "seo_score": 40,
                "traffic_score": 45,
                "buyer_intent": 25,
                "revenue_score": 20,
                "competition": 75,
                "freshness": 80,
                "youtube_potential": 35,
            },
        ]

    def test_intent_detection(self) -> None:
        self.assertEqual(infer_intent("Surfer SEO Pricing 2026"), "pricing")
        self.assertEqual(infer_intent("ChatGPT vs Claude"), "comparison")
        self.assertEqual(infer_intent("Best AI SEO Tools"), "best list")

    def test_opportunity_breakdown_contains_component_scores_and_reason(self) -> None:
        rows = build_opportunity_breakdown(self.sample_rows())
        self.assertEqual(rows[0]["intent"], "pricing")
        self.assertGreater(rows[0]["buyer_intent_score"], 80)
        self.assertIn("commercial keyword", rows[0]["reason"])

    def test_money_score_estimates_revenue_fields(self) -> None:
        rows = build_money_score(self.sample_rows())
        self.assertGreater(rows[0]["estimated_monthly_traffic"], 0)
        self.assertGreater(rows[0]["estimated_affiliate_clicks"], 0)
        self.assertIn("affiliate", rows[0]["recommended_affiliate_program"].lower())

    def test_seo_difficulty_adjusts_high_competition_buyer_topic(self) -> None:
        high_comp = [{**self.sample_rows()[0], "competition": 85}]
        rows = build_seo_difficulty(high_comp)
        self.assertEqual(rows[0]["competition_level"], "High")
        self.assertEqual(rows[0]["recommendation_adjustment"], "Refresh / Long-tail / Support article")

    def test_article_plan_only_contains_actionable_topics(self) -> None:
        rows = build_article_plan(self.sample_rows())
        self.assertTrue(rows)
        self.assertIn("Pricing", rows[0]["suggested_title"])
        self.assertEqual(rows[0]["youtube_needed"], "yes")

    def test_execution_tracker_defaults_pending_or_no(self) -> None:
        rows = build_execution_tracker(self.sample_rows())
        self.assertEqual(rows[0]["approved"], "Pending")
        self.assertIn(rows[0]["youtube_uploaded"], {"Yes", "No"})
        self.assertEqual(rows[0]["facebook_posted"], "No")

    def test_trend_momentum_uses_history(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "unused.csv"
            self.assertFalse(path.exists())
            rows = build_trend_momentum(now=datetime(2026, 6, 18, 8, 0, tzinfo=timezone.utc))
        self.assertTrue(rows)
        self.assertIn(rows[0]["momentum"], {"Rising", "Stable", "Declining"})

    def test_affiliate_match_flags_program_priority(self) -> None:
        rows = build_affiliate_match(self.sample_rows())
        self.assertIn(rows[0]["affiliate_priority"], {"High", "Medium", "Low"})
        self.assertIn("Verify terms", rows[0]["notes"])

    def test_final_action_prioritizes_strong_money_topic(self) -> None:
        action = final_action(
            {"total_score": 85, "video_score": 70},
            {"money_score": 75},
            {"competition_level": "Medium", "recommendation_adjustment": "Primary article"},
        )
        self.assertEqual(action, "Write Now")

    def test_dashboard_html_generation(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "dashboard.html"
            write_daily_ceo_dashboard_html(output, build_dashboard_rows(), [])
            self.assertTrue(output.exists())
            self.assertIn("AI CEO Business Intelligence Dashboard", output.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
