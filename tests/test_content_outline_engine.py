import unittest

from modules.content_outline_engine import ContentOutlineEngine, ContentOutlineResult


class ContentOutlineEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = ContentOutlineEngine()

    def test_builds_a_structured_outline_for_commercial_intent(self) -> None:
        result = self.engine.build_outline(
            topic="ai coding assistants",
            intent="commercial",
            keywords=["best ai coding assistants", "cursor vs windsurf", "pricing"],
        )

        self.assertIsInstance(result, ContentOutlineResult)
        self.assertEqual(result.topic, "ai coding assistants")
        self.assertEqual(result.intent, "commercial")
        self.assertTrue(result.sections)
        self.assertIn("comparison", [section.name.lower() for section in result.sections])
        self.assertTrue(result.recommended_cta)
        self.assertTrue(result.reasoning)

    def test_builds_an_informational_outline_with_steps(self) -> None:
        result = self.engine.build_outline(
            topic="ai coding assistants",
            intent="informational",
            keywords=["what is an ai coding assistant", "how to use ai coding assistant"],
        )

        self.assertTrue(any(section.name.lower() == "how to use" for section in result.sections))
        self.assertTrue(any(section.name.lower() == "faq" for section in result.sections))
        self.assertGreaterEqual(result.confidence, 0.6)


if __name__ == "__main__":
    unittest.main()
