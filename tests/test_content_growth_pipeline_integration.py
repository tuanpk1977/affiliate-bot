from __future__ import annotations

from contextlib import ExitStack
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

from modules import content_growth_pipeline as pipeline


class ContentGrowthPipelineIntegrationTests(unittest.TestCase):
    def test_run_daily_content_growth_attaches_planning_and_publishes_locally(self) -> None:
        topic = {
            "topic": "best ai coding assistants for teams",
            "slug": "best-ai-coding-assistants-for-teams",
            "content_type": "comparison",
            "search_intent": "commercial",
            "total_score": 91,
            "related_keywords": [
                "ai coding tools for teams",
                "cursor for teams",
                "copilot for developers",
            ],
            "suggested_internal_links": [
                "/comparisons/cursor-vs-windsurf/",
                "/category/ai-coding-tools/",
            ],
        }

        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            data_dir = root / "data"
            site_output = root / "site_output"
            published_dir = data_dir / "published_static_pages"
            video_output = root / "video_output"
            social_drafts = root / "social_drafts"
            report_dir = data_dir / "content_growth_reports"
            tracking_csv = data_dir / "content_growth_performance_log.csv"
            trending_json = data_dir / "trending_topics.json"

            with ExitStack() as stack:
                stack.enter_context(patch.object(pipeline, "ROOT", root))
                stack.enter_context(patch.object(pipeline, "DATA_DIR", data_dir))
                stack.enter_context(patch.object(pipeline, "SITE_OUTPUT", site_output))
                stack.enter_context(patch.object(pipeline, "PUBLISHED_DIR", published_dir))
                stack.enter_context(patch.object(pipeline, "VIDEO_OUTPUT", video_output))
                stack.enter_context(patch.object(pipeline, "SOCIAL_DRAFTS", social_drafts))
                stack.enter_context(patch.object(pipeline, "REPORT_DIR", report_dir))
                stack.enter_context(patch.object(pipeline, "TRACKING_CSV", tracking_csv))
                stack.enter_context(patch.object(pipeline, "TRENDING_JSON", trending_json))
                stack.enter_context(patch.object(pipeline, "_CONTENT_PLANNER", None))
                stack.enter_context(patch.object(pipeline, "load_or_discover_topics", return_value=[topic]))

                report = pipeline.run_daily_content_growth(
                    limit=1,
                    discover=False,
                    build=False,
                    submit_indexnow_enabled=False,
                    dry_run=False,
                )

            self.assertEqual(len(report["generated_pages"]), 1)
            self.assertTrue(report["build"]["skipped"])
            self.assertTrue(report["indexnow"]["skipped"])

            page = report["generated_pages"][0]
            planning = page["planning"]
            article_file = Path(page["article_file"])
            site_file = site_output / topic["slug"] / "index.html"
            social_folder = Path(page["social_folder"])
            video_folder = Path(page["video_folder"])

            self.assertEqual(planning["keyword"], topic["topic"])
            self.assertEqual(planning["intent"], "commercial")
            self.assertIn("coverage_score", planning)
            self.assertTrue(planning["outline_sections"])
            self.assertTrue(planning["reasoning"])
            self.assertEqual(planning["related_keywords"], topic["related_keywords"])

            self.assertTrue(article_file.exists())
            self.assertTrue(site_file.exists())
            self.assertTrue(video_folder.exists())
            self.assertTrue(social_folder.exists())
            self.assertTrue(tracking_csv.exists())

            article_html = article_file.read_text(encoding="utf-8")
            self.assertIn("<title>best ai coding assistants for teams 2026</title>", article_html.lower())
            self.assertIn('<meta name="description"', article_html)
            self.assertIn("Content planning snapshot", article_html)
            self.assertIn("Planned outline sections", article_html)
            self.assertIn("Planning reasoning", article_html)
            self.assertIn("Coverage score", article_html)
            self.assertIn("Related keywords", article_html)
            self.assertIn("Quick verdict", article_html)


if __name__ == "__main__":
    unittest.main()
