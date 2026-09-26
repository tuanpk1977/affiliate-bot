from __future__ import annotations

import hashlib
import json
from pathlib import Path

import modules.external_writer_pipeline as pipeline
from modules.external_writer_pipeline import UniversalExternalWriterExporter


def _write(path: Path, value: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")
    return path


def _write_json(path: Path, value: object) -> Path:
    return _write(path, json.dumps(value))


def test_existing_article_snapshot_prefers_markdown_and_metadata(tmp_path: Path) -> None:
    slug = "refresh-me"
    source = tmp_path / "data" / "production_article_drafts" / slug
    _write(source / "article.md", "current markdown")
    _write_json(source / "metadata.json", {"slug": slug})
    _write(source / "index.html", "<p>fallback only</p>")
    package = tmp_path / "package"

    UniversalExternalWriterExporter(root=tmp_path)._copy_existing_article_snapshot(
        package,
        {
            "article_slug": slug,
            "refresh_reason": ["stale"],
            "refresh_scope": ["pricing"],
        },
    )

    target = package / "existing_article" / slug
    assert (target / "article.md").read_text(encoding="utf-8") == "current markdown"
    assert json.loads((target / "metadata.json").read_text(encoding="utf-8")) == {"slug": slug}
    assert not (target / "current_article.html").exists()
    contract = json.loads((target / "refresh_contract.json").read_text(encoding="utf-8"))
    assert contract == {
        "schema_version": "existing_article_refresh_contract_v1",
        "task_type": "UPDATE EXISTING ARTICLE",
        "existing_slug": slug,
        "preserve_slug": True,
        "create_new_url": False,
        "refresh_reason": ["stale"],
        "refresh_scope": ["pricing"],
        "snapshot_files": ["article.md", "metadata.json"],
        "human_approval_required": True,
    }


def test_existing_article_snapshot_html_fallback_and_empty_contract(tmp_path: Path) -> None:
    exporter = UniversalExternalWriterExporter(root=tmp_path)
    _write(
        tmp_path / "data" / "production_article_drafts" / "html-only" / "index.html",
        "<h1>Current</h1>",
    )
    package = tmp_path / "package"

    exporter._copy_existing_article_snapshot(package, {"article_slug": "html-only"})
    exporter._copy_existing_article_snapshot(package, {"article_slug": "missing"})

    assert (package / "existing_article" / "html-only" / "current_article.html").is_file()
    html_contract = json.loads(
        (package / "existing_article" / "html-only" / "refresh_contract.json").read_text(encoding="utf-8")
    )
    empty_contract = json.loads(
        (package / "existing_article" / "missing" / "refresh_contract.json").read_text(encoding="utf-8")
    )
    assert html_contract["snapshot_files"] == ["current_article.html"]
    assert empty_contract["snapshot_files"] == []
    assert empty_contract["refresh_reason"] == []
    assert empty_contract["refresh_scope"] == []


def test_website_research_artifacts_filter_and_inventory_contract(
    tmp_path: Path, monkeypatch
) -> None:
    slug = "alpha"
    source = tmp_path / "data" / "research" / slug
    first = _write(source / "a.md", "alpha")
    nested = _write(source / "nested" / "b.json", "{}")
    _write(source / "private-token.txt", "secret")
    _write(source / ".hidden" / "ignored.md", "hidden")
    _write(source / "binary.bin", "binary")
    _write(source / "AFFILIATE_OPPORTUNITY_BRIEF.json", "old")
    monkeypatch.setattr(
        pipeline,
        "build_affiliate_opportunity_brief",
        lambda root, requested_slug: {"slug": requested_slug, "generated": True},
    )
    package = tmp_path / "package"

    UniversalExternalWriterExporter(root=tmp_path)._copy_website_research_artifacts(package, slug)

    target = package / "research" / slug
    assert (target / "a.md").read_text(encoding="utf-8") == "alpha"
    assert (target / "nested" / "b.json").is_file()
    assert not (target / "private-token.txt").exists()
    assert not (target / ".hidden").exists()
    assert not (target / "binary.bin").exists()
    assert json.loads((target / "AFFILIATE_OPPORTUNITY_BRIEF.json").read_text(encoding="utf-8")) == {
        "slug": slug,
        "generated": True,
    }
    inventory = json.loads((target / "research_inventory.json").read_text(encoding="utf-8"))
    assert inventory["artifact_count"] == 2
    assert inventory["artifacts"] == [
        {
            "path": "research/alpha/a.md",
            "source": "data/research/alpha/a.md",
            "sha256": hashlib.sha256(first.read_bytes()).hexdigest(),
        },
        {
            "path": "research/alpha/nested/b.json",
            "source": "data/research/alpha/nested/b.json",
            "sha256": hashlib.sha256(nested.read_bytes()).hexdigest(),
        },
    ]


def test_website_research_missing_source_is_noop(tmp_path: Path) -> None:
    package = tmp_path / "package"
    UniversalExternalWriterExporter(root=tmp_path)._copy_website_research_artifacts(package, "missing")
    assert not package.exists()


def test_series_history_filters_orders_limits_and_sanitizes_metadata(tmp_path: Path) -> None:
    draft_root = tmp_path / "data" / "production_article_drafts"
    for number in range(9):
        slug = f"prior-{number}"
        _write_json(
            draft_root / slug / "metadata.json",
            {
                "slug": slug,
                "title": f"Prior {number}",
                "root_topic_id": "root-1",
                "series_id": "series",
                "batch_date": f"2026-09-{number + 1:02d}",
                "ignored": "not exported",
            },
        )
        _write(draft_root / slug / "article.md", slug)
    _write_json(draft_root / "current" / "metadata.json", {"slug": "current", "root_topic_id": "root-1"})
    _write(draft_root / "current" / "article.md", "current")
    _write_json(draft_root / "other" / "metadata.json", {"slug": "other", "root_topic_id": "root-2"})
    _write(draft_root / "other" / "article.md", "other")
    package = tmp_path / "package"

    UniversalExternalWriterExporter(root=tmp_path)._copy_series_history(
        package,
        {"article_slug": "current", "root_topic_id": "root-1"},
    )

    history = package / "research" / "current" / "series_history"
    assert sorted(path.name for path in history.iterdir()) == [f"prior-{number}" for number in range(7)]
    context = json.loads((history / "prior-0" / "context.json").read_text(encoding="utf-8"))
    assert context == {
        "slug": "prior-0",
        "title": "Prior 0",
        "root_topic_id": "root-1",
        "series_id": "series",
        "batch_date": "2026-09-01",
    }


def test_series_history_without_root_or_draft_tree_is_noop(tmp_path: Path) -> None:
    exporter = UniversalExternalWriterExporter(root=tmp_path)
    package = tmp_path / "package"
    exporter._copy_series_history(package, {"article_slug": "current"})
    exporter._copy_series_history(package, {"article_slug": "current", "root_topic_id": "root"})
    assert not package.exists()


def test_guidance_materialization_preserves_layout_and_filters_trees(tmp_path: Path) -> None:
    _write(tmp_path / "PROJECT_GUIDE.md", "guide")
    _write(tmp_path / "docs" / "editorial" / "ARTICLE_TEMPLATE.md", "template")
    _write(tmp_path / "docs" / "examples" / "one.md", "example")
    _write(tmp_path / "docs" / "examples" / "ignored.txt", "ignored")
    _write(tmp_path / "docs" / "editorial" / "editorial_brain" / "nested" / "brain.json", "{}")
    _write(tmp_path / "docs" / "editorial" / "editorial_brain" / "ignored.py", "pass")
    _write(tmp_path / "editorial_memory" / "memory.txt", "memory")
    _write(tmp_path / "gold_library" / "gold.md", "gold")
    package = tmp_path / "package"

    UniversalExternalWriterExporter(root=tmp_path)._copy_guidance(package)

    assert (package / "templates" / "PROJECT_GUIDE.md").read_text(encoding="utf-8") == "guide"
    assert (package / "templates" / "docs__editorial__ARTICLE_TEMPLATE.md").is_file()
    assert (package / "examples" / "one.md").is_file()
    assert not (package / "examples" / "ignored.txt").exists()
    assert (package / "editorial_brain" / "nested" / "brain.json").is_file()
    assert not (package / "editorial_brain" / "ignored.py").exists()
    assert (package / "editorial_memory" / "memory.txt").is_file()
    assert (package / "gold_library" / "gold.md").is_file()


def test_copy_inputs_materializes_facts_sources_images_and_research(tmp_path: Path) -> None:
    task = {
        "article_slug": "social-item",
        "task_id": "task-1",
        "task_type": "SOCIAL_HOT_NEWS",
        "batch_date": "2026-09-26",
        "research_files": ["inputs/research.md", "inputs/missing.md"],
        "source_files": ["inputs/source.json"],
    }
    _write_json(tmp_path / "data" / "write_queue" / "task-1" / "verified_facts.json", {"ok": True})
    _write_json(tmp_path / "data" / "intelligence" / "verified_facts" / "task-1" / "fact_conflicts.json", [])
    _write(tmp_path / "inputs" / "research.md", "research")
    _write(tmp_path / "inputs" / "source.json", "{}")
    asset_root = tmp_path / "data" / "social_drafts" / "2026-09-26" / "social-item" / "assets"
    _write(asset_root / "image.PNG", "image")
    _write(asset_root / "ignored.gif", "ignored")
    package = tmp_path / "package"

    UniversalExternalWriterExporter(root=tmp_path)._copy_inputs(package, [task])

    assert (package / "research" / "social-item" / "verified_facts" / "verified_facts.json").is_file()
    assert (package / "research" / "social-item" / "verified_facts" / "fact_conflicts.json").is_file()
    assert (package / "research" / "social-item" / "research.md").is_file()
    assert (package / "official_sources" / "social-item" / "source.json").is_file()
    assert (package / "images" / "social-item" / "image.PNG").is_file()
    assert not (package / "images" / "social-item" / "ignored.gif").exists()


def test_copy_inputs_legacy_queue_suppresses_loose_research_files(tmp_path: Path) -> None:
    _write(tmp_path / "inputs" / "research.md", "research")
    package = tmp_path / "package"
    UniversalExternalWriterExporter(root=tmp_path)._copy_inputs(
        package,
        [
            {
                "article_slug": "strict",
                "task_id": "strict-task",
                "task_type": "SOCIAL_HOT_NEWS",
                "batch_date": "2026-09-26",
                "legacy_queue_file": "legacy.json",
                "research_files": ["inputs/research.md"],
            }
        ],
    )
    assert not (package / "research" / "strict" / "research.md").exists()


def test_copy_inputs_dispatches_website_update_and_advanced_helpers(
    tmp_path: Path, monkeypatch
) -> None:
    exporter = UniversalExternalWriterExporter(root=tmp_path)
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(
        exporter,
        "_copy_website_research_artifacts",
        lambda package, slug: calls.append(("research", slug)),
    )
    monkeypatch.setattr(
        exporter,
        "_copy_existing_article_snapshot",
        lambda package, task: calls.append(("snapshot", task["article_slug"])),
    )
    monkeypatch.setattr(
        exporter,
        "_copy_series_history",
        lambda package, task: calls.append(("history", task["article_slug"])),
    )
    base = {"batch_date": "2026-09-26", "research_files": [], "source_files": []}
    exporter._copy_inputs(
        tmp_path / "package",
        [
            {**base, "article_slug": "update", "task_id": "u", "task_type": "WEBSITE_UPDATE"},
            {**base, "article_slug": "advanced", "task_id": "a", "task_type": "WEBSITE_ADVANCED"},
        ],
    )
    assert calls == [
        ("research", "update"),
        ("snapshot", "update"),
        ("research", "advanced"),
        ("history", "advanced"),
    ]
