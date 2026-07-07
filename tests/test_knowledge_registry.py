from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from modules.knowledge_registry import KnowledgeRegistry


class KnowledgeRegistryTests(unittest.TestCase):
    def test_registry_detects_duplicates_and_stale_records(self) -> None:
        with TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir) / "data"
            data_dir.mkdir(parents=True, exist_ok=True)
            now = datetime.now(UTC)
            rows = [
                {
                    "brand": "Cursor",
                    "slug": "cursor",
                    "source_type": "official_docs",
                    "source_name": "Cursor Docs",
                    "source_url": "https://cursor.com/docs",
                    "verification_status": "verified",
                    "confidence": 92,
                    "verification_date": (now - timedelta(days=1)).isoformat(),
                },
                {
                    "brand": "Cursor",
                    "slug": "cursor",
                    "source_type": "pricing_page",
                    "source_name": "Cursor Pricing",
                    "source_url": "https://cursor.com/pricing",
                    "verification_status": "verified",
                    "confidence": 88,
                    "verification_date": (now - timedelta(days=500)).isoformat(),
                },
                {
                    "brand": "Cursor",
                    "slug": "cursor",
                    "source_type": "pricing_page",
                    "source_name": "OpenAI API Pricing",
                    "source_url": "https://cursor.com/pricing",
                    "verification_status": "verified",
                    "confidence": 88,
                    "verification_date": (now - timedelta(days=5)).isoformat(),
                },
            ]
            registry = KnowledgeRegistry(data_dir)

            normalized = registry.normalize_rows(rows)

            official = next(row for row in normalized if row["source_type"] == "official_docs")
            stale_pricing = next(row for row in normalized if row["source_name"] == "Cursor Pricing")
            duplicate = next(row for row in normalized if row["source_name"] == "OpenAI API Pricing")
            self.assertEqual(official["verification_status"], "verified")
            self.assertGreaterEqual(official["freshness_score"], 90)
            self.assertIn(stale_pricing["verification_status"], {"expired", "needs_review"})
            self.assertEqual(duplicate["verification_status"], "duplicate")
            self.assertTrue(duplicate["duplicate_of"])
            self.assertIn("trust_score", official)
            self.assertIn("history", official)

    def test_registry_sync_keeps_version_history(self) -> None:
        with TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir) / "data"
            data_dir.mkdir(parents=True, exist_ok=True)
            registry = KnowledgeRegistry(data_dir)
            acquisition = {
                "registry_records": {
                    "official_docs": [
                        {
                            "brand": "Cursor",
                            "slug": "cursor",
                            "source_type": "official_docs",
                            "source_name": "Cursor Docs",
                            "source_url": "https://cursor.com/docs",
                            "verification_status": "verified",
                            "confidence": 91,
                            "verification_date": datetime.now(UTC).isoformat(),
                        }
                    ]
                }
            }

            first = registry.sync_acquisition("cursor pricing", acquisition)
            second = registry.sync_acquisition(
                "cursor pricing",
                {
                    "registry_records": {
                        "official_docs": [
                            {
                                "brand": "Cursor",
                                "slug": "cursor",
                                "source_type": "official_docs",
                                "source_name": "Cursor Developer Docs",
                                "source_url": "https://cursor.com/docs",
                                "verification_status": "verified",
                                "confidence": 95,
                                "verification_date": datetime.now(UTC).isoformat(),
                            }
                        ]
                    }
                },
            )

            self.assertEqual(len(first["registry_rows"]), 1)
            updated = second["registry_rows"][0]
            self.assertGreaterEqual(updated["version"], 2)
            self.assertGreaterEqual(len(updated["history"]), 2)
            self.assertTrue((data_dir / "source_registry.json").exists())
            self.assertTrue((data_dir / "source_registry_history.jsonl").exists())


if __name__ == "__main__":
    unittest.main()
