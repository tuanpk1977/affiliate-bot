from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from modules.keyword_intelligence import analyze_keyword_opportunities, score_affiliate_intent, score_competition
from scripts.validate_keyword_intelligence import validate_text_integrity


class KeywordIntelligenceTest(unittest.TestCase):
    def test_affiliate_intent_detects_pricing_review_vs(self) -> None:
        self.assertGreaterEqual(score_affiliate_intent("cursor pricing", {}), 35)
        self.assertGreater(score_affiliate_intent("semrush review", {}), score_affiliate_intent("how to write content", {}))
        self.assertGreater(score_affiliate_intent("copilot vs cursor", {}), 50)

    def test_competition_scores_broad_terms_higher_than_niche_terms(self) -> None:
        self.assertGreater(score_competition("best ai tools", {}), 85)
        self.assertLess(score_competition("cursor pricing", {"competition_level": "Medium"}), 55)

    def test_analyze_keyword_opportunities_outputs_required_columns(self) -> None:
        keywords = pd.DataFrame(
            [
                {
                    "keyword": "cursor pricing",
                    "keyword_group": "buyer_keywords",
                    "intent_score": 90,
                    "competition_level": "Medium",
                    "estimated_cpc": 4.0,
                },
                {
                    "keyword": "random informational topic",
                    "keyword_group": "problem_solution_keywords",
                    "intent_score": 40,
                    "competition_level": "High",
                    "estimated_cpc": 1.0,
                },
            ]
        )
        result = analyze_keyword_opportunities(keywords)
        self.assertIn("seo_priority_score", result.columns)
        self.assertIn("recommended_action", result.columns)
        self.assertIn("suggested_slug", result.columns)
        self.assertIn("target_page_title", result.columns)
        self.assertIn("priority_rank", result.columns)
        self.assertEqual(result.iloc[0]["keyword"], "cursor pricing")
        self.assertEqual(result.iloc[0]["recommended_action"], "build_priority_page")
        self.assertEqual(result.iloc[0]["suggested_slug"], "cursor-pricing")

    def test_dedupes_normalized_keywords_and_keeps_best(self) -> None:
        keywords = pd.DataFrame(
            [
                {
                    "keyword": "  Cursor Pricing ",
                    "keyword_group": "buyer_keywords",
                    "intent_score": 90,
                    "competition_level": "Medium",
                    "estimated_cpc": 4.0,
                },
                {
                    "keyword": "cursor pricing",
                    "keyword_group": "problem_solution_keywords",
                    "intent_score": 40,
                    "competition_level": "High",
                    "estimated_cpc": 1.0,
                },
            ]
        )
        result = analyze_keyword_opportunities(keywords)
        self.assertEqual(len(result), 1)
        self.assertEqual(result.iloc[0]["keyword"], "cursor pricing")
        self.assertEqual(result.iloc[0]["priority_rank"], 1)

    def test_validator_rejects_truncated_keyword_tokens(self) -> None:
        df = pd.DataFrame(
            [
                {
                    "keyword": "email mark alternatives",
                    "suggested_slug": "email-mark-alternatives",
                    "target_page_title": "Best Email Mark Alternatives for 2026",
                }
            ]
        )
        errors = validate_text_integrity(df, "test.csv")
        self.assertTrue(errors)

    def test_validator_accepts_full_keyword_text(self) -> None:
        df = pd.DataFrame(
            [
                {
                    "keyword": "website builder alternatives",
                    "suggested_slug": "website-builder-alternatives",
                    "target_page_title": "Best Website Builder Alternatives for 2026",
                }
            ]
        )
        self.assertEqual(validate_text_integrity(df, "test.csv"), [])


if __name__ == "__main__":
    unittest.main()
