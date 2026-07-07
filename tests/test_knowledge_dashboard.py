from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from modules.knowledge_dashboard import KnowledgeDashboard
from modules.knowledge_registry import KnowledgeRegistry
from modules.source_review import SourceReview


class KnowledgeDashboardTests(unittest.TestCase):
    def test_dashboard_reports_governance_metrics(self) -> None:
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
                        "verification_status": "verified",
                        "confidence": 92,
                        "verification_date": datetime.now(UTC).isoformat(),
                    },
                    {
                        "brand": "Cursor",
                        "slug": "cursor",
                        "source_type": "pricing_page",
                        "source_name": "Cursor Pricing",
                        "source_url": "https://cursor.com/pricing",
                        "verification_status": "needs_review",
                        "confidence": 70,
                        "verification_date": (datetime.now(UTC) - timedelta(days=120)).isoformat(),
                    },
                    {
                        "brand": "Windsurf",
                        "slug": "windsurf",
                        "source_type": "affiliate_program_page",
                        "source_name": "Windsurf Affiliate",
                        "source_url": "https://windsurf.com/affiliate",
                        "verification_status": "verified",
                        "confidence": 84,
                        "verification_date": (datetime.now(UTC) - timedelta(days=430)).isoformat(),
                    },
                ]
            )
            registry.save_registry(rows)
            SourceReview(data_dir, registry=registry).sync_from_registry(rows)
            dashboard = KnowledgeDashboard(data_dir, registry=registry)

            report = dashboard.generate()

            self.assertIn("verified_sources", report)
            self.assertIn("average_trust", report)
            self.assertIn("missing_pricing", report)
            self.assertTrue((data_dir / "knowledge_dashboard.json").exists())
            self.assertTrue((data_dir / "knowledge_dashboard.csv").exists())
            self.assertTrue((data_dir / "knowledge_dashboard.md").exists())


if __name__ == "__main__":
    unittest.main()
