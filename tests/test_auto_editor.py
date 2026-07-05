import unittest

from modules.content_operations import optimize_article_text


class AutoEditorTests(unittest.TestCase):
    def test_adds_required_sections(self):
        output, report = optimize_article_text("Short draft.", slug="short-draft", youtube_url="https://youtu.be/test")
        self.assertIn("Table of Contents", output)
        self.assertIn("Watch the video review", output)
        self.assertEqual(report["status"], "optimized")


if __name__ == "__main__":
    unittest.main()
