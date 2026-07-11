from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from modules.daily_editorial_workflow import DailyEditorialWorkflow
from modules.publish_lock import PublishLock


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def seed_ready(root: Path, slug: str = "ready-article") -> DailyEditorialWorkflow:
    data = root / "data"
    write_json(data / "editorial_queue" / "2026-07-11" / "topics.json", {"date": "2026-07-11", "count": 1, "topics": [{"slug": slug, "keyword": slug, "status": "approved", "batch_date": "2026-07-11"}]})
    write_json(data / "publish_queue.json", [{"slug": slug, "status": "approved_for_publish", "failures": [], "hard_blockers": [], "url": f"https://smileaireviewhub.com/{slug}/"}])
    write_json(data / "human_approval_queue.json", [{"slug": slug, "status": "human_approved"}])
    write_json(data / "live_status_report.json", {"items": []})
    draft = data / "production_article_drafts" / slug / "index.html"
    draft.parent.mkdir(parents=True)
    draft.write_text("<html><head><link rel='canonical' href='https://smileaireviewhub.com/ready-article/'></head><body><img src='hero.webp'><script type='application/ld+json'>{}</script></body></html>", encoding="utf-8")
    return DailyEditorialWorkflow(root=root, data_dir=data, site_output_dir=root / "site_output")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_published_and_live_candidates_are_excluded(tmp_path: Path) -> None:
    workflow = seed_ready(tmp_path)
    publish_path = tmp_path / "data" / "publish_queue.json"
    write_json(publish_path, [{"slug": "ready-article", "status": "published_local", "published_local": True}])
    write_json(tmp_path / "data" / "live_status_report.json", {"items": [{"slug": "ready-article", "live_http_status": 200, "display_status": "Live 200"}]})
    row = workflow.diagnose_batch(batch_date="2026-07-11")["candidates"][0]
    assert row["selected_for_publish"] is False
    assert "already published locally" in row["exclusion_reason"]
    assert "already Live 200" in row["exclusion_reason"]


def test_historical_approval_without_ready_gate_is_excluded(tmp_path: Path) -> None:
    workflow = seed_ready(tmp_path)
    write_json(tmp_path / "data" / "publish_queue.json", [{"slug": "ready-article", "status": "blocked", "failures": ["AI review failed"]}])
    row = workflow.diagnose_batch(batch_date="2026-07-11")["candidates"][0]
    assert row["selected_for_publish"] is False
    assert row["publish_gate"] != "Ready for Publish"


def test_dry_run_preserves_queue_hashes_and_outputs(tmp_path: Path) -> None:
    workflow = seed_ready(tmp_path)
    paths = [tmp_path / "data" / name for name in ("publish_queue.json", "human_approval_queue.json")]
    before = {path: digest(path) for path in paths}
    result = workflow.publish_dry_run(batch_date="2026-07-11", slug="ready-article")
    assert result["dry_run"] is True
    assert result["build"]["status"] == "planned_not_run"
    assert before == {path: digest(path) for path in paths}
    assert not (tmp_path / "site_output" / "ready-article").exists()


def test_command_timeout_is_controlled(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    workflow = seed_ready(tmp_path)
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], kwargs["timeout"], stderr="last child error")
    monkeypatch.setattr(subprocess, "run", timeout)
    with pytest.raises(RuntimeError, match="timeout after 1s") as error:
        workflow._run_command(["child"], cwd=tmp_path, timeout=1)
    assert "last child error" in str(error.value)


def test_build_retry_is_capped_at_one(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    workflow = seed_ready(tmp_path)
    monkeypatch.setattr(workflow, "prepare_article_output", lambda **kwargs: {"status": "prepared"})
    calls = []
    def fail(command, **kwargs):
        calls.append(command)
        raise RuntimeError("controlled failure")
    monkeypatch.setattr(workflow, "_run_command", fail)
    result = workflow.build_selected(batch_date="2026-07-11", slug="ready-article", timeout=1, retry_count=99)
    assert result["status"] == "failed"
    assert len(calls) == 2
    assert all(any(str(part).endswith("build_selected_output.py") for part in call) for call in calls)
    assert all("build_site.py" not in call for call in calls)


def test_publish_lock_refuses_active_and_requires_confirm_for_stale(tmp_path: Path) -> None:
    lock = PublishLock(tmp_path / "publish.lock")
    lock.acquire(batch_date="2026-07-11", slugs=["one"], command="publish-ready")
    with pytest.raises(RuntimeError, match="already running"):
        lock.acquire(batch_date="2026-07-11", slugs=["two"], command="publish-ready")
    lock.release()
    (tmp_path / "publish.lock").write_text(json.dumps({"pid": 99999999, "started_at": "2026-01-01T00:00:00+00:00"}), encoding="utf-8")
    with pytest.raises(ValueError, match="confirm"):
        lock.clear_stale(confirm=False)
    assert lock.clear_stale(confirm=True)["status"] == "cleared"


def test_recover_interrupted_preparation_preserves_audit_and_refuses_live(tmp_path: Path) -> None:
    workflow = seed_ready(tmp_path)
    slug = "ready-article"
    paths = workflow._article_bundle_paths(slug)
    for key in ("site_output", "published_static"):
        paths[key].parent.mkdir(parents=True, exist_ok=True)
        paths[key].write_text("output", encoding="utf-8")
    write_json(tmp_path / "data" / "publish_queue.json", [{"slug": slug, "status": "published_local", "published_local": True, "published_at": "now"}])
    result = workflow.recover_interrupted_preparation(batch_date="2026-07-11", slug=slug, confirm=True)
    assert result["final_gate"] == "Ready for Publish"
    row = json.loads((tmp_path / "data" / "publish_queue.json").read_text(encoding="utf-8"))[0]
    assert row["status"] == "approved_for_publish"
    assert row["audit_history"][0]["previous_status"] == "published_local"
    write_json(tmp_path / "data" / "live_status_report.json", {"items": [{"slug": slug, "live_http_status": 200}]})
    row["status"] = "published_local"
    write_json(tmp_path / "data" / "publish_queue.json", [row])
    with pytest.raises(ValueError, match="Live 200"):
        workflow.recover_interrupted_preparation(batch_date="2026-07-11", slug=slug, confirm=True)
