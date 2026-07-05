import unittest

from modules.content_operations import build_ai_priority_dashboard, build_daily_publishing_schedule, build_revenue_opportunity


class AiPriorityEngineTests(unittest.TestCase):
    def test_priority_dashboard_has_final_score_and_create_action(self):
        topics = [
            {
                "topic": "Affordable AI App Builder Review",
                "slug": "affordable-ai-app-builder-review",
                "trend_score": 80,
                "affiliate_value": 85,
                "competition": 30,
                "internal_linking_opportunity": 70,
                "youtube_potential": 75,
                "social_share_potential": 65,
                "estimated_traffic": 70,
                "estimated_conversion": 60,
            }
        ]
        money = [{"topic": topics[0]["topic"], "slug": topics[0]["slug"], "money_score": 88}]
        rows = build_ai_priority_dashboard(topics=topics, money_rows=money, duplicate_rows=[{"slug": topics[0]["slug"], "decision": "NEW_TOPIC_OK"}], inventory=[], authority_rows=[])
        self.assertEqual(rows[0]["recommended_action"], "CREATE")
        self.assertGreater(rows[0]["final_score"], 50)
        self.assertIn("estimated_revenue_score", rows[0])

    def test_revenue_and_schedule_outputs(self):
        priority = [
            {"topic": "Tool Review", "slug": "tool-review", "recommended_action": "CREATE", "article_type": "review", "final_score": 90, "estimated_revenue_score": 80, "estimated_value": 100},
            {"topic": "Best AI Tools", "slug": "best-ai-tools", "recommended_action": "CREATE", "article_type": "best list", "final_score": 85, "estimated_revenue_score": 75, "estimated_value": 90},
            {"topic": "Tool A vs Tool B", "slug": "tool-a-vs-tool-b", "recommended_action": "CREATE", "article_type": "comparison", "final_score": 82, "estimated_revenue_score": 70, "estimated_value": 85},
        ]
        revenue = build_revenue_opportunity(priority)
        schedule = build_daily_publishing_schedule(priority, days=1)
        self.assertEqual(len(revenue), 3)
        self.assertEqual(len(schedule), 3)


if __name__ == "__main__":
    unittest.main()
