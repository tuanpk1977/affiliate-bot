from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from modules.knowledge_registry import KnowledgeRegistry
from modules.source_review import SourceReview


class SourceReviewTests(unittest.TestCase):
    def test_review_queue_syncs_and_approve_updates_registry(self) -> None:
        with TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir) / "data"
            data_dir.mkdir(parents=True, exist_ok=True)
            registry = KnowledgeRegistry(data_dir)
            rows = registry.normalize_rows(
                [
                    {
                        "brand": "Cursor",
                        "slug": "cursor",
                        "source_type": "official_docs",
                        "source_name": "Cursor Docs",
                        "source_url": "https://cursor.com/docs",
                        "verification_status": "pending",
                        "confidence": 75,
                        "verification_date": datetime.now(UTC).isoformat(),
                    },
                    {
                        "brand": "Cursor",
                        "slug": "cursor",
                        "source_type": "pricing_page",
                        "source_name": "Cursor Pricing",
                        "source_url": "https://cursor.com/pricing",
                        "verification_status": "verified",
                        "confidence": 80,
                        "verification_date": (datetime.now(UTC) - timedelta(days=500)).isoformat(),
                    },
                ]
            )
            registry.save_registry(rows)
            review = SourceReview(data_dir, registry=registry)

            queue = review.sync_from_registry(registry.load_registry())
            pending = next(row for row in queue if row["source"] == "Cursor Docs")
            self.assertIn(pending["status"], {"pending", "needs_review"})
            self.assertTrue((data_dir / "source_review_report.json").exists())

            updated = review.approve_source(pending["id"], reviewer="qa", confidence=90)
            queue_after = review.load_queue()
            self.assertIsNotNone(updated)
            self.assertEqual(updated["verification_status"], "verified")
            approved_queue = next(row for row in queue_after if row["id"] == pending["id"])
            self.assertEqual(approved_queue["status"], "verified")


if __name__ == "__main__":
    unittest.main()
