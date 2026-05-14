import unittest

from modules.category_page_builder import render_category_page


class CategoryPageBuilderTests(unittest.TestCase):
    def test_render_category_page_has_required_elements(self):
        category = {
            "slug": "ai-coding-tools",
            "title": "AI Coding Tools",
            "tools": ["cursor", "github-copilot"],
            "hub": "/hub/ai-coding/",
            "toplist": "/best-ai-coding-tools/",
            "angle": "developer productivity, code review, repository context, and team policy",
        }
        tools = [
            {"offer_id": "cursor", "brand_name": "Cursor", "niche": "AI Coding", "website": "https://cursor.com", "score": "88", "risk": "Low", "competition": "Medium"},
            {"offer_id": "github-copilot", "brand_name": "GitHub Copilot", "niche": "AI Coding", "website": "https://github.com/features/copilot", "score": "88", "risk": "Low", "competition": "Medium"},
        ]
        html = render_category_page(category, tools)
        self.assertIn("<h1>AI Coding Tools: Research Guide and Shortlist</h1>", html)
        self.assertIn("Best tools table", html)
        self.assertIn("Best for solo / team / agency", html)
        self.assertIn("How to choose AI Coding Tools", html)
        self.assertIn("Common mistakes", html)
        self.assertIn("/go/cursor/?src=category/ai-coding-tools&cta=category_page", html)
        self.assertIn("/review/cursor/", html)
        self.assertIn("/compare/cursor-vs-github-copilot/", html)
        self.assertIn("/pricing/cursor/", html)
        self.assertIn('"@type": "FAQPage"', html)
        self.assertIn('"@type": "BreadcrumbList"', html)


if __name__ == "__main__":
    unittest.main()
