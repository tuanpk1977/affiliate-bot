from __future__ import annotations

from datetime import date, datetime, timezone
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from modules.publishing_indexing import BASE_URL, validate_batch, validate_sitemap
from modules.sitemap_generator import generate_sitemap, read_lastmod_map
from modules.search_engine_submission import submit_bing_sitemap, submit_google_sitemap


def page_html(url: str) -> str:
    article = {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": "Test article",
        "author": {"@type": "Person", "name": "Tuan Nguyen Quoc"},
    }
    breadcrumb = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [{"@type": "ListItem", "position": 1, "name": "Home", "item": f"{BASE_URL}/"}],
    }
    return (
        "<!doctype html><html><head>"
        f'<link rel="canonical" href="{url}">'
        f'<script type="application/ld+json">{json.dumps(article)}</script>'
        f'<script type="application/ld+json">{json.dumps(breadcrumb)}</script>'
        "</head><body><a href='/'>Home</a></body></html>"
    )


def sitemap_xml(rows: list[tuple[str, str]]) -> str:
    items = "".join(
        f"<url><loc>{url}</loc><lastmod>{lastmod}</lastmod></url>" for url, lastmod in rows
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        f"{items}</urlset>"
    )


class PublishingIndexingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.docs = self.root / "docs"
        self.docs.mkdir()
        (self.docs / "index.html").write_text(page_html(f"{BASE_URL}/"), encoding="utf-8")
        self.url = f"{BASE_URL}/test-article/"
        target = self.docs / "test-article"
        target.mkdir()
        (target / "index.html").write_text(page_html(self.url), encoding="utf-8")
        self.sitemap = self.docs / "sitemap.xml"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_valid_batch_passes(self) -> None:
        self.sitemap.write_text(
            sitemap_xml([(f"{BASE_URL}/", "2026-07-02"), (self.url, "2026-07-02")]),
            encoding="utf-8",
        )
        result = validate_batch(
            self.docs,
            self.sitemap,
            [self.url],
            expected_lastmod=date(2026, 7, 2),
        )
        self.assertTrue(result.ok, result.to_dict())
        self.assertEqual(result.sitemap.total_urls, 2)

    def test_duplicate_sitemap_url_fails(self) -> None:
        self.sitemap.write_text(
            sitemap_xml([(self.url, "2026-07-02"), (self.url, "2026-07-02")]),
            encoding="utf-8",
        )
        result = validate_sitemap(self.sitemap, self.docs, [self.url])
        self.assertFalse(result.ok)
        self.assertEqual(result.duplicate_urls, [self.url])

    def test_missing_published_url_and_old_lastmod_fail(self) -> None:
        self.sitemap.write_text(
            sitemap_xml([(f"{BASE_URL}/", "2026-06-01")]),
            encoding="utf-8",
        )
        result = validate_sitemap(
            self.sitemap,
            self.docs,
            [self.url],
            expected_lastmod=date(2026, 7, 2),
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.published_urls_missing, [self.url])

    def test_sitemap_generation_preserves_old_lastmod(self) -> None:
        self.sitemap.write_text(
            sitemap_xml([(f"{BASE_URL}/", "2026-01-10"), (self.url, "2026-01-11")]),
            encoding="utf-8",
        )
        generate_sitemap(self.docs, BASE_URL, updated_urls=[self.url])
        lastmods = read_lastmod_map(self.sitemap)
        self.assertEqual(lastmods[f"{BASE_URL}/"], "2026-01-10")
        self.assertEqual(lastmods[self.url], date.today().isoformat())

    def test_bing_missing_credentials_is_safe(self) -> None:
        state = self.root / "state.json"
        log = self.root / "bing.log"
        result = submit_bing_sitemap(
            f"{BASE_URL}/",
            f"{BASE_URL}/sitemap.xml",
            state_path=state,
            log_path=log,
            dry_run=True,
        )
        self.assertIn(result.status, {"dry_run", "skipped_missing_credentials"})
        self.assertTrue(log.exists())

    def test_google_missing_credentials_uses_natural_discovery(self) -> None:
        state = self.root / "state.json"
        log = self.root / "google.log"
        result = submit_google_sitemap(
            f"{BASE_URL}/",
            f"{BASE_URL}/sitemap.xml",
            state_path=state,
            log_path=log,
            dry_run=True,
        )
        self.assertIn(result.status, {"dry_run", "queued_natural_discovery"})
        self.assertTrue(log.exists())

    def test_bing_daily_limit_prevents_second_submission(self) -> None:
        state = self.root / "state.json"
        log = self.root / "bing.log"
        state.write_text(
            json.dumps({"bing_sitemap_submitted_at": datetime.now(timezone.utc).isoformat()}),
            encoding="utf-8",
        )
        with patch.dict(os.environ, {"BING_WEBMASTER_API_KEY": "not-used"}, clear=False):
            result = submit_bing_sitemap(
                f"{BASE_URL}/",
                f"{BASE_URL}/sitemap.xml",
                state_path=state,
                log_path=log,
            )
        self.assertEqual(result.status, "skipped_daily_limit")
        self.assertFalse(result.attempted)


if __name__ == "__main__":
    unittest.main()
