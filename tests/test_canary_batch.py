from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts.run_canary_batch import run_canary_batch


class CanaryBatchTests(unittest.TestCase):
    def test_canary_batch_writes_artifacts_only_and_preserves_safety_flags(self) -> None:
        with TemporaryDirectory() as temp_dir, patch.dict("os.environ", {"OPENAI_API_KEY": ""}, clear=False):
            output_root = Path(temp_dir) / "artifacts" / "canary"
            report = run_canary_batch(count=5, output_root=output_root, batch_id="test-canary", allow_heuristic_fallback=True)

            self.assertTrue(report["canary_mode"])
            self.assertEqual(report["canary_batch_size"], 5)
            self.assertFalse(report["safety"]["publish"])
            self.assertFalse(report["safety"]["deploy"])
            self.assertFalse(report["safety"]["index"])
            self.assertFalse(report["safety"]["auto_approve"])
            self.assertTrue(report["safety"]["human_approval_required"])
            self.assertEqual(report["selected"], 5)
            self.assertEqual(report["drafts_generated"], 5)
            self.assertEqual(report["failed"], 0)
            self.assertEqual(report["production_review_ready"], 0)
            self.assertEqual(report["provider_status"]["provider_mode"], "heuristic_fallback")
            self.assertTrue(report["provider_status"]["heuristic_fallback_used"])

            root = output_root / "test-canary"
            self.assertTrue((root / "canary_report.json").exists())
            self.assertTrue((root / "canary_human_review_queue.json").exists())
            self.assertTrue((root / "data" / "content_review_queue.json").exists())
            for row in report["per_article"]:
                self.assertEqual(row["provider_mode"], "heuristic_fallback")
                self.assertFalse(row["production_review_ready"])
                self.assertGreaterEqual(row["sources"], 2)
                self.assertGreaterEqual(len(row["source_domains"]), 2)
                self.assertTrue(row["claim_source_mapping"])
                self.assertIn(row["judge_decision"], {"pass_to_human", "warning_to_human", "block"})
                self.assertTrue(Path(row["html_path"]).exists())
                self.assertTrue(Path(row["markdown_path"]).exists())
                self.assertTrue(Path(row["research_path"]).exists())
                self.assertTrue(Path(row["review_path"]).exists())
                self.assertTrue(row["validation"]["source_validation"])
                self.assertTrue(row["validation"]["schema_validation"])
                self.assertTrue(row["validation"]["render_validation"])
                self.assertTrue(row["validation"]["duplicate_validation"])

            stored = json.loads((root / "canary_report.json").read_text(encoding="utf-8"))
            self.assertEqual(stored["selected"], 5)
            self.assertEqual(stored["production_recommendation"]["ready_for_5_per_day"], False)

    def test_single_article_failure_does_not_stop_canary_batch(self) -> None:
        with TemporaryDirectory() as temp_dir, patch.dict("os.environ", {"OPENAI_API_KEY": ""}, clear=False):
            output_root = Path(temp_dir) / "artifacts" / "canary"
            report = run_canary_batch(count=3, output_root=output_root, batch_id="partial-canary", allow_heuristic_fallback=True)

            self.assertEqual(report["selected"], 3)
            self.assertEqual(len(report["per_article"]), 3)
            self.assertLessEqual(report["failed"], 3)
            self.assertTrue((output_root / "partial-canary" / "canary_report.json").exists())


if __name__ == "__main__":
    unittest.main()
