from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from modules.content_intelligence import (
    GOOGLE_TRENDS_FIELDS,
    normalize_google_news,
    normalize_google_trends,
    normalize_producthunt,
    normalize_reddit,
    normalize_youtube_trends,
    parse_google_news_rss,
    to_topic_record,
    write_dual_outputs,
)
from modules.performance_tracking import read_csv


class ContentIntelligenceTests(unittest.TestCase):
    def test_google_trends_breakout_scores_to_100(self) -> None:
        rows = normalize_google_trends([{"keyword": "AI agent software", "growth": "Breakout", "category": "SaaS"}])
        self.assertEqual(rows[0]["trend_score"], 100)
        self.assertEqual(rows[0]["country"], "US")

    def test_google_news_rss_parses_items(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "news.xml"
            path.write_text(
                """<?xml version="1.0"?><rss><channel><item><title>New AI SaaS platform launches</title><link>https://example.com/a</link><pubDate>Thu, 18 Jun 2026 08:00:00 GMT</pubDate></item></channel></rss>""",
                encoding="utf-8",
            )
            rows = parse_google_news_rss(path)
        self.assertEqual(rows[0]["title"], "New AI SaaS platform launches")

    def test_news_normalization_scores_authority_and_freshness(self) -> None:
        rows = normalize_google_news([{"title": "AI startup funding", "url": "https://techcrunch.com/example", "freshness_score": 80}])
        self.assertGreater(rows[0]["authority_score"], 55)
        self.assertGreater(rows[0]["trend_score"], 50)

    def test_youtube_velocity_from_views_and_subscribers(self) -> None:
        rows = normalize_youtube_trends([{"title": "Best AI tools review", "views": 10000, "subscribers": 5000}])
        self.assertGreater(rows[0]["estimated_velocity"], 0)
        self.assertIn("review", rows[0]["potential_review_topic"].lower())

    def test_reddit_discussion_uses_upvotes_comments_and_entity(self) -> None:
        rows = normalize_reddit([{"topic": "Cursor vs Copilot for real projects", "upvotes": 120, "comments": 45}])
        self.assertGreater(rows[0]["trend_score"], 0)
        self.assertEqual(rows[0]["tracked_entity"], "Cursor")

    def test_producthunt_outputs_review_comparison_and_video_candidates(self) -> None:
        rows = normalize_producthunt([{"product": "Example AI", "votes": 240, "comments": 30}])
        self.assertIn("Review", rows[0]["potential_review_article"])
        self.assertIn("Alternatives", rows[0]["potential_comparison_article"])
        self.assertIn("Video", rows[0]["potential_youtube_video"])

    def test_topic_record_infers_money_inputs(self) -> None:
        row = to_topic_record("Best AI SEO software review", "unit_test", "SEO", 80)
        self.assertGreater(row["buyer_intent"], 50)
        self.assertGreater(row["affiliate_value"], 50)
        self.assertEqual(row["slug"], "best-ai-seo-software-review")

    def test_write_dual_outputs_writes_csv_and_json(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            csv_path = Path(folder) / "google_trends.csv"
            json_path = Path(folder) / "google_trends.json"
            write_dual_outputs(csv_path, json_path, [{"keyword": "AI tools", "trend_score": 50}], GOOGLE_TRENDS_FIELDS)
            self.assertTrue(json_path.exists())
            self.assertEqual(read_csv(csv_path)[0]["keyword"], "AI tools")


if __name__ == "__main__":
    unittest.main()
