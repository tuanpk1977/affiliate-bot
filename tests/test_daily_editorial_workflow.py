from __future__ import annotations

import json
import io
import unittest
from contextlib import redirect_stdout
from datetime import date
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from modules.daily_editorial_workflow import DailyEditorialWorkflow

EDITORIAL_CONSOLE_PATH = Path(__file__).resolve().parents[1] / "editorial_console.py"
EDITORIAL_CONSOLE_SPEC = spec_from_file_location("root_editorial_console", EDITORIAL_CONSOLE_PATH)
assert EDITORIAL_CONSOLE_SPEC and EDITORIAL_CONSOLE_SPEC.loader
EDITORIAL_CONSOLE_MODULE = module_from_spec(EDITORIAL_CONSOLE_SPEC)
EDITORIAL_CONSOLE_SPEC.loader.exec_module(EDITORIAL_CONSOLE_MODULE)
build_parser = EDITORIAL_CONSOLE_MODULE.build_parser
editorial_console_main = EDITORIAL_CONSOLE_MODULE.main


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _read_json_for_test(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _canonical_article_html(title: str = "Good") -> str:
    return f"""<!doctype html>
<html lang="en"><head>
<title>{title}</title>
<meta name="description" content="desc">
<link rel="canonical" href="https://smileaireviewhub.com/good/">
<link rel="stylesheet" href="/assets/article.css">
<script type="application/ld+json">{{"@context":"https://schema.org","@type":"FAQPage","mainEntity":[]}}</script>
</head><body>
<header class="site-header"><nav class="site-nav"></nav></header>
<main class="article-layout"><article class="article-container">
<a class="cta-button" href="https://example.com" rel="noopener noreferrer">Visit official website</a>
<div class="table-wrapper"><table class="article-table"><thead><tr><th scope="col">Tool</th></tr></thead><tbody><tr><th scope="row">One</th></tr></tbody></table></div>
<section id="faq"><div class="faq-list"><details><summary>Question?</summary><p>Answer.</p></details></div></section>
</article></main>
<footer class="site-footer">
<div class="footer-grid"><div class="footer-column footer-brand"><p class="footer-description">Independent reviews.</p></div>
<div class="footer-column"><ul class="footer-links"><li><a href="/reviews/">Reviews</a></li></ul></div>
<div class="footer-column"><ul class="footer-links"><li><a href="/about/">About</a></li></ul></div>
<div class="footer-column"><ul class="footer-links footer-social-links"><li><a href="https://example.com">LinkedIn</a></li></ul></div></div>
<div class="footer-bottom"><p>Copyright</p></div>
</footer></body></html>"""


class DailyEditorialWorkflowTests(unittest.TestCase):
    def test_public_render_validator_rejects_internal_status_and_legacy_markup(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workflow = DailyEditorialWorkflow(root=root, data_dir=root / "data", site_output_dir=root / "site_output")
            page = root / "site_output" / "example" / "index.html"
            page.parent.mkdir(parents=True, exist_ok=True)
            page.write_text(
                """<!doctype html>
<html lang="en"><head>
<title>Example</title>
<meta name="description" content="Example description.">
<link rel="canonical" href="https://example.com/example/">
<link rel="stylesheet" href="/assets/article.css">
</head><body>
<header class="site-header"></header>
<main class="article-layout">
<a href="https://example.com">Visit official website</a>
<table><tr><td>Bad table</td></tr></table>
<p>Reviewed by: needs_human_review</p>
<p>Status: needs_review</p>
<p>Pricing Cursor: những điểm cần kiểm tra trước khi mua</p>
</main></body></html>""",
                encoding="utf-8",
            )

            errors = workflow._validate_single_html_file(page, scope="site_output")

            self.assertTrue(any("internal workflow status" in error for error in errors))
            self.assertTrue(any("needs_review" in error for error in errors))
            self.assertTrue(any("comparison tables" in error for error in errors))
            self.assertTrue(any("CTA links" in error for error in errors))
            self.assertTrue(any("Vietnamese public label" in error for error in errors))

    def test_public_render_validator_accepts_canonical_article_markup(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workflow = DailyEditorialWorkflow(root=root, data_dir=root / "data", site_output_dir=root / "site_output")
            page = root / "site_output" / "example" / "index.html"
            page.parent.mkdir(parents=True, exist_ok=True)
            page.write_text(
                """<!doctype html>
<html lang="en"><head>
<title>Example</title>
<meta name="description" content="Example description.">
<link rel="canonical" href="https://example.com/example/">
<link rel="stylesheet" href="/assets/article.css">
<script type="application/ld+json">{"@context":"https://schema.org","@type":"FAQPage","mainEntity":[]}</script>
</head><body>
<header class="site-header"></header>
<main class="article-layout"><article class="article-container">
<a class="cta-button" href="/go/example/" rel="sponsored noopener noreferrer">Visit official website</a>
<div class="table-wrapper"><table class="article-table"><thead><tr><th scope="col">Tool</th></tr></thead><tbody><tr><th scope="row">Example</th></tr></tbody></table></div>
<section class="article-card" id="faq"><div class="faq-list"><details><summary>Question?</summary><p>Answer.</p></details></div></section>
<div class="related-grid"><article class="related-card"><h3>Related</h3><p>Useful.</p><a href="/related/">Read guide</a></article></div>
</article></main>
<footer class="site-footer">
<div class="footer-grid"><div class="footer-column footer-brand"><p class="footer-description">Independent reviews.</p></div>
<div class="footer-column"><ul class="footer-links"><li><a href="/reviews/">Reviews</a></li></ul></div>
<div class="footer-column"><ul class="footer-links"><li><a href="/about/">About</a></li></ul></div>
<div class="footer-column"><ul class="footer-links footer-social-links"><li><a href="https://example.com">LinkedIn</a></li></ul></div></div>
<div class="footer-bottom"><p>Copyright</p></div>
</footer></body></html>""",
                encoding="utf-8",
            )

            self.assertEqual(workflow._validate_single_html_file(page, scope="site_output"), [])

    def test_public_render_validator_rejects_broken_hero_image(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workflow = DailyEditorialWorkflow(root=root, data_dir=root / "data", site_output_dir=root / "site_output")
            page = root / "site_output" / "example" / "index.html"
            page.parent.mkdir(parents=True, exist_ok=True)
            page.write_text(
                _canonical_article_html("Broken").replace(
                    "<main class=\"article-layout\">",
                    '<main class="article-layout"><img class="article-hero-image" src="/assets/og/pages/missing.png" alt="Missing">',
                ),
                encoding="utf-8",
            )

            errors = workflow._validate_single_html_file(page, scope="site_output")

            self.assertTrue(any("hero image local path is missing" in error for error in errors))
            self.assertTrue(any("hero image must include width and height" in error for error in errors))

    def test_public_render_validator_accepts_valid_hero_image(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workflow = DailyEditorialWorkflow(root=root, data_dir=root / "data", site_output_dir=root / "site_output")
            image = root / "site_output" / "assets" / "og" / "pages" / "valid.png"
            image.parent.mkdir(parents=True, exist_ok=True)
            image.write_bytes(b"png")
            page = root / "site_output" / "example" / "index.html"
            page.parent.mkdir(parents=True, exist_ok=True)
            page.write_text(
                _canonical_article_html("Valid").replace(
                    "<main class=\"article-layout\">",
                    '<main class="article-layout"><img class="article-hero-image" src="/assets/og/pages/valid.png" width="1200" height="630" alt="Valid" loading="eager" decoding="async">',
                ),
                encoding="utf-8",
            )

            self.assertEqual(workflow._validate_single_html_file(page, scope="site_output"), [])

    def test_editorial_console_defaults_date_to_today(self) -> None:
        parser = build_parser()
        today = date.today().isoformat()

        for args in (
            ["trend"],
            ["morning"],
            ["morning", "--open"],
            ["draft"],
            ["approve", "--slug", "example-slug"],
            ["reject", "--slug", "example-slug", "--reason", "Needs fixes"],
            ["publish"],
            ["publish-ready"],
            ["validate-batch"],
            ["autofix-batch"],
            ["status"],
            ["check-live"],
            ["check-live", "--blocked-only"],
            ["open"],
            ["serve"],
        ):
            with self.subTest(args=args):
                parsed = parser.parse_args(args)
                self.assertEqual(parsed.date, today)

    def test_editorial_console_request_topic_parser(self) -> None:
        parser = build_parser()

        parsed = parser.parse_args(
            [
                "request-topic",
                "--topic",
                "UGCVideo AI review",
                "--category",
                "AI Video Tools",
                "--intent",
                "commercial research",
                "--source-url",
                "https://ugcvideo.ai",
                "--open",
            ]
        )

        self.assertEqual(parsed.command, "request-topic")
        self.assertEqual(parsed.topic, "UGCVideo AI review")
        self.assertEqual(parsed.category, "AI Video Tools")
        self.assertEqual(parsed.intent, "commercial research")
        self.assertEqual(parsed.source_url, "https://ugcvideo.ai")
        self.assertTrue(parsed.open)

    def test_publish_ready_cli_handles_no_ready_without_traceback(self) -> None:
        class FakeWorkflow:
            def set_progress_reporter(self, reporter):
                self.reporter = reporter

            def publish_ready(self, *, batch_date: str, validation_mode: str = "smart"):
                raise ValueError(f"No articles are ready for publish in batch {batch_date}. Blocked: one, two")

            def status(self, *, batch_date: str):
                return {
                    "date": batch_date,
                    "total_topics": 10,
                    "human_approved": 3,
                    "ready_for_publish": 0,
                    "publish_blocked": 7,
                    "top_block_reasons": [
                        "AI quality review required",
                        "Knowledge needs refresh",
                        "Need better verified sources",
                    ],
                }

        stdout = io.StringIO()
        with patch.object(EDITORIAL_CONSOLE_MODULE, "DailyEditorialWorkflow", return_value=FakeWorkflow()):
            with redirect_stdout(stdout):
                exit_code = editorial_console_main(["publish-ready", "--date", "2026-07-10"])

        output = stdout.getvalue()
        self.assertEqual(exit_code, 2)
        self.assertIn("[INFO] Hôm nay chưa có bài nào đủ điều kiện Ready for Publish.", output)
        self.assertIn("Batch 2026-07-10", output)
        self.assertIn("Human Approved: 3", output)
        self.assertIn("Ready for Publish: 0", output)
        self.assertIn("Publish Blocked: 7", output)
        self.assertIn("- AI quality review required", output)
        self.assertIn("Open menu 4 and review the blocked articles.", output)
        self.assertNotIn("Traceback", output)
        self.assertNotIn("git add", output)
        self.assertNotIn("git commit", output)
        self.assertNotIn("git push", output)

    def test_publish_ready_cli_reports_unexpected_errors_as_failures(self) -> None:
        class FakeWorkflow:
            def set_progress_reporter(self, reporter):
                self.reporter = reporter

            def publish_ready(self, *, batch_date: str, validation_mode: str = "smart"):
                raise RuntimeError("git push failed")

        stdout = io.StringIO()
        with patch.object(EDITORIAL_CONSOLE_MODULE, "DailyEditorialWorkflow", return_value=FakeWorkflow()):
            with redirect_stdout(stdout):
                exit_code = editorial_console_main(["publish-ready", "--date", "2026-07-10"])

        output = stdout.getvalue()
        self.assertEqual(exit_code, 1)
        self.assertIn("[ERROR] Publish-ready failed: git push failed", output)
        self.assertNotIn("[INFO] Hôm nay chưa có bài nào đủ điều kiện Ready for Publish.", output)

    def test_runbot_menu_handles_no_ready_exit_code_before_generic_failure(self) -> None:
        menu_text = (Path(__file__).resolve().parents[1] / "runbot_menu.bat").read_text(encoding="utf-8")

        today_publish = menu_text.index("python editorial_console.py publish-ready --validation-mode smart")
        today_no_ready = menu_text.index("if errorlevel 2 goto publish_no_ready_today", today_publish)
        today_failure = menu_text.index("if errorlevel 1 goto publish_failed_today", today_publish)
        custom_publish = menu_text.index("python editorial_console.py publish-ready --date %PUBLISH_DATE% --validation-mode smart")
        custom_no_ready = menu_text.index("if errorlevel 2 goto publish_no_ready_custom", custom_publish)
        custom_failure = menu_text.index("if errorlevel 1 goto publish_failed_custom", custom_publish)

        self.assertLess(today_no_ready, today_failure)
        self.assertLess(custom_no_ready, custom_failure)
        self.assertIn(":publish_no_ready_today", menu_text)
        self.assertIn(":publish_no_ready_custom", menu_text)

    def test_editorial_console_partner_intake_parser(self) -> None:
        parser = build_parser()

        parsed = parser.parse_args(
            [
                "partner-intake",
                "--name",
                "UGCVideo.ai",
                "--official-url",
                "https://ugcvideo.ai",
                "--affiliate-url",
                "https://ugcvideo.ai/affiliates",
                "--pricing-url",
                "https://ugcvideo.ai/pricing",
                "--contact-note",
                "Contacted via email",
                "--commission-note",
                "20% recurring",
                "--payout-note",
                "Monthly payout",
                "--count",
                "8",
                "--open",
            ]
        )

        self.assertEqual(parsed.command, "partner-intake")
        self.assertEqual(parsed.name, "UGCVideo.ai")
        self.assertEqual(parsed.official_url, "https://ugcvideo.ai")
        self.assertEqual(parsed.affiliate_url, "https://ugcvideo.ai/affiliates")
        self.assertEqual(parsed.pricing_url, "https://ugcvideo.ai/pricing")
        self.assertEqual(parsed.count, 8)
        self.assertTrue(parsed.open)

    def test_trend_saves_topics_json(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workflow = DailyEditorialWorkflow(root=root, data_dir=root / "data", site_output_dir=root / "site_output")
            candidate = SimpleNamespace(
                topic="best ai productivity software",
                slug="best-ai-productivity-software",
                search_intent="commercial research",
                affiliate_opportunity=84,
                competition=42,
                news_freshness=73,
                content_type="listicle",
                source_urls=["https://example.com/a"],
                suggested_internal_links=["/reviews/"],
                suggested_article_angle="Angle",
                why_selected=["Strong fit"],
                signals=3,
                confidence="high",
            )
            discovery = SimpleNamespace(selected_topics=[candidate], source_status={"local_keyword_intelligence": {"status": "ok", "signals": 1}})
            with patch("modules.daily_editorial_workflow.TrendDiscoveryEngine") as engine_cls:
                engine_cls.return_value.run.return_value = discovery
                with patch("modules.daily_editorial_workflow.load_affiliate_brands", return_value=frozenset({"notion", "gamma"})):
                    payload = workflow.trend(count=1, mode="standard", batch_date="2026-07-07")

            self.assertEqual(payload["count"], 1)
            self.assertEqual(payload["topics"][0]["status"], "selected")
            self.assertTrue((root / "data" / "editorial_queue" / "2026-07-07" / "topics.json").exists())
            self.assertTrue((root / "data" / "editorial_queue" / "weeks" / "2026-07-06" / "week.json").exists())
            self.assertEqual(payload.get("duplicate_warning_count"), 0)

    def test_trend_flags_near_duplicate_against_published_live_history(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            data_dir = root / "data"
            _write_json(root / "config" / "editorial_system.json", {"published_live_duplicate_guard": {"score_penalty": 4.0}})
            workflow = DailyEditorialWorkflow(root=root, data_dir=data_dir, site_output_dir=root / "site_output")
            history_path = data_dir / "published_live_urls.jsonl"
            history_path.parent.mkdir(parents=True, exist_ok=True)
            history_path.write_text(
                json.dumps(
                    {
                        "checked_at": "2026-07-07T00:00:00+00:00",
                        "slug": "best-ai-productivity-software",
                        "keyword": "best ai productivity software",
                        "title": "Best AI Productivity Software 2026",
                        "url": "https://smileaireviewhub.com/best-ai-productivity-software/",
                        "live_status": "live",
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            candidate = SimpleNamespace(
                topic="best ai productivity software 2026",
                slug="best-ai-productivity-software-2026",
                search_intent="commercial research",
                affiliate_opportunity=84,
                competition=42,
                news_freshness=73,
                content_type="listicle",
                source_urls=["https://example.com/a"],
                suggested_internal_links=["/reviews/"],
                suggested_article_angle="Angle",
                why_selected=["Strong fit"],
                signals=3,
                confidence="high",
            )
            discovery = SimpleNamespace(selected_topics=[candidate], source_status={"local_keyword_intelligence": {"status": "ok", "signals": 1}})
            with patch("modules.daily_editorial_workflow.TrendDiscoveryEngine") as engine_cls:
                engine_cls.return_value.run.return_value = discovery
                with patch("modules.daily_editorial_workflow.load_affiliate_brands", return_value=frozenset({"notion", "gamma"})):
                    payload = workflow.trend(count=1, mode="standard", batch_date="2026-07-07")

            topic = payload["topics"][0]
            self.assertEqual(payload.get("duplicate_warning_count"), 1)
            self.assertIn("Published-live duplicate warning", topic["published_live_duplicate_warning"])
            self.assertEqual(topic["published_live_duplicate_match"]["matched_slug"], "best-ai-productivity-software")
            self.assertEqual(topic["raw_total_score"], 73.7)
            self.assertEqual(topic["duplicate_penalty_applied"], 4.0)
            self.assertEqual(topic["total_score"], 69.7)
            saved_week = json.loads((data_dir / "editorial_queue" / "weeks" / "2026-07-06" / "week.json").read_text(encoding="utf-8"))
            self.assertEqual(saved_week["duplicate_warning_count"], 1)
            self.assertEqual(saved_week["duplicate_warning_slugs"], ["best-ai-productivity-software-2026"])

    def test_trend_deprioritizes_duplicate_topics_in_weekly_ranking(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            data_dir = root / "data"
            _write_json(root / "config" / "editorial_system.json", {"published_live_duplicate_guard": {"score_penalty": 4.0}})
            workflow = DailyEditorialWorkflow(root=root, data_dir=data_dir, site_output_dir=root / "site_output")
            data_dir.mkdir(parents=True, exist_ok=True)
            (data_dir / "published_live_urls.jsonl").write_text(
                json.dumps(
                    {
                        "checked_at": "2026-07-07T00:00:00+00:00",
                        "slug": "best-ai-productivity-software",
                        "keyword": "best ai productivity software",
                        "url": "https://smileaireviewhub.com/best-ai-productivity-software/",
                        "live_status": "live",
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            duplicate_candidate = SimpleNamespace(
                topic="best ai productivity software 2026",
                slug="best-ai-productivity-software-2026",
                search_intent="commercial research",
                affiliate_opportunity=84,
                competition=42,
                news_freshness=73,
                content_type="listicle",
                source_urls=[],
                suggested_internal_links=[],
                suggested_article_angle="Angle",
                why_selected=["Duplicate risk"],
                signals=3,
                confidence="high",
            )
            fresh_candidate = SimpleNamespace(
                topic="best ai team collaboration software",
                slug="best-ai-team-collaboration-software",
                search_intent="commercial research",
                affiliate_opportunity=84,
                competition=41,
                news_freshness=72,
                content_type="listicle",
                source_urls=[],
                suggested_internal_links=[],
                suggested_article_angle="Angle",
                why_selected=["Fresh opportunity"],
                signals=3,
                confidence="high",
            )
            discovery = SimpleNamespace(selected_topics=[duplicate_candidate, fresh_candidate], source_status={})
            with patch("modules.daily_editorial_workflow.TrendDiscoveryEngine") as engine_cls:
                engine_cls.return_value.run.return_value = discovery
                with patch("modules.daily_editorial_workflow.load_affiliate_brands", return_value=frozenset({"notion", "gamma"})):
                    payload = workflow.trend(count=2, mode="standard", batch_date="2026-07-07")

            self.assertEqual(payload["topics"][0]["slug"], "best-ai-team-collaboration-software")
            self.assertEqual(payload["topics"][1]["slug"], "best-ai-productivity-software-2026")
            self.assertEqual(payload["topics"][1]["duplicate_penalty_applied"], 4.0)

    def test_advanced_mode_expands_topics(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workflow = DailyEditorialWorkflow(root=root, data_dir=root / "data", site_output_dir=root / "site_output")
            candidate = SimpleNamespace(
                topic="notion",
                slug="notion",
                search_intent="commercial research",
                affiliate_opportunity=80,
                competition=35,
                news_freshness=70,
                content_type="review",
                source_urls=[],
                suggested_internal_links=[],
                suggested_article_angle="Angle",
                why_selected=["Strong fit"],
                signals=2,
                confidence="high",
            )
            discovery = SimpleNamespace(selected_topics=[candidate], source_status={})
            with patch("modules.daily_editorial_workflow.TrendDiscoveryEngine") as engine_cls:
                engine_cls.return_value.run.return_value = discovery
                with patch("modules.daily_editorial_workflow.load_affiliate_brands", return_value=frozenset({"notion"})):
                    workflow.trend(count=1, mode="standard", batch_date="2026-07-06")
                    payload = workflow.trend(count=1, mode="advanced", batch_date="2026-07-08")

            keywords = [item["keyword"] for item in payload["topics"]]
            self.assertTrue(any("alternatives" in keyword for keyword in keywords))
            self.assertEqual(payload["week_start"], "2026-07-06")

    def test_advanced_mode_does_not_duplicate_review_suffix(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workflow = DailyEditorialWorkflow(root=root, data_dir=root / "data", site_output_dir=root / "site_output")
            candidate = SimpleNamespace(
                topic="agent skills review 2026",
                slug="agent-skills-review-2026",
                search_intent="commercial research",
                affiliate_opportunity=80,
                competition=35,
                news_freshness=70,
                content_type="review",
                source_urls=[],
                suggested_internal_links=[],
                suggested_article_angle="Angle",
                why_selected=["Strong fit"],
                signals=2,
                confidence="high",
            )
            discovery = SimpleNamespace(selected_topics=[candidate], source_status={})
            with patch("modules.daily_editorial_workflow.TrendDiscoveryEngine") as engine_cls:
                engine_cls.return_value.run.return_value = discovery
                with patch("modules.daily_editorial_workflow.load_affiliate_brands", return_value=frozenset({"notion"})):
                    workflow.trend(count=1, mode="standard", batch_date="2026-07-06")
                    payload = workflow.trend(count=1, mode="advanced", batch_date="2026-07-12")

            keywords = [item["keyword"] for item in payload["topics"]]
            self.assertFalse(any("review 2026 review 2026" in keyword.lower() for keyword in keywords))

    def test_advanced_mode_reuses_existing_weekly_topics_without_new_discovery(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workflow = DailyEditorialWorkflow(root=root, data_dir=root / "data", site_output_dir=root / "site_output")
            weekly_manifest = {
                "generated_at": "2026-07-06T00:00:00+00:00",
                "week_start": "2026-07-06",
                "week_end": "2026-07-12",
                "count": 1,
                "source_status": {"local": {"status": "ok", "signals": 1}},
                "topics": [
                    {
                        "keyword": "best ai productivity software",
                        "slug": "best-ai-productivity-software",
                        "parent_keyword": "best ai productivity software",
                        "parent_slug": "best-ai-productivity-software",
                        "search_intent": "commercial research",
                        "search_intent_score": 90,
                        "affiliate_monetization_score": 84,
                        "competition_difficulty_score": 42,
                        "product_availability_score": 58,
                        "content_freshness_score": 73,
                        "content_type": "listicle",
                        "total_score": 88.5,
                        "rank": 1,
                    }
                ],
            }
            _write_json(root / "data" / "editorial_queue" / "weeks" / "2026-07-06" / "week.json", weekly_manifest)

            with patch("modules.daily_editorial_workflow.TrendDiscoveryEngine") as engine_cls:
                payload = workflow.trend(count=1, mode="advanced", batch_date="2026-07-09")

            engine_cls.assert_not_called()
            self.assertEqual(payload["topics"][0]["parent_slug"], "best-ai-productivity-software")
            self.assertIn("comparison", payload["topics"][0]["keyword"])

    def test_draft_generates_preview_and_updates_status(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            data_dir = root / "data"
            site_output = root / "site_output"
            workflow = DailyEditorialWorkflow(root=root, data_dir=data_dir, site_output_dir=site_output)
            _write_json(
                data_dir / "editorial_queue" / "2026-07-07" / "topics.json",
                {
                    "generated_at": "2026-07-07T00:00:00+00:00",
                    "date": "2026-07-07",
                    "mode": "standard",
                    "count": 1,
                    "topics": [
                        {
                            "keyword": "best ai productivity software",
                            "slug": "best-ai-productivity-software",
                            "search_intent": "commercial research",
                            "content_type": "listicle",
                            "total_score": 88.5,
                            "suggested_internal_links": ["/reviews/"],
                            "status": "selected",
                        }
                    ],
                },
            )
            draft_dir = data_dir / "production_article_drafts" / "best-ai-productivity-software"
            draft_dir.mkdir(parents=True, exist_ok=True)
            (draft_dir / "index.html").write_text("<html><body>Draft</body></html>", encoding="utf-8")
            metadata = {
                "title": "Best AI Productivity Software",
                "review": {"status": "needs_human_review"},
                "human_approval": {"status": "needs_human_review"},
                "publish_gate": {"status": "blocked"},
            }
            (draft_dir / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")

            class FakePlatform:
                def build_research_package(self, topic: dict):
                    return SimpleNamespace(package_dir=str(data_dir / "research" / topic["slug"]))

                def evaluate_quality_gate(self, package, topic: dict, allow_override: bool = False):
                    return SimpleNamespace(passed=True, score=81, threshold=60, override_used=False, status="passed")

            with patch("modules.daily_editorial_workflow.get_research_platform", return_value=FakePlatform()):
                with patch(
                    "modules.daily_editorial_workflow.generate_production_article_draft_from_package",
                    return_value={"draft_dir": str(draft_dir), "metadata_file": str(draft_dir / "metadata.json")},
                ):
                    result = workflow.draft(batch_date="2026-07-07")

            self.assertEqual(result["drafted"], 1)
            saved = json.loads((data_dir / "editorial_queue" / "2026-07-07" / "topics.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["topics"][0]["status"], "drafted")
            self.assertTrue((site_output / "review" / "2026-07-07" / "best-ai-productivity-software" / "index.html").exists())
            self.assertTrue((site_output / "review" / "2026-07-07" / "actions" / "publish-batch.cmd").exists())
            self.assertTrue((root / "upload" / "2026-07-07" / "review_dashboard.html").exists())
            self.assertTrue((root / "upload" / "2026-07-07" / "review" / "best-ai-productivity-software" / "index.html").exists())
            self.assertTrue((root / "upload" / "2026-07-07" / "drafts" / "best-ai-productivity-software" / "metadata.json").exists())

    def test_draft_ignores_old_public_html_validation_when_syncing_review_batch(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            data_dir = root / "data"
            site_output = root / "site_output"
            workflow = DailyEditorialWorkflow(root=root, data_dir=data_dir, site_output_dir=site_output)
            _write_json(
                data_dir / "editorial_queue" / "2026-07-07" / "topics.json",
                {
                    "generated_at": "2026-07-07T00:00:00+00:00",
                    "date": "2026-07-07",
                    "week_start": "2026-07-06",
                    "mode": "standard",
                    "count": 1,
                    "topics": [
                        {
                            "keyword": "best ai productivity software",
                            "slug": "best-ai-productivity-software",
                            "search_intent": "commercial research",
                            "content_type": "listicle",
                            "total_score": 88.5,
                            "status": "selected",
                        }
                    ],
                },
            )
            (site_output / "legacy-page").mkdir(parents=True, exist_ok=True)
            (site_output / "legacy-page" / "index.html").write_text("<html><body>Content planning snapshot</body></html>", encoding="utf-8")
            draft_dir = data_dir / "production_article_drafts" / "best-ai-productivity-software"
            draft_dir.mkdir(parents=True, exist_ok=True)
            (draft_dir / "index.html").write_text("<html><body>Draft</body></html>", encoding="utf-8")
            (draft_dir / "metadata.json").write_text(json.dumps({"title": "Best AI Productivity Software"}), encoding="utf-8")

            class FakePlatform:
                def build_research_package(self, topic: dict):
                    return SimpleNamespace(package_dir=str(data_dir / "research" / topic["slug"]))

                def evaluate_quality_gate(self, package, topic: dict, allow_override: bool = False):
                    return SimpleNamespace(passed=True, score=81, threshold=60, override_used=False, status="passed")

            with patch("modules.daily_editorial_workflow.get_research_platform", return_value=FakePlatform()):
                with patch(
                    "modules.daily_editorial_workflow.generate_production_article_draft_from_package",
                    return_value={"draft_dir": str(draft_dir), "metadata_file": str(draft_dir / "metadata.json")},
                ):
                    result = workflow.draft(batch_date="2026-07-07")

            self.assertEqual(result["drafted"], 1)

    def test_draft_allows_generation_override_from_config(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            data_dir = root / "data"
            site_output = root / "site_output"
            workflow = DailyEditorialWorkflow(root=root, data_dir=data_dir, site_output_dir=site_output)
            _write_json(
                data_dir / "editorial_queue" / "2026-07-07" / "topics.json",
                {
                    "generated_at": "2026-07-07T00:00:00+00:00",
                    "date": "2026-07-07",
                    "week_start": "2026-07-06",
                    "mode": "standard",
                    "count": 1,
                    "topics": [
                        {
                            "keyword": "best ai productivity software",
                            "slug": "best-ai-productivity-software",
                            "search_intent": "commercial research",
                            "content_type": "listicle",
                            "total_score": 88.5,
                            "status": "selected",
                        }
                    ],
                },
            )
            draft_dir = data_dir / "production_article_drafts" / "best-ai-productivity-software"
            draft_dir.mkdir(parents=True, exist_ok=True)
            (draft_dir / "index.html").write_text("<html><body>Draft</body></html>", encoding="utf-8")
            (draft_dir / "metadata.json").write_text(json.dumps({"title": "Best AI Productivity Software"}), encoding="utf-8")

            class FakePlatform:
                def build_research_package(self, topic: dict):
                    return SimpleNamespace(package_dir=str(data_dir / "research" / topic["slug"]))

                def evaluate_quality_gate(self, package, topic: dict, allow_override: bool = False):
                    self.allow_override = allow_override
                    return SimpleNamespace(passed=True, score=45.14, threshold=60.0, override_used=True, status="override_allowed")

            fake_platform = FakePlatform()
            with patch("modules.daily_editorial_workflow.get_research_platform", return_value=fake_platform):
                with patch(
                    "modules.daily_editorial_workflow.generate_production_article_draft_from_package",
                    return_value={"draft_dir": str(draft_dir), "metadata_file": str(draft_dir / "metadata.json")},
                ):
                    with patch("modules.daily_editorial_workflow.settings", SimpleNamespace(editorial_research_config={"allow_generation_override": True})):
                        result = workflow.draft(batch_date="2026-07-07")

            saved = json.loads((data_dir / "editorial_queue" / "2026-07-07" / "topics.json").read_text(encoding="utf-8"))
            self.assertEqual(result["drafted"], 1)
            self.assertEqual(saved["topics"][0]["status"], "drafted")
            self.assertEqual(saved["topics"][0]["research_quality_gate"]["status"], "override_allowed")
            self.assertTrue(saved["topics"][0]["research_quality_gate"]["override_used"])

    def test_morning_run_builds_dashboard_and_console_paths(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            data_dir = root / "data"
            site_output = root / "site_output"
            workflow = DailyEditorialWorkflow(root=root, data_dir=data_dir, site_output_dir=site_output)
            candidate = SimpleNamespace(
                topic="best ai productivity software",
                slug="best-ai-productivity-software",
                search_intent="commercial research",
                affiliate_opportunity=84,
                competition=42,
                news_freshness=73,
                content_type="listicle",
                source_urls=["https://example.com/a"],
                suggested_internal_links=["/reviews/"],
                suggested_article_angle="Angle",
                why_selected=["Strong fit"],
                signals=3,
                confidence="high",
            )
            discovery = SimpleNamespace(selected_topics=[candidate], source_status={"local_keyword_intelligence": {"status": "ok", "signals": 1}})
            draft_dir = data_dir / "production_article_drafts" / "best-ai-productivity-software"
            draft_dir.mkdir(parents=True, exist_ok=True)
            (draft_dir / "index.html").write_text("<html><body>Draft</body></html>", encoding="utf-8")
            (draft_dir / "metadata.json").write_text(
                json.dumps(
                    {
                        "title": "Best AI Productivity Software",
                        "review": {"status": "needs_human_review"},
                        "human_approval": {"status": "needs_human_review"},
                        "publish_gate": {"status": "blocked"},
                    }
                ),
                encoding="utf-8",
            )

            class FakePlatform:
                def build_research_package(self, topic: dict):
                    return SimpleNamespace(package_dir=str(data_dir / "research" / topic["slug"]))

                def evaluate_quality_gate(self, package, topic: dict, allow_override: bool = False):
                    return SimpleNamespace(passed=True, score=81, threshold=60, override_used=False, status="passed")

            with patch("modules.daily_editorial_workflow.TrendDiscoveryEngine") as engine_cls:
                engine_cls.return_value.run.return_value = discovery
                with patch("modules.daily_editorial_workflow.load_affiliate_brands", return_value=frozenset({"notion"})):
                    with patch("modules.daily_editorial_workflow.get_research_platform", return_value=FakePlatform()):
                        with patch(
                            "modules.daily_editorial_workflow.generate_production_article_draft_from_package",
                            return_value={"draft_dir": str(draft_dir), "metadata_file": str(draft_dir / "metadata.json")},
                        ):
                            result = workflow.morning_run(count=1, batch_date="2026-07-07")

            self.assertTrue(result["dashboard_file"].endswith("site_output\\review\\2026-07-07\\index.html"))
            self.assertIn("editorial_operations_console.html", result["operator_console"])
            self.assertIn("upload\\2026-07-07", result["upload_dir"])
            self.assertTrue((root / "upload" / "dashboard.html").exists())
            self.assertTrue((root / "upload" / "2026-07-07" / "open_dashboard.cmd").exists())
            self.assertTrue((root / "upload" / "2026-07-07" / "publish_approved.cmd").exists())
            self.assertTrue((root / "upload" / "2026-07-07" / "status.cmd").exists())
            html_text = (site_output / "review" / "2026-07-07" / "index.html").read_text(encoding="utf-8")
            self.assertIn("Publish Ready Articles", html_text)
            self.assertIn("Open Operator Console", html_text)
            self.assertIn("Upload:", html_text)
            self.assertIn("Weekly batch", html_text)
            self.assertIn("Today's angle", html_text)

    def test_morning_run_reuses_same_weekly_topics_for_followup_day(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            data_dir = root / "data"
            site_output = root / "site_output"
            workflow = DailyEditorialWorkflow(root=root, data_dir=data_dir, site_output_dir=site_output)
            candidate = SimpleNamespace(
                topic="best ai productivity software",
                slug="best-ai-productivity-software",
                search_intent="commercial research",
                affiliate_opportunity=84,
                competition=42,
                news_freshness=73,
                content_type="listicle",
                source_urls=["https://example.com/a"],
                suggested_internal_links=["/reviews/"],
                suggested_article_angle="Angle",
                why_selected=["Strong fit"],
                signals=3,
                confidence="high",
            )
            discovery = SimpleNamespace(selected_topics=[candidate], source_status={"local_keyword_intelligence": {"status": "ok", "signals": 1}})
            for slug in ("best-ai-productivity-software", "best-ai-productivity-software-comparison"):
                draft_dir = data_dir / "production_article_drafts" / slug
                draft_dir.mkdir(parents=True, exist_ok=True)
                (draft_dir / "index.html").write_text("<html><body>Draft</body></html>", encoding="utf-8")
                (draft_dir / "metadata.json").write_text(json.dumps({"title": slug}), encoding="utf-8")

            class FakePlatform:
                def build_research_package(self, topic: dict):
                    return SimpleNamespace(package_dir=str(data_dir / "research" / topic["slug"]))

                def evaluate_quality_gate(self, package, topic: dict, allow_override: bool = False):
                    return SimpleNamespace(passed=True, score=81, threshold=60, override_used=False, status="passed")

            with patch("modules.daily_editorial_workflow.TrendDiscoveryEngine") as engine_cls:
                engine_cls.return_value.run.return_value = discovery
                with patch("modules.daily_editorial_workflow.load_affiliate_brands", return_value=frozenset({"notion"})):
                    with patch("modules.daily_editorial_workflow.get_research_platform", return_value=FakePlatform()):
                        with patch(
                            "modules.daily_editorial_workflow.generate_production_article_draft_from_package",
                            side_effect=lambda slug: {"draft_dir": str(data_dir / "production_article_drafts" / slug), "metadata_file": str(data_dir / "production_article_drafts" / slug / "metadata.json")},
                        ):
                            monday = workflow.morning_run(count=1, mode="standard", batch_date="2026-07-06")
                            thursday = workflow.morning_run(count=1, mode="advanced", batch_date="2026-07-09")

            self.assertEqual(monday["trend"]["topics"][0]["slug"], "best-ai-productivity-software")
            self.assertEqual(thursday["trend"]["topics"][0]["parent_slug"], "best-ai-productivity-software")
            self.assertIn("comparison", thursday["trend"]["topics"][0]["keyword"])

    def test_approve_and_reject_update_batch_status(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            data_dir = root / "data"
            workflow = DailyEditorialWorkflow(root=root, data_dir=data_dir, site_output_dir=root / "site_output")
            _write_json(
                data_dir / "editorial_queue" / "2026-07-07" / "topics.json",
                {"generated_at": "", "date": "2026-07-07", "mode": "standard", "count": 1, "topics": [{"keyword": "best ai productivity software", "slug": "best-ai-productivity-software", "status": "drafted", "total_score": 80}]},
            )
            with patch.object(workflow.console, "approve_slug", return_value={"status": "ok"}):
                workflow.approve(slug="best-ai-productivity-software", batch_date="2026-07-07")
            saved = json.loads((data_dir / "editorial_queue" / "2026-07-07" / "topics.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["topics"][0]["status"], "approved")
            with patch.object(workflow.console, "reject_slug", return_value={"status": "ok"}):
                workflow.reject(slug="best-ai-productivity-software", batch_date="2026-07-07", reason="Needs fixes")
            saved = json.loads((data_dir / "editorial_queue" / "2026-07-07" / "topics.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["topics"][0]["status"], "rejected")

    def test_publish_requires_all_topics_approved(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            data_dir = root / "data"
            workflow = DailyEditorialWorkflow(root=root, data_dir=data_dir, site_output_dir=root / "site_output")
            _write_json(
                data_dir / "editorial_queue" / "2026-07-07" / "topics.json",
                {
                    "generated_at": "",
                    "date": "2026-07-07",
                    "mode": "standard",
                    "count": 2,
                    "topics": [
                        {"keyword": "one", "slug": "one", "status": "approved", "total_score": 80},
                        {"keyword": "two", "slug": "two", "status": "drafted", "total_score": 79},
                    ],
                },
            )
            with self.assertRaises(ValueError):
                workflow.publish(batch_date="2026-07-07")

    def test_publish_requires_publish_gate_ready(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            data_dir = root / "data"
            workflow = DailyEditorialWorkflow(root=root, data_dir=data_dir, site_output_dir=root / "site_output")
            _write_json(
                data_dir / "editorial_queue" / "2026-07-07" / "topics.json",
                {
                    "generated_at": "",
                    "date": "2026-07-07",
                    "mode": "standard",
                    "count": 1,
                    "topics": [{"keyword": "one", "slug": "one", "status": "approved", "total_score": 80}],
                },
            )
            _write_json(
                data_dir / "publish_queue.json",
                [{"slug": "one", "status": "blocked", "failures": ["AI review failed"]}],
            )

            with self.assertRaisesRegex(ValueError, "Publish gate is still blocking"):
                workflow.publish(batch_date="2026-07-07")

    def test_publish_writes_upload_published_copy_and_report(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            data_dir = root / "data"
            site_output = root / "site_output"
            workflow = DailyEditorialWorkflow(root=root, data_dir=data_dir, site_output_dir=site_output)
            _write_json(
                data_dir / "editorial_queue" / "2026-07-07" / "topics.json",
                {
                    "generated_at": "",
                    "date": "2026-07-07",
                    "mode": "standard",
                    "count": 1,
                    "topics": [{"keyword": "one", "slug": "one", "status": "approved", "total_score": 80}],
                },
            )
            _write_json(
                data_dir / "publish_queue.json",
                [{"slug": "one", "status": "approved_for_publish", "failures": []}],
            )

            with patch.object(workflow.console, "publish_slug", return_value={"site_file": str(site_output / "one" / "index.html"), "article_file": str(data_dir / "published_static_pages" / "one" / "index.html")}):
                (site_output / "one").mkdir(parents=True, exist_ok=True)
                (site_output / "one" / "index.html").write_text(_canonical_article_html("One"), encoding="utf-8")
                (data_dir / "published_static_pages" / "one").mkdir(parents=True, exist_ok=True)
                (data_dir / "published_static_pages" / "one" / "index.html").write_text(_canonical_article_html("One"), encoding="utf-8")
                with patch("modules.daily_editorial_workflow.incremental_build", return_value="ok"):
                    with patch.object(
                        workflow,
                        "_run_command",
                        side_effect=[
                            {"returncode": 0, "stdout": "", "stderr": ""},
                            {"returncode": 0, "stdout": "", "stderr": ""},
                            {"returncode": 0, "stdout": "", "stderr": ""},
                            {"returncode": 0, "stdout": "", "stderr": ""},
                            {"returncode": 0, "stdout": "", "stderr": ""},
                        ],
                    ):
                        with patch.object(
                            workflow,
                            "_verify_live_after_push",
                            return_value={"status": "pages_pending", "message": "GitHub push OK but Pages chua cap nhat", "attempts": [], "items": [{"slug": "one", "url": "https://smileaireviewhub.com/one/", "status": "404", "http_status": 404, "reason": "not found"}]},
                        ):
                            result = workflow.publish(batch_date="2026-07-07")

            self.assertEqual(result["published"][0]["slug"], "one")
            self.assertEqual(result["sync_docs"]["returncode"], 0)
            self.assertEqual(result["post_push_live_check"]["status"], "pages_pending")
            self.assertIn("live_url_history", result)
            self.assertTrue((data_dir / "published_live_urls.jsonl").exists())
            self.assertTrue((data_dir / "published_live_urls_latest.json").exists())
            self.assertTrue((root / "upload" / "2026-07-07" / "published" / "one" / "index.html").exists())
            self.assertTrue((root / "upload" / "2026-07-07" / "publish_report.md").exists())

    def test_publish_ready_only_publishes_gate_ready_rows(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            data_dir = root / "data"
            site_output = root / "site_output"
            workflow = DailyEditorialWorkflow(root=root, data_dir=data_dir, site_output_dir=site_output)
            _write_json(
                data_dir / "editorial_queue" / "2026-07-07" / "topics.json",
                {
                    "generated_at": "",
                    "date": "2026-07-07",
                    "mode": "standard",
                    "count": 2,
                    "topics": [
                        {"keyword": "one", "slug": "one", "status": "approved", "total_score": 80},
                        {"keyword": "two", "slug": "two", "status": "approved", "total_score": 79},
                    ],
                },
            )
            _write_json(
                data_dir / "publish_queue.json",
                [
                    {"slug": "one", "status": "approved_for_publish", "failures": []},
                    {"slug": "two", "status": "blocked", "failures": ["AI review failed"]},
                ],
            )

            with patch.object(workflow.console, "publish_slug", return_value={"site_file": str(site_output / "one" / "index.html"), "article_file": str(data_dir / "published_static_pages" / "one" / "index.html")}):
                (site_output / "one").mkdir(parents=True, exist_ok=True)
                (site_output / "one" / "index.html").write_text(_canonical_article_html("One"), encoding="utf-8")
                (data_dir / "published_static_pages" / "one").mkdir(parents=True, exist_ok=True)
                (data_dir / "published_static_pages" / "one" / "index.html").write_text(_canonical_article_html("One"), encoding="utf-8")
                with patch("modules.daily_editorial_workflow.incremental_build", return_value="ok"):
                    with patch.object(
                        workflow,
                        "_run_command",
                        side_effect=[
                            {"returncode": 0, "stdout": "", "stderr": ""},
                            {"returncode": 0, "stdout": "", "stderr": ""},
                            {"returncode": 0, "stdout": "", "stderr": ""},
                            {"returncode": 0, "stdout": "", "stderr": ""},
                            {"returncode": 0, "stdout": "", "stderr": ""},
                        ],
                    ):
                        with patch.object(
                            workflow,
                            "_verify_live_after_push",
                            return_value={"status": "live_ok", "message": "Website live OK", "attempts": [], "items": [{"slug": "one", "url": "https://smileaireviewhub.com/one/", "status": "live", "http_status": 200, "reason": "reachable"}]},
                        ):
                            result = workflow.publish_ready(batch_date="2026-07-07")

            self.assertEqual(result["published_count"], 1)
            self.assertEqual(result["published"][0]["slug"], "one")
            self.assertEqual(result["skipped_count"], 1)
            self.assertEqual(result["skipped"][0]["slug"], "two")
            self.assertEqual(result["sync_docs"]["returncode"], 0)
            self.assertEqual(result["post_push_live_check"]["status"], "live_ok")
            self.assertIn("live_url_history", result)
            self.assertTrue((data_dir / "published_live_urls.jsonl").exists())

    def test_autofix_batch_repairs_meta_cta_faq_and_markers(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            data_dir = root / "data"
            site_output = root / "site_output"
            workflow = DailyEditorialWorkflow(root=root, data_dir=data_dir, site_output_dir=site_output)
            slug = "one"
            _write_json(
                data_dir / "editorial_queue" / "2026-07-07" / "topics.json",
                {
                    "generated_at": "",
                    "date": "2026-07-07",
                    "mode": "standard",
                    "count": 1,
                    "topics": [{"keyword": "one", "slug": slug, "status": "approved", "total_score": 80}],
                },
            )
            _write_json(data_dir / "publish_queue.json", [{"slug": slug, "status": "published_local", "failures": []}])
            for base in (data_dir / "published_static_pages", site_output, root / "docs"):
                target = base / slug
                target.mkdir(parents=True, exist_ok=True)
                (target / "index.html").write_text(
                    "<html><head><title>One</title></head><body>"
                    "<section>Research package snapshot</section>"
                    "<p><a class='btn' href='https://www.notion.com'>Go now</a></p>"
                    "<details><summary>What is One?</summary><p>One is a tool.</p></details>"
                    "{{AFFILIATE_LINK}}"
                    "</body></html>",
                    encoding="utf-8",
                )
            result = workflow.autofix_batch(batch_date="2026-07-07")
            html_text = (root / "docs" / slug / "index.html").read_text(encoding="utf-8")
            self.assertGreater(result["total_auto_fixed"], 0)
            self.assertIn('meta name="description"', html_text)
            self.assertIn("Visit official website", html_text)
            self.assertIn("FAQPage", html_text)
            self.assertNotIn("Research package snapshot", html_text)
            self.assertNotIn("{{", html_text)

    def test_validate_batch_smart_skips_only_failing_article(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            data_dir = root / "data"
            site_output = root / "site_output"
            workflow = DailyEditorialWorkflow(root=root, data_dir=data_dir, site_output_dir=site_output)
            topics = []
            publish_rows = []
            for slug, broken in (("good", False), ("bad", True)):
                topics.append({"keyword": slug, "slug": slug, "status": "approved", "total_score": 80})
                publish_rows.append({"slug": slug, "status": "published_local", "failures": []})
                for base in (data_dir / "published_static_pages", site_output, root / "docs"):
                    target = base / slug
                    target.mkdir(parents=True, exist_ok=True)
                    html_text = _canonical_article_html("Good")
                    (target / "index.html").write_text(html_text, encoding="utf-8")
                if broken:
                    (site_output / slug / "index.html").unlink()
            _write_json(
                data_dir / "editorial_queue" / "2026-07-07" / "topics.json",
                {"generated_at": "", "date": "2026-07-07", "mode": "standard", "count": 2, "topics": topics},
            )
            _write_json(data_dir / "publish_queue.json", publish_rows)
            report = workflow.validate_batch(batch_date="2026-07-07", mode="smart")
            self.assertEqual(report["total_published"], 1)
            self.assertEqual(report["total_skipped"], 1)
            self.assertEqual(report["published"][0]["slug"], "good")
            self.assertEqual(report["skipped"][0]["slug"], "bad")

    def test_prepare_article_output_builds_ready_article_missing_output_only(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            data_dir = root / "data"
            site_output = root / "site_output"
            workflow = DailyEditorialWorkflow(root=root, data_dir=data_dir, site_output_dir=site_output)
            target_slug = "best-agent-skills-review-2026-for-small-business"
            other_slug = "other-ready-article"
            _write_json(
                data_dir / "editorial_queue" / "2026-07-11" / "topics.json",
                {
                    "generated_at": "",
                    "date": "2026-07-11",
                    "mode": "standard",
                    "count": 2,
                    "topics": [
                        {"keyword": "Best Agent Skills Review 2026", "slug": target_slug, "status": "approved", "total_score": 90},
                        {"keyword": "Other Ready Article", "slug": other_slug, "status": "approved", "total_score": 91},
                    ],
                },
            )
            _write_json(
                data_dir / "publish_queue.json",
                [
                    {"slug": target_slug, "status": "approved_for_publish", "failures": [], "hard_blockers": [], "url": f"https://smileaireviewhub.com/{target_slug}/"},
                    {"slug": other_slug, "status": "approved_for_publish", "failures": [], "hard_blockers": [], "url": f"https://smileaireviewhub.com/{other_slug}/"},
                ],
            )
            for slug in (target_slug, other_slug):
                draft_dir = data_dir / "production_article_drafts" / slug
                draft_dir.mkdir(parents=True, exist_ok=True)
                (draft_dir / "index.html").write_text(_canonical_article_html(slug), encoding="utf-8")
                _write_json(draft_dir / "metadata.json", {"slug": slug, "title": slug, "url": f"https://smileaireviewhub.com/{slug}/"})

            result = workflow.prepare_article_output(batch_date="2026-07-11", slug=target_slug)

            self.assertEqual(result["status"], "prepared")
            for base in (data_dir / "published_static_pages", site_output, root / "docs"):
                self.assertTrue((base / target_slug / "index.html").exists())
                self.assertFalse((base / other_slug / "index.html").exists())
            self.assertTrue((root / "upload" / "2026-07-11" / "published" / target_slug / "index.html").exists())
            publish_rows = _read_json_for_test(data_dir / "publish_queue.json")
            self.assertEqual(publish_rows[0]["status"], "approved_for_publish")
            self.assertEqual(publish_rows[1]["status"], "approved_for_publish")

    def test_publish_dry_run_builds_missing_output_and_does_not_commit_or_push(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            data_dir = root / "data"
            site_output = root / "site_output"
            workflow = DailyEditorialWorkflow(root=root, data_dir=data_dir, site_output_dir=site_output)
            slug = "best-agent-skills-review-2026-for-small-business"
            _write_json(
                data_dir / "editorial_queue" / "2026-07-11" / "topics.json",
                {"generated_at": "", "date": "2026-07-11", "mode": "standard", "count": 1, "topics": [{"keyword": "Best Agent Skills Review 2026", "slug": slug, "status": "approved", "total_score": 90}]},
            )
            _write_json(
                data_dir / "publish_queue.json",
                [{"slug": slug, "status": "approved_for_publish", "failures": [], "hard_blockers": [], "url": f"https://smileaireviewhub.com/{slug}/"}],
            )
            draft_dir = data_dir / "production_article_drafts" / slug
            draft_dir.mkdir(parents=True, exist_ok=True)
            (draft_dir / "index.html").write_text(_canonical_article_html("Best Agent Skills Review 2026"), encoding="utf-8")
            _write_json(draft_dir / "metadata.json", {"slug": slug, "title": "Best Agent Skills Review 2026", "url": f"https://smileaireviewhub.com/{slug}/"})

            with patch.object(workflow, "_run_command", side_effect=AssertionError("git command should not run in dry-run")):
                result = workflow.publish_dry_run(batch_date="2026-07-11", slug=slug, validation_mode="smart")

            self.assertTrue(result["dry_run"])
            self.assertEqual(result["git_actions"]["commit"], "skipped_dry_run")
            self.assertEqual(result["git_actions"]["push"], "skipped_dry_run")
            self.assertEqual(result["publish_gate_result"]["status"], "approved_for_publish")
            self.assertEqual(result["validation_result"]["total_published"], 1)
            self.assertIn(f"site_output/{slug}", result["would_stage"])
            self.assertIn(f"docs/{slug}", result["would_stage"])
            self.assertTrue((site_output / slug / "index.html").exists())
            self.assertTrue((root / "docs" / slug / "index.html").exists())
            publish_rows = _read_json_for_test(data_dir / "publish_queue.json")
            self.assertEqual(publish_rows[0]["status"], "approved_for_publish")

    def test_publish_report_accepts_targeted_validation_candidate_paths(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workflow = DailyEditorialWorkflow(root=root, data_dir=root / "data", site_output_dir=root / "site_output")
            slug = "best-agent-skills-review-2026-for-small-business"

            report = workflow._write_publish_report(
                batch_date="2026-07-11",
                published=[
                    {
                        "slug": slug,
                        "paths": {
                            "site_output": str(root / "site_output" / slug / "index.html"),
                            "published_static": str(root / "data" / "published_static_pages" / slug / "index.html"),
                        },
                    }
                ],
                skipped=[],
                validation={"mode": "smart", "total_published": 1, "total_skipped": 0},
                build_result={"status": "targeted_no_full_rebuild"},
                post_push_live_check={"status": "not_run", "message": "", "attempts": [], "items": []},
            )

            report_text = report.read_text(encoding="utf-8")
            self.assertIn("site_output", report_text)
            self.assertIn("published_static_pages", report_text)

    def test_check_live_reports_local_docs_git_and_live_status(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            data_dir = root / "data"
            site_output = root / "site_output"
            docs_dir = root / "docs"
            workflow = DailyEditorialWorkflow(root=root, data_dir=data_dir, site_output_dir=site_output)
            slug = "best-ai-productivity-software"
            _write_json(
                data_dir / "editorial_queue" / "2026-07-07" / "topics.json",
                {
                    "generated_at": "",
                    "date": "2026-07-07",
                    "mode": "standard",
                    "count": 1,
                    "topics": [{"keyword": "best ai productivity software", "slug": slug, "status": "published", "total_score": 88.5}],
                },
            )
            _write_json(
                data_dir / "publish_queue.json",
                [{"slug": slug, "status": "published_local", "url": "https://smileaireviewhub.com/best-ai-productivity-software/"}],
            )
            draft_dir = data_dir / "production_article_drafts" / slug
            draft_dir.mkdir(parents=True, exist_ok=True)
            (draft_dir / "metadata.json").write_text(
                json.dumps({"slug": slug, "title": "Best AI Productivity Software", "url": "https://smileaireviewhub.com/best-ai-productivity-software/"}),
                encoding="utf-8",
            )
            (site_output / slug).mkdir(parents=True, exist_ok=True)
            (site_output / slug / "index.html").write_text("<html><body>Published</body></html>", encoding="utf-8")
            (docs_dir / slug).mkdir(parents=True, exist_ok=True)
            (docs_dir / slug / "index.html").write_text("<html><body>Published</body></html>", encoding="utf-8")

            git_results = [
                {"returncode": 0, "stdout": "", "stderr": ""},
                {"returncode": 0, "stdout": "abc123\n", "stderr": ""},
                {"returncode": 0, "stdout": "", "stderr": ""},
                {"returncode": 0, "stdout": "0 0\n", "stderr": ""},
            ]
            with patch.object(workflow, "_run_command", side_effect=git_results):
                with patch.object(workflow, "_probe_live_url", return_value={"status": "404", "http_status": 404, "reason": "HTTP Error 404"}):
                    report = workflow.check_live(batch_date="2026-07-07")

            self.assertEqual(report["summary"]["total_items"], 1)
            self.assertEqual(report["items"][0]["local_status"], "docs_synced")
            self.assertEqual(report["items"][0]["git_status"], "pushed")
            self.assertEqual(report["items"][0]["live_status"], "404")
            self.assertEqual(report["items"][0]["display_status"], "Unexpected Live 404")
            self.assertIn("Live 404", report["items"][0]["block_reason"])
            self.assertIn("check-live", report["items"][0]["next_action_command"])
            self.assertTrue((data_dir / "live_status_report.json").exists())
            self.assertTrue((data_dir / "live_status_report.md").exists())
            self.assertTrue((data_dir / "live_status_report.html").exists())

    def test_check_live_reports_block_reason_for_blocked_queue_items(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            data_dir = root / "data"
            workflow = DailyEditorialWorkflow(root=root, data_dir=data_dir, site_output_dir=root / "site_output")
            _write_json(
                data_dir / "editorial_queue" / "2026-07-07" / "topics.json",
                {
                    "generated_at": "",
                    "date": "2026-07-07",
                    "mode": "standard",
                    "count": 1,
                    "topics": [{"keyword": "agent skills review 2026", "slug": "agent-skills-review-2026", "status": "selected", "total_score": 61}],
                },
            )
            _write_json(
                data_dir / "publish_queue.json",
                [{"slug": "agent-skills-review-2026", "status": "blocked", "failures": ["affiliate disclosure missing", "verified source score too low"]}],
            )

            with patch.object(workflow, "_probe_live_url", return_value={"status": "404", "http_status": 404, "reason": "HTTP Error 404"}):
                report = workflow.check_live(batch_date="2026-07-07")

            item = report["items"][0]
            self.assertEqual(item["display_status"], "Missing Local Output")
            self.assertIn("Publish Blocked", item["block_reason"])
            self.assertIn("affiliate disclosure missing", item["block_reason"])
            self.assertIn("Need better verified sources", item["block_reason"])
            self.assertIn("Recommended Action", item["resolution"])
            self.assertIn("serve --date 2026-07-07 --open", item["next_action_command"])

    def test_check_live_blocked_only_filters_non_blocked_items(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            data_dir = root / "data"
            workflow = DailyEditorialWorkflow(root=root, data_dir=data_dir, site_output_dir=root / "site_output")
            _write_json(
                data_dir / "editorial_queue" / "2026-07-07" / "topics.json",
                {
                    "generated_at": "",
                    "date": "2026-07-07",
                    "mode": "standard",
                    "count": 2,
                    "topics": [
                        {"keyword": "one", "slug": "one", "status": "selected", "total_score": 61},
                        {"keyword": "two", "slug": "two", "status": "selected", "total_score": 60},
                    ],
                },
            )
            _write_json(
                data_dir / "publish_queue.json",
                [
                    {"slug": "one", "status": "blocked", "failures": ["affiliate disclosure missing"]},
                    {"slug": "two", "status": "published_local", "failures": []},
                ],
            )

            with patch.object(workflow, "_probe_live_url", return_value={"status": "404", "http_status": 404, "reason": "HTTP Error 404"}):
                report = workflow.check_live(batch_date="2026-07-07", blocked_only=True)

            self.assertTrue(report["summary"]["blocked_only"])
            self.assertEqual(report["summary"]["total_items"], 1)
            self.assertEqual(report["items"][0]["slug"], "one")

    def test_verify_live_after_push_reports_live_ok(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workflow = DailyEditorialWorkflow(root=root, data_dir=root / "data", site_output_dir=root / "site_output")
            workflow.post_push_live_waits = (0,)
            workflow.sleep_fn = lambda _: None

            with patch.object(workflow, "_probe_live_url", return_value={"status": "live", "http_status": 200, "reason": "reachable"}):
                result = workflow._verify_live_after_push(
                    [{"slug": "one", "url": "https://smileaireviewhub.com/one/"}]
                )

            self.assertEqual(result["status"], "live_ok")
            self.assertIn("Website live OK", result["message"])

    def test_verify_live_after_push_reports_pages_pending(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workflow = DailyEditorialWorkflow(root=root, data_dir=root / "data", site_output_dir=root / "site_output")
            workflow.post_push_live_waits = (0, 0)
            workflow.sleep_fn = lambda _: None

            with patch.object(workflow, "_probe_live_url", return_value={"status": "404", "http_status": 404, "reason": "not found"}):
                result = workflow._verify_live_after_push(
                    [{"slug": "one", "url": "https://smileaireviewhub.com/one/"}]
                )

            self.assertEqual(result["status"], "pages_pending")
            self.assertIn("Pages", result["message"])

    def test_render_interactive_dashboard_contains_preview_and_actions(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            data_dir = root / "data"
            site_output = root / "site_output"
            workflow = DailyEditorialWorkflow(root=root, data_dir=data_dir, site_output_dir=site_output)
            draft_dir = data_dir / "production_article_drafts" / "one"
            draft_dir.mkdir(parents=True, exist_ok=True)
            (draft_dir / "index.html").write_text("<html><body>Draft</body></html>", encoding="utf-8")
            _write_json(
                data_dir / "editorial_queue" / "2026-07-07" / "topics.json",
                {
                    "generated_at": "",
                    "date": "2026-07-07",
                    "mode": "standard",
                    "count": 1,
                    "topics": [{"keyword": "one", "slug": "one", "status": "drafted", "total_score": 80}],
                },
            )

            html_text = workflow.render_interactive_dashboard(batch_date="2026-07-07", selected_slug="one")

            self.assertIn('/preview?date=2026-07-07&amp;slug=one', html_text)
            self.assertIn('action="/approve"', html_text)
            self.assertIn('action="/reject"', html_text)
            self.assertIn('action="/publish"', html_text)
            self.assertIn("preview-frame", html_text)
            self.assertIn("Ready for Publish", html_text)
            self.assertIn("Top block reasons", html_text)
            self.assertIn("Main block reason", html_text)
            self.assertIn("data-filter", html_text)
            self.assertIn("Editorial status", html_text)
            self.assertIn("Publish gate", html_text)
            self.assertIn("Deployment", html_text)
            self.assertIn('method="post"', html_text)

    def test_render_interactive_dashboard_blocks_preview_for_needs_enrichment(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            data_dir = root / "data"
            site_output = root / "site_output"
            workflow = DailyEditorialWorkflow(root=root, data_dir=data_dir, site_output_dir=site_output)
            _write_json(
                data_dir / "editorial_queue" / "2026-07-07" / "topics.json",
                {
                    "generated_at": "",
                    "date": "2026-07-07",
                    "mode": "standard",
                    "count": 1,
                    "topics": [
                        {
                            "keyword": "blocked topic",
                            "slug": "blocked-topic",
                            "status": "needs_enrichment",
                            "total_score": 61,
                            "error": "Research quality gate blocked draft generation: 42 < 60",
                        }
                    ],
                },
            )

            html_text = workflow.render_interactive_dashboard(batch_date="2026-07-07", selected_slug="blocked-topic")

            self.assertIn("No draft preview yet.", html_text)
            self.assertIn("Research quality gate blocked draft generation", html_text)
            self.assertIn("disabled", html_text)

    def test_status_counts_current_batch_without_live_200_as_published(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            data_dir = root / "data"
            workflow = DailyEditorialWorkflow(root=root, data_dir=data_dir, site_output_dir=root / "site_output")
            _write_json(
                data_dir / "editorial_queue" / "2026-07-07" / "topics.json",
                {
                    "generated_at": "",
                    "date": "2026-07-07",
                    "mode": "standard",
                    "count": 4,
                    "topics": [
                        {"keyword": "draft", "slug": "draft", "status": "selected"},
                        {"keyword": "review", "slug": "review", "status": "drafted", "review_preview": str(data_dir / "production_article_drafts" / "review" / "index.html")},
                        {"keyword": "approved", "slug": "approved", "status": "approved"},
                        {"keyword": "old live", "slug": "old-live", "status": "drafted"},
                    ],
                },
            )
            (data_dir / "production_article_drafts" / "review").mkdir(parents=True, exist_ok=True)
            (data_dir / "production_article_drafts" / "review" / "index.html").write_text("<html></html>", encoding="utf-8")
            _write_json(
                data_dir / "publish_queue.json",
                [
                    {"slug": "approved", "status": "approved_for_publish", "failures": []},
                    {"slug": "old-live", "status": "blocked", "failures": ["AI review failed"], "url": "https://example.com/old-live/"},
                ],
            )

            summary = workflow.status(batch_date="2026-07-07")

            self.assertEqual(summary["total_topics"], 4)
            self.assertEqual(summary["drafts"], 2)
            self.assertEqual(summary["needs_review"], 1)
            self.assertEqual(summary["human_approved"], 1)
            self.assertEqual(summary["ready_for_publish"], 1)
            self.assertEqual(summary["publish_blocked"], 0)
            self.assertEqual(summary["human_approval_required"], 1)
            self.assertEqual(summary["published_this_batch"], 0)

    def test_live_200_blocked_article_is_not_counted_as_unpublished_error(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            data_dir = root / "data"
            workflow = DailyEditorialWorkflow(root=root, data_dir=data_dir, site_output_dir=root / "site_output")
            _write_json(
                data_dir / "editorial_queue" / "2026-07-07" / "topics.json",
                {
                    "generated_at": "",
                    "date": "2026-07-07",
                    "mode": "standard",
                    "count": 1,
                    "topics": [{"keyword": "old live", "slug": "old-live", "status": "drafted"}],
                },
            )
            _write_json(
                data_dir / "publish_queue.json",
                [{"slug": "old-live", "status": "blocked", "failures": ["AI review failed"], "url": "https://example.com/old-live/"}],
            )

            with patch.object(workflow, "_probe_live_url", return_value={"status": "live", "http_status": 200, "reason": "reachable"}):
                report = workflow.check_live(batch_date="2026-07-07")

            self.assertEqual(report["items"][0]["display_status"], "Live 200")
            self.assertEqual(report["summary"]["live_200"], 1)
            self.assertEqual(report["summary"]["unexpected_live_404"], 0)

    def test_draft_404_is_not_unexpected_live_404(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            data_dir = root / "data"
            workflow = DailyEditorialWorkflow(root=root, data_dir=data_dir, site_output_dir=root / "site_output")
            _write_json(
                data_dir / "editorial_queue" / "2026-07-07" / "topics.json",
                {
                    "generated_at": "",
                    "date": "2026-07-07",
                    "mode": "standard",
                    "count": 1,
                    "topics": [{"keyword": "draft", "slug": "draft", "status": "selected"}],
                },
            )
            _write_json(data_dir / "publish_queue.json", [{"slug": "draft", "status": "missing", "url": "https://example.com/draft/"}])

            with patch.object(workflow, "_probe_live_url", return_value={"status": "404", "http_status": 404, "reason": "HTTP Error 404"}):
                report = workflow.check_live(batch_date="2026-07-07")

            self.assertNotEqual(report["items"][0]["display_status"], "Unexpected Live 404")
            self.assertEqual(report["summary"]["unexpected_live_404"], 0)

    def test_already_approved_detail_does_not_show_active_approve_button(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            data_dir = root / "data"
            workflow = DailyEditorialWorkflow(root=root, data_dir=data_dir, site_output_dir=root / "site_output")
            draft_dir = data_dir / "production_article_drafts" / "approved"
            draft_dir.mkdir(parents=True, exist_ok=True)
            (draft_dir / "index.html").write_text("<html><body>Draft</body></html>", encoding="utf-8")
            _write_json(
                data_dir / "editorial_queue" / "2026-07-07" / "topics.json",
                {
                    "generated_at": "",
                    "date": "2026-07-07",
                    "mode": "standard",
                    "count": 1,
                    "topics": [{"keyword": "approved", "slug": "approved", "status": "approved", "review_preview": str(draft_dir / "index.html")}],
                },
            )
            _write_json(data_dir / "publish_queue.json", [{"slug": "approved", "status": "approved_for_publish", "failures": []}])

            html_text = workflow.render_interactive_dashboard(batch_date="2026-07-07", selected_slug="approved")

            self.assertIn(">Approved</span>", html_text)
            self.assertNotIn(">Approve</button>", html_text)


if __name__ == "__main__":
    unittest.main()
