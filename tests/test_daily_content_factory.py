from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from modules.content_writer import generate_article_markdown, generate_article_package
from modules.ctr_title_engine import generate_title_variants
from modules.daily_content_factory import build_internal_link_insertions, build_today_selected_topics
from modules.video_package_generator import REQUIRED_VIDEO_PACKAGE_FILES, generate_video_package
from modules.website_publisher import publish_article


class DailyContentFactoryTests(unittest.TestCase):
    def test_selected_topics_limit_and_unique_slugs(self) -> None:
        priority_rows = [
            {
                "topic": f"Tool {index} Review 2026",
                "slug": f"tool-{index}-review-2026",
                "article_exists": "NO",
                "recommended_action": "CREATE",
                "final_score": 90 - index,
                "youtube_score": 70,
            }
            for index in range(12)
        ]
        priority_rows.append(priority_rows[0].copy())
        selected = build_today_selected_topics(limit=10, priority_rows=priority_rows)
        slugs = [row["slug"] for row in selected]
        self.assertLessEqual(len(selected), 10)
        self.assertEqual(len(slugs), len(set(slugs)))

    def test_existing_topic_is_not_write_now(self) -> None:
        priority_rows = [
            {
                "topic": "Existing Tool Review 2026",
                "slug": "existing-tool-review-2026",
                "article_exists": "YES",
                "final_score": 80,
                "youtube_score": 50,
            }
        ]
        selected = build_today_selected_topics(limit=10, priority_rows=priority_rows)
        self.assertEqual(selected[0]["decision"], "REFRESH_EXISTING")

    def test_article_draft_has_required_sections(self) -> None:
        markdown = generate_article_markdown({"topic": "Example AI Tool Review 2026", "slug": "example-ai-tool-review-2026"})
        for heading in (
            "## Watch the video review",
            "## Pros",
            "## Cons",
            "## Pricing Notes",
            "## Alternatives",
            "## FAQ",
            "## Final Verdict",
        ):
            self.assertIn(heading, markdown)

    def test_article_package_writes_markdown_and_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            package = generate_article_package(
                {"topic": "Package Tool Review 2026", "slug": "package-tool-review-2026"},
                output_dir=Path(temp_dir),
            )
            self.assertTrue(Path(package["markdown_path"]).exists())
            self.assertTrue(Path(package["json_path"]).exists())

    def test_title_engine_returns_five_variants(self) -> None:
        rows = generate_title_variants("Example AI Tool Review 2026", "example-ai-tool-review-2026")
        self.assertEqual(len(rows), 5)
        self.assertEqual({row["variant_type"] for row in rows}, {"seo_safe", "curiosity", "comparison", "buyer_intent", "youtube"})

    def test_internal_link_plan_has_no_self_link(self) -> None:
        selected = [{"topic": "Surfer SEO Review 2026", "slug": "surfer-seo-review-2026", "article_url": "https://smileaireviewhub.com/surfer-seo-review-2026/"}]
        rows = build_internal_link_insertions(selected, max_links=5)
        self.assertTrue(all(row["source_slug"] != row["target_slug"] for row in rows))

    def test_video_package_has_required_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            report = generate_video_package(
                {"topic": "Video Tool Review 2026", "slug": "video-tool-review-2026"},
                output_root=Path(temp_dir),
            )
            folder = Path(report["video_folder"])
            for filename in REQUIRED_VIDEO_PACKAGE_FILES:
                self.assertTrue((folder / filename).exists(), filename)

    def test_website_publisher_creates_preview(self) -> None:
        report = publish_article({"topic": "Preview Tool Review 2026", "slug": "preview-tool-review-2026", "decision": "WRITE_NOW"}, publish=False)
        self.assertEqual(report["status"], "preview")
        self.assertTrue(Path(report["output_path"]).exists())


if __name__ == "__main__":
    unittest.main()
