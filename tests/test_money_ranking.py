import unittest

from modules.content_operations import build_money_ranking


class MoneyRankingTests(unittest.TestCase):
    def test_commercial_review_scores_write_now(self):
        topics = [
            {
                "topic": "NeuronWriter Review 2026",
                "slug": "neuronwriter-review-2026",
                "buyer_intent": 90,
                "affiliate_value": 85,
                "cpc_potential": 80,
                "seo_score": 75,
                "trend_score": 70,
                "evergreen_potential": 80,
                "competition": 35,
                "estimated_traffic": 70,
            }
        ]
        rows = build_money_ranking(topics, duplicates=[{"slug": "neuronwriter-review-2026", "decision": "NEW_TOPIC_OK"}])
        self.assertEqual(rows[0]["decision"], "WRITE NOW")
        self.assertGreaterEqual(rows[0]["money_score"], 82)


if __name__ == "__main__":
    unittest.main()
