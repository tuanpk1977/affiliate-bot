from __future__ import annotations

import json
import zipfile
from pathlib import Path

from modules.external_writer_pipeline import (
    QUEUE_SCHEMA,
    UniversalExternalWriterExporter,
    UniversalWriteQueue,
)
from modules.verified_writer_package import (
    AGENT_PIPELINE_V2_FILES,
    REQUIRED_ROOT_FILES,
    validate_verified_package,
)


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2), encoding="utf-8")


def _task(*, strict: bool = False) -> dict:
    task = {
        "schema_version": QUEUE_SCHEMA,
        "task_id": "website_custom-2026-07-28-verified",
        "task_type": "WEBSITE_CUSTOM",
        "workflow_lane": "WEBSITE_CUSTOM",
        "batch_date": "2026-07-28",
        "week_start": "2026-07-27",
        "root_topic_id": "alpha",
        "series_id": "alpha",
        "article_slug": "alpha-review",
        "title": "Alpha Review",
        "normalized_title": "alpha review",
        "primary_source_url": "https://official.example/alpha",
        "supporting_source_urls": [],
        "source_files": [],
        "research_files": ["data/research/alpha-review/package.json"],
        "target_output_type": "website",
        "target_output_paths": [
            "website/alpha-review/article.html",
            "website/alpha-review/article.md",
            "website/alpha-review/metadata.json",
            "website/alpha-review/validation_report.json",
        ],
        "article_type": "review",
        "content_goal": "Help a small business decide whether Alpha fits its workflow.",
        "reader_intent": "Evaluate Alpha before buying.",
        "search_intent": "commercial",
        "audience": "Small business operators",
        "language": "en",
        "platform_targets": [],
        "language_targets": ["en"],
        "required_sections": ["Quick verdict", "Pricing", "Alternatives", "FAQ"],
        "required_tables": ["Buyer comparison"],
        "required_faq": ["Who should use Alpha?", "What should buyers verify?"],
        "required_cta": "Verify the product on its official website.",
        "internal_link_requirements": ["/best-ai-tools/"],
        "next_article_bridge": {"slug": "alpha-alternatives"},
        "tone": "independent",
        "voice": "editorial",
        "style_contract": "Follow package DNA.",
        "source_rules": "Use only supplied evidence.",
        "claim_safety_rules": "No unsupported claims.",
        "forbidden_actions": ["approve", "publish"],
        "validation_commands": ["UTF-8"],
        "status": "PENDING",
        "created_at": "2026-07-28T00:00:00Z",
        "updated_at": "2026-07-28T00:00:00Z",
        "writer": {},
        "revision": 1,
    }
    if strict:
        task["legacy_queue_file"] = "data/editorial_queue/2026-07-28/topics.json"
    return task


def _article_evidence() -> str:
    return " ".join(
        f"Alpha evidence statement {index} describes a documented workflow capability for business users."
        for index in range(1, 21)
    )


def _research(root: Path, *, excerpt: str | None = None) -> None:
    evidence = _article_evidence() if excerpt is None else excerpt
    _write_json(
        root / "data/research/alpha-review/package.json",
        {
            "outline": {
                "heading_hierarchy": [
                    {"level": 2, "heading": "Quick verdict", "purpose": "Answer buyer fit."},
                    {"level": 2, "heading": "Pricing", "purpose": "State verification limits."},
                ],
                "faq_groups": {"buyer": ["Who should use Alpha?"]},
            },
            "writing_plan": {"recommended_word_count": 1800},
            "entities": {"products": ["Alpha"], "product_categories": ["Workflow software"]},
            "sources": {
                "verified_registry_records": [
                    {
                        "id": "alpha-product",
                        "source_name": "Alpha official product page",
                        "source_url": "https://official.example/alpha",
                        "verification_status": "verified",
                        "verification_date": "2026-07-28",
                        "extracted_relevant_paragraphs": [evidence] if evidence else [],
                        "allowed_usage": "Paraphrase with attribution.",
                        "limitations": "Do not infer pricing or performance.",
                        "confidence": 95,
                    }
                ]
            },
        },
    )


def _export(root: Path, *, strict: bool = False) -> Path:
    _research(root)
    task = _task(strict=strict)
    UniversalWriteQueue(root=root).save(task)
    result = UniversalExternalWriterExporter(root=root).export(
        batch_date=task["batch_date"],
        task_type=task["task_type"],
    )
    return Path(result["zip_path"])


def test_verified_export_contains_complete_model_neutral_contract(tmp_path: Path) -> None:
    package = _export(tmp_path, strict=True)
    result = validate_verified_package(package)
    assert result.valid, result.errors
    with zipfile.ZipFile(package) as archive:
        names = set(archive.namelist())
        start = archive.read("START_HERE.txt").decode("utf-8")
        blueprint = json.loads(archive.read("ARTICLE_BLUEPRINT.json"))
        ledger = json.loads(archive.read("FACT_LEDGER.json"))
        excerpts = json.loads(archive.read("SOURCE_EXCERPTS.json"))
        contract = json.loads(archive.read("verified_package_contract.json"))
        output_contract = json.loads(archive.read("OUTPUT_CONTRACT.json"))
    assert set(REQUIRED_ROOT_FILES) <= names
    assert set(AGENT_PIPELINE_V2_FILES) <= names
    assert {
        "GOLDEN_EXAMPLE/research.json",
        "GOLDEN_EXAMPLE/blueprint.json",
        "GOLDEN_EXAMPLE/finished_article.md",
        "GOLDEN_EXAMPLE/validation.json",
    } <= names
    assert "ChatGPT" not in start
    assert "Never search, browse, crawl, verify, or research" in start
    assert contract["agent_pipeline_version"] == 2
    assert output_contract["website_required"][-1] == "validation.json"
    assert blueprint["articles"][0]["section_order"][0]["purpose"]
    facts = ledger["articles"][0]["facts"]
    assert len(facts) == 20
    assert all(
        {
            "source_url",
            "supporting_excerpt",
            "allowed_usage",
            "limitations",
            "freshness",
            "confidence",
        }
        <= set(fact)
        for fact in facts
    )
    assert excerpts["articles"][0]["sources"][0]["extracted_relevant_paragraphs"] == [
        _article_evidence()
    ]
    assert "Validated by weekly topic source-readiness preflight." not in json.dumps(ledger)


def test_strict_export_consumes_separate_enrichment_artifacts(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "data/research/alpha-review/package.json",
        {
            "outline": {},
            "writing_plan": {"recommended_word_count": 1800},
            "entities": {"products": ["Alpha"]},
            "sources": {
                "verified_sources": [
                    {
                        "source_url": "https://official.example/alpha",
                        "verification_status": "verified",
                    }
                ]
            },
        },
    )
    paragraph = _article_evidence()
    _write_json(
        tmp_path / "data/research/alpha-review/SOURCE_EXCERPTS.json",
        {
            "schema_version": 2,
            "sources": [
                {
                    "source_id": "source-001",
                    "title": "Alpha official documentation",
                    "url": "https://official.example/alpha",
                    "source_type": "official_docs",
                    "extracted_relevant_paragraphs": [paragraph],
                    "allowed_usage": "Paraphrase narrowly with attribution.",
                    "limitations": "Do not infer unstated terms.",
                    "freshness": "2026-07-28",
                    "confidence": "high",
                }
            ],
        },
    )
    facts = [
        {
            "claim_id": f"claim-{index:03d}",
            "exact_statement": f"Alpha evidence statement {index} describes a documented workflow capability for business users.",
            "source_id": "source-001",
            "source_url": "https://official.example/alpha",
            "supporting_excerpt": f"Alpha evidence statement {index} describes a documented workflow capability for business users.",
            "allowed_usage": "Paraphrase narrowly with attribution.",
            "limitations": "Do not infer unstated terms.",
            "freshness": "2026-07-28",
            "confidence": "high",
        }
        for index in range(1, 21)
    ]
    _write_json(
        tmp_path / "data/research/alpha-review/FACT_LEDGER.json",
        {"schema_version": 2, "facts": facts},
    )
    _write_json(
        tmp_path / "data/research/alpha-review/ARTICLE_BLUEPRINT.json",
        {
            "schema_version": 2,
            "sections": [
                {
                    "section_id": "quick-verdict",
                    "order": 1,
                    "heading": "Quick verdict",
                    "purpose": "Answer buyer fit using the verified evidence.",
                    "assigned_claim_ids": [row["claim_id"] for row in facts],
                    "evidence_coverage_status": "covered",
                    "prohibited_claims": ["Claims absent from the ledger."],
                }
            ],
        },
    )
    task = _task(strict=True)
    UniversalWriteQueue(root=tmp_path).save(task)
    result = UniversalExternalWriterExporter(root=tmp_path).export(
        batch_date=task["batch_date"],
        task_type=task["task_type"],
    )
    verified = validate_verified_package(Path(result["zip_path"]))
    assert verified.valid, verified.errors


def test_strict_export_warns_for_missing_source_excerpt_without_blocking(tmp_path: Path) -> None:
    _research(tmp_path, excerpt="")
    task = _task(strict=True)
    UniversalWriteQueue(root=tmp_path).save(task)
    exported = UniversalExternalWriterExporter(root=tmp_path).export(
        batch_date=task["batch_date"],
        task_type=task["task_type"],
    )
    validation = validate_verified_package(Path(exported["zip_path"]))
    assert validation.valid
    assert any(
        "extracted_relevant_paragraphs" in warning
        for warning in validation.warnings
    )


def test_preflight_placeholder_becomes_warning_without_blocking_export(tmp_path: Path) -> None:
    _research(tmp_path, excerpt="Validated by weekly topic source-readiness preflight.")
    task = _task(strict=True)
    UniversalWriteQueue(root=tmp_path).save(task)
    exported = UniversalExternalWriterExporter(root=tmp_path).export(
        batch_date=task["batch_date"],
        task_type=task["task_type"],
    )
    validation = validate_verified_package(Path(exported["zip_path"]))
    assert validation.valid
    assert any(
        "no publishable claims" in warning
        or "non-evidence placeholder" in warning
        for warning in validation.warnings
    )


def test_fresh_context_validation_uses_only_the_zip(tmp_path: Path) -> None:
    package = _export(tmp_path, strict=True)
    isolated = tmp_path / "fresh-context" / "verified_package.zip"
    isolated.parent.mkdir()
    isolated.write_bytes(package.read_bytes())
    result = validate_verified_package(isolated)
    assert result.valid
    assert result.article_count == 1
