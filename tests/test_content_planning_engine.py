import unittest

from modules.content_planning_engine import ContentPlanningEngine, ContentPlanResult
class ContentPlanningEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.planner = ContentPlanningEngine()

    def test_creates_plan_for_keyword(self) -> None:
        result = self.planner.create_plan("best ai coding assistants")

        self.assertIsInstance(result, ContentPlanResult)
        self.assertEqual(result.keyword, "best ai coding assistants")
        self.assertIn(result.search_intent, {"informational", "commercial", "transactional", "navigational"})
        self.assertIn(result.article_type, {"review", "comparison", "alternatives", "best list", "tutorial", "pricing", "use cases"})
        self.assertTrue(0 <= result.confidence <= 1.0)
        self.assertTrue(result.reasoning)

    def test_plan_includes_all_required_fields(self) -> None:
        result = self.planner.create_plan("ai coding assistants pricing")

        required_fields = [
            "keyword", "search_intent", "article_type", "cluster",
            "coverage_score", "outline_sections", "recommended_cta", "confidence", "reasoning",
        ]
        for field_name in required_fields:
            self.assertTrue(hasattr(result, field_name), f"Missing field: {field_name}")

        self.assertTrue(result.outline_sections)
        self.assertTrue(result.recommended_cta)
        self.assertTrue(result.reasoning)

    def test_detects_commercial_intent_and_best_list(self) -> None:
        result = self.planner.create_plan("best ai coding assistants for teams")

        self.assertEqual(result.search_intent, "commercial")
        self.assertEqual(result.article_type, "best list")
        self.assertGreaterEqual(result.confidence, 0.55)

    def test_detects_transactional_pricing_plan(self) -> None:
        result = self.planner.create_plan("canva pricing plans")

        self.assertEqual(result.search_intent, "transactional")
        self.assertEqual(result.article_type, "pricing")
        self.assertGreaterEqual(result.confidence, 0.6)

    def test_handles_informational_queries(self) -> None:
        result = self.planner.create_plan("how to use ai coding assistants")

        self.assertEqual(result.search_intent, "informational")
        self.assertEqual(result.article_type, "tutorial")
        self.assertGreaterEqual(result.confidence, 0.5)

    def test_includes_cluster_info(self) -> None:
        result = self.planner.create_plan("cursor vs windsurf")

        self.assertIn("clusters", result.cluster)
        self.assertEqual(result.cluster["name"], "cursor vs windsurf")
        self.assertTrue(result.cluster["keywords"])

    def test_includes_coverage_score(self) -> None:
        result = self.planner.create_plan("ai coding assistants")

        self.assertGreaterEqual(result.coverage_score, 0)
        self.assertLessEqual(result.coverage_score, 100)

    def test_includes_outline_sections(self) -> None:
        result = self.planner.create_plan("best ai coding assistants")

        self.assertTrue(result.outline_sections)
        expected_sections = {"quick verdict", "comparison", "pricing"}
        sections_lower = {s.lower() for s in result.outline_sections}
        self.assertTrue(
            any(expected in " ".join(sections_lower) for expected in expected_sections),
            f"Expected sections {expected_sections} not found in {sections_lower}",
        )

    def test_includes_reasoning(self) -> None:
        result = self.planner.create_plan("best ai coding assistants for teams")

        self.assertTrue(len(result.reasoning) > 0)
        self.assertTrue(any("confidence" in reason.lower() for reason in result.reasoning))

    def test_creates_multiple_plans(self) -> None:
        keywords = [
            "best ai coding assistants",
            "how to use ai coding assistants",
            "canva pricing plans",
        ]
        results = self.planner.create_plan_many(keywords)

        self.assertEqual(len(results), len(keywords))
        for plan, kw in zip(results, keywords):
            self.assertEqual(plan.keyword, kw)
            self.assertIsInstance(plan, ContentPlanResult)

    def test_handles_empty_related_keywords(self) -> None:
        result = self.planner.create_plan("best ai coding assistants", related_keywords=[])

        self.assertEqual(result.keyword, "best ai coding assistants")
        self.assertTrue(result.reasoning)

    def test_handles_empty_entities(self) -> None:
        result = self.planner.create_plan("best ai coding assistants", entities=[])

        self.assertEqual(result.keyword, "best ai coding assistants")
        self.assertTrue(result.reasoning)

    def test_confidence_calculation(self) -> None:
        keyword_result = self.planner.keyword_engine.analyze("best ai coding assistants for teams")
        search_result = self.planner.search_analyzer.analyze("best ai coding assistants for teams")
        outline_result = self.planner.outline_engine.build_outline(
            topic="best ai coding assistants for teams",
            intent=keyword_result.search_intent,
        )

        coverage_result = self.planner.coverage_analyzer.analyze(
            planned_sections=[s.name for s in outline_result.sections],
            entities=["copilot", "cursor", "windsurf"],
            keywords=["best ai coding assistants for teams"],
            topic="best ai coding assistants for teams",
        )

        confidence = self.planner._calculate_overall_confidence(
            keyword_result, search_result, coverage_result, outline_result,
        )

        self.assertGreaterEqual(confidence, 0.0)
        self.assertLessEqual(confidence, 1.0)

    def test_reasoning_combines_all_components(self) -> None:
        result = self.planner.create_plan("cursor vs windsurf")

        self.assertTrue(len(result.reasoning) >= 4)
        has_keyword_reasoning = any("keyword" in reason.lower() for reason in result.reasoning)
        self.assertTrue(has_keyword_reasoning, "Planning reasoning should include keyword analysis")


if __name__ == "__main__":
    unittest.main()