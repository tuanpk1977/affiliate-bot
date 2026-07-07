from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from modules.research_intelligence import ResearchIntelligencePlatform


class ResearchIntelligenceTests(unittest.TestCase):
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
                config={"research_intelligence": {"quality_gate": {"threshold": 90, "enabled": True, "allow_override": False}}},
            )
            package = engine.build_research_package({"topic": "unknown ai workflow", "slug": "unknown-ai-workflow"})
            gate = engine.evaluate_quality_gate(package, topic={"topic": package.keyword, "slug": package.slug})

            self.assertFalse(gate.passed)
            self.assertEqual(gate.status, "needs_enrichment")
            queue = json.loads((data_dir / "research_enrichment_queue.json").read_text(encoding="utf-8"))
            self.assertEqual(queue[0]["slug"], "unknown-ai-workflow")

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
                config={"research_intelligence": {"quality_gate": {"threshold": 60, "enabled": True, "allow_override": False}}},
            )
            topic = {"topic": "cursor pricing", "slug": "cursor-pricing"}
            package = engine.build_research_package(topic)
            gate = engine.evaluate_quality_gate(package, topic=topic)
            self.assertFalse(gate.passed)

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
            engine = ResearchIntelligencePlatform(
                data_dir=data_dir,
                offers_file=offers_file,
                affiliate_links_file=affiliate_links_file,
                config={"research_intelligence": {"quality_gate": {"threshold": 60, "enabled": True, "allow_override": False}}},
            )
            result = engine.run_enrichment()

            self.assertEqual(result["topics_processed"], 1)
            queue = json.loads((data_dir / "research_enrichment_queue.json").read_text(encoding="utf-8"))
            self.assertEqual(queue[0]["status"], "approved")
            self.assertTrue((data_dir / "research_enrichment_report.json").exists())


if __name__ == "__main__":
    unittest.main()
