from __future__ import annotations

import unittest

from modules.quick_reply_finder import find_related_articles, quick_reply


class QuickReplyFinderTests(unittest.TestCase):
    def test_finds_related_articles_for_comparison_query(self) -> None:
        results = find_related_articles("copilot vs codex", limit=3)
        self.assertTrue(results)
        self.assertTrue(any("copilot" in item.url.lower() or "codex" in item.url.lower() for item in results))

    def test_replies_are_short_and_natural(self) -> None:
        payload = quick_reply("cursor review")
        replies = payload["replies"]
        self.assertGreaterEqual(len(replies), 1)
        self.assertTrue(all(len(reply) < 420 for reply in replies))
        self.assertFalse(any("affiliate" in reply.lower() for reply in replies))

    def test_tracked_links_have_quick_reply_utm(self) -> None:
        results = find_related_articles("windsurf worth it", limit=1)
        self.assertTrue(results)
        tracked = results[0].tracked_url
        self.assertIn("utm_source=quick_reply", tracked)
        self.assertIn("utm_medium=social_comment", tracked)

    def test_codex_openclaw_query_returns_new_comparison(self) -> None:
        results = find_related_articles("codex vs openclaw", limit=3)
        self.assertTrue(results)
        self.assertEqual(results[0].url, "/comparisons/codex-vs-openclaw/")
        payload = quick_reply("openclaw")
        self.assertTrue(any("/comparisons/codex-vs-openclaw/" in reply for reply in payload["replies"]))
        platform_replies = payload["platform_replies"]
        self.assertIn("reddit", platform_replies)
        self.assertIn("facebook", platform_replies)
        self.assertIn("quora", platform_replies)
        self.assertTrue(any("deeper breakdown" in reply.lower() for reply in platform_replies["reddit"]))


if __name__ == "__main__":
    unittest.main()
