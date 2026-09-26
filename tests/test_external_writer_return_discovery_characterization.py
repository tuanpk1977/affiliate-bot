from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import zipfile
from pathlib import Path

import pytest

from modules.external_writer_pipeline import ImportCandidate, UniversalExternalWriterImporter


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _manifest_zip(path: Path, manifest: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("completed_manifest.json", json.dumps(manifest))
    return path


def _candidate(path: Path, *, status: str = "PENDING") -> ImportCandidate:
    return ImportCandidate(path.resolve(), "sha", "stamp", "pkg", "LANE", status, "reason")


def test_import_candidate_field_order_defaults_value_semantics_and_frozen_contract() -> None:
    path = Path("return.zip")
    candidate = ImportCandidate(path, "abc")

    assert [field.name for field in dataclasses.fields(ImportCandidate)] == [
        "path",
        "checksum",
        "modified_at",
        "package_id",
        "lane",
        "status",
        "reason",
    ]
    assert candidate == ImportCandidate(path, "abc")
    assert repr(candidate).startswith("ImportCandidate(path=")
    assert dataclasses.astuple(candidate) == (path, "abc", "", "", "", "PENDING", "")
    with pytest.raises(dataclasses.FrozenInstanceError):
        candidate.status = "INVALID"  # type: ignore[misc]


def test_discover_and_audit_preserve_pattern_filter_order_and_status_rules(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    importer = UniversalExternalWriterImporter(root=tmp_path)
    importer.returned_root.mkdir(parents=True)
    older = importer.returned_root / "completed_drafts-old.zip"
    newer = importer.returned_root / "completed_drafts-new.zip"
    ignored = importer.returned_root / "other.zip"
    for path in (older, newer, ignored):
        path.write_bytes(path.name.encode())
    os.utime(older, (100, 100))
    os.utime(newer, (200, 200))
    statuses = {older.resolve(): "PENDING", newer.resolve(): "INVALID"}
    monkeypatch.setattr(
        importer,
        "inspect_candidate",
        lambda path: _candidate(path, status=statuses[path.resolve()]),
    )

    assert [row.path.name for row in importer.discover()] == ["completed_drafts-old.zip"]
    audited = importer.audit_returned()
    assert [(row.path.name, row.status) for row in audited] == [
        ("completed_drafts-new.zip", "INVALID"),
        ("completed_drafts-old.zip", "PENDING"),
    ]


def test_explicit_discovery_returns_nonpending_but_rejects_missing_and_non_zip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    importer = UniversalExternalWriterImporter(root=tmp_path)
    source = tmp_path / "arbitrary-name.ZIP"
    source.write_bytes(b"return")
    monkeypatch.setattr(importer, "inspect_candidate", lambda path: _candidate(path, status="INVALID"))

    assert [row.status for row in importer.discover(explicit=str(source))] == ["INVALID"]
    assert importer.discover(explicit=str(tmp_path / "missing.zip")) == []
    non_zip = tmp_path / "return.txt"
    non_zip.write_text("return", encoding="utf-8")
    assert importer.discover(explicit=str(non_zip)) == []


def test_missing_returned_directory_has_deterministic_empty_results(tmp_path: Path) -> None:
    importer = UniversalExternalWriterImporter(root=tmp_path)

    assert importer.discover() == []
    assert importer.audit_returned() == []


def test_successful_import_index_uses_only_successful_imports_and_first_value(tmp_path: Path) -> None:
    importer = UniversalExternalWriterImporter(root=tmp_path)
    first = {
        "status": "IMPORTED",
        "imported": [{"task_id": "one"}],
        "zip_sha256": "ABC",
        "package_id": "pkg-one",
    }
    second = {
        "status": "IMPORTED",
        "imported": [{"task_id": "two"}],
        "zip_sha256": "abc",
        "package_id": "pkg-two",
    }
    ignored = {"status": "FAILED_IMPORT", "imported": [{"task_id": "bad"}], "zip_sha256": "bad"}
    _write_json(importer.history_root / "2026-01-01/a/import.json", first)
    _write_json(importer.history_root / "2026-01-02/b/import.json", second)
    _write_json(importer.history_root / "2026-01-03/c/import.json", ignored)
    (importer.history_root / "2026-01-04/d").mkdir(parents=True)
    (importer.history_root / "2026-01-04/d/import.json").write_text("{broken", encoding="utf-8")

    by_sha, by_package = importer._successful_import_index()

    assert set(by_sha) == {"abc"}
    assert by_sha["abc"]["package_id"] == "pkg-one"
    assert set(by_package) == {"pkg-one", "pkg-two"}
    assert Path(by_package["pkg-one"]["history_path"]).parts[-3:] == (
        "2026-01-01",
        "a",
        "import.json",
    )


def test_manifest_identity_normalizes_fields_and_detects_mixed_lanes(tmp_path: Path) -> None:
    importer = UniversalExternalWriterImporter(root=tmp_path)
    source = _manifest_zip(
        tmp_path / "completed_drafts.zip",
        {
            "package_id": " pkg-1 ",
            "task_type": "WEBSITE_FOUNDATION",
            "items": [{"task_id": "social-1"}],
        },
    )
    importer.queue.get = lambda task_id: {"task_type": "SOCIAL_HOT_NEWS"}  # type: ignore[method-assign]

    assert importer._manifest_identity(source) == (
        "pkg-1",
        "",
        "Completed ZIP mixes workflow lanes: ['SOCIAL_HOT_NEWS', 'WEBSITE_FOUNDATION']",
    )


@pytest.mark.parametrize(
    ("payload", "error_fragment"),
    ((b"not-a-zip", "File is not a zip file"),),
)
def test_manifest_identity_returns_parse_errors_instead_of_raising(
    tmp_path: Path, payload: bytes, error_fragment: str
) -> None:
    source = tmp_path / "completed_drafts.zip"
    source.write_bytes(payload)

    package_id, lane, error = UniversalExternalWriterImporter(root=tmp_path)._manifest_identity(source)

    assert (package_id, lane) == ("", "")
    assert error_fragment in error


def test_protected_manifest_states_returns_sorted_current_conflicts(tmp_path: Path) -> None:
    importer = UniversalExternalWriterImporter(root=tmp_path)
    source = _manifest_zip(
        tmp_path / "completed_drafts.zip",
        {"items": [{"task_id": "website-1"}, {"task_id": "social-1"}]},
    )
    tasks = {
        "website-1": {"task_type": "WEBSITE_FOUNDATION"},
        "social-1": {"task_type": "SOCIAL_HOT_NEWS"},
    }
    importer.queue.get = lambda task_id: tasks.get(task_id)  # type: ignore[method-assign]
    importer.queue._website_states = lambda task: {"reviewed", "approved"}  # type: ignore[method-assign]
    importer.queue._invalidated_unpublished_approval = lambda task: False  # type: ignore[method-assign]

    assert importer._protected_manifest_states(source) == [
        {"task_id": "website-1", "states": ["approved", "reviewed"]}
    ]


@pytest.mark.parametrize(
    ("case", "expected_status", "expected_reason"),
    (
        ("archive", "ARCHIVE_PENDING", "Import succeeded previously, but the archive move did not finish."),
        ("sha", "DUPLICATE", "SHA-256 checksum was imported previously."),
        ("package", "DUPLICATE", "package_id was imported previously."),
        ("identity", "INVALID", "identity failed"),
        (
            "protected",
            "STALE_PROTECTED",
            "Package targets protected website state and is no longer pending (task-1: approved, reviewed).",
        ),
        ("validation", "INVALID", "first; second"),
        ("pending", "PENDING", ""),
    ),
)
def test_inspect_candidate_preserves_classification_precedence_and_result_shape(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    case: str,
    expected_status: str,
    expected_reason: str,
) -> None:
    importer = UniversalExternalWriterImporter(root=tmp_path)
    source = tmp_path / "relative" / "completed_drafts.zip"
    source.parent.mkdir()
    source.write_bytes(b"candidate")
    checksum = hashlib.sha256(b"candidate").hexdigest()
    identity_error = "identity failed" if case == "identity" else ""
    monkeypatch.setattr(importer, "_manifest_identity", lambda path: ("pkg-1", "WEBSITE_FOUNDATION", identity_error))
    monkeypatch.setattr(
        importer,
        "_successful_import_index",
        lambda: (
            ({checksum: {"status": "IMPORTED"}} if case == "sha" else {}),
            ({"pkg-1": {"status": "IMPORTED"}} if case == "package" else {}),
        ),
    )
    monkeypatch.setattr(
        importer,
        "_protected_manifest_states",
        lambda path: ([{"task_id": "task-1", "states": ["approved", "reviewed"]}] if case == "protected" else []),
    )
    monkeypatch.setattr(
        importer,
        "validate_zip",
        lambda path: (
            {"status": "FAILED_VALIDATION", "rejected": [{"reason": "first"}, {}, {"reason": "second"}]}
            if case == "validation"
            else {"status": "VALIDATION_PASS", "rejected": []}
        ),
    )
    if case == "archive":
        _write_json(importer.lifecycle_root / f"{checksum}.json", {"import_result": "IMPORTED"})

    result = importer.inspect_candidate(source)

    assert dataclasses.astuple(result) == (
        source.resolve(),
        checksum,
        result.modified_at,
        "pkg-1",
        "WEBSITE_FOUNDATION",
        expected_status,
        expected_reason,
    )
    assert result.modified_at.endswith("+00:00")


def test_inspect_candidate_missing_source_preserves_file_not_found_exception(tmp_path: Path) -> None:
    importer = UniversalExternalWriterImporter(root=tmp_path)

    with pytest.raises(FileNotFoundError):
        importer.inspect_candidate(tmp_path / "missing.zip")
