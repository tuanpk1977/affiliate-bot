from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from modules.competitor_snapshot_ingestion import CompetitorSnapshotIngestion


class CompetitorSnapshotIngestionTests(unittest.TestCase):
    def test_reports_missing_coverage_without_fake_data(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            ingestion = CompetitorSnapshotIngestion(
                json_path=root / "competitor_snapshots.json",
                csv_path=root / "competitor_snapshots.csv",
            )
            result = ingestion.for_keyword("cursor pricing")
            self.assertEqual(result["coverage_status"], "missing")
            self.assertEqual(result["profiles"], [])

    def test_loads_local_snapshot_data(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            json_path = root / "competitor_snapshots.json"
            json_path.write_text(
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
            ingestion = CompetitorSnapshotIngestion(json_path=json_path, csv_path=root / "competitor_snapshots.csv")
            result = ingestion.for_keyword("cursor pricing")

            self.assertEqual(result["coverage_status"], "available")
            self.assertEqual(len(result["profiles"]), 1)
            self.assertEqual(result["profiles"][0]["word_count"], 1800)


if __name__ == "__main__":
    unittest.main()
