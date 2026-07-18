from __future__ import annotations

import copy
import json
from pathlib import Path

from modules.platform.config_drift import (
    DIFFERENT,
    HARDCODED,
    MATCH,
    PROFILE_MISSING,
    analyze_site_profile_drift,
    classify_hardcode,
    redact_value,
    scan_hardcodes,
)
from scripts.report_site_profile_drift import main


def profile_payload() -> dict:
    return {
        "schema_version": 1,
        "site_id": "smile_ai_review_hub",
        "site_name": "MS Smile AI Review Hub",
        "brand_name": "Smile AI Review Hub",
        "domain": "https://smileaireviewhub.com",
        "default_language": "en",
        "supported_languages": ["en", "vi"],
        "niche": "AI software, SaaS, automation, and productivity tools",
        "categories": ["AI Software"],
        "content_types": ["review"],
        "affiliate_disclosure": "Some links may be affiliate links.",
        "editorial_settings": {"human_approval_required": True},
        "seo_defaults": {
            "canonical_base_url": "https://smileaireviewhub.com",
            "robots_public": "index,follow",
        },
        "social_platform_settings": {"manual_publish_only": True},
        "source_policy": {"minimum_usable_sources": 2},
        "output": {
            "site_output_dir": "site_output",
            "production_output_dir": "docs",
            "published_static_pages_dir": "data/published_static_pages",
        },
        "active": True,
        "production_enabled": True,
        "example": False,
    }


def make_repository(tmp_path: Path, profile: dict | None = None) -> Path:
    root = tmp_path / "repo"
    (root / "config" / "sites").mkdir(parents=True)
    payload = profile or profile_payload()
    (root / "config" / "sites" / "smile_ai_review_hub.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )
    editorial = {
        "human_approval": {"required": True},
        "threshold_policy": {"initial_thresholds": {"minimum_usable_sources": 2}},
    }
    (root / "config" / "editorial_system.json").write_text(
        json.dumps(editorial), encoding="utf-8"
    )
    return root


def row(report, key: str):
    return next(item for item in report.field_comparison if item.key == key)


def test_exact_config_values_match_profile(tmp_path: Path) -> None:
    report = analyze_site_profile_drift(
        "smile_ai_review_hub", root=make_repository(tmp_path), environ={}, scan_paths=[]
    )
    assert row(report, "site_identity.site_name").status == MATCH
    assert row(report, "content.source.minimum_usable_sources").status == MATCH
    assert row(report, "paths.site_output").status == MATCH


def test_different_domain_is_reported(tmp_path: Path) -> None:
    payload = profile_payload()
    payload["domain"] = "https://different.example"
    payload["seo_defaults"]["canonical_base_url"] = "https://different.example"
    root = make_repository(tmp_path, payload)
    report = analyze_site_profile_drift(
        "smile_ai_review_hub",
        root=root,
        environ={},
        scan_paths=[],
    )
    domain = row(report, "site_identity.production_domain")
    assert domain.status == DIFFERENT
    assert domain.current == "https://smileaireviewhub.com"


def test_missing_profile_field_is_reported_without_crash(tmp_path: Path) -> None:
    payload = profile_payload()
    del payload["output"]["site_output_dir"]
    report = analyze_site_profile_drift(
        "smile_ai_review_hub",
        root=make_repository(tmp_path, payload),
        environ={},
        scan_paths=[],
    )
    assert not report.profile_valid
    assert row(report, "paths.site_output").status == PROFILE_MISSING


def test_hardcoded_production_domain_is_critical(tmp_path: Path) -> None:
    root = make_repository(tmp_path)
    path = root / "modules" / "canonical_routes.py"
    path.parent.mkdir()
    path.write_text('BASE_URL = "https://smileaireviewhub.com"\n', encoding="utf-8")
    findings = scan_hardcodes(root, ["modules/canonical_routes.py"])
    assert findings[0].classification == "production-critical hardcode"
    assert findings[0].severity == "critical"


def test_docs_only_and_test_fixture_are_not_critical() -> None:
    assert classify_hardcode(Path("architecture/README.md"), "production_domain")[0] == "documentation only"
    assert classify_hardcode(Path("tests/test_urls.py"), "production_domain")[0] == "test fixture"


def test_secret_values_are_always_redacted(tmp_path: Path) -> None:
    assert redact_value("api_key", "super-secret") == "PRESENT"
    root = make_repository(tmp_path)
    report = analyze_site_profile_drift(
        "smile_ai_review_hub",
        root=root,
        environ={"INDEXNOW_KEY": "never-print-this"},
        scan_paths=[],
    )
    encoded = json.dumps(report.as_dict())
    assert "never-print-this" not in encoded
    assert report.credential_presence["INDEXNOW_KEY"] == "OVERRIDE_PRESENT"


def test_cli_normal_and_strict_exit_codes(tmp_path: Path, capsys) -> None:
    root = make_repository(tmp_path)
    critical = root / "modules" / "canonical_routes.py"
    critical.parent.mkdir()
    critical.write_text('BASE_URL = "https://smileaireviewhub.com"\n', encoding="utf-8")
    # Default CLI scan includes the critical file.
    assert main(["--site", "smile_ai_review_hub"], root=root, environ={}) == 0
    assert main(["--site", "smile_ai_review_hub", "--strict"], root=root, environ={}) == 2
    assert "SITE PROFILE CONFIGURATION DRIFT" in capsys.readouterr().out


def test_cli_json_and_explicit_output_only(tmp_path: Path, capsys) -> None:
    root = make_repository(tmp_path)
    before = {path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()}
    assert main(["--site", "smile_ai_review_hub", "--json"], root=root, environ={}) == 0
    after = {path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()}
    assert before == after
    payload = json.loads(capsys.readouterr().out)
    assert payload["site_id"] == "smile_ai_review_hub"

    output = tmp_path / "reports" / "drift.json"
    assert (
        main(
            ["--site", "smile_ai_review_hub", "--json", "--output", str(output)],
            root=root,
            environ={},
        )
        == 0
    )
    assert json.loads(output.read_text(encoding="utf-8"))["summary"]["field_count"] > 0


def test_analysis_has_no_network_or_configuration_mutation(tmp_path: Path, monkeypatch) -> None:
    root = make_repository(tmp_path)
    profile_path = root / "config" / "sites" / "smile_ai_review_hub.json"
    editorial_path = root / "config" / "editorial_system.json"
    before = (profile_path.read_bytes(), editorial_path.read_bytes())

    def fail_network(*args, **kwargs):
        raise AssertionError("network access is forbidden")

    monkeypatch.setattr("socket.create_connection", fail_network)
    first = analyze_site_profile_drift(
        "smile_ai_review_hub", root=root, environ={}, scan_paths=[]
    )
    second = analyze_site_profile_drift(
        "smile_ai_review_hub", root=root, environ={}, scan_paths=[]
    )
    assert first.as_dict() == second.as_dict()
    assert before == (profile_path.read_bytes(), editorial_path.read_bytes())


def test_profile_input_is_not_mutated_by_fixture_helpers(tmp_path: Path) -> None:
    payload = profile_payload()
    original = copy.deepcopy(payload)
    make_repository(tmp_path, payload)
    assert payload == original
