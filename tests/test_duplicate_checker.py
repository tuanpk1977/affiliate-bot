import unittest

from modules.content_operations import build_duplicate_report


class DuplicateCheckerTests(unittest.TestCase):
    def test_exact_slug_refreshes_existing(self):
        topics = [{"topic": "Surfer SEO Review 2026", "slug": "surfer-seo-review-2026"}]
        inventory = [{"topic": "Surfer SEO Review 2026", "slug": "surfer-seo-review-2026", "article_url": "https://example.com/surfer/"}]
        rows = build_duplicate_report(topics, inventory)
        self.assertEqual(rows[0]["decision"], "REFRESH_EXISTING")
        self.assertGreaterEqual(rows[0]["duplicate_score"], 92)


if __name__ == "__main__":
    unittest.main()
