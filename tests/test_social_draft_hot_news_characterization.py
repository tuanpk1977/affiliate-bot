"""Current hot-news monitoring behavior, before and after ownership transfer."""

import json

import pytest

from modules.social import draft_workflow as legacy


def test_package_preserves_urls_duplicates_platforms_and_metadata(tmp_path):
    workflow = legacy.SocialDraftWorkflow(root=tmp_path)
    package = workflow.hot_news_monitoring_package(
        title="AI News", batch_date="2026-09-27",
        source_urls=[" https://example.com/a ", "", "https://example.com/a"],
        discovery_timestamp="2026-09-27T01:02:03Z", platforms=["x", "x"],
        editorial_metadata={"reason": "watch"},
    )
    assert package["hot_news"]["source_urls"] == ["https://example.com/a"] * 2
    assert list(package["required_outputs"]) == ["x"]
    assert package["platforms"] == ["x", "x"]
    assert package["editorial_selection"] == {"reason": "watch"}
    assert package["requirements"]["must_not_create_website_draft"] is True
    with pytest.raises(ValueError, match="at least one preserved source URL"):
        workflow.hot_news_monitoring_package(
            title="Empty", batch_date="2026-09-27", source_urls=["  "],
            discovery_timestamp="now", platforms=["x"],
        )


def test_prompt_contract_and_missing_key_exception(tmp_path):
    workflow = legacy.SocialDraftWorkflow(root=tmp_path)
    package = workflow.hot_news_monitoring_package(
        title="News", batch_date="2026-09-27", source_urls=["https://example.com/a"],
        discovery_timestamp="stamp", platforms=["x"],
    )
    prompt = workflow.hot_news_monitoring_prompt(package)
    assert "- Discovery timestamp: stamp" in prompt
    assert "- https://example.com/a" in prompt
    assert "- x: create A.md, B.md, C.md and metadata.json" in prompt
    assert "Do not publish, approve, deploy, index, or push." in prompt
    with pytest.raises(KeyError, match="hot_news"):
        workflow.hot_news_monitoring_prompt({})


def test_default_monitoring_platforms_are_stable(tmp_path, monkeypatch):
    workflow = legacy.SocialDraftWorkflow(root=tmp_path)
    monkeypatch.setattr(workflow, "generate_social_assets", lambda article, **kwargs: {"outputs": {}})
    manifest = workflow.prepare_hot_news_monitoring(
        batch_date="2026-09-27", title="News",
        source_urls=["https://example.com/a"], discovery_timestamp="stamp",
        create_placeholder_drafts=False,
    )
    assert manifest["items"][0]["platforms"] == legacy.HOT_NEWS_MONITORING_PLATFORMS
    assert len(manifest["items"][0]["platforms"]) == 8


@pytest.mark.parametrize("platform", ["x", "quora", "pinterest", "facebook_vi"])
def test_starter_draft_shape_and_determinism(platform):
    kwargs = dict(title="GitHub Copilot agents", summary="", source_urls=["https://github.com/example"],
                  discovery_timestamp="stamp", platform=platform)
    first = legacy._hot_news_starter_drafts(**kwargs)
    assert first == legacy._hot_news_starter_drafts(**kwargs)
    assert list(first["drafts"]) == ["A.md", "B.md", "C.md"]
    assert all(value.endswith("\n") for value in first["drafts"].values())
    assert first["title"]
    if platform in {"x", "quora"}:
        assert first["hashtags"] == []
    else:
        assert "#GitHub" in first["hashtags"]


@pytest.mark.parametrize("placeholder", [False, True])
def test_prepare_manifest_and_artifact_boundaries(tmp_path, monkeypatch, placeholder):
    workflow = legacy.SocialDraftWorkflow(root=tmp_path)
    monkeypatch.setattr(legacy, "now_iso", lambda: "fixed-now")
    monkeypatch.setattr(workflow, "generate_social_assets", lambda article, **kwargs: {"outputs": {}})
    inputs = dict(batch_date="2026-09-27", title="GitHub Copilot agents",
                  source_urls=[" https://github.com/example "], discovery_timestamp="stamp",
                  platforms=["x", "quora"], create_placeholder_drafts=placeholder)
    result = workflow.prepare_hot_news_monitoring(**inputs)
    row = result["items"][0]
    article_dir = tmp_path / "data" / "social_drafts" / "2026-09-27" / row["slug"]
    assert result["workflow_contracts"] == ["HOT_NEWS_MONITORING"]
    assert row["status"] == ("writing_package_ready" if placeholder else "needs_social_draft")
    assert json.loads((article_dir / "source_package.json").read_text(encoding="utf-8"))["hot_news"]["source_urls"] == ["https://github.com/example"]
    assert (article_dir / "CODEX_SOCIAL_WRITING_PROMPT.md").exists()
    for platform in ("x", "quora"):
        metadata = json.loads((article_dir / platform / "metadata.json").read_text(encoding="utf-8"))
        assert metadata["created_at"] == "fixed-now"
        assert metadata["website_url"] == metadata["canonical_url"] == ""
        assert (article_dir / platform / "A.md").exists() is placeholder
    assert workflow.prepare_hot_news_monitoring(**inputs)["items"] == result["items"]
