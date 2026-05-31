from __future__ import annotations

import unittest
from datetime import datetime

from modules.social_draft_generator import build_draft_id, create_social_draft
from modules.social_posting_connectors import dry_run_post
from modules.social_scheduler import next_schedule_times


class SocialAutomationTests(unittest.TestCase):
    def test_social_draft_has_required_metadata(self) -> None:
        draft = create_social_draft(
            "https://smileaireviewhub.com/cursor/",
            "en",
            "linkedin",
            created_at="2026-05-16T07:00:00",
        )
        self.assertEqual(draft["id"], build_draft_id("https://smileaireviewhub.com/cursor/", "en", "linkedin"))
        self.assertEqual(draft["status"], "draft")
        self.assertTrue(draft["source_url"].endswith("/cursor/"))
        self.assertTrue(draft["cta_url"].endswith("/cursor/"))
        self.assertEqual(draft["approved_at"], "")
        self.assertEqual(draft["scheduled_at"], "")
        self.assertEqual(draft["posted_at"], "")

    def test_schedule_uses_required_slots_and_max_two_per_day(self) -> None:
        config = {
            "timezone": "Asia/Ho_Chi_Minh",
            "daily_slots": ["07:30", "20:30"],
            "max_posts_per_day": 2,
            "require_approval": True,
            "auto_post_enabled": False,
        }
        times = next_schedule_times(3, config=config, start=datetime(2026, 5, 16, 6, 0))
        self.assertEqual([time.split("T")[1] for time in times[:2]], ["07:30", "20:30"])
        self.assertEqual(times[2].split("T")[0], "2026-05-17")
        self.assertEqual(times[2].split("T")[1], "07:30")

    def test_social_connector_does_not_auto_post_when_disabled(self) -> None:
        result = dry_run_post("facebook", {"id": "draft-1", "content": "hello"}, {"auto_post_enabled": False})
        self.assertFalse(result["posted"])
        self.assertEqual(result["status"], "dry_run")

    def test_social_connector_never_claims_real_api_post(self) -> None:
        result = dry_run_post("twitter", {"id": "draft-2", "content": "hello"}, {"auto_post_enabled": True})
        self.assertFalse(result["posted"])
        self.assertEqual(result["status"], "not_implemented")


if __name__ == "__main__":
    unittest.main()
