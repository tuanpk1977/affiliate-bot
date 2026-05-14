import unittest

import pandas as pd

from modules.comparison_page_builder import build_tool_map, render_comparison_page


class ComparisonPageBuilderTests(unittest.TestCase):
    def test_render_comparison_page_has_required_elements(self):
        left = {
            "offer_id": "cursor",
            "brand_name": "Cursor",
            "niche": "AI Coding",
            "website": "https://cursor.com",
            "affiliate_url": "",
            "score": "88",
            "risk": "Low",
            "competition": "Medium",
            "trend": "Rising",
            "recommended_channels": "Google Search",
        }
        right = {
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
        html = render_comparison_page(left, right, "AI coding assistants")
        self.assertIn("<h1>Cursor vs GitHub Copilot</h1>", html)
        self.assertIn("/go/cursor/?src=compare/cursor-vs-github-copilot&cta=comparison_page", html)
        self.assertIn("/go/github-copilot/?src=compare/cursor-vs-github-copilot&cta=comparison_page", html)
        self.assertIn("Quick comparison table", html)
        self.assertIn("Quick verdict", html)
        self.assertIn("Choose Cursor if...", html)
        self.assertIn("Choose GitHub Copilot if...", html)
        self.assertIn("scorecard", html)
        self.assertIn("ease_of_use", html)
        self.assertIn("Migration / switching", html)
        self.assertIn("Pricing and contract risk", html)
        self.assertIn("Team size recommendation", html)
        self.assertIn("Best alternative if neither fits", html)
        self.assertIn("Final verdict", html)
        self.assertIn('"@type": "FAQPage"', html)
        self.assertIn('"@type": "BreadcrumbList"', html)

    def test_build_tool_map_adds_fallback_tools(self):
        offers = pd.DataFrame([{"offer_id": "cursor", "brand_name": "Cursor", "niche": "AI Coding", "website": "https://cursor.com"}])
        tools = build_tool_map(offers)
        self.assertIn("cursor", tools)
        self.assertIn("windsurf", tools)
        self.assertEqual(tools["windsurf"]["brand_name"], "Windsurf")


if __name__ == "__main__":
    unittest.main()
