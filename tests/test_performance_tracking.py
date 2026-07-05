from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from modules.performance_tracking import (
    aggregate_gsc,
    build_revenue_dashboard,
    calculate_refresh_score,
    parse_gsc_export,
    parse_youtube_export,
    recommend_internal_links,
    recommend_refresh,
    write_csv,
)


class PerformanceTrackingTests(unittest.TestCase):
    def test_parse_gsc_export_maps_page_and_query_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "gsc.csv"
            write_csv(
                path,
                [
                    {
                        "Page": "https://smileaireviewhub.com/surfer-seo-free-trial/",
                        "Query": "surfer seo free trial",
                        "Clicks": "4",
                        "Impressions": "200",
                        "CTR": "2.0%",
                        "Position": "8.5",
                        "Country": "USA",
                    }
                ],
                ["Page", "Query", "Clicks", "Impressions", "CTR", "Position", "Country"],
            )
            pages, queries = parse_gsc_export(path)
        self.assertEqual(pages[0]["slug"], "surfer-seo-free-trial")
        self.assertEqual(queries[0]["query"], "surfer seo free trial")
        self.assertEqual(pages[0]["clicks"], 4)

    def test_parse_youtube_export_maps_video_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "youtube.csv"
            write_csv(
                path,
                [{"Slug": "surfer-seo-free-trial", "Video URL": "https://youtu.be/test", "Views": "100", "Watch time (hours)": "5"}],
                ["Slug", "Video URL", "Views", "Watch time (hours)"],
            )
            rows = parse_youtube_export(path)
        self.assertEqual(rows[0]["slug"], "surfer-seo-free-trial")
        self.assertEqual(rows[0]["views"], 100)
        self.assertEqual(rows[0]["watch_time"], 5)

    def test_refresh_score_flags_low_ctr_and_missing_video(self) -> None:
        score = calculate_refresh_score({"impressions": 500, "ctr": 0.8, "position": 18}, {}, {"buyer_intent": 70}, {})
        self.assertGreaterEqual(score, 60)

    def test_revenue_dashboard_marks_high_traffic_low_revenue(self) -> None:
        rows = build_revenue_dashboard(
            [
                {
                    "slug": "surfer-seo",
                    "article_url": "https://smileaireviewhub.com/surfer-seo/",
                    "topic": "Surfer SEO",
                    "google_clicks": 100,
                    "affiliate_clicks": 1,
                    "revenue_estimate": 0,
                }
            ]
        )
        self.assertEqual(rows[0]["revenue_opportunity"], "High traffic low revenue")

    def test_refresh_and_internal_link_recommendations(self) -> None:
        lifecycle = [
            {
                "slug": "surfer-seo-review",
                "article_url": "https://smileaireviewhub.com/surfer-seo-review/",
                "topic": "Surfer SEO Review",
                "impressions": 300,
                "ctr": 0.5,
                "avg_position": 15,
                "google_clicks": 2,
                "revenue_estimate": 0,
                "refresh_score": 65,
                "next_action": "Refresh article",
            },
            {
                "slug": "surfer-seo-alternatives",
                "article_url": "https://smileaireviewhub.com/surfer-seo-alternatives/",
                "topic": "Surfer SEO Alternatives",
                "refresh_score": 0,
            },
        ]
        refresh = recommend_refresh(lifecycle)
        internal = recommend_internal_links(lifecycle)
        self.assertEqual(refresh[0]["priority"], "High")
        self.assertGreaterEqual(len(internal), 1)


if __name__ == "__main__":
    unittest.main()
