from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any


CONTENT_HASH_VERSION = "sha256_utf8_exact_v1"
REVISION_ID_PREFIX = "website-revision-v1"


def content_hash(text: str) -> str:
    """Hash the exact UTF-8 candidate consumed by the publish gate."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def revision_id_for_hash(value: str) -> str:
    clean = str(value or "").strip().lower()
    return f"{REVISION_ID_PREFIX}:{clean}" if clean else ""


def binding_for_content(text: str) -> dict[str, str]:
    value = content_hash(text)
    return {
        "content_hash": value,
        "revision_id": revision_id_for_hash(value),
        "content_hash_version": CONTENT_HASH_VERSION,
    }


def binding_for_file(path: Path) -> dict[str, str]:
    return binding_for_content(path.read_text(encoding="utf-8"))


def approval_binding_status(
    approval: dict[str, Any], *, current_content_hash: str, current_revision_id: str
) -> str:
    if str(approval.get("status") or "").strip().lower() != "human_approved":
        return "APPROVAL_NOT_GRANTED"
    if str(approval.get("approved_by") or "").strip().lower() == "system_optional":
        return "INVALID_APPROVER"
    approved_hash = str(
        approval.get("approved_content_hash") or approval.get("content_hash") or ""
    ).strip().lower()
    approved_revision = str(
        approval.get("approved_revision_id")
        or approval.get("revision_id")
        or approval.get("task_revision")
        or ""
    ).strip()
    if not approved_hash or not approved_revision:
        return "LEGACY_APPROVAL_UNBOUND"
    if approved_hash != str(current_content_hash or "").strip().lower():
        return "CONTENT_HASH_MISMATCH"
    if approved_revision != str(current_revision_id or "").strip():
        return "REVISION_ID_MISMATCH"
    return "MATCHED"
