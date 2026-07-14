from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Sequence


RunCommand = Callable[[list[str]], dict[str, object]]
Progress = Callable[[str], None]


@dataclass
class GitPushRecoveryResult:
    status: str
    initial_push: dict[str, object]
    fetch: dict[str, object] | None = None
    rebase: dict[str, object] | None = None
    retry_push: dict[str, object] | None = None
    sync: dict[str, object] | None = None
    conflict_files: list[str] = field(default_factory=list)
    force_push_used: bool = False
    retry_count: int = 0
    reason: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "initial_push": self.initial_push,
            "fetch": self.fetch,
            "rebase": self.rebase,
            "retry_push": self.retry_push,
            "sync": self.sync,
            "conflict_files": self.conflict_files,
            "force_push_used": self.force_push_used,
            "retry_count": self.retry_count,
            "reason": self.reason,
        }


def is_non_fast_forward_push(result: dict[str, object]) -> bool:
    text = f"{result.get('stdout', '')}\n{result.get('stderr', '')}".lower()
    return (
        "non-fast-forward" in text
        or "fetch first" in text
        or "remote contains work that you do" in text
        or ("rejected" in text and "main -> main" in text)
    )


def has_git_operation_in_progress(repo: Path) -> bool:
    git_dir = repo / ".git"
    return any((git_dir / name).exists() for name in ("rebase-merge", "rebase-apply", "MERGE_HEAD", "CHERRY_PICK_HEAD"))


def parse_ahead_behind(stdout: str) -> tuple[int, int]:
    parts = stdout.strip().split()
    if len(parts) != 2:
        raise ValueError("unexpected rev-list output")
    behind = int(parts[0])
    ahead = int(parts[1])
    return ahead, behind


class GitPublishRecovery:
    def __init__(
        self,
        *,
        repo: Path,
        run_command: RunCommand,
        progress: Progress | None = None,
        branch: str = "main",
        remote: str = "origin",
    ) -> None:
        self.repo = repo
        self.run_command = run_command
        self.progress = progress or (lambda message: None)
        self.branch = branch
        self.remote = remote

    def push_with_recovery(self) -> GitPushRecoveryResult:
        initial = self._run(["git", "push", self.remote, self.branch], "[6/7] Git push origin main")
        if int(initial.get("returncode") or 0) == 0:
            sync = self._sync_status()
            return GitPushRecoveryResult(status="pushed", initial_push=initial, sync=sync)
        if not is_non_fast_forward_push(initial):
            return GitPushRecoveryResult(status="push_failed", initial_push=initial, reason="push failed and was not classified as non-fast-forward")

        self.progress("[WARN] Remote contains newer commits.")
        guard_error = self._pre_rebase_guard()
        if guard_error:
            return GitPushRecoveryResult(status="push_blocked", initial_push=initial, reason=guard_error)

        self.progress("[INFO] Fetching origin/main...")
        fetch = self._run(["git", "fetch", self.remote, self.branch], "")
        if int(fetch.get("returncode") or 0) != 0:
            return GitPushRecoveryResult(status="push_blocked", initial_push=initial, fetch=fetch, reason="git fetch failed")

        sync_before = self._sync_status()
        ahead = int(sync_before.get("ahead") or 0)
        behind = int(sync_before.get("behind") or 0)
        if ahead <= 0 or behind <= 0:
            return GitPushRecoveryResult(status="push_blocked", initial_push=initial, fetch=fetch, sync=sync_before, reason="repo is not in expected ahead/behind state after fetch")

        self.progress("[INFO] Rebasing local publish commit onto origin/main...")
        rebase = self._run(["git", "pull", "--rebase", self.remote, self.branch], "")
        if int(rebase.get("returncode") or 0) != 0:
            conflicts = self._conflict_files()
            self.progress("[ERROR] Rebase conflict detected.")
            self.progress("[INFO] Publish commit preserved locally.")
            self.progress("[INFO] No force push was attempted.")
            return GitPushRecoveryResult(
                status="rebase_conflict",
                initial_push=initial,
                fetch=fetch,
                rebase=rebase,
                sync=sync_before,
                conflict_files=conflicts,
                reason="rebase failed; operator review required",
            )

        self.progress("[INFO] Rebase successful.")
        self.progress("[INFO] Retrying push...")
        retry = self._run(["git", "push", self.remote, self.branch], "")
        if int(retry.get("returncode") or 0) != 0:
            return GitPushRecoveryResult(
                status="push_failed_after_rebase",
                initial_push=initial,
                fetch=fetch,
                rebase=rebase,
                retry_push=retry,
                retry_count=1,
                reason="retry push failed after successful rebase",
            )
        self.progress("[OK] Push completed.")
        sync_after = self._sync_status()
        return GitPushRecoveryResult(
            status="pushed_after_rebase",
            initial_push=initial,
            fetch=fetch,
            rebase=rebase,
            retry_push=retry,
            retry_count=1,
            sync=sync_after,
        )

    def _pre_rebase_guard(self) -> str:
        branch = self._run(["git", "branch", "--show-current"], "")
        if str(branch.get("stdout") or "").strip() != self.branch:
            return f"current branch is not {self.branch}"
        remote_check = self._run(["git", "rev-parse", "--verify", f"{self.remote}/{self.branch}"], "")
        if int(remote_check.get("returncode") or 0) != 0:
            return f"remote branch {self.remote}/{self.branch} is missing"
        if has_git_operation_in_progress(self.repo):
            return "rebase, merge, or cherry-pick is already in progress"
        status = self._run(["git", "status", "--porcelain"], "")
        dirty = str(status.get("stdout") or "").strip()
        if dirty:
            dirty_files = "; ".join(line.strip() for line in dirty.splitlines()[:12] if line.strip())
            suffix = " ..." if len(dirty.splitlines()) > 12 else ""
            return f"working tree is dirty after publish commit: {dirty_files}{suffix}"
        return ""

    def _sync_status(self) -> dict[str, object]:
        result = self._run(["git", "rev-list", "--left-right", "--count", f"{self.remote}/{self.branch}...HEAD"], "")
        if int(result.get("returncode") or 0) != 0:
            return {"status": "unknown", "ahead": None, "behind": None, "reason": str(result.get("stderr") or result.get("stdout") or "").strip()}
        try:
            ahead, behind = parse_ahead_behind(str(result.get("stdout") or ""))
        except ValueError:
            return {"status": "unknown", "ahead": None, "behind": None, "reason": "unexpected rev-list output"}
        return {"status": "in_sync" if ahead == 0 and behind == 0 else "diverged" if ahead and behind else "ahead" if ahead else "behind", "ahead": ahead, "behind": behind, "reason": ""}

    def _conflict_files(self) -> list[str]:
        result = self._run(["git", "diff", "--name-only", "--diff-filter=U"], "")
        return [line.strip() for line in str(result.get("stdout") or "").splitlines() if line.strip()]

    def _run(self, command: Sequence[str], label: str) -> dict[str, object]:
        if any("--force" in part for part in command):
            raise RuntimeError("force push is not allowed")
        if label:
            self.progress(f"{label}... running")
        result = self.run_command(list(command))
        if label:
            status = "OK" if int(result.get("returncode") or 0) == 0 else f"FAILED ({result.get('returncode')})"
            self.progress(f"{label}... {status}")
        return result
