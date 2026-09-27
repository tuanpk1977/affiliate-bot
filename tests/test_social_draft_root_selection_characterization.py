from __future__ import annotations

import hashlib
import json

from modules.social import draft_workflow as legacy
from modules.social.utils import PublishedArticle


def _write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _article(slug, *, description="", image="", headings=None, key_points=None):
    return PublishedArticle(
        article_id=slug, title=slug.title(), url=f"https://example.test/{slug}/",
        description=description, image=image, tags=[], publish_date="2026-09-01",
        headings=headings or [], key_points=key_points or [],
    )


def test_research_source_count_handles_nested_urls_duplicates_and_malformed_json(tmp_path):
    root = tmp_path / "data" / "research" / "one"
    _write_json(root / "sources.json", {"url": "https://a.test", "nested": [{"source_url": "https://a.test"}, {"link": "https://b.test"}, {"url": "local"}]})
    (root / "bad.json").write_text("{", encoding="utf-8")
    workflow = legacy.SocialDraftWorkflow(root=tmp_path)
    assert workflow._research_source_count("missing") == 0
    assert workflow._research_source_count("one") == 2


def test_rank_articles_sorts_score_then_slug_and_selects_two(tmp_path, monkeypatch):
    workflow = legacy.SocialDraftWorkflow(root=tmp_path)
    articles = {
        "low": _article("low"),
        "zeta": _article("zeta", description="Pricing comparison for business workflow software. " * 3, image="https://example.test/a.png", headings=["A", "B", "C", "D"], key_points=["A", "B", "C", "D"]),
        "alpha": _article("alpha", description="Pricing comparison for business workflow software. " * 3, image="https://example.test/a.png", headings=["A", "B", "C", "D"], key_points=["A", "B", "C", "D"]),
    }
    monkeypatch.setattr(workflow, "article_from_live_row", lambda row: articles[row["slug"]])
    for slug in ("alpha", "zeta"):
        _write_json(tmp_path / "data" / "research" / slug / "sources.json", {
            "sources": [{"url": f"https://example.test/{index}"} for index in range(3)]
        })
    result = workflow.rank_articles([{"slug": "zeta"}, {"slug": "low"}, {"slug": "alpha"}])
    assert [row["slug"] for row in result] == ["alpha", "zeta", "low"]
    assert [row["selected"] for row in result] == [True, True, False]
    assert result[0]["source_count"] == 3
    assert result[2]["reason"] == "basic live article metadata"


def test_weekly_website_roots_require_locked_manifest_and_limit(tmp_path):
    workflow = legacy.SocialDraftWorkflow(root=tmp_path)
    path = tmp_path / "data" / "editorial_queue" / "weeks" / "2026-08-31" / "week.json"
    _write_json(path, {"lock_status": "open", "topics": [{"slug": "one"}]})
    assert workflow._website_weekly_roots("bad") == []
    assert workflow._website_weekly_roots("2026-09-01") == []
    _write_json(path, {"lock_status": "locked", "topics": [{"slug": "one"}, {"slug": "two"}, {"slug": "three"}]})
    assert [row["slug"] for row in workflow._website_weekly_roots("2026-09-01")] == ["one", "two"]


def test_website_root_bindings_project_current_cycle_and_parent_fallback(tmp_path):
    workflow = legacy.SocialDraftWorkflow(root=tmp_path)
    roots = [{"root_topic_id": "root", "parent_slug": "parent", "title": "Root Title"}]
    _write_json(tmp_path / "data" / "editorial_queue" / "2026-09-01" / "topics.json", {"topics": [{"slug": "child", "root_topic_id": "root", "daily_angle": "Fresh angle"}, {"slug": "other", "root_topic_id": "unknown"}]})
    assert workflow._website_root_bindings(batch_date="bad", roots=roots) == {}
    rows = workflow._website_root_bindings(batch_date="2026-09-01", roots=roots)
    assert list(rows) == ["child", "parent"]
    assert rows["child"]["source_batch_date"] == "2026-09-01"
    assert rows["child"]["today_social_angle"] == "Fresh angle"
    assert rows["parent"]["social_angle"] == "root_topic_adaptation"


def test_source_binding_preserves_revision_and_evidence_projection(tmp_path):
    workflow = legacy.SocialDraftWorkflow(root=tmp_path)
    page = tmp_path / "data" / "production_article_drafts" / "one" / "index.html"
    page.parent.mkdir(parents=True)
    page.write_text("<p>Original</p>", encoding="utf-8")
    _write_json(page.parent / "metadata.json", {"human_approval": {"approved_revision_id": "approved-7"}})
    research = tmp_path / "data" / "research" / "one"
    _write_json(research / "FACT_LEDGER.json", {})
    _write_json(research / "enrichment_report.json", {"status": "RESEARCH_GOOD", "blockers": []})
    row = workflow._source_binding("one", {"marker": "kept"})
    assert row["marker"] == "kept"
    assert row["source_revision_id"] == "approved-7"
    assert row["source_content_hash"] == hashlib.sha256(page.read_bytes()).hexdigest()
    assert row["source_evidence_reference"] == "data/research/one/FACT_LEDGER.json"
    assert row["evidence_inheritance"] == "VERIFIED_SOURCE_ARTICLE"
    assert row["source_research_state"] == "PASSED"


def test_weekly_roots_read_empty_and_derive_earlier_manifest(tmp_path, monkeypatch):
    workflow = legacy.SocialDraftWorkflow(root=tmp_path)
    assert workflow._read_weekly_social_roots("bad") == {}
    monkeypatch.setattr(workflow, "_social_batch_dates", lambda: ["2026-08-31", "2026-09-01"])
    _write_json(tmp_path / "data" / "social_drafts" / "2026-08-31" / "manifest.json", {"items": [{"slug": "one"}, {"slug": "two"}, {"slug": "three"}]})
    result = workflow._read_weekly_social_roots("2026-09-02")
    assert result["root_slugs"] == ["one", "two"]
    assert result["source_batch_date"] == "2026-08-31"


def test_weekly_roots_write_preserves_existing_created_at(tmp_path, monkeypatch):
    workflow = legacy.SocialDraftWorkflow(root=tmp_path)
    monkeypatch.setattr(legacy, "now_iso", lambda: "new-time")
    first = workflow._write_weekly_social_roots(batch_date="2026-09-01", ranking=[{"slug": "one"}], selected=[{"slug": "one"}])
    assert first["created_at"] == "new-time"
    monkeypatch.setattr(legacy, "now_iso", lambda: "later-time")
    second = workflow._write_weekly_social_roots(batch_date="2026-09-01", ranking=[], selected=[{"slug": "two"}])
    assert second["created_at"] == "new-time"
    assert second["root_slugs"] == ["two"]


def test_cycle_angle_history_only_prior_approved_distinct_angles(tmp_path):
    workflow = legacy.SocialDraftWorkflow(root=tmp_path)
    assert workflow._current_cycle_angle_history(batch_date="bad", root_topic_id="root", platform="facebook") == []
    base = tmp_path / "data" / "social_drafts" / "2026-08-31"
    _write_json(base / "one" / "facebook" / "metadata.json", {"root_topic_id": "root", "status": "approved_for_copy", "today_social_angle": "Angle A"})
    _write_json(base / "two" / "facebook" / "metadata.json", {"root_topic_id": "root", "status": "published_manual", "today_social_angle": "Angle A"})
    _write_json(base / "three" / "facebook" / "metadata.json", {"root_topic_id": "root", "status": "draft", "today_social_angle": "Angle B"})
    _write_json(tmp_path / "data" / "social_drafts" / "2026-09-01" / "one" / "facebook" / "metadata.json", {"root_topic_id": "root", "status": "approved_for_copy", "today_social_angle": "Current"})
    assert workflow._current_cycle_angle_history(batch_date="2026-09-01", root_topic_id="root", platform="facebook") == ["Angle A"]


def test_live_row_for_weekly_root_uses_docs_fallback(tmp_path):
    workflow = legacy.SocialDraftWorkflow(root=tmp_path)
    assert workflow._live_row_for_weekly_root("missing", "2026-09-01", {}) is None
    existing = {"slug": "one", "url": "https://example.test/one/"}
    assert workflow._live_row_for_weekly_root("one", "2026-09-01", {"one": existing}) is existing
    page = tmp_path / "docs" / "two" / "index.html"
    page.parent.mkdir(parents=True)
    page.write_text('<title>Two Article</title><link rel="canonical" href="https://example.test/two/">', encoding="utf-8")
    row = workflow._live_row_for_weekly_root("two", "2026-09-01", {})
    assert row["slug"] == "two"
    assert row["source"] == "weekly_social_root_docs_fallback"
    assert row["url"] == "https://example.test/two/"
