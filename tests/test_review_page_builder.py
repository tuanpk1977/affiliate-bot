import unittest

import pandas as pd

from modules.review_page_builder import prepare_tools, render_review_page, select_related_tools, slugify


class ReviewPageBuilderTests(unittest.TestCase):
    def test_render_review_page_has_required_elements(self):
        tool = {
            "offer_id": "cursor",
            "brand_name": "Cursor",
            "niche": "AI Coding",
            "website": "https://cursor.com",
            "affiliate_url": "",
            "score": "88",
            "risk": "Low",
            "competition": "Medium",
            "trend": "Rising",
            "recommended_channels": "Google Search, developer newsletters",
        }
        related = [
            {
                "offer_id": "github-copilot",
                "brand_name": "GitHub Copilot",
                "niche": "AI Coding",
                "website": "https://github.com/features/copilot",
                "affiliate_url": "",
                "score": "88",
                "risk": "Low",
                "competition": "Medium",
                "trend": "Rising",
                "recommended_channels": "Google Search",
            }
        ]
        html = render_review_page(tool, related)
        self.assertIn("<h1>Cursor Review for AI Coding Buyers</h1>", html)
        self.assertIn("/go/cursor/?src=review/cursor&amp;cta=review_page", html)
        self.assertIn("/go/cursor/?src=review/cursor&amp;cta=pricing_check", html)
        self.assertIn("Official site / affiliate pending", html)
        self.assertIn("Quick verdict", html)
        self.assertIn("Best for / Not best for", html)
        self.assertIn("Feature checklist", html)
        self.assertIn("Real buying considerations", html)
        self.assertIn("Some links may be affiliate links", html)
        self.assertIn('"@type": "FAQPage"', html)
        self.assertIn('"@type": "BreadcrumbList"', html)
        self.assertIn("/review/github-copilot/", html)

    def test_prepare_tools_dedupes_and_keeps_brand_names(self):
        offers = pd.DataFrame(
            [
                {"offer_id": "make", "brand_name": "Make", "niche": "Automation", "total_score": 88},
                {"offer_id": "make", "brand_name": "Make", "niche": "Automation", "total_score": 80},
            ]
        )
        tools = prepare_tools(offers)
        self.assertEqual(len(tools), 1)
        self.assertEqual(tools.iloc[0]["brand_name"], "Make")

    def test_select_related_tools_prefers_same_niche(self):
        current = {"offer_id": "cursor", "brand_name": "Cursor", "niche": "AI Coding"}
        all_tools = [
            current,
            {"offer_id": "github-copilot", "brand_name": "GitHub Copilot", "niche": "AI Coding"},
            {"offer_id": "semrush", "brand_name": "Semrush", "niche": "AI SEO"},
        ]
        related = select_related_tools(current, all_tools)
        self.assertEqual(related[0]["offer_id"], "github-copilot")

    def test_slugify(self):
        self.assertEqual(slugify("GitHub Copilot"), "github-copilot")


if __name__ == "__main__":
    unittest.main()
