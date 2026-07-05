import unittest

from modules.topic_cluster_engine import TopicClusterAnalysisResult, TopicClusterEngine


class TopicClusterEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = TopicClusterEngine()

    def test_groups_keywords_into_a_parent_topic_cluster(self) -> None:
        keywords = [
            "best ai coding assistants",
            "ai coding assistants for teams",
            "how to use ai coding assistants",
            "cursor vs windsurf",
            "ai coding assistants pricing",
            "what is an ai coding assistant",
        ]

        result = self.engine.analyze(keywords, seed_topic="ai coding assistants")

        self.assertIsInstance(result, TopicClusterAnalysisResult)
        self.assertEqual(result.parent_topic, "ai coding assistants")
        self.assertTrue(result.clusters)
        self.assertEqual(result.clusters[0]["name"], "ai coding assistants")
        self.assertIn("best ai coding assistants", result.buyer_keywords)
        self.assertIn("how to use ai coding assistants", result.informational_keywords)
        self.assertIn("cursor vs windsurf", result.comparison_keywords)
        self.assertGreaterEqual(result.confidence, 0.6)
        self.assertTrue(result.reasoning)

    def test_detects_supporting_topics_and_pillar_suggestion(self) -> None:
        result = self.engine.analyze(
            [
                "best ai coding assistants",
                "ai coding assistants pricing",
                "how to use ai coding assistants",
                "ai coding assistant use cases",
            ],
            seed_topic="ai coding assistants",
        )

        self.assertTrue(result.supporting_topics)
        self.assertTrue(any("pricing" in topic.lower() for topic in result.supporting_topics))
        self.assertTrue(result.pillar_page_suggestion.lower().startswith("pillar"))
        self.assertTrue(result.supporting_article_ideas)

    def test_detects_comparison_keywords_and_supporting_article_ideas(self) -> None:
        result = self.engine.analyze(
            [
                "cursor vs windsurf",
                "github copilot alternatives",
                "best ai coding assistants",
                "what is copilot",
            ],
            seed_topic="ai coding assistants",
        )

        self.assertIn("cursor vs windsurf", result.comparison_keywords)
        self.assertIn("github copilot alternatives", result.comparison_keywords)
        self.assertTrue(any("comparison" in idea.lower() or "alternatives" in idea.lower() for idea in result.supporting_article_ideas))


if __name__ == "__main__":
    unittest.main()
