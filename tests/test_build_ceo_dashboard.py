from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
import unittest

import scripts.build_ceo_dashboard as dashboard_script


class BuildCeoDashboardTests(unittest.TestCase):
    def test_builds_dashboard_html_json_and_workbook(self) -> None:
        with TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir) / "data"
            data_dir.mkdir(parents=True, exist_ok=True)
            (data_dir / "weekly_topics.json").write_text(json.dumps([{"keyword": "topic a", "slug": "topic-a"}]), encoding="utf-8")
            (data_dir / "editorial_calendar.json").write_text(json.dumps([{"day_of_week": "Monday", "keyword": "topic a", "article_type": "article"}]), encoding="utf-8")
            (data_dir / "content_review_report.json").write_text(json.dumps({"summary": {}, "items": []}), encoding="utf-8")
            (data_dir / "publish_gate_report.json").write_text(json.dumps({"summary": {}, "items": []}), encoding="utf-8")
            (data_dir / "optimization_report.json").write_text(json.dumps({"actions": []}), encoding="utf-8")
            (data_dir / "research_quality_report.json").write_text(json.dumps([]), encoding="utf-8")
            (data_dir / "research_enrichment_queue.json").write_text(json.dumps([]), encoding="utf-8")
            (data_dir / "human_approval_queue.json").write_text(json.dumps([]), encoding="utf-8")
            (data_dir / "publish_queue.json").write_text(json.dumps([]), encoding="utf-8")

            fake_settings = SimpleNamespace(data_dir=data_dir)
            with patch.object(dashboard_script, "settings", fake_settings), patch.object(dashboard_script, "DATA_DIR", data_dir), patch.object(dashboard_script, "HTML_PATH", data_dir / "daily_ceo_dashboard.html"), patch.object(dashboard_script, "JSON_PATH", data_dir / "daily_ceo_dashboard.json"), patch.object(dashboard_script, "XLSX_PATH", data_dir / "master_dashboard.xlsx"):
                result = dashboard_script.main()

            self.assertEqual(result, 0)
            self.assertTrue((data_dir / "daily_ceo_dashboard.html").exists())
            self.assertTrue((data_dir / "daily_ceo_dashboard.json").exists())
            self.assertTrue((data_dir / "master_dashboard.xlsx").exists())


if __name__ == "__main__":
    unittest.main()
