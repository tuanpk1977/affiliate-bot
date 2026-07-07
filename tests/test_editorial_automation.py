from __future__ import annotations

import json
from contextlib import ExitStack
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
import unittest

from modules import content_growth_pipeline as pipeline
from modules import editorial_automation


def make_candidates() -> list[editorial_automation.CandidateTopicRecord]:
    return [
        editorial_automation.CandidateTopicRecord(
            generated_at="2026-07-07T00:00:00+00:00",
            keyword=f"validation editorial topic {index}",
            title=f"validation editorial topic {index}",
            slug=f"validation-editorial-topic-{index}",
            intent="commercial",
            category="AI Software",
            cluster=f"validation editorial cluster {index}",
            score=90 - index,
            popularity=80,
            freshness=75,
            seo_opportunity=65,
            affiliate_opportunity=70,
            commercial_intent=68,
            competition=35,
            existing_website_coverage=0,
            source_count=3,
            source_list=["static"],
            priority="P1",
            article_type="comparison",
            affiliate_score="high",
            estimated_article_count=7,
            related_keywords=[f"validation editorial topic {index} pricing"],
            planning_reasoning=["fixture reasoning"],
            already_published=False,
        )
        for index in range(1, 11)
    ]


class EditorialAutomationTests(unittest.TestCase):
    def test_weekly_cycle_writes_topics_and_calendar(self) -> None:
        with TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir) / "data"
            fake_settings = SimpleNamespace(
                base_dir=Path(temp_dir),
                data_dir=data_dir,
                site_output_dir=Path(temp_dir) / "site_output",
                offers_file=data_dir / "offers.csv",
                affiliate_links_file=data_dir / "affiliate_links.csv",
                editorial_config={
                    "business_intelligence": {"evergreen": {"min_word_count": 100, "min_readability_score": 10}},
                    "research_intelligence": {"quality_gate": {"threshold": 0, "enabled": True, "allow_override": False}},
                },
                editorial_research_config={"quality_gate": {"threshold": 0, "enabled": True, "allow_override": False}},
                editorial_candidate_limit=200,
                editorial_max_per_source=40,
                editorial_top_topics=10,
                editorial_calendar_days=7,
            )
            with patch.object(editorial_automation, "settings", fake_settings):
                engine = editorial_automation.WeeklyTrendIntelligenceEngine(providers=[])
                with patch.object(engine, "collect_candidates", return_value=make_candidates()):
                    result = engine.run_weekly_cycle()

            self.assertEqual(result["weekly_topics"], 10)
            self.assertEqual(result["approved_topics"], 10)
            self.assertEqual(result["calendar_entries"], 70)
            self.assertTrue((data_dir / "weekly_topics.csv").exists())
            self.assertTrue((data_dir / "editorial_calendar.json").exists())
            self.assertTrue((data_dir / "evergreen_report.json").exists())
            self.assertTrue((data_dir / "affiliate_opportunities.json").exists())
            self.assertTrue((data_dir / "weekly_dashboard.md").exists())
            self.assertTrue((data_dir / "weekly_history.jsonl").exists())
            self.assertTrue((data_dir / "content_lifecycle.jsonl").exists())

            weekly_topics = json.loads((data_dir / "weekly_topics.json").read_text(encoding="utf-8"))
            calendar = json.loads((data_dir / "editorial_calendar.json").read_text(encoding="utf-8"))
            self.assertEqual(len(weekly_topics), 10)
            self.assertEqual(len(calendar), 70)
            self.assertTrue(all(topic["estimated_article_count"] == 7 for topic in weekly_topics))
            self.assertTrue(any(entry["day_of_week"] == "Monday" for entry in calendar))

    def test_daily_runner_uses_existing_calendar_only(self) -> None:
        target_date = date(2026, 7, 7)
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            data_dir = root / "data"
            calendar_path = data_dir / "editorial_calendar.json"
            calendar_path.parent.mkdir(parents=True, exist_ok=True)
            calendar_path.write_text(
                json.dumps(
                    [
                        {
                            "publish_date": target_date.isoformat(),
                            "day_of_week": "Tuesday",
                            "parent_keyword": "best ai coding assistants for teams",
                            "parent_slug": "best-ai-coding-assistants-for-teams",
                            "keyword": "best ai coding assistants for teams pricing",
                            "title": "best ai coding assistants for teams Pricing",
                            "slug": "best-ai-coding-assistants-for-teams-pricing",
                            "stage": "deep_dive",
                            "article_type": "pricing",
                            "cluster": "best ai coding assistants for teams",
                            "priority": "P1",
                            "intent": "commercial",
                            "related_keywords": ["ai coding tools for teams"],
                            "reasoning": ["calendar test"],
                        }
                    ],
                    indent=2,
                ),
                encoding="utf-8",
            )

            fake_settings = SimpleNamespace(
                base_dir=root,
                data_dir=data_dir,
                site_output_dir=root / "site_output",
                offers_file=data_dir / "offers.csv",
                affiliate_links_file=data_dir / "affiliate_links.csv",
                editorial_config={
                    "business_intelligence": {"evergreen": {"min_word_count": 100, "min_readability_score": 10}},
                    "research_intelligence": {"quality_gate": {"threshold": 0, "enabled": True, "allow_override": False}},
                },
                editorial_research_config={"quality_gate": {"threshold": 0, "enabled": True, "allow_override": False}},
                editorial_candidate_limit=200,
                editorial_max_per_source=40,
                editorial_top_topics=10,
                editorial_calendar_days=7,
            )
            with ExitStack() as stack:
                stack.enter_context(patch.object(editorial_automation, "settings", fake_settings))
                stack.enter_context(patch.object(pipeline, "ROOT", root))
                stack.enter_context(patch.object(pipeline, "DATA_DIR", data_dir))
                stack.enter_context(patch.object(pipeline, "PUBLISHED_DIR", data_dir / "published_static_pages"))
                stack.enter_context(patch.object(pipeline, "SITE_OUTPUT", root / "site_output"))
                stack.enter_context(patch.object(pipeline, "VIDEO_OUTPUT", root / "video_output"))
                stack.enter_context(patch.object(pipeline, "SOCIAL_DRAFTS", root / "social_drafts"))
                stack.enter_context(patch.object(pipeline, "REPORT_DIR", data_dir / "content_growth_reports"))
                stack.enter_context(patch.object(pipeline, "TRACKING_CSV", data_dir / "content_growth_performance_log.csv"))
                stack.enter_context(patch.object(pipeline, "_CONTENT_PLANNER", None))
                stack.enter_context(patch.object(pipeline, "_RESEARCH_PLATFORM", None))
                result = editorial_automation.run_daily_editorial_content(target_date=target_date, build=False)

            self.assertEqual(result["calendar_rows"], 1)
            self.assertEqual(len(result["generated_pages"]), 1)
            self.assertIsNone(result["weekly_refresh"])
            self.assertTrue((data_dir / f"daily_editorial_report_{target_date.isoformat()}.json").exists())
            self.assertTrue((data_dir / "content_lifecycle.jsonl").exists())
            page = result["generated_pages"][0]
            self.assertIn("research", page)
            self.assertIn("planning", page)
            self.assertEqual(page["slug"], "best-ai-coding-assistants-for-teams-pricing")

    def test_monday_runner_refreshes_weekly_topics_before_generation(self) -> None:
        target_date = date(2026, 7, 6)
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            data_dir = root / "data"
            fake_settings = SimpleNamespace(
                base_dir=root,
                data_dir=data_dir,
                site_output_dir=root / "site_output",
                offers_file=data_dir / "offers.csv",
                affiliate_links_file=data_dir / "affiliate_links.csv",
                editorial_config={
                    "business_intelligence": {"evergreen": {"min_word_count": 100, "min_readability_score": 10}},
                    "research_intelligence": {
                        "quality_gate": {"threshold": 0, "enabled": True, "allow_override": False},
                        "auto_refresh_weekly_on_monday": True,
                    },
                },
                editorial_research_config={
                    "quality_gate": {"threshold": 0, "enabled": True, "allow_override": False},
                    "auto_refresh_weekly_on_monday": True,
                },
                editorial_candidate_limit=200,
                editorial_max_per_source=40,
                editorial_top_topics=10,
                editorial_calendar_days=7,
            )
            monday_rows = [
                {
                    "publish_date": target_date.isoformat(),
                    "day_of_week": "Monday",
                    "parent_keyword": "best ai coding assistants for teams",
                    "parent_slug": "best-ai-coding-assistants-for-teams",
                    "keyword": "best ai coding assistants for teams",
                    "title": "best ai coding assistants for teams",
                    "slug": "best-ai-coding-assistants-for-teams",
                    "stage": "pillar",
                    "article_type": "comparison",
                    "cluster": "best ai coding assistants for teams",
                    "priority": "P1",
                    "intent": "commercial",
                    "related_keywords": ["ai coding tools for teams"],
                    "reasoning": ["calendar test"],
                }
            ]
            with ExitStack() as stack:
                stack.enter_context(patch.object(editorial_automation, "settings", fake_settings))
                stack.enter_context(patch.object(pipeline, "ROOT", root))
                stack.enter_context(patch.object(pipeline, "DATA_DIR", data_dir))
                stack.enter_context(patch.object(pipeline, "PUBLISHED_DIR", data_dir / "published_static_pages"))
                stack.enter_context(patch.object(pipeline, "SITE_OUTPUT", root / "site_output"))
                stack.enter_context(patch.object(pipeline, "VIDEO_OUTPUT", root / "video_output"))
                stack.enter_context(patch.object(pipeline, "SOCIAL_DRAFTS", root / "social_drafts"))
                stack.enter_context(patch.object(pipeline, "REPORT_DIR", data_dir / "content_growth_reports"))
                stack.enter_context(patch.object(pipeline, "TRACKING_CSV", data_dir / "content_growth_performance_log.csv"))
                stack.enter_context(patch.object(pipeline, "_CONTENT_PLANNER", None))
                stack.enter_context(patch.object(pipeline, "_RESEARCH_PLATFORM", None))
                stack.enter_context(patch.object(editorial_automation, "load_editorial_calendar", return_value=monday_rows))
                stack.enter_context(
                    patch.object(
                        editorial_automation.WeeklyTrendIntelligenceEngine,
                        "run_weekly_cycle",
                        return_value={"weekly_topics": 10, "approved_topics": 3, "calendar_entries": 21},
                    )
                )
                result = editorial_automation.run_daily_editorial_content(target_date=target_date, build=False)

            self.assertIsNotNone(result["weekly_refresh"])
            self.assertEqual(result["weekly_refresh"]["approved_topics"], 3)


if __name__ == "__main__":
    unittest.main()
