from __future__ import annotations

import json
from pathlib import Path
from modules.editorial_state_reset import EditorialStateReset


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def seed_batch(root: Path, batch_date: str, rows: list[dict[str, object]]) -> None:
    write_json(root / "data" / "editorial_queue" / batch_date / "topics.json", {"date": batch_date, "count": len(rows), "topics": rows})


def base_state(root: Path) -> None:
    seed_batch(root, "2026-07-10", [{"slug": "stale-draft", "status": "drafted"}])
    seed_batch(root, "2026-07-11", [{"slug": "current-item", "status": "drafted"}])
    write_json(root / "data" / "content_review_queue.json", [{"slug": "stale-draft", "status": "needs_revision"}])
    write_json(root / "data" / "human_approval_queue.json", [{"slug": "stale-draft", "status": "needs_human_review"}])
    write_json(root / "data" / "publish_queue.json", [{"slug": "stale-draft", "status": "blocked"}])
    preview = root / "upload" / "2026-07-10" / "review" / "stale-draft" / "index.html"
    preview.parent.mkdir(parents=True)
    preview.write_text("stale", encoding="utf-8")


def test_published_sitemap_live_seo_and_current_items_are_protected(tmp_path: Path) -> None:
    rows = [
        {"slug": "published-item", "status": "drafted"},
        {"slug": "sitemap-item", "status": "drafted"},
        {"slug": "live-item", "status": "drafted"},
        {"slug": "seo-item", "status": "selected", "source": "seo_engine"},
        {"slug": "approved-item", "status": "approved"},
    ]
    seed_batch(tmp_path, "2026-07-10", rows)
    seed_batch(tmp_path, "2026-07-11", [{"slug": "current-item", "status": "drafted"}])
    published = tmp_path / "docs" / "published-item" / "index.html"
    published.parent.mkdir(parents=True)
    published.write_text("published", encoding="utf-8")
    (tmp_path / "docs" / "sitemap.xml").write_text("<urlset><url><loc>https://example.com/sitemap-item/</loc></url></urlset>", encoding="utf-8")
    write_json(tmp_path / "data" / "live_status_report.json", {"items": [{"slug": "live-item", "live_http_status": 200}]})
    write_json(tmp_path / "data" / "seo" / "opportunities.json", [{"slug": "seo-item", "selected": True}])
    write_json(tmp_path / "data" / "content_review_queue.json", [])
    write_json(tmp_path / "data" / "human_approval_queue.json", [])
    write_json(tmp_path / "data" / "publish_queue.json", [])

    plan = EditorialStateReset(root=tmp_path).plan()

    assert not plan["stale_slugs"]
    for slug in ("published-item", "sitemap-item", "live-item", "seo-item", "current-item"):
        assert slug in plan["protected_slugs"]
    assert plan["excluded_candidates"]["approved-item"] == "approved, ready, published, or live state"


def test_dry_run_lists_only_stale_files_and_has_no_side_effects(tmp_path: Path) -> None:
    base_state(tmp_path)
    before = (tmp_path / "data" / "content_review_queue.json").read_text(encoding="utf-8")
    plan = EditorialStateReset(root=tmp_path).plan()
    assert plan["stale_slugs"] == ["stale-draft"]
    assert plan["queue_row_count"] == 4
    assert plan["files_to_archive"] == ["upload/2026-07-10/review/stale-draft"]
    assert (tmp_path / "data" / "content_review_queue.json").read_text(encoding="utf-8") == before
    assert not (tmp_path / "data" / "archive").exists()


class FakeConsole:
    def __init__(self) -> None:
        self.calls = 0
        self.review_engine = SimpleReportWriter()
        self.publish_gate = SimpleReportWriter()

    def build_console(self) -> None:
        self.calls += 1


class SimpleReportWriter:
    def __init__(self) -> None:
        self.calls = 0

    def refresh_reports(self) -> None:
        self.calls += 1


class FakeWorkflow:
    def __init__(self) -> None:
        self.console = FakeConsole()
        self.dashboard_calls: list[str] = []
        self.live_calls: list[str] = []

    def build_review_dashboard(self, *, batch_date: str) -> None:
        self.dashboard_calls.append(batch_date)

    def check_live(self, *, batch_date: str, include_all: bool) -> None:
        self.live_calls.append(batch_date)


def test_apply_creates_backup_archives_and_is_idempotent(tmp_path: Path) -> None:
    base_state(tmp_path)
    workflow = FakeWorkflow()
    reset = EditorialStateReset(root=tmp_path, workflow=workflow)
    result = reset.apply()
    archive = Path(result["archive_dir"])
    assert (archive / "reset_manifest.json").exists()
    assert (archive / "removed_records.json").exists()
    assert (archive / "protected_records.json").exists()
    assert (archive / "backups" / "data" / "content_review_queue.json").exists()
    assert (archive / "files" / "upload" / "2026-07-10" / "review" / "stale-draft" / "index.html").exists()
    assert not (tmp_path / "upload" / "2026-07-10" / "review" / "stale-draft").exists()
    assert workflow.console.calls == 1
    assert workflow.console.review_engine.calls == 1
    assert workflow.console.publish_gate.calls == 1
    assert workflow.dashboard_calls == ["2026-07-11"]
    assert workflow.live_calls == ["2026-07-11"]
    assert result["final_plan"]["stale_count"] == 0
    assert reset.plan()["stale_count"] == 0


def test_apply_restores_confirmed_live_output_to_published_final_state(tmp_path: Path) -> None:
    base_state(tmp_path)
    slug = "live-article"
    for base in (tmp_path / "docs", tmp_path / "site_output", tmp_path / "data" / "published_static_pages"):
        path = base / slug / "index.html"
        path.parent.mkdir(parents=True)
        path.write_text("live", encoding="utf-8")
    publish = json.loads((tmp_path / "data" / "publish_queue.json").read_text(encoding="utf-8"))
    publish.append({"slug": slug, "status": "blocked", "failures": ["legacy warning"]})
    write_json(tmp_path / "data" / "publish_queue.json", publish)
    current_path = tmp_path / "data" / "editorial_queue" / "2026-07-11" / "topics.json"
    current = json.loads(current_path.read_text(encoding="utf-8"))
    current["topics"].append({"slug": slug, "status": "drafted"})
    write_json(current_path, current)
    write_json(tmp_path / "data" / "live_status_report.json", {"items": [{"slug": slug, "live_http_status": 200}]})

    result = EditorialStateReset(root=tmp_path).apply()

    rows = json.loads((tmp_path / "data" / "publish_queue.json").read_text(encoding="utf-8"))
    live_row = next(row for row in rows if row["slug"] == slug)
    assert live_row["status"] == "published_local"
    assert live_row["failures"] == []
    current = json.loads(current_path.read_text(encoding="utf-8"))
    assert next(row for row in current["topics"] if row["slug"] == slug)["status"] == "published"
    assert result["restored_published_slugs"] == [slug]


def test_ready_and_published_queue_rows_never_enter_archive_plan(tmp_path: Path) -> None:
    seed_batch(tmp_path, "2026-07-10", [{"slug": "ready", "status": "drafted"}, {"slug": "published", "status": "drafted"}])
    seed_batch(tmp_path, "2026-07-11", [{"slug": "current", "status": "drafted"}])
    write_json(tmp_path / "data" / "content_review_queue.json", [])
    write_json(tmp_path / "data" / "human_approval_queue.json", [])
    write_json(tmp_path / "data" / "publish_queue.json", [{"slug": "ready", "status": "approved_for_publish"}, {"slug": "published", "status": "published_local"}])
    plan = EditorialStateReset(root=tmp_path).plan()
    assert plan["stale_count"] == 0
    assert "published" in plan["protected_slugs"]
    assert plan["excluded_candidates"]["ready"] == "approved, ready, published, or live state"
