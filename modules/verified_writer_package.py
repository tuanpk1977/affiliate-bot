from __future__ import annotations

import json
import re
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from modules.external_writer_return_validator import public_output_validation_contract
from modules.research_artifacts import resolve_research_artifacts


VERIFIED_PACKAGE_SCHEMA = "verified_external_writer_package_v2"
CONTRACT_SCHEMA = "verified_external_writer_contract_v2"
MIN_PUBLISHABLE_FACTS = 20
MAX_PUBLISHABLE_FACTS = 100
MINIMUM_FACTS_BY_LEVEL = {
    "RESEARCH_MINIMUM": 8,
    "RESEARCH_GOOD": 12,
    "RESEARCH_STRONG": 16,
    "RESEARCH_COMPLETE": 20,
    "ARTICLE_READY": 20,
}

NON_EVIDENCE_MARKERS = (
    "validated by weekly topic source-readiness preflight",
    "no live fetch",
    "requires manual confirmation",
    "pricing should be verified",
    "reviewed on",
    "source-readiness",
)

REQUIRED_ROOT_FILES = (
    "START_HERE.txt",
    "TASK.md",
    "ARTICLE_BLUEPRINT.json",
    "FACT_LEDGER.json",
    "SOURCE_EXCERPTS.json",
    "ENTITY_PROFILE.json",
    "ANGLE_RESEARCH_PLAN.json",
    "WRITING_DNA.md",
    "STRUCTURE_DNA.md",
    "VOICE_DNA.md",
    "SELF_REVIEW.md",
    "QUALITY_SCORE.md",
    "VALIDATION_RULES.json",
    "OUTPUT_SCHEMA.json",
    "verified_package_contract.json",
)

AGENT_PIPELINE_V2_FILES = (
    "ARTICLE_SPEC.json",
    "OUTLINE.json",
    "VERIFIED_CLAIMS.json",
    "SECTION_GUIDE.json",
    "FAQ.json",
    "TERMINOLOGY.json",
    "COMPETITOR_NOTES.json",
    "IMAGE_GUIDE.json",
    "INTERNAL_LINKS.json",
    "EXTERNAL_LINKS.json",
    "SCHEMA.json",
    "EDITORIAL_RULES.json",
    "RESEARCH_GAPS.json",
    "WRITER_CHECKLIST.json",
    "OUTPUT_CONTRACT.json",
)

BLUEPRINT_FIELDS = (
    "title",
    "slug",
    "article_type",
    "search_intent",
    "reader_intent",
    "target_audience",
    "article_thesis",
    "unique_angle",
    "section_order",
    "target_length",
    "required_tables",
    "faq_requirements",
    "cta_intention",
    "next_article_bridge",
    "required_internal_links",
    "forbidden_overlap",
)

FACT_FIELDS = (
    "claim_id",
    "exact_statement",
    "evidence_level",
    "source_url",
    "supporting_excerpt",
    "allowed_usage",
    "limitations",
    "freshness",
    "confidence",
)

SOURCE_FIELDS = (
    "source_id",
    "title",
    "url",
    "author",
    "publication",
    "publication_date",
    "extracted_relevant_paragraphs",
    "allowed_usage",
    "limitations",
    "freshness",
    "confidence",
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _read_json(path: Path, default: Any) -> Any:
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return default


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _unique_strings(values: Iterable[Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _text(value)
        key = text.casefold()
        if text and key not in seen:
            seen.add(key)
            result.append(text)
    return result


def _flatten_questions(value: Any) -> list[str]:
    if isinstance(value, dict):
        return _unique_strings(
            question
            for questions in value.values()
            for question in (questions if isinstance(questions, list) else [])
        )
    return _unique_strings(value if isinstance(value, list) else [])


def _is_publishable_evidence(value: Any) -> bool:
    text = _text(value)
    lowered = text.casefold()
    return (
        len(text.split()) >= 6
        and not any(marker in lowered for marker in NON_EVIDENCE_MARKERS)
        and not text.startswith(("http://", "https://"))
    )


def _paragraphs_from_value(value: Any) -> list[str]:
    if isinstance(value, list):
        return _unique_strings(
            paragraph
            for item in value
            for paragraph in _paragraphs_from_value(item)
        )
    if isinstance(value, dict):
        return _unique_strings(
            paragraph
            for key in (
                "extracted_relevant_paragraphs",
                "relevant_paragraphs",
                "paragraphs",
                "source_excerpts",
                "content",
                "body",
                "text",
                "excerpt",
                "supporting_excerpt",
            )
            for paragraph in _paragraphs_from_value(value.get(key))
        )
    text = _text(value)
    if not text:
        return []
    blocks = re.split(r"(?:\r?\n){2,}", text)
    return [block.strip() for block in blocks if _is_publishable_evidence(block)]


def _confidence(value: Any, default: float = 0.7) -> float:
    labels = {"low": 0.45, "medium": 0.7, "high": 0.9}
    if isinstance(value, str) and value.casefold() in labels:
        return labels[value.casefold()]
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    if result > 1:
        result /= 100
    return round(max(0.0, min(1.0, result)), 3)


def _sentence_claims(paragraph: str) -> list[str]:
    sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", paragraph.strip())
    return [
        sentence.strip()
        for sentence in sentences
        if _is_publishable_evidence(sentence)
    ]


def _source_rows(research: dict[str, Any], task: dict[str, Any]) -> list[dict[str, Any]]:
    sources = research.get("sources") if isinstance(research.get("sources"), dict) else {}
    candidates: list[dict[str, Any]] = []
    registry = sources.get("verified_registry_records")
    if isinstance(registry, list):
        candidates.extend(row for row in registry if isinstance(row, dict))
    trusted = sources.get("trusted_sources")
    if isinstance(trusted, dict):
        for source_type, rows in trusted.items():
            for row in rows if isinstance(rows, list) else []:
                if isinstance(row, dict):
                    candidates.append({**row, "source_type": row.get("source_type") or source_type})
    direct = sources.get("verified_sources")
    if isinstance(direct, list):
        candidates.extend(row for row in direct if isinstance(row, dict))
    for key in ("source_excerpts", "source_snapshots", "approved_source_content"):
        rows = research.get(key)
        if isinstance(rows, dict):
            rows = rows.get("sources") or rows.get("items") or []
        if isinstance(rows, list):
            candidates.extend(row for row in rows if isinstance(row, dict))

    if not research.get("_enriched_evidence"):
        for url in (
            task.get("primary_source_url"),
            *(task.get("supporting_source_urls") or []),
        ):
            if _text(url):
                candidates.append(
                    {
                        "source_name": f"Editorially supplied source for {task.get('title')}",
                        "source_url": url,
                        "verification_status": "supplied",
                        "notes": _text(task.get("source_rules")),
                    }
                )

    result: list[dict[str, Any]] = []
    by_url: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(candidates, start=1):
        url = _text(row.get("source_url") or row.get("url"))
        if not url:
            continue
        paragraphs = _unique_strings(
            paragraph
            for key in (
                "extracted_relevant_paragraphs",
                "relevant_paragraphs",
                "paragraphs",
                "source_excerpts",
                "content",
                "body",
                "text",
                "excerpt",
                "supporting_excerpt",
            )
            for paragraph in _paragraphs_from_value(row.get(key))
        )
        freshness = _text(
            row.get("freshness")
            or row.get("publication_date")
            or row.get("verification_date")
            or row.get("last_checked")
        ) or "date_not_available"
        limitations = _text(row.get("limitations") or row.get("caveat")) or (
            "Use only the supplied paragraphs. Do not infer unstated pricing, availability, "
            "performance, eligibility, or commercial terms."
        )
        key = url.casefold()
        if key in by_url:
            existing = by_url[key]
            existing["extracted_relevant_paragraphs"] = _unique_strings(
                [*existing["extracted_relevant_paragraphs"], *paragraphs]
            )
            continue
        normalized = {
                "source_id": _text(row.get("id")) or f"source-{index:03d}",
                "title": _text(row.get("source_name") or row.get("label") or row.get("title"))
                or url,
                "url": url,
                "author": _text(row.get("author")),
                "publication": _text(row.get("publication") or row.get("brand")),
                "publication_date": _text(
                    row.get("publication_date")
                    or row.get("verification_date")
                    or row.get("last_checked")
                ),
                "extracted_relevant_paragraphs": paragraphs,
                "verification_status": _text(
                    row.get("verification_status") or row.get("status") or "supplied"
                ),
                "source_type": _text(row.get("source_type") or row.get("connector_type")),
                "allowed_usage": _text(row.get("allowed_usage"))
                or "Paraphrase or quote briefly with attribution to this source URL.",
                "limitations": limitations,
                "freshness": freshness,
                "freshness_score": row.get("freshness_score"),
                "trust_score": row.get("trust_score"),
                "confidence": _confidence(row.get("confidence")),
        }
        result.append(normalized)
        by_url[key] = normalized
    return result


def _fact_rows(
    research: dict[str, Any],
    task: dict[str, Any],
    source_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    raw_fact_groups: list[Any] = []
    for key in ("verified_facts", "facts", "fact_ledger"):
        value = research.get(key)
        if isinstance(value, dict):
            raw_fact_groups.extend(value.get("facts") or value.get("items") or [])
        elif isinstance(value, list):
            raw_fact_groups.extend(value)
    for index, row in enumerate(raw_fact_groups, start=1):
        if not isinstance(row, dict):
            continue
        statement = _text(row.get("exact_statement") or row.get("claim") or row.get("statement"))
        excerpt = _text(row.get("supporting_excerpt") or row.get("excerpt") or row.get("evidence"))
        source = _text(row.get("source_url") or row.get("source"))
        if statement and source and excerpt:
            facts.append(
                {
                    "claim_id": _text(row.get("claim_id") or row.get("id")) or f"claim-{index:03d}",
                    "exact_statement": statement,
                    "evidence_level": _text(row.get("evidence_level") or row.get("status"))
                    or "verified",
                    "source_url": source,
                    "source": source,
                    "supporting_excerpt": excerpt,
                    "allowed_usage": _text(row.get("allowed_usage"))
                    or "Paraphrase this claim with attribution to the source URL.",
                    "limitations": _text(row.get("limitations") or row.get("caveat")),
                    "freshness": _text(row.get("freshness") or row.get("verified_at")),
                    "confidence": _confidence(row.get("confidence"), 0.8),
                }
            )
    if raw_fact_groups:
        return facts[:MAX_PUBLISHABLE_FACTS]
    seen_statements = {_text(row.get("exact_statement")).casefold() for row in facts}
    for source in source_rows:
        paragraphs = source.get("extracted_relevant_paragraphs") or []
        for paragraph in paragraphs:
            for statement in _sentence_claims(_text(paragraph)):
                key = statement.casefold()
                if key in seen_statements:
                    continue
                seen_statements.add(key)
                facts.append(
                    {
                        "claim_id": f"claim-{len(facts) + 1:03d}",
                        "exact_statement": statement,
                        "evidence_level": _text(source.get("verification_status")) or "verified",
                        "source_url": source["url"],
                        "source": source["url"],
                        "supporting_excerpt": _text(paragraph),
                        "allowed_usage": _text(source.get("allowed_usage")),
                        "limitations": _text(source.get("limitations")),
                        "freshness": _text(source.get("freshness")) or "date_not_available",
                        "confidence": _confidence(source.get("confidence")),
                    }
                )
                if len(facts) >= MAX_PUBLISHABLE_FACTS:
                    return facts
    return facts[:MAX_PUBLISHABLE_FACTS]


def _sections(research: dict[str, Any], task: dict[str, Any], claim_ids: list[str]) -> list[dict[str, Any]]:
    enriched = research.get("article_blueprint")
    enriched_sections = enriched.get("sections") if isinstance(enriched, dict) else None
    if isinstance(enriched_sections, list) and enriched_sections:
        rows: list[dict[str, Any]] = []
        for index, section in enumerate(enriched_sections, start=1):
            if not isinstance(section, dict):
                continue
            rows.append(
                {
                    "order": int(section.get("order") or index),
                    "section_id": _text(section.get("section_id")) or f"section-{index:02d}",
                    "heading": _text(section.get("heading")),
                    "purpose": _text(section.get("purpose")),
                    "required_evidence_claim_ids": list(
                        section.get("assigned_claim_ids")
                        or section.get("required_evidence_claim_ids")
                        or []
                    ),
                    "claims_to_avoid": list(
                        section.get("prohibited_claims")
                        or ["Any claim absent from FACT_LEDGER.json"]
                    ),
                    "evidence_coverage_status": _text(section.get("evidence_coverage_status")),
                    "unresolved_gaps": list(section.get("unresolved_gaps") or []),
                }
            )
        if rows:
            return rows
    outline = research.get("outline") if isinstance(research.get("outline"), dict) else {}
    hierarchy = outline.get("heading_hierarchy")
    rows: list[dict[str, Any]] = []
    if isinstance(hierarchy, list):
        for index, row in enumerate(hierarchy, start=1):
            if not isinstance(row, dict):
                continue
            heading = _text(row.get("heading"))
            if heading:
                rows.append(
                    {
                        "order": index,
                        "heading": heading,
                        "purpose": _text(row.get("purpose"))
                        or f"Answer the reader's decision question for {heading}.",
                        "required_evidence_claim_ids": claim_ids[:3],
                        "claims_to_avoid": [
                            "Any price, feature, integration, or performance claim not present in FACT_LEDGER.json"
                        ],
                    }
                )
    if not rows:
        required = _unique_strings(task.get("required_sections") or [])
        if not required:
            required = [
                "Quick verdict",
                "Evaluation criteria",
                "Main analysis",
                "Pricing and limitations",
                "Alternatives",
                "FAQ",
                "Final recommendation",
            ]
        rows = [
            {
                "order": index,
                "heading": heading,
                "purpose": f"Deliver the required {heading} decision support without adding unsupported claims.",
                "required_evidence_claim_ids": claim_ids[:3],
                "claims_to_avoid": [
                    "Any price, feature, integration, or performance claim not present in FACT_LEDGER.json"
                ],
            }
            for index, heading in enumerate(required, start=1)
        ]
    if claim_ids and rows:
        for index, row in enumerate(rows):
            start = (len(claim_ids) * index) // len(rows)
            end = (len(claim_ids) * (index + 1)) // len(rows)
            row["required_evidence_claim_ids"] = claim_ids[start:end] or claim_ids[:1]
    return rows


def _entity_rows(research: dict[str, Any], task: dict[str, Any], facts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    entities = research.get("entities") if isinstance(research.get("entities"), dict) else {}
    names = _unique_strings(
        [
            *(entities.get("companies") or []),
            *(entities.get("products") or []),
            *(entities.get("ai_tools") or []),
        ]
    )
    if not names:
        names = [_text(task.get("title"))]
    source_urls = _unique_strings(
        [task.get("primary_source_url"), *(task.get("supporting_source_urls") or [])]
    )
    return [
        {
            "official_name": name,
            "aliases": [],
            "website": source_urls[0] if source_urls else "",
            "github": "",
            "documentation": source_urls[1] if len(source_urls) > 1 else "",
            "category": _text((entities.get("product_categories") or [""])[0]),
            "positioning": _text(task.get("content_goal")),
            "strengths": [],
            "limitations": _unique_strings(research.get("quality", {}).get("missing_information", []))
            if isinstance(research.get("quality"), dict)
            else [],
            "competitors": _unique_strings(
                [*(entities.get("competitors") or []), *(entities.get("alternatives") or [])]
            ),
            "supported_claims": [row["claim_id"] for row in facts],
        }
        for name in names
        if name
    ]


def build_verified_package(
    *,
    package_dir: Path,
    root: Path,
    package_id: str,
    task_type: str,
    batch_date: str,
    tasks: list[dict[str, Any]],
    output_contract: dict[str, Any],
    website_contract: dict[str, Any] | None,
) -> dict[str, Any]:
    article_blueprints: list[dict[str, Any]] = []
    ledgers: list[dict[str, Any]] = []
    excerpts: list[dict[str, Any]] = []
    profiles: list[dict[str, Any]] = []
    angle_plans: list[dict[str, Any]] = []
    research_task_sets: list[dict[str, Any]] = []
    contract_tasks: list[dict[str, Any]] = []
    research_contexts: dict[str, dict[str, Any]] = {}

    strict_articles: list[str] = []
    compatibility_articles: list[str] = []
    for task in tasks:
        slug = _text(task.get("article_slug"))
        resolution = resolve_research_artifacts(
            root,
            task_id=_text(task.get("task_id")),
            slug=slug,
            batch_date=_text(task.get("batch_date") or batch_date),
        )
        research_path = resolution.package_file
        research = _read_json(research_path, {})
        research_contexts[slug] = research if isinstance(research, dict) else {}
        research_dir = research_path.parent
        if isinstance(research, dict):
            source_artifact = _read_json(research_dir / "SOURCE_EXCERPTS.json", {})
            fact_artifact = _read_json(research_dir / "FACT_LEDGER.json", {})
            blueprint_artifact = _read_json(research_dir / "ARTICLE_BLUEPRINT.json", {})
            angle_plan_artifact = _read_json(research_dir / "ANGLE_RESEARCH_PLAN.json", {})
            research_tasks_artifact = _read_json(
                research_dir / "research_tasks.json",
                {},
            )
            enrichment_artifact = _read_json(
                research_dir / "enrichment_report.json",
                {},
            )
            if isinstance(source_artifact, dict) and isinstance(source_artifact.get("sources"), list):
                research["sources"] = {}
                research["source_excerpts"] = source_artifact["sources"]
                research["_enriched_evidence"] = True
            if isinstance(fact_artifact, dict) and isinstance(fact_artifact.get("facts"), list):
                research["fact_ledger"] = fact_artifact["facts"]
            if isinstance(blueprint_artifact, dict) and isinstance(blueprint_artifact.get("sections"), list):
                research["article_blueprint"] = blueprint_artifact
            if isinstance(angle_plan_artifact, dict):
                research["angle_research_plan"] = angle_plan_artifact
            if isinstance(research_tasks_artifact, dict):
                research["research_tasks"] = research_tasks_artifact
            if isinstance(enrichment_artifact, dict):
                research["research_readiness"] = {
                    key: enrichment_artifact.get(key)
                    for key in (
                        "research_level",
                        "draft_exportable",
                        "critical_safety_violations",
                        "known_uncertainties",
                        "weak_sections",
                        "comparison_status",
                        "estimated_publish_readiness",
                        "revision_count",
                    )
                }
        strict = bool(_text(task.get("legacy_queue_file")))
        (strict_articles if strict else compatibility_articles).append(slug)
        source_rows = _source_rows(research if isinstance(research, dict) else {}, task)
        facts = _fact_rows(research if isinstance(research, dict) else {}, task, source_rows)
        claim_ids = [row["claim_id"] for row in facts]
        outline = research.get("outline") if isinstance(research, dict) else {}
        faq = (
            _flatten_questions(outline.get("faq_groups"))
            if isinstance(outline, dict)
            else []
        )
        faq = faq or _unique_strings(task.get("required_faq") or [])
        writing_plan = research.get("writing_plan") if isinstance(research, dict) else {}
        target_length = (
            int(writing_plan.get("recommended_word_count") or 0)
            if isinstance(writing_plan, dict)
            else 0
        ) or 2200
        if task_type == "WEBSITE_ADVANCED":
            target_length = max(2200, min(2600, target_length))
        sections = _sections(research if isinstance(research, dict) else {}, task, claim_ids)
        blueprint = {
            "task_id": task["task_id"],
            "revision": int(task.get("revision") or 1),
            "title": _text(task.get("title")),
            "slug": slug,
            "article_type": _text(task.get("article_type")),
            "search_intent": _text(task.get("search_intent")) or "not_applicable",
            "reader_intent": _text(task.get("reader_intent")) or _text(task.get("content_goal")),
            "target_audience": _text(task.get("audience")),
            "article_thesis": _text(task.get("content_goal")),
            "unique_angle": _text(task.get("content_goal")),
            "section_order": sections,
            "target_length": (
                {
                    "minimum_words": 2200,
                    "target_words": max(2400, target_length),
                    "maximum_words": 2600,
                }
                if task_type == "WEBSITE_ADVANCED"
                else {
                    "minimum_words": max(800, target_length - 300),
                    "target_words": target_length,
                }
            ),
            "required_tables": list(task.get("required_tables") or []),
            "faq_requirements": {
                "required": bool(faq),
                "questions": faq,
                "minimum_questions": len(faq),
            },
            "cta_intention": _text(task.get("required_cta")),
            "next_article_bridge": task.get("next_article_bridge") or {},
            "required_internal_links": list(task.get("internal_link_requirements") or []),
            "forbidden_overlap": {
                "root_topic_id": _text(task.get("root_topic_id")),
                "rules": [
                    "Do not reuse a prior article's thesis, heading sequence, or conclusion.",
                    "Do not repeat evidence outside the section assignments in this blueprint.",
                ],
            },
            "source_rules": _text(task.get("source_rules")),
            "claim_safety_rules": _text(task.get("claim_safety_rules")),
        }
        article_blueprints.append(blueprint)
        ledgers.append({"task_id": task["task_id"], "slug": slug, "facts": facts})
        excerpts.append({"task_id": task["task_id"], "slug": slug, "sources": source_rows})
        profiles.append(
            {
                "task_id": task["task_id"],
                "slug": slug,
                "entities": _entity_rows(
                    research if isinstance(research, dict) else {}, task, facts
                ),
            }
        )
        angle_plans.append(
            {
                "task_id": task["task_id"],
                "slug": slug,
                **(
                    research.get("angle_research_plan")
                    if isinstance(research.get("angle_research_plan"), dict)
                    else {
                        "schema_version": 1,
                        "angle_profile": "not_applicable",
                        "planning_status": "NOT_APPLICABLE",
                    }
                ),
            }
        )
        research_task_payload = (
            research.get("research_tasks")
            if isinstance(research.get("research_tasks"), dict)
            else {}
        )
        task_rows = list(research_task_payload.get("tasks") or [])
        known_reasons = {
            _text(row.get("reason")).casefold()
            for row in task_rows
            if isinstance(row, dict)
        }
        for reason in (*resolution.missing_files, *resolution.legacy_reasons):
            if _text(reason).casefold() in known_reasons:
                continue
            task_rows.append(
                {
                    "task_id": f"research-package-gap-{len(task_rows) + 1:03d}",
                    "task_type": "EVIDENCE_GAP",
                    "section": "general",
                    "status": "PENDING",
                    "severity": "non_critical",
                    "blocks_first_draft": False,
                    "reason": _text(reason),
                    "recommended_source_families": [],
                    "recommended_wording": (
                        "Use only supplied verified claims and mark absent details "
                        "as a Research Gap."
                    ),
                }
            )
        research_task_sets.append(
            {
                "task_id": task["task_id"],
                "slug": slug,
                "research_level": (
                    research.get("research_readiness", {}).get("research_level")
                    if isinstance(research.get("research_readiness"), dict)
                    else task.get("research_level")
                ),
                "comparison_status": research_task_payload.get(
                    "comparison_status",
                    task.get("comparison_status") or "NOT_APPLICABLE",
                ),
                "tasks": task_rows,
                "known_uncertainties": list(
                    research_task_payload.get("known_uncertainties") or []
                ),
                "weak_sections": list(
                    research_task_payload.get("weak_sections") or []
                ),
                "recommended_writer_policy": research_task_payload.get(
                    "recommended_writer_policy"
                )
                or (
                    "Use only verified facts. Omit or qualify uncertain details. "
                    "A draft is not approval to publish."
                ),
            }
        )
        minimum_publishable_claims = MINIMUM_FACTS_BY_LEVEL.get(
            _text(resolution.research_level).upper(),
            MIN_PUBLISHABLE_FACTS,
        )
        contract_tasks.append(
            {
                **task,
                "evidence_policy": {
                    "strict_article_evidence": strict,
                    "minimum_publishable_claims": minimum_publishable_claims,
                    "maximum_publishable_claims": MAX_PUBLISHABLE_FACTS,
                    "web_revisit_required": False,
                },
                "blueprint": blueprint,
                "fact_ledger": facts,
                "source_excerpts": source_rows,
                "entity_profile": profiles[-1]["entities"],
                "allowed_source_urls": [row["url"] for row in source_rows],
                "research_readiness": (
                    research.get("research_readiness")
                    if isinstance(research.get("research_readiness"), dict)
                    else {
                        "research_level": task.get("research_level"),
                        "draft_exportable": task.get("draft_exportable"),
                        "comparison_status": task.get("comparison_status"),
                    }
                ),
                "research_tasks": research_task_sets[-1]["tasks"],
                "known_uncertainties": research_task_sets[-1][
                    "known_uncertainties"
                ],
                "known_weak_sections": research_task_sets[-1]["weak_sections"],
                "recommended_wording": [
                    row.get("recommended_wording")
                    for row in research_task_sets[-1]["tasks"]
                    if isinstance(row, dict) and row.get("recommended_wording")
                ],
            }
        )

    _write_json(
        package_dir / "ARTICLE_BLUEPRINT.json",
        {"schema_version": VERIFIED_PACKAGE_SCHEMA, "articles": article_blueprints},
    )
    _write_json(
        package_dir / "FACT_LEDGER.json",
        {"schema_version": VERIFIED_PACKAGE_SCHEMA, "articles": ledgers},
    )
    _write_json(
        package_dir / "SOURCE_EXCERPTS.json",
        {"schema_version": VERIFIED_PACKAGE_SCHEMA, "articles": excerpts},
    )
    _write_json(
        package_dir / "ENTITY_PROFILE.json",
        {"schema_version": VERIFIED_PACKAGE_SCHEMA, "articles": profiles},
    )
    _write_json(
        package_dir / "ANGLE_RESEARCH_PLAN.json",
        {"schema_version": VERIFIED_PACKAGE_SCHEMA, "articles": angle_plans},
    )
    _write_json(
        package_dir / "RESEARCH_TASKS.json",
        {"schema_version": VERIFIED_PACKAGE_SCHEMA, "articles": research_task_sets},
    )

    blueprints_by_slug = {
        _text(row.get("slug")): row for row in article_blueprints if isinstance(row, dict)
    }
    profiles_by_slug = {
        _text(row.get("slug")): row for row in profiles if isinstance(row, dict)
    }
    tasks_by_slug = {
        _text(row.get("article_slug")): row for row in contract_tasks if isinstance(row, dict)
    }
    research_tasks_by_slug = {
        _text(row.get("slug")): row
        for row in research_task_sets
        if isinstance(row, dict)
    }
    article_specs: list[dict[str, Any]] = []
    outlines: list[dict[str, Any]] = []
    section_guides: list[dict[str, Any]] = []
    faq_sets: list[dict[str, Any]] = []
    terminology_sets: list[dict[str, Any]] = []
    competitor_notes: list[dict[str, Any]] = []
    image_guides: list[dict[str, Any]] = []
    internal_link_sets: list[dict[str, Any]] = []
    external_link_sets: list[dict[str, Any]] = []
    schema_sets: list[dict[str, Any]] = []
    research_gaps: list[dict[str, Any]] = []
    writer_checklists: list[dict[str, Any]] = []
    for slug, blueprint in blueprints_by_slug.items():
        task = tasks_by_slug.get(slug, {})
        research = research_contexts.get(slug, {})
        profile = profiles_by_slug.get(slug, {})
        task_set = research_tasks_by_slug.get(slug, {})
        entities = list(profile.get("entities") or [])
        entity_names = _unique_strings(
            value
            for entity in entities
            if isinstance(entity, dict)
            for value in (
                entity.get("name"),
                entity.get("category"),
                *(entity.get("competitors") or []),
            )
        )
        competitors = _unique_strings(
            competitor
            for entity in entities
            if isinstance(entity, dict)
            for competitor in entity.get("competitors") or []
        )
        source_rows = next(
            (
                list(row.get("sources") or [])
                for row in excerpts
                if isinstance(row, dict) and _text(row.get("slug")) == slug
            ),
            [],
        )
        faq_questions = list(
            (blueprint.get("faq_requirements") or {}).get("questions") or []
        )
        sections = list(blueprint.get("section_order") or [])
        gaps = list(task_set.get("tasks") or [])
        article_specs.append(
            {
                **blueprint,
                "research_level": task_set.get("research_level"),
                "comparison_status": task_set.get("comparison_status"),
                "writer_role": "write_only",
                "external_research_allowed": False,
            }
        )
        outlines.append(
            {
                "task_id": blueprint.get("task_id"),
                "slug": slug,
                "sections": sections,
            }
        )
        section_guides.append(
            {
                "task_id": blueprint.get("task_id"),
                "slug": slug,
                "sections": [
                    {
                        **section,
                        "gap_policy": (
                            "Write a reader-facing Research Gap note and do not invent details."
                            if any(
                                _text(gap.get("section")).casefold()
                                == _text(section.get("heading")).casefold()
                                for gap in gaps
                                if isinstance(gap, dict)
                            )
                            else "Use only the assigned verified claim IDs."
                        ),
                    }
                    for section in sections
                    if isinstance(section, dict)
                ],
            }
        )
        faq_sets.append(
            {
                "task_id": blueprint.get("task_id"),
                "slug": slug,
                "questions": faq_questions,
                "answer_policy": "Answer only when FACT_LEDGER.json supports the answer.",
            }
        )
        terminology_sets.append(
            {
                "task_id": blueprint.get("task_id"),
                "slug": slug,
                "preferred_terms": entity_names,
                "forbidden_inventions": [
                    "Unverified product, plan, feature, integration, certification, or benchmark names."
                ],
            }
        )
        competitor_notes.append(
            {
                "task_id": blueprint.get("task_id"),
                "slug": slug,
                "status": task_set.get("comparison_status") or "NOT_APPLICABLE",
                "verified_competitors": competitors,
                "instruction": (
                    "Do not write direct comparisons or rankings."
                    if task_set.get("comparison_status") == "HELD_WAITING_COMPARATORS"
                    else "Use only competitor claims supplied in FACT_LEDGER.json."
                ),
            }
        )
        image_guides.append(
            {
                "task_id": blueprint.get("task_id"),
                "slug": slug,
                "suggestions": list(
                    research.get("image_suggestions")
                    or research.get("visual_suggestions")
                    or task.get("image_suggestions")
                    or []
                ),
                "screenshot_metadata": list(
                    research.get("screenshots_metadata")
                    or research.get("screenshot_metadata")
                    or []
                ),
                "policy": "Do not invent screenshots, image URLs, or visual test results.",
            }
        )
        internal_link_sets.append(
            {
                "task_id": blueprint.get("task_id"),
                "slug": slug,
                "links": list(blueprint.get("required_internal_links") or []),
            }
        )
        external_link_sets.append(
            {
                "task_id": blueprint.get("task_id"),
                "slug": slug,
                "links": [
                    {
                        "url": row.get("url"),
                        "title": row.get("title"),
                        "allowed_usage": row.get("allowed_usage"),
                    }
                    for row in source_rows
                    if isinstance(row, dict) and _text(row.get("url"))
                ],
            }
        )
        schema_sets.append(
            {
                "task_id": blueprint.get("task_id"),
                "slug": slug,
                "required_types": [
                    "Article",
                    *(["FAQPage"] if faq_questions else []),
                ],
                "canonical_url": f"https://smileaireviewhub.com/{slug}/",
                "policy": "Use only metadata and claims supplied in this package.",
            }
        )
        research_gaps.append(
            {
                "task_id": blueprint.get("task_id"),
                "slug": slug,
                "research_level": task_set.get("research_level"),
                "comparison_status": task_set.get("comparison_status"),
                "known_uncertainties": list(task_set.get("known_uncertainties") or []),
                "weak_sections": list(task_set.get("weak_sections") or []),
                "tasks": gaps,
            }
        )
        writer_checklists.append(
            {
                "task_id": blueprint.get("task_id"),
                "slug": slug,
                "checks": [
                    "Read only this package; do not search, crawl, verify, or browse.",
                    "Use only claims from FACT_LEDGER.json or VERIFIED_CLAIMS.json.",
                    *(
                        [
                            "Consume FACT_LEDGER.json, SOURCE_EXCERPTS.json, sources.json, outline.json, writing_plan.json, faq.json, competitor_analysis.json, entities.json, and research_inventory.json.",
                            "Write the complete 2,200-2,600-word article; do not stop after outline generation.",
                            "Run self-review for duplicate risk, section completeness, entity coverage, citation coverage, CTA, disclosure, links, FAQ, and JSON-LD.",
                            "Regenerate automatically on any failed check or predicted AI score below 70, up to three total attempts.",
                        ]
                        if task_type == "WEBSITE_ADVANCED"
                        else []
                    ),
                    "Write Research Gap when a required detail is unavailable.",
                    "Create article.md, article.html, metadata.json, and validation.json.",
                    "Keep task ID, slug, revision, canonical URL, and package ID unchanged.",
                    "Do not approve, publish, deploy, push, or submit indexing.",
                ],
            }
        )

    _write_json(
        package_dir / "ARTICLE_SPEC.json",
        {"schema_version": VERIFIED_PACKAGE_SCHEMA, "articles": article_specs},
    )
    _write_json(
        package_dir / "OUTLINE.json",
        {"schema_version": VERIFIED_PACKAGE_SCHEMA, "articles": outlines},
    )
    _write_json(
        package_dir / "VERIFIED_CLAIMS.json",
        {"schema_version": VERIFIED_PACKAGE_SCHEMA, "articles": ledgers},
    )
    _write_json(
        package_dir / "SECTION_GUIDE.json",
        {"schema_version": VERIFIED_PACKAGE_SCHEMA, "articles": section_guides},
    )
    _write_json(
        package_dir / "FAQ.json",
        {"schema_version": VERIFIED_PACKAGE_SCHEMA, "articles": faq_sets},
    )
    _write_json(
        package_dir / "TERMINOLOGY.json",
        {"schema_version": VERIFIED_PACKAGE_SCHEMA, "articles": terminology_sets},
    )
    _write_json(
        package_dir / "COMPETITOR_NOTES.json",
        {"schema_version": VERIFIED_PACKAGE_SCHEMA, "articles": competitor_notes},
    )
    _write_json(
        package_dir / "IMAGE_GUIDE.json",
        {"schema_version": VERIFIED_PACKAGE_SCHEMA, "articles": image_guides},
    )
    _write_json(
        package_dir / "INTERNAL_LINKS.json",
        {"schema_version": VERIFIED_PACKAGE_SCHEMA, "articles": internal_link_sets},
    )
    _write_json(
        package_dir / "EXTERNAL_LINKS.json",
        {"schema_version": VERIFIED_PACKAGE_SCHEMA, "articles": external_link_sets},
    )
    _write_json(
        package_dir / "SCHEMA.json",
        {"schema_version": VERIFIED_PACKAGE_SCHEMA, "articles": schema_sets},
    )
    _write_json(
        package_dir / "RESEARCH_GAPS.json",
        {"schema_version": VERIFIED_PACKAGE_SCHEMA, "articles": research_gaps},
    )
    _write_json(
        package_dir / "WRITER_CHECKLIST.json",
        {"schema_version": VERIFIED_PACKAGE_SCHEMA, "articles": writer_checklists},
    )
    _write_json(
        package_dir / "EDITORIAL_RULES.json",
        {
            "schema_version": VERIFIED_PACKAGE_SCHEMA,
            "writer_role": "write_only",
            "external_research_allowed": False,
            "research_gap_wording": "Research Gap",
            "rules": [
                "Never search, crawl, browse, verify, or add facts outside this package.",
                "Never invent facts, sources, URLs, prices, features, integrations, or competitors.",
                "Do not approve, publish, commit, push, deploy, or submit indexing.",
            ],
        },
    )

    guidance = {
        "WRITING_DNA.md": root / "WRITING_DNA.md",
        "STRUCTURE_DNA.md": root / "STRUCTURE_DNA.md",
        "VOICE_DNA.md": root / "VOICE_DNA.md",
        "SELF_REVIEW.md": root / "SELF_VALIDATION_ENGINE.md",
        "QUALITY_SCORE.md": root / "QUALITY_SCORE_ENGINE.md",
    }
    fallback_guidance = {
        "WRITING_DNA.md": (
            "# Writing DNA\n\nWrite for the reader's decision, not for search-engine filler. "
            "Use short paragraphs, practical examples, source-aware claims, clear caveats, "
            "and a skeptical affiliate voice. Never invent prices, features, integrations, "
            "benchmarks, awards, experience, or URLs. Every section must add new information."
        ),
        "STRUCTURE_DNA.md": (
            "# Structure DNA\n\nFollow ARTICLE_BLUEPRINT.json exactly. Use one H1, then the "
            "declared H2 order and purpose. Include required tables, FAQ, CTA, internal links, "
            "final recommendation, metadata, canonical URL, disclosure, and schema only when "
            "the output contract requires them. Never move pricing ahead of its assigned section."
        ),
        "VOICE_DNA.md": (
            "# Voice DNA\n\nUse a practical, calm, skeptical, source-aware editorial voice. "
            "Prefer plain sentences and direct transitions. Avoid hype, pressure, generic SEO "
            "introductions, repeated conclusions, and claims of first-hand testing unless supplied."
        ),
        "SELF_REVIEW.md": (
            "# Self Review\n\nTrace every factual statement to FACT_LEDGER.json. Verify title, "
            "H1, metadata, canonical, structure, tables, FAQ, CTA, links, disclosure, UTF-8, "
            "public safety, unique paragraphs, and absence of placeholders or workflow markers."
        ),
        "QUALITY_SCORE.md": (
            "# Quality Score\n\nScore structure 15, SEO 10, readability 15, trust 15, public "
            "safety 10, blueprint consistency 10, style 10, links 5, and research 10. A reviewable "
            "draft needs 70+ and no hard blocker. Unsupported facts or entity mismatch score zero."
        ),
    }
    for target, source in guidance.items():
        text = (
            source.read_text(encoding="utf-8")
            if source.is_file()
            else fallback_guidance[target]
        )
        (package_dir / target).write_text(text, encoding="utf-8", newline="\n")

    public_output_validation = public_output_validation_contract()
    validation_rules = {
        "schema_version": VERIFIED_PACKAGE_SCHEMA,
        "validator_scope": [
            "required files and paths",
            "UTF-8, JSON, Markdown, HTML, metadata, and schema structure",
            "citation identifiers and URLs exist in the supplied package",
            "public-output safety and immutable identifiers",
        ],
        "research_revalidation": False,
        "hard_fail": {
            "missing_required_output": True,
            "unsupported_factual_claim": False,
            "unknown_url": True,
            "internal_workflow_marker": True,
            "placeholder_token": True,
            "wrong_slug_or_task_id": True,
        },
        "claim_policy": {
            "allowed_claim_ids_only": True,
            "facts_source": "FACT_LEDGER.json",
            "source_context": "SOURCE_EXCERPTS.json",
            "minimum_publishable_claims_per_article": 0,
            "maximum_publishable_claims_per_article": MAX_PUBLISHABLE_FACTS,
            "source_excerpts_are_complete": False,
            "external_web_revisit_allowed": False,
        },
        "content_rules": {
            "follow_blueprint_order": True,
            "answer_every_required_faq": True,
            "include_every_required_table": True,
            "human_approval_required": True,
            "content_gaps_create_revision_tasks": True,
        },
        "public_output_validation": public_output_validation,
    }
    _write_json(package_dir / "VALIDATION_RULES.json", validation_rules)
    _write_json(
        package_dir / "PUBLIC_OUTPUT_VALIDATION.json",
        public_output_validation,
    )
    _write_json(
        package_dir / "OUTPUT_SCHEMA.json",
        {
            "schema_version": VERIFIED_PACKAGE_SCHEMA,
            "return_filename": "completed_drafts.zip",
            "manifest": output_contract,
            "article_outputs": {
                row["task_id"]: row["target_output_paths"] for row in tasks
            },
            "required_contract_copy": "verified_package_contract.json",
        },
    )
    _write_json(package_dir / "OUTPUT_CONTRACT.json", output_contract)

    contract = {
        "schema_version": CONTRACT_SCHEMA,
        "agent_pipeline_version": 2,
        "package_schema": VERIFIED_PACKAGE_SCHEMA,
        "package_id": package_id,
        "task_type": task_type,
        "batch_date": batch_date,
        "tasks": contract_tasks,
        "article_specs": article_specs,
        "output_contract": output_contract,
        "website_writing_contract": website_contract or {},
        "validation_rules": validation_rules,
    }
    _write_json(package_dir / "verified_package_contract.json", contract)
    _write_golden_example(package_dir / "GOLDEN_EXAMPLE")
    return {
        "strict_articles": strict_articles,
        "compatibility_articles": compatibility_articles,
        "contract": contract,
    }


def _write_golden_example(target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    _write_json(
        target / "research.json",
        {
            "source": "https://example.invalid/product",
            "excerpt": "The official product page describes a workflow product.",
            "note": "Demonstration data only; never copy this claim into real articles.",
        },
    )
    _write_json(
        target / "blueprint.json",
        {
            "heading": "Who this product fits",
            "purpose": "Translate supplied evidence into a buyer-fit decision.",
            "required_evidence_claim_ids": ["example-claim-001"],
        },
    )
    (target / "finished_article.md").write_text(
        "# Example product review\n\n"
        "## Who this product fits\n\n"
        "Based on the supplied example excerpt, the product addresses a workflow use case. "
        "The source does not establish pricing or performance, so those claims are omitted.\n",
        encoding="utf-8",
        newline="\n",
    )
    _write_json(
        target / "validation.json",
        {
            "status": "PASS",
            "traceability": {"example-claim-001": "research.json"},
            "unsupported_claims": [],
        },
    )


@dataclass(frozen=True)
class VerificationResult:
    valid: bool
    errors: list[str]
    warnings: list[str]
    article_count: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "errors": self.errors,
            "warnings": self.warnings,
            "article_count": self.article_count,
        }


def validate_verified_package(path: Path) -> VerificationResult:
    source = path.resolve()
    if source.is_file() and source.suffix.lower() == ".zip":
        with tempfile.TemporaryDirectory(prefix="verified-package-") as raw:
            root = Path(raw)
            with zipfile.ZipFile(source) as archive:
                archive.extractall(root)
            return _validate_directory(root)
    return _validate_directory(source)


def _validate_directory(root: Path) -> VerificationResult:
    errors: list[str] = []
    warnings: list[str] = []
    for name in REQUIRED_ROOT_FILES:
        path = root / name
        if not path.is_file() or path.stat().st_size == 0:
            errors.append(f"Missing or empty required file: {name}")
    golden = root / "GOLDEN_EXAMPLE"
    for name in ("research.json", "blueprint.json", "finished_article.md", "validation.json"):
        if not (golden / name).is_file():
            errors.append(f"Missing golden example file: GOLDEN_EXAMPLE/{name}")
    if errors:
        return VerificationResult(False, errors, warnings, 0)

    blueprints = _read_json(root / "ARTICLE_BLUEPRINT.json", {}).get("articles")
    ledgers = _read_json(root / "FACT_LEDGER.json", {}).get("articles")
    excerpts = _read_json(root / "SOURCE_EXCERPTS.json", {}).get("articles")
    profiles = _read_json(root / "ENTITY_PROFILE.json", {}).get("articles")
    contract = _read_json(root / "verified_package_contract.json", {})
    if int(contract.get("agent_pipeline_version") or 0) >= 2:
        for name in AGENT_PIPELINE_V2_FILES:
            path = root / name
            if not path.is_file() or path.stat().st_size == 0:
                errors.append(f"Missing or empty Agent Pipeline V2 file: {name}")
    if not isinstance(blueprints, list) or not blueprints:
        errors.append("ARTICLE_BLUEPRINT.json must contain a non-empty articles list.")
        blueprints = []
    for collection, label in (
        (ledgers, "FACT_LEDGER.json"),
        (excerpts, "SOURCE_EXCERPTS.json"),
        (profiles, "ENTITY_PROFILE.json"),
    ):
        if not isinstance(collection, list) or len(collection) != len(blueprints):
            errors.append(f"{label} must contain one entry per blueprint.")
    if contract.get("schema_version") != CONTRACT_SCHEMA:
        errors.append(f"verified_package_contract.json schema must be {CONTRACT_SCHEMA}.")

    for blueprint in blueprints:
        slug = _text(blueprint.get("slug")) if isinstance(blueprint, dict) else ""
        if not isinstance(blueprint, dict):
            errors.append("Every blueprint must be an object.")
            continue
        optional_empty = {
            "required_tables",
            "next_article_bridge",
            "required_internal_links",
        }
        for field in BLUEPRINT_FIELDS:
            if field not in blueprint or (
                field not in optional_empty and blueprint.get(field) in (None, "", [], {})
            ):
                errors.append(f"{slug or 'unknown'}: incomplete blueprint field {field}.")
        sections = blueprint.get("section_order")
        if isinstance(sections, list):
            for section in sections:
                if not isinstance(section, dict) or not _text(section.get("heading")) or not _text(
                    section.get("purpose")
                ):
                    errors.append(f"{slug}: every section requires heading and purpose.")

    contract_tasks = contract.get("tasks", [])
    sources_by_slug: dict[str, dict[str, list[str]]] = {}
    for article in excerpts if isinstance(excerpts, list) else []:
        if not isinstance(article, dict):
            continue
        slug = _text(article.get("slug"))
        source_map: dict[str, list[str]] = {}
        for source in article.get("sources") or []:
            if not isinstance(source, dict):
                continue
            url = _text(source.get("url"))
            paragraphs = source.get("extracted_relevant_paragraphs") or []
            source_map[url] = [_text(value) for value in paragraphs if _text(value)]
        sources_by_slug[slug] = source_map

    for ledger in ledgers if isinstance(ledgers, list) else []:
        slug = _text(ledger.get("slug"))
        facts = ledger.get("facts")
        if not isinstance(facts, list) or not facts:
            warnings.append(
                f"{slug}: fact ledger has no publishable claims; writer must use a Research Gap."
            )
            continue
        for fact in facts:
            for field in FACT_FIELDS:
                if not isinstance(fact, dict) or fact.get(field) in (None, ""):
                    warnings.append(f"{slug}: incomplete fact field {field}.")
            if not isinstance(fact, dict):
                continue
            source_url = _text(fact.get("source_url"))
            excerpt = _text(fact.get("supporting_excerpt"))
            if any(marker in excerpt.casefold() for marker in NON_EVIDENCE_MARKERS):
                warnings.append(
                    f"{slug}: fact {fact.get('claim_id')} uses non-evidence placeholder text."
                )
            source_paragraphs = sources_by_slug.get(slug, {}).get(source_url, [])
            if source_url not in sources_by_slug.get(slug, {}):
                warnings.append(
                    f"{slug}: fact {fact.get('claim_id')} references an unknown source URL."
                )
            elif not any(excerpt in paragraph for paragraph in source_paragraphs):
                warnings.append(
                    f"{slug}: fact {fact.get('claim_id')} excerpt is not present in SOURCE_EXCERPTS.json."
                )

    for article in excerpts if isinstance(excerpts, list) else []:
        slug = _text(article.get("slug"))
        sources = article.get("sources")
        if not isinstance(sources, list) or not sources:
            errors.append(f"{slug}: no official source exists in the research package.")
            continue
        for source in sources:
            for field in SOURCE_FIELDS:
                if field in {"author", "publication", "publication_date"}:
                    continue
                if not isinstance(source, dict) or source.get(field) in (None, "", []):
                    if field == "url":
                        errors.append(f"{slug}: official source URL is missing.")
                    else:
                        warnings.append(f"{slug}: incomplete source field {field}.")
            if not isinstance(source, dict):
                continue
            for paragraph in source.get("extracted_relevant_paragraphs") or []:
                if any(marker in _text(paragraph).casefold() for marker in NON_EVIDENCE_MARKERS):
                    warnings.append(
                        f"{slug}: source excerpts contain non-evidence placeholder text."
                    )

    for name in (
        "WRITING_DNA.md",
        "STRUCTURE_DNA.md",
        "VOICE_DNA.md",
        "SELF_REVIEW.md",
        "QUALITY_SCORE.md",
    ):
        if len((root / name).read_text(encoding="utf-8").strip()) < 40:
            errors.append(f"{name} does not contain the full rules.")

    output_schema = _read_json(root / "OUTPUT_SCHEMA.json", {})
    if output_schema.get("return_filename") != "completed_drafts.zip":
        errors.append("OUTPUT_SCHEMA.json must require completed_drafts.zip.")
    if not isinstance(output_schema.get("article_outputs"), dict):
        errors.append("OUTPUT_SCHEMA.json article_outputs must be an object.")
    if re.search(r"\b(ChatGPT|Claude|Gemini|DeepSeek)\b", (root / "START_HERE.txt").read_text(encoding="utf-8")):
        errors.append("START_HERE.txt must remain model-neutral.")
    return VerificationResult(not errors, errors, warnings, len(blueprints))
