from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from modules.competitor_trends import (
    CompetitorArticle,
    parse_feed,
    parse_sitemap_index,
    scan_competitors,
    score_articles,
    write_reports,
)


class CompetitorTrendTest(unittest.TestCase):
    def test_feed_and_sitemap_index_parsing(self) -> None:
        feed = """<rss><channel><item><title>AI Coding Tool Pricing</title>
        <link>https://example.com/ai-coding-pricing/</link>
        <description>Pricing and alternatives for developers.</description>
        <pubDate>Wed, 01 Jul 2026 08:00:00 GMT</pubDate></item></channel></rss>"""
        rows = parse_feed(feed, "Example")
        self.assertEqual(rows[0].title, "AI Coding Tool Pricing")
        sitemap_index = """<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
        <sitemap><loc>https://example.com/posts.xml</loc></sitemap></sitemapindex>"""
        self.assertEqual(parse_sitemap_index(sitemap_index), ["https://example.com/posts.xml"])

    def test_scoring_recommends_create_or_refresh(self) -> None:
        articles = [
            CompetitorArticle(
                competitor="One",
                url="https://one.example/new-ai-coding-tool/",
                title="New AI Coding Tool Review",
                published_at="2026-07-01T08:00:00+00:00",
                keywords=["ai coding tool", "coding tool review"],
            ),
            CompetitorArticle(
                competitor="Two",
                url="https://two.example/ai-coding-tool-pricing/",
                title="AI Coding Tool Pricing",
                published_at="2026-07-01T09:00:00+00:00",
                keywords=["ai coding tool", "coding tool pricing"],
            ),
        ]
        candidates = score_articles(articles, [])
        target = next(row for row in candidates if row.keyword == "ai coding tool")
        self.assertEqual(target.competitor_frequency, 2)
        self.assertEqual(target.recommended_action, "create")
        self.assertGreaterEqual(target.trend_score, 70)

    def test_scanner_uses_cached_robots_and_writes_reports(self) -> None:
        sitemap = """<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
        <url><loc>https://example.com/ai-tool-review/</loc><lastmod>2026-07-01</lastmod></url>
        </urlset>"""
        html = """<html><head><title>AI Tool Review and Pricing</title>
        <meta name="description" content="Compare AI software pricing and alternatives."></head>
        <body><h1>AI Tool Review</h1><h2>Pricing</h2><h2>Alternatives</h2></body></html>"""
        calls: list[str] = []

        def fetcher(url: str) -> tuple[int, str]:
            calls.append(url)
            if url.endswith("robots.txt"):
                return 200, "User-agent: *\nAllow: /\n"
            if url.endswith("sitemap.xml"):
                return 200, sitemap
            return 200, html

        with TemporaryDirectory() as temp:
            root = Path(temp)
            candidates, failures = scan_competitors(
                [{"name": "Example", "website_url": "https://example.com/", "sitemap_url": "https://example.com/sitemap.xml", "priority": 1}],
                root,
                max_items=2,
                delay_seconds=0,
                fetcher=fetcher,
            )
            self.assertFalse(failures)
            self.assertTrue(candidates)
            self.assertEqual(calls.count("https://example.com/robots.txt"), 1)
            md_path, json_path = write_reports(candidates, failures, root / "reports")
            self.assertTrue(md_path.exists())
            self.assertTrue(json_path.exists())

if __name__ == "__main__":
    unittest.main()
