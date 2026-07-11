from __future__ import annotations

import json
from pathlib import Path

import pytest

from modules.seo_engine.keyword_research import collect_candidates
from modules.seo_engine.seo_pipeline import SeoPipeline


def test_keyword_import_normalizes_and_deduplicates(tmp_path: Path) -> None:
    imported = tmp_path / "keywords.csv"
    imported.write_text("keyword,search_volume\nBest AI Tools,100\nbest   ai tools,100\n", encoding="utf-8")
    rows = collect_candidates(["BEST AI TOOLS"], [imported])
    assert len(rows) == 1
    assert rows[0]["keyword"] == "best ai tools"
    assert rows[0]["source_status"] == "verified"


def test_pipeline_is_offline_transparent_and_writes_dashboard(tmp_path: Path) -> None:
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "seo_engine.json").write_text(json.dumps({"seed_keywords": ["best ai calendar tools"]}), encoding="utf-8")
    pipeline = SeoPipeline(tmp_path)
    report = pipeline.run()
    assert report["mode"] == "offline_deterministic"
    assert Path(report["dashboard"]).exists()
    competitors = json.loads((tmp_path / "data" / "seo" / "competitor_analysis.json").read_text(encoding="utf-8"))
    assert competitors[0]["source_status"] == "unavailable"


def test_queue_is_dry_run_and_never_approves_or_publishes(tmp_path: Path) -> None:
    pipeline = SeoPipeline(tmp_path)
    pipeline._write("opportunities.json", [{"keyword": "best ai crm", "slug": "best-ai-crm", "decision": "create", "search_intent": "commercial", "suggested_content_type": "buyer_guide", "opportunity_score": 80}])
    result = pipeline.queue_opportunities(["best-ai-crm"], batch_date="2026-07-11")
    assert result["dry_run"] is True
    assert result["queued"][0]["status"] == "selected"
    assert result["approval_changed"] is False
    assert result["published"] is False
    assert not Path(result["queue_path"]).exists()


def test_queue_apply_excludes_existing_content(tmp_path: Path) -> None:
    page = tmp_path / "docs" / "best-ai-crm" / "index.html"
    page.parent.mkdir(parents=True)
    page.write_text("<html><title>Best AI CRM</title></html>", encoding="utf-8")
    pipeline = SeoPipeline(tmp_path)
    pipeline._write("opportunities.json", [{"keyword": "best ai crm", "slug": "best-ai-crm", "decision": "create", "search_intent": "commercial", "suggested_content_type": "buyer_guide", "opportunity_score": 80}])
    with pytest.raises(ValueError, match="cannot be queued"):
        pipeline.queue_opportunities(["best-ai-crm"], dry_run=False)
