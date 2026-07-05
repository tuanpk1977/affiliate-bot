from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from modules.ai_trend_discovery import TrendDiscoveryEngine, TrendSignal, published_match_for, slugify


class AITrendDiscoveryTest(unittest.TestCase):
    def test_slugify(self) -> None:
        self.assertEqual(slugify("AI Agent Workflow Tools 2026"), "ai-agent-workflow-tools-2026")

    def test_published_filter_detects_matching_topic(self) -> None:
        published = [{"slug": "cursor-review-2026", "title": "Cursor Review", "tokens": {"cursor"}}]
        self.assertTrue(published_match_for("Cursor Review 2026", published))

    def test_scoring_prefers_multi_source_commercial_topic(self) -> None:
        engine = TrendDiscoveryEngine(timeout=1)
        engine.published = []
        signals = [
            TrendSignal("New AI agent automation software review", "reddit", engagement=500),
            TrendSignal("New AI agent automation software review", "hacker_news", engagement=300),
            TrendSignal("New AI agent automation software review", "product_hunt", engagement=100),
        ]
        result = engine.aggregate(signals)
        self.assertEqual(len(result), 1)
        self.assertGreaterEqual(result[0].affiliate_opportunity, 60)
        self.assertEqual(result[0].confidence, "high")

    def test_already_published_is_excluded_from_selection(self) -> None:
        engine = TrendDiscoveryEngine(timeout=1)
        engine.published = [{"slug": "new-ai-agent-tool", "title": "New AI Agent Tool", "tokens": {"new", "ai", "agent", "tool"}}]
        engine.google_trends = lambda: [TrendSignal("New AI Agent Tool", "google_trends")]
        for name in ("bing_trending", "reddit", "hacker_news", "product_hunt", "github_trending", "x_twitter", "linkedin", "youtube_trending", "ai_newsletters", "local_keyword_intelligence"):
            setattr(engine, name, lambda: [])
        result = engine.run(limit=10)
        self.assertEqual(result.selected_topics, [])


if __name__ == "__main__":
    unittest.main()
