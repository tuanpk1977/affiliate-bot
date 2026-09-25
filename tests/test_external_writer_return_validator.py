from __future__ import annotations

import json

import pytest

from modules.external_writer_return_validator import (
    RULE_ID,
    public_output_validation_contract,
    validate_public_output_files,
    validate_website_advanced_html,
)


def validate(html: str) -> list[dict]:
    return validate_public_output_files(
        task_id="website-foundation-task",
        slug="alpha-review",
        files={"website/alpha-review/article.html": (html, "html")},
    )


@pytest.mark.parametrize(
    "token",
    [
        "needs_human_review",
        "HUMAN_APPROVED",
        "READY_FOR_PUBLISH",
        "BLOCKED_RESEARCH",
        "ARTICLE_READY",
    ],
)
def test_exact_workflow_state_tokens_are_blocked(token: str) -> None:
    errors = validate(f"<html><body><p>{token}</p></body></html>")
    assert errors
    assert errors[0]["rule_id"] == RULE_ID
    assert errors[0]["matched_marker"] == token


@pytest.mark.parametrize(
    "path",
    [
        "CURRENT_TASK.md",
        "data/editorial_queue/2026-07-27/topics.json",
        r"data\production_article_drafts\alpha-review\index.html",
    ],
)
def test_internal_repository_paths_are_blocked(path: str) -> None:
    assert validate(f"<p>{path}</p>")


def test_serialized_internal_state_in_html_is_blocked_with_actionable_detail() -> None:
    html = '<script type="application/ld+json">\n{"approval_state":"needs_human_review"}\n</script>'
    error = validate(html)[0]
    assert error["file"] == "website/alpha-review/article.html"
    assert error["line"] == 2
    assert error["column"] == 2
    assert error["character_offset"] > 0
    assert error["matched_marker"]
    assert error["matcher_name"]
    assert error["snippet"]
    assert error["location_type"] == "json_ld"
    assert error["fix_instruction"]


@pytest.mark.parametrize(
    "sentence",
    [
        "This workflow helps buyers compare options.",
        "Our review is based on public documentation.",
        "The editorial team checked the source.",
        "Internal collaboration is a product feature.",
        "Validation can reduce migration risk.",
        "Approval controls are useful for administrators.",
        "The supplied research package did not establish pricing.",
        "This draft explains the public product workflow.",
    ],
)
def test_normal_public_language_is_allowed(sentence: str) -> None:
    assert validate(f"<html><body><p>{sentence}</p></body></html>") == []


def test_valid_json_ld_closing_braces_are_allowed() -> None:
    html = (
        '<script type="application/ld+json">'
        + json.dumps({"@context": "https://schema.org", "@type": "Article"})
        + "</script>"
    )
    assert validate(html) == []


def test_scheduled_not_yet_live_is_not_a_vague_marker() -> None:
    assert validate("<p>The follow-up is scheduled but not yet live.</p>") == []


def test_complete_placeholder_is_blocked_but_json_braces_are_not() -> None:
    errors = validate('<script type="application/ld+json">{"url":"{{AFFILIATE_LINK}}"}</script>')
    assert len(errors) == 1
    assert errors[0]["matcher_name"] == "template_placeholder"


@pytest.mark.parametrize(
    "marker",
    [
        "HUMAN_REVIEW_REQUIRED",
        "DUPLICATE_RISK_REMEDIATION",
        "canonical_task_id",
        "legacy_task_id",
        "revision_id",
        "approved_content_hash",
        "OBSERVATION_START",
        "LEGACY_APPROVAL_UNBOUND",
        "Revision reason:",
        "Review status:",
    ],
)
def test_publication_hygiene_blocks_unmistakable_internal_metadata(marker: str) -> None:
    html = f"<html><body><article><p>{marker}</p></article></body></html>"
    before = html
    errors = validate(html)
    assert errors
    assert errors[0]["rule_id"] == RULE_ID
    assert errors[0]["matcher_name"].startswith("publication_hygiene_")
    assert html == before


@pytest.mark.parametrize(
    "sentence",
    [
        "Review the official source before choosing a plan.",
        "This source review explains the product's scheduling limits.",
        "The product revision improves calendar controls.",
        "Manager approval is useful when administrators change permissions.",
        "Our research compares scheduling and meeting capture.",
    ],
)
def test_publication_hygiene_allows_natural_editorial_language(sentence: str) -> None:
    assert validate(f"<html><body><article><p>{sentence}</p></article></body></html>") == []


def test_private_sidecar_may_retain_revision_metadata_when_not_rendered_publicly() -> None:
    sidecar = {
        "status": "HUMAN_REVIEW_REQUIRED",
        "revision_id": "website-revision-v1:abc",
        "revision_reason": "DUPLICATE_RISK_REMEDIATION",
    }
    public_html = "<html><body><article><p>Review the official source before choosing.</p></article></body></html>"
    assert validate(public_html) == []
    assert sidecar["status"] == "HUMAN_REVIEW_REQUIRED"
    assert sidecar["revision_id"] == "website-revision-v1:abc"


def test_exported_contract_contains_exact_machine_readable_rules() -> None:
    contract = public_output_validation_contract()
    assert contract["schema_version"] == "public_output_validation_v1"
    assert contract["rules"]
    assert all(row["rule_id"] == RULE_ID for row in contract["rules"])
    assert all(row["pattern"] for row in contract["rules"])
    assert "workflow" in contract["explicitly_allowed_public_words"]


def advanced_html(*, body_words: int = 205, duplicate_sections: bool = False) -> str:
    sections = [
        "Overview",
        "Pricing and costs",
        "Security and privacy",
        "Integrations and connectors",
        "Comparison and alternatives",
        "Use cases",
        "Limitations",
        "Final verdict",
    ]
    prose = " ".join(["evidence"] * body_words)
    faq = "".join(f"<h3>Question {index}?</h3><p>Verified answer.</p>" for index in range(12))
    return (
        '<html><head><link rel="canonical" href="https://example.test/alpha/">'
        '<script type="application/ld+json">{"@type":"Article"}</script></head><body>'
        "<h1>Alpha</h1>"
        + "".join(
            f"<h2>{heading}</h2><p>{'' if duplicate_sections else heading + ' '}{prose}</p>"
            for heading in sections
        )
        + "<h2>Frequently asked questions</h2>"
        + faq
        + "<p>Affiliate disclosure: we may earn a commission.</p>"
        + "<table><tr><th>Option</th><th>Evidence</th></tr>"
        + "<tr><td>Alpha</td><td>Verified fit</td></tr></table>"
        + '<a href="/">Home</a><a href="/reviews/">Read reviews</a>'
        + '<a href="https://source.example/alpha">Source</a>'
        + '<a href="https://docs.example/alpha">Documentation</a>'
        + "</body></html>"
    )


def advanced_spec() -> dict:
    return {
        "target_length": {"minimum_words": 1600},
        "faq_requirements": {"required": True, "minimum_questions": 12},
        "required_internal_links": ["/", "/reviews/"],
    }


def test_website_advanced_validator_enforces_article_spec() -> None:
    report = validate_website_advanced_html(
        task_id="advanced-task",
        slug="alpha",
        html=advanced_html(),
        article_spec=advanced_spec(),
        website_contract={"structure": {"h2_range": [8, 14]}},
    )

    assert report["status"] == "PASS"
    assert report["metrics"]["minimum_word_count"] == 1600
    assert report["metrics"]["minimum_faq_questions"] == 12
    assert report["metrics"]["minimum_internal_links"] == 2


def test_website_advanced_validator_reports_every_editorial_requirement() -> None:
    report = validate_website_advanced_html(
        task_id="advanced-task",
        slug="alpha",
        html="<html><body><h1>Short</h1><p>Only a few words.</p></body></html>",
        article_spec=advanced_spec(),
        website_contract={"structure": {"h2_range": [8, 14]}},
    )

    requirements = {row["requirement"] for row in report["errors"]}
    assert requirements == {
        "minimum_word_count",
        "minimum_h2_count",
        "faq",
        "pricing_section",
        "security_section",
        "integrations_section",
        "comparison_section",
        "affiliate_disclosure",
        "internal_links",
        "citations",
        "cta",
        "json_ld",
        "comparison_table",
        "predicted_ai_score",
    }


def test_website_advanced_validator_rejects_placeholders_and_empty_sections() -> None:
    html = advanced_html().replace(
        "<h2>Security and privacy</h2>",
        "<h2>Security and privacy</h2><p>Coming soon.</p><h2>Security evidence</h2>",
        1,
    )
    report = validate_website_advanced_html(
        task_id="advanced-task",
        slug="alpha",
        html=html,
        article_spec=advanced_spec(),
        website_contract={"structure": {"h2_range": [8, 14]}},
    )

    requirements = {row["requirement"] for row in report["errors"]}
    assert "placeholders" in requirements
    assert "empty_sections" in requirements


def test_website_advanced_validator_rejects_high_duplicate_risk() -> None:
    report = validate_website_advanced_html(
        task_id="advanced-task",
        slug="alpha",
        html=advanced_html(duplicate_sections=True),
        article_spec=advanced_spec(),
        website_contract={
            "structure": {"h2_range": [8, 14]},
            "preflight_quality": {"maximum_duplicate_risk": 35},
        },
    )

    requirements = {row["requirement"] for row in report["errors"]}
    assert report["metrics"]["duplicate_risk"] > 35
    assert "duplicate_risk" in requirements
