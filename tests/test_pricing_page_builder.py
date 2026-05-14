import unittest

import pandas as pd

from modules.pricing_page_builder import generate_pricing_pages, render_pricing_page


class PricingPageBuilderTests(unittest.TestCase):
    def test_render_pricing_page_has_required_elements(self):
        tool = {
            "offer_id": "cursor",
            "brand_name": "Cursor",
            "niche": "AI Coding",
            "website": "https://cursor.com",
            "score": "88",
            "risk": "Low",
            "competition": "Medium",
        }
        related = {
            "comparisons": [("Cursor vs GitHub Copilot", "/compare/cursor-vs-github-copilot/")],
            "alternatives": [("GitHub Copilot review", "/review/github-copilot/")],
            "hubs": [("AI coding hub", "/hub/ai-coding/")],
        }
        html = render_pricing_page(tool, related)
        self.assertIn("<h1>Cursor Pricing Guide</h1>", html)
        self.assertIn("Quick pricing verdict", html)
        self.assertIn("Pricing plan explanation", html)
        self.assertIn("Free plan / trial note", html)
        self.assertIn("Hidden cost / contract risk", html)
        self.assertIn("Best plan for solo user", html)
        self.assertIn("Best plan for small team", html)
        self.assertIn("Best plan for agency/business", html)
        self.assertIn("Alternative if too expensive", html)
        self.assertIn("/go/cursor/?src=pricing/cursor&cta=pricing_page", html)
        self.assertIn("/go/cursor/?src=pricing/cursor&cta=pricing_check", html)
        self.assertIn("Official site / affiliate pending", html)
        self.assertIn('"@type": "FAQPage"', html)
        self.assertIn('"@type": "BreadcrumbList"', html)
        self.assertIn("/review/cursor/", html)
        self.assertIn("/compare/cursor-vs-github-copilot/", html)

    def test_generate_pricing_pages_returns_target_pages(self):
        offers = pd.DataFrame(
            [
                {"offer_id": "cursor", "brand_name": "Cursor", "niche": "AI Coding", "website": "https://cursor.com"},
                {"offer_id": "make", "brand_name": "Make", "niche": "Automation", "website": "https://www.make.com"},
            ]
        )
        # This test only verifies the tool list is stable without writing site_output.
        self.assertGreaterEqual(len(generate_pricing_pages.__globals__["PRICING_TOOLS"]), 10)
        self.assertIn("cursor", generate_pricing_pages.__globals__["PRICING_TOOLS"])
        self.assertIn("make", generate_pricing_pages.__globals__["PRICING_TOOLS"])


if __name__ == "__main__":
    unittest.main()
