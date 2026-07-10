from __future__ import annotations

from contextlib import ExitStack
import json
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
            "topic": "how to onboard ai coding assistants for teams",
            "slug": "best-ai-coding-assistants-for-teams",
            "content_type": "tutorial",
            "search_intent": "informational",
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
                            "manual_approval_article_types": ["pricing", "comparison", "review", "product_recommendation"],
                            "manual_approval_title_markers": [],
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
                                "manual_approval_article_types": ["pricing", "comparison", "review", "product_recommendation"],
                                "manual_approval_title_markers": [],
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
            self.assertEqual(planning["intent"], "informational")
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
            self.assertIn("<title>how to onboard ai coding assistants for teams 2026</title>", article_html.lower())
            self.assertIn('<meta name="description"', article_html)
            self.assertIn("Quick verdict", article_html)
            self.assertIn('/assets/article.css', article_html)
            self.assertIn('class="site-header"', article_html)
            self.assertIn('class="site-nav"', article_html)
            self.assertIn('class="article-layout"', article_html)
            self.assertIn('class="article-container"', article_html)
            self.assertIn("breadcrumbs", article_html)
            self.assertIn("Comparison table", article_html)
            self.assertIn('class="table-wrapper"', article_html)
            self.assertIn('class="article-table"', article_html)
            self.assertIn("Pros and cons", article_html)
            self.assertIn("Pricing section", article_html)
            self.assertIn("Alternatives", article_html)
            self.assertIn('class="related-card"', article_html)
            self.assertIn("FAQ", article_html)
            self.assertIn('class="faq-list"', article_html)
            self.assertIn("Sources checked", article_html)
            self.assertIn('class="source-list"', article_html)
            self.assertIn("Our Community Signals", article_html)
            self.assertIn('class="community-signals-grid"', article_html)
            self.assertIn("Metrics reflect public content activity", article_html)
            self.assertIn('class="site-footer"', article_html)
            self.assertIn("footer-grid", article_html)
            self.assertIn('href="/editorial-policy/"', article_html)
            self.assertIn('href="/privacy-policy/"', article_html)
            self.assertNotIn("Affiliate DisclosurePrivacy PolicyAbout", article_html)
            self.assertIn("Visit official website", article_html)
            self.assertIn('class="cta-button"', article_html)
            self.assertNotIn("Research package snapshot", article_html)
            self.assertNotIn("Content planning snapshot", article_html)
            self.assertNotIn("Affiliate placeholder fields", article_html)
            self.assertNotIn("{{", article_html)
            self.assertNotIn("needs_human_review", article_html)

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

    def test_generate_production_article_draft_from_package_stops_at_human_approval(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            data_dir = root / "data"
            site_output = root / "site_output"
            social_drafts = root / "social_drafts"
            slug = "best-ai-productivity-software"
            package_dir = data_dir / "research" / slug
            package_dir.mkdir(parents=True, exist_ok=True)
            for href in ("reviews", "comparisons", "categories", "best-website-builder-2026", "review/surfer-seo"):
                target = site_output / href / "index.html"
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("<html></html>", encoding="utf-8")
            package_dir.joinpath("package.json").write_text(
                """
{
  "keyword": "best ai productivity software",
  "slug": "best-ai-productivity-software",
  "generated_at": "2026-07-07T00:00:00+00:00",
  "package_dir": "TEMP_PACKAGE_DIR",
  "keyword_intelligence": {
    "primary_keyword": "best ai productivity software",
    "semantic_keywords": ["best ai productivity software pricing", "best ai productivity software comparison"],
    "search_intent": "commercial",
    "cluster": {
      "seed_topic": "best ai productivity software",
      "supporting_topics": ["best ai productivity software pricing", "best ai productivity software comparison"],
      "supporting_article_ideas": ["Comparison article", "Pricing article"]
    }
  },
  "keyword_summary": {
    "keyword": "best ai productivity software",
    "slug": "best-ai-productivity-software",
    "primary_keyword": "best ai productivity software",
    "intent": "commercial",
    "article_type": "best list",
    "cluster_seed": "best ai productivity software"
  },
  "outline": {
    "seo_outline": ["Quick verdict", "Comparison", "Pros and cons", "Pricing", "FAQ"],
    "faq_placement": "After alternatives and before final CTA",
    "cta_placement": "Hero CTA and final verdict CTA",
    "recommended_cta": "Review the comparison and shortlist the best option for your workflow.",
    "confidence": 0.8,
    "reasoning": ["Fixture outline reasoning"]
  },
  "faq": {
    "beginner": ["What is best ai productivity software and who is it for?"],
    "comparison": ["How does best ai productivity software compare with alternatives?"],
    "pricing": ["What should readers verify on the pricing page?"]
  },
  "entities": {
    "products": ["Notion", "Gamma", "Notion AI"],
    "companies": ["Notion", "Gamma", "Notion AI"],
    "entity_coverage_score": 60,
    "missing_entity_types": ["competitors"]
  },
  "competitors": {
    "keyword": "best ai productivity software",
    "coverage_status": "missing",
    "profiles": [],
    "report": "competitor coverage is missing"
  },
  "sources": {
    "verified_sources": [
      {
        "brand": "Notion",
        "slug": "notion",
        "source_type": "official_docs",
        "source_name": "Notion Help Center",
        "source_url": "https://www.notion.com/help",
        "verification_status": "verified",
        "verification_date": "2026-07-07T00:00:00+00:00",
        "trust_score": 100,
        "freshness_score": 100,
        "confidence": 94
      }
    ],
    "official_docs_score": 100,
    "pricing_source_score": 100,
    "affiliate_source_score": 98,
    "changelog_source_score": 98,
    "competitor_source_score": 0,
    "total_verified_source_score": 79,
    "source_confidence": 91.6,
    "source_status": "verified"
  },
  "writing_plan": {
    "recommended_word_count": 2370,
    "affiliate_value": 64,
    "seo_opportunity": 85,
    "commercial_intent": 90,
    "article_type": "best list",
    "intent": "commercial"
  },
  "quality": {
    "overall_score": 62.36,
    "coverage": 72,
    "entity_coverage": 60,
    "entity_coverage_score": 60,
    "faq_coverage": 68,
    "outline_quality": 80,
    "affiliate_readiness": 57,
    "source_quality": 89.5,
    "official_docs_score": 100,
    "pricing_source_score": 100,
    "affiliate_source_score": 98,
    "changelog_source_score": 98,
    "competitor_source_score": 0,
    "total_verified_source_score": 79,
    "source_confidence": 91.6,
    "source_status": "verified",
    "missing_information": ["competitor coverage is limited"],
    "status": "ready"
  },
  "cache_hits": ["Notion", "Gamma", "Notion AI"]
}
                """.replace("TEMP_PACKAGE_DIR", str(package_dir).replace("\\", "\\\\")),
                encoding="utf-8",
            )
            with ExitStack() as stack:
                stack.enter_context(patch.object(pipeline, "DATA_DIR", data_dir))
                stack.enter_context(patch.object(pipeline, "SITE_OUTPUT", site_output))
                stack.enter_context(patch.object(pipeline, "PRODUCTION_DRAFTS", data_dir / "production_article_drafts"))
                stack.enter_context(patch.object(pipeline, "VIDEO_OUTPUT", root / "video_output"))
                stack.enter_context(patch.object(pipeline, "SOCIAL_DRAFTS", root / "social_drafts"))
                stack.enter_context(patch.object(pipeline, "REPORT_DIR", data_dir / "content_growth_reports"))
                stack.enter_context(patch.object(pipeline, "_RESEARCH_PLATFORM", None))
                stack.enter_context(patch.object(pipeline, "_CONTENT_REVIEW_ENGINE", None))
                stack.enter_context(patch.object(pipeline, "_HUMAN_APPROVAL_WORKFLOW", None))
                stack.enter_context(patch.object(pipeline, "_PUBLISH_GATE", None))
                (data_dir / "offers.csv").write_text("offer_id,brand_name,website,affiliate_url,niche,commission_type,commission_rate,flat_commission,cookie_days,recurring,traffic_policy,direct_linking_allowed,brand_bidding_allowed,vendor_trust,buyer_intent,notes\n", encoding="utf-8")
                (data_dir / "affiliate_links.csv").write_text("tool_slug,tool_name,brand,slug,official_url,affiliate_url,affiliate_status,status,notes,commission_note,network,approved\n", encoding="utf-8")
                stack.enter_context(
                    patch.object(
                        pipeline,
                        "get_research_platform",
                        return_value=ResearchIntelligencePlatform(
                            data_dir=data_dir,
                            site_output_dir=site_output,
                            offers_file=data_dir / "offers.csv",
                            affiliate_links_file=data_dir / "affiliate_links.csv",
                            config={
                                "research_intelligence": {
                                    "quality_gate": {"threshold": 60, "enabled": True, "allow_override": False},
                                    "verified_source_gate": {
                                        "enabled": True,
                                        "minimum_official_docs_score": 20,
                                        "minimum_pricing_source_score": 20,
                                        "minimum_affiliate_source_score": 10,
                                        "minimum_total_score": 35,
                                    },
                                },
                                "knowledge_review": {
                                    "minimum_verified_sources": 1,
                                    "minimum_official_sources": 1,
                                    "minimum_trust_score": 50,
                                    "minimum_freshness": 35,
                                },
                            },
                        ),
                    )
                )
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
                                "manual_approval_article_types": ["pricing", "comparison", "review", "product_recommendation"],
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
                                "minimum_verified_source_score": 35,
                                "minimum_knowledge_freshness": 20,
                                "minimum_business_score": 35,
                                "minimum_readability_score": 30,
                                "require_human_approval": False,
                            },
                        ),
                    )
                )

                result = pipeline.generate_production_article_draft_from_package(slug)

            self.assertEqual(result["page"]["review"]["status"], "needs_human_review")
            self.assertEqual(result["page"]["human_approval"]["status"], "needs_human_review")
            self.assertEqual(result["page"]["publish_gate"]["status"], "needs_human_review")
            self.assertIn("human approval missing", result["page"]["publish_gate"]["pending_reviews"])
            self.assertTrue((data_dir / "production_article_drafts" / slug / "article.md").exists())
            self.assertTrue((data_dir / "production_article_drafts" / slug / "index.html").exists())
            metadata = json.loads((data_dir / "production_article_drafts" / slug / "metadata.json").read_text(encoding="utf-8"))
            self.assertIn("editorial", metadata)
            self.assertEqual(metadata["editorial"]["author_name"], "Nguyen Quoc Tuan")
            self.assertTrue(str(metadata.get("social_folder", "")).endswith(slug))
            article_html = (data_dir / "production_article_drafts" / slug / "index.html").read_text(encoding="utf-8")
            self.assertIn("Author and editorial review", article_html)
            self.assertTrue((social_drafts / "2026-07-07" / slug / "devto.md").exists())
            self.assertTrue((social_drafts / "2026-07-07" / slug / "product-hunt.md").exists())

    def test_community_signals_can_be_omitted_without_configured_values(self) -> None:
        with patch.object(pipeline, "load_site_stats", return_value={"communityChannels": []}):
            self.assertEqual(pipeline.render_community_signals(), "")

    def test_community_signals_render_configured_public_channels_only(self) -> None:
        stats = {
            "communityChannels": [
                {"name": "LinkedIn", "label": "Public", "url": "https://linkedin.example/profile"},
                {"name": "Private", "label": "Internal", "url": "https://internal.example"},
                {"name": "X", "label": "Active", "url": ""},
            ]
        }
        with patch.object(pipeline, "load_site_stats", return_value=stats):
            html_text = pipeline.render_community_signals()

        self.assertIn("Our Community Signals", html_text)
        self.assertIn("LinkedIn", html_text)
        self.assertIn("Public", html_text)
        self.assertNotIn("Private", html_text)
        self.assertIn("Metrics reflect public content activity", html_text)

    def test_footer_includes_required_links_without_concatenation(self) -> None:
        html_text = pipeline.render_site_footer()

        for href in (
            "/about/",
            "/editorial-policy/",
            "/affiliate-disclosure/",
            "/privacy-policy/",
            "/contact/",
            "/reviews/",
            "/comparisons/",
            "/pricing/",
            "/categories/",
        ):
            self.assertIn(f'href="{href}"', html_text)
        self.assertIn("footer-social-links", html_text)
        self.assertNotIn("Affiliate DisclosurePrivacy PolicyAbout", html_text)

    def test_broken_hero_image_is_not_rendered(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            with patch.object(pipeline, "ROOT", root), patch.object(pipeline, "SITE_OUTPUT", root / "site_output"):
                self.assertEqual(pipeline.render_article_hero_image("missing", "Missing Hero"), "")

    def test_valid_hero_image_renders_dimensions_and_decoding(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            image = root / "site_output" / "assets" / "og" / "pages" / "valid.png"
            image.parent.mkdir(parents=True, exist_ok=True)
            image.write_bytes(b"png")
            with patch.object(pipeline, "ROOT", root), patch.object(pipeline, "SITE_OUTPUT", root / "site_output"):
                html_text = pipeline.render_article_hero_image("valid", "Valid Hero")

        self.assertIn('src="/assets/og/pages/valid.png"', html_text)
        self.assertIn('width="1200"', html_text)
        self.assertIn('height="630"', html_text)
        self.assertIn('decoding="async"', html_text)


if __name__ == "__main__":
    unittest.main()
