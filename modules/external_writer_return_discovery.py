from __future__ import annotations

import hashlib
import json
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable


@dataclass(frozen=True)
class ImportCandidate:
    path: Path
    checksum: str
    modified_at: str = ""
    package_id: str = ""
    lane: str = ""
    status: str = "PENDING"
    reason: str = ""


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return default


def _text(value: Any) -> str:
    return str(value or "").strip()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class ExternalWriterReturnDiscovery:
    """Read-only discovery and classification of returned Writer packages."""

    def __init__(
        self,
        *,
        root: Path,
        queue: Any,
        validate_zip: Callable[[Path], dict[str, Any]],
        validate_archive_members: Callable[[zipfile.ZipFile], list[zipfile.ZipInfo]],
        read_zip_json: Callable[[zipfile.ZipFile, str], dict[str, Any]],
        normalize_completed_manifest: Callable[[dict[str, Any], zipfile.ZipFile], dict[str, Any]],
        immutable_website_states: set[str],
        protected_website_states: set[str],
        is_website_revision: Callable[[dict[str, Any]], bool],
    ) -> None:
        self.root = root
        self.queue = queue
        self.validate_zip = validate_zip
        self.validate_archive_members = validate_archive_members
        self.read_zip_json = read_zip_json
        self.normalize_completed_manifest = normalize_completed_manifest
        self.immutable_website_states = immutable_website_states
        self.protected_website_states = protected_website_states
        self.is_website_revision = is_website_revision
        self.data_dir = root / "data"
        self.history_root = self.data_dir / "import_history" / "external_writer"
        self.returned_root = root / "exports" / "external_writer" / "returned"
        self.lifecycle_root = self.history_root / "file_lifecycle"

    def discover(
        self,
        *,
        explicit: str = "",
        inspect_candidate: Callable[[Path], ImportCandidate] | None = None,
    ) -> list[ImportCandidate]:
        inspect = inspect_candidate or self.inspect_candidate
        paths: list[Path] = (
            [Path(explicit).expanduser()]
            if explicit
            else list(self.returned_root.glob("completed_drafts*.zip"))
            if self.returned_root.exists()
            else []
        )
        unique: dict[str, Path] = {}
        for path in paths:
            try:
                resolved = path.resolve()
            except OSError:
                continue
            if resolved.is_file() and resolved.suffix.lower() == ".zip":
                unique[str(resolved).lower()] = resolved
        candidates = [
            inspect(path)
            for path in sorted(unique.values(), key=lambda item: item.stat().st_mtime, reverse=True)
        ]
        return candidates if explicit else [row for row in candidates if row.status == "PENDING"]

    def audit_returned(
        self,
        *,
        inspect_candidate: Callable[[Path], ImportCandidate] | None = None,
    ) -> list[ImportCandidate]:
        """Classify Returned read-only; never changes workflow state or moves a file."""
        inspect = inspect_candidate or self.inspect_candidate
        if not self.returned_root.exists():
            return []
        paths = sorted(
            self.returned_root.glob("completed_drafts*.zip"),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )
        return [inspect(path) for path in paths if path.is_file()]

    def successful_import_index(self) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
        by_sha: dict[str, dict[str, Any]] = {}
        by_package: dict[str, dict[str, Any]] = {}
        if not self.history_root.exists():
            return by_sha, by_package
        for path in self.history_root.glob("*/*/import.json"):
            record = _read_json(path, {})
            if not isinstance(record, dict) or record.get("status") != "IMPORTED":
                continue
            if not record.get("imported"):
                continue
            checksum = _text(record.get("zip_sha256")).lower()
            package_id = _text(record.get("package_id"))
            payload = {**record, "history_path": str(path)}
            if checksum:
                by_sha.setdefault(checksum, payload)
            if package_id:
                by_package.setdefault(package_id, payload)
        return by_sha, by_package

    def manifest_identity(self, source: Path) -> tuple[str, str, str]:
        package_id = ""
        lane = ""
        try:
            with zipfile.ZipFile(source) as archive:
                self.validate_archive_members(archive)
                raw = self.read_zip_json(archive, "completed_manifest.json")
                manifest = self.normalize_completed_manifest(raw, archive)
                package_id = _text(manifest.get("package_id"))
                lanes = {_text(manifest.get("task_type"))} if manifest.get("task_type") else set()
                for item in manifest.get("items", []):
                    if isinstance(item, dict) and item.get("task_type"):
                        lanes.add(_text(item.get("task_type")))
                    task_id = _text(item.get("task_id")) if isinstance(item, dict) else ""
                    queued = self.queue.get(task_id) if task_id else None
                    if queued and queued.get("task_type"):
                        lanes.add(_text(queued.get("task_type")))
                lanes.discard("")
                if len(lanes) > 1:
                    return package_id, "", f"Completed ZIP mixes workflow lanes: {sorted(lanes)}"
                lane = next(iter(lanes), "")
        except (OSError, ValueError, zipfile.BadZipFile, UnicodeError, json.JSONDecodeError) as exc:
            return package_id, lane, str(exc)
        return package_id, lane, ""

    def protected_manifest_states(self, source: Path) -> list[dict[str, Any]]:
        """Identify stale website returns before validation/import prompts."""
        conflicts: list[dict[str, Any]] = []
        try:
            with zipfile.ZipFile(source) as archive:
                self.validate_archive_members(archive)
                raw = self.read_zip_json(archive, "completed_manifest.json")
                manifest = self.normalize_completed_manifest(raw, archive)
            for item in manifest.get("items", []):
                task_id = _text(item.get("task_id")) if isinstance(item, dict) else ""
                task = self.queue.get(task_id) if task_id else None
                if not task or not _text(task.get("task_type")).startswith("WEBSITE_"):
                    continue
                states = self.queue._website_states(task)
                protected = states & (
                    (
                        {"published", "published_local"}
                        if self.queue._invalidated_unpublished_approval(task)
                        else self.immutable_website_states
                    )
                    if self.is_website_revision(task)
                    else self.protected_website_states
                )
                if protected:
                    conflicts.append({"task_id": task_id, "states": sorted(protected)})
        except (OSError, ValueError, zipfile.BadZipFile, UnicodeError, json.JSONDecodeError):
            return []
        return conflicts

    def inspect_candidate(
        self,
        source: Path,
        *,
        manifest_identity: Callable[[Path], tuple[str, str, str]] | None = None,
        successful_import_index: Callable[
            [], tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]
        ] | None = None,
        protected_manifest_states: Callable[[Path], list[dict[str, Any]]] | None = None,
    ) -> ImportCandidate:
        identity = manifest_identity or self.manifest_identity
        successful = successful_import_index or self.successful_import_index
        protected_states = protected_manifest_states or self.protected_manifest_states
        resolved = source.resolve()
        checksum = _sha256(resolved)
        modified_at = datetime.fromtimestamp(resolved.stat().st_mtime, tz=UTC).isoformat()
        package_id, lane, identity_error = identity(resolved)
        lifecycle = _read_json(self.lifecycle_root / f"{checksum}.json", {})
        if lifecycle.get("import_result") == "IMPORTED" and not lifecycle.get("destination_path"):
            return ImportCandidate(
                resolved, checksum, modified_at, package_id, lane, "ARCHIVE_PENDING",
                "Import succeeded previously, but the archive move did not finish.",
            )
        by_sha, by_package = successful()
        if checksum.lower() in by_sha:
            return ImportCandidate(
                resolved, checksum, modified_at, package_id, lane, "DUPLICATE",
                "SHA-256 checksum was imported previously.",
            )
        if package_id and package_id in by_package:
            return ImportCandidate(
                resolved, checksum, modified_at, package_id, lane, "DUPLICATE",
                "package_id was imported previously.",
            )
        if identity_error:
            return ImportCandidate(
                resolved, checksum, modified_at, package_id, lane, "INVALID", identity_error,
            )
        protected = protected_states(resolved)
        if protected:
            details = "; ".join(
                f"{row['task_id']}: {', '.join(row['states'])}" for row in protected
            )
            return ImportCandidate(
                resolved,
                checksum,
                modified_at,
                package_id,
                lane,
                "STALE_PROTECTED",
                f"Package targets protected website state and is no longer pending ({details}).",
            )
        validation = self.validate_zip(resolved)
        if validation.get("status") != "VALIDATION_PASS":
            reasons = [
                _text(row.get("reason")) for row in validation.get("rejected", [])
                if isinstance(row, dict) and row.get("reason")
            ]
            return ImportCandidate(
                resolved, checksum, modified_at, package_id, lane, "INVALID",
                "; ".join(reasons) or "Shared completed-drafts validator failed.",
            )
        return ImportCandidate(resolved, checksum, modified_at, package_id, lane, "PENDING", "")
