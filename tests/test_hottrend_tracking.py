from __future__ import annotations

import builtins
import csv
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from scripts.update_hottrend_tracking import score_grade, update_hottrend_tracking, write_excel_workbook


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


class HottrendTrackingTests(unittest.TestCase):
    def write_scores(self, path: Path, rows: list[dict]) -> None:
        path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

    def run_tracker(self, tmp: Path, scores: Path, now: datetime) -> dict:
        return update_hottrend_tracking(
            scores_path=scores,
            history_path=tmp / "hottrend_topic_history.csv",
            excel_path=tmp / "hottrend_topic_history.xlsx",
            master_excel_path=tmp / "master_dashboard.xlsx",
            latest_dashboard_path=tmp / "hottrend_latest_dashboard.csv",
            weekly_path=tmp / "hottrend_weekly_summary.csv",
            monthly_path=tmp / "hottrend_monthly_summary.csv",
            html_dashboard_path=tmp / "hottrend_dashboard.html",
            now=now,
        )

    def test_score_grade_calculation(self) -> None:
        self.assertEqual(score_grade(91), "Excellent")
        self.assertEqual(score_grade(80), "Strong")
        self.assertEqual(score_grade(70), "Good")
        self.assertEqual(score_grade(64), "Watch")
        self.assertEqual(score_grade(42), "Skip")

    def test_first_run_creates_history_and_dashboards(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            tmp = Path(folder)
            scores = tmp / "topic_scores.json"
            self.write_scores(
                scores,
                [
                    {
                        "topic": "Alpha AI Review 2026",
                        "total_score": 70,
                        "traffic_score": 65,
                        "revenue_score": 72,
                        "seo_score": 60,
                        "trend_score": 68,
                        "buyer_intent": 74,
                        "recommendation": "Strong Candidate",
                        "content_decision": "Article + Video",
                        "video_priority": "Review",
                        "social_scores": {"x": 60, "linkedin": 80},
                        "source": "test",
                    }
                ],
            )
            result = self.run_tracker(tmp, scores, datetime(2026, 6, 18, 8, 0, tzinfo=timezone.utc))

            self.assertEqual(result["topics"], 1)
            history = read_rows(tmp / "hottrend_topic_history.csv")
            latest = read_rows(tmp / "hottrend_latest_dashboard.csv")
            self.assertEqual(len(history), 1)
            self.assertEqual(history[0]["topic"], "Alpha AI Review 2026")
            self.assertEqual(history[0]["first_seen_date"], "2026-06-18")
            self.assertEqual(history[0]["times_seen"], "1")
            self.assertEqual(latest[0]["score_grade"], "Good")
            self.assertEqual(latest[0]["priority"], "P2")
            self.assertEqual(latest[0]["recommended_action"], "Article")
            self.assertTrue((tmp / "hottrend_dashboard.html").exists())

    def test_second_run_tracks_repeated_topic_score_and_rank_change(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            tmp = Path(folder)
            scores = tmp / "topic_scores.json"
            self.write_scores(
                scores,
                [
                    {"topic": "Alpha AI Review 2026", "total_score": 70, "recommendation": "Opportunity"},
                    {"topic": "Beta AI Review 2026", "total_score": 60, "recommendation": "Watch"},
                ],
            )
            self.run_tracker(tmp, scores, datetime(2026, 6, 18, 8, 0, tzinfo=timezone.utc))
            self.write_scores(
                scores,
                [
                    {"topic": "Beta AI Review 2026", "total_score": 75, "recommendation": "Strong Candidate"},
                    {"topic": "Alpha AI Review 2026", "total_score": 67, "recommendation": "Opportunity"},
                ],
            )
            self.run_tracker(tmp, scores, datetime(2026, 6, 19, 8, 0, tzinfo=timezone.utc))

            history = read_rows(tmp / "hottrend_topic_history.csv")
            alpha_rows = [row for row in history if row["slug"] == "alpha-ai-review-2026"]
            beta_rows = [row for row in history if row["slug"] == "beta-ai-review-2026"]
            self.assertEqual(len(history), 4)
            self.assertEqual(alpha_rows[-1]["times_seen"], "2")
            self.assertEqual(alpha_rows[-1]["score_change_vs_previous"], "-3.0")
            self.assertEqual(alpha_rows[-1]["rank_change_vs_previous"], "-1")
            self.assertEqual(beta_rows[-1]["score_change_vs_previous"], "15.0")
            self.assertEqual(beta_rows[-1]["rank_change_vs_previous"], "1")
            latest = read_rows(tmp / "hottrend_latest_dashboard.csv")
            self.assertEqual(latest[0]["trend_direction"], "Rising")

    def test_weekly_and_monthly_summaries_are_written(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            tmp = Path(folder)
            scores = tmp / "topic_scores.json"
            self.write_scores(scores, [{"topic": "Alpha AI Review 2026", "total_score": 70, "recommendation": "Opportunity"}])
            self.run_tracker(tmp, scores, datetime(2026, 6, 18, 8, 0, tzinfo=timezone.utc))
            self.write_scores(scores, [{"topic": "Alpha AI Review 2026", "total_score": 80, "recommendation": "Strong Candidate"}])
            self.run_tracker(tmp, scores, datetime(2026, 6, 20, 8, 0, tzinfo=timezone.utc))

            weekly = read_rows(tmp / "hottrend_weekly_summary.csv")
            monthly = read_rows(tmp / "hottrend_monthly_summary.csv")
            self.assertEqual(weekly[0]["times_seen"], "2")
            self.assertEqual(weekly[0]["best_score"], "80.0")
            self.assertEqual(monthly[0]["average_score"], "75.0")

    def test_master_excel_generation_is_reported_when_available(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            tmp = Path(folder)
            scores = tmp / "topic_scores.json"
            self.write_scores(scores, [{"topic": "Alpha AI Review 2026", "total_score": 80, "recommendation": "Strong Candidate"}])
            result = self.run_tracker(tmp, scores, datetime(2026, 6, 18, 8, 0, tzinfo=timezone.utc))
            if result["master_excel_written"]:
                self.assertTrue((tmp / "master_dashboard.xlsx").exists())
            else:
                self.assertFalse((tmp / "master_dashboard.xlsx").exists())

    def test_excel_generation_skips_gracefully_without_openpyxl(self) -> None:
        original_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "openpyxl" or name.startswith("openpyxl."):
                raise ImportError("openpyxl unavailable")
            return original_import(name, *args, **kwargs)

        with tempfile.TemporaryDirectory() as folder:
            tmp = Path(folder)
            builtins.__import__ = fake_import
            try:
                written = write_excel_workbook(
                    tmp / "history.xlsx",
                    latest=[],
                    history=[],
                    weekly=[],
                    monthly=[],
                )
            finally:
                builtins.__import__ = original_import
            self.assertFalse(written)


if __name__ == "__main__":
    unittest.main()
