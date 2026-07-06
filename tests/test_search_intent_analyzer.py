import unittest

from modules.search_intent_analyzer import SearchIntentAnalysisResult, SearchIntentAnalyzer


class SearchIntentAnalyzerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.analyzer = SearchIntentAnalyzer()

    def test_detects_broad_top_funnel_informational_query(self) -> None:
        result = self.analyzer.analyze("ai coding assistants")

        self.assertIsInstance(result, SearchIntentAnalysisResult)
        self.assertEqual(result.search_intent, "informational")
        self.assertEqual(result.intent_depth, "shallow")
        self.assertEqual(result.scope, "broad")
        self.assertEqual(result.buyer_journey_stage, "awareness")
        self.assertEqual(result.funnel_stage, "top")
        self.assertLess(result.scores["intent_depth"], 0.55)
        self.assertLess(result.scores["scope"], 0.5)

    def test_detects_narrow_middle_funnel_commercial_query(self) -> None:
        result = self.analyzer.analyze("best ai coding assistants for teams")

        self.assertEqual(result.search_intent, "commercial")
        self.assertEqual(result.intent_depth, "medium")
        self.assertEqual(result.scope, "narrow")
        self.assertEqual(result.buyer_journey_stage, "consideration")
        self.assertEqual(result.funnel_stage, "middle")
        self.assertGreaterEqual(result.scores["scope"], 0.55)
        self.assertGreaterEqual(result.scores["buyer_journey"], 0.55)

    def test_detects_bottom_funnel_transactional_query(self) -> None:
        result = self.analyzer.analyze("canva pricing plans")

        self.assertEqual(result.search_intent, "transactional")
        self.assertEqual(result.intent_depth, "deep")
        self.assertEqual(result.scope, "narrow")
        self.assertEqual(result.buyer_journey_stage, "decision")
        self.assertEqual(result.funnel_stage, "bottom")
        self.assertGreaterEqual(result.scores["funnel"], 0.75)
        self.assertTrue(result.reasoning)


if __name__ == "__main__":
    unittest.main()
