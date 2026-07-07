from __future__ import annotations

from contextlib import ExitStack
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

from modules import content_growth_pipeline as pipeline
from modules.content_review import ContentReviewEngine
from modules.human_approval import HumanApprovalWorkflow
from modules.publish_gate import PublishGate
from modules.research_intelligence import ResearchIntelligencePlatform


class ContentGrowthPipelineIntegrationTests(unittest.TestCase):
    def test_resolve_internal_links_excludes_missing_targets(self) -> None:
        with TemporaryDirectory() as temp_dir:
            site_output = Path(temp_dir) / "site_output"
            existing = site_output / "reviews" / "index.html"
            existing.parent.mkdir(parents=True, exist_ok=True)
            existing.write_text("<html></html>", encoding="utf-8")

            with patch.object(pipeline, "SITE_OUTPUT", site_output):
                links = pipeline.resolve_internal_links(
                    {
                        "suggested_internal_links": [
                            "/reviews/",
                            "/missing-page/",
                        ]
                    }
                )

        self.assertIn(("/reviews/", "Reviews"), links)
        self.assertNotIn(("/missing-page/", "Missing Page"), links)

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
                stack.enter_context(patch.object(pipeline, "_RESEARCH_PLATFORM", None))
                stack.enter_context(patch.object(pipeline, "_CONTENT_REVIEW_ENGINE", None))
                stack.enter_context(patch.object(pipeline, "_HUMAN_APPROVAL_WORKFLOW", None))
                stack.enter_context(patch.object(pipeline, "_PUBLISH_GATE", None))
                stack.enter_context(patch.object(pipeline, "load_or_discover_topics", return_value=[topic]))
                research_platform = ResearchIntelligencePlatform(
                    data_dir=data_dir,
                    site_output_dir=site_output,
                    offers_file=data_dir / "offers.csv",
                    affiliate_links_file=data_dir / "affiliate_links.csv",
                    config={
                        "research_intelligence": {
                            "quality_gate": {"threshold": 0, "enabled": True, "allow_override": False},
                            "verified_source_gate": {"enabled": False},
                        },
                        "content_review": {
                            "minimum_word_count": 50,
                            "minimum_publish_readiness": 50,
                            "minimum_source_quality": 0,
                            "minimum_factual_quality": 0,
                            "minimum_seo_quality": 0,
                            "minimum_business_value": 0,
                            "minimum_readability_score": 0,
                        },
                    },
                )
                stack.enter_context(patch.object(pipeline, "get_research_platform", return_value=research_platform))
                stack.enter_context(
                    patch.object(
                        pipeline,
                        "get_content_review_engine",
                        return_value=ContentReviewEngine(
                            data_dir=data_dir,
                            config={
                                "minimum_word_count": 50,
                                "minimum_publish_readiness": 50,
                                "minimum_source_quality": 0,
                                "minimum_factual_quality": 0,
                                "minimum_seo_quality": 0,
                                "minimum_business_value": 0,
                                "minimum_readability_score": 0,
                            },
                        ),
                    )
                )
                stack.enter_context(
                    patch.object(
                        pipeline,
                        "get_human_approval_workflow",
                        return_value=HumanApprovalWorkflow(data_dir=data_dir, config={"required": False}),
                    )
                )
                stack.enter_context(
                    patch.object(
                        pipeline,
                        "get_publish_gate",
                        return_value=PublishGate(
                            data_dir=data_dir,
                            site_output_dir=site_output,
                            config={
                                "enabled": True,
                                "minimum_verified_source_score": 0,
                                "minimum_knowledge_freshness": 0,
                                "minimum_business_score": 0,
                                "minimum_readability_score": 0,
                                "require_human_approval": False,
                            },
                        ),
                    )
                )

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
            research = page["research"]
            planning = page["planning"]
            article_file = Path(page["article_file"])
            site_file = site_output / topic["slug"] / "index.html"
            social_folder = Path(page["social_folder"])
            video_folder = Path(page["video_folder"])

            self.assertEqual(research["keyword"], topic["topic"])
            self.assertTrue(Path(research["package_dir"]).exists())
            self.assertTrue(research["keyword_intelligence"]["primary_keyword"])
            self.assertTrue(research["outline"]["heading_hierarchy"])
            self.assertIn("overall_score", research["quality"])
            self.assertIn("source_status", research["quality"])

            self.assertEqual(planning["keyword"], topic["topic"])
            self.assertEqual(planning["intent"], "commercial")
            self.assertIn("coverage_score", planning)
            self.assertTrue(planning["outline_sections"])
            self.assertTrue(planning["reasoning"])
            self.assertEqual(planning["related_keywords"], topic["related_keywords"])
            self.assertIn("review", page)
            self.assertIn("human_approval", page)
            self.assertIn("publish_gate", page)
            self.assertEqual(page["review"]["status"], "ai_review_passed")
            self.assertEqual(page["human_approval"]["status"], "human_approved")
            self.assertEqual(page["publish_gate"]["status"], "published_local")

            self.assertTrue(article_file.exists())
            self.assertTrue(site_file.exists())
            self.assertTrue(video_folder.exists())
            self.assertTrue(social_folder.exists())
            self.assertTrue(tracking_csv.exists())
            self.assertEqual(article_file.parent.parent, published_dir)
            self.assertEqual(site_file.parent.parent, site_output)

            article_html = article_file.read_text(encoding="utf-8")
            self.assertIn("<title>best ai coding assistants for teams 2026</title>", article_html.lower())
            self.assertIn('<meta name="description"', article_html)
            self.assertIn("Research package snapshot", article_html)
            self.assertIn("Research quality score", article_html)
            self.assertIn("Content planning snapshot", article_html)
            self.assertIn("Planned outline sections", article_html)
            self.assertIn("Planning reasoning", article_html)
            self.assertIn("Coverage score", article_html)
            self.assertIn("Related keywords", article_html)
            self.assertIn("Quick verdict", article_html)

            research_dir = Path(research["package_dir"])
            self.assertTrue((research_dir / "keyword.json").exists())
            self.assertTrue((research_dir / "outline.json").exists())
            self.assertTrue((research_dir / "faq.json").exists())
            self.assertTrue((research_dir / "entities.json").exists())
            self.assertTrue((research_dir / "sources.json").exists())
            self.assertTrue((data_dir / "research_quality_report.json").exists())
            self.assertTrue((data_dir / "content_review_queue.json").exists())
            self.assertTrue((data_dir / "content_review_report.json").exists())
            self.assertTrue((data_dir / "human_approval_queue.json").exists())
            self.assertTrue((data_dir / "publish_queue.json").exists())
            self.assertTrue((data_dir / "publish_gate_report.json").exists())

    def test_low_quality_research_is_blocked_and_queued(self) -> None:
        topic = {
            "topic": "unknown ai workflow",
            "slug": "unknown-ai-workflow",
            "content_type": "comparison",
            "search_intent": "commercial",
            "total_score": 91,
            "related_keywords": ["unknown ai workflow pricing"],
            "suggested_internal_links": ["/comparisons/cursor-vs-windsurf/"],
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
            with ExitStack() as stack:
                stack.enter_context(patch.object(pipeline, "ROOT", root))
                stack.enter_context(patch.object(pipeline, "DATA_DIR", data_dir))
                stack.enter_context(patch.object(pipeline, "SITE_OUTPUT", site_output))
                stack.enter_context(patch.object(pipeline, "PUBLISHED_DIR", published_dir))
                stack.enter_context(patch.object(pipeline, "VIDEO_OUTPUT", video_output))
                stack.enter_context(patch.object(pipeline, "SOCIAL_DRAFTS", social_drafts))
                stack.enter_context(patch.object(pipeline, "REPORT_DIR", report_dir))
                stack.enter_context(patch.object(pipeline, "TRACKING_CSV", tracking_csv))
                stack.enter_context(patch.object(pipeline, "_CONTENT_PLANNER", None))
                stack.enter_context(patch.object(pipeline, "_RESEARCH_PLATFORM", None))
                stack.enter_context(patch.object(pipeline, "_CONTENT_REVIEW_ENGINE", None))
                stack.enter_context(patch.object(pipeline, "_HUMAN_APPROVAL_WORKFLOW", None))
                stack.enter_context(patch.object(pipeline, "_PUBLISH_GATE", None))
                research_platform = ResearchIntelligencePlatform(
                    data_dir=data_dir,
                    site_output_dir=site_output,
                    offers_file=data_dir / "offers.csv",
                    affiliate_links_file=data_dir / "affiliate_links.csv",
                    config={
                        "research_intelligence": {
                            "quality_gate": {"threshold": 95, "enabled": True, "allow_override": False},
                            "verified_source_gate": {"enabled": False},
                        }
                    },
                )
                stack.enter_context(patch.object(pipeline, "get_research_platform", return_value=research_platform))
                stack.enter_context(
                    patch.object(
                        pipeline,
                        "get_content_review_engine",
                        return_value=ContentReviewEngine(data_dir=data_dir, config={"minimum_word_count": 50}),
                    )
                )
                stack.enter_context(
                    patch.object(
                        pipeline,
                        "get_human_approval_workflow",
                        return_value=HumanApprovalWorkflow(data_dir=data_dir, config={"required": False}),
                    )
                )
                with self.assertRaises(RuntimeError):
                    pipeline.generate_topic_package(topic)

            queue_file = data_dir / "research_enrichment_queue.json"
            self.assertTrue(queue_file.exists())

    def test_publish_gate_blocks_content_before_local_publish(self) -> None:
        topic = {
            "topic": "cursor pricing review",
            "slug": "cursor-pricing-review",
            "content_type": "comparison",
            "search_intent": "commercial",
            "total_score": 91,
            "related_keywords": ["cursor pricing"],
            "suggested_internal_links": [],
        }
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            data_dir = root / "data"
            site_output = root / "site_output"
            published_dir = data_dir / "published_static_pages"
            with ExitStack() as stack:
                stack.enter_context(patch.object(pipeline, "ROOT", root))
                stack.enter_context(patch.object(pipeline, "DATA_DIR", data_dir))
                stack.enter_context(patch.object(pipeline, "SITE_OUTPUT", site_output))
                stack.enter_context(patch.object(pipeline, "PUBLISHED_DIR", published_dir))
                stack.enter_context(patch.object(pipeline, "VIDEO_OUTPUT", root / "video_output"))
                stack.enter_context(patch.object(pipeline, "SOCIAL_DRAFTS", root / "social_drafts"))
                stack.enter_context(patch.object(pipeline, "REPORT_DIR", data_dir / "content_growth_reports"))
                stack.enter_context(patch.object(pipeline, "TRACKING_CSV", data_dir / "content_growth_performance_log.csv"))
                stack.enter_context(patch.object(pipeline, "_CONTENT_PLANNER", None))
                stack.enter_context(patch.object(pipeline, "_RESEARCH_PLATFORM", None))
                stack.enter_context(patch.object(pipeline, "_CONTENT_REVIEW_ENGINE", None))
                stack.enter_context(patch.object(pipeline, "_HUMAN_APPROVAL_WORKFLOW", None))
                stack.enter_context(patch.object(pipeline, "_PUBLISH_GATE", None))
                research_platform = ResearchIntelligencePlatform(
                    data_dir=data_dir,
                    site_output_dir=site_output,
                    offers_file=data_dir / "offers.csv",
                    affiliate_links_file=data_dir / "affiliate_links.csv",
                    config={
                        "research_intelligence": {
                            "quality_gate": {"threshold": 0, "enabled": True, "allow_override": False},
                            "verified_source_gate": {"enabled": False},
                        }
                    },
                )
                stack.enter_context(patch.object(pipeline, "get_research_platform", return_value=research_platform))
                stack.enter_context(
                    patch.object(
                        pipeline,
                        "get_content_review_engine",
                        return_value=ContentReviewEngine(
                            data_dir=data_dir,
                            config={
                                "minimum_word_count": 50,
                                "minimum_publish_readiness": 50,
                                "minimum_source_quality": 0,
                                "minimum_factual_quality": 0,
                                "minimum_seo_quality": 0,
                                "minimum_business_value": 0,
                                "minimum_readability_score": 0,
                                "require_human_approval": True,
                            },
                        ),
                    )
                )
                stack.enter_context(
                    patch.object(
                        pipeline,
                        "get_human_approval_workflow",
                        return_value=HumanApprovalWorkflow(data_dir=data_dir, config={"required": True}),
                    )
                )
                stack.enter_context(
                    patch.object(
                        pipeline,
                        "get_publish_gate",
                        return_value=PublishGate(
                            data_dir=data_dir,
                            site_output_dir=site_output,
                            config={
                                "enabled": True,
                                "minimum_verified_source_score": 0,
                                "minimum_knowledge_freshness": 0,
                                "minimum_business_score": 0,
                                "minimum_readability_score": 0,
                                "require_human_approval": True,
                            },
                        ),
                    )
                )
                with self.assertRaises(RuntimeError):
                    pipeline.generate_topic_package(topic)

            self.assertFalse((published_dir / topic["slug"] / "index.html").exists())
            publish_queue = data_dir / "publish_queue.json"
            self.assertTrue(publish_queue.exists())


if __name__ == "__main__":
    unittest.main()
