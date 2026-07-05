from __future__ import annotations

import unittest

from modules.content_planner import DailyContentPlanner, PlannerConfig
from modules.content_strategy import ContentStrategyEngine
from modules.social_score import SocialValueEstimator
from modules.topic_ranker import TopicRanker
from modules.topic_scorer import TopicFeatureSet, TopicScorer
from modules.video_priority import VideoPriorityEngine
from scripts.score_topics import adapt_topic_item, extract_topic_items
from scripts.score_topics import build_plan as build_scoring_plan


class TopicDecisionEngineTest(unittest.TestCase):
    def test_topic_scoring_and_decision_paths(self) -> None:
        scorer = TopicScorer()
        strategy = ContentStrategyEngine()
        video_engine = VideoPriorityEngine()
        social_estimator = SocialValueEstimator()
        ranker = TopicRanker()
        planner = DailyContentPlanner(config=PlannerConfig(days=["Monday", "Tuesday"], max_articles_per_day=1, max_videos_per_day=1, max_social_posts_per_day=1, max_quora_answers_per_day=1, max_x_threads_per_day=1))

        features = TopicFeatureSet(
            topic="AI writing tools for startups",
            trend_score=88,
            search_intent=80,
            seo_opportunity=68,
            competition_level=60,
            affiliate_value=72,
            buyer_intent=70,
            cpc_potential=65,
            evergreen_potential=75,
            freshness=62,
            social_share_potential=72,
            reddit_discussion_potential=60,
            quora_potential=55,
            linkedin_potential=70,
            youtube_potential=68,
            internal_linking_opportunity=70,
            brand_fit=78,
            difficulty=60,
            estimated_traffic=80,
            estimated_conversion=68,
        )

        score = scorer.score_topic(features)
        self.assertGreaterEqual(score.total_score, 60)
        self.assertIn(score.recommendation, ["Excellent", "Strong", "Good", "Watch"])

        decision, rationale = strategy.decide_content_type(score)
        self.assertIn(decision, ["Website + YouTube + Social", "Website + YouTube", "Website", "Website Only (manual review)", "Ignore"])
        self.assertIsInstance(rationale, str)

        video = video_engine.prioritize(score)
        self.assertIn(video, ["No video", "Short", "Long review", "Comparison", "Tutorial", "Demo"])

        social_score = social_estimator.estimate(features.topic, features.as_dict())
        self.assertIsInstance(social_score.facebook, int)
        self.assertIsInstance(social_score.linkedin, int)

        ranked = ranker.rank_topics([score])
        self.assertEqual(ranked[0].topic, features.topic)

        plan = planner.build_plan(ranked)
        self.assertIn("Monday", plan)
        self.assertIn("Tuesday", plan)

    def test_skip_low_score_topic(self) -> None:
        scorer = TopicScorer()
        strategy = ContentStrategyEngine()
        features = TopicFeatureSet(
            topic="AI niche compliance service",
            trend_score=20,
            search_intent=24,
            seo_opportunity=20,
            competition_level=30,
            affiliate_value=18,
            buyer_intent=15,
            cpc_potential=10,
            evergreen_potential=25,
            freshness=20,
            social_share_potential=18,
            reddit_discussion_potential=15,
            quora_potential=18,
            linkedin_potential=20,
            youtube_potential=18,
            internal_linking_opportunity=20,
            brand_fit=25,
            difficulty=45,
            estimated_traffic=22,
            estimated_conversion=18,
        )

        score = scorer.score_topic(features)
        decision, _ = strategy.decide_content_type(score)
        self.assertEqual(decision, "Ignore")
        self.assertEqual(score.recommendation, "Skip")

    def test_trending_topic_input_is_adapted_for_scoring(self) -> None:
        raw = {
            "selected_topics": [
                {
                    "topic": "ai seo software comparison",
                    "sources": ["local_keyword_intelligence"],
                    "search_intent": "comparison",
                    "content_type": "comparison",
                    "affiliate_potential": "low",
                    "competition_level": "medium",
                    "suggested_internal_links": ["/", "/reviews/", "/comparisons/"],
                    "classifications": ["comparison", "rising trend"],
                    "search_volume_potential": 59,
                    "competition": 47,
                    "affiliate_opportunity": 44,
                    "evergreen_value": 51,
                    "news_freshness": 56,
                    "cpc_potential": 52,
                }
            ]
        }

        items = extract_topic_items(raw)
        features = adapt_topic_item(items[0])

        self.assertEqual(features.topic, "ai seo software comparison")
        self.assertEqual(features.source, "local_keyword_intelligence")
        self.assertIn("comparison", features.tags)
        self.assertGreater(features.search_intent, 0)
        self.assertGreater(features.seo_opportunity, 0)
        self.assertGreater(features.youtube_potential, 0)

    def test_all_candidates_are_preferred_over_selected_topics(self) -> None:
        raw = {
            "selected_topics": [{"topic": "Selected Only Topic"}],
            "all_candidates": [{"topic": "All Candidate Topic"}, {"topic": "Second Candidate Topic"}],
        }

        items = extract_topic_items(raw)
        self.assertEqual([item["topic"] for item in items], ["All Candidate Topic", "Second Candidate Topic"])

    def test_affiliate_comparison_topic_can_reach_strong_score(self) -> None:
        scorer = TopicScorer()
        features = TopicFeatureSet(
            topic="AI video software comparison",
            trend_score=72,
            search_intent=78,
            seo_opportunity=70,
            competition_level=48,
            affiliate_value=72,
            buyer_intent=76,
            cpc_potential=68,
            evergreen_potential=74,
            freshness=62,
            social_share_potential=66,
            reddit_discussion_potential=58,
            quora_potential=64,
            linkedin_potential=62,
            youtube_potential=78,
            internal_linking_opportunity=70,
            brand_fit=82,
            difficulty=48,
            estimated_traffic=72,
            estimated_conversion=74,
            tags=["comparison", "affiliate", "software"],
        )

        score = scorer.score_topic(features)
        self.assertGreaterEqual(score.total_score, 80)
        self.assertIn(score.as_dict()["score_grade"], ["Strong", "Excellent"])

    def test_news_style_topic_is_penalized(self) -> None:
        scorer = TopicScorer()
        commercial_news = TopicFeatureSet(
            topic="OpenAI says new funding round launched today",
            trend_score=90,
            search_intent=60,
            seo_opportunity=55,
            competition_level=55,
            affiliate_value=45,
            buyer_intent=45,
            cpc_potential=65,
            evergreen_potential=35,
            freshness=95,
            social_share_potential=70,
            reddit_discussion_potential=60,
            quora_potential=45,
            linkedin_potential=65,
            youtube_potential=55,
            internal_linking_opportunity=55,
            brand_fit=65,
            difficulty=55,
            estimated_traffic=75,
            estimated_conversion=45,
            tags=["news/update"],
        )

        score = scorer.score_topic(commercial_news)
        self.assertLess(score.total_score, 70)

    def test_scoring_plan_contains_required_dashboard_groups(self) -> None:
        scorer = TopicScorer()
        planner = DailyContentPlanner()
        features = TopicFeatureSet(
            topic="Best AI SEO Tools Review",
            trend_score=80,
            search_intent=85,
            seo_opportunity=80,
            competition_level=45,
            affiliate_value=85,
            buyer_intent=86,
            cpc_potential=80,
            evergreen_potential=82,
            freshness=70,
            social_share_potential=72,
            reddit_discussion_potential=65,
            quora_potential=70,
            linkedin_potential=72,
            youtube_potential=82,
            internal_linking_opportunity=80,
            brand_fit=86,
            difficulty=45,
            estimated_traffic=82,
            estimated_conversion=84,
            tags=["review", "best", "software"],
        )
        score = scorer.score_topic(features)
        score.content_decision = "Website + YouTube"
        score.video_priority = "Comparison"
        score.social_scores = {"facebook": 72, "linkedin": 74, "reddit": 70, "quora": 76, "x": 70, "medium": 72}

        plan = build_scoring_plan([score], planner)
        self.assertIn("todays_top_10", plan)
        self.assertIn("top_3", plan)
        self.assertIn("highest_revenue", plan)
        self.assertIn("highest_seo", plan)
        self.assertIn("highest_video", plan)
        self.assertIn("highest_social", plan)
        self.assertIn("monitor", plan)
        self.assertIn("skip", plan)


if __name__ == "__main__":
    unittest.main()
