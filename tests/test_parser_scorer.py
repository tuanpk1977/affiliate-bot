from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ads_compliance import build_ads_compliance_precheck
from parser import (
    is_recurring,
    normalize_commission_type,
    parse_commission_percent,
    parse_commission_text,
    parse_cookie_days,
    parse_flat_commission_amount,
    parse_payout_text,
)
from reviewer import build_review_workflow
from scorer import score_project


class ParserScorerTest(unittest.TestCase):
    def test_parser_extracts_common_affiliate_terms(self) -> None:
        text = (
            "Earn up to 40% recurring revenue share with a 90 day cookie. "
            "Payout via PayPal on Net 30."
        )

        self.assertEqual(parse_commission_text(text), "up to 40%")
        self.assertEqual(parse_commission_percent(text), 40)
        self.assertEqual(parse_cookie_days(text), 90)
        self.assertTrue(is_recurring(text))
        self.assertIn("paypal", parse_payout_text(text))
        self.assertIn("net 30", parse_payout_text(text))

    def test_parser_extracts_flat_commission(self) -> None:
        text = "Get $100 per sale. Minimum payout is $50."

        self.assertEqual(parse_flat_commission_amount(text), 100)
        self.assertEqual(normalize_commission_type(False, "$100 per sale"), "flat")

    def test_scorer_marks_strong_lead_as_ad_ready(self) -> None:
        result = score_project(
            {
                "category": "saas",
                "homepage_description": "B2B software platform",
                "commission_text": "40%",
                "commission_percent": 40,
                "flat_commission_amount": 0,
                "cookie_days": 90,
                "recurring": True,
                "payout_text": "paypal, net 30",
                "commission_type": "recurring",
                "affiliate_found": True,
                "legal_pages_found": True,
                "linkedin_found": True,
                "blog_found": True,
                "changelog_found": True,
                "status": "ok",
            }
        )

        self.assertGreaterEqual(result["total_score"], 80)
        self.assertEqual(result["verdict"], "Premium lead")
        self.assertIn("paid lead", result["recommended_action"])

    def test_reviewer_blocks_unverified_missing_terms(self) -> None:
        workflow = build_review_workflow(
            {
                "total_score": 85,
                "affiliate_quality_score": 90,
                "data_product_value_score": 90,
                "ad_readiness_score": 80,
                "affiliate_found": True,
                "affiliate_url": "https://example.com/affiliate",
                "commission_text": "",
                "payout_text": "",
                "cookie_days": 0,
                "legal_pages_found": False,
                "recurring": False,
                "status": "ok",
            }
        )

        self.assertEqual(workflow["review_status"], "needs_manual_review")
        self.assertEqual(workflow["sale_status"], "blocked_until_verified")
        self.assertIn("confirm commission rate", workflow["verification_checklist"])

    def test_reviewer_allows_verified_ready_candidate(self) -> None:
        workflow = build_review_workflow(
            {
                "total_score": 90,
                "affiliate_quality_score": 90,
                "data_product_value_score": 90,
                "ad_readiness_score": 80,
                "affiliate_found": True,
                "affiliate_url": "https://example.com/affiliate",
                "commission_text": "40%",
                "payout_text": "paypal, net 30",
                "cookie_days": 90,
                "legal_pages_found": True,
                "recurring": True,
                "status": "ok",
            }
        )

        self.assertEqual(workflow["review_status"], "ready_for_verification")
        self.assertEqual(workflow["sale_status"], "can_package_after_proof")
        self.assertEqual(workflow["ads_status"], "prepare_ad_test_after_terms_check")

    def test_ads_precheck_blocks_crypto_until_certified(self) -> None:
        result = build_ads_compliance_precheck(
            {
                "category": "crypto",
                "affiliate_text": "Earn up to 50% commission with our affiliate program.",
                "ads_status": "prepare_ad_test_after_terms_check",
            },
            timeout=5,
            user_agent="test",
        )

        self.assertEqual(result["ads_policy_risk"], "high")
        self.assertEqual(result["ads_status"], "blocked_by_ads_compliance")
        self.assertEqual(result["google_ads_precheck"], "requires_google_certification_and_local_legal_review")

    def test_ads_precheck_blocks_ppc_prohibited_terms(self) -> None:
        result = build_ads_compliance_precheck(
            {
                "category": "saas",
                "affiliate_text": "Affiliates earn 30%. PPC prohibited. No brand bidding.",
                "ads_status": "prepare_ad_test_after_terms_check",
            },
            timeout=5,
            user_agent="test",
        )

        self.assertEqual(result["ads_policy_risk"], "high")
        self.assertEqual(result["ads_status"], "blocked_by_ads_compliance")
        self.assertIn("ppc prohibited", result["ads_policy_findings"])


if __name__ == "__main__":
    unittest.main()
