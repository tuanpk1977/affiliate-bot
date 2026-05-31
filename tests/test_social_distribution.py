from __future__ import annotations

import unittest

from modules.distribution_boost import generate_distribution_boost
from modules.social_content_generator import render_platform_post
from modules.social_publish_queue import PLATFORM_LIMITS


class SocialDistributionTests(unittest.TestCase):
    def test_platform_posts_have_distinct_tone_and_url(self) -> None:
        url = "https://smileaireviewhub.com/cursor/"
        facebook = render_platform_post("facebook", "Cursor Review", "cursor review", "Cursor fits solo coding workflows.", url)
        linkedin = render_platform_post("linkedin", "Cursor Review", "cursor review", "Cursor fits solo coding workflows.", url)
        telegram = render_platform_post("telegram", "Cursor Review", "cursor review", "Cursor fits solo coding workflows.", url)
        self.assertIn(url, facebook)
        self.assertIn(url, linkedin)
        self.assertIn(url, telegram)
        self.assertNotEqual(facebook, linkedin)
        self.assertNotEqual(facebook, telegram)

    def test_distribution_boost_has_required_sections(self) -> None:
        boost = generate_distribution_boost("Cursor Review", "https://smileaireviewhub.com/cursor/", "Cursor review content")
        self.assertIn("reddit_summary", boost)
        self.assertIn("faq_schema_suggestions", boost)
        self.assertGreaterEqual(len(boost["faq_schema_suggestions"]), 3)

    def test_platform_limits_are_conservative(self) -> None:
        self.assertLessEqual(PLATFORM_LIMITS["facebook"], 3)
        self.assertLessEqual(PLATFORM_LIMITS["linkedin"], 2)
        self.assertLessEqual(PLATFORM_LIMITS["telegram"], 6)


if __name__ == "__main__":
    unittest.main()
