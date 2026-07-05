import unittest

from modules.content_writer import generate_article_markdown


class ContentWriterTests(unittest.TestCase):
    def test_generates_ready_for_review_markdown(self):
        content = generate_article_markdown({"topic": "Kilocode Review 2026", "slug": "kilocode-review-2026", "article_type": "review"})
        self.assertIn("status: READY_FOR_REVIEW", content)
        self.assertIn("## FAQ", content)
        self.assertGreaterEqual(len(content.split()), 2500)


if __name__ == "__main__":
    unittest.main()
