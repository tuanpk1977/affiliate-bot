import unittest

from modules.content_operations import build_today_write_plan


class TodayWritePlanTests(unittest.TestCase):
    def test_selects_write_today(self):
        priority = [
            {
                "topic": "Tool Review 2026",
                "slug": "tool-review-2026",
                "recommended_action": "CREATE",
                "final_score": 90,
                "article_type": "review",
                "youtube_score": 75,
            }
        ]
        rows = build_today_write_plan(duplicate_rows=[{"slug": "tool-review-2026", "decision": "NEW_TOPIC_OK", "duplicate_score": 10}], gap_rows=[], priority_rows=priority)
        self.assertEqual(rows[0]["action"], "CREATE")
        self.assertEqual(rows[0]["youtube_action"], "CREATE VIDEO")

    def test_existing_article_only_refreshes_once(self):
        priority = [
            {"topic": "Kilocode Review 2026", "slug": "kilocode-review-2026", "recommended_action": "REFRESH", "final_score": 88, "article_type": "review"},
            {"topic": "Kilocode Review 2026", "slug": "kilocode-review-2026", "recommended_action": "CREATE", "final_score": 87, "article_type": "review"},
        ]
        rows = build_today_write_plan(duplicate_rows=[{"slug": "kilocode-review-2026", "decision": "REFRESH_EXISTING", "duplicate_score": 100}], gap_rows=[], priority_rows=priority)
        actions = [row["action"] for row in rows if row["slug"] == "kilocode-review-2026"]
        self.assertEqual(actions, ["REFRESH"])


if __name__ == "__main__":
    unittest.main()
