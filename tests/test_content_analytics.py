from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from modules.content_analytics import ContentAnalytics


class ContentAnalyticsTests(unittest.TestCase):
    def test_builds_performance_report_from_tracking_csv(self) -> None:
        with TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir) / "data"
            tracking_csv = data_dir / "content_growth_performance_log.csv"
            tracking_csv.parent.mkdir(parents=True, exist_ok=True)
            tracking_csv.write_text(
                "\n".join(
                    [
                        "publish_date,url,topic,article_type,source_keyword,google_indexed_status,bing_discovered_status,bing_indexed_status,yandex_index_status,impressions,clicks,ctr,average_position,social_views,youtube_views,affiliate_clicks,revenue,notes",
                        "2026-07-01,https://example.com/cursor-pricing/,cursor pricing,comparison,cursor pricing,pending,pending,pending,pending,200,12,6,16,0,0,8,40,fixture",
                    ]
                ),
                encoding="utf-8",
            )
            analytics = ContentAnalytics(data_dir=data_dir, tracking_csv=tracking_csv)

            rows = analytics.build_performance_report()

            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["slug"], "cursor-pricing")
            self.assertGreater(rows[0]["topic_roi_score"], 0)
            self.assertTrue((data_dir / "content_performance.json").exists())
            self.assertTrue((data_dir / "content_performance.csv").exists())
            self.assertTrue((data_dir / "topic_feedback_history.jsonl").exists())


if __name__ == "__main__":
    unittest.main()
