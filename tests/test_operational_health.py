from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from modules.content_quality import inspect_content
from modules.operational_health import audit_site, safe_repair_pages, write_health_reports


def page(url: str, title: str = "Example Review") -> str:
    schema = [
        {
            "@context": "https://schema.org",
            "@type": "Article",
            "headline": title,
            "author": {"@type": "Person", "name": "Tuan Nguyen Quoc"},
        },
        {
            "@context": "https://schema.org",
            "@type": "BreadcrumbList",
            "itemListElement": [{"@type": "ListItem", "position": 1, "name": "Home", "item": "https://smileaireviewhub.com/"}],
        },
        {
            "@context": "https://schema.org",
            "@type": "FAQPage",
            "mainEntity": [{"@type": "Question", "name": "Is it useful?", "acceptedAnswer": {"@type": "Answer", "text": "It depends on the workflow."}}],
        },
    ]
    return f"""<!doctype html><html><head>
<title>{title}</title><meta name="description" content="A practical review.">
<meta name="robots" content="index,follow,max-image-preview:large">
<meta property="og:title" content="{title}"><meta property="og:description" content="A practical review.">
<meta name="twitter:card" content="summary_large_image"><link rel="canonical" href="{url}">
<script type="application/ld+json">{json.dumps(schema)}</script></head>
<body><h1>{title}</h1><p>This detailed introduction explains the product, its intended audience, practical constraints, and the evidence buyers should verify before making a decision.</p>
<img src="/assets/example.png" alt="Example product dashboard">
<a href="/">Home</a><a href="/related/">Related</a><a href="https://example.org/reference">Reference</a>
<h2>Frequently Asked Questions</h2><p>Check the official website before making a decision and compare the available options.</p></body></html>"""


class OperationalHealthTest(unittest.TestCase):
    def test_clean_site_generates_reports(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "assets").mkdir()
            (root / "assets" / "example.png").write_bytes(b"png")
            (root / "related").mkdir()
            (root / "related" / "index.html").write_text(page("https://smileaireviewhub.com/related/", "Related Review"), encoding="utf-8")
            (root / "index.html").write_text(page("https://smileaireviewhub.com/", "Home Review"), encoding="utf-8")
            urls = ["https://smileaireviewhub.com/", "https://smileaireviewhub.com/related/"]
            (root / "sitemap.xml").write_text(
                '<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
                + "".join(f"<url><loc>{url}</loc><lastmod>2026-07-02</lastmod></url>" for url in urls)
                + "</urlset>",
                encoding="utf-8",
            )
            (root / "robots.txt").write_text(
                "User-agent: *\nAllow: /\nSitemap: https://smileaireviewhub.com/sitemap.xml\n",
                encoding="utf-8",
            )
            audit = audit_site(root)
            self.assertEqual(audit.summary()["sitemap_status"], "PASS")
            self.assertEqual(audit.summary()["broken_internal_links"], 0)
            outputs = write_health_reports(audit, root / "reports", today_urls=urls)
            self.assertTrue(outputs["health"].exists())
            self.assertTrue(outputs["dashboard_json"].exists())

    def test_content_qa_detects_and_repairs_exact_repeat(self) -> None:
        with TemporaryDirectory() as temp:
            target = Path(temp) / "index.html"
            repeated = "This is a sufficiently long paragraph that should never appear twice in a useful buyer-focused article because repetition reduces quality."
            target.write_text(
                f"<html><body><h1>Review</h1><p>{repeated}</p><p>{repeated}</p>"
                "<h2>Frequently Asked Questions</h2><p>Visit the official website to compare the product.</p></body></html>",
                encoding="utf-8",
            )
            before = inspect_content(target)
            self.assertFalse(before.ok)
            after = inspect_content(target, repair=True)
            self.assertTrue(after.ok)
            self.assertEqual(target.read_text(encoding="utf-8").count(repeated), 1)

    def test_safe_repair_adds_author_breadcrumb_and_obvious_link_target(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "assets").mkdir()
            (root / "assets" / "example.png").write_bytes(b"png")
            (root / "related-review").mkdir()
            target_url = "https://smileaireviewhub.com/related-review/"
            (root / "related-review" / "index.html").write_text(page(target_url, "Related Review"), encoding="utf-8")
            review_dir = root / "product-review"
            review_dir.mkdir()
            source_url = "https://smileaireviewhub.com/product-review/"
            source = page(source_url, "Product Review")
            source = source.replace(
                '"author": {"@type": "Person", "name": "Tuan Nguyen Quoc"}',
                '"author": ""',
                1,
            )
            source = source.replace(
                '<a href="/related/">Related</a>',
                '<a href="/related-revie/">Related</a>',
            )
            source = source.replace('"@type": "BreadcrumbList"', '"@type": "WebPage"', 1)
            (review_dir / "index.html").write_text(source, encoding="utf-8")
            result = safe_repair_pages(root, [source_url])
            updated = (review_dir / "index.html").read_text(encoding="utf-8")
            self.assertIn('"name": "Tuan Nguyen Quoc"', updated)
            self.assertIn('"@type": "BreadcrumbList"', updated)
            self.assertIn('href="/related-review/"', updated)
            self.assertIn(source_url, result["repaired"])


if __name__ == "__main__":
    unittest.main()
