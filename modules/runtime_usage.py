"""Minimal, local, privacy-bounded runtime usage evidence."""

from __future__ import annotations

import json
import re
import time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable


DISCLAIMER = "No observation is not proof of non-use."
VALID_PROFILES = {"LITE_DAILY", "FULL_COMPATIBILITY"}
VALID_STATUSES = {"USED", "NOT_OBSERVED", "UNKNOWN"}
_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,99}$")


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _safe_identifier(value: object, fallback: str = "UNKNOWN") -> str:
    text = str(value or "").strip()
    return text if _SAFE_IDENTIFIER.fullmatch(text) else fallback


def _read_json(path: Path, default: Any) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError, TypeError):
        return default


def load_usage_config(root: Path) -> dict[str, Any]:
    default = {
        "enabled": True,
        "store": "observability/usage/events.jsonl",
        "monitoring_started_at": utc_now(),
        "default_window_days": 30,
        "allowed_window_days": [7, 30, 60, 90],
    }
    value = _read_json(root / "config" / "usage_evidence.json", default)
    return value if isinstance(value, dict) else default


def event_store(root: Path, config: dict[str, Any] | None = None) -> Path:
    value = str((config or load_usage_config(root)).get("store") or "observability/usage/events.jsonl")
    path = (root / value).resolve()
    root_resolved = root.resolve()
    if root_resolved != path and root_resolved not in path.parents:
        raise ValueError("Usage store must remain inside the project root")
    return path


def build_event(
    *,
    runtime_profile: str,
    entry_point: str,
    feature: str,
    workflow: str,
    operation: str,
    success: bool,
    output_generated: bool,
    duration_ms: int | None = None,
    error_class: str | None = None,
    timestamp: str | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": "runtime_usage_event_v1",
        "event_id": uuid.uuid4().hex,
        "timestamp": timestamp or utc_now(),
        "runtime_profile": runtime_profile if runtime_profile in VALID_PROFILES else "UNKNOWN",
        "entry_point": _safe_identifier(entry_point),
        "feature": _safe_identifier(feature),
        "workflow": _safe_identifier(workflow),
        "operation": _safe_identifier(operation),
        "success": bool(success),
        "output_generated": bool(output_generated),
        "duration_ms": max(0, int(duration_ms)) if duration_ms is not None else None,
        "error_class": _safe_identifier(error_class, "") if error_class else None,
    }


def append_event(path: Path, event: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(event, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(line + "\n")


def record_usage(root: Path, **fields: Any) -> dict[str, Any]:
    config = load_usage_config(root)
    if not bool(config.get("enabled", True)):
        return {"ok": True, "recorded": False, "reason": "DISABLED"}
    event = build_event(**fields)
    append_event(event_store(root, config), event)
    return {"ok": True, "recorded": True, "event": event}


def observe_usage_best_effort(root: Path, **fields: Any) -> dict[str, Any]:
    """Record evidence without ever raising into the business workflow."""
    try:
        return record_usage(root, **fields)
    except Exception as exc:  # telemetry is intentionally fail-open
        return {
            "ok": False,
            "recorded": False,
            "warning": "USAGE_EVIDENCE_WRITE_FAILED",
            "error_class": exc.__class__.__name__,
        }


def read_events(path: Path) -> tuple[list[dict[str, Any]], int]:
    rows: list[dict[str, Any]] = []
    malformed = 0
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return rows, malformed
    for line in lines:
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except ValueError:
            malformed += 1
            continue
        if isinstance(value, dict) and value.get("schema_version") == "runtime_usage_event_v1":
            rows.append(value)
        else:
            malformed += 1
    return rows, malformed


def _parse_timestamp(value: object) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(UTC)
    except (TypeError, ValueError):
        return None


def _component_used(record: dict[str, Any], events: Iterable[dict[str, Any]]) -> bool:
    selectors = record.get("usage_selectors")
    if isinstance(selectors, list) and selectors:
        for event in events:
            for selector in selectors:
                if isinstance(selector, dict) and all(str(event.get(key) or "") == str(value) for key, value in selector.items()):
                    return True
        return False
    needles = {str(record[key]) for key in ("component", "feature_id") if record.get(key)}
    needles.update(str(value) for value in record.get("entrypoints", []) if value)
    for event in events:
        values = {
            str(event.get("entry_point") or ""),
            str(event.get("feature") or ""),
            str(event.get("workflow") or ""),
        }
        if needles & values:
            return True
    return False


def aggregate_usage(
    *,
    root: Path,
    registry: dict[str, Any],
    window_days: int,
    now: datetime | None = None,
) -> dict[str, Any]:
    config = load_usage_config(root)
    allowed = {int(value) for value in config.get("allowed_window_days", [7, 30, 60, 90])}
    if int(window_days) not in allowed:
        raise ValueError(f"window_days must be one of {sorted(allowed)}")
    as_of = (now or datetime.now(UTC)).astimezone(UTC)
    cutoff = as_of - timedelta(days=int(window_days))
    rows, malformed = read_events(event_store(root, config))
    window_events = [row for row in rows if (_parse_timestamp(row.get("timestamp")) or as_of) >= cutoff]
    started = _parse_timestamp(config.get("monitoring_started_at"))
    coverage_complete = bool(started and started <= cutoff and malformed == 0)
    components: list[dict[str, Any]] = []
    for record in registry.get("records", []):
        used = _component_used(record, window_events)
        observable = bool(record.get("usage_selectors"))
        status = "USED" if used else ("NOT_OBSERVED" if coverage_complete and observable else "UNKNOWN")
        components.append(
            {
                "component": record.get("component"),
                "status": status,
                "observation_window_days": int(window_days),
                "reason": (
                    "At least one matching bounded usage event exists in the window."
                    if used
                    else "No matching event in a complete observation window."
                    if coverage_complete and observable
                    else "This component lacks a complete instrumented observation window."
                ),
            }
        )
    return {
        "schema_version": "runtime_usage_report_v1",
        "generated_at": utc_now(),
        "as_of": as_of.isoformat().replace("+00:00", "Z"),
        "window_days": int(window_days),
        "coverage_complete": coverage_complete,
        "monitoring_started_at": config.get("monitoring_started_at"),
        "events_in_window": len(window_events),
        "malformed_records": malformed,
        "status_vocabulary": sorted(VALID_STATUSES),
        "disclaimer": DISCLAIMER,
        "components": components,
    }


class UsageTimer:
    """Timer for future stable Python seams; workflow exceptions still propagate."""

    def __init__(self, root: Path, **fields: Any) -> None:
        self.root = root
        self.fields = dict(fields)
        self.started = 0.0

    def __enter__(self) -> "UsageTimer":
        self.started = time.perf_counter()
        return self

    def __exit__(self, exc_type: type[BaseException] | None, exc: BaseException | None, traceback: Any) -> bool:
        elapsed = round((time.perf_counter() - self.started) * 1000)
        fields = dict(self.fields)
        output_generated = bool(fields.pop("output_generated", False))
        observe_usage_best_effort(
            self.root,
            **fields,
            success=exc is None,
            output_generated=output_generated,
            duration_ms=elapsed,
            error_class=exc_type.__name__ if exc_type else None,
        )
        return False
