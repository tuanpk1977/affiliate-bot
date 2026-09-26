from __future__ import annotations

import json
from pathlib import Path

import pytest

from config import settings
from modules.daily_editorial_workflow import DailyEditorialWorkflow


def _workflow(root: Path) -> DailyEditorialWorkflow:
    return DailyEditorialWorkflow(root=root, data_dir=root / "data", site_output_dir=root / "site_output")


def _draft_paths(root: Path, slug: str) -> tuple[Path, Path]:
    base = root / "data" / "production_article_drafts" / slug
    return base / "index.html", base / "metadata.json"


def _write(path: Path, value: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")
    return path


def test_required_image_paths_contract(tmp_path: Path) -> None:
    workflow = _workflow(tmp_path)
    assert workflow._required_image_src("alpha") == "/assets/og/pages/alpha.svg"
    assert workflow._required_image_asset_paths("alpha") == [
        tmp_path / "assets" / "og" / "pages" / "alpha.svg",
        tmp_path / "site_output" / "assets" / "og" / "pages" / "alpha.svg",
        tmp_path / "docs" / "assets" / "og" / "pages" / "alpha.svg",
    ]


def test_cover_svg_contract_escapes_title_and_slug(tmp_path: Path) -> None:
    rendered = _workflow(tmp_path)._render_local_cover_svg(
        title="A < B & " + ("x" * 140),
        slug="alpha&beta",
    )
    assert rendered.startswith('<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="630"')
    assert "A &lt; B &amp;" in rendered
    assert "alpha&amp;beta" in rendered
    assert "Source-backed AI software review" in rendered
    assert ("x" * 121) not in rendered


def test_html_image_detection_preserves_existing_path_rules(tmp_path: Path) -> None:
    workflow = _workflow(tmp_path)
    existing = tmp_path / "site_output" / "assets" / "hero.svg"
    _write(existing, "svg")

    assert workflow._html_has_local_image('<img src="https://example.com/hero.png">') is True
    assert workflow._html_has_local_image('<img src="data:image/png;base64,abc">') is True
    assert workflow._html_has_local_image('<img src="relative/hero.png">') is True
    assert workflow._html_has_local_image('<img src="/assets/hero.svg">') is True
    assert workflow._html_has_local_image('<img src="/assets/missing.svg">') is False
    assert workflow._html_has_local_image('<img src="">') is False
    assert workflow._html_has_local_image("<p>No image</p>") is False


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("<html><body><h1>Title</h1><p>Body</p></body></html>", "</h1>\n<img data-test>"),
        ("<html><body><p>Body</p></body></html>", "<body>\n<img data-test>"),
        ("<p>Body</p>", "<img data-test>\n<p>Body</p>"),
    ],
)
def test_image_html_injection_precedence(tmp_path: Path, source: str, expected: str) -> None:
    result = _workflow(tmp_path)._inject_required_image_html(source, image_html="<img data-test>")
    assert expected in result


def test_meta_upsert_replaces_first_or_inserts_before_head_close(tmp_path: Path) -> None:
    workflow = _workflow(tmp_path)
    source = (
        '<html><head><meta property="og:image" content="old">'
        '<meta name="twitter:image" content="old"></head><body></body></html>'
    )
    updated = workflow._upsert_meta_property(source, "og:image", "https://example.com/a&b.svg")
    updated = workflow._upsert_meta_name(updated, "twitter:image", "https://example.com/a&b.svg")
    assert '<meta property="og:image" content="https://example.com/a&amp;b.svg">' in updated
    assert '<meta name="twitter:image" content="https://example.com/a&amp;b.svg">' in updated
    inserted = workflow._upsert_meta_property("<html><head></head></html>", "og:image", "value")
    assert inserted == '<html><head>  <meta property="og:image" content="value">\n</head></html>'
    assert workflow._upsert_meta_name("<p>no head</p>", "twitter:image", "value") == "<p>no head</p>"


def test_ensure_image_missing_draft_raises_exact_file_error(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="Missing draft HTML for missing"):
        _workflow(tmp_path)._ensure_required_article_image(slug="missing", title="Missing")


def test_ensure_image_existing_image_is_noop(tmp_path: Path) -> None:
    draft, _ = _draft_paths(tmp_path, "existing")
    original = '<html><body><img src="relative.png"></body></html>'
    _write(draft, original)

    result = _workflow(tmp_path)._ensure_required_article_image(slug="existing", title="Existing")

    assert result == {"slug": "existing", "status": "already_has_image", "changed_files": []}
    assert draft.read_text(encoding="utf-8") == original
    assert not (tmp_path / "assets" / "og" / "pages" / "existing.svg").exists()


def test_ensure_image_dry_run_reports_changes_without_writing(tmp_path: Path) -> None:
    draft, metadata = _draft_paths(tmp_path, "preview")
    original = "<html><head></head><body><h1>Preview</h1></body></html>"
    _write(draft, original)

    result = _workflow(tmp_path)._ensure_required_article_image(
        slug="preview", title="Preview", dry_run=True
    )

    assert result["status"] == "would_generate"
    assert result["image_src"] == "/assets/og/pages/preview.svg"
    assert result["changed_files"] == [
        str(tmp_path / "assets" / "og" / "pages" / "preview.svg"),
        str(tmp_path / "site_output" / "assets" / "og" / "pages" / "preview.svg"),
        str(tmp_path / "docs" / "assets" / "og" / "pages" / "preview.svg"),
        str(draft),
        str(metadata),
    ]
    assert draft.read_text(encoding="utf-8") == original
    assert not metadata.exists()
    assert not (tmp_path / "assets" / "og" / "pages" / "preview.svg").exists()


def test_ensure_image_generates_assets_html_and_metadata_without_overwrite(tmp_path: Path) -> None:
    slug = "generated"
    title = "Generated & Safe"
    draft, metadata = _draft_paths(tmp_path, slug)
    _write(draft, "<html><head></head><body><h1>Generated</h1><p>Body</p></body></html>")
    _write(metadata, json.dumps({"slug": slug, "kept": True}))
    preserved_asset = tmp_path / "assets" / "og" / "pages" / f"{slug}.svg"
    _write(preserved_asset, "operator-owned")

    result = _workflow(tmp_path)._ensure_required_article_image(slug=slug, title=title)

    assert result["status"] == "generated"
    assert preserved_asset.read_text(encoding="utf-8") == "operator-owned"
    assert (tmp_path / "site_output" / "assets" / "og" / "pages" / f"{slug}.svg").is_file()
    assert (tmp_path / "docs" / "assets" / "og" / "pages" / f"{slug}.svg").is_file()
    html_text = draft.read_text(encoding="utf-8")
    assert '<img class="article-hero-image" src="/assets/og/pages/generated.svg"' in html_text
    assert 'alt="Generated &amp; Safe cover image"' in html_text
    absolute = f"{settings.base_site_url.rstrip('/')}/assets/og/pages/generated.svg"
    assert f'<meta property="og:image" content="{absolute}">' in html_text
    assert f'<meta name="twitter:image" content="{absolute}">' in html_text
    payload = json.loads(metadata.read_text(encoding="utf-8"))
    assert payload["kept"] is True
    assert payload["image"] == {
        "src": "/assets/og/pages/generated.svg",
        "alt": "Generated & Safe cover image",
        "width": 1200,
        "height": 630,
        "generated_by": "local_svg_cover_generator",
    }
    assert payload["og_image"] == absolute
    assert payload["twitter_image"] == absolute


def test_ensure_image_leaves_non_mapping_metadata_bytes_unchanged(tmp_path: Path) -> None:
    draft, metadata = _draft_paths(tmp_path, "list-metadata")
    _write(draft, "<html><head></head><body><h1>List</h1></body></html>")
    _write(metadata, "[]")

    _workflow(tmp_path)._ensure_required_article_image(slug="list-metadata", title="List")

    assert metadata.read_text(encoding="utf-8") == "[]"
