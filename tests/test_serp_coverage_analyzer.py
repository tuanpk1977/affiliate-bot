import unittest

from modules.serp_coverage_analyzer import SerpCoverageAnalysisResult, SerpCoverageAnalyzer


class SerpCoverageAnalyzerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.analyzer = SerpCoverageAnalyzer()

    def test_rates_coverage_for_a_planned_article(self) -> None:
        planned_sections = [
            "what is ai coding assistant",
            "how to use ai coding assistant",
            "best ai coding assistants",
            "pricing",
            "faq",
        ]
        entities = ["copilot", "cursor", "windsurf"]
        keywords = [
            "ai coding assistant",
            "best ai coding assistants",
            "ai coding assistant pricing",
            "how to use ai coding assistant",
            "cursor vs windsurf",
            "what is an ai coding assistant",
        ]

        result = self.analyzer.analyze(planned_sections, entities, keywords, topic="ai coding assistants")

        self.assertIsInstance(result, SerpCoverageAnalysisResult)
        self.assertGreaterEqual(result.coverage_score, 55)
        self.assertTrue(result.missing_subtopics)
        self.assertTrue(result.missing_entities)
        self.assertTrue(result.faq_opportunities)
        self.assertTrue(result.comparison_gaps)
        self.assertTrue(result.improvement_suggestions)
        self.assertTrue(result.reasoning)

    def test_detects_missing_comparison_and_buyer_questions(self) -> None:
        result = self.analyzer.analyze(
            ["what is ai coding assistant", "pricing"],
            ["copilot"],
            ["ai coding assistant pricing", "best ai coding assistants"],
            topic="ai coding assistants",
        )

        self.assertIn("comparison", result.missing_sections)
        self.assertTrue(any("buyer" in suggestion.lower() for suggestion in result.improvement_suggestions))


if __name__ == "__main__":
    unittest.main()
