from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import subprocess
from typing import Any
import urllib.request

import pytest

from modules.social import draft_selection as canonical
from modules.social import draft_workflow as legacy


def workflow(tmp_path: Path) -> legacy.SocialDraftWorkflow:
    value = legacy.SocialDraftWorkflow.__new__(legacy.SocialDraftWorkflow)
    value.root = tmp_path
    value.data_dir = tmp_path / "data"
    value.draft_root = value.data_dir / "social_drafts"
    return value


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def file_snapshot(root: Path) -> dict[str, bytes]:
    if not root.exists():
        return {}
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


def test_live_report_merge_order_duplicate_preference_and_input_immutability(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    value = workflow(tmp_path)
    report = {
        "date": "2026-09-20",
        "items": [
            {"slug": "alpha", "url": "https://example.test/alpha/", "status": "draft", "marker": "report"},
            {"slug": "beta", "url": "https://example.test/beta/", "http_status": 200, "title": "Beta"},
            "ignored",
        ],
    }
    receipts = {
        "batch_date": "2026-09-20",
        "items": [
            {"slug": "alpha", "url": "https://example.test/alpha/", "live_http_status": "200", "marker": "receipt"},
            {"slug": "gamma", "url": "https://example.test/gamma/", "live_status": "live"},
            42,
        ],
    }
    before = deepcopy((report, receipts))

    def fake_read(path: Path, default: Any) -> Any:
        return report if path.name == "live_status_report.json" else receipts

    monkeypatch.setattr(legacy, "read_json", fake_read)
    resolved, rows = value._live_report_items()

    assert resolved == "2026-09-20"
    assert [row["slug"] for row in rows] == ["alpha", "beta", "gamma"]
    assert rows[0] == {
        "slug": "alpha",
        "url": "https://example.test/alpha/",
        "live_http_status": "200",
        "marker": "receipt",
        "batch_date": "2026-09-20",
        "title": "Alpha",
    }
    assert "marker" not in rows[1]
    assert rows[2]["title"] == "Gamma"
    assert (report, receipts) == before


def test_blocked_report_is_not_live_inventory_and_receipt_supplies_latest(tmp_path: Path) -> None:
    value = workflow(tmp_path)
    write_json(
        value.data_dir / "live_status_report.json",
        {
            "date": "2026-09-22",
            "blocked_only": True,
            "items": [{"slug": "blocked", "url": "https://example.test/blocked/", "http_status": 200}],
        },
    )
    write_json(
        value.data_dir / "published_live_urls_latest.json",
        {
            "batch_date": "2026-09-21",
            "items": [{"slug": "receipt", "url": "https://example.test/receipt/", "live_http_status": 200}],
        },
    )

    resolved, rows = value._live_report_items()
    assert resolved == "2026-09-21"
    assert [row["slug"] for row in rows] == ["receipt"]
    assert value.resolve_latest_live_batch() == "2026-09-21"


def test_explicit_batch_resolution_bypasses_inventory_reads(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    value = workflow(tmp_path)
    monkeypatch.setattr(
        value,
        "_live_report_items",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("inventory read")),
    )
    monkeypatch.setattr(
        value,
        "_social_batch_dates",
        lambda: (_ for _ in ()).throw(AssertionError("directory read")),
    )
    assert value.resolve_latest_live_batch("2026-09-18") == "2026-09-18"
    assert value.resolve_latest_social_batch("2026-09-19") == "2026-09-19"


def test_social_batch_directory_order_manifest_preference_and_live_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    value = workflow(tmp_path)
    for name in ("not-a-date", "2026-09-01", "2026-09-03", "2026-09-02", "2026-99-99"):
        (value.draft_root / name).mkdir(parents=True, exist_ok=True)
    write_json(value.draft_root / "2026-09-01" / "manifest.json", {})
    write_json(value.draft_root / "2026-09-03" / "manifest.json", {})

    assert value._social_batch_dates() == ["2026-09-01", "2026-09-02", "2026-09-03", "2026-99-99"]
    assert value.resolve_latest_social_batch() == "2026-09-03"

    (value.draft_root / "2026-09-01" / "manifest.json").unlink()
    (value.draft_root / "2026-09-03" / "manifest.json").unlink()
    monkeypatch.setattr(value, "resolve_latest_live_batch", lambda requested="latest": "live-fallback")
    assert value.resolve_latest_social_batch() == "live-fallback"


@pytest.mark.parametrize(
    ("row", "expected"),
    [
        ({"live_http_status": 200}, True),
        ({"http_status": "200"}, True),
        ({"live_status": "LIVE 200 OK"}, True),
        ({"display_status": "live"}, True),
        ({"status": "Live"}, True),
        ({"http_status": 404, "status": "failed"}, False),
        ({"status": "published"}, False),
        ({}, False),
    ],
)
def test_live_status_normalization(row: dict[str, Any], expected: bool) -> None:
    value = workflow(Path("unused"))
    assert value._is_live_200(row) is expected


def test_live_status_invalid_input_preserves_attribute_error() -> None:
    value = workflow(Path("unused"))
    with pytest.raises(AttributeError, match="has no attribute 'get'"):
        value._is_live_200(None)  # type: ignore[arg-type]


def test_live_articles_filtering_order_shape_and_source_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    value = workflow(tmp_path)
    rows = [
        {"slug": "first", "title": "First", "url": "https://example.test/first/", "http_status": 200},
        {"title": "Derived", "url": "https://example.test/derived/", "status": "live"},
        {"slug": "http", "url": "http://example.test/http/", "status": "live"},
        {"slug": "not-live", "url": "https://example.test/not-live/", "status": "draft"},
        {"slug": "", "url": "", "status": "live"},
    ]
    before = deepcopy(rows)
    monkeypatch.setattr(value, "resolve_latest_live_batch", lambda requested="latest": "2026-09-20")
    monkeypatch.setattr(value, "_live_report_items", lambda requested=None: ("2026-09-20", rows))

    result = value.live_articles("latest")
    assert result == [
        {
            "slug": "first",
            "title": "First",
            "url": "https://example.test/first/",
            "batch_date": "2026-09-20",
            "source": "live_status_report",
        },
        {
            "slug": "derived",
            "title": "Derived",
            "url": "https://example.test/derived/",
            "batch_date": "2026-09-20",
            "source": "live_status_report",
        },
    ]
    assert rows == before

    monkeypatch.setattr(value, "_live_report_items", lambda requested=None: ("2026-09-19", rows))
    assert value.live_articles("2026-09-20") == []


def test_empty_missing_and_malformed_inventory_contracts(tmp_path: Path) -> None:
    value = workflow(tmp_path)
    assert value._live_report_items() == ("", [])
    assert value._social_batch_dates() == []
    assert value.resolve_latest_live_batch() == "latest"
    assert value.resolve_latest_social_batch() == "latest"
    assert value.live_articles() == []

    write_json(value.data_dir / "live_status_report.json", [])
    with pytest.raises(AttributeError, match="has no attribute 'get'"):
        value._live_report_items()

    (value.data_dir / "live_status_report.json").write_text("{broken", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        value._live_report_items()


def test_six_methods_are_read_only_and_do_not_use_external_effects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    value = workflow(tmp_path)
    write_json(
        value.data_dir / "live_status_report.json",
        {
            "date": "2026-09-20",
            "items": [{"slug": "one", "title": "One", "url": "https://example.test/one/", "http_status": 200}],
        },
    )
    write_json(value.data_dir / "published_live_urls_latest.json", {"batch_date": "2026-09-20", "items": []})
    write_json(value.draft_root / "2026-09-20" / "manifest.json", {})
    before = file_snapshot(tmp_path)

    monkeypatch.setattr(Path, "write_text", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("write_text")))
    monkeypatch.setattr(Path, "write_bytes", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("write_bytes")))
    monkeypatch.setattr(Path, "mkdir", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("mkdir")))
    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("network")),
    )
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("subprocess")),
    )

    assert value._live_report_items()[0] == "2026-09-20"
    assert value._social_batch_dates() == ["2026-09-20"]
    assert value.resolve_latest_live_batch() == "2026-09-20"
    assert value.resolve_latest_social_batch() == "2026-09-20"
    assert value._is_live_200({"http_status": 200}) is True
    assert len(value.live_articles()) == 1
    assert file_snapshot(tmp_path) == before


def test_legacy_six_method_surface_and_internal_monkeypatch_seams(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    value = workflow(tmp_path)
    names = (
        "_live_report_items",
        "_social_batch_dates",
        "resolve_latest_live_batch",
        "resolve_latest_social_batch",
        "_is_live_200",
        "live_articles",
    )
    assert all(callable(getattr(legacy.SocialDraftWorkflow, name)) for name in names)
    assert all(callable(getattr(canonical.SocialDraftSelectionService, name)) for name in names)

    monkeypatch.setattr(value, "_social_batch_dates", lambda: [])
    monkeypatch.setattr(value, "resolve_latest_live_batch", lambda requested="latest": "patched-live")
    assert value.resolve_latest_social_batch() == "patched-live"

    observed: list[str] = []
    monkeypatch.setattr(value, "resolve_latest_live_batch", lambda requested="latest": "resolved")
    monkeypatch.setattr(value, "_live_report_items", lambda requested=None: ("resolved", [{"slug": "one", "url": "https://x/one/"}]))
    monkeypatch.setattr(value, "_is_live_200", lambda row: observed.append(str(row["slug"])) or True)
    assert value.live_articles() == [
        {
            "slug": "one",
            "title": "One",
            "url": "https://x/one/",
            "batch_date": "resolved",
            "source": "live_status_report",
        }
    ]
    assert observed == ["one"]
