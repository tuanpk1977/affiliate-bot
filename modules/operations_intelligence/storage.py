from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any


PROTECTED_STATE_NAMES = {
    "content_review_queue.json",
    "human_approval_queue.json",
    "publish_queue.json",
    "current_week.json",
}


def _assert_intelligence_path(path: Path, intelligence_root: Path) -> None:
    resolved = path.resolve()
    root = intelligence_root.resolve()
    if root != resolved and root not in resolved.parents:
        raise ValueError(f"Intelligence output must stay under {root}")
    if path.name in PROTECTED_STATE_NAMES:
        raise ValueError(f"Refusing to write protected workflow state: {path.name}")


def atomic_write_text(
    path: Path,
    content: str,
    *,
    intelligence_root: Path,
    archive_existing: bool = True,
) -> Path | None:
    _assert_intelligence_path(path, intelligence_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    archived: Path | None = None
    if path.exists() and archive_existing:
        history = intelligence_root / "history" / path.relative_to(intelligence_root).parent
        history.mkdir(parents=True, exist_ok=True)
        index = 1
        archived = history / f"{path.name}.{index:04d}.bak"
        while archived.exists():
            index += 1
            archived = history / f"{path.name}.{index:04d}.bak"
        shutil.copyfile(path, archived)
    handle, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return archived


def atomic_write_json(
    path: Path,
    payload: Any,
    *,
    intelligence_root: Path,
    archive_existing: bool = True,
) -> Path | None:
    content = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    return atomic_write_text(
        path,
        content,
        intelligence_root=intelligence_root,
        archive_existing=archive_existing,
    )
