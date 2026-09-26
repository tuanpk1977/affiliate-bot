from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

import modules.external_writer_pipeline as legacy
from modules.external_writer_pipeline import (
    _CachedOnlySourceRetriever,
    _website_source_preflight,
)
from modules.research_enrichment import SourceRetriever


APPROVED_STATUSES = (
    "verified",
    "approved",
    "cache_hit",
    "retrieved",
    "not_modified_cache",
    "stale_cache_fallback",
)


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _task(**changes: object) -> dict[str, object]:
    task: dict[str, object] = {
        "task_id": "website-advanced-2026-09-24-alpha",
        "task_type": "WEBSITE_ADVANCED",
        "batch_date": "2026-09-24",
        "article_slug": "alpha",
    }
    task.update(changes)
    return task


def _resolution(**changes: object) -> SimpleNamespace:
    values: dict[str, object] = {
        "source_quality_score": 40.0,
        "failing_gates": (),
        "draft_exportable": True,
    }
    values.update(changes)
    return SimpleNamespace(**values)


def _patch_resolution(monkeypatch: pytest.MonkeyPatch, **changes: object) -> None:
    owner = sys.modules[_website_source_preflight.__module__]
    monkeypatch.setattr(owner, "resolve_research_artifacts", lambda *args, **kwargs: _resolution(**changes))


def _tree(root: Path) -> dict[str, bytes]:
    if not root.exists():
        return {}
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


def test_legacy_symbols_are_directly_accessible() -> None:
    assert legacy._website_source_preflight is _website_source_preflight
    assert legacy._CachedOnlySourceRetriever is _CachedOnlySourceRetriever


def test_preflight_return_shape_sorting_url_filtering_and_no_input_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_resolution(monkeypatch)
    task = _task(
        primary_source_url=" https://z.example/docs ",
        supporting_source_urls=[
            "http://a.example/source",
            "ftp://ignored.example/file",
            "https://z.example/docs",
            "not-a-url",
        ],
    )
    original = json.loads(json.dumps(task))

    result = _website_source_preflight(tmp_path, task)

    assert result == {
        "ready": True,
        "approved_source_urls": ["http://a.example/source", "https://z.example/docs"],
        "verified_source_score": 40.0,
        "canonical_eligibility": True,
        "quality_report": "data/research/alpha/research_quality.json",
        "blockers": [],
    }
    assert task == original
    assert _tree(tmp_path) == {}


@pytest.mark.parametrize("status", APPROVED_STATUSES)
@pytest.mark.parametrize(
    ("filename", "wrapper"),
    (
        ("source_inventory.json", lambda row: [row]),
        ("SOURCE_EXCERPTS.json", lambda row: {"verified_sources": [row]}),
        ("package.json", lambda row: {"trusted_sources": [row]}),
    ),
)
def test_preflight_accepts_current_artifact_files_shapes_and_statuses(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    status: str,
    filename: str,
    wrapper,
) -> None:
    _patch_resolution(monkeypatch)
    row = {"final_url": "https://evidence.example/item", "retrieval_status": status}
    _write_json(tmp_path / "data/research/alpha" / filename, wrapper(row))

    result = _website_source_preflight(tmp_path, _task())

    assert result["ready"] is True
    assert result["approved_source_urls"] == ["https://evidence.example/item"]


def test_preflight_reads_all_supported_row_keys_and_ignores_invalid_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_resolution(monkeypatch)
    _write_json(
        tmp_path / "data/research/alpha/source_inventory.json",
        {
            "sources": [
                {"canonical_url": "https://a.example", "verification_status": "VERIFIED"},
                {"source_url": "https://b.example", "source_status": "approved"},
                {"url": "https://c.example", "status": "retrieved"},
                {"final_url": "https://d.example", "retrieval_status": "cache_hit"},
                {"source_url": "https://ignored.example", "status": "pending"},
                {"source_url": "file:///ignored", "status": "verified"},
                "not-a-row",
            ],
            "source_inventory": [{"url": "https://e.example", "status": "approved"}],
        },
    )

    result = _website_source_preflight(tmp_path, _task())

    assert result["approved_source_urls"] == [
        "https://a.example",
        "https://b.example",
        "https://c.example",
        "https://d.example",
        "https://e.example",
    ]


def test_preflight_missing_empty_malformed_and_unsupported_artifacts_fall_back_read_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_resolution(monkeypatch, source_quality_score=None, draft_exportable=False)
    research = tmp_path / "data/research/alpha"
    research.mkdir(parents=True)
    (research / "source_inventory.json").write_text("{broken", encoding="utf-8")
    _write_json(research / "SOURCE_EXCERPTS.json", "unsupported-string-payload")
    _write_json(research / "package.json", {"sources": {"not": "a-list"}})
    before = _tree(tmp_path)

    result = _website_source_preflight(tmp_path, _task())

    assert result == {
        "ready": False,
        "approved_source_urls": [],
        "verified_source_score": None,
        "canonical_eligibility": False,
        "quality_report": "data/research/alpha/research_quality.json",
        "blockers": ["No approved source URL exists on the external-writer task."],
    }
    assert _tree(tmp_path) == before


def test_preflight_filters_gates_and_rewrites_explicit_zero_score(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_resolution(
        monkeypatch,
        source_quality_score=0,
        draft_exportable=False,
        failing_gates=(
            "VERIFIED_SOURCE_SCORE 0 < 40",
            "OFFICIAL_DOCS_SCORE 0 < 20",
            "PRICING_SOURCE_SCORE 0 < 10",
            "AFFILIATE_SOURCE_SCORE 0 < 10",
            "NO_VERIFIED_SOURCE_FAMILY",
            "IGNORED_GATE",
        ),
    )

    result = _website_source_preflight(
        tmp_path,
        _task(primary_source_url="https://approved.example/docs"),
    )

    assert result["ready"] is False
    assert result["blockers"] == [
        "Research quality reports zero usable verified sources (VERIFIED_SOURCE_SCORE 0 < 40).",
        "OFFICIAL_DOCS_SCORE 0 < 20",
        "PRICING_SOURCE_SCORE 0 < 10",
        "AFFILIATE_SOURCE_SCORE 0 < 10",
        "NO_VERIFIED_SOURCE_FAMILY",
    ]


def test_preflight_preserves_current_exception_for_non_iterable_supporting_sources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_resolution(monkeypatch)

    with pytest.raises(TypeError, match="not iterable"):
        _website_source_preflight(tmp_path, _task(supporting_source_urls=42))


class _NoNetworkSession:
    def __init__(self) -> None:
        self.calls = 0

    def get(self, *args, **kwargs):  # pragma: no cover - any invocation fails the contract
        self.calls += 1
        raise AssertionError("cache-only retrieval must not use the network")


@pytest.mark.parametrize(
    ("source", "refresh", "reuse_cache"),
    (
        ({"source_url": "https://missing.example"}, False, True),
        ({"canonical_url": "https://missing.example"}, True, True),
        ({"url": "https://missing.example"}, False, False),
        ({}, True, False),
    ),
)
def test_cache_only_miss_never_calls_network_or_writes(
    tmp_path: Path,
    source: dict[str, str],
    refresh: bool,
    reuse_cache: bool,
) -> None:
    session = _NoNetworkSession()
    retriever = _CachedOnlySourceRetriever(cache_dir=tmp_path, session=session)

    result = retriever.retrieve(source, refresh=refresh, reuse_cache=reuse_cache)

    assert result["retrieval_status"] == "blocked"
    assert result["error_code"] == "local_cache_miss"
    assert result["error"] == "No verified local source-content cache exists; operator source review is required."
    assert session.calls == 0
    assert _tree(tmp_path) == {}


def test_cache_only_hit_returns_exact_overlay_without_mutating_cache(tmp_path: Path) -> None:
    url = "https://cached.example/docs"
    cache_path = tmp_path / f"{SourceRetriever.cache_key(url)}.json"
    cached = {"url": url, "content": "verified local content", "custom": {"keep": True}}
    _write_json(cache_path, cached)
    before = cache_path.read_bytes()
    session = _NoNetworkSession()
    retriever = _CachedOnlySourceRetriever(cache_dir=tmp_path, session=session)

    result = retriever.retrieve({"source_url": f" {url} "}, refresh=True, reuse_cache=False)

    assert result == {
        **cached,
        "retrieval_status": "cache_hit",
        "cache_path": str(cache_path),
    }
    assert cache_path.read_bytes() == before
    assert session.calls == 0


@pytest.mark.parametrize(
    "payload",
    (
        "{malformed",
        json.dumps({"url": "https://other.example", "content": "content"}),
        json.dumps({"url": "https://cached.example/docs", "content": ""}),
    ),
)
def test_cache_only_malformed_mismatched_or_empty_cache_is_a_local_miss(
    tmp_path: Path, payload: str
) -> None:
    url = "https://cached.example/docs"
    cache_path = tmp_path / f"{SourceRetriever.cache_key(url)}.json"
    cache_path.write_text(payload, encoding="utf-8")
    before = cache_path.read_bytes()

    result = _CachedOnlySourceRetriever(cache_dir=tmp_path).retrieve({"source_url": url})

    assert result["error_code"] == "local_cache_miss"
    assert cache_path.read_bytes() == before


def test_cache_only_unsupported_list_cache_preserves_current_attribute_error(tmp_path: Path) -> None:
    url = "https://cached.example/docs"
    cache_path = tmp_path / f"{SourceRetriever.cache_key(url)}.json"
    cache_path.write_text(json.dumps(["unsupported"]), encoding="utf-8")
    before = cache_path.read_bytes()

    with pytest.raises(AttributeError, match="has no attribute 'get'"):
        _CachedOnlySourceRetriever(cache_dir=tmp_path).retrieve({"source_url": url})

    assert cache_path.read_bytes() == before
