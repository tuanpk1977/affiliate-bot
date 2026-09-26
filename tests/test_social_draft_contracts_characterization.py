from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from modules.social import draft_workflow as legacy
from modules.social.utils import PublishedArticle


ROOT = Path(__file__).resolve().parents[1]


def _digest(value: object) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _article() -> PublishedArticle:
    return PublishedArticle(
        article_id="workflow-ai-review-2026",
        title="Workflow AI Review 2026 for Small Business",
        url="https://smileaireviewhub.com/workflow-ai-review-2026/",
        canonical_url="https://smileaireviewhub.com/workflow-ai-review-2026/",
        description="A practical workflow review for small-business teams evaluating AI automation, pricing, integrations, governance, and export controls.",
        image="https://smileaireviewhub.com/assets/workflow-ai-review.png",
        og_image="https://smileaireviewhub.com/assets/workflow-ai-review-og.png",
        tags=["#AI", "#SmallBusiness", "#AI"],
        publish_date="2026-09-20",
        summary="Workflow AI helps teams automate repeatable tasks, but buyers should verify pricing, exports, integrations, review controls, and workflow fit before adoption.",
        headings=["Workflow fit", "Pricing and limits", "Governance controls"],
        key_points=[
            "Verify the workflow problem before comparing feature lists.",
            "Check pricing, integrations, exports, support, and review controls.",
        ],
        affiliate_disclosure="This article may contain affiliate links.",
    )


@pytest.mark.parametrize(
    ("raw", "normalized", "validation"),
    [
        (
            " https://pinterest.com/pin/123456/?utm_source=test#frag ",
            "https://www.pinterest.com/pin/123456/",
            {
                "valid": True,
                "status": "valid_pin_url",
                "normalized_url": "https://www.pinterest.com/pin/123456/",
                "message": "Pinterest Pin URL accepted.",
            },
        ),
        (
            "https://pin.it/Abc_123?tracking=yes",
            "https://pin.it/Abc_123",
            {
                "valid": True,
                "status": "limited_short_url",
                "normalized_url": "https://pin.it/Abc_123",
                "message": "pin.it short URL accepted with limited validation. Use the full pinterest.com/pin URL when available.",
            },
        ),
        (
            "",
            "",
            {"valid": False, "status": "empty", "message": "Final Pinterest URL is required."},
        ),
        (
            "https://example.com/pin/123",
            "",
            {
                "valid": False,
                "status": "invalid",
                "message": "Enter a Pinterest Pin URL such as https://www.pinterest.com/pin/<numeric-id>/ or a pin.it short URL.",
            },
        ),
    ],
)
def test_pinterest_url_current_contract(raw: str, normalized: str, validation: dict[str, object]) -> None:
    assert legacy.normalize_pinterest_final_url(raw) == normalized
    assert legacy.validate_pinterest_final_url(raw) == validation


def test_pinterest_metadata_and_text_normalization_golden() -> None:
    fields = legacy._pinterest_fields_from_metadata(
        metadata={
            "hashtags": ["#AI", "#Workflow"],
            "CTA": "Read the full guide: https://smileaireviewhub.com/workflow-ai-review-2026/",
            "keywords": "AI workflow, small business",
            "official_source_name": "Smile AI Review Hub",
        },
        body=(
            "Pin title: Workflow AI Buying Guide\n"
            "Pin description: Compare workflow fit before buying.\n"
            "Destination URL: https://smileaireviewhub.com/workflow-ai-review-2026/\n"
            "Suggested board: AI Tools\n"
            "Overlay text: Verify Workflow Fit"
        ),
        title="Workflow AI Review",
        source_url="https://smileaireviewhub.com/workflow-ai-review-2026/",
        platform_image_path="assets/social/workflow-ai-pinterest.png",
    )
    assert fields == {
        "pin_title": "Workflow AI Buying Guide",
        "pin_description": (
            "Compare workflow fit before buying.\n\n"
            "Source: Smile AI Review Hub\n\n"
            "Read the full guide: https://smileaireviewhub.com/workflow-ai-review-2026/\n\n"
            "#AI #Workflow"
        ),
        "destination_url": "https://smileaireviewhub.com/workflow-ai-review-2026/",
        "image_path": "assets/social/workflow-ai-pinterest.png",
        "image_url": "",
        "suggested_board": "AI Tools",
        "keywords": ["AI workflow", "small business"],
        "alt_text": "Pinterest graphic for Workflow AI Buying Guide.",
        "overlay_text": "Verify Workflow Fit",
        "hashtags": ["#AI", "#Workflow"],
        "official_source_name": "Smile AI Review Hub",
    }
    assert _digest(fields) == "2276d47f0eda2c7702704f29c61b42ad5989d7eb6cee77de9a2a3aa0d809ac10"
    assert legacy._clean_pin_description(
        "Pin description: Compare tools carefully.\n\nRead the full guide: https://example.com/old\n\n#AI #AI",
        cta="Read the full guide: https://example.com/new",
        hashtags=["#AI", "#Workflow"],
        source_name="Official Source",
    ) == (
        "Read the full comparison on Smile AI Review Hub.\n\n"
        "Source: Official Source\n\n"
        "Read the full guide: https://example.com/new\n\n"
        "#AI #Workflow"
    )


def test_blogger_generated_schema_and_golden_current_behavior() -> None:
    fields = legacy._blogger_article_fields(
        _article(),
        platform_image_path="assets/social/workflow-ai-blogger.png",
    )
    assert list(fields) == [
        "title", "seo_title", "h1", "html_body", "plain_text_body", "labels",
        "search_description", "source_article_url", "recommended_permalink_slug", "slug",
        "disclosure", "image_path", "image_alt_text", "image_caption",
        "recommended_image_filename", "open_graph_title", "open_graph_description",
        "twitter_card_description", "json_ld", "body", "character_count", "blogger_word_count",
        "seo_score", "estimated_reading_time_minutes", "heading_count", "faq_count",
        "internal_link_count", "external_link_count", "json_ld_status", "seo_checks",
        "source_limit_note", "validation_warnings",
    ]
    assert fields["validation_warnings"] == ["Blogger image file is missing."]
    assert _digest(fields) == "5d10d750e57ecb878d529f70206eadee70949620230e33f512874ed86a2bdf66"


def test_blogger_validator_invalid_boundary_order_and_text_are_stable() -> None:
    warnings = legacy.validate_blogger_metadata(
        {
            "title": "T" * 61,
            "html_body": "<h3>Duplicate</h3><h3>Duplicate</h3><p>placeholder metadata.json local image file: x</p>",
            "plain_text_body": "Title: placeholder metadata.json C:\\private\\draft.txt",
            "search_description": "unfinished for the",
            "source_article_url": "ftp://invalid",
            "image_path": "Z:/definitely-missing/wave1.png",
            "disclosure": "",
            "recommended_permalink_slug": "Bad--best-top-10-" + ("x" * 80),
            "faq_count": 0,
            "json_ld": {},
        }
    )
    assert warnings == [
        "Blogger title should stay under 60 characters.",
        "Blogger article is below the 1300-word minimum.",
        "Blogger search description should be 140-160 characters.",
        "Blogger search description appears truncated or incomplete.",
        "Source website URL is missing or invalid.",
        "Blogger image file is missing.",
        "Blogger visible body contains internal metadata or local paths.",
        "Blogger visible body contains raw internal label: Title:",
        "Blogger visible body contains raw internal label: Local image file:",
        "Blogger visible body contains raw internal label: metadata.json",
        "Blogger body contains placeholder text.",
        "Affiliate disclosure is missing.",
        "Blogger permalink slug must be lowercase hyphenated text.",
        "Blogger permalink slug is longer than 75 characters.",
        "Blogger permalink slug contains redundant or malformed wording.",
        "Blogger article contains duplicate headings.",
        "Blogger article contains a heading without content.",
        "Blogger article is missing an H1.",
        "Blogger heading hierarchy skips H2 before H3.",
        "Blogger FAQ section should include at least 3 questions.",
        "Blogger JSON-LD is missing.",
    ]
    assert _digest(warnings) == "347c1ff223c2b2171022b2f731df4a1d0fb3386786ffe77e46271c2dca8cccba"


def test_bluesky_generated_schema_defaults_and_golden_current_behavior() -> None:
    fields = legacy._bluesky_fields(
        _article(),
        platform_image_path="assets/social/workflow-ai-bluesky.png",
    )
    assert fields == {
        "standalone_post": (
            "Verify the workflow problem before comparing feature lists.\n\n"
            "Read the guide: https://smileaireviewhub.com/workflow-ai-review-2026/\n\n"
            "#AI #SmallBusiness"
        ),
        "thread_posts": [
            "1/4 Verify the workflow problem before comparing feature lists.",
            "2/4 Start with workflow fit before comparing feature lists. Check what changes in the real weekly process.",
            "3/4 Verify pricing, integrations, exports, support, and review controls before adopting a new AI tool.",
            "4/4 Full source guide: https://smileaireviewhub.com/workflow-ai-review-2026/\n#AI #SmallBusiness",
        ],
        "article_url": "https://smileaireviewhub.com/workflow-ai-review-2026/",
        "hashtags": ["#AI", "#SmallBusiness"],
        "image_path": "assets/social/workflow-ai-bluesky.png",
        "image_alt_text": "Social card for Workflow AI Review 2026 for Small Business.",
        "character_counts": {"standalone_post": 150, "thread_posts": [63, 106, 102, 95]},
        "body": (
            "Verify the workflow problem before comparing feature lists.\n\n"
            "Read the guide: https://smileaireviewhub.com/workflow-ai-review-2026/\n\n"
            "#AI #SmallBusiness"
        ),
        "character_count": 150,
        "validation_warnings": [],
    }
    assert _digest(fields) == "637a1ed6f314dbda899e4cbd5d54ab0338cd1dfab85d9c05208e4426eafe3cab"


def test_bluesky_validator_invalid_boundary_order_and_text_are_stable() -> None:
    assert legacy.validate_bluesky_metadata(
        {
            "standalone_post": "placeholder metadata.json " + ("x" * 310),
            "article_url": "https://example.com/article",
            "thread_posts": ["", "y" * 301],
            "hashtags": ["#AI", "#ai", "#One", "#Two"],
        }
    ) == [
        "Bluesky standalone post exceeds the character limit.",
        "Bluesky article URL is missing from post text.",
        "Bluesky thread post 1 is empty.",
        "Bluesky thread post 2 exceeds the character limit.",
        "Bluesky hashtags contain duplicates.",
        "Bluesky uses too many hashtags.",
        "Bluesky text contains internal metadata or local paths.",
        "Bluesky text contains placeholder text.",
    ]


def test_hot_news_starter_drafts_current_behavior_snapshot() -> None:
    expected = {
        "facebook_en": "a9960e5ecba114d0f108970c96925f3a2ec538a76065aeedaba063a79166adcd",
        "facebook_vi": "29712f59a95e6203091a318fb660a6ac3c08246bc98ae05fa764bf8c4975117c",
        "linkedin": "90d1b40003a491ed6b4a12de87de8dcc3e2b9660573327fc425a42375d02327b",
        "x": "330425735f7182e003f7816a1df8861874ceaa693d1fc32d30e6d3ae28107f72",
        "quora": "7617d26540e6829ee77b3426cd1b6dad7b0a01e5a8314dcc9050d4c31120c19b",
        "devto": "d1875b480b59a6fe1e38c00c47af65fa53aaf536eb40204a1a4ef96c2e759864",
        "pinterest": "e4827239a90bc80846151d4b6eb28c560a9b3ebc2cef6b716e23501a29c323e5",
        "blogger": "50173cd0fb516671a61de32029254702a699418b837a79af8f18a05bea63e31d",
    }
    actual: dict[str, str] = {}
    for platform in legacy.HOT_NEWS_MONITORING_PLATFORMS:
        value = legacy._hot_news_starter_drafts(
            title="GitHub Copilot Agent Update",
            summary="GitHub announced an agent workflow update for development teams.",
            source_urls=[
                "https://github.blog/copilot-agent-update",
                "https://docs.github.com/copilot/agent-update",
            ],
            discovery_timestamp="2026-09-20T12:34:56Z",
            platform=platform,
        )
        assert list(value) == ["title", "cta", "hashtags", "drafts"]
        assert list(value["drafts"]) == ["A.md", "B.md", "C.md"]
        actual[platform] = _digest(value)
    assert actual == expected


def test_status_platform_and_mojibake_defaults_are_stable() -> None:
    assert [legacy._status_key(value) for value in [None, "Approved for Copy", "published-manual", "unknown"]] == [
        "needs_social_review", "approved_for_copy", "published_manual", "needs_social_review",
    ]
    assert legacy._status_label("revision requested") == "Revision Requested"
    assert legacy._platform_label("facebook_vi") == "Facebook Vietnamese"
    assert legacy._platform_label("new_platform") == "New Platform"
    assert legacy.has_vietnamese_mojibake("ChÃƒ corrupted") is True
    assert legacy.has_vietnamese_mojibake("") is False
    assert legacy.vietnamese_mojibake_warning() == (
        "Facebook Vietnamese draft appears to contain mojibake/corrupted Vietnamese text. "
        "Regenerate or edit it before approving for copy."
    )
    assert legacy._append_unique_warning(["one", "one", ""], "one") == ["one", "one"]
    assert legacy._append_unique_warning(["one"], "two") == ["one", "two"]


def test_legacy_module_exports_de_facto_contract_symbols() -> None:
    names = {
        "SOCIAL_DRAFT_STATUSES", "SOCIAL_STATUS_LABELS", "SOCIAL_STATUS_ALIASES", "PLATFORM_LABELS",
        "VIETNAMESE_MOJIBAKE_PATTERNS", "BLUESKY_CHARACTER_LIMIT", "_status_key", "_status_label",
        "_platform_label", "has_vietnamese_mojibake", "vietnamese_mojibake_warning",
        "normalize_pinterest_final_url", "validate_pinterest_final_url", "_clean_pin_description",
        "_pinterest_fields_from_metadata", "_blogger_article_fields", "validate_blogger_metadata",
        "_bluesky_fields", "validate_bluesky_metadata", "_hot_news_starter_drafts",
    }
    assert names <= set(vars(legacy))


def test_validators_are_pure_and_do_not_write_or_call_external_boundaries(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    before = list(tmp_path.rglob("*"))

    def forbidden(*args: object, **kwargs: object) -> object:
        raise AssertionError("validator attempted an external side effect")

    monkeypatch.setattr(Path, "write_text", forbidden)
    monkeypatch.setattr(Path, "mkdir", forbidden)
    monkeypatch.setattr("urllib.request.urlopen", forbidden)
    monkeypatch.setattr(subprocess, "run", forbidden)

    assert legacy.validate_pinterest_final_url("https://www.pinterest.com/pin/123/")["valid"] is True
    assert legacy.validate_blogger_metadata({})
    assert legacy.validate_bluesky_metadata({})
    assert list(tmp_path.rglob("*")) == before


def test_optional_pillow_present_binding_matches_current_environment() -> None:
    if importlib.util.find_spec("PIL") is None:
        pytest.skip("Pillow is not installed in this environment")
    assert legacy.Image is not None
    assert legacy.ImageDraw is not None
    assert legacy.ImageFont is not None


def test_optional_pillow_absence_keeps_legacy_module_importable() -> None:
    code = r'''
import builtins
real_import = builtins.__import__
def guarded(name, globals=None, locals=None, fromlist=(), level=0):
    if name == "PIL" or name.startswith("PIL."):
        raise ImportError("Pillow intentionally unavailable")
    return real_import(name, globals, locals, fromlist, level)
builtins.__import__ = guarded
from modules.social import draft_workflow
assert draft_workflow.Image is None
assert draft_workflow.ImageDraw is None
assert draft_workflow.ImageFont is None
print("OPTIONAL_PILLOW_OK")
'''
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "OPTIONAL_PILLOW_OK"
