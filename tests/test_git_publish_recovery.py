from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from modules.git_publish_recovery import GitPublishRecovery, is_non_fast_forward_push, parse_ahead_behind


def _result(returncode: int = 0, stdout: str = "", stderr: str = "") -> dict[str, object]:
    return {"returncode": returncode, "stdout": stdout, "stderr": stderr}


class FakeGit:
    def __init__(self, responses: dict[tuple[str, ...], list[dict[str, object]]]) -> None:
        self.responses = {command: list(items) for command, items in responses.items()}
        self.calls: list[list[str]] = []

    def __call__(self, command: list[str]) -> dict[str, object]:
        self.calls.append(list(command))
        key = tuple(command)
        if key in self.responses and self.responses[key]:
            return self.responses[key].pop(0)
        return _result()

    def called(self, command: list[str]) -> bool:
        return command in self.calls


class GitPublishRecoveryTests(unittest.TestCase):
    def _recovery(self, root: Path, fake: FakeGit) -> GitPublishRecovery:
        return GitPublishRecovery(repo=root, run_command=fake, progress=lambda _message: None)

    def test_parse_ahead_behind_uses_origin_left_head_right(self) -> None:
        ahead, behind = parse_ahead_behind("1\t2\n")
        self.assertEqual(ahead, 2)
        self.assertEqual(behind, 1)

    def test_initial_push_success_does_not_fetch_or_rebase(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            fake = FakeGit(
                {
                    ("git", "push", "origin", "main"): [_result(0)],
                    ("git", "rev-list", "--left-right", "--count", "origin/main...HEAD"): [_result(0, "0\t0\n")],
                }
            )

            result = self._recovery(root, fake).push_with_recovery()

            self.assertEqual(result.status, "pushed")
            self.assertEqual(result.retry_count, 0)
            self.assertFalse(fake.called(["git", "fetch", "origin", "main"]))
            self.assertFalse(fake.called(["git", "pull", "--rebase", "origin", "main"]))

    def test_non_fast_forward_fetch_rebase_and_retry_once(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / ".git").mkdir()
            fake = FakeGit(
                {
                    ("git", "push", "origin", "main"): [
                        _result(1, stderr="[rejected] main -> main (non-fast-forward)"),
                        _result(0),
                    ],
                    ("git", "branch", "--show-current"): [_result(0, "main\n")],
                    ("git", "rev-parse", "--verify", "origin/main"): [_result(0, "abc\n")],
                    ("git", "status", "--porcelain"): [_result(0, "")],
                    ("git", "fetch", "origin", "main"): [_result(0)],
                    ("git", "rev-list", "--left-right", "--count", "origin/main...HEAD"): [
                        _result(0, "1\t1\n"),
                        _result(0, "0\t0\n"),
                    ],
                    ("git", "pull", "--rebase", "origin", "main"): [_result(0)],
                }
            )

            result = self._recovery(root, fake).push_with_recovery()

            self.assertEqual(result.status, "pushed_after_rebase")
            self.assertEqual(result.retry_count, 1)
            self.assertEqual(fake.calls.count(["git", "push", "origin", "main"]), 2)
            self.assertTrue(fake.called(["git", "fetch", "origin", "main"]))
            self.assertTrue(fake.called(["git", "pull", "--rebase", "origin", "main"]))
            self.assertFalse(any("--force" in part for call in fake.calls for part in call))
            self.assertFalse(result.force_push_used)

    def test_dirty_working_tree_blocks_rebase(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / ".git").mkdir()
            fake = FakeGit(
                {
                    ("git", "push", "origin", "main"): [_result(1, stderr="remote contains work that you do not have")],
                    ("git", "branch", "--show-current"): [_result(0, "main\n")],
                    ("git", "rev-parse", "--verify", "origin/main"): [_result(0, "abc\n")],
                    ("git", "status", "--porcelain"): [_result(0, " M docs/page/index.html\n?? temp.txt\n")],
                }
            )

            result = self._recovery(root, fake).push_with_recovery()

            self.assertEqual(result.status, "push_blocked")
            self.assertIn("working tree is dirty", result.reason)
            self.assertIn("docs/page/index.html", result.reason)
            self.assertFalse(fake.called(["git", "fetch", "origin", "main"]))
            self.assertFalse(fake.called(["git", "pull", "--rebase", "origin", "main"]))

    def test_merge_in_progress_blocks_rebase(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / ".git").mkdir()
            (root / ".git" / "MERGE_HEAD").write_text("abc\n", encoding="utf-8")
            fake = FakeGit(
                {
                    ("git", "push", "origin", "main"): [_result(1, stderr="[rejected] main -> main (non-fast-forward)")],
                    ("git", "branch", "--show-current"): [_result(0, "main\n")],
                    ("git", "rev-parse", "--verify", "origin/main"): [_result(0, "abc\n")],
                }
            )

            result = self._recovery(root, fake).push_with_recovery()

            self.assertEqual(result.status, "push_blocked")
            self.assertIn("already in progress", result.reason)
            self.assertFalse(fake.called(["git", "fetch", "origin", "main"]))

    def test_rebase_conflict_stops_without_retry_push(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / ".git").mkdir()
            fake = FakeGit(
                {
                    ("git", "push", "origin", "main"): [_result(1, stderr="[rejected] main -> main (non-fast-forward)")],
                    ("git", "branch", "--show-current"): [_result(0, "main\n")],
                    ("git", "rev-parse", "--verify", "origin/main"): [_result(0, "abc\n")],
                    ("git", "status", "--porcelain"): [_result(0, "")],
                    ("git", "fetch", "origin", "main"): [_result(0)],
                    ("git", "rev-list", "--left-right", "--count", "origin/main...HEAD"): [_result(0, "1\t1\n")],
                    ("git", "pull", "--rebase", "origin", "main"): [_result(1, stderr="CONFLICT")],
                    ("git", "diff", "--name-only", "--diff-filter=U"): [_result(0, "docs/page/index.html\n")],
                }
            )

            result = self._recovery(root, fake).push_with_recovery()

            self.assertEqual(result.status, "rebase_conflict")
            self.assertEqual(result.conflict_files, ["docs/page/index.html"])
            self.assertEqual(fake.calls.count(["git", "push", "origin", "main"]), 1)
            self.assertFalse(result.force_push_used)

    def test_non_fast_forward_classifier_is_specific(self) -> None:
        self.assertTrue(is_non_fast_forward_push(_result(1, stderr="[rejected] main -> main (non-fast-forward)")))
        self.assertTrue(is_non_fast_forward_push(_result(1, stderr="remote contains work that you do not have")))
        self.assertFalse(is_non_fast_forward_push(_result(1, stderr="Permission denied")))


if __name__ == "__main__":
    unittest.main()
