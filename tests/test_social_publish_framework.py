from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from modules.social.pinterest import PinterestPublisher
from modules.social.publisher_manager import SocialPublisherManager
from modules.social.publish_status import SocialPublishStatusStore
from modules.social.utils import PublishedArticle


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
        self.assertEqual(result.status, "prepared_browser_hook")
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


if __name__ == "__main__":
    unittest.main()
