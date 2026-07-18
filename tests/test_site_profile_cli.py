from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
import unittest

from scripts.show_site_profile import main as show_profile_main
from scripts.validate_site_profiles import main as validate_profiles_main


ROOT = Path(__file__).resolve().parents[1]


class SiteProfileCliTests(unittest.TestCase):
    def test_validate_cli_passes_all_profiles_without_writes(self) -> None:
        stdout = StringIO()
        stderr = StringIO()

        with redirect_stdout(stdout), redirect_stderr(stderr):
            result = validate_profiles_main(
                ["--root", str(ROOT), "--production-check"]
            )

        self.assertEqual(result, 0, stderr.getvalue())
        self.assertIn("PASS smile_ai_review_hub", stdout.getvalue())
        self.assertIn("failed: 0", stdout.getvalue())

    def test_show_cli_prints_default_profile(self) -> None:
        stdout = StringIO()

        with redirect_stdout(stdout):
            result = show_profile_main(
                ["--root", str(ROOT), "--site", "smile_ai_review_hub"]
            )

        self.assertEqual(result, 0)
        self.assertIn('"site_id": "smile_ai_review_hub"', stdout.getvalue())
        self.assertIn('"domain": "https://smileaireviewhub.com"', stdout.getvalue())

    def test_show_cli_rejects_example_for_production(self) -> None:
        stderr = StringIO()

        with redirect_stderr(stderr):
            result = show_profile_main(
                [
                    "--root",
                    str(ROOT),
                    "--site",
                    "example_health",
                    "--production-check",
                ]
            )

        self.assertEqual(result, 1)
        self.assertIn("cannot be used for production", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
