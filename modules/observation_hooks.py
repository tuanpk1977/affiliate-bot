"""Tiny fail-open adapters from successful production events to Phase 1B.

Nothing returned by this module is a business decision.  Callers deliberately
ignore the return value and retain their original result/exception semantics.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from scripts.observe_architecture import ArchitectureObserver, canonical_task_id, content_action, read_json


def _warn(message: str) -> None:
    print(f"[OBSERVATION WARNING] {message}. Production result is unchanged.", file=sys.stderr)


def _task_path(root: Path, *, batch_date: str, slug: str) -> Path | None:
    for path in sorted((root / "data/write_queue").glob("*.json")):
        row = read_json(path, {})
        if not isinstance(row, dict):
            continue
        if str(row.get("article_slug") or row.get("slug") or "") != slug:
            continue
        if batch_date and str(row.get("batch_date") or "") != batch_date:
            continue
        return path
    return None


def _content_path(root: Path, batch_date: str, slug: str) -> Path | None:
    candidates = (
        root / "data/production_article_drafts" / slug / "article.md",
        root / "upload" / batch_date / "drafts" / slug / "article.md",
    )
    return next((path for path in candidates if path.is_file()), None)


def observe_website_approval_best_effort(
    *, root: Path, batch_date: str, slug: str, approver: str
) -> dict[str, Any]:
    """Observe a website approval only after the production approval succeeded."""
    try:
        observer = ArchitectureObserver(root)
        if not bool(observer.config.get("enabled", True)):
            return {"ok": True, "enabled": False, "production_state_changed": False}
        task_path = _task_path(root, batch_date=batch_date, slug=slug)
        if task_path is None:
            raise FileNotFoundError(f"No touched writer task for approval: {batch_date}/{slug}")
        result = observer.observe_non_blocking(
            observer.observe_task,
            task_path,
            content_path=_content_path(root, batch_date, slug),
            approval_path=root / "data/human_approval_queue.json",
            publish_path=root / "data/publish_queue.json",
        )
        event: dict[str, Any] | None = None
        if result.get("ok"):
            observation = result["observation"]
            paths = [root / "data/publish_queue.json"]
            content = _content_path(root, batch_date, slug)
            if content is not None:
                paths.append(content)
            event = observer.observe_non_blocking(
                observer.observe_business_event,
                "PUBLISH_GATE_OBSERVED",
                menu="WEBSITE_APPROVAL",
                artifact_paths=paths,
                canonical_task_id_value=str(observation.get("canonical_task_id") or "") or None,
                details={
                    "batch_date": batch_date,
                    "slug": slug,
                    "approved_by": approver,
                    "observed_task_revision": observation.get("observed_task_revision"),
                    "publish_gate_enabled": observation.get("publish_gate_enabled"),
                    "publish_observation_status": observation.get("publish_observation_status"),
                    "canonical_safety_projection": observation.get("canonical_safety_projection"),
                },
            )
        failures = [row for row in (result, event) if isinstance(row, dict) and not row.get("ok")]
        if failures:
            _warn(str(failures[0].get("warning") or "OBSERVATION_FAILED"))
        result["publish_gate_event"] = event
        return result
    except Exception as exc:  # the camera must never alter approval behavior
        _warn(f"OBSERVATION_FAILED: {exc}")
        return {"ok": False, "warning": "OBSERVATION_FAILED", "production_state_changed": False}


def observe_social_event_best_effort(
    *,
    root: Path,
    batch_date: str,
    slug: str,
    platform: str,
    action: str,
    previous_status: str = "",
    new_status: str = "",
) -> dict[str, Any]:
    """Observe a saved social event after its production event log was appended."""
    try:
        observer = ArchitectureObserver(root)
        if not bool(observer.config.get("enabled", True)):
            return {"ok": True, "enabled": False, "production_state_changed": False}
        metadata_path = root / "data/social_drafts" / batch_date / slug / platform / "metadata.json"
        task_path = _task_path(root, batch_date=batch_date, slug=slug)
        social = observer.observe_non_blocking(
            observer.observe_social,
            metadata_path,
            task_path=task_path,
        )
        canonical_id: str | None = None
        if task_path is not None:
            task = read_json(task_path, {})
            if isinstance(task, dict):
                workflow = str(task.get("task_type") or task.get("workflow_lane") or "")
                identity_date = str(task.get("batch_date") or task.get("week_start") or "unknown-date")
                canonical_id = canonical_task_id(workflow, identity_date, slug, content_action(task))
        if action == "status" and new_status == "approved_for_copy":
            event_type = "PLATFORM_APPROVAL_OBSERVED"
        elif action == "save" and previous_status == "approved_for_copy":
            event_type = "POTENTIAL_STALE_PLATFORM_APPROVAL"
        elif action in {"published_manual", "confirm", "final_url"} or new_status == "published_manual":
            event_type = "PUBLISH_GATE_OBSERVED"
        else:
            event_type = "SOCIAL_REVIEW_EVENT_OBSERVED"
        event = observer.observe_non_blocking(
            observer.observe_business_event,
            event_type,
            menu="MENU_G" if action in {"save", "status"} else "MENU_E",
            artifact_paths=[metadata_path],
            canonical_task_id_value=canonical_id,
            details={
                "batch_date": batch_date,
                "slug": slug,
                "platform": platform,
                "action": action,
                "previous_status": previous_status,
                "new_status": new_status,
            },
        )
        failures = [row for row in (social, event) if not row.get("ok")]
        if failures:
            _warn(str(failures[0].get("warning") or "OBSERVATION_FAILED"))
        return {
            "ok": not failures,
            "social": social,
            "event": event,
            "production_state_changed": False,
        }
    except Exception as exc:  # the camera must never alter social workflow behavior
        _warn(f"OBSERVATION_FAILED: {exc}")
        return {"ok": False, "warning": "OBSERVATION_FAILED", "production_state_changed": False}


def observe_revision_safety_event_best_effort(
    *,
    root: Path,
    event_type: str,
    slug: str,
    details: dict[str, Any],
    artifact_paths: list[Path] | None = None,
    canonical_task_id_value: str | None = None,
) -> dict[str, Any]:
    """Record a Phase 1C fact without participating in the production decision."""
    try:
        observer = ArchitectureObserver(root)
        if not bool(observer.config.get("enabled", True)):
            return {"ok": True, "enabled": False, "production_state_changed": False}
        result = observer.observe_non_blocking(
            observer.observe_business_event,
            event_type,
            menu="PHASE_1C_SAFETY",
            artifact_paths=list(artifact_paths or []),
            canonical_task_id_value=canonical_task_id_value,
            details={"slug": slug, **details},
        )
        if not result.get("ok"):
            _warn(str(result.get("warning") or "OBSERVATION_FAILED"))
        result["production_state_changed"] = False
        return result
    except Exception as exc:  # observation must remain camera-only
        _warn(f"OBSERVATION_FAILED: {exc}")
        return {"ok": False, "warning": "OBSERVATION_FAILED", "production_state_changed": False}
