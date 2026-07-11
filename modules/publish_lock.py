from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class PublishLock:
    def __init__(self, path: Path) -> None:
        self.path = path

    def read(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"status": "unlocked"}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"status": "stale", "reason": "invalid lock file", "path": str(self.path)}
        pid = int(payload.get("pid") or 0)
        active = self._pid_active(pid)
        started = str(payload.get("started_at") or "")
        elapsed = 0
        try:
            elapsed = max(0, int((datetime.now(UTC) - datetime.fromisoformat(started)).total_seconds()))
        except ValueError:
            pass
        return {**payload, "status": "active" if active else "stale", "elapsed_seconds": elapsed, "path": str(self.path)}

    def acquire(self, *, batch_date: str, slugs: list[str], command: str) -> dict[str, Any]:
        current = self.read()
        if current["status"] == "active":
            raise RuntimeError(f"Publish already running (PID {current.get('pid')}, elapsed {current.get('elapsed_seconds')}s).")
        if current["status"] == "stale":
            raise RuntimeError("Stale publish lock exists. Run clear-stale-publish-lock --confirm after verifying the PID is not active.")
        payload = {"pid": os.getpid(), "started_at": datetime.now(UTC).isoformat(), "date": batch_date, "selected_slugs": slugs, "command": command}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        return payload

    def release(self) -> None:
        if self.path.exists():
            self.path.unlink()

    def clear_stale(self, *, confirm: bool) -> dict[str, Any]:
        current = self.read()
        if not confirm:
            raise ValueError("--confirm is required.")
        if current["status"] == "active":
            raise RuntimeError(f"Refusing to remove active publish lock for PID {current.get('pid')}.")
        if self.path.exists():
            self.path.unlink()
        return {"status": "cleared", "previous": current}

    @staticmethod
    def _pid_active(pid: int) -> bool:
        if pid <= 0:
            return False
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return True
