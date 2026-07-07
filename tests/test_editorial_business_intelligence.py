from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from modules.editorial_business_intelligence import ContentLifecycleManager, EditorialBusinessIntelligence


def write_page(root: Path, slug: str, html: str) -> None:
    path = root / slug / "index.html"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")


def sample_html(*, title: str, date_published: str, date_modified: str, disclosure: bool = True, cta: bool = True, schema: bool = True, links: list[str] | None = None) -> str:
    links = links or ["/reviews/", "/comparisons/", "/pricing/cursor/"]
    schema_block = (
        f'<script type="application/ld+json">{{"@context":"https://schema.org","@type":"Article","headline":"{title}","datePublished":"{date_published}","dateModified":"{date_modified}"}}</script>'
        if schema
        else ""
    )
    disclosure_block = "<p>Some links may be affiliate links. Read the affiliate disclosure.</p>" if disclosure else ""
    cta_block = "<p><a href='/go/cursor/'>Visit Official Website</a></p>" if cta else ""
    links_html = "".join(f"<a href='{href}'>Link</a>" for href in links)
    body = " ".join(["Useful article copy."] * 220)
    return f"""
    <html>
      <head>
        <title>{title}</title>
        <meta name="description" content="{title} description">
        {schema_block}
      </head>
      <body>
        <h1>{title}</h1>
        {disclosure_block}
        {cta_block}
        <p>{body}</p>
        {links_html}
      </body>
    </html>
    """


class EditorialBusinessIntelligenceTests(unittest.TestCase):
    def test_reports_and_dashboard_are_generated(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            data_dir = root / "data"
            site_output = root / "site_output"
            offers_file = data_dir / "offers.csv"
            affiliate_links_file = data_dir / "affiliate_links.csv"
            report_dir = data_dir / "content_growth_reports"
            report_dir.mkdir(parents=True, exist_ok=True)

            offers_file.write_text(
                "\n".join(
                    [
                        "offer_id,brand_name,website,affiliate_url,niche,commission_type,commission_rate,flat_commission,cookie_days,recurring,traffic_policy,direct_linking_allowed,brand_bidding_allowed,vendor_trust,buyer_intent,notes",
                        "cursor,Cursor,https://cursor.com,https://cursor.com/aff,AI Coding,recurring,25,0,30,True,allowed,False,False,88,84,fixture",
                        "surfer-seo,Surfer SEO,https://surferseo.com,https://surferseo.com/aff,SEO,recurring,25,0,60,True,allowed,False,False,86,82,fixture",
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

            write_page(site_output, "reviews", "<html><body><h1>Reviews</h1></body></html>")
            write_page(site_output, "comparisons", "<html><body><h1>Comparisons</h1></body></html>")
            write_page(site_output, "pricing/cursor", "<html><body><h1>Cursor Pricing</h1></body></html>")
            write_page(site_output, "go/cursor", "<html><body><h1>Cursor Redirect</h1></body></html>")
            write_page(
                site_output,
                "cursor-review-2026",
                sample_html(title="Cursor Review 2026", date_published="2026-06-20", date_modified="2026-07-01"),
            )
            write_page(
                site_output,
                "legacy-seo-pricing-2024",
                sample_html(
                    title="Legacy SEO Pricing 2024",
                    date_published="2024-01-10",
                    date_modified="2024-01-10",
                    disclosure=False,
                    cta=False,
                    schema=False,
                    links=["/missing-page/"],
                ),
            )

            validation_report = {
                "generated_at": "2026-07-07T10:00:00+00:00",
                "pages_generated": 2,
                "errors": [],
                "page_validations": [
                    {"slug": "cursor-review-2026"},
                    {"slug": "legacy-seo-pricing-2024"},
                ],
            }
            (report_dir / "production-pipeline-validation-20260707-100000.json").write_text(
                json.dumps(validation_report, indent=2),
                encoding="utf-8",
            )

            engine = EditorialBusinessIntelligence(
                base_dir=root,
                data_dir=data_dir,
                site_output_dir=site_output,
                offers_file=offers_file,
                affiliate_links_file=affiliate_links_file,
                config={
                    "business_intelligence": {
                        "evergreen": {
                            "review_after_days": 30,
                            "update_after_days": 90,
                            "outdated_after_days": 180,
                            "deprecated_after_days": 365,
                            "broken_links_threshold": 1,
                            "min_word_count": 200,
                            "min_readability_score": 20,
                            "duplicate_similarity_threshold": 0.8,
                        }
                    }
                },
            )
            weekly_topics = [
                {"keyword": "cursor review 2026", "slug": "cursor-review-2026", "category": "AI Coding", "article_type": "review", "intent": "commercial", "score": 82},
                {"keyword": "surfer seo pricing", "slug": "surfer-seo-pricing", "category": "SEO", "article_type": "pricing", "intent": "commercial", "score": 78},
            ]
            candidate_topics = [
                {"keyword": "cursor review 2026", "slug": "cursor-review-2026", "commercial_intent": 86, "competition": 28, "freshness": 74},
                {"keyword": "surfer seo pricing", "slug": "surfer-seo-pricing", "commercial_intent": 92, "competition": 33, "freshness": 70},
            ]
            calendar = [{"slug": "cursor-review-2026"}, {"slug": "surfer-seo-pricing"}]

            result = engine.run_weekly_intelligence(
                weekly_topics=weekly_topics,
                candidate_topics=candidate_topics,
                editorial_calendar=calendar,
            )

            self.assertEqual(result["affiliate_opportunities"], 2)
            self.assertEqual(result["historical_topics_logged"], 2)
            self.assertTrue((data_dir / "evergreen_report.json").exists())
            self.assertTrue((data_dir / "affiliate_opportunities.csv").exists())
            self.assertTrue((data_dir / "content_gap_report.md").exists())
            self.assertTrue((data_dir / "affiliate_coverage_report.json").exists())
            self.assertTrue((data_dir / "weekly_dashboard.md").exists())
            self.assertTrue((data_dir / "weekly_history.jsonl").exists())

            evergreen = json.loads((data_dir / "evergreen_report.json").read_text(encoding="utf-8"))
            by_slug = {row["slug"]: row for row in evergreen}
            self.assertEqual(by_slug["cursor-review-2026"]["status"], "Fresh")
            self.assertEqual(by_slug["legacy-seo-pricing-2024"]["status"], "Broken")

            dashboard = json.loads((data_dir / "weekly_dashboard.json").read_text(encoding="utf-8"))
            self.assertIn("top_topics", dashboard)
            self.assertIn("business_score", dashboard)
            self.assertTrue(dashboard["content_gaps"])

    def test_lifecycle_manager_logs_only_real_transitions(self) -> None:
        with TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir) / "data"
            manager = ContentLifecycleManager(data_dir)
            first = manager.record_transition("cursor-review-2026", "Cursor Review 2026", "planned")
            second = manager.record_transition("cursor-review-2026", "Cursor Review 2026", "planned")
            third = manager.record_transition("cursor-review-2026", "Cursor Review 2026", "published")

            self.assertIsNotNone(first)
            self.assertIsNone(second)
            self.assertIsNotNone(third)

            lines = (data_dir / "content_lifecycle.jsonl").read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 2)
            state = json.loads((data_dir / "content_lifecycle_state.json").read_text(encoding="utf-8"))
            self.assertEqual(state["cursor-review-2026"], "published")


if __name__ == "__main__":
    unittest.main()
