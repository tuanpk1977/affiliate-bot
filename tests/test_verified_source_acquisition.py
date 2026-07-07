from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from modules.verified_source_acquisition import VerifiedSourceAcquisition
from scripts import import_verified_sources


class VerifiedSourceAcquisitionTests(unittest.TestCase):
    def test_acquires_verified_sources_and_scores_registry(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            registry = root / "source_registry.json"
            registry.write_text(
                json.dumps(
                    [
                        {
                            "brand": "Cursor",
                            "slug": "cursor",
                            "source_type": "official_docs",
                            "source_name": "Cursor docs",
                            "source_url": "https://cursor.com/docs",
                            "source_status": "verified",
                            "confidence": 95,
                            "notes": "fixture",
                            "last_verified_at": "2026-07-07",
                        },
                        {
                            "brand": "Cursor",
                            "slug": "cursor",
                            "source_type": "pricing_page",
                            "source_name": "Cursor pricing",
                            "source_url": "https://cursor.com/pricing",
                            "source_status": "verified",
                            "confidence": 91,
                            "notes": "fixture",
                            "last_verified_at": "2026-07-07",
                        },
                        {
                            "brand": "Cursor",
                            "slug": "cursor",
                            "source_type": "affiliate_program_page",
                            "source_name": "Cursor affiliate",
                            "source_url": "https://cursor.com/affiliates",
                            "source_status": "verified",
                            "confidence": 87,
                            "notes": "fixture",
                            "last_verified_at": "2026-07-07",
                        },
                    ]
                ),
                encoding="utf-8",
            )
            acquisition = VerifiedSourceAcquisition(registry_json=registry, registry_csv=root / "source_registry.csv")

            result = acquisition.acquire("cursor pricing", {"products": ["Cursor"], "companies": ["Cursor"]})

            self.assertEqual(result["source_status"], "verified")
            self.assertEqual(len(result["verified_sources"]), 3)
            self.assertGreaterEqual(result["official_docs_score"], 40)
            self.assertGreaterEqual(result["total_verified_source_score"], 35)
            self.assertNotIn("official_docs", result["missing_verified_sources"])

    def test_import_script_normalizes_registry_and_writes_reports(self) -> None:
        with TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir) / "data"
            data_dir.mkdir(parents=True, exist_ok=True)
            (data_dir / "source_registry.json").write_text(
                json.dumps(
                    [
                        {
                            "brand": "Cursor",
                            "source_type": "official_docs",
                            "source_name": "Cursor docs",
                            "source_url": "https://cursor.com/docs",
                            "source_status": "verified",
                            "confidence": 90,
                        },
                        {
                            "brand": "Cursor",
                            "source_type": "official_docs",
                            "source_name": "Cursor docs",
                            "source_url": "https://cursor.com/docs",
                            "source_status": "verified",
                            "confidence": 90,
                        },
                    ]
                ),
                encoding="utf-8",
            )

            # Call script logic via argv-compatible entry to target temp data dir.
            import sys

            original_argv = sys.argv
            try:
                sys.argv = ["import_verified_sources.py", "--data-dir", str(data_dir)]
                result = import_verified_sources.main()
            finally:
                sys.argv = original_argv

            self.assertEqual(result, 0)
            normalized = json.loads((data_dir / "source_registry.json").read_text(encoding="utf-8"))
            self.assertEqual(len(normalized), 1)
            self.assertIn("verification_status", normalized[0])
            self.assertIn("freshness_score", normalized[0])
            self.assertTrue((data_dir / "source_registry.csv").exists())
            self.assertTrue((data_dir / "source_registry_report.json").exists())
            self.assertTrue((data_dir / "source_registry_report.csv").exists())
            self.assertTrue((data_dir / "source_registry_report.md").exists())
            self.assertTrue((data_dir / "source_review_queue.json").exists())
            self.assertTrue((data_dir / "knowledge_dashboard.json").exists())


if __name__ == "__main__":
    unittest.main()
