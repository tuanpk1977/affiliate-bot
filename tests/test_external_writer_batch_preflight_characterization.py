from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import modules.external_writer_pipeline as pipeline
from modules.external_writer_pipeline import UniversalExternalWriterExporter


def _exporter(root: Path) -> UniversalExternalWriterExporter:
    return UniversalExternalWriterExporter(root=root)


def _resolution(root: Path, **overrides: object) -> SimpleNamespace:
    values: dict[str, object] = {
        "canonical_dir": root / "data" / "research" / "alpha",
        "enrichment_report_file": root / "data" / "research" / "alpha" / "report.json",
        "missing_files": [],
        "legacy_reasons": [],
        "status": "READY",
        "article_ready": True,
        "research_level": "verified",
        "draft_exportable": True,
        "comparison_status": "READY",
        "outstanding_research_tasks": [],
        "weak_sections": [],
        "estimated_publish_readiness": 0.9,
        "paragraph_count": 4,
        "claim_count": 3,
        "coverage_score": 0.8,
        "angle_profile": "review",
        "required_entity_count": 2,
        "resolved_entity_count": 2,
        "entity_coverage_score": 1.0,
        "candidate_claim_count": 3,
        "rejected_claim_count": 0,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_active_batches_empty_when_no_queue_or_advanced_batch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    exporter = _exporter(tmp_path)
    monkeypatch.setattr(exporter.queue, "list_tasks", lambda **_: [])
    monkeypatch.setattr(exporter.queue, "_resolve_website_date", lambda _: (_ for _ in ()).throw(FileNotFoundError()))
    assert exporter.active_batches() == []


def test_active_batches_selects_latest_date_per_type_in_sorted_type_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    exporter = _exporter(tmp_path)
    rows = [
        {"task_id": "social-old", "article_slug": "social-old", "task_type": "SOCIAL_FX", "batch_date": "2026-01-01", "social_mode": "SOURCE_BASED_SOCIAL"},
        {"task_id": "website-new", "article_slug": "website-new", "task_type": "WEBSITE_STANDARD", "batch_date": "2026-01-03"},
        {"task_id": "social-new", "article_slug": "social-new", "task_type": "SOCIAL_FX", "batch_date": "2026-01-02", "social_mode": "SOURCE_BASED_SOCIAL"},
        {"task_id": "website-old", "article_slug": "website-old", "task_type": "WEBSITE_STANDARD", "batch_date": "2026-01-01"},
    ]
    monkeypatch.setattr(exporter.queue, "list_tasks", lambda **_: rows)
    monkeypatch.setattr(exporter, "_partition_research_ready", lambda selected, _: (selected[:1], selected[1:]))
    monkeypatch.setattr(exporter.queue, "_resolve_website_date", lambda _: (_ for _ in ()).throw(FileNotFoundError()))
    monkeypatch.setattr(pipeline, "resolve_research_artifacts", lambda *_, **__: _resolution(tmp_path))

    result = exporter.active_batches()

    assert [row["task_type"] for row in result] == ["SOCIAL_FX", "WEBSITE_STANDARD"]
    assert [row["batch_date"] for row in result] == ["2026-01-02", "2026-01-03"]
    assert [[task["task_id"] for task in row["tasks"]] for row in result] == [["social-new"], ["website-new"]]
    assert all(row["task_count"] == row["eligible"] == 1 and row["held"] == 0 for row in result)


def test_active_batches_appends_distinct_advanced_preflight(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    exporter = _exporter(tmp_path)
    monkeypatch.setattr(exporter.queue, "list_tasks", lambda **_: [])
    monkeypatch.setattr(exporter.queue, "_resolve_website_date", lambda _: "2026-01-04")
    path = tmp_path / "data" / "editorial_queue" / "2026-01-04" / "topics.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"mode": "advanced", "topics": [{"slug": "alpha"}]}), encoding="utf-8")
    monkeypatch.setattr(pipeline, "resolve_research_artifacts", lambda *_, **__: _resolution(tmp_path))
    result = exporter.active_batches()
    assert len(result) == 1
    assert result[0]["task_type"] == "WEBSITE_ADVANCED"
    assert result[0]["batch_date"] == "2026-01-04"


def test_advanced_preflight_ignores_missing_or_non_advanced_queue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    exporter = _exporter(tmp_path)
    monkeypatch.setattr(exporter.queue, "_resolve_website_date", lambda _: "2026-01-04")
    assert exporter._advanced_editorial_preflight("latest") is None
    path = tmp_path / "data" / "editorial_queue" / "2026-01-04" / "topics.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"mode": "standard", "topics": [{"slug": "alpha"}]}), encoding="utf-8")
    assert exporter._advanced_editorial_preflight("latest") is None
    path.write_text(json.dumps({"mode": "advanced", "topics": [{"slug": ""}, None]}), encoding="utf-8")
    assert exporter._advanced_editorial_preflight("latest") is None


def test_advanced_preflight_projects_evidence_and_reason(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    exporter = _exporter(tmp_path)
    monkeypatch.setattr(exporter.queue, "_resolve_website_date", lambda _: "2026-01-04")
    path = tmp_path / "data" / "editorial_queue" / "2026-01-04" / "topics.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"mode": "advanced", "topics": [{"slug": "alpha", "root_topic_id": "root"}]}), encoding="utf-8")
    monkeypatch.setattr(pipeline, "resolve_research_artifacts", lambda *_, **__: _resolution(tmp_path))

    result = exporter._advanced_editorial_preflight("latest")

    assert result is not None
    assert result["task_type"] == "WEBSITE_ADVANCED"
    assert result["task_count"] == result["eligible"] == 1
    assert result["held"] == 0
    assert result["tasks"][0]["task_id"] == "website-advanced-2026-01-04-alpha"
    assert result["tasks"][0]["reason"] == "Research evidence is ready."


def test_preflight_rows_source_based_social_inherits_evidence_without_resolver(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    exporter = _exporter(tmp_path)
    monkeypatch.setattr(pipeline, "resolve_research_artifacts", lambda *_, **__: pytest.fail("unexpected resolver"))
    task = {"task_id": "social-1", "task_type": "SOCIAL_FX", "article_slug": "alpha", "social_mode": "SOURCE_BASED_SOCIAL", "source_revision_id": "r1"}
    result = exporter._preflight_task_rows([task], [task], [])
    assert len(result) == 1
    assert result[0]["research_state"] == "EVIDENCE_INHERITED"
    assert result[0]["eligible"] is True
    assert result[0]["source_revision_id"] == "r1"
    assert result[0]["reason"].startswith("Verified Website source evidence is inherited")


def test_preflight_rows_website_uses_hold_reason_and_preserves_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    exporter = _exporter(tmp_path)
    monkeypatch.setattr(pipeline, "resolve_research_artifacts", lambda *_, **__: _resolution(tmp_path))
    ready = {"task_id": "ready", "article_slug": "alpha", "batch_date": "2026-01-04"}
    held = {"task_id": "held", "article_slug": "beta", "batch_date": "2026-01-04"}
    result = exporter._preflight_task_rows([held, ready], [ready], [{**held, "reason": "Blocked by source"}])
    assert [row["task_id"] for row in result] == ["held", "ready"]
    assert [row["eligible"] for row in result] == [False, True]
    assert [row["reason"] for row in result] == ["Blocked by source", "Research evidence is ready."]
    assert result[0]["coverage_score"] == 0.8
