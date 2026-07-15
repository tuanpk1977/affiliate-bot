from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from modules.social.pinterest import PinterestPublisher
from modules.social.publisher_manager import SocialPublisherManager
from modules.social.publish_status import SocialPublishStatusStore
from modules.social.manual_actions import platform_target_url
from modules.social.utils import PublishedArticle, load_simple_yaml


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


class SocialPublishFrameworkTests(unittest.TestCase):
    def test_status_store_creates_csv_and_prevents_duplicate_publish_flags(self) -> None:
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "data" / "social_publish_status.csv"
            store = SocialPublishStatusStore(path)
            article = PublishedArticle(
                article_id="one",
                title="One",
                url="https://smileaireviewhub.com/one/",
                description="Desc",
                image="",
                tags=[],
                publish_date="",
            )

            first = store.ensure_article(article)
            second = store.ensure_article(article)
            store.mark_result(article, "pinterest", success=True)
            summary = store.summary(article)

            self.assertEqual(first["article_id"], second["article_id"])
            self.assertTrue(path.exists())
            self.assertEqual(len(store.load()), 1)
            self.assertEqual(summary["row"]["website"], "TRUE")
            self.assertEqual(summary["row"]["pinterest"], "TRUE")
            self.assertEqual(summary["row"]["pinterest_status"], "PUBLISHED_MANUAL")
            self.assertNotIn("pinterest", store.unpublished_platforms(article, ["pinterest", "linkedin"]))

    def test_pinterest_preview_maps_board_from_article_topic(self) -> None:
        article = PublishedArticle(
            article_id="cursor-ai-review",
            title="Cursor AI Review 2026",
            url="https://smileaireviewhub.com/cursor-ai-review/",
            description="A buyer guide for AI coding teams.",
            image="https://example.com/image.png",
            tags=["AI Coding"],
            publish_date="",
        )
        publisher = PinterestPublisher({"enabled": True, "mode": "browser_hook"})

        preview = publisher.preview(article)
        result = publisher.publish(article)

        self.assertEqual(preview["board"], "AI Coding")
        self.assertEqual(preview["canonical_url"], article.url)
        self.assertEqual(result.status, "prepared_manual")
        self.assertFalse(result.success)

    def test_manager_loads_latest_live_article_from_production_docs(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_json(
                root / "data" / "publish_queue.json",
                [
                    {"slug": "old", "status": "blocked", "url": "https://smileaireviewhub.com/old/"},
                    {
                        "slug": "new-live",
                        "status": "live",
                        "url": "https://smileaireviewhub.com/new-live/",
                        "live_at": "2026-07-15T00:00:00+00:00",
                    },
                ],
            )
            html_path = root / "docs" / "new-live" / "index.html"
            html_path.parent.mkdir(parents=True, exist_ok=True)
            html_path.write_text(
                """<!doctype html><html><head>
<title>New Live Article</title>
<meta name="description" content="Independent AI automation review.">
<meta property="og:image" content="/assets/new-live.png">
</head><body></body></html>""",
                encoding="utf-8",
            )

            manager = SocialPublisherManager(root=root, config_path=root / "config" / "social_publish.yaml")
            article = manager.latest_article()
            status = manager.website_status()
            preview = manager.preview("pinterest")

            self.assertEqual(article.article_id, "new-live")
            self.assertEqual(article.title, "New Live Article")
            self.assertEqual(article.image, "https://smileaireviewhub.com/assets/new-live.png")
            self.assertEqual(status["unpublished_social_posts"], 11)
            self.assertIn("pinterest", status["enabled_platforms"])
            self.assertEqual(preview["url"], "https://smileaireviewhub.com/new-live/")

    def test_manager_skips_already_published_platform(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_json(root / "data" / "publish_queue.json", [{"slug": "one", "status": "live", "url": "https://smileaireviewhub.com/one/"}])
            (root / "docs" / "one").mkdir(parents=True, exist_ok=True)
            (root / "docs" / "one" / "index.html").write_text("<title>One</title><meta name='description' content='AI review.'>", encoding="utf-8")
            manager = SocialPublisherManager(root=root, config_path=root / "config" / "social_publish.yaml")
            article = manager.latest_article()
            manager.status.ensure_article(article)
            manager.status.mark_result(article, "pinterest", success=True)

            result = manager.publish_platform("pinterest")

            self.assertEqual(result.status, "skipped_already_published")
            self.assertTrue(result.success)

    def test_manual_prepare_does_not_mark_platform_published_until_confirmed(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_json(root / "data" / "publish_queue.json", [{"slug": "one", "status": "live", "url": "https://smileaireviewhub.com/one/"}])
            (root / "docs" / "one").mkdir(parents=True, exist_ok=True)
            (root / "docs" / "one" / "index.html").write_text("<title>One</title><meta name='description' content='AI review.'>", encoding="utf-8")
            manager = SocialPublisherManager(root=root, config_path=root / "config" / "social_publish.yaml")
            article = manager.latest_article()

            preview = manager.preview_platform("pinterest", article=article)
            prepared = manager.prepare_platform("pinterest", article=article)
            pending = manager.status.summary(article)["row"]
            confirmed = manager.confirm_manual_publish(
                "pinterest",
                article=article,
                published_url="https://www.pinterest.com/pin/123/",
                notes="manual test",
            )
            published = manager.status.summary(article)["row"]

            self.assertEqual(preview["canonical_url"], article.url)
            self.assertEqual(prepared.status, "prepared_manual")
            self.assertFalse(prepared.success)
            self.assertEqual(pending["pinterest"], "FALSE")
            self.assertEqual(pending["pinterest_status"], "PENDING")
            self.assertEqual(confirmed.status, "PUBLISHED_MANUAL")
            self.assertEqual(published["pinterest"], "TRUE")
            self.assertEqual(published["pinterest_status"], "PUBLISHED_MANUAL")
            self.assertEqual(published["published_url"], "https://www.pinterest.com/pin/123/")

    def test_manual_social_config_has_no_api_or_oauth_secret_fields(self) -> None:
        config_text = json.dumps(load_simple_yaml(Path("config/social_publish.yaml")), sort_keys=True).lower()
        for forbidden in ("api_key", "oauth", "token", "password", "secret"):
            self.assertNotIn(forbidden, config_text)
        self.assertIn("manual_assisted", config_text)

    def test_clipboard_fallback_writes_utf8_text_with_website_url(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_json(root / "data" / "publish_queue.json", [{"slug": "one", "status": "live", "url": "https://smileaireviewhub.com/one/"}])
            html_path = root / "docs" / "one" / "index.html"
            html_path.parent.mkdir(parents=True, exist_ok=True)
            html_path.write_text(
                "<title>One</title><meta name='description' content='AI review for teams.'><h2>Pricing fit</h2>",
                encoding="utf-8",
            )
            manager = SocialPublisherManager(root=root, config_path=root / "config" / "social_publish.yaml")
            article = manager.latest_article()

            result = manager.copy_prepared_content("pinterest", article=article, field="all", use_clipboard=False)

            self.assertFalse(result.copied_to_clipboard)
            self.assertTrue(result.file_path.exists())
            saved = result.file_path.read_text(encoding="utf-8")
            self.assertIn("https://smileaireviewhub.com/one/", saved)
            self.assertIn("Platform: pinterest", saved)

    def test_platform_content_contains_url_and_long_form_is_excerpt(self) -> None:
        long_summary = " ".join(f"word{i}" for i in range(500))
        article = PublishedArticle(
            article_id="long",
            title="Long AI Review",
            url="https://smileaireviewhub.com/long/",
            description="Short description",
            image="https://smileaireviewhub.com/image.webp",
            tags=["AI Tools"],
            publish_date="",
            summary=long_summary,
            headings=["Pricing", "Alternatives", "Workflow"],
        )
        manager = SocialPublisherManager(root=Path("."), config_path=Path("config/social_publish.yaml"))
        linkedin = manager.publishers["linkedin"].preview(article)
        medium = manager.publishers["medium"].preview(article)

        self.assertIn(article.url, linkedin["post_text"])
        self.assertIn(article.url, medium["post_text"])
        self.assertLess(len(str(medium["post_text"]).split()), len(long_summary.split()))
        self.assertIn("Canonical URL for republishing", medium["post_text"])

    def test_share_target_urls_are_public_platform_urls(self) -> None:
        payload = {
            "platform": "linkedin",
            "title": "One",
            "description": "Desc",
            "url": "https://smileaireviewhub.com/one/",
            "image_url": "https://smileaireviewhub.com/one.webp",
        }

        self.assertIn("linkedin.com", platform_target_url("linkedin", payload))
        self.assertIn("facebook.com", platform_target_url("facebook", payload))
        self.assertIn("pinterest.com", platform_target_url("pinterest", payload))

    def test_manager_lists_live_articles_with_social_counts(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_json(
                root / "data" / "publish_queue.json",
                [
                    {"slug": "blocked", "status": "blocked", "url": "https://smileaireviewhub.com/blocked/"},
                    {"slug": "not-live", "status": "published", "url": "https://smileaireviewhub.com/not-live/", "live_status": "404"},
                    {"slug": "one", "status": "live", "url": "https://smileaireviewhub.com/one/", "live_at": "2026-07-15T02:00:00+00:00"},
                    {"slug": "two", "status": "published", "url": "https://smileaireviewhub.com/two/", "live_at": "2026-07-15T03:00:00+00:00"},
                ],
            )
            for slug in ("one", "two"):
                path = root / "docs" / slug / "index.html"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(f"<title>{slug}</title><meta name='description' content='AI review.'>", encoding="utf-8")
            manager = SocialPublisherManager(root=root, config_path=root / "config" / "social_publish.yaml")

            listed = manager.list_articles()

            self.assertEqual([item["article"].article_id for item in listed], ["two", "one"])
            self.assertEqual(listed[0]["website"], "LIVE")
            self.assertEqual(listed[0]["published_social"], 0)
            self.assertEqual(listed[0]["total_social"], 11)
            self.assertEqual(listed[0]["published_platforms"], [])
            self.assertIn("pinterest", listed[0]["remaining_platforms"])


if __name__ == "__main__":
    unittest.main()
