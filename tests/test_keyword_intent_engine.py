import unittest

from modules.keyword_intent_engine import IntentAnalysisResult, KeywordIntentEngine


class KeywordIntentEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = KeywordIntentEngine()

    def test_detects_best_list_intent_and_article_type(self) -> None:
        result = self.engine.analyze("best ai writing tools for teams in 2026")

        self.assertIsInstance(result, IntentAnalysisResult)
        self.assertEqual(result.search_intent, "commercial")
        self.assertEqual(result.article_type, "best list")
        self.assertGreaterEqual(result.intent_confidence, 0.6)
        self.assertGreaterEqual(result.article_type_confidence, 0.6)
        self.assertTrue(any("best" in reason.lower() for reason in result.reasoning))

    def test_detects_comparison_for_vs_queries(self) -> None:
        result = self.engine.analyze("cursor vs windsurf")

        self.assertEqual(result.search_intent, "commercial")
        self.assertEqual(result.article_type, "comparison")
        self.assertGreaterEqual(result.intent_confidence, 0.65)
        self.assertGreaterEqual(result.article_type_confidence, 0.7)

    def test_detects_informational_tutorial_content(self) -> None:
        result = self.engine.analyze("how to use notional ai for content writing")

        self.assertEqual(result.search_intent, "informational")
        self.assertEqual(result.article_type, "tutorial")
        self.assertGreaterEqual(result.intent_confidence, 0.65)
        self.assertGreaterEqual(result.article_type_confidence, 0.7)

    def test_detects_transactional_pricing_intent(self) -> None:
        result = self.engine.analyze("canva pricing plans")

        self.assertEqual(result.search_intent, "transactional")
        self.assertEqual(result.article_type, "pricing")
        self.assertGreaterEqual(result.intent_confidence, 0.7)
        self.assertGreaterEqual(result.article_type_confidence, 0.75)

    def test_detects_navigational_intent_for_brand_pages(self) -> None:
        result = self.engine.analyze("notion official login")

        self.assertEqual(result.search_intent, "navigational")
        self.assertEqual(result.article_type, "review")
        self.assertGreaterEqual(result.intent_confidence, 0.6)
        self.assertGreaterEqual(result.article_type_confidence, 0.4)


if __name__ == "__main__":
    unittest.main()
