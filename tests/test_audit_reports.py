from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.build_audit_reports import REQUIRED_REPORTS, generate_reports


class AuditReportsTest(unittest.TestCase):
    def test_generate_reports_creates_all_expected_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            generated = generate_reports(output_dir=output_dir)

            self.assertEqual(len(generated), len(REQUIRED_REPORTS))
            for report_name in REQUIRED_REPORTS:
                self.assertTrue((output_dir / report_name).exists(), f"Missing {report_name}")

            governance_path = output_dir / "ai-governance.md"
            self.assertTrue(governance_path.exists())

            feature_flags_path = output_dir / "feature-flags.json"
            self.assertTrue(feature_flags_path.exists())

            architecture_report = (output_dir / "architecture-report.md").read_text(encoding="utf-8")
            self.assertIn("Architecture", architecture_report)


if __name__ == "__main__":
    unittest.main()
