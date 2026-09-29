"""Isolated characterization of external-writer return trust boundaries."""

from __future__ import annotations

import copy
import hashlib
import json
import zipfile
from pathlib import Path

import pytest

from modules.external_writer_pipeline import (
    QUEUE_SCHEMA,
    RETURN_SCHEMA,
    UniversalExternalWriterImporter,
    UniversalWriteQueue,
)
from modules.verified_writer_package import CONTRACT_SCHEMA


PACKAGE_ID = "trusted-security-fixture"
TASK_ID = "website_foundation-2026-09-29-security-fixture"
PRIMARY = "https://official.example/alpha"
SUPPORTING = "https://docs.example/alpha"
EVIDENCE_CHILD = "https://docs.example/alpha/features"
UNAUTHORIZED = "https://untrusted.example/new-claim"
CANONICAL = "https://smileaireviewhub.com/alpha-review/"
OUTPUT = "website/alpha-review"


def _json(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _fixture(tmp_path: Path) -> tuple[dict, dict, dict[str, bytes]]:
    task = {
        "schema_version": QUEUE_SCHEMA,
        "task_id": TASK_ID,
        "task_type": "WEBSITE_FOUNDATION",
        "workflow_lane": "FOUNDATION_MAIN",
        "batch_date": "2026-09-29",
        "article_slug": "alpha-review",
        "title": "Alpha Review",
        "primary_source_url": PRIMARY,
        "supporting_source_urls": [SUPPORTING],
        "target_output_paths": [
            f"{OUTPUT}/article.html",
            f"{OUTPUT}/article.md",
            f"{OUTPUT}/metadata.json",
            f"{OUTPUT}/validation.json",
        ],
        "revision": 1,
        "status": "EXPORTED",
        "package_id": PACKAGE_ID,
        "prior_website_titles": [],
        "internal_link_requirements": [],
        "website_url": CANONICAL,
        "exported_zip": "exports/external_writer/2026-09-29/trusted_package.zip",
    }
    contract = {
        "schema_version": CONTRACT_SCHEMA,
        "package_id": PACKAGE_ID,
        "tasks": [
            {
                **task,
                "allowed_source_urls": [PRIMARY, EVIDENCE_CHILD],
                "source_excerpts": [{"url": EVIDENCE_CHILD, "source_id": "source-002"}],
            }
        ],
    }
    trusted = tmp_path / task["exported_zip"]
    trusted.parent.mkdir(parents=True)
    with zipfile.ZipFile(trusted, "w") as archive:
        archive.writestr("manifest.json", _json({"package_id": PACKAGE_ID}))
        archive.writestr("verified_package_contract.json", _json(contract))
    UniversalWriteQueue(root=tmp_path).save(task)
    files = {
        f"{OUTPUT}/article.html": (
            '<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<title>Alpha Review</title>'
            f'<link rel="canonical" href="{CANONICAL}"></head><body>'
            f'<h1>Alpha Review</h1><p>Review the supplied <a href="{PRIMARY}">source</a>.</p>'
            "</body></html>"
        ).encode("utf-8"),
        f"{OUTPUT}/article.md": f"# Alpha Review\n\nRead {PRIMARY}.\n".encode("utf-8"),
        f"{OUTPUT}/metadata.json": _json(
            {
                "title": "Alpha Review",
                "canonical_url": CANONICAL,
                "source_urls": [PRIMARY],
            }
        ),
        f"{OUTPUT}/validation.json": _json(
            {"status": "passed", "research_utilization": {"citation_urls": [PRIMARY]}}
        ),
    }
    return task, contract, files


def _returned_zip(
    root: Path,
    contract: dict,
    files: dict[str, bytes],
    *,
    manifest_mutator=None,
    stale_hash: bool = False,
) -> Path:
    hashes = {name: _sha(content) for name, content in files.items()}
    if stale_hash:
        hashes[f"{OUTPUT}/article.md"] = "0" * 64
    manifest = {
        "schema_version": RETURN_SCHEMA,
        "package_id": PACKAGE_ID,
        "writer_name": "Fixture Writer",
        "writer_type": "external_ai",
        "writer_version": "test",
        "verified_package_contract": {
            "path": "verified_package_contract.json",
            "sha256": _sha(_json(contract)),
        },
        "items": [
            {
                "task_id": TASK_ID,
                "revision": 1,
                "output_root": OUTPUT,
                "files": hashes,
            }
        ],
    }
    if manifest_mutator:
        manifest_mutator(manifest)
    path = root / "returned.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("completed_manifest.json", _json(manifest))
        archive.writestr("verified_package_contract.json", _json(contract))
        for name, content in files.items():
            archive.writestr(name, content)
    return path


def _result(root: Path, contract: dict, files: dict[str, bytes], **kwargs) -> dict:
    path = _returned_zip(root, contract, files, **kwargs)
    return UniversalExternalWriterImporter(root=root).validate_zip(path)


def _reason(result: dict) -> str:
    return " ".join(str(row.get("reason") or "") for row in result.get("rejected", []))


def test_valid_trusted_contract_with_evidence_child_and_task_source(tmp_path: Path) -> None:
    _task, contract, files = _fixture(tmp_path)
    assert _result(tmp_path, contract, files)["status"] == "VALIDATION_PASS"


def test_disallowed_metadata_source_url_fails(tmp_path: Path) -> None:
    _task, contract, files = _fixture(tmp_path)
    metadata = json.loads(files[f"{OUTPUT}/metadata.json"])
    metadata["source_urls"].append(UNAUTHORIZED)
    files[f"{OUTPUT}/metadata.json"] = _json(metadata)
    result = _result(tmp_path, contract, files)
    assert result["status"] == "FAILED_VALIDATION"
    assert UNAUTHORIZED in _reason(result)


@pytest.mark.parametrize("name", ["article.html", "article.md"])
def test_disallowed_article_url_fails(tmp_path: Path, name: str) -> None:
    _task, contract, files = _fixture(tmp_path)
    key = f"{OUTPUT}/{name}"
    files[key] += f"\n{UNAUTHORIZED}\n".encode("utf-8")
    result = _result(tmp_path, contract, files)
    assert result["status"] == "FAILED_VALIDATION"
    assert UNAUTHORIZED in _reason(result)


def test_disallowed_validation_citation_url_fails(tmp_path: Path) -> None:
    _task, contract, files = _fixture(tmp_path)
    report = json.loads(files[f"{OUTPUT}/validation.json"])
    report["research_utilization"]["citation_urls"].append(UNAUTHORIZED)
    files[f"{OUTPUT}/validation.json"] = _json(report)
    result = _result(tmp_path, contract, files)
    assert result["status"] == "FAILED_VALIDATION"
    assert UNAUTHORIZED in _reason(result)


def test_disallowed_other_metadata_citation_url_fails(tmp_path: Path) -> None:
    _task, contract, files = _fixture(tmp_path)
    metadata = json.loads(files[f"{OUTPUT}/metadata.json"])
    metadata["citations"] = [{"source_url": UNAUTHORIZED}]
    files[f"{OUTPUT}/metadata.json"] = _json(metadata)
    result = _result(tmp_path, contract, files)
    assert result["status"] == "FAILED_VALIDATION"
    assert UNAUTHORIZED in _reason(result)


def test_disallowed_manifest_writer_url_fails(tmp_path: Path) -> None:
    _task, contract, files = _fixture(tmp_path)
    result = _result(
        tmp_path,
        contract,
        files,
        manifest_mutator=lambda manifest: manifest.update(
            {"writer": {"writer_name": "Fixture Writer", "profile_url": UNAUTHORIZED}}
        ),
    )
    assert result["status"] == "FAILED_VALIDATION"
    assert UNAUTHORIZED in _reason(result)


def test_rehashed_tampered_contract_fails_trusted_identity(tmp_path: Path) -> None:
    _task, contract, files = _fixture(tmp_path)
    altered = copy.deepcopy(contract)
    altered["tasks"][0]["allowed_source_urls"].append(UNAUTHORIZED)
    result = _result(tmp_path, altered, files)
    assert result["status"] == "FAILED_VALIDATION"
    assert "trusted contract identity mismatch" in _reason(result).lower()


def test_explicit_evidence_child_url_is_authorized(tmp_path: Path) -> None:
    _task, contract, files = _fixture(tmp_path)
    metadata = json.loads(files[f"{OUTPUT}/metadata.json"])
    metadata["source_urls"] = [EVIDENCE_CHILD]
    files[f"{OUTPUT}/metadata.json"] = _json(metadata)
    result = _result(tmp_path, contract, files)
    assert result["status"] == "VALIDATION_PASS"


def test_artifact_hash_mismatch_fails(tmp_path: Path) -> None:
    _task, contract, files = _fixture(tmp_path)
    result = _result(tmp_path, contract, files, stale_hash=True)
    assert result["status"] == "FAILED_VALIDATION"
    assert "Checksum mismatch" in _reason(result)
