import unittest

from modules.content_operations import build_content_gap


class ContentGapTests(unittest.TestCase):
    def test_missing_pricing_gap_is_created(self):
        inventory = [{"slug": "surfer-seo-review", "topic": "Surfer SEO Review", "article_url": "https://example.com/surfer/"}]
        rows = build_content_gap(inventory)
        missing = {row["missing_article_type"] for row in rows if row["cluster"] == "AI SEO"}
        self.assertIn("pricing", missing)


if __name__ == "__main__":
    unittest.main()
