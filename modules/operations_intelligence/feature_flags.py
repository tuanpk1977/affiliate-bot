from __future__ import annotations

import json
from pathlib import Path
from typing import Any


SAFE_DEFAULT_FLAGS = {
    "knowledge_graph.enabled": False,
    "editorial_memory.enabled": False,
    "analytics_feedback.enabled": False,
    "social_signal_ingestion.enabled": False,
    "source_scoring_v2.enabled": False,
}


def load_feature_flags(root: Path) -> dict[str, bool]:
    """Return explicit opt-in flags; malformed/missing config stays safely disabled."""
    flags = dict(SAFE_DEFAULT_FLAGS)
    path = root.resolve() / "config" / "operations_intelligence.json"
    try:
        payload: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return flags
    configured = payload.get("feature_flags", {}) if isinstance(payload, dict) else {}
    if not isinstance(configured, dict):
        return flags
    for name in flags:
        value = configured.get(name)
        if isinstance(value, bool):
            flags[name] = value
    return flags


def feature_enabled(root: Path, name: str) -> bool:
    if name not in SAFE_DEFAULT_FLAGS:
        return False
    return load_feature_flags(root)[name]
