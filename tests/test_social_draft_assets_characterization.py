from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any
import urllib.request

import pytest

from modules.social import draft_assets as canonical
from modules.social import draft_workflow as legacy
from modules.social.utils import PublishedArticle


FIXED_NOW = "2026-09-24T02:30:00+00:00"


def article(**overrides: Any) -> PublishedArticle:
    values: dict[str, Any] = {
        "article_id": "asset-case",
        "title": "Café AI Launch",
        "url": "https://example.com/review/",
        "description": "Detailed summary",
        "image": "hero.svg",
        "tags": ["ai"],
        "publish_date": "2026-09-24",
        "key_points": ["Point one", "Point two"],
    }
    values.update(overrides)
    return PublishedArticle(**values)


def workflow(tmp_path: Path) -> legacy.SocialDraftWorkflow:
    value = legacy.SocialDraftWorkflow.__new__(legacy.SocialDraftWorkflow)
    value.root = tmp_path
    value.data_dir = tmp_path / "data"
    value.draft_root = value.data_dir / "social_drafts"
    return value


class FakeSavedImage:
    def __init__(self, size: tuple[int, int], registry: dict[str, tuple[int, int]]) -> None:
        self.size = size
        self.registry = registry

    def save(self, path: Path, image_format: str) -> None:
        assert image_format == "PNG"
        payload = f"fake-png:{self.size[0]}x{self.size[1]}".encode("ascii")
        path.write_bytes(payload)
        self.registry[str(path)] = self.size

    def __enter__(self) -> "FakeSavedImage":
        return self

    def __exit__(self, *args: object) -> None:
        return None


class FakeImageAPI:
    sizes: dict[str, tuple[int, int]] = {}
    new_calls: list[tuple[str, tuple[int, int], str]] = []

    @classmethod
    def reset(cls) -> None:
        cls.sizes = {}
        cls.new_calls = []

    @classmethod
    def new(cls, mode: str, size: tuple[int, int], color: str) -> FakeSavedImage:
        cls.new_calls.append((mode, size, color))
        return FakeSavedImage(size, cls.sizes)

    @classmethod
    def open(cls, path: Path) -> FakeSavedImage:
        return FakeSavedImage(cls.sizes[str(path)], cls.sizes)


class FakeDrawer:
    def rounded_rectangle(self, *args: object, **kwargs: object) -> None:
        return None

    def text(self, *args: object, **kwargs: object) -> None:
        return None

    def ellipse(self, *args: object, **kwargs: object) -> None:
        return None

    def line(self, *args: object, **kwargs: object) -> None:
        return None


class FakeImageDrawAPI:
    @staticmethod
    def Draw(image: FakeSavedImage) -> FakeDrawer:  # noqa: N802 - Pillow compatibility
        return FakeDrawer()


class FakeImageFontAPI:
    fallback_calls = 0

    @classmethod
    def reset(cls) -> None:
        cls.fallback_calls = 0

    @staticmethod
    def truetype(*args: object, **kwargs: object) -> object:
        raise OSError("font unavailable")

    @classmethod
    def load_default(cls) -> object:
        cls.fallback_calls += 1
        return object()


def install_fake_pillow(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeImageAPI.reset()
    FakeImageFontAPI.reset()
    monkeypatch.setattr(legacy, "Image", FakeImageAPI)
    monkeypatch.setattr(legacy, "ImageDraw", FakeImageDrawAPI)
    monkeypatch.setattr(legacy, "ImageFont", FakeImageFontAPI)


def test_asset_constants_and_pure_helpers_are_stable(tmp_path: Path) -> None:
    assert legacy.SOCIAL_ASSET_FORMATS == {
        "master": (1200, 1200),
        "og": (1200, 630),
        "facebook": (1200, 630),
        "linkedin": (1200, 630),
        "x": (1200, 675),
        "pinterest": (1000, 1500),
        "threads": (1080, 1080),
        "bluesky": (1200, 675),
        "medium": (1200, 630),
        "hashnode": (1200, 630),
        "blogger": (1200, 630),
        "telegram": (1280, 720),
        "devto": (1200, 630),
        "quora": (1200, 630),
        "producthunt": (1200, 630),
    }
    assert legacy.PLATFORM_ASSET_NAME == {
        "twitter": "x",
        "facebook_en": "facebook",
        "facebook_vi": "facebook",
    }
    assert legacy._safe_asset_name("Twitter") == "x"
    assert legacy._safe_asset_name("facebook.vi") == "facebookvi"
    assert legacy._safe_asset_name("FACEBOOK_EN") == "facebook"
    assert legacy._safe_asset_name("") == "og"
    assert legacy._safe_asset_name("!!!") == "og"
    assert legacy._wrap_card_text("") == ["Smile AI Review Hub"]
    assert legacy._wrap_card_text("one two three four", max_chars=7, max_lines=2) == ["one two", "three..."]
    assert legacy._wrap_card_text("  alpha\n beta  ", max_chars=20, max_lines=2) == ["alpha beta"]

    missing = tmp_path / "missing.bin"
    assert legacy._sha256_file(missing) == ""
    empty = tmp_path / "empty.bin"
    empty.write_bytes(b"")
    assert legacy._sha256_file(empty) == hashlib.sha256(b"").hexdigest()
    large = tmp_path / "large.bin"
    payload = b"a" * 70000
    large.write_bytes(payload)
    assert legacy._sha256_file(large) == hashlib.sha256(payload).hexdigest()
    with pytest.raises(PermissionError):
        legacy._sha256_file(tmp_path)


def test_asset_fingerprint_exact_contract(tmp_path: Path) -> None:
    value = workflow(tmp_path)
    original = article()
    assert value._asset_fingerprint(original) == "d2d9576184c1037bbf38da5bc057f08b3234588ddd05abf92ee4cc0467d95018"
    assert value._asset_fingerprint(article(title="Different")) != value._asset_fingerprint(original)
    assert value._asset_fingerprint(article(key_points=[])) != value._asset_fingerprint(original)


def test_optional_pillow_absence_fails_before_writing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    value = workflow(tmp_path)
    monkeypatch.setattr(legacy, "Image", None)
    monkeypatch.setattr(legacy, "ImageDraw", None)
    monkeypatch.setattr(legacy, "ImageFont", None)
    target = tmp_path / "never" / "asset.png"
    with pytest.raises(RuntimeError, match="^Pillow is required for local social asset generation\\.$"):
        value._render_social_asset(target, title="Title", subtitle="Sub", size=(1200, 630))
    assert not target.parent.exists()
    with pytest.raises(RuntimeError, match="^Pillow is required for local social asset generation\\.$"):
        value.generate_social_assets(article(), batch_date="2026-09-24")
    assert not value.draft_root.exists()


def test_generation_metadata_filesystem_cache_and_no_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    value = workflow(tmp_path)
    install_fake_pillow(monkeypatch)
    monkeypatch.setattr(legacy, "now_iso", lambda: FIXED_NOW)
    monkeypatch.setattr(legacy, "official_source_name", lambda url: "Example Source")
    monkeypatch.setattr(
        legacy,
        "validate_pinterest_visual",
        lambda **kwargs: {"status": "PASS", "received": kwargs},
    )
    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("network call")),
    )

    result = value.generate_social_assets(article(), batch_date="2026-09-24")
    assets_dir = value.draft_root / "2026-09-24" / "asset-case" / "assets"
    assert result["schema_version"] == 1
    assert result["source_image"] == "hero.svg"
    assert result["generation_method"] == "local_pillow_branded_asset"
    assert result["warnings"] == [
        "source image is SVG; generated local PNG assets instead of relying on social preview"
    ]
    assert result["validation_status"] == "PASS"
    assert result["pinterest_visual_facts"] == ["Point one", "Point two"]
    assert result["created_at"] == FIXED_NOW
    assert result["updated_at"] == FIXED_NOW
    assert set(result["outputs"]) == set(legacy.SOCIAL_ASSET_FORMATS)
    assert result["master_dimensions"] == {"width": 1200, "height": 1200}
    assert len(FakeImageAPI.new_calls) == len(legacy.SOCIAL_ASSET_FORMATS)
    assert FakeImageFontAPI.fallback_calls == 3 * len(legacy.SOCIAL_ASSET_FORMATS)

    for name, size in legacy.SOCIAL_ASSET_FORMATS.items():
        output = result["outputs"][name]
        path = assets_dir / f"{name}.png"
        assert output["filename"] == f"{name}.png"
        assert (output["width"], output["height"]) == size
        assert output["mime_type"] == "image/png"
        assert output["file_size"] == path.stat().st_size
        assert output["local_path"] == str(path)
        assert output["checksum"] == hashlib.sha256(path.read_bytes()).hexdigest()
        assert output["validation_status"] == "PASS"
        assert output["public_url"] == ""
    assert result["outputs"]["pinterest"]["visual_validation"]["status"] == "PASS"

    expected_files = {assets_dir / "manifest.json"} | {
        assets_dir / f"{name}.png" for name in legacy.SOCIAL_ASSET_FORMATS
    }
    assert set(path for path in tmp_path.rglob("*") if path.is_file()) == expected_files

    calls = len(FakeImageAPI.new_calls)
    cached = value.generate_social_assets(article(), batch_date="2026-09-24")
    assert cached == result
    assert len(FakeImageAPI.new_calls) == calls

    (assets_dir / "og.png").unlink()
    regenerated = value.generate_social_assets(article(), batch_date="2026-09-24")
    assert regenerated["fingerprint"] == result["fingerprint"]
    assert len(FakeImageAPI.new_calls) == calls + len(legacy.SOCIAL_ASSET_FORMATS)

    value.generate_social_assets(article(), batch_date="2026-09-24", force=True)
    assert len(FakeImageAPI.new_calls) == calls + 2 * len(legacy.SOCIAL_ASSET_FORMATS)


def test_generation_uses_fallback_visual_points(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    value = workflow(tmp_path)
    install_fake_pillow(monkeypatch)
    monkeypatch.setattr(legacy, "now_iso", lambda: FIXED_NOW)
    monkeypatch.setattr(legacy, "official_source_name", lambda url: "Example Source")
    observed: dict[str, Any] = {}

    def validate(**kwargs: Any) -> dict[str, Any]:
        observed.update(kwargs)
        return {"status": "PASS"}

    monkeypatch.setattr(legacy, "validate_pinterest_visual", validate)
    result = value.generate_social_assets(article(image="", key_points=[]), batch_date="2026-09-24")
    expected = [
        "Official update from Example Source",
        "Check scope and applicability for your workflow",
        "Use the official source as the canonical reference",
    ]
    assert result["warnings"] == []
    assert result["pinterest_visual_facts"] == expected
    assert observed["points"] == expected
    assert observed["verified_facts"] == expected


def test_ensure_local_social_card_preserves_synthetic_article_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    value = workflow(tmp_path)
    captured: dict[str, Any] = {}

    def generate(generated: PublishedArticle, *, batch_date: str, force: bool = False) -> dict[str, Any]:
        captured.update({"article": generated, "batch_date": batch_date, "force": force})
        return {"outputs": {"og": {"local_path": "C:/assets/og.png"}}}

    monkeypatch.setattr(value, "generate_social_assets", generate)
    assert value._ensure_local_social_card(batch_date="2026-09-24", slug="my-post", title="My Post") == "C:/assets/og.png"
    generated = captured["article"]
    assert isinstance(generated, PublishedArticle)
    assert generated.article_id == "my-post"
    assert generated.title == "My Post"
    assert generated.url == "https://smileaireviewhub.com/my-post/"
    assert generated.description == ""
    assert generated.image == ""
    assert generated.tags == []
    assert generated.publish_date == ""
    assert captured == {"article": generated, "batch_date": "2026-09-24", "force": False}


def test_legacy_asset_symbols_are_importable() -> None:
    for name in (
        "SOCIAL_ASSET_FORMATS",
        "PLATFORM_ASSET_NAME",
        "Image",
        "ImageDraw",
        "ImageFont",
        "_wrap_card_text",
        "_sha256_file",
        "_safe_asset_name",
    ):
        assert hasattr(legacy, name)
    for name in (
        "_asset_fingerprint",
        "_render_social_asset",
        "generate_social_assets",
        "_ensure_local_social_card",
    ):
        assert callable(getattr(legacy.SocialDraftWorkflow, name))
    assert legacy.SOCIAL_ASSET_FORMATS is canonical.SOCIAL_ASSET_FORMATS
    assert legacy.PLATFORM_ASSET_NAME is canonical.PLATFORM_ASSET_NAME
    assert legacy._wrap_card_text is canonical._wrap_card_text
    assert legacy._sha256_file is canonical._sha256_file
    assert legacy._safe_asset_name is canonical._safe_asset_name
