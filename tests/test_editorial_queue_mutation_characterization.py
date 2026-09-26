from __future__ import annotations

import builtins
import json
from pathlib import Path

import pytest

from modules.daily_editorial_workflow import DailyEditorialWorkflow


def _workflow(root: Path) -> DailyEditorialWorkflow:
    return DailyEditorialWorkflow(
        root=root,
        data_dir=root / "data",
        site_output_dir=root / "site_output",
    )


def _write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_save_queue_and_batch_item_preserve_path_copy_and_unknown_contract(tmp_path: Path) -> None:
    workflow = _workflow(tmp_path)
    payload = {"date": "2026-09-26", "topics": [{"slug": "alpha", "status": "drafted"}]}

    workflow._save_queue("2026-09-26", payload)

    queue_path = tmp_path / "data" / "editorial_queue" / "2026-09-26" / "topics.json"
    assert json.loads(queue_path.read_text(encoding="utf-8")) == payload
    item = workflow._batch_item(batch_date="2026-09-26", slug="alpha")
    item["status"] = "local-only"
    assert workflow._batch_item(batch_date="2026-09-26", slug="alpha")["status"] == "drafted"
    with pytest.raises(ValueError, match="Unknown batch slug: missing"):
        workflow._batch_item(batch_date="2026-09-26", slug="missing")


def test_publish_row_returns_copy_or_empty_mapping(tmp_path: Path) -> None:
    workflow = _workflow(tmp_path)
    _write_json(
        tmp_path / "data" / "publish_queue.json",
        [{"slug": "alpha", "status": "approved_for_publish"}],
    )

    row = workflow._publish_row("alpha")
    row["status"] = "changed"

    assert workflow._publish_row("alpha") == {
        "slug": "alpha",
        "status": "approved_for_publish",
    }
    assert workflow._publish_row("missing") == {}


def test_copy_review_preview_copies_exact_bytes_and_missing_raises(tmp_path: Path) -> None:
    workflow = _workflow(tmp_path)
    source = tmp_path / "data" / "production_article_drafts" / "alpha" / "index.html"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"<h1>Alpha</h1>\r\n")

    target = workflow._copy_review_preview(slug="alpha", batch_date="2026-09-26")

    assert target == tmp_path / "site_output" / "review" / "2026-09-26" / "alpha" / "index.html"
    assert target.read_bytes() == source.read_bytes()
    with pytest.raises(FileNotFoundError, match="Draft preview missing for missing"):
        workflow._copy_review_preview(slug="missing", batch_date="2026-09-26")


def test_batch_status_updates_and_missing_queue_fail_open_contract(tmp_path: Path) -> None:
    workflow = _workflow(tmp_path)
    workflow._save_queue(
        "2026-09-26",
        {"topics": [{"slug": "alpha", "status": "drafted"}, {"slug": "beta", "status": "drafted"}]},
    )

    workflow._update_batch_status(
        batch_date="2026-09-26",
        slug="alpha",
        status="approved",
        extra={"approved_by": "operator"},
    )
    workflow._update_batch_status_if_present(
        batch_date="2026-09-26",
        slug="beta",
        extra={"validation": "passed"},
    )
    workflow._update_batch_status_if_present(
        batch_date="2099-01-01",
        slug="missing",
        status="ignored",
    )

    saved = workflow._load_queue("2026-09-26")["topics"]
    assert saved == [
        {"slug": "alpha", "status": "approved", "approved_by": "operator"},
        {"slug": "beta", "status": "drafted", "validation": "passed"},
    ]
    assert not (tmp_path / "data" / "editorial_queue" / "2099-01-01").exists()


def test_upsert_topics_replaces_in_place_appends_and_refreshes_batch_fields(tmp_path: Path) -> None:
    workflow = _workflow(tmp_path)
    workflow._save_queue(
        "2026-09-26",
        {
            "generated_at": "old",
            "mode": "old",
            "count": 2,
            "topics": [{"slug": "alpha", "value": 1}, {"slug": "beta", "value": 2}],
        },
    )

    result = workflow._upsert_topics_into_batch(
        batch_date="2026-09-26",
        topics=[{"slug": "alpha", "value": 3}, {"slug": "gamma", "value": 4}],
        mode="custom",
    )

    assert result["mode"] == "custom"
    assert result["count"] == 3
    assert result["generated_at"] != "old"
    assert result["topics"] == [
        {"slug": "alpha", "value": 3},
        {"slug": "beta", "value": 2},
        {"slug": "gamma", "value": 4},
    ]
    assert workflow._load_queue("2026-09-26") == result


def test_upsert_topics_creates_missing_batch_with_week_contract(tmp_path: Path) -> None:
    workflow = _workflow(tmp_path)

    result = workflow._upsert_topics_into_batch(
        batch_date="2026-09-26",
        topics=[{"slug": "alpha"}],
        mode="partner",
    )

    assert result["date"] == "2026-09-26"
    assert result["week_start"] == "2026-09-21"
    assert result["week_end"] == "2026-09-27"
    assert result["mode"] == "partner"
    assert result["count"] == 1


def test_queue_entry_non_draft_preserves_normalization_and_source_order(tmp_path: Path) -> None:
    workflow = _workflow(tmp_path)

    entry = workflow._queue_entry_from_request_result(
        keyword="Alpha",
        slug="alpha",
        result={"quality_gate": {"passed": False}},
        batch_date="2026-09-26",
        category=" AI ",
        intent=" ",
        content_type="review",
        source_type="custom_topic",
        partner_name=" Partner ",
        official_url=" https://official.example ",
        affiliate_url="",
        pricing_url=" https://official.example/pricing ",
        cluster_article_number=0,
        cluster_article_total=0,
        suggested_article_angle="Angle",
    )

    assert entry["status"] == "needs_enrichment"
    assert entry["search_intent"] == "commercial research"
    assert entry["category"] == "AI"
    assert entry["partner_name"] == "Partner"
    assert entry["cluster_article_number"] == 1
    assert entry["cluster_article_total"] == 1
    assert entry["source_urls"] == [
        "https://official.example",
        "https://official.example/pricing",
    ]
    assert entry["draft_dir"] == ""
    assert entry["review_preview"] == ""
    assert entry["research_quality_gate"] == {"passed": False}
    assert entry["error"] == "Research/source quality gate blocked draft generation."


def test_queue_entry_drafted_adds_preview_and_files_but_missing_preview_is_tolerated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workflow = _workflow(tmp_path)
    preview = tmp_path / "preview" / "index.html"
    monkeypatch.setattr(workflow, "_copy_review_preview", lambda **_: preview)
    arguments = dict(
        keyword="Alpha",
        slug="alpha",
        result={"draft": {"ok": True}},
        batch_date="2026-09-26",
        category="AI",
        intent="commercial",
        content_type="review",
        source_type="custom_topic",
        partner_name="",
        official_url="",
        affiliate_url="",
        pricing_url="",
        cluster_article_number=1,
        cluster_article_total=1,
        suggested_article_angle="Angle",
    )

    entry = workflow._queue_entry_from_request_result(**arguments)
    assert entry["status"] == "drafted"
    assert entry["review_preview"] == str(preview)
    assert entry["draft_file"].endswith("production_article_drafts\\alpha\\index.html")
    assert entry["metadata_file"].endswith("production_article_drafts\\alpha\\metadata.json")
    assert entry["error"] == ""

    def missing(**_: object) -> Path:
        raise FileNotFoundError("missing")

    monkeypatch.setattr(workflow, "_copy_review_preview", missing)
    tolerated = workflow._queue_entry_from_request_result(**arguments)
    assert tolerated["status"] == "drafted"
    assert tolerated["review_preview"] == ""
    assert "draft_file" not in tolerated


def test_custom_topic_request_templates_preserve_empty_single_order_and_cap(tmp_path: Path) -> None:
    workflow = _workflow(tmp_path)

    assert workflow._build_custom_topic_requests(topic_name="  ", category="x", intent="y", count=3) == []
    assert workflow._build_custom_topic_requests(
        topic_name=" Alpha Tool ", category=" Cat ", intent=" buy ", count=1
    ) == [
        {
            "topic": "Alpha Tool",
            "content_type": "review",
            "suggested_article_angle": "Custom topic request for Alpha Tool",
            "category": "Cat",
            "intent": "buy",
        }
    ]
    cluster = workflow._build_custom_topic_requests(
        topic_name="Alpha Tool", category="Cat", intent="buy", count=99
    )
    assert [row["content_type"] for row in cluster] == [
        "review",
        "pricing",
        "alternatives",
        "pros_cons",
        "tutorial",
        "comparison",
        "affiliate_program",
        "faq",
    ]


def test_partner_cluster_templates_preserve_default_order_and_cap(tmp_path: Path) -> None:
    workflow = _workflow(tmp_path)

    defaulted = workflow._build_partner_cluster_topics(partner_name="Partner X", count=0)
    capped = workflow._build_partner_cluster_topics(partner_name="Partner X", count=99)

    assert defaulted == capped
    assert len(defaulted) == 8
    assert [row["content_type"] for row in defaulted] == [
        "review",
        "pricing",
        "alternatives",
        "pros_cons",
        "tutorial",
        "affiliate_program",
        "comparison",
        "faq",
    ]
    assert all(row["category"] == "Affiliate Partner" for row in defaulted)


def test_carry_forward_filters_known_and_ineligible_rows_preserving_input_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workflow = _workflow(tmp_path)
    monkeypatch.setattr(
        workflow.console,
        "_load_metadata",
        lambda slug: {"title": "Metadata Alpha"} if slug == "alpha" else {},
    )
    rows = {
        "one": {"slug": "alpha", "status": "approved_for_publish", "title": "Row Alpha"},
        "two": {"slug": "known", "status": "published_local"},
        "three": {"slug": "blocked", "status": "drafted"},
        "four": {"slug": "beta", "status": "published_local", "title": "Row Beta"},
        "five": {"slug": "", "status": "approved_for_publish"},
    }

    result = workflow._carry_forward_publish_candidates(
        batch_date="2026-09-26",
        topics=[{"slug": "known"}],
        publish_rows=rows,
    )

    assert result == [
        {
            "keyword": "Metadata Alpha",
            "slug": "alpha",
            "status": "approved",
            "carry_forward": True,
            "batch_date": "2026-09-26",
        },
        {
            "keyword": "Row Beta",
            "slug": "beta",
            "status": "published",
            "carry_forward": True,
            "batch_date": "2026-09-26",
        },
    ]


def test_affiliate_partner_upsert_maps_fields_and_import_failure_is_fail_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workflow = _workflow(tmp_path)
    captured: list[dict[str, object]] = []
    monkeypatch.setattr("modules.affiliate_links.upsert_affiliate_link", lambda row: captured.append(row))
    profile = {
        "name": " Partner X ",
        "slug": " partner-x ",
        "official_url": " https://official.example ",
        "affiliate_url": " https://affiliate.example ",
        "contact_note": " Contact ",
        "commission_note": " 20% ",
        "payout_note": "",
    }

    workflow._upsert_affiliate_partner_record(profile)

    assert captured == [
        {
            "brand": " Partner X ",
            "slug": " partner-x ",
            "official_url": " https://official.example ",
            "affiliate_url": " https://affiliate.example ",
            "status": "approved",
            "affiliate_status": "approved",
            "notes": " Contact ",
            "commission_note": " 20% ",
            "network": "Direct",
            "approved": True,
        }
    ]

    original_import = builtins.__import__

    def blocked_import(name: str, *args: object, **kwargs: object):
        if name == "modules.affiliate_links":
            raise ImportError("blocked")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked_import)
    assert workflow._upsert_affiliate_partner_record(profile) is None
