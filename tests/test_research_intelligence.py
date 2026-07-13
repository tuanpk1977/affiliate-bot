from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from modules.research_intelligence import ResearchIntelligencePlatform, ResearchPackage


class ResearchIntelligenceTests(unittest.TestCase):
    def _research_package(
        self,
        *,
        score: float = 48,
        entity_score: float = 38,
        competitor_score: float = 10,
        source_confidence: float = 35,
        verified_sources: int = 2,
    ) -> ResearchPackage:
        sources = {
            "verified_sources": [
                {"url": f"https://source{index}.example.com", "source_type": "validated_topic_source", "trust_score": 70, "freshness_score": source_confidence}
                for index in range(verified_sources)
            ],
            "reference_count": verified_sources,
            "total_verified_source_score": 20,
            "official_docs_score": 0,
            "pricing_source_score": 0,
            "affiliate_source_score": 0,
            "source_confidence": source_confidence,
        }
        return ResearchPackage(
            keyword="warning topic",
            slug="warning-topic",
            generated_at="2026-07-13T00:00:00+00:00",
            package_dir="",
            keyword_intelligence={},
            keyword_summary={},
            outline={},
            faq={},
            entities={"entity_coverage_score": entity_score},
            competitors={"coverage_status": "missing"},
            sources=sources,
            writing_plan={},
            quality={
                "overall_score": score,
                "entity_coverage_score": entity_score,
                "competitor_quality": competitor_score,
                "source_confidence": source_confidence,
                "missing_information": ["competitor coverage is limited", "entity extraction needs richer tool coverage"],
            },
        )

    def test_research_enrichment_queue_csv_handles_mixed_row_fields(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            data_dir = root / "data"
            queue = (data_dir / "research_enrichment_queue.json")
            queue.parent.mkdir(parents=True, exist_ok=True)
            queue.write_text(
                json.dumps(
                    [
                        {"slug": "topic-a", "topic": "topic a", "status": "needs_enrichment"},
                        {"slug": "topic-b", "topic": "topic b", "status": "approved", "approved_at": "2026-07-07T00:00:00+00:00"},
                    ]
                ),
                encoding="utf-8",
            )
            platform = ResearchIntelligencePlatform(data_dir=data_dir)

            platform.queue.save(platform.queue.load())

            csv_text = (data_dir / "research_enrichment_queue.csv").read_text(encoding="utf-8")
            self.assertIn("approved_at", csv_text)
            self.assertIn("topic-b", csv_text)

    def test_build_package_uses_validated_weekly_source_urls(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            data_dir = root / "data"
            config = {
                "knowledge_review": {
                    "minimum_verified_sources": 2,
                    "minimum_official_sources": 1,
                    "minimum_trust_score": 50,
                    "minimum_freshness": 35,
                },
                "research_intelligence": {
                    "quality_gate": {"enabled": True, "threshold": 60, "allow_override": False},
                    "verified_source_gate": {
                        "enabled": True,
                        "minimum_official_docs_score": 20,
                        "minimum_pricing_source_score": 20,
                        "minimum_affiliate_source_score": 10,
                        "minimum_total_score": 35,
                    },
                },
            }
            platform = ResearchIntelligencePlatform(data_dir=data_dir, config=config)
            topic = {
                "topic": "Pydantic AI Review 2026",
                "slug": "pydantic-ai-review-2026",
                "validated_source_urls": [
                    "https://pydantic.dev/docs/ai/overview/",
                    "https://github.com/pydantic/pydantic-ai",
                ],
                "source_readiness": {"passes": True, "source_count": 2},
            }

            package = platform.build_research_package(topic)
            source_gate_passed, source_gate_reasons = platform._passes_verified_source_gate(
                package.sources,
                config["research_intelligence"]["verified_source_gate"],
            )

            self.assertEqual(package.sources["reference_count"], 2)
            self.assertEqual(len(package.sources["verified_sources"]), 2)
            self.assertEqual(package.sources["source_status"], "verified")
            self.assertTrue(source_gate_passed, source_gate_reasons)

    def test_validated_weekly_sources_rebuild_stale_zero_source_package(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            data_dir = root / "data"
            stale_dir = data_dir / "research" / "pydantic-ai-review-2026"
            stale_dir.mkdir(parents=True, exist_ok=True)
            stale_package = {
                "keyword": "Pydantic AI Review 2026",
                "slug": "pydantic-ai-review-2026",
                "generated_at": "2026-07-13T00:00:00+00:00",
                "package_dir": str(stale_dir),
                "keyword_intelligence": {},
                "keyword_summary": {},
                "outline": {},
                "faq": {},
                "entities": {},
                "competitors": {},
                "sources": {"verified_sources": [], "reference_count": 0},
                "writing_plan": {},
                "quality": {"overall_score": 0},
                "cache_hits": [],
            }
            (stale_dir / "package.json").write_text(json.dumps(stale_package), encoding="utf-8")
            platform = ResearchIntelligencePlatform(
                data_dir=data_dir,
                config={
                    "knowledge_review": {"minimum_verified_sources": 2, "minimum_official_sources": 1},
                    "research_intelligence": {"quality_gate": {"enabled": True, "threshold": 60, "allow_override": False}},
                },
            )

            package = platform.build_research_package(
                {
                    "topic": "Pydantic AI Review 2026",
                    "slug": "pydantic-ai-review-2026",
                    "validated_source_urls": [
                        "https://pydantic.dev/docs/ai/overview/",
                        "https://github.com/pydantic/pydantic-ai",
                    ],
                }
            )

            self.assertEqual(package.sources["reference_count"], 2)
            self.assertEqual(len(package.sources["verified_sources"]), 2)

    def test_builds_research_package_and_quality_report(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            data_dir = root / "data"
            site_output = root / "site_output"
            offers_file = data_dir / "offers.csv"
            affiliate_links_file = data_dir / "affiliate_links.csv"
            offers_file.parent.mkdir(parents=True, exist_ok=True)
            offers_file.write_text(
                "\n".join(
                    [
                        "offer_id,brand_name,website,affiliate_url,niche,commission_type,commission_rate,flat_commission,cookie_days,recurring,traffic_policy,direct_linking_allowed,brand_bidding_allowed,vendor_trust,buyer_intent,notes",
                        "cursor,Cursor,https://cursor.com,https://cursor.com/aff,AI Coding,recurring,25,0,30,True,allowed,False,False,88,84,fixture",
                        "windsurf,Windsurf,https://windsurf.com,https://windsurf.com/aff,AI Coding,recurring,20,0,30,True,allowed,False,False,84,80,fixture",
                    ]
                ),
                encoding="utf-8",
            )
            affiliate_links_file.write_text(
                "\n".join(
                    [
                        "tool_slug,tool_name,brand,slug,official_url,affiliate_url,affiliate_status,status,notes,commission_note,network,approved",
                        "cursor,Cursor,Cursor,cursor,https://cursor.com,https://cursor.com/aff,active,active,fixture,25% recurring,PartnerStack,True",
                    ]
                ),
                encoding="utf-8",
            )
            (data_dir / "source_registry.json").write_text(
                json.dumps(
                    [
                        {
                            "brand": "Cursor",
                            "slug": "cursor",
                            "source_type": "official_docs",
                            "source_name": "Cursor docs",
                            "source_url": "https://cursor.com/docs",
                            "source_status": "verified",
                            "confidence": 92,
                            "notes": "fixture registry",
                            "last_verified_at": "2026-07-07",
                        },
                        {
                            "brand": "Cursor",
                            "slug": "cursor",
                            "source_type": "pricing_page",
                            "source_name": "Cursor pricing",
                            "source_url": "https://cursor.com/pricing",
                            "source_status": "verified",
                            "confidence": 92,
                            "notes": "fixture registry",
                            "last_verified_at": "2026-07-07",
                        },
                        {
                            "brand": "Cursor",
                            "slug": "cursor",
                            "source_type": "affiliate_program_page",
                            "source_name": "Cursor affiliate",
                            "source_url": "https://cursor.com/affiliates",
                            "source_status": "verified",
                            "confidence": 88,
                            "notes": "fixture registry",
                            "last_verified_at": "2026-07-07",
                        },
                    ]
                ),
                encoding="utf-8",
            )

            engine = ResearchIntelligencePlatform(
                data_dir=data_dir,
                site_output_dir=site_output,
                offers_file=offers_file,
                affiliate_links_file=affiliate_links_file,
                config={"research_intelligence": {"cache_enabled": True}},
            )
            topic = {
                "topic": "cursor vs windsurf for teams",
                "slug": "cursor-vs-windsurf-for-teams",
                "related_keywords": [
                    "cursor pricing",
                    "windsurf alternatives",
                    "ai coding tools for teams",
                ],
                "suggested_internal_links": [
                    "/comparisons/cursor-vs-windsurf/",
                    "/category/ai-coding-tools/",
                ],
            }

            package = engine.build_research_package(topic)

            self.assertEqual(package.keyword, topic["topic"])
            self.assertTrue(package.keyword_intelligence["primary_keyword"])
            self.assertTrue(package.outline["heading_hierarchy"])
            self.assertTrue(package.faq["pricing"])
            self.assertIn("Cursor", package.entities["products"])
            self.assertTrue(package.sources["reference_count"] >= 1)
            self.assertIn("overall_score", package.quality)
            self.assertEqual(package.sources["source_status"], "verified")
            self.assertGreaterEqual(package.quality["total_verified_source_score"], 35)
            self.assertTrue((data_dir / "source_review_queue.json").exists())
            self.assertTrue((data_dir / "source_review_report.json").exists())
            self.assertTrue((data_dir / "knowledge_dashboard.json").exists())

            package_dir = Path(package.package_dir)
            self.assertTrue((package_dir / "keyword.json").exists())
            self.assertTrue((package_dir / "keyword_intelligence.json").exists())
            self.assertTrue((package_dir / "outline.json").exists())
            self.assertTrue((package_dir / "faq.json").exists())
            self.assertTrue((package_dir / "entities.json").exists())
            self.assertTrue((package_dir / "competitors.json").exists())
            self.assertTrue((package_dir / "sources.json").exists())
            self.assertTrue((package_dir / "writing_plan.json").exists())
            self.assertTrue((data_dir / "research_quality_report.json").exists())

            report = json.loads((data_dir / "research_quality_report.json").read_text(encoding="utf-8"))
            self.assertEqual(report[0]["slug"], topic["slug"])
            self.assertIn("entity_coverage_score", package.quality)
            self.assertIn("missing_entity_types", package.quality)

    def test_reuses_cached_research_for_shared_tool_entities(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            data_dir = root / "data"
            offers_file = data_dir / "offers.csv"
            affiliate_links_file = data_dir / "affiliate_links.csv"
            offers_file.parent.mkdir(parents=True, exist_ok=True)
            offers_file.write_text(
                "\n".join(
                    [
                        "offer_id,brand_name,website,affiliate_url,niche,commission_type,commission_rate,flat_commission,cookie_days,recurring,traffic_policy,direct_linking_allowed,brand_bidding_allowed,vendor_trust,buyer_intent,notes",
                        "cursor,Cursor,https://cursor.com,https://cursor.com/aff,AI Coding,recurring,25,0,30,True,allowed,False,False,88,84,fixture",
                    ]
                ),
                encoding="utf-8",
            )
            affiliate_links_file.write_text(
                "\n".join(
                    [
                        "tool_slug,tool_name,brand,slug,official_url,affiliate_url,affiliate_status,status,notes,commission_note,network,approved",
                        "cursor,Cursor,Cursor,cursor,https://cursor.com,https://cursor.com/aff,active,active,fixture,25% recurring,PartnerStack,True",
                    ]
                ),
                encoding="utf-8",
            )
            (data_dir / "source_registry.json").write_text(
                json.dumps(
                    [
                        {
                            "brand": "Cursor",
                            "slug": "cursor",
                            "source_type": "official_docs",
                            "source_name": "Cursor docs",
                            "source_url": "https://cursor.com/docs",
                            "source_status": "verified",
                            "confidence": 92,
                            "notes": "fixture registry",
                            "last_verified_at": "2026-07-07",
                        },
                        {
                            "brand": "Cursor",
                            "slug": "cursor",
                            "source_type": "pricing_page",
                            "source_name": "Cursor pricing",
                            "source_url": "https://cursor.com/pricing",
                            "source_status": "verified",
                            "confidence": 92,
                            "notes": "fixture registry",
                            "last_verified_at": "2026-07-07",
                        },
                    ]
                ),
                encoding="utf-8",
            )
            engine = ResearchIntelligencePlatform(
                data_dir=data_dir,
                offers_file=offers_file,
                affiliate_links_file=affiliate_links_file,
            )
            first = engine.build_research_package({"topic": "cursor pricing", "slug": "cursor-pricing"})
            second = engine.build_research_package({"topic": "cursor review for teams", "slug": "cursor-review-for-teams"})

            self.assertTrue((data_dir / "research_cache" / "entities" / "cursor.json").exists())
            self.assertIn("Cursor", second.cache_hits)
            self.assertTrue(first.sources["reference_count"] >= 1)

    def test_quality_gate_blocks_low_score_and_enters_queue(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            data_dir = root / "data"
            offers_file = data_dir / "offers.csv"
            affiliate_links_file = data_dir / "affiliate_links.csv"
            offers_file.parent.mkdir(parents=True, exist_ok=True)
            offers_file.write_text("offer_id,brand_name,website,affiliate_url,niche,commission_type,commission_rate,flat_commission,cookie_days,recurring,traffic_policy,direct_linking_allowed,brand_bidding_allowed,vendor_trust,buyer_intent,notes\n", encoding="utf-8")
            affiliate_links_file.write_text("tool_slug,tool_name,brand,slug,official_url,affiliate_url,affiliate_status,status,notes,commission_note,network,approved\n", encoding="utf-8")
            engine = ResearchIntelligencePlatform(
                data_dir=data_dir,
                offers_file=offers_file,
                affiliate_links_file=affiliate_links_file,
                config={
                    "research_intelligence": {
                        "quality_gate": {"threshold": 90, "enabled": True, "allow_override": False},
                        "verified_source_gate": {
                            "enabled": True,
                            "minimum_official_docs_score": 20,
                            "minimum_pricing_source_score": 20,
                            "minimum_affiliate_source_score": 10,
                            "minimum_total_score": 35,
                        },
                    }
                },
            )
            package = engine.build_research_package({"topic": "unknown ai workflow", "slug": "unknown-ai-workflow"})
            gate = engine.evaluate_quality_gate(package, topic={"topic": package.keyword, "slug": package.slug})

            self.assertFalse(gate.passed)
            self.assertEqual(gate.status, "needs_enrichment")
            queue = json.loads((data_dir / "research_enrichment_queue.json").read_text(encoding="utf-8"))
            self.assertEqual(queue[0]["slug"], "unknown-ai-workflow")
            self.assertIn("missing_verified_sources", queue[0])

    def test_warning_level_quality_gates_do_not_block_generation(self) -> None:
        with TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir) / "data"
            engine = ResearchIntelligencePlatform(
                data_dir=data_dir,
                config={
                    "threshold_policy": {
                        "initial_thresholds": {
                            "research_quality_score": 50,
                            "entity_coverage_score": 40,
                            "competitor_coverage_score": 30,
                            "freshness_score": 40,
                        },
                        "critical_minimums": {"minimum_usable_sources": 1, "research_quality_score": 35},
                    },
                    "research_intelligence": {
                        "quality_gate": {"enabled": True, "threshold": 50, "allow_override": False},
                        "verified_source_gate": {"enabled": True, "minimum_total_score": 35},
                    },
                    "knowledge_review": {"minimum_verified_sources": 2, "minimum_official_sources": 0, "minimum_trust_score": 50, "minimum_freshness": 20},
                },
            )
            package = self._research_package(score=48, entity_score=38, competitor_score=10, source_confidence=35, verified_sources=2)

            gate = engine.evaluate_quality_gate(package, topic={"topic": package.keyword, "slug": package.slug})

            self.assertTrue(gate.passed)
            self.assertEqual(gate.status, "warning")
            self.assertEqual(gate.hard_blockers, ())
            self.assertTrue(any("competitor_coverage_score" in warning for warning in gate.warnings))
            self.assertTrue(any("entity_coverage_score" in warning for warning in gate.warnings))

    def test_critical_research_quality_blocks_generation(self) -> None:
        with TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir) / "data"
            engine = ResearchIntelligencePlatform(
                data_dir=data_dir,
                config={
                    "threshold_policy": {
                        "initial_thresholds": {"research_quality_score": 50},
                        "critical_minimums": {"minimum_usable_sources": 1, "research_quality_score": 35},
                    },
                    "research_intelligence": {"quality_gate": {"enabled": True, "threshold": 50, "allow_override": False}, "verified_source_gate": {"enabled": False}},
                },
            )
            package = self._research_package(score=30, verified_sources=2)

            gate = engine.evaluate_quality_gate(package, topic={"topic": package.keyword, "slug": package.slug})

            self.assertFalse(gate.passed)
            self.assertIn("research_quality_score 30.0 below critical minimum 35.0", gate.hard_blockers)

    def test_thresholds_can_be_raised_by_config_only(self) -> None:
        with TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir) / "data"
            package = self._research_package(score=58, entity_score=45, competitor_score=35, source_confidence=45, verified_sources=2)
            base_engine = ResearchIntelligencePlatform(
                data_dir=data_dir,
                config={
                    "threshold_policy": {
                        "initial_thresholds": {"research_quality_score": 50},
                        "critical_minimums": {"minimum_usable_sources": 1, "research_quality_score": 35},
                    },
                    "research_intelligence": {"quality_gate": {"enabled": True, "threshold": 50, "allow_override": False}, "verified_source_gate": {"enabled": False}},
                },
            )
            raised_engine = ResearchIntelligencePlatform(
                data_dir=data_dir,
                config={
                    "threshold_policy": {
                        "initial_thresholds": {"research_quality_score": 70},
                        "critical_minimums": {"minimum_usable_sources": 1, "research_quality_score": 35},
                    },
                    "research_intelligence": {"quality_gate": {"enabled": True, "threshold": 50, "allow_override": False}, "verified_source_gate": {"enabled": False}},
                },
            )

            self.assertEqual(base_engine.evaluate_quality_gate(package, topic={"topic": package.keyword, "slug": package.slug}).status, "passed")
            raised = raised_engine.evaluate_quality_gate(package, topic={"topic": package.keyword, "slug": package.slug})
            self.assertTrue(raised.passed)
            self.assertEqual(raised.status, "warning")

    def test_verified_source_gate_warns_when_registry_is_missing(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            data_dir = root / "data"
            offers_file = data_dir / "offers.csv"
            affiliate_links_file = data_dir / "affiliate_links.csv"
            offers_file.parent.mkdir(parents=True, exist_ok=True)
            offers_file.write_text(
                "\n".join(
                    [
                        "offer_id,brand_name,website,affiliate_url,niche,commission_type,commission_rate,flat_commission,cookie_days,recurring,traffic_policy,direct_linking_allowed,brand_bidding_allowed,vendor_trust,buyer_intent,notes",
                        "cursor,Cursor,https://cursor.com,https://cursor.com/aff,AI Coding,recurring,25,0,30,True,allowed,False,False,88,84,fixture",
                    ]
                ),
                encoding="utf-8",
            )
            affiliate_links_file.write_text(
                "\n".join(
                    [
                        "tool_slug,tool_name,brand,slug,official_url,affiliate_url,affiliate_status,status,notes,commission_note,network,approved",
                        "cursor,Cursor,Cursor,cursor,https://cursor.com,https://cursor.com/aff,active,active,fixture,25% recurring,PartnerStack,True",
                    ]
                ),
                encoding="utf-8",
            )
            engine = ResearchIntelligencePlatform(
                data_dir=data_dir,
                offers_file=offers_file,
                affiliate_links_file=affiliate_links_file,
                config={
                    "research_intelligence": {
                        "quality_gate": {"threshold": 0, "enabled": True, "allow_override": False},
                        "verified_source_gate": {
                            "enabled": True,
                            "minimum_official_docs_score": 20,
                            "minimum_pricing_source_score": 20,
                            "minimum_affiliate_source_score": 10,
                            "minimum_total_score": 35,
                        },
                    }
                },
            )

            package = engine.build_research_package({"topic": "cursor pricing", "slug": "cursor-pricing"})
            gate = engine.evaluate_quality_gate(package, topic={"topic": package.keyword, "slug": package.slug})

            self.assertTrue(gate.passed)
            self.assertEqual(gate.status, "warning")
            self.assertTrue(gate.warnings)

    def test_expired_verified_sources_do_not_raise_confidence(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            data_dir = root / "data"
            offers_file = data_dir / "offers.csv"
            affiliate_links_file = data_dir / "affiliate_links.csv"
            offers_file.parent.mkdir(parents=True, exist_ok=True)
            offers_file.write_text(
                "\n".join(
                    [
                        "offer_id,brand_name,website,affiliate_url,niche,commission_type,commission_rate,flat_commission,cookie_days,recurring,traffic_policy,direct_linking_allowed,brand_bidding_allowed,vendor_trust,buyer_intent,notes",
                        "cursor,Cursor,https://cursor.com,https://cursor.com/aff,AI Coding,recurring,25,0,30,True,allowed,False,False,88,84,fixture",
                    ]
                ),
                encoding="utf-8",
            )
            affiliate_links_file.write_text(
                "\n".join(
                    [
                        "tool_slug,tool_name,brand,slug,official_url,affiliate_url,affiliate_status,status,notes,commission_note,network,approved",
                        "cursor,Cursor,Cursor,cursor,https://cursor.com,https://cursor.com/aff,active,active,fixture,25% recurring,PartnerStack,True",
                    ]
                ),
                encoding="utf-8",
            )
            (data_dir / "source_registry.json").write_text(
                json.dumps(
                    [
                        {
                            "brand": "Cursor",
                            "slug": "cursor",
                            "source_type": "official_docs",
                            "source_name": "Cursor docs",
                            "source_url": "https://cursor.com/docs",
                            "verification_status": "verified",
                            "confidence": 92,
                            "verification_date": "2024-01-01T00:00:00+00:00",
                        },
                        {
                            "brand": "Cursor",
                            "slug": "cursor",
                            "source_type": "pricing_page",
                            "source_name": "Cursor pricing",
                            "source_url": "https://cursor.com/pricing",
                            "verification_status": "verified",
                            "confidence": 92,
                            "verification_date": "2024-01-01T00:00:00+00:00",
                        },
                    ]
                ),
                encoding="utf-8",
            )
            engine = ResearchIntelligencePlatform(
                data_dir=data_dir,
                offers_file=offers_file,
                affiliate_links_file=affiliate_links_file,
                config={
                    "research_intelligence": {
                        "quality_gate": {"threshold": 0, "enabled": True, "allow_override": False},
                        "verified_source_gate": {
                            "enabled": True,
                            "minimum_official_docs_score": 20,
                            "minimum_pricing_source_score": 20,
                            "minimum_affiliate_source_score": 0,
                            "minimum_total_score": 35,
                        },
                    },
                    "knowledge_review": {
                        "minimum_verified_sources": 1,
                        "minimum_official_sources": 1,
                        "minimum_trust_score": 50,
                        "minimum_freshness": 35,
                        "review_after_days": 90,
                        "expire_after_days": 365,
                    },
                },
            )

            package = engine.build_research_package({"topic": "cursor pricing", "slug": "cursor-pricing"})
            gate = engine.evaluate_quality_gate(package, topic={"topic": package.keyword, "slug": package.slug})

            self.assertTrue(gate.passed)
            self.assertEqual(gate.status, "warning")
            self.assertTrue(gate.warnings)
            self.assertIn(package.sources["source_status"], {"needs_review", "missing"})
            self.assertLessEqual(float(package.sources["source_confidence"]), 45)

    def test_enrichment_runner_updates_status_when_local_snapshot_improves_quality(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            data_dir = root / "data"
            offers_file = data_dir / "offers.csv"
            affiliate_links_file = data_dir / "affiliate_links.csv"
            offers_file.parent.mkdir(parents=True, exist_ok=True)
            offers_file.write_text(
                "\n".join(
                    [
                        "offer_id,brand_name,website,affiliate_url,niche,commission_type,commission_rate,flat_commission,cookie_days,recurring,traffic_policy,direct_linking_allowed,brand_bidding_allowed,vendor_trust,buyer_intent,notes",
                        "cursor,Cursor,https://cursor.com,https://cursor.com/aff,AI Coding,recurring,25,0,30,True,allowed,False,False,88,84,fixture",
                    ]
                ),
                encoding="utf-8",
            )
            affiliate_links_file.write_text(
                "\n".join(
                    [
                        "tool_slug,tool_name,brand,slug,official_url,affiliate_url,affiliate_status,status,notes,commission_note,network,approved",
                        "cursor,Cursor,Cursor,cursor,https://cursor.com,https://cursor.com/aff,active,active,fixture,25% recurring,PartnerStack,True",
                    ]
                ),
                encoding="utf-8",
            )
            engine = ResearchIntelligencePlatform(
                data_dir=data_dir,
                offers_file=offers_file,
                affiliate_links_file=affiliate_links_file,
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
                    }
                },
            )
            topic = {"topic": "cursor pricing", "slug": "cursor-pricing"}
            package = engine.build_research_package(topic)
            gate = engine.evaluate_quality_gate(package, topic=topic)
            self.assertTrue(gate.passed)
            self.assertEqual(gate.status, "warning")

            (data_dir / "competitor_snapshots.json").write_text(
                json.dumps(
                    [
                        {
                            "keyword": "cursor pricing",
                            "competitor_url": "https://example.com/cursor-pricing",
                            "title": "Cursor Pricing Review",
                            "meta_description": "Fixture competitor snapshot",
                            "headings": ["Overview", "Pricing"],
                            "word_count": 1800,
                            "content_angle": "pricing comparison",
                            "strengths": ["clear pricing"],
                            "weaknesses": ["thin faq"],
                            "missing_topics": ["affiliate disclosure"],
                            "affiliate_elements": ["cta"],
                            "last_checked": "2026-07-07",
                        }
                    ]
                ),
                encoding="utf-8",
            )
            (data_dir / "source_registry.json").write_text(
                json.dumps(
                    [
                        {
                            "brand": "Cursor",
                            "slug": "cursor",
                            "source_type": "official_docs",
                            "source_name": "Cursor docs",
                            "source_url": "https://cursor.com/docs",
                            "source_status": "verified",
                            "confidence": 92,
                            "notes": "fixture registry",
                            "last_verified_at": "2026-07-07",
                        },
                        {
                            "brand": "Cursor",
                            "slug": "cursor",
                            "source_type": "pricing_page",
                            "source_name": "Cursor pricing",
                            "source_url": "https://cursor.com/pricing",
                            "source_status": "verified",
                            "confidence": 92,
                            "notes": "fixture registry",
                            "last_verified_at": "2026-07-07",
                        },
                        {
                            "brand": "Cursor",
                            "slug": "cursor",
                            "source_type": "affiliate_program_page",
                            "source_name": "Cursor affiliate",
                            "source_url": "https://cursor.com/affiliates",
                            "source_status": "verified",
                            "confidence": 88,
                            "notes": "fixture registry",
                            "last_verified_at": "2026-07-07",
                        },
                    ]
                ),
                encoding="utf-8",
            )
            engine = ResearchIntelligencePlatform(
                data_dir=data_dir,
                offers_file=offers_file,
                affiliate_links_file=affiliate_links_file,
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
                    }
                },
            )
            result = engine.run_enrichment()

            self.assertEqual(result["topics_processed"], 1)
            queue = json.loads((data_dir / "research_enrichment_queue.json").read_text(encoding="utf-8"))
            self.assertEqual(queue[0]["status"], "approved")
            self.assertTrue((data_dir / "research_enrichment_report.json").exists())


if __name__ == "__main__":
    unittest.main()
