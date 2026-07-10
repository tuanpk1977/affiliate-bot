from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
import unittest

from modules.publishing_indexing import BASE_URL
from scripts import post_deploy_indexing as indexing


class _FakeValidation:
    def __init__(self, ok: bool = True) -> None:
        self.ok = ok
        self.pages = []
        self.sitemap = SimpleNamespace(ok=ok, total_urls=1)

    def to_dict(self) -> dict[str, object]:
        return {"ok": self.ok, "sitemap": {"ok": self.ok, "total_urls": 1}, "pages": []}


def _engine_result(status: str) -> SimpleNamespace:
    return SimpleNamespace(to_dict=lambda: {"engine": status.split("_", 1)[0], "status": status, "message": ""})


class PostDeployIndexingTests(unittest.TestCase):
    def _run_main(self, root: Path, argv: list[str], *, validation_ok: bool = True, indexnow_error: Exception | None = None) -> int:
        log_root = root / "logs" / "indexing"
        with patch.object(indexing, "ROOT", root), patch.object(indexing, "LOG_ROOT", log_root), patch.object(indexing, "STATE_PATH", log_root / "submission-state.json"):
            with patch("sys.argv", ["post_deploy_indexing.py", *argv]):
                with patch.object(indexing, "validate_batch", return_value=_FakeValidation(validation_ok)):
                    with patch.object(indexing, "wait_with_recovery", return_value={f"{BASE_URL}/one/": 200}):
                        with patch.object(indexing, "wait_for_live_urls", return_value={f"{BASE_URL}/one/": 200}):
                            with patch.object(indexing, "validate_live_sitemap", return_value=(True, 1, [])):
                                with patch.object(indexing, "validate_live_pages", return_value=(True, {})):
                                    with patch.object(indexing, "submit_bing_sitemap", return_value=_engine_result("skipped_missing_credentials")):
                                        with patch.object(indexing, "submit_google_sitemap", return_value=_engine_result("queued_natural_discovery")):
                                            if indexnow_error is None:
                                                submit_patch = patch.object(indexing, "submit_indexnow", return_value=True)
                                            else:
                                                submit_patch = patch.object(indexing, "submit_indexnow", side_effect=indexnow_error)
                                            with submit_patch:
                                                return indexing.main()

    def test_missing_indexnow_credentials_non_strict_returns_zero_and_writes_report(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            code = self._run_main(
                root,
                ["--url", f"{BASE_URL}/one/", "--recovery-delays", ""],
                indexnow_error=FileNotFoundError("missing key"),
            )
            report = json.loads((root / "logs" / "indexing" / "daily-report.json").read_text(encoding="utf-8"))

        self.assertEqual(code, 0)
        self.assertEqual(report["status"], "PARTIAL")
        self.assertEqual(report["indexing_mode"], "non-strict")
        self.assertTrue(report["warnings"])

    def test_missing_indexnow_credentials_strict_returns_nonzero(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            code = self._run_main(
                root,
                ["--strict", "--url", f"{BASE_URL}/one/", "--recovery-delays", ""],
                indexnow_error=FileNotFoundError("missing key"),
            )

        self.assertEqual(code, 1)

    def test_zero_changed_urls_returns_success_and_report(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            log_root = root / "logs" / "indexing"
            with patch.object(indexing, "ROOT", root), patch.object(indexing, "LOG_ROOT", log_root):
                with patch.object(indexing, "git_changed_urls", return_value=[]):
                    with patch("sys.argv", ["post_deploy_indexing.py", "--from-git"]):
                        code = indexing.main()
            report = json.loads((log_root / "daily-report.json").read_text(encoding="utf-8"))

        self.assertEqual(code, 0)
        self.assertEqual(report["status"], "SKIPPED_NO_CHANGED_URLS")

    def test_preflight_warning_non_strict_returns_zero_and_report(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            code = self._run_main(root, ["--url", f"{BASE_URL}/one/"], validation_ok=False)
            report_exists = (root / "logs" / "indexing" / "daily-report.json").exists()

        self.assertEqual(code, 0)
        self.assertTrue(report_exists)

    def test_preflight_warning_strict_returns_nonzero(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            code = self._run_main(root, ["--strict", "--url", f"{BASE_URL}/one/"], validation_ok=False)

        self.assertEqual(code, 1)

    def test_malformed_recovery_config_returns_clear_error_and_report(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            code = self._run_main(root, ["--url", f"{BASE_URL}/one/", "--recovery-delays", "bad"])
            report_exists = (root / "logs" / "indexing" / "daily-report.json").exists()

        self.assertEqual(code, 2)
        self.assertTrue(report_exists)

    def test_workflow_uploads_artifact_always(self) -> None:
        workflow = Path(".github/workflows/post-deploy-indexing.yml").read_text(encoding="utf-8")

        self.assertIn("Upload indexing report", workflow)
        self.assertIn("if: always()", workflow)
        self.assertIn('STRICT_INDEXING: "false"', workflow)


if __name__ == "__main__":
    unittest.main()
