from __future__ import annotations

import hashlib

import pytest

from modules.social import draft_workflow as legacy
from modules.social.utils import PublishedArticle


def _article() -> PublishedArticle:
    return PublishedArticle(
        article_id="one",
        title="One Article",
        url="https://example.test/one/",
        description="Useful summary",
        image="",
        tags=["one"],
        publish_date="2026-09-01",
        canonical_url="https://example.test/one/",
        summary="Useful summary",
    )


def test_article_from_live_row_without_html_uses_row_and_empty_fields(tmp_path):
    workflow = legacy.SocialDraftWorkflow(root=tmp_path)
    article = workflow.article_from_live_row(
        {"slug": "one", "title": "One Article", "url": "https://example.test/one/"}
    )
    assert article.article_id == "one"
    assert article.title == "One Article"
    assert article.url == article.canonical_url == "https://example.test/one/"
    assert article.image == ""
    assert article.headings == []


def test_article_from_live_row_extracts_html_and_normalizes_root_image(tmp_path):
    page = tmp_path / "docs" / "one" / "index.html"
    page.parent.mkdir(parents=True)
    page.write_text(
        '<html><head><title>Fallback</title><meta property="og:title" content="One Better Title">'
        '<meta name="description" content="A &amp; B">'
        '<meta property="og:image" content="/assets/one.png">'
        '<link rel="canonical" href="https://example.test/canonical/"></head>'
        '<body><h2>Useful Heading</h2><p>Useful paragraph.</p></body></html>',
        encoding="utf-8",
    )
    article = legacy.SocialDraftWorkflow(root=tmp_path).article_from_live_row(
        {"slug": "one", "title": "Old", "url": "https://example.test/one/"}
    )
    assert article.title == "One Better Title"
    assert article.description == "A & B"
    assert article.image == "https://smileaireviewhub.com/assets/one.png"
    assert article.canonical_url == "https://example.test/canonical/"
    assert "Useful Heading" in article.headings


def test_article_from_live_row_missing_required_slug_raises(tmp_path):
    with pytest.raises(KeyError, match="slug"):
        legacy.SocialDraftWorkflow(root=tmp_path).article_from_live_row({"url": "https://example.test/"})


def test_source_package_missing_html_preserves_blocked_defaults_and_inputs(tmp_path):
    workflow = legacy.SocialDraftWorkflow(root=tmp_path)
    article = _article()
    platforms = ["facebook", "linkedin"]
    package = workflow.source_package(article, batch_date="2026-09-01", platforms=platforms)
    assert package["status"] == "writing_package_ready"
    assert package["article"]["slug"] == "one"
    assert package["platforms"] is platforms
    assert list(package["required_outputs"]) == platforms
    assert package["social_series"] == {}
    assert package["provenance"] == {}
    assert package["evidence"]["status"] == "BLOCKED_RESEARCH"
    assert package["evidence"]["source_excerpts"] == []
    assert package["evidence"]["fact_ledger"] == []
    assert not (tmp_path / "data" / "social_drafts").exists()


def test_source_package_site_output_fallback_projects_evidence(tmp_path, monkeypatch):
    page = tmp_path / "site_output" / "one" / "index.html"
    page.parent.mkdir(parents=True)
    page.write_text("<html><p>Evidence.</p></html>", encoding="utf-8")

    class FakeResearch:
        def __init__(self, **kwargs):
            assert kwargs["root"] == tmp_path

        def extract_paragraphs(self, raw_html, **kwargs):
            assert raw_html == "<html><p>Evidence.</p></html>"
            return ([{"text": "Evidence."}], {})

        def extract_claims(self, sources, **kwargs):
            assert sources[0]["paragraphs"][0]["paragraph_id"] == "live-article-001-p001"
            return [{"claim": "Evidence."}]

    monkeypatch.setattr(legacy, "ResearchEnrichmentPipeline", FakeResearch)
    monkeypatch.setattr(legacy, "now_iso", lambda: "2026-09-01T00:00:00+00:00")
    package = legacy.SocialDraftWorkflow(root=tmp_path).source_package(
        _article(), batch_date="2026-09-01", platforms=["facebook"],
        social_series={"root_slugs": ["one"]}, provenance={"source": "test"},
    )
    evidence = package["evidence"]
    assert evidence["status"] == "EVIDENCE_VALIDATED"
    assert evidence["warnings"] == []
    assert evidence["fact_ledger"] == [{"claim": "Evidence."}]
    assert evidence["source_excerpts"][0]["retrieved_at"] == "2026-09-01T00:00:00+00:00"
    assert evidence["source_excerpts"][0]["content_hash"] == hashlib.sha256(page.read_bytes()).hexdigest()
    assert package["social_series"] == {"root_slugs": ["one"]}
    assert package["provenance"] == {"source": "test"}


def test_writing_prompt_preserves_platform_order_and_optional_series(tmp_path):
    workflow = legacy.SocialDraftWorkflow(root=tmp_path)
    package = {
        "article": {"title": "One", "url": "https://example.test/one/", "canonical_url": "https://example.test/one/", "image": "", "summary": "Summary"},
        "platforms": ["linkedin", "facebook"],
        "batch_date": "2026-09-01",
    }
    plain = workflow.writing_prompt(package)
    assert plain.index("- linkedin: create") < plain.index("- facebook: create")
    assert "Weekly social series:" not in plain
    package["social_series"] = {"social_week_start": "2026-08-31", "root_slugs": ["one", "two"]}
    series = workflow.writing_prompt(package)
    assert "Weekly social series:" in series
    assert "one, two" in series
    assert "Current batch date: 2026-09-01" in series
    assert "Do not publish, approve, deploy, index, or push." in series


def test_writing_prompt_missing_article_raises(tmp_path):
    with pytest.raises(KeyError, match="article"):
        legacy.SocialDraftWorkflow(root=tmp_path).writing_prompt({})
