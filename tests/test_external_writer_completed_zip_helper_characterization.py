from __future__ import annotations

import hashlib
from pathlib import Path

from modules.external_writer_pipeline import UniversalExternalWriterExporter


EXPECTED_SHA256 = "9ca99a0fc8ee2b941643b02af0f0550784364f347daccaedec5578442f77165e"


def test_completed_zip_helper_exact_output_is_deterministic() -> None:
    first = UniversalExternalWriterExporter._completed_zip_helper_script()
    second = UniversalExternalWriterExporter._completed_zip_helper_script()
    assert first == second
    assert hashlib.sha256(first.encode("utf-8")).hexdigest() == EXPECTED_SHA256
    for marker in (
        "from __future__ import annotations",
        "EXECUTABLE_SUFFIXES = {",
        "def main(",
        "approval_changed: false",
        "published: false",
        'if __name__ == "__main__":',
    ):
        assert marker in first


def test_build_package_writes_exact_helper_only_under_tmp_path(tmp_path: Path, monkeypatch) -> None:
    exporter = UniversalExternalWriterExporter(root=tmp_path)
    monkeypatch.setattr(exporter, "_copy_inputs", lambda *args: None)
    monkeypatch.setattr(exporter, "_write_editorial_memory_brief", lambda *args: None)
    monkeypatch.setattr(exporter, "_copy_guidance", lambda *args: None)
    package_dir = tmp_path / "package"
    package_dir.mkdir()
    exporter._build_package(package_dir, "test-package", "SOCIAL_HOT_NEWS", "2026-07-25", [])
    helper = package_dir / "CREATE_COMPLETED_DRAFTS.py"
    expected = exporter._completed_zip_helper_script().encode("utf-8")
    assert helper.read_bytes() == expected
    assert hashlib.sha256(helper.read_bytes()).hexdigest() == EXPECTED_SHA256
