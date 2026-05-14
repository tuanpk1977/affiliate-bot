import unittest

import pandas as pd

from modules.priority_page_builder import render_priority_page, select_tools_for_keyword, slugify


class PriorityPageBuilderTests(unittest.TestCase):
    def test_select_tools_matches_keyword_context(self):
        offers = pd.DataFrame(
            [
                {"offer_id": "cursor", "brand_name": "Cursor", "niche": "AI Coding", "total_score": 86},
                {"offer_id": "semrush", "brand_name": "Semrush", "niche": "AI SEO", "total_score": 84},
            ]
        )
        selected = select_tools_for_keyword("ai coding alternatives", offers)
        self.assertEqual(selected.iloc[0]["offer_id"], "cursor")

    def test_render_priority_page_has_required_elements(self):
        row = {
            "keyword": "email marketing alternatives",
            "suggested_slug": "email-marketing-alternatives",
            "target_page_title": "Best Email Marketing Alternatives for 2026",
        }
        tools = pd.DataFrame(
            [
                {
                    "offer_id": "activecampaign",
                    "brand_name": "ActiveCampaign",
                    "niche": "Email Marketing",
                    "total_score": 82,
                    "risk_level": "Medium",
                    "recommendation": "Good for research-driven email automation comparisons.",
                }
            ]
        )
        html = render_priority_page(row, tools)
        self.assertIn("<title>Best Email Marketing Alternatives for 2026", html)
        self.assertIn("/go/activecampaign/?src=/email-marketing-alternatives/&cta=priority_page", html)
        self.assertIn('"@type": "FAQPage"', html)
        self.assertIn('"@type": "BreadcrumbList"', html)
        self.assertIn("Some links may be affiliate links", html)
        self.assertIn("email marketing alternatives", html)
        self.assertIn("replacement", html.lower())
        self.assertIn("shortlist", html.lower())
        self.assertIn("risk", html.lower())

    def test_slugify_preserves_full_words(self):
        self.assertEqual(slugify("Website Builder Alternatives"), "website-builder-alternatives")


if __name__ == "__main__":
    unittest.main()
