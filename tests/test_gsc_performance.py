from __future__ import annotations

import unittest

import pandas as pd

from modules.gsc_performance import (
    build_go_click_performance_report,
    build_gsc_page_report,
    build_gsc_query_report,
    build_traffic_performance_report,
    normalize_page_path,
)


class GSCPerformanceTests(unittest.TestCase):
    def test_normalize_page_path(self) -> None:
        self.assertEqual(normalize_page_path("https://review.mssmileenglish.com/cursor/"), "/cursor/")
        self.assertEqual(normalize_page_path("cursor"), "/cursor/")
        self.assertEqual(normalize_page_path("/comparisons/cursor-vs-windsurf"), "/comparisons/cursor-vs-windsurf/")

    def test_gsc_reports_accept_empty_data(self) -> None:
        empty = pd.DataFrame()
        self.assertTrue(build_gsc_page_report(empty).empty)
        self.assertTrue(build_gsc_query_report(empty).empty)

    def test_gsc_page_aggregation(self) -> None:
        df = pd.DataFrame(
            [
                {"page": "/cursor/", "query": "cursor review", "clicks": 2, "impressions": 100, "ctr": 0.02, "position": 8},
                {"page": "/cursor/", "query": "cursor pricing", "clicks": 1, "impressions": 50, "ctr": 0.02, "position": 12},
            ]
        )
        report = build_gsc_page_report(df)
        self.assertEqual(int(report.iloc[0]["clicks"]), 3)
        self.assertEqual(int(report.iloc[0]["impressions"]), 150)
        self.assertIn("cursor review", report.iloc[0]["top_queries"])

    def test_traffic_report_has_priority_pages_without_data(self) -> None:
        report = build_traffic_performance_report(pd.DataFrame(), pd.DataFrame())
        self.assertIn("/", set(report["page"]))
        row = report[report["page"] == "/"].iloc[0]
        self.assertEqual(row["recommended_action"], "no_data_yet")

    def test_go_click_report_safe_without_events(self) -> None:
        report = build_go_click_performance_report()
        self.assertIn("clicks", report.columns)


if __name__ == "__main__":
    unittest.main()
