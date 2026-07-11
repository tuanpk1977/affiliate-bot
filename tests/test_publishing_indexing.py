from __future__ import annotations

from datetime import date, datetime, timezone
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from modules.publishing_indexing import BASE_URL, validate_batch, validate_live_pages, validate_sitemap
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
    faq = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name": "Is this a test?",
                "acceptedAnswer": {"@type": "Answer", "text": "Yes, this is a validation fixture."},
            }
        ],
    }
    return (
        "<!doctype html><html><head>"
        "<title>Test article</title>"
        '<meta name="description" content="A complete publishing validation fixture.">'
        '<meta property="og:title" content="Test article">'
        '<meta property="og:description" content="A complete publishing validation fixture.">'
        '<meta name="twitter:card" content="summary_large_image">'
        f'<link rel="canonical" href="{url}">'
        f'<script type="application/ld+json">{json.dumps(article)}</script>'
        f'<script type="application/ld+json">{json.dumps(breadcrumb)}</script>'
        f'<script type="application/ld+json">{json.dumps(faq)}</script>'
        "</head><body><h1>Test article</h1>"
        "<img src='/assets/test.png' alt='Test product interface'>"
        f"<a href='/'>Home</a><a href='{url}'>Current article</a>"
        "<a href='https://example.org/reference'>Official reference</a></body></html>"
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
        (self.docs / "assets").mkdir()
        (self.docs / "assets" / "test.png").write_bytes(b"png")
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

    def test_smart_live_validation_checks_full_page_contract(self) -> None:
        source = page_html(self.url)
        with patch("modules.publishing_indexing.fetch_url", return_value=(200, source)):
            ok, failures = validate_live_pages([self.url])
        self.assertTrue(ok, failures)

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

    def test_targeted_validation_ignores_unrelated_review_canonical_issue(self) -> None:
        review_url = f"{BASE_URL}/review/old-dashboard/"
        self.sitemap.write_text(
            sitemap_xml([(self.url, "2026-07-11"), (review_url, "2026-07-01")]),
            encoding="utf-8",
        )
        targeted = validate_batch(self.docs, self.sitemap, [self.url], validate_all_canonicals=False)
        full_site = validate_batch(self.docs, self.sitemap, [self.url], validate_all_canonicals=True)

        self.assertTrue(targeted.ok, targeted.to_dict())
        self.assertFalse(full_site.ok)
        self.assertTrue(any("review/old-dashboard" in item for item in full_site.sitemap.canonical_mismatches))

    def test_selected_article_missing_canonical_blocks_targeted_validation(self) -> None:
        self.sitemap.write_text(sitemap_xml([(self.url, "2026-07-11")]), encoding="utf-8")
        target = self.docs / "test-article" / "index.html"
        target.write_text(page_html(self.url).replace('<link rel="canonical" href="' + self.url + '">', ""), encoding="utf-8")

        result = validate_batch(self.docs, self.sitemap, [self.url], validate_all_canonicals=False)

        self.assertFalse(result.ok)
        self.assertTrue(any("canonical" in error for error in result.pages[0].errors))

    def test_sitemap_generation_preserves_old_lastmod(self) -> None:
        self.sitemap.write_text(
            sitemap_xml([(f"{BASE_URL}/", "2026-01-10"), (self.url, "2026-01-11")]),
            encoding="utf-8",
        )
        generate_sitemap(self.docs, BASE_URL, updated_urls=[self.url])
        lastmods = read_lastmod_map(self.sitemap)
        self.assertEqual(lastmods[f"{BASE_URL}/"], "2026-01-10")
        self.assertEqual(lastmods[self.url], date.today().isoformat())

    def test_sitemap_generation_excludes_internal_review_draft_and_report_routes(self) -> None:
        excluded_routes = (
            "review/2026-07-11/internal-article",
            "vi/review/2026-07-11/internal-article",
            "draft/internal-article",
            "vi/drafts/internal-article",
            "dashboard/editorial",
            "reports/publish-gate",
        )
        for route in excluded_routes:
            target = self.docs / route
            target.mkdir(parents=True)
            (target / "index.html").write_text(page_html(f"{BASE_URL}/{route}/"), encoding="utf-8")

        generate_sitemap(self.docs, BASE_URL, preserve_existing_lastmod=False)
        sitemap_text = self.sitemap.read_text(encoding="utf-8")

        self.assertIn(self.url, sitemap_text)
        for route in excluded_routes:
            self.assertNotIn(f"{BASE_URL}/{route}/", sitemap_text)

    def test_sitemap_generation_rejects_local_or_file_base_urls(self) -> None:
        for base_url in ("http://localhost:8765", "http://127.0.0.1:8765", "file:///tmp/site"):
            with self.subTest(base_url=base_url):
                with self.assertRaises(ValueError):
                    generate_sitemap(self.docs, base_url, preserve_existing_lastmod=False)

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
        self.assertIn(result.status, {"dry_run", "skipped_credentials_missing"})
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
        self.assertIn(result.status, {"dry_run", "skipped_credentials_missing"})
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
