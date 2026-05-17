import re
import unittest

from config import settings


BREADCRUMB_NAV_RE = re.compile(
    r"<nav\b[^>]*class=['\"][^'\"]*\bbreadcrumb\b[^'\"]*['\"][^>]*>",
    re.IGNORECASE,
)


CHECK_PATHS = [
    "comparisons/framer-vs-webflow",
    "comparisons/cursor-vs-windsurf",
    "comparisons/copilot-vs-cursor",
    "cursor",
    "windsurf-review",
    "about",
]


class BreadcrumbIntegrityTest(unittest.TestCase):
    def read_page(self, path: str) -> str:
        return (settings.site_output_dir / path / "index.html").read_text(encoding="utf-8")

    def test_priority_pages_do_not_render_duplicate_breadcrumb_nav(self):
        for path in CHECK_PATHS:
            with self.subTest(path=path):
                html = self.read_page(path)
                self.assertLessEqual(
                    len(BREADCRUMB_NAV_RE.findall(html)),
                    1,
                    "page should not render duplicate visible breadcrumb nav blocks",
                )

    def test_comparison_pages_have_single_visible_breadcrumb_nav(self):
        for page in sorted((settings.site_output_dir / "comparisons").glob("*/index.html")):
            rel = page.relative_to(settings.site_output_dir).as_posix()
            with self.subTest(path=rel):
                html = page.read_text(encoding="utf-8")
                self.assertLessEqual(
                    len(BREADCRUMB_NAV_RE.findall(html)),
                    1,
                    "comparison page should have at most one visible breadcrumb nav block",
                )


if __name__ == "__main__":
    unittest.main()
