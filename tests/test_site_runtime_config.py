from __future__ import annotations

import json
from dataclasses import FrozenInstanceError
from pathlib import Path
from types import SimpleNamespace

import pytest

from modules.platform.config_drift import (
    READ_ONLY_ADAPTER_INTEGRATED,
    integration_statuses,
)
from modules.platform.site_runtime_config import (
    FALLBACK_TO_LEGACY,
    INCOMPATIBLE,
    LEGACY_ONLY,
    MATCH,
    PROFILE_ONLY_NOT_ACTIVE,
    SiteRuntimeConfigError,
    build_site_runtime_config,
)
from modules.site_builder import page_shell
from scripts.show_site_runtime_config import main


def profile_payload(**overrides: object) -> dict:
    payload = {
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
        "affiliate_disclosure": (
            "Some links may be affiliate links. We may earn a commission at no extra cost to you."
        ),
        "editorial_settings": {"human_approval_required": True},
        "seo_defaults": {"canonical_base_url": "https://smileaireviewhub.com"},
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
    payload.update(overrides)
    return payload


def make_root(tmp_path: Path, payload: dict | None = None) -> Path:
    root = tmp_path / "repo"
    profile_dir = root / "config" / "sites"
    profile_dir.mkdir(parents=True)
    (profile_dir / "smile_ai_review_hub.json").write_text(
        json.dumps(payload or profile_payload()),
        encoding="utf-8",
    )
    return root


def fake_settings(root: Path, **overrides: object) -> SimpleNamespace:
    values = {
        "site_name": "MS Smile AI Review Hub",
        "base_site_url": "https://smileaireviewhub.com",
        "site_domain": "https://smileaireviewhub.com",
        "site_output_dir": root / "site_output",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_runtime_config_is_deeply_immutable(tmp_path: Path) -> None:
    root = make_root(tmp_path)
    runtime = build_site_runtime_config(root=root, settings_source=fake_settings(root))

    with pytest.raises(FrozenInstanceError):
        runtime.site_name = "Changed"  # type: ignore[misc]
    with pytest.raises(TypeError):
        runtime.field_statuses["site_name"] = MATCH  # type: ignore[index]
    assert isinstance(runtime.supported_languages, tuple)


def test_matching_profile_preserves_legacy_values_and_paths(tmp_path: Path) -> None:
    root = make_root(tmp_path)
    runtime = build_site_runtime_config(root=root, settings_source=fake_settings(root))

    assert runtime.compatibility_status == MATCH
    assert set(runtime.field_statuses.values()) == {MATCH}
    assert runtime.site_name == "MS Smile AI Review Hub"
    assert runtime.docs_output_path == root / "docs"
    assert runtime.site_output_path == root / "site_output"
    assert runtime.asset_path == root / "site_output" / "assets"


def test_legacy_settings_have_precedence_on_profile_mismatch(tmp_path: Path) -> None:
    payload = profile_payload(site_name="Different Profile Name")
    root = make_root(tmp_path, payload)
    runtime = build_site_runtime_config(root=root, settings_source=fake_settings(root))

    assert runtime.compatibility_status == FALLBACK_TO_LEGACY
    assert runtime.field_statuses["site_name"] == INCOMPATIBLE
    assert runtime.site_name == "MS Smile AI Review Hub"


def test_strict_mode_fails_closed_on_mismatch(tmp_path: Path) -> None:
    root = make_root(tmp_path, profile_payload(site_name="Different Profile Name"))

    with pytest.raises(SiteRuntimeConfigError, match="do not match"):
        build_site_runtime_config(
            root=root,
            settings_source=fake_settings(root),
            strict_profile_match=True,
        )


@pytest.mark.parametrize(
    "overrides",
    [
        {
            "domain": "https://different.example.org",
            "seo_defaults": {"canonical_base_url": "https://different.example.org"},
        },
        {"brand_name": "Different Brand"},
    ],
)
def test_strict_mode_rejects_domain_and_brand_mismatch(
    tmp_path: Path,
    overrides: dict,
) -> None:
    root = make_root(tmp_path, profile_payload(**overrides))

    with pytest.raises(SiteRuntimeConfigError, match="do not match"):
        build_site_runtime_config(
            root=root,
            settings_source=fake_settings(root),
            strict_profile_match=True,
        )


@pytest.mark.parametrize(
    "overrides",
    [
        {"active": False},
        {"production_enabled": False},
        {"example": True, "active": False, "production_enabled": False},
    ],
)
def test_inactive_or_example_profile_is_not_activated(
    tmp_path: Path,
    overrides: dict,
) -> None:
    root = make_root(tmp_path, profile_payload(**overrides))
    runtime = build_site_runtime_config(root=root, settings_source=fake_settings(root))

    assert runtime.compatibility_status == PROFILE_ONLY_NOT_ACTIVE
    assert not runtime.profile_active
    with pytest.raises(SiteRuntimeConfigError, match="not active"):
        build_site_runtime_config(
            root=root,
            settings_source=fake_settings(root),
            strict_profile_match=True,
        )


@pytest.mark.parametrize("site_id", ["example_health", "example_sports"])
def test_repository_example_profiles_are_never_activated(site_id: str) -> None:
    root = Path(__file__).resolve().parents[1]
    runtime = build_site_runtime_config(
        site_id,
        root=root,
        settings_source=fake_settings(root),
    )

    assert runtime.compatibility_status == PROFILE_ONLY_NOT_ACTIVE
    assert not runtime.profile_active
    with pytest.raises(SiteRuntimeConfigError, match="not active"):
        build_site_runtime_config(
            site_id,
            root=root,
            settings_source=fake_settings(root),
            strict_profile_match=True,
        )


def test_profile_missing_required_field_falls_back_or_fails_strict(
    tmp_path: Path,
) -> None:
    payload = profile_payload()
    del payload["brand_name"]
    root = make_root(tmp_path, payload)

    runtime = build_site_runtime_config(root=root, settings_source=fake_settings(root))

    assert runtime.compatibility_status == FALLBACK_TO_LEGACY
    assert runtime.field_statuses["brand_name"] == LEGACY_ONLY
    assert "missing required fields" in runtime.profile_error
    with pytest.raises(SiteRuntimeConfigError, match="missing required fields"):
        build_site_runtime_config(
            root=root,
            settings_source=fake_settings(root),
            strict_profile_match=True,
        )


def test_missing_profile_falls_back_without_selecting_another_site(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    runtime = build_site_runtime_config(
        "missing_site",
        root=root,
        settings_source=fake_settings(root),
    )

    assert runtime.site_id == "missing_site"
    assert runtime.compatibility_status == FALLBACK_TO_LEGACY
    assert "was not found" in runtime.profile_error


def test_missing_profile_strict_mode_fails_closed(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    with pytest.raises(SiteRuntimeConfigError, match="was not found"):
        build_site_runtime_config(
            "missing_site",
            root=root,
            settings_source=fake_settings(root),
            strict_profile_match=True,
        )


def test_environment_style_override_remains_authoritative(tmp_path: Path) -> None:
    root = make_root(tmp_path)
    runtime = build_site_runtime_config(
        root=root,
        settings_source=fake_settings(root, site_name="Local Operator Override"),
    )

    assert runtime.site_name == "Local Operator Override"
    assert runtime.compatibility_status == FALLBACK_TO_LEGACY


def test_adapter_does_not_read_secrets_or_make_network_calls(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = make_root(tmp_path)

    class GuardedSettings:
        site_name = "MS Smile AI Review Hub"
        base_site_url = "https://smileaireviewhub.com"
        site_domain = "https://smileaireviewhub.com"
        site_output_dir = root / "site_output"

        @property
        def api_key(self) -> str:
            raise AssertionError("secret property must not be read")

    def fail_network(*args: object, **kwargs: object) -> None:
        raise AssertionError("network access is forbidden")

    monkeypatch.setattr("socket.create_connection", fail_network)
    runtime = build_site_runtime_config(root=root, settings_source=GuardedSettings())
    assert runtime.compatibility_status == MATCH
    assert "api_key" not in json.dumps(runtime.as_dict())


def test_adapter_does_not_mutate_profile_or_create_files(tmp_path: Path) -> None:
    root = make_root(tmp_path)
    profile = root / "config" / "sites" / "smile_ai_review_hub.json"
    before_bytes = profile.read_bytes()
    before_paths = sorted(path.relative_to(root) for path in root.rglob("*"))

    first = build_site_runtime_config(root=root, settings_source=fake_settings(root))
    second = build_site_runtime_config(root=root, settings_source=fake_settings(root))

    assert first.as_dict() == second.as_dict()
    assert profile.read_bytes() == before_bytes
    assert sorted(path.relative_to(root) for path in root.rglob("*")) == before_paths


def test_windows_paths_remain_path_objects_and_are_not_reformatted(tmp_path: Path) -> None:
    root = make_root(tmp_path)
    windows_style = root / "site output"
    payload = profile_payload()
    payload["output"]["site_output_dir"] = "site output"
    (root / "config" / "sites" / "smile_ai_review_hub.json").write_text(
        json.dumps(payload),
        encoding="utf-8",
    )
    runtime = build_site_runtime_config(
        root=root,
        settings_source=fake_settings(root, site_output_dir=windows_style),
    )

    assert runtime.site_output_path == windows_style
    assert runtime.asset_path == windows_style / "assets"
    assert runtime.compatibility_status == MATCH


def test_read_only_cli_writes_nothing_and_supports_utf8(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    payload = profile_payload(site_name="MS Smile AI Review Hub")
    root = make_root(tmp_path, payload)
    before = sorted(path.relative_to(root) for path in root.rglob("*"))

    assert main(["--root", str(root)]) == 0

    output = capsys.readouterr().out
    assert "Smile AI Review Hub" in output
    assert '"renderer_integration_status": "READ_ONLY_ADAPTER_INTEGRATED"' in output
    assert '"secret_handling": "NOT_READ"' in output
    assert "compatibility validation only" in output
    assert sorted(path.relative_to(root) for path in root.rglob("*")) == before


def test_page_shell_adapter_is_exactly_byte_equivalent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import modules.site_builder as site_builder

    legacy_name = site_builder.settings.site_name
    original_factory = site_builder.build_site_runtime_config
    monkeypatch.setattr(
        site_builder,
        "build_site_runtime_config",
        lambda **kwargs: SimpleNamespace(site_name=legacy_name),
    )
    legacy_html = page_shell(
        "Kiểm tra tương thích",
        "Mô tả UTF-8 tiếng Việt.",
        "<h1>Kiểm tra</h1><p>Nội dung không đổi.</p>",
        "/compatibility-preview/",
    )
    monkeypatch.setattr(site_builder, "build_site_runtime_config", original_factory)
    adapter_html = page_shell(
        "Kiểm tra tương thích",
        "Mô tả UTF-8 tiếng Việt.",
        "<h1>Kiểm tra</h1><p>Nội dung không đổi.</p>",
        "/compatibility-preview/",
    )

    assert legacy_html.encode("utf-8") == adapter_html.encode("utf-8")
    assert "Kiểm tra tương thích" in adapter_html
    assert "Nội dung không đổi." in adapter_html
    assert not adapter_html.startswith("\ufeff")
    assert "\r\n" not in adapter_html


def test_page_shell_mismatched_profile_still_renders_legacy_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import modules.site_builder as site_builder

    monkeypatch.setattr(
        site_builder,
        "build_site_runtime_config",
        lambda **kwargs: SimpleNamespace(site_name=site_builder.settings.site_name),
    )
    rendered = page_shell("Preview", "Description", "<h1>Preview</h1>", "/preview/")
    assert f"Preview - {site_builder.settings.site_name}" in rendered


def test_drift_marks_only_renderer_adapter_as_integrated() -> None:
    statuses = {item.component: item.status for item in integration_statuses()}

    assert statuses["renderer"] == READ_ONLY_ADAPTER_INTEGRATED
    for component in ("canonical", "sitemap", "social", "affiliate_resolver", "publish", "deployment", "indexing"):
        assert statuses[component] != READ_ONLY_ADAPTER_INTEGRATED
