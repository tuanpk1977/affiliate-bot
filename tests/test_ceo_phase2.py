from __future__ import annotations

import unittest
from datetime import date, timedelta

from modules.ceo_phase2 import (
    build_ai_summary,
    build_roi_analysis,
    deadline_for_priority,
    grade_momentum,
    map_action,
    pipeline_completion,
    recommend_momentum,
)


class CEOPhase2Tests(unittest.TestCase):
    def test_momentum_grade_and_recommendation(self) -> None:
        self.assertEqual(grade_momentum(18, 75), "A")
        self.assertEqual(grade_momentum(-10, 20), "D")
        self.assertEqual(recommend_momentum(15, 70), "Act this week")
        self.assertEqual(recommend_momentum(-12, 30), "Avoid unless strong buyer intent")

    def test_map_action_expands_to_business_actions(self) -> None:
        comparison = map_action(
            "Write Now",
            {"topic": "Cursor vs GitHub Copilot"},
            {"estimated_monthly_revenue": 25},
            {},
        )
        self.assertEqual(comparison, "CREATE COMPARISON PAGE")
        self.assertEqual(map_action("Refresh Existing", {"topic": "Surfer SEO Review"}, {}, {}), "REFRESH ARTICLE")
        self.assertEqual(map_action("Make Video", {"topic": "Zapier Pricing"}, {}, {}), "CREATE VIDEO")

    def test_deadline_for_priority(self) -> None:
        self.assertEqual(deadline_for_priority("P1"), date.today().isoformat())
        self.assertEqual(deadline_for_priority("P2"), (date.today() + timedelta(days=2)).isoformat())

    def test_pipeline_completion(self) -> None:
        self.assertEqual(pipeline_completion({}), 0)
        self.assertEqual(
            pipeline_completion(
                {
                    "article_created": "Yes",
                    "website_published": "Yes",
                    "youtube_uploaded": "Yes",
                    "indexed_google": "No",
                    "revenue_checked": "No",
                }
            ),
            60,
        )

    def test_roi_and_summary_are_generated_from_current_data(self) -> None:
        roi = build_roi_analysis()
        self.assertTrue(roi)
        self.assertIn("roi_per_hour", roi[0])
        summary = build_ai_summary()
        self.assertTrue(summary)
        self.assertEqual(summary[0]["section"], "Executive Summary")


if __name__ == "__main__":
    unittest.main()
