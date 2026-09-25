"""Deterministic Phase 1A/1B non-authoritative observation CLI.

Production artifacts are read-only. All writes are confined to the top-level
``observability`` store, which is not a production authority.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
import shutil
import time
import unicodedata
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable


OBSERVATION_SCHEMA_VERSION = "architecture_observation_v1"
STORE_NAME = "observability"
DEFAULT_OBSERVATION_CONFIG = {
    "enabled": True,
    "lock_timeout_seconds": 5.0,
    "stale_lock_seconds": 30.0,
    "retention_enabled": True,
    "routine_run_retention_days": 30,
    "routine_run_max_count": 500,
    "health_summary_enabled": True,
}
CANONICAL_WORKFLOWS = {
    "WEBSITE_FOUNDATION", "WEBSITE_ADVANCED", "WEBSITE_UPDATE",
    "SOCIAL_WEBSITE_DISTRIBUTION", "SOCIAL_HOT_NEWS",
}
VOLATILE_KEYS = {
    "observed_at", "updated_at", "created_at", "generated_at", "checked_at",
    "approved_at", "approved_by", "published_at", "imported_at", "exported_at",
    "reviewed_at", "timestamp", "started_at", "completed_at", "attempt_number",
    "generation_attempt", "retry_count", "last_retry_at", "audit_history",
    "reviewer_notes", "operator_notes", "notes", "status_label", "absolute_path",
    "exported_zip", "verified_package_zip", "package_id", "writer",
}
AUTHORITATIVE_TASK_KEYS = {
    "task_type", "workflow_lane", "batch_date", "week_start", "root_topic_id",
    "series_id", "article_slug", "title", "normalized_title", "primary_keyword",
    "reader_intent", "reader_question", "search_intent", "daily_angle",
    "unique_thesis", "required_evidence", "prohibited_overlap", "content_goal",
    "article_type", "source_rules", "claim_safety_rules", "required_sections",
    "required_tables", "required_faq", "required_cta", "target_output_type",
    "target_output_paths", "primary_source_url", "supporting_source_urls",
    "source_files", "research_files", "what_is_known", "what_is_not_confirmed",
    "safe_wording_guidance", "fallback_level", "opportunity_type",
    "create_new_url", "preserve_slug", "existing_slug", "content_action",
}
APPROVED_STATES = {"human_approved", "approved", "approved_for_copy"}
PRODUCTION_OUTPUT_PREFIXES = (
    "data/editorial_queue", "data/write_queue", "data/research",
    "data/social_drafts", "data/import_history", "site_output", "exports",
    "upload", "docs",
)


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def read_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


class ObservationLockTimeout(TimeoutError):
    """A bounded observability-only lock wait expired."""


def observation_config(root: Path, store: Path | None = None) -> dict[str, Any]:
    resolved_store = _store(root, store)
    configured = read_json(resolved_store / "config.json", {})
    return {
        **DEFAULT_OBSERVATION_CONFIG,
        **(configured if isinstance(configured, dict) else {}),
    }


@contextmanager
def observation_lock(
    lock_path: Path,
    *,
    timeout_seconds: float = 5.0,
    stale_seconds: float = 30.0,
):
    """Portable Windows-safe lock using atomic directory creation."""
    deadline = time.monotonic() + max(0.0, timeout_seconds)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    while True:
        try:
            lock_path.mkdir()
            try:
                atomic_json(
                    lock_path / "owner.json",
                    {"pid": os.getpid(), "acquired_at": utc_now()},
                )
            except OSError:
                pass
            break
        except (FileExistsError, PermissionError):
            # On Windows a simultaneous directory create can surface as
            # ERROR_ACCESS_DENIED while the winning thread is creating files
            # inside the lock directory.  Treat it as ordinary contention.
            try:
                age = time.time() - lock_path.stat().st_mtime
                if age > max(1.0, stale_seconds):
                    shutil.rmtree(lock_path)
                    continue
            except OSError:
                pass
            if time.monotonic() >= deadline:
                raise ObservationLockTimeout(f"OBSERVATION_LOCK_TIMEOUT: {lock_path}")
            time.sleep(min(0.025, max(0.005, timeout_seconds / 10 or 0.005)))
    try:
        yield
    finally:
        try:
            shutil.rmtree(lock_path)
        except OSError:
            pass


def repo_reference(root: Path, path: Path | None) -> str | None:
    if path is None:
        return None
    resolved = path.resolve()
    try:
        return resolved.relative_to(root.resolve()).as_posix()
    except ValueError:
        return f"external:{resolved.name}"


def _normalize(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _normalize(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
            if str(key) not in VOLATILE_KEYS
        }
    if isinstance(value, list):
        return [_normalize(item) for item in value]
    if isinstance(value, tuple):
        return [_normalize(item) for item in value]
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value.replace("\r\n", "\n").replace("\r", "\n"))
    return value


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        _normalize(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def hash_json(value: Any) -> str:
    return sha256_bytes(canonical_json_bytes(value))


def normalized_text_bytes(path: Path) -> bytes:
    raw = path.read_bytes()
    text = raw.decode("utf-8-sig")
    normalized = unicodedata.normalize("NFC", text.replace("\r\n", "\n").replace("\r", "\n"))
    return normalized.encode("utf-8")


def hash_reference(path: Path | None) -> str | None:
    if path is None or not path.is_file():
        return None
    if path.suffix.casefold() == ".json":
        payload = read_json(path)
        return hash_json(payload) if payload is not None else sha256_bytes(path.read_bytes())
    return sha256_bytes(normalized_text_bytes(path))


def canonical_task_id(
    workflow_name: str,
    business_date_or_week: str,
    canonical_slug: str,
    content_action: str,
) -> str:
    identity = "|".join(
        ("canonical-task-v1", workflow_name, business_date_or_week, canonical_slug, content_action)
    )
    return sha256_bytes(identity.encode("utf-8"))


def content_action(task: dict[str, Any]) -> str:
    explicit = str(task.get("content_action") or "").strip().upper()
    if explicit:
        return explicit
    level = task.get("fallback_level")
    opportunity = str(task.get("opportunity_type") or "").casefold()
    if task.get("task_type") == "WEBSITE_UPDATE" or level == 3 or opportunity == "content_refresh":
        return "ADVANCED_REFRESH"
    if level == 2 or opportunity == "existing_root_expansion":
        return "EXISTING_ROOT_EXPANSION"
    return "NEW_OPPORTUNITY"


def is_approved_status(value: object) -> bool:
    return str(value or "").strip().casefold() in APPROVED_STATES


def mapping_for_state(root: Path, lane: str, state: object) -> tuple[str | None, str]:
    raw = str(state or "")
    payload = read_json(
        root / "tests/fixtures/architecture_contracts/legacy_state_mapping_v1.json", {}
    )
    for row in payload.get("mappings", []):
        if row.get("lane") == lane and str(row.get("legacy")) == raw:
            return str(row.get("canonical")), "EXACT" if raw == row.get("canonical") else "HIGH"
    if raw == "CANCELLED_BY_OPERATOR":
        return "HOLD", "AMBIGUOUS"
    return None, "LOW"


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    os.replace(temporary, path)


def append_unique(path: Path, value: dict[str, Any], id_field: str) -> bool:
    identifier = str(value.get(id_field) or "")
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.parent / ".locks" / f"{sha256_bytes(path.name.encode('utf-8'))}.lock"
    with observation_lock(lock_path):
        existing = path.read_text(encoding="utf-8") if path.is_file() else ""
        if identifier:
            for line in existing.splitlines():
                try:
                    if str(json.loads(line).get(id_field) or "") == identifier:
                        return False
                except json.JSONDecodeError as exc:
                    raise ValueError(f"Malformed observation JSONL: {path}") from exc
        line = json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n"
        temporary = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
        temporary.write_text(existing + line, encoding="utf-8", newline="\n")
        os.replace(temporary, path)
        return True


def _store(root: Path, requested: Path | None = None) -> Path:
    store = (requested or root / STORE_NAME).resolve()
    expected = (root / STORE_NAME).resolve()
    if store != expected and expected not in store.parents:
        raise ValueError(f"Observation output must stay beneath {expected}")
    reference = repo_reference(root, store) or ""
    if reference.startswith(PRODUCTION_OUTPUT_PREFIXES):
        raise ValueError(f"Observation output cannot use production store: {reference}")
    return store


def resolve_row(path: Path | None, slug: str) -> dict[str, Any]:
    if path is None or not path.is_file():
        return {}
    payload = read_json(path, {})
    if isinstance(payload, list):
        return next((row for row in payload if isinstance(row, dict) and str(row.get("slug") or "") == slug), {})
    if isinstance(payload, dict):
        rows = payload.get("items") or payload.get("tasks")
        if isinstance(rows, list):
            return next((row for row in rows if isinstance(row, dict) and str(row.get("slug") or row.get("article_slug") or "") == slug), {})
        return payload
    return {}


def authoritative_components(
    task: dict[str, Any], content_hash: str | None, source_hash: str | None
) -> dict[str, Any]:
    task_input = {key: task.get(key) for key in sorted(AUTHORITATIVE_TASK_KEYS) if key in task}
    claims = {
        key: task.get(key)
        for key in ("what_is_known", "what_is_not_confirmed", "required_evidence", "unique_thesis")
        if task.get(key) not in (None, "", [])
    }
    return {
        "task": task_input,
        "content_hash": content_hash,
        "source_package_hash": source_hash,
        "title_hash": hash_json(task.get("title") or ""),
        "keyword_brief_hash": hash_json(
            {key: task.get(key) for key in ("primary_keyword", "reader_intent", "reader_question", "search_intent")}
        ),
        "claims_hash": hash_json(claims),
    }


def revision_reason(previous: dict[str, Any], current: dict[str, Any]) -> str:
    old = previous.get("component_hashes") or {}
    if old.get("content_hash") != current.get("content_hash"):
        return "BODY_CHANGED"
    if old.get("source_package_hash") != current.get("source_package_hash"):
        return "SOURCE_PACKAGE_CHANGED"
    if old.get("claims_hash") != current.get("claims_hash"):
        return "CLAIMS_CHANGED"
    if old.get("title_hash") != current.get("title_hash"):
        return "AUTHORITATIVE_TITLE_CHANGED"
    if old.get("keyword_brief_hash") != current.get("keyword_brief_hash"):
        return "AUTHORITATIVE_KEYWORD_BRIEF_CHANGED"
    return "OTHER_AUTHORITATIVE_INPUT_CHANGED"


def contradiction_event(
    *,
    canonical_id: str,
    event_type: str,
    artifact_references: list[str],
    artifact_hashes: dict[str, str | None],
    observed_values: dict[str, Any],
    severity: str,
    safety_impact: str,
    confidence: str,
    recommended_future_policy: str,
) -> dict[str, Any]:
    stable = {
        "canonical_task_id": canonical_id,
        "type": event_type,
        "artifact_references": artifact_references,
        "artifact_hashes": artifact_hashes,
        "observed_values": observed_values,
    }
    return {
        "contradiction_id": hash_json(stable),
        "canonical_task_id": canonical_id,
        "detected_at": utc_now(),
        "severity": severity,
        "type": event_type,
        "artifact_references": artifact_references,
        "artifact_hashes": artifact_hashes,
        "observed_values": observed_values,
        "safety_impact": safety_impact,
        "confidence": confidence,
        "recommended_future_policy": recommended_future_policy,
        "resolved": False,
    }


class ArchitectureObserver:
    def __init__(self, root: Path, store: Path | None = None) -> None:
        self.root = root.resolve()
        self.store = _store(self.root, store)
        self.config = observation_config(self.root, self.store)

    def _lock_path(self, kind: str, identity: str) -> Path:
        digest = sha256_bytes(identity.encode("utf-8"))
        return self.store / ".locks" / f"{kind}-{digest}.lock"

    @contextmanager
    def _locked(self, kind: str, identity: str):
        with observation_lock(
            self._lock_path(kind, identity),
            timeout_seconds=float(self.config.get("lock_timeout_seconds") or 5.0),
            stale_seconds=float(self.config.get("stale_lock_seconds") or 30.0),
        ):
            yield

    def _append_contradiction(self, value: dict[str, Any]) -> None:
        append_unique(
            self.store / "contradictions/contradictions.jsonl",
            value,
            "contradiction_id",
        )

    def observe_task(
        self,
        task_path: Path,
        **kwargs: Any,
    ) -> dict[str, Any]:
        resolved = task_path.resolve()
        with self._locked("task", str(resolved).casefold()):
            return self._observe_task_unlocked(resolved, **kwargs)

    def _observe_task_unlocked(
        self,
        task_path: Path,
        *,
        content_path: Path | None = None,
        source_path: Path | None = None,
        approval_path: Path | None = None,
        publish_path: Path | None = None,
    ) -> dict[str, Any]:
        task_path = task_path.resolve()
        task = read_json(task_path)
        if not isinstance(task, dict):
            raise ValueError(f"Invalid task JSON: {task_path}")
        workflow = str(task.get("task_type") or task.get("workflow_lane") or "")
        if workflow not in CANONICAL_WORKFLOWS:
            raise ValueError(f"Unsupported observed workflow: {workflow}")
        slug = str(task.get("article_slug") or task.get("slug") or "")
        if not slug:
            raise ValueError("Observed task has no canonical slug")
        business_date = str(task.get("batch_date") or "") or None
        business_week = str(task.get("week_start") or "") or None
        identity_date = business_date or business_week or "unknown-date"
        action = content_action(task)
        canonical_id = canonical_task_id(workflow, identity_date, slug, action)
        current_path = self.store / "tasks" / canonical_id / "current.json"
        previous = read_json(current_path, None) if current_path.exists() else {}
        if not isinstance(previous, dict):
            raise ValueError(f"Malformed previous observation snapshot: {current_path}")
        content_hash = hash_reference(content_path)
        source_hash = hash_reference(source_path)
        components = authoritative_components(task, content_hash, source_hash)
        input_hash = hash_json(components)
        previous_hash = previous.get("input_hash") if isinstance(previous, dict) else None
        if previous_hash is None:
            revision = 1
            origin = "OBSERVATION_START"
            reason = None
        elif previous_hash == input_hash:
            revision = int(previous.get("observed_task_revision") or 1)
            origin = str(previous.get("revision_origin") or "OBSERVATION_START")
            reason = None
        else:
            revision = int(previous.get("observed_task_revision") or 1) + 1
            origin = "OBSERVED_CHANGE"
            reason = revision_reason(previous, components)

        legacy_state = str(task.get("status") or "") or None
        projected, confidence = mapping_for_state(self.root, "writer_exchange", legacy_state)
        approval = resolve_row(approval_path, slug)
        publish = resolve_row(publish_path, slug)
        approval_state = str(approval.get("status") or "") or None
        publish_state = str(publish.get("status") or "") or None
        prior_approval_state = str(previous.get("approval_observation_status") or "")
        previous_binding = str(previous.get("approval_binding_status") or "")
        previous_approval_hash = previous.get("approval_observed_hash")
        if is_approved_status(approval_state) and not previous:
            binding = "LEGACY_APPROVAL_UNBOUND"
            approval_observed_hash = None
        elif is_approved_status(approval_state) and not is_approved_status(prior_approval_state):
            binding = "OBSERVED_AT_APPROVAL_EVENT"
            approval_observed_hash = content_hash
        elif is_approved_status(approval_state) and previous_binding == "OBSERVED_AT_APPROVAL_EVENT":
            binding = previous_binding
            approval_observed_hash = previous_approval_hash
        elif approval_state:
            binding = "NOT_APPROVED"
            approval_observed_hash = None
        else:
            binding = None
            approval_observed_hash = None

        warnings: list[str] = []
        contradiction_types: list[str] = []
        if binding == "LEGACY_APPROVAL_UNBOUND":
            warnings.append("CANNOT_PROVE_HISTORICAL_CONTENT_CHANGE")
        if (
            binding == "OBSERVED_AT_APPROVAL_EVENT"
            and approval_observed_hash
            and content_hash
            and approval_observed_hash != content_hash
        ):
            event = contradiction_event(
                canonical_id=canonical_id,
                event_type="APPROVED_CONTENT_HASH_CHANGED",
                artifact_references=[ref for ref in (repo_reference(self.root, approval_path), repo_reference(self.root, content_path)) if ref],
                artifact_hashes={"approval_observed_hash": approval_observed_hash, "current_content_hash": content_hash},
                observed_values={"approval_observed_revision": previous.get("approval_observed_revision"), "current_observed_revision": revision},
                severity="HIGH",
                safety_impact="Observed content no longer matches the hash captured at approval observation.",
                confidence="EXACT",
                recommended_future_policy="Phase 3 approval invalidation; no Phase 1A enforcement.",
            )
            self._append_contradiction(event)
            contradiction_types.append(event["type"])
        if is_approved_status(approval_state) and publish_state == "blocked":
            event = contradiction_event(
                canonical_id=canonical_id,
                event_type="HUMAN_APPROVED_BUT_PUBLISH_BLOCKED",
                artifact_references=[ref for ref in (repo_reference(self.root, approval_path), repo_reference(self.root, publish_path)) if ref],
                artifact_hashes={"approval": hash_reference(approval_path), "publish": hash_reference(publish_path)},
                observed_values={"approval": approval_state, "publish": publish_state},
                severity="MEDIUM",
                safety_impact="Approval and publish projection differ; current gate remains safely blocking.",
                confidence="HIGH",
                recommended_future_policy="Keep separate authorities and expose the active blocker.",
            )
            self._append_contradiction(event)
            contradiction_types.append(event["type"])
        gate_enabled = bool(
            (read_json(self.root / "config/editorial_system.json", {}) or {})
            .get("publish_gate", {})
            .get("enabled", False)
        )
        if not gate_enabled and publish_state == "approved_for_publish":
            event = contradiction_event(
                canonical_id=canonical_id,
                event_type="KNOWN_FAIL_OPEN_BRANCH_OBSERVED",
                artifact_references=[ref for ref in ("config/editorial_system.json", repo_reference(self.root, publish_path)) if ref],
                artifact_hashes={"publish": hash_reference(publish_path)},
                observed_values={"publish_gate_enabled": False, "legacy_gate_result": publish_state},
                severity="HIGH",
                safety_impact="Disabled gate semantically permits publication.",
                confidence="EXACT",
                recommended_future_policy="Fail closed in Phase 3/4.",
            )
            self._append_contradiction(event)
            contradiction_types.append(event["type"])

        stable_observation = {
            "canonical_task_id": canonical_id,
            "legacy_task_id": task.get("task_id"),
            "observed_task_revision": revision,
            "input_hash": input_hash,
            "legacy_state": legacy_state,
            "approval_observation_status": approval_state,
            "publish_observation_status": publish_state,
        }
        observation = {
            "observation_schema_version": OBSERVATION_SCHEMA_VERSION,
            "observation_id": hash_json(stable_observation),
            "observed_at": utc_now(),
            "canonical_task_id": canonical_id,
            "legacy_task_id": task.get("task_id"),
            "workflow_name": workflow,
            "business_date": business_date,
            "business_week": business_week,
            "canonical_slug": slug,
            "content_action": action,
            "observed_task_revision": revision,
            "revision_origin": origin,
            "previous_input_hash": previous_hash,
            "current_input_hash": input_hash,
            "revision_reason": reason,
            "event_type": (
                "TASK_FIRST_OBSERVED"
                if previous_hash is None
                else "TASK_REVISION_CHANGED"
                if reason
                else "TASK_SNAPSHOT_UNCHANGED"
            ),
            "legacy_state": legacy_state,
            "canonical_state_projection": projected,
            "legacy_substatus": legacy_state,
            "mapping_confidence": confidence,
            "authority_source": repo_reference(self.root, task_path),
            "input_reference": repo_reference(self.root, task_path),
            "input_hash": input_hash,
            "content_reference": repo_reference(self.root, content_path),
            "content_hash": content_hash,
            "source_reference": repo_reference(self.root, source_path),
            "source_package_hash": source_hash,
            "approval_reference": repo_reference(self.root, approval_path),
            "approval_observation_status": approval_state,
            "approval_binding_status": binding,
            "approval_observed_hash": approval_observed_hash,
            "approval_observed_revision": revision if binding == "OBSERVED_AT_APPROVAL_EVENT" and not is_approved_status(prior_approval_state) else previous.get("approval_observed_revision"),
            "publish_reference": repo_reference(self.root, publish_path),
            "publish_observation_status": publish_state,
            "publish_gate_enabled": gate_enabled,
            "canonical_safety_projection": "BLOCKED" if publish_state == "blocked" else "READY_FOR_PUBLISH" if publish_state == "approved_for_publish" and gate_enabled and is_approved_status(approval_state) else "NOT_EVALUATED",
            "component_hashes": components,
            "provenance": {
                "observer": "PHASE_1A_DETERMINISTIC",
                "production_authority": False,
                "network_used": False,
                "paid_api_used": False,
            },
            "warnings": warnings,
            "contradictions": contradiction_types,
        }
        atomic_json(current_path, observation)
        append_unique(current_path.parent / "events.jsonl", observation, "observation_id")
        if approval_state:
            approval_event = {
                "approval_observation_id": hash_json({"canonical_task_id": canonical_id, "status": approval_state, "binding": binding, "content_hash": approval_observed_hash}),
                "event_type": "APPROVAL_OBSERVED",
                "observed_at": observation["observed_at"],
                "canonical_task_id": canonical_id,
                "observed_task_revision": revision,
                "legacy_approval_status": approval_state,
                "approved_by": approval.get("approved_by"),
                "approved_at": approval.get("approved_at"),
                "current_content_hash": content_hash,
                "content_hash_at_observation_time": approval_observed_hash,
                "approval_binding_status": binding,
                "approval_scope": "WEBSITE_ARTICLE",
                "approval_reference": observation["approval_reference"],
                "production_authority": False,
            }
            append_unique(
                self.store / "approvals/approval_observations.jsonl",
                approval_event,
                "approval_observation_id",
            )
        self._write_run_summary("task", [observation["observation_id"]], warnings)
        return observation

    def observe_social(self, metadata_path: Path, *, task_path: Path | None = None) -> dict[str, Any]:
        resolved = metadata_path.resolve()
        with self._locked("social", str(resolved).casefold()):
            return self._observe_social_unlocked(resolved, task_path=task_path)

    def _observe_social_unlocked(self, metadata_path: Path, *, task_path: Path | None = None) -> dict[str, Any]:
        metadata_path = metadata_path.resolve()
        metadata = read_json(metadata_path)
        if not isinstance(metadata, dict):
            raise ValueError(f"Invalid social metadata: {metadata_path}")
        task = read_json(task_path, {}) if task_path else {}
        if not isinstance(task, dict):
            task = {}
        slug = str(metadata.get("article_slug") or task.get("article_slug") or metadata_path.parent.parent.name)
        platform = str(metadata.get("platform") or metadata_path.parent.name).casefold()
        workflow = str(task.get("task_type") or "")
        legacy_task_id = str(metadata.get("task_id") or task.get("task_id") or "")
        if not workflow:
            workflow = "SOCIAL_HOT_NEWS" if legacy_task_id.startswith("social_hot_news") or str(metadata.get("content_lane") or "").startswith("SOCIAL_HOT") else "SOCIAL_WEBSITE_DISTRIBUTION"
        business_date = str(task.get("batch_date") or metadata_path.parts[-4])
        action = content_action(task) if task else "NEW_OPPORTUNITY"
        parent_id = canonical_task_id(workflow, business_date, slug, action)
        selected = str(metadata.get("selected_variant") or "A.md")
        content_path = metadata_path.parent / selected
        platform_hash = hash_reference(content_path)
        shared_source_hash = hash_json(sorted(str(url) for url in metadata.get("source_urls") or []))
        current_path = self.store / "social" / parent_id / platform / "current.json"
        previous = read_json(current_path, {})
        previous_platform_hash = previous.get("platform_content_hash")
        previous_shared_hash = previous.get("shared_source_hash")
        platform_revision = int(previous.get("platform_revision") or 1)
        reason = None
        if previous and previous_platform_hash != platform_hash:
            platform_revision += 1
            reason = "PLATFORM_CONTENT_CHANGED"
        legacy_status = str(metadata.get("status") or "")
        projected, confidence = mapping_for_state(self.root, "social", legacy_status)
        prior_status = str(previous.get("legacy_platform_status") or "")
        prior_binding = str(previous.get("approval_binding_status") or "")
        prior_approved_hash = previous.get("approval_observed_hash")
        approval_present = (
            is_approved_status(legacy_status)
            or metadata.get("approved_for_copy") is True
            or legacy_status.casefold() in {"published", "published_manual"}
        )
        prior_approval_present = bool(previous.get("approval_present"))
        legacy_observer_upgrade = (
            bool(previous)
            and "approval_present" not in previous
            and approval_present
            and prior_status == legacy_status
        )
        if approval_present and (not previous or legacy_observer_upgrade):
            binding = "LEGACY_APPROVAL_UNBOUND"
            observed_approval_hash = None
        elif approval_present and not prior_approval_present:
            binding = "OBSERVED_AT_APPROVAL_EVENT"
            observed_approval_hash = platform_hash
        elif approval_present and prior_binding == "OBSERVED_AT_APPROVAL_EVENT":
            binding = prior_binding
            observed_approval_hash = prior_approved_hash
        else:
            binding = "NOT_APPROVED" if legacy_status else None
            observed_approval_hash = None
        contradictions: list[str] = []
        if binding == "OBSERVED_AT_APPROVAL_EVENT" and observed_approval_hash and platform_hash and observed_approval_hash != platform_hash:
            event = contradiction_event(
                canonical_id=parent_id,
                event_type="POTENTIAL_STALE_PLATFORM_APPROVAL",
                artifact_references=[repo_reference(self.root, metadata_path) or "", repo_reference(self.root, content_path) or ""],
                artifact_hashes={"approval_observed_hash": observed_approval_hash, "platform_content_hash": platform_hash},
                observed_values={"platform": platform, "approval_status": legacy_status, "platform_revision": platform_revision},
                severity="HIGH",
                safety_impact="Observed platform content differs from its approval-observation hash.",
                confidence="EXACT",
                recommended_future_policy="Invalidate only this unpublished platform in Phase 3.",
            )
            self._append_contradiction(event)
            contradictions.append(event["type"])
        if previous and previous_shared_hash != shared_source_hash:
            event = contradiction_event(
                canonical_id=parent_id,
                event_type="SHARED_SOURCE_CHANGED",
                artifact_references=[repo_reference(self.root, metadata_path) or ""],
                artifact_hashes={"previous_shared_source_hash": previous_shared_hash, "shared_source_hash": shared_source_hash},
                observed_values={"platform": platform},
                severity="HIGH",
                safety_impact="Shared evidence changed and may affect multiple platforms.",
                confidence="EXACT",
                recommended_future_policy="Review affected unpublished platforms; never rewrite published history.",
            )
            self._append_contradiction(event)
            contradictions.append(event["type"])
        stable = {"parent": parent_id, "platform": platform, "platform_revision": platform_revision, "platform_hash": platform_hash, "shared_source_hash": shared_source_hash, "status": legacy_status}
        observation = {
            "social_observation_schema_version": "social_platform_observation_v1",
            "social_observation_id": hash_json(stable),
            "observed_at": utc_now(),
            "parent_canonical_task_id": parent_id,
            "legacy_task_id": legacy_task_id or None,
            "workflow_name": workflow,
            "business_date": business_date,
            "canonical_slug": slug,
            "shared_source_hash": shared_source_hash,
            "platform": platform,
            "platform_revision": platform_revision,
            "platform_content_hash": platform_hash,
            "platform_content_reference": repo_reference(self.root, content_path),
            "legacy_platform_status": legacy_status,
            "canonical_platform_projection": projected,
            "mapping_confidence": confidence,
            "approved_at": metadata.get("approved_at"),
            "published_at": metadata.get("published_at"),
            "approval_binding_status": binding,
            "approval_present": approval_present,
            "approval_observed_hash": observed_approval_hash,
            "revision_reason": reason,
            "event_type": (
                "PLATFORM_FIRST_OBSERVED"
                if not previous
                else "PLATFORM_REVISION_CHANGED"
                if reason
                else "PLATFORM_SNAPSHOT_UNCHANGED"
            ),
            "provenance": {"metadata_reference": repo_reference(self.root, metadata_path), "production_authority": False, "network_used": False, "paid_api_used": False},
            "warnings": ["CANNOT_PROVE_HISTORICAL_CONTENT_CHANGE"] if binding == "LEGACY_APPROVAL_UNBOUND" else [],
            "contradictions": contradictions,
        }
        atomic_json(current_path, observation)
        append_unique(
            self.store / "social/platform_observations.jsonl",
            observation,
            "social_observation_id",
        )
        self._write_run_summary("social", [observation["social_observation_id"]], observation["warnings"])
        return observation

    def observe_sources(self, source_path: Path) -> dict[str, Any]:
        resolved = source_path.resolve()
        with self._locked("source", str(resolved).casefold()):
            return self._observe_sources_unlocked(resolved)

    def _observe_sources_unlocked(self, source_path: Path) -> dict[str, Any]:
        source_path = source_path.resolve()
        payload = read_json(source_path)
        if not isinstance(payload, dict):
            raise ValueError(f"Invalid source artifact: {source_path}")
        rows = payload.get("verified_sources") or payload.get("sources") or []
        if not isinstance(rows, list):
            rows = []
        if not rows and isinstance(payload.get("trusted_sources"), dict):
            rows = [row for values in payload["trusted_sources"].values() if isinstance(values, list) for row in values if isinstance(row, dict)]
        observations = []
        for row in rows:
            url = str(row.get("url") or row.get("source_url") or "")
            provenance = str(row.get("provenance") or "")
            verified_by = str(row.get("verified_by") or "").casefold()
            if provenance == "MANUAL_OPERATOR" or verified_by in {"operator", "human", "editor"}:
                method = "MANUAL_OPERATOR"
                confidence = "HIGH"
            elif verified_by in {"system", "auto", "automated"} or provenance:
                method = "AUTOMATED"
                confidence = "HIGH" if verified_by else "MEDIUM"
            else:
                method = "UNKNOWN"
                confidence = "AMBIGUOUS"
            raw = str(row.get("verification_status") or row.get("status") or "").casefold()
            verification = "VERIFIED" if raw in {"verified", "approved"} else "REJECTED" if raw == "rejected" else "PENDING"
            operator = "APPROVED" if method == "MANUAL_OPERATOR" and verification == "VERIFIED" else "REJECTED" if method == "MANUAL_OPERATOR" and verification == "REJECTED" else "UNKNOWN" if method == "UNKNOWN" else "NOT_REVIEWED"
            source_id = str(row.get("source_id") or row.get("id") or sha256_bytes(url.encode("utf-8"))[:16])
            observation = {
                "source_observation_schema_version": "source_observation_v1",
                "source_observation_id": hash_json({"source_id": source_id, "url": url, "artifact_hash": hash_reference(source_path)}),
                "source_id": source_id,
                "source_url": url,
                "verification_method": method,
                "verification_status": verification,
                "operator_approval_status": operator,
                "provenance": provenance or verified_by or "UNKNOWN",
                "source_content_hash": None,
                "observed_at": utc_now(),
                "mapping_confidence": confidence,
                "artifact_reference": repo_reference(self.root, source_path),
                "production_authority": False,
            }
            append_unique(self.store / "source/source_observations.jsonl", observation, "source_observation_id")
            observations.append(observation)
            if confidence == "AMBIGUOUS":
                event = contradiction_event(
                    canonical_id=sha256_bytes(("source|" + source_id).encode()),
                    event_type="SOURCE_VERIFICATION_AMBIGUITY",
                    artifact_references=[repo_reference(self.root, source_path) or ""],
                    artifact_hashes={"source_artifact_hash": hash_reference(source_path)},
                    observed_values={"source_id": source_id, "verification_method": method, "operator_approval_status": operator},
                    severity="MEDIUM",
                    safety_impact="Automated verification cannot be distinguished from operator approval.",
                    confidence="AMBIGUOUS",
                    recommended_future_policy="Preserve UNKNOWN and collect explicit provenance; never infer operator approval.",
                )
                self._append_contradiction(event)
        result = {"artifact": repo_reference(self.root, source_path), "artifact_hash": hash_reference(source_path), "observed_count": len(observations), "ambiguous_count": sum(1 for row in observations if row["mapping_confidence"] == "AMBIGUOUS")}
        self._write_run_summary("source", [row["source_observation_id"] for row in observations], [])
        return result

    def observe_research(self, research_dir: Path) -> dict[str, Any]:
        resolved = research_dir.resolve()
        with self._locked("research", str(resolved).casefold()):
            return self._observe_research_unlocked(resolved)

    def _observe_research_unlocked(self, research_dir: Path) -> dict[str, Any]:
        research_dir = research_dir.resolve()
        if not research_dir.is_dir():
            raise ValueError(f"Missing research directory: {research_dir}")
        files = {path.name: path for path in research_dir.glob("*.json") if path.is_file()}
        def matching(*names: str) -> list[Path]:
            return [files[name] for name in names if name in files]
        def combined(paths: list[Path]) -> str | None:
            return hash_json({path.name: hash_reference(path) for path in sorted(paths)}) if paths else None
        source_files = matching("sources.json", "source_inventory.json")
        evidence_files = matching("claims.json", "evidence_coverage.json", "research_quality.json")
        entity_files = matching("entities.json", "entity_coverage.json")
        package_files = matching("package.json", "research_package.json")
        source_payload = read_json(source_files[0], {}) if source_files else {}
        result = {
            "research_observation_schema_version": "research_observation_v1",
            "research_observation_id": "",
            "observed_at": utc_now(),
            "slug": research_dir.name,
            "observation_kind": "DERIVED_OBSERVATION",
            "source_inventory_hash": combined(source_files),
            "source_verification_summary": {
                "verified": len(source_payload.get("verified_sources") or []),
                "pending": len(source_payload.get("pending_sources") or []),
                "rejected": len(source_payload.get("rejected_sources") or []),
            },
            "operator_approval_summary": "UNKNOWN_WHEN_PROVENANCE_ABSENT",
            "evidence_coverage_hash": combined(evidence_files),
            "entity_coverage_hash": combined(entity_files),
            "research_eligibility_observation": source_payload.get("source_status") or "UNKNOWN",
            "research_package_hash": combined(package_files),
            "artifact_references": [repo_reference(self.root, path) for path in sorted(files.values())],
            "production_authority": False,
        }
        result["research_observation_id"] = hash_json({key: value for key, value in result.items() if key not in {"observed_at", "research_observation_id"}})
        append_unique(self.store / "research/research_observations.jsonl", result, "research_observation_id")
        self._write_run_summary("research", [result["research_observation_id"]], [])
        return result

    def observe_deep_dive(self, plan_path: Path) -> dict[str, Any]:
        resolved = plan_path.resolve()
        with self._locked("deep-dive", str(resolved).casefold()):
            return self._observe_deep_dive_unlocked(resolved)

    def _observe_deep_dive_unlocked(self, plan_path: Path) -> dict[str, Any]:
        plan_path = plan_path.resolve()
        payload = read_json(plan_path)
        if not isinstance(payload, dict):
            raise ValueError(f"Invalid deep-dive plan: {plan_path}")
        source_week = str(payload.get("source_week") or plan_path.parent.name)
        target_week = str(payload.get("target_week") or "")
        result = {
            "deep_dive_observation_schema_version": "deep_dive_observation_v1",
            "observation_id": "",
            "observed_at": utc_now(),
            "source_week": source_week,
            "target_week": target_week,
            "physical_path": repo_reference(self.root, plan_path),
            "business_owner_week": target_week,
            "plan_hash": hash_reference(plan_path),
            "production_authority": False,
        }
        result["observation_id"] = hash_json({key: value for key, value in result.items() if key not in {"observation_id", "observed_at"}})
        index_path = self.store / "deep_dive/target_week_index.json"
        with self._locked("deep-dive-index", target_week or "unknown-target-week"):
            index = read_json(index_path, {})
            if not isinstance(index, dict):
                index = {}
            index[target_week] = {"source_week": source_week, "physical_path": result["physical_path"], "plan_hash": result["plan_hash"], "observation_id": result["observation_id"], "authority": False}
            atomic_json(index_path, index)
        append_unique(self.store / "deep_dive/deep_dive_observations.jsonl", result, "observation_id")
        self._write_run_summary("deep_dive", [result["observation_id"]], [])
        return result

    def observe_transition(
        self,
        task_path: Path,
        from_state: str,
        to_state: str,
    ) -> dict[str, Any]:
        identity = f"{task_path.resolve()}|{from_state}|{to_state}"
        with self._locked("transition", identity.casefold()):
            return self._observe_transition_unlocked(task_path.resolve(), from_state, to_state)

    def _observe_transition_unlocked(
        self,
        task_path: Path,
        from_state: str,
        to_state: str,
    ) -> dict[str, Any]:
        task = read_json(task_path)
        if not isinstance(task, dict):
            raise ValueError(f"Invalid transition task: {task_path}")
        workflow = str(task.get("task_type") or "")
        slug = str(task.get("article_slug") or "")
        business = str(task.get("batch_date") or task.get("week_start") or "unknown-date")
        cid = canonical_task_id(workflow, business, slug, content_action(task))
        canonical_from, _ = mapping_for_state(self.root, "writer_exchange", from_state)
        canonical_to, _ = mapping_for_state(self.root, "writer_exchange", to_state)
        allowed_pairs = {
            ("QUEUED", "EXPORTED"), ("EDIT_REQUIRED", "EXPORTED"),
            ("EXPORTED", "RETURNED"), ("RETURNED", "VALIDATING"),
            ("VALIDATING", "IMPORTED"), ("IMPORTED", "QA_REQUIRED"),
            ("QA_REQUIRED", "EDIT_REQUIRED"),
        }
        if canonical_from and canonical_to and (canonical_from, canonical_to) in allowed_pairs:
            policy = "ALLOWED"
        elif to_state in {"FAILED_IMPORT", "NEEDS_REVIEW", "REVISION_REQUESTED"}:
            policy = "AMBIGUOUS"
        else:
            policy = "NOT_ALLOWED"
        stable = {"canonical_task_id": cid, "from": from_state, "to": to_state, "policy": policy, "task_hash": hash_reference(task_path)}
        result = {
            "transition_observation_schema_version": "transition_observation_v1",
            "transition_observation_id": hash_json(stable),
            "observed_at": utc_now(),
            "canonical_task_id": cid,
            "from_legacy_state": from_state,
            "to_legacy_state": to_state,
            "canonical_from": canonical_from,
            "canonical_to": canonical_to,
            "policy_v1_result": policy,
            "task_reference": repo_reference(self.root, task_path),
            "production_transition_blocked": False,
        }
        append_unique(self.store / "transition/transition_observations.jsonl", result, "transition_observation_id")
        if policy != "ALLOWED":
            event = contradiction_event(
                canonical_id=cid,
                event_type="TRANSITION_POLICY_MISMATCH",
                artifact_references=[repo_reference(self.root, task_path) or ""],
                artifact_hashes={"task_hash": hash_reference(task_path)},
                observed_values={"from": from_state, "to": to_state, "policy_v1_result": policy},
                severity="MEDIUM" if policy == "AMBIGUOUS" else "HIGH",
                safety_impact="Current production edge does not cleanly match future Transition Policy V1.",
                confidence="HIGH",
                recommended_future_policy="Observe only until Phase 4 compatibility policy is approved.",
            )
            self._append_contradiction(event)
        self._write_run_summary("transition", [result["transition_observation_id"]], [])
        return result

    def observe_business_event(
        self,
        event_type: str,
        *,
        menu: str,
        artifact_paths: list[Path],
        canonical_task_id_value: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        references = [repo_reference(self.root, path) for path in artifact_paths if path.exists()]
        hashes = {
            reference: hash_reference(path)
            for path, reference in zip(
                [path for path in artifact_paths if path.exists()],
                references,
                strict=False,
            )
            if reference
        }
        stable = {
            "event_type": event_type,
            "menu": menu,
            "canonical_task_id": canonical_task_id_value,
            "artifact_hashes": hashes,
            "details": details or {},
        }
        event = {
            "business_event_schema_version": "observation_business_event_v1",
            "business_event_id": hash_json(stable),
            "event_type": event_type,
            "event_class": "BUSINESS_EVENT",
            "observed_at": utc_now(),
            "menu": menu,
            "canonical_task_id": canonical_task_id_value,
            "artifact_references": references,
            "artifact_hashes": hashes,
            "details": details or {},
            "production_authority": False,
        }
        append_unique(
            self.store / "events/business_events.jsonl",
            event,
            "business_event_id",
        )
        return event

    def _task_files_for_date(self, business_date: str) -> list[Path]:
        rows: list[Path] = []
        for path in (self.root / "data/write_queue").glob("*.json"):
            payload = read_json(path, {})
            if isinstance(payload, dict) and str(payload.get("batch_date") or "") == business_date:
                rows.append(path)
        return sorted(rows)

    def _latest_active_date(self) -> str:
        dates: list[str] = []
        for path in (self.root / "data/write_queue").glob("*.json"):
            payload = read_json(path, {})
            if isinstance(payload, dict) and str(payload.get("batch_date") or ""):
                dates.append(str(payload["batch_date"]))
        return max(dates) if dates else datetime.now().date().isoformat()

    @staticmethod
    def _latest_dated_directory(parent: Path) -> str | None:
        dates = [path.name for path in parent.iterdir() if path.is_dir() and len(path.name) == 10 and path.name[4:5] == "-" and path.name[7:8] == "-"] if parent.is_dir() else []
        return max(dates) if dates else None

    def _task_path_for_social(self, business_date: str, slug: str, task_id: str = "") -> Path | None:
        for path in self._task_files_for_date(business_date):
            payload = read_json(path, {})
            if not isinstance(payload, dict):
                continue
            if task_id and str(payload.get("task_id") or "") == task_id:
                return path
            if str(payload.get("article_slug") or "") == slug:
                return path
        return None

    def observe_live(self, *, menu: str, business_date: str = "latest") -> dict[str, Any]:
        """Observe only artifacts touched by a normal current operator boundary."""
        if not bool(self.config.get("enabled", True)):
            return {
                "ok": True,
                "enabled": False,
                "menu": menu,
                "production_state_changed": False,
                "observations": 0,
                "warnings": [],
            }
        normalized_menu = menu.strip().upper().removeprefix("MENU_")
        if business_date != "latest":
            resolved_date = business_date
        elif normalized_menu == "W":
            resolved_date = self._latest_dated_directory(self.root / "data/import_history/external_writer") or self._latest_active_date()
        elif normalized_menu == "X":
            resolved_date = self._latest_dated_directory(self.root / "exports/external_writer") or self._latest_active_date()
        else:
            resolved_date = self._latest_active_date()
        type_filters = {
            "1": {"WEBSITE_FOUNDATION"},
            "2": {"WEBSITE_ADVANCED", "WEBSITE_UPDATE"},
            "F": {"SOCIAL_WEBSITE_DISTRIBUTION"},
            "H": {"SOCIAL_HOT_NEWS"},
        }
        task_paths = self._task_files_for_date(resolved_date)
        if normalized_menu in type_filters:
            task_paths = [
                path
                for path in task_paths
                if str((read_json(path, {}) or {}).get("task_type") or "") in type_filters[normalized_menu]
            ]
        observed_ids: list[str] = []
        observed_tasks: list[dict[str, Any]] = []
        warnings: list[str] = []
        approval_queue = self.root / "data/human_approval_queue.json"
        publish_queue = self.root / "data/publish_queue.json"
        task_slugs: set[str] = set()
        weeks: set[str] = set()
        for task_path in task_paths:
            task = read_json(task_path, {})
            if not isinstance(task, dict):
                continue
            slug = str(task.get("article_slug") or "")
            if slug:
                task_slugs.add(slug)
            if task.get("week_start"):
                weeks.add(str(task["week_start"]))
            source_path: Path | None = None
            references = list(task.get("research_files") or []) + list(task.get("source_files") or [])
            for reference in references:
                candidate = self.root / str(reference)
                if candidate.is_file():
                    source_path = candidate
                    break
            content_candidates = [
                self.root / "data/production_article_drafts" / slug / "article.md",
                self.root / "upload" / resolved_date / "drafts" / slug / "article.md",
            ]
            content_path = next((path for path in content_candidates if path.is_file()), None)
            workflow = str(task.get("task_type") or "")
            identity_date = str(task.get("batch_date") or task.get("week_start") or "unknown-date")
            cid = canonical_task_id(workflow, identity_date, slug, content_action(task))
            previous = read_json(self.store / "tasks" / cid / "current.json", {})
            previous_state = str(previous.get("legacy_state") or "") if isinstance(previous, dict) else ""
            result = self.observe_non_blocking(
                self.observe_task,
                task_path,
                content_path=content_path,
                source_path=source_path,
                approval_path=approval_queue if approval_queue.is_file() else None,
                publish_path=publish_queue if publish_queue.is_file() else None,
            )
            if result.get("ok"):
                observation = result["observation"]
                observed_ids.append(str(observation.get("observation_id") or ""))
                observed_tasks.append({
                    "canonical_task_id": observation.get("canonical_task_id"),
                    "legacy_task_id": observation.get("legacy_task_id"),
                    "observed_task_revision": observation.get("observed_task_revision"),
                    "input_hash": observation.get("input_hash"),
                    "content_hash": observation.get("content_hash"),
                    "legacy_state": observation.get("legacy_state"),
                    "canonical_state_projection": observation.get("canonical_state_projection"),
                })
                current_state = str(observation.get("legacy_state") or "")
                if previous_state and current_state and previous_state != current_state:
                    transition = self.observe_non_blocking(
                        self.observe_transition,
                        task_path,
                        previous_state,
                        current_state,
                    )
                    if not transition.get("ok"):
                        warnings.append(str(transition.get("warning") or "OBSERVATION_FAILED"))
            else:
                warnings.append(str(result.get("warning") or "OBSERVATION_FAILED"))

            research_dir = self.root / "data/research" / slug
            if normalized_menu in {"1", "2", "S"} and research_dir.is_dir():
                source_inventory = research_dir / "sources.json"
                if source_inventory.is_file():
                    source_result = self.observe_non_blocking(self.observe_sources, source_inventory)
                    if not source_result.get("ok"):
                        warnings.append(str(source_result.get("warning") or "OBSERVATION_FAILED"))
                research_result = self.observe_non_blocking(self.observe_research, research_dir)
                if not research_result.get("ok"):
                    warnings.append(str(research_result.get("warning") or "OBSERVATION_FAILED"))

        if normalized_menu == "S":
            for source_path in (self.root / "data/research").glob("*/sources.json"):
                try:
                    touched_date = datetime.fromtimestamp(source_path.stat().st_mtime).date().isoformat()
                except OSError:
                    continue
                if touched_date == resolved_date and source_path.parent.name not in task_slugs:
                    source_result = self.observe_non_blocking(self.observe_sources, source_path)
                    if not source_result.get("ok"):
                        warnings.append(str(source_result.get("warning") or "OBSERVATION_FAILED"))

        if normalized_menu in {"F", "W", "H", "G", "E"}:
            social_root = self.root / "data/social_drafts" / resolved_date
            for metadata_path in social_root.glob("*/*/metadata.json") if social_root.is_dir() else []:
                slug = metadata_path.parent.parent.name
                metadata = read_json(metadata_path, {})
                task_path = self._task_path_for_social(
                    resolved_date,
                    slug,
                    str(metadata.get("task_id") or "") if isinstance(metadata, dict) else "",
                )
                social_result = self.observe_non_blocking(
                    self.observe_social,
                    metadata_path,
                    task_path=task_path,
                )
                if social_result.get("ok"):
                    observed_ids.append(str(social_result["observation"].get("social_observation_id") or ""))
                else:
                    warnings.append(str(social_result.get("warning") or "OBSERVATION_FAILED"))

        if normalized_menu in {"1", "2"}:
            for week in weeks:
                plan = self.root / "data/editorial_queue/weeks" / week / "deep_dive_plan.json"
                if plan.is_file():
                    deep_result = self.observe_non_blocking(self.observe_deep_dive, plan)
                    if not deep_result.get("ok"):
                        warnings.append(str(deep_result.get("warning") or "OBSERVATION_FAILED"))

        boundary_paths: list[Path] = []
        boundary_type = f"MENU_{normalized_menu}_OPERATION_COMPLETED"
        if normalized_menu == "X":
            boundary_type = "EXTERNAL_WRITER_EXPORT_COMPLETED"
            boundary_paths = sorted(
                (self.root / "exports/external_writer" / resolved_date).glob("*_verified_package.zip")
            )[-1:]
        elif normalized_menu == "W":
            boundary_type = "EXTERNAL_WRITER_RETURN_IMPORTED"
            boundary_paths = sorted(
                (self.root / "data/import_history/external_writer" / resolved_date).glob("*/import.json")
            )
        else:
            boundary_paths = task_paths
        if boundary_paths:
            event_result = self.observe_non_blocking(
                self.observe_business_event,
                boundary_type,
                menu=f"MENU_{normalized_menu}",
                artifact_paths=boundary_paths,
                details={"business_date": resolved_date, "tasks": observed_tasks},
            )
            if not event_result.get("ok"):
                warnings.append(str(event_result.get("warning") or "OBSERVATION_FAILED"))
        if normalized_menu == "W" and observed_tasks:
            review_result = self.observe_non_blocking(
                self.observe_business_event,
                "DRAFT_ENTERED_REVIEW",
                menu="MENU_W",
                artifact_paths=task_paths,
                details={"business_date": resolved_date, "tasks": observed_tasks},
            )
            if not review_result.get("ok"):
                warnings.append(str(review_result.get("warning") or "OBSERVATION_FAILED"))

        rotation = self.apply_retention()
        return {
            "ok": not warnings,
            "enabled": True,
            "menu": f"MENU_{normalized_menu}",
            "business_date": resolved_date,
            "observations": len([value for value in observed_ids if value]),
            "observation_ids": [value for value in observed_ids if value],
            "warnings": sorted(set(warnings)),
            "retention": rotation,
            "production_state_changed": False,
        }

    def apply_retention(self) -> dict[str, Any]:
        if not bool(self.config.get("retention_enabled", True)):
            return {"enabled": False, "archived": 0, "deleted": 0}
        run_root = self.store / "run"
        archive_root = self.store / "archive/run"
        candidates: list[Path] = []
        run_dirs = sorted(
            [path for path in run_root.iterdir() if path.is_dir()] if run_root.is_dir() else [],
            key=lambda path: path.stat().st_mtime,
        )
        cutoff = time.time() - int(self.config.get("routine_run_retention_days") or 30) * 86400
        candidates.extend(path for path in run_dirs if path.stat().st_mtime < cutoff)
        maximum = int(self.config.get("routine_run_max_count") or 500)
        remaining = [path for path in run_dirs if path not in candidates]
        if len(remaining) > maximum:
            candidates.extend(remaining[: len(remaining) - maximum])
        archived = 0
        for source in dict.fromkeys(candidates):
            destination = archive_root / source.name
            if destination.exists():
                continue
            archive_root.mkdir(parents=True, exist_ok=True)
            try:
                os.replace(source, destination)
                archived += 1
            except OSError:
                continue
        return {
            "enabled": True,
            "archived": archived,
            "deleted": 0,
            "protected_evidence_deleted": False,
        }

    def health(self) -> dict[str, Any]:
        store_bytes = sum(path.stat().st_size for path in self.store.rglob("*") if path.is_file()) if self.store.exists() else 0
        event_rows: list[dict[str, Any]] = []
        malformed = 0
        for path in self.store.rglob("*.jsonl") if self.store.exists() else []:
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                try:
                    value = json.loads(line)
                    if isinstance(value, dict):
                        event_rows.append(value)
                except json.JSONDecodeError:
                    malformed += 1
        failure_files = list((self.store / "run/failures").glob("*.json")) if (self.store / "run/failures").is_dir() else []
        failures = [row for row in event_rows if str(row.get("status") or "").startswith("OBSERVATION_") and "FAILED" in str(row.get("status"))]
        failures.extend(read_json(path, {}) for path in failure_files)
        lock_timeouts = sum(1 for row in event_rows if row.get("status") == "OBSERVATION_LOCK_TIMEOUT") + sum(1 for path in failure_files if (read_json(path, {}) or {}).get("status") == "OBSERVATION_LOCK_TIMEOUT")
        contradictions = [row for row in event_rows if row.get("contradiction_id")]
        timestamps = [
            str(row.get("observed_at") or row.get("detected_at") or "")
            for row in event_rows
            if row.get("observed_at") or row.get("detected_at")
        ]
        status = "DEGRADED" if failures or lock_timeouts or malformed else "WARNING" if contradictions else "OK"
        run_dirs = [path for path in (self.store / "run").iterdir() if path.is_dir()] if (self.store / "run").is_dir() else []
        return {
            "observation_health": status,
            "enabled": bool(self.config.get("enabled", True)),
            "last_observation": max(timestamps) if timestamps else None,
            "tasks_observed": len(list((self.store / "tasks").glob("*/current.json"))),
            "new_revisions": sum(1 for row in event_rows if row.get("event_type") == "TASK_REVISION_CHANGED"),
            "approval_observations": sum(1 for row in event_rows if row.get("approval_observation_id")),
            "events_count": len(event_rows),
            "contradictions_count": len(contradictions),
            "contradictions_by_severity": {
                level: sum(1 for row in contradictions if str(row.get("severity") or "").upper() == level)
                for level in ("CRITICAL", "HIGH", "MEDIUM", "LOW")
            },
            "observation_failures": len(failures),
            "lock_timeouts": lock_timeouts,
            "malformed_event_records": malformed,
            "observability_store_bytes": store_bytes,
            "oldest_event": min(timestamps) if timestamps else None,
            "newest_event": max(timestamps) if timestamps else None,
            "rotation_candidates_count": max(0, len(run_dirs) - int(self.config.get("routine_run_max_count") or 500)),
            "production_authority": False,
        }

    def backfill_dry_run(self) -> dict[str, Any]:
        return {
            "mode": "BACKFILL_DRY_RUN",
            "writes_performed": False,
            "task_candidates": len(list((self.root / "data/write_queue").glob("*.json"))),
            "social_candidates": len(list((self.root / "data/social_drafts").glob("*/*/*/metadata.json"))),
            "source_candidates": len(list((self.root / "data/research").glob("*/sources.json"))),
            "message": "Historical backfill is not automatic and was not executed.",
        }

    def _write_run_summary(self, kind: str, ids: list[str], warnings: list[str]) -> None:
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        atomic_json(
            self.store / "run" / stamp / "summary.json",
            {
                "observation_run_schema_version": "observation_run_v1",
                "observed_at": utc_now(),
                "kind": kind,
                "observation_ids": ids,
                "warnings": warnings,
                "production_state_changed": False,
                "network_used": False,
                "paid_api_used": False,
            },
        )

    def observe_non_blocking(
        self,
        operation: Callable[..., dict[str, Any]],
        *args: Any,
        **kwargs: Any,
    ) -> dict[str, Any]:
        try:
            return {"ok": True, "observation": operation(*args, **kwargs), "production_state_changed": False}
        except Exception as exc:  # observation failures must not escape into production callers
            status = "OBSERVATION_LOCK_TIMEOUT" if isinstance(exc, ObservationLockTimeout) else "OBSERVATION_FAILED"
            failure = {
                "failure_id": hash_json({"operation": getattr(operation, "__name__", "unknown"), "error": str(exc)}),
                "observed_at": utc_now(),
                "status": status,
                "operation": getattr(operation, "__name__", "unknown"),
                "error": str(exc),
                "production_state_changed": False,
                "retry_count": 0,
            }
            try:
                append_unique(self.store / "run/observation_failures.jsonl", failure, "failure_id")
            except Exception:
                try:
                    atomic_json(self.store / "run/failures" / f"{failure['failure_id']}.json", failure)
                except Exception:
                    pass
            return {"ok": False, "warning": status, "error": str(exc), "production_state_changed": False}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Phase 1B non-authoritative architecture observer")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--store", type=Path, default=None)
    sub = parser.add_subparsers(dest="command", required=True)
    task = sub.add_parser("task")
    task.add_argument("--task", type=Path, required=True)
    task.add_argument("--content", type=Path)
    task.add_argument("--source", type=Path)
    task.add_argument("--approval", type=Path)
    task.add_argument("--publish", type=Path)
    social = sub.add_parser("social")
    social.add_argument("--metadata", type=Path, required=True)
    social.add_argument("--task", type=Path)
    source = sub.add_parser("source")
    source.add_argument("--source", type=Path, required=True)
    research = sub.add_parser("research")
    research.add_argument("--research-dir", type=Path, required=True)
    deep = sub.add_parser("deep-dive")
    deep.add_argument("--plan", type=Path, required=True)
    transition = sub.add_parser("transition")
    transition.add_argument("--task", type=Path, required=True)
    transition.add_argument("--from-state", required=True)
    transition.add_argument("--to-state", required=True)
    backfill = sub.add_parser("backfill")
    backfill.add_argument("--dry-run", action="store_true")
    live = sub.add_parser("live", help="Best-effort observation after a successful operator boundary.")
    live.add_argument("--menu", required=True)
    live.add_argument("--date", default="latest")
    sub.add_parser("health", help="Show concise observation-system health; never a production gate.")
    sub.add_parser("rotate", help="Archive rotatable routine run summaries conservatively.")
    return parser


def print_health(result: dict[str, Any]) -> None:
    severities = result.get("contradictions_by_severity") or {}
    print(f"Observation Health: {result.get('observation_health', 'OK')}")
    print(f"Enabled: {str(bool(result.get('enabled'))).upper()}")
    print(f"Last observation: {result.get('last_observation') or 'none'}")
    print(f"Tasks observed: {result.get('tasks_observed', 0)}")
    print(f"New revisions: {result.get('new_revisions', 0)}")
    print(f"Approval observations: {result.get('approval_observations', 0)}")
    print("Contradictions: " + ", ".join(
        f"{level.title()}={severities.get(level, 0)}"
        for level in ("CRITICAL", "HIGH", "MEDIUM", "LOW")
    ))
    print(f"Observation failures: {result.get('observation_failures', 0)}")
    print(f"Lock timeouts: {result.get('lock_timeouts', 0)}")
    print(f"Store size: {result.get('observability_store_bytes', 0)} bytes")
    print(f"Rotation candidates: {result.get('rotation_candidates_count', 0)}")
    print("Production authority: NO")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = args.root.resolve()
    store = args.store.resolve() if args.store else None
    observer = ArchitectureObserver(root, store)
    if args.command == "task":
        result = observer.observe_non_blocking(observer.observe_task, args.task, content_path=args.content, source_path=args.source, approval_path=args.approval, publish_path=args.publish)
    elif args.command == "social":
        result = observer.observe_non_blocking(observer.observe_social, args.metadata, task_path=args.task)
    elif args.command == "source":
        result = observer.observe_non_blocking(observer.observe_sources, args.source)
    elif args.command == "research":
        result = observer.observe_non_blocking(observer.observe_research, args.research_dir)
    elif args.command == "deep-dive":
        result = observer.observe_non_blocking(observer.observe_deep_dive, args.plan)
    elif args.command == "transition":
        result = observer.observe_non_blocking(observer.observe_transition, args.task, args.from_state, args.to_state)
    elif args.command == "live":
        result = observer.observe_non_blocking(
            observer.observe_live,
            menu=args.menu,
            business_date=args.date,
        )
        if result.get("ok") and isinstance(result.get("observation"), dict):
            result = result["observation"]
        print(json.dumps(result, ensure_ascii=False, indent=2))
        # Live hooks are cameras. Their exit code must never fail a production menu.
        return 0
    elif args.command == "health":
        result = observer.health()
        print_health(result)
        return 0
    elif args.command == "rotate":
        result = observer.apply_retention()
    else:
        if not args.dry_run:
            raise SystemExit("backfill requires --dry-run; historical backfill is never automatic")
        result = observer.backfill_dry_run()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok", True) else 2


if __name__ == "__main__":
    raise SystemExit(main())
