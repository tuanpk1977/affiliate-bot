import tempfile
from pathlib import Path
import unittest

from modules.bilingual_site import set_localized_seo_metadata
from modules.seo_metadata_uniqueness import rewrite_duplicate_metadata


HTML_TEMPLATE = """<!doctype html>
<html>
<head>
<title>{title}</title>
<meta name="description" content="{description}">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{description}">
<meta name="twitter:title" content="{title}">
<meta name="twitter:description" content="{description}">
</head>
<body>
<h1>{h1}</h1>
<p>Example content.</p>
</body>
</html>
"""


class SeoMetadataUniquenessTests(unittest.TestCase):
    def test_bilingual_pages_get_localized_metadata(self) -> None:
        html = HTML_TEMPLATE.format(
            title="Cursor vs GitHub Copilot",
            description="Compare features and pricing.",
            h1="Cursor vs GitHub Copilot",
        )
        updated = set_localized_seo_metadata(html, "/compare/cursor-vs-github-copilot/", "vi")
        self.assertIn("Cursor vs GitHub Copilot | Tiếng Việt", updated)
        self.assertIn("Bản tiếng Việt", updated)
        self.assertIn('meta property="og:title" content="Cursor vs GitHub Copilot | Tiếng Việt"', updated)
        self.assertIn('meta name="twitter:description"', updated)

    def test_duplicate_titles_and_descriptions_are_rewritten(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "one").mkdir()
            (root / "two").mkdir()
            (root / "vi" / "three").mkdir(parents=True)

            duplicate_title = "Duplicate Tool Review"
            duplicate_desc = "Shared description for two pages."

            (root / "one" / "index.html").write_text(
                HTML_TEMPLATE.format(title=duplicate_title, description=duplicate_desc, h1="Alpha Tool Review"),
                encoding="utf-8",
            )
            (root / "two" / "index.html").write_text(
                HTML_TEMPLATE.format(title=duplicate_title, description=duplicate_desc, h1="Beta Tool Review"),
                encoding="utf-8",
            )
            (root / "vi" / "three" / "index.html").write_text(
                HTML_TEMPLATE.format(title=duplicate_title, description=duplicate_desc, h1="Gamma Tool Review"),
                encoding="utf-8",
            )

            stats = rewrite_duplicate_metadata(root)
            self.assertEqual(stats["pages"], 3)
            self.assertGreaterEqual(stats["pages_changed"], 3)

            texts = [
                (root / "one" / "index.html").read_text(encoding="utf-8"),
                (root / "two" / "index.html").read_text(encoding="utf-8"),
                (root / "vi" / "three" / "index.html").read_text(encoding="utf-8"),
            ]
            titles = [self._extract(text, "title") for text in texts]
            descriptions = [self._extract_meta(text, "description") for text in texts]

            self.assertEqual(len(set(titles)), 3)
            self.assertEqual(len(set(descriptions)), 3)
            self.assertTrue(any("Tiếng Việt" in title for title in titles))

    def _extract(self, text: str, tag: str) -> str:
        import re

        match = re.search(rf"<{tag}\b[^>]*>(.*?)</{tag}>", text, flags=re.I | re.S)
        self.assertIsNotNone(match)
        return re.sub(r"\s+", " ", match.group(1)).strip()

    def _extract_meta(self, text: str, name: str) -> str:
        import re

        match = re.search(
            rf"<meta\b(?=[^>]*\bname=['\"]{name}['\"])[^>]*\bcontent=['\"]([^'\"]*)['\"][^>]*>",
            text,
            flags=re.I | re.S,
        )
        self.assertIsNotNone(match)
        return re.sub(r"\s+", " ", match.group(1)).strip()


if __name__ == "__main__":
    unittest.main()
