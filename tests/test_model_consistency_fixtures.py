from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = ROOT / "tests" / "fixtures" / "model_consistency"
REQUIRED_FILES = {
    "CURRENT_TASK.md",
    "task.md",
    "research_package.json",
    "source_package.json",
    "expected_contract.json",
    "expected_output/article.html",
}


def test_fixture_contract_shape_and_isolated_paths() -> None:
    fixture_dirs = sorted(path for path in FIXTURE_ROOT.iterdir() if path.is_dir())
    assert {path.name for path in fixture_dirs} == {"comparison", "software_review", "top_list"}

    for fixture in fixture_dirs:
        for relative in REQUIRED_FILES:
            assert (fixture / relative).exists(), f"{fixture.name}/{relative}"
        contract = json.loads((fixture / "expected_contract.json").read_text(encoding="utf-8"))
        assert contract["minimum_total_score"] >= 95
        assert "data/production_article_drafts" not in json.dumps(contract)
        assert contract["expected_output_suffix"].endswith("/expected_output/article.html")


def test_fixture_sources_have_independent_domains() -> None:
    for fixture in sorted(path for path in FIXTURE_ROOT.iterdir() if path.is_dir()):
        package = json.loads((fixture / "research_package.json").read_text(encoding="utf-8"))
        domains = {source["domain"] for source in package["sources"]}
        assert len(domains) >= 2, fixture.name
        assert len(package["sources"]) >= 2, fixture.name


def test_fixture_tasks_forbid_production_mutation() -> None:
    for fixture in sorted(path for path in FIXTURE_ROOT.iterdir() if path.is_dir()):
        text = (fixture / "task.md").read_text(encoding="utf-8")
        assert "expected_output/article.html" in text
        assert "publish" not in text.lower() or "do not" in text.lower()
