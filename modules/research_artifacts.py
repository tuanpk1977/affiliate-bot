from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
from typing import Any

from modules.research_readiness import (
    applicable_source_score_thresholds,
    is_draft_exportable,
    normalize_research_level,
)
from modules.source_classification import classify_source, source_status


REQUIRED_EVIDENCE_FILES = (
    "SOURCE_EXCERPTS.json",
    "FACT_LEDGER.json",
    "ARTICLE_BLUEPRINT.json",
    "evidence_coverage.json",
    "enrichment_report.json",
)
ADVANCED_EVIDENCE_FILES = (
    "ANGLE_RESEARCH_PLAN.json",
    "claim_extraction_diagnostics.json",
)


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return default


def _schema_version(payload: Any) -> int:
    if not isinstance(payload, dict):
        return 0
    try:
        return int(payload.get("schema_version") or 0)
    except (TypeError, ValueError):
        return 0


@dataclass(frozen=True)
class ResearchArtifactResolution:
    task_id: str
    slug: str
    batch_date: str
    canonical_dir: Path
    package_file: Path
    enrichment_report_file: Path
    source_excerpts_file: Path
    fact_ledger_file: Path
    article_blueprint_file: Path
    evidence_coverage_file: Path
    angle_research_plan_file: Path
    claim_extraction_diagnostics_file: Path
    duplicate_dirs: tuple[Path, ...] = ()
    slug_aliases: tuple[str, ...] = ()
    missing_files: tuple[str, ...] = ()
    legacy_reasons: tuple[str, ...] = ()
    paragraph_count: int = 0
    claim_count: int = 0
    coverage_score: float = 0.0
    angle_profile: str = ""
    required_entity_count: int = 0
    resolved_entity_count: int = 0
    entity_coverage_score: float = 0.0
    candidate_claim_count: int = 0
    rejected_claim_count: int = 0
    mandatory_sections_covered: int = 0
    mandatory_sections_total: int = 0
    status: str = "MISSING_RESEARCH"
    article_ready: bool = False
    research_level: str = "BLOCKED_RESEARCH"
    draft_exportable: bool = False
    critical_safety_violations: tuple[str, ...] = ()
    outstanding_research_tasks: int = 0
    weak_sections: tuple[str, ...] = ()
    comparison_status: str = "NOT_APPLICABLE"
    estimated_publish_readiness: float = 0.0
    revision_count: int = 0
    total_source_count: int = 0
    official_source_count: int = 0
    verified_source_count: int = 0
    source_families: tuple[str, ...] = ()
    source_quality_score: float | None = None
    failing_gates: tuple[str, ...] = ()

    @property
    def is_legacy(self) -> bool:
        return bool(self.legacy_reasons)

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        for key in (
            "canonical_dir",
            "package_file",
            "enrichment_report_file",
            "source_excerpts_file",
            "fact_ledger_file",
            "article_blueprint_file",
            "evidence_coverage_file",
            "angle_research_plan_file",
            "claim_extraction_diagnostics_file",
        ):
            payload[key] = str(payload[key])
        payload["duplicate_dirs"] = [str(path) for path in self.duplicate_dirs]
        payload["is_legacy"] = self.is_legacy
        return payload


def resolve_research_artifacts(
    root: Path,
    *,
    task_id: str,
    slug: str,
    batch_date: str = "",
) -> ResearchArtifactResolution:
    """Resolve one canonical research directory without mutating repository state."""
    root = root.resolve()
    data_dir = root / "data"
    research_root = data_dir / "research"
    canonical_dir = research_root / slug
    aliases: list[str] = []
    candidates = [
        research_root / task_id,
        research_root / batch_date / slug if batch_date else None,
        research_root / "tasks" / task_id,
        data_dir / "research_packages" / batch_date / slug if batch_date else None,
    ]
    duplicate_dirs: list[Path] = []
    for candidate in candidates:
        if candidate is None or candidate == canonical_dir or not candidate.is_dir():
            continue
        duplicate_dirs.append(candidate)
        if candidate.name != slug:
            aliases.append(candidate.name)

    package_file = canonical_dir / "package.json"
    report_file = canonical_dir / "enrichment_report.json"
    excerpts_file = canonical_dir / "SOURCE_EXCERPTS.json"
    ledger_file = canonical_dir / "FACT_LEDGER.json"
    blueprint_file = canonical_dir / "ARTICLE_BLUEPRINT.json"
    coverage_file = canonical_dir / "evidence_coverage.json"
    angle_plan_file = canonical_dir / "ANGLE_RESEARCH_PLAN.json"
    extraction_diagnostics_file = canonical_dir / "claim_extraction_diagnostics.json"

    missing = [
        name for name in REQUIRED_EVIDENCE_FILES if not (canonical_dir / name).is_file()
    ]
    excerpts = _read_json(excerpts_file, {})
    ledger = _read_json(ledger_file, {})
    coverage = _read_json(coverage_file, {})
    report = _read_json(report_file, {})
    quality = _read_json(canonical_dir / "research_quality.json", {})
    inventory = _read_json(canonical_dir / "source_inventory.json", {})
    source_registry = _read_json(canonical_dir / "sources.json", {})
    angle_plan = _read_json(angle_plan_file, {})
    extraction_diagnostics = _read_json(extraction_diagnostics_file, {})
    angle_contract = report.get("angle_contract") if isinstance(report, dict) else {}
    is_advanced = bool(
        angle_plan_file.is_file()
        or (isinstance(angle_contract, dict) and angle_contract.get("daily_angle"))
    )
    if is_advanced:
        missing.extend(
            name
            for name in ADVANCED_EVIDENCE_FILES
            if not (canonical_dir / name).is_file()
        )

    sources = excerpts.get("sources", []) if isinstance(excerpts, dict) else []
    paragraph_count = 0
    empty_excerpt_sources = 0
    for source in sources if isinstance(sources, list) else []:
        if not isinstance(source, dict):
            continue
        paragraphs = source.get("extracted_relevant_paragraphs")
        if not isinstance(paragraphs, list) or not any(str(row).strip() for row in paragraphs):
            empty_excerpt_sources += 1
            continue
        paragraph_count += sum(1 for row in paragraphs if str(row).strip())
    facts = ledger.get("facts", []) if isinstance(ledger, dict) else []
    claim_count = len([row for row in facts if isinstance(row, dict)])

    legacy_reasons: list[str] = []
    package = _read_json(package_file, {})
    if package_file.is_file() and missing:
        legacy_reasons.append("legacy package is missing current evidence artifacts")
    if sources and empty_excerpt_sources:
        legacy_reasons.append("source records contain empty extracted_relevant_paragraphs")
    if ledger_file.is_file() and claim_count == 0:
        legacy_reasons.append("FACT_LEDGER contains zero claims")
    if isinstance(excerpts, dict) and excerpts and _schema_version(excerpts) < 2:
        legacy_reasons.append("SOURCE_EXCERPTS uses an old schema")
    if isinstance(ledger, dict) and ledger and _schema_version(ledger) < 2:
        legacy_reasons.append("FACT_LEDGER uses an old schema")
    if package_file.is_file() and not isinstance(package, dict):
        legacy_reasons.append("package.json is invalid")

    article_ready = bool(
        isinstance(report, dict)
        and report.get("status") == "ARTICLE_READY"
        and report.get("article_ready") is True
        and not missing
        and paragraph_count > 0
        and claim_count > 0
    )
    status = (
        "ARTICLE_READY"
        if article_ready
        else str(report.get("status") or ("LEGACY_RESEARCH" if legacy_reasons else "BLOCKED_RESEARCH"))
    )
    research_level = normalize_research_level(
        report.get("research_level") or status,
        article_ready=article_ready,
    )
    critical_safety_violations = tuple(
        str(row)
        for row in report.get("critical_safety_violations", [])
        if str(row).strip()
    )
    # Menu X trusts the Research Agent's readiness result. Missing optional V2
    # artifacts and incomplete section coverage are follow-up tasks, not a
    # second evidence gate at export time.
    source_rows = (
        inventory.get("sources", [])
        if isinstance(inventory, dict)
        else inventory if isinstance(inventory, list) else []
    )
    source_rows = [row for row in source_rows if isinstance(row, dict)]
    excerpt_rows = excerpts.get("sources", []) if isinstance(excerpts, dict) else []
    excerpt_rows = [row for row in excerpt_rows if isinstance(row, dict)]
    registry_rows: list[dict[str, Any]] = []
    if isinstance(source_registry, dict):
        registry_rows.extend(
            row for row in source_registry.get("verified_sources", [])
            if isinstance(row, dict)
        )
        trusted = source_registry.get("trusted_sources", {})
        if isinstance(trusted, dict):
            registry_rows.extend(
                row
                for rows in trusted.values()
                if isinstance(rows, list)
                for row in rows
                if isinstance(row, dict)
            )
    # Once excerpts exist they are the canonical set of successfully retrieved
    # evidence.  Inventory/registry rows also contain untried candidates and
    # must not inflate Source Review counts or eligibility.
    all_source_rows = excerpt_rows if excerpt_rows else [*source_rows, *registry_rows]
    total_source_count = len(
        {
            str(row.get("canonical_url") or row.get("source_url") or row.get("url") or "").strip()
            for row in all_source_rows
            if str(row.get("canonical_url") or row.get("source_url") or row.get("url") or "").strip()
        }
    )
    entity_names = [
        str(row.get("canonical_name") or "").strip()
        for row in [
            angle_plan.get("root_entity") or {},
            *(angle_plan.get("required_comparator_entities") or []),
        ]
        if isinstance(row, dict) and str(row.get("canonical_name") or "").strip()
    ] if isinstance(angle_plan, dict) else []
    classified_rows = [classify_source(row, entity_names) for row in all_source_rows]
    verified_rows = [
        row for row in classified_rows
        if source_status(row) in {"verified", "approved"}
    ]
    verified_source_count = len({
        str(row.get("canonical_url") or row.get("source_url") or row.get("url") or row.get("source_id") or "").strip()
        for row in verified_rows
        if str(row.get("canonical_url") or row.get("source_url") or row.get("url") or row.get("source_id") or "").strip()
    })
    official_source_count = len({
        str(row.get("canonical_url") or row.get("source_url") or row.get("url") or row.get("source_id") or "").strip()
        for row in verified_rows
        if bool(row.get("official_ownership_verified"))
    })
    if isinstance(quality, dict):
        try:
            verified_source_count = max(verified_source_count, int(quality.get("verified_source_count") or 0))
            official_source_count = max(official_source_count, int(quality.get("official_source_count") or 0))
            if official_source_count == 0 and float(quality.get("official_docs_score") or 0) > 0:
                official_source_count = 1
        except (TypeError, ValueError):
            pass
    source_families = tuple(sorted({
        str(row.get("source_type") or "unknown").strip().casefold()
        for row in verified_rows
    }))
    raw_quality_score = quality.get("total_verified_source_score") if isinstance(quality, dict) else None
    try:
        source_quality_score = float(raw_quality_score) if raw_quality_score is not None else None
    except (TypeError, ValueError):
        source_quality_score = None
    failing_gates: list[str] = []
    # An explicit score from research_quality.json is authoritative.  This is
    # the same hard source gate used by review and publish validation; an old
    # enrichment_report flag must never override it.
    config = _read_json(root / "config" / "editorial_system.json", {})
    source_gate = (
        config.get("research_intelligence", {}).get("verified_source_gate", {})
        if isinstance(config, dict)
        else {}
    )
    claim_rows = ledger.get("claims") if isinstance(ledger, dict) else []
    claim_categories = {
        str(row.get("claim_category") or "").strip().casefold()
        for row in (claim_rows or [])
        if isinstance(row, dict) and str(row.get("claim_category") or "").strip()
    }
    threshold_context = {
        "daily_angle": (angle_contract or {}).get("daily_angle") if isinstance(angle_contract, dict) else "",
        "article_type": report.get("article_type") if isinstance(report, dict) else "",
        "title": report.get("title") if isinstance(report, dict) else "",
        "affiliate_claim_required": bool(
            (angle_contract or {}).get("affiliate_claim_required")
            if isinstance(angle_contract, dict)
            else False
        ),
    }
    thresholds = applicable_source_score_thresholds(
        source_gate,
        article_type=str(threshold_context.get("article_type") or ""),
        task=threshold_context,
        claim_categories=claim_categories,
    )
    gate_labels = {
        "total_verified_source_score": "VERIFIED_SOURCE_SCORE",
        "official_docs_score": "OFFICIAL_DOCS_SCORE",
        "pricing_source_score": "PRICING_SOURCE_SCORE",
        "affiliate_source_score": "AFFILIATE_SOURCE_SCORE",
    }
    for key, threshold in thresholds.items():
        if not isinstance(quality, dict) or key not in quality:
            continue
        try:
            actual = float(quality.get(key) or 0)
        except (TypeError, ValueError):
            actual = 0.0
        if actual < threshold:
            failing_gates.append(f"{gate_labels[key]} {actual:g} below {threshold:g}")
    verified_gate_reported = isinstance(quality, dict) and "verified_source_count" in quality
    if verified_gate_reported and int(quality.get("verified_source_count") or 0) <= 0:
        failing_gates.append("NO_VERIFIED_SOURCES")
    official_gate_reported = isinstance(quality, dict) and (
        "official_docs_score" in quality or "official_source_count" in quality
    )
    if official_gate_reported and official_source_count <= 0:
        failing_gates.append("NO_VERIFIED_OFFICIAL_SOURCE")
    report_blockers = [
        str(row).strip()
        for row in (report.get("blockers") or [])
        if str(row).strip()
    ]
    if not is_draft_exportable(research_level, article_ready=article_ready):
        failing_gates.extend(report_blockers or ["RESEARCH_LEVEL_NOT_EXPORTABLE"])
    draft_exportable = bool(
        is_draft_exportable(research_level, article_ready=article_ready)
        and not critical_safety_violations
        and not failing_gates
    )
    research_tasks = report.get("research_tasks") or []
    weak_sections = tuple(
        str(row)
        for row in report.get("weak_sections", [])
        if str(row).strip()
    )
    try:
        estimated_publish_readiness = float(
            report.get("estimated_publish_readiness") or 0.0
        )
        revision_count = int(report.get("revision_count") or 0)
    except (TypeError, ValueError):
        estimated_publish_readiness = 0.0
        revision_count = 0
    try:
        coverage_score = float(coverage.get("coverage_score") or report.get("coverage_score") or 0)
    except (TypeError, ValueError):
        coverage_score = 0.0
    try:
        mandatory_sections_covered = int(coverage.get("covered") or 0)
        mandatory_sections_total = int(coverage.get("total") or 0)
    except (TypeError, ValueError):
        mandatory_sections_covered = 0
        mandatory_sections_total = 0
    angle_profile = (
        str(angle_plan.get("angle_profile") or report.get("angle_profile") or "")
        if isinstance(angle_plan, dict) and isinstance(report, dict)
        else ""
    )
    entities = []
    if isinstance(angle_plan, dict):
        entities = [
            angle_plan.get("root_entity"),
            *(angle_plan.get("required_comparator_entities") or []),
        ]
    try:
        required_entity_count = int(
            angle_plan.get("required_entity_count") or len(entities)
        )
        resolved_entity_count = int(
            angle_plan.get("resolved_entity_count") or len(entities)
        )
        entity_rows = coverage.get("entity_coverage") or []
        entity_coverage_score = (
            min(float(row.get("coverage_score") or 0) for row in entity_rows)
            if entity_rows
            else 0.0
        )
    except (TypeError, ValueError):
        required_entity_count = len(entities)
        resolved_entity_count = len(entities)
        entity_coverage_score = 0.0
    try:
        candidate_claim_count = int(
            extraction_diagnostics.get("candidate_claims_generated")
            or report.get("candidate_claims")
            or 0
        )
        rejected_claim_count = int(
            extraction_diagnostics.get("candidate_claims_rejected")
            or report.get("rejected_claims")
            or 0
        )
    except (TypeError, ValueError):
        candidate_claim_count = 0
        rejected_claim_count = 0

    return ResearchArtifactResolution(
        task_id=task_id,
        slug=slug,
        batch_date=batch_date,
        canonical_dir=canonical_dir,
        package_file=package_file,
        enrichment_report_file=report_file,
        source_excerpts_file=excerpts_file,
        fact_ledger_file=ledger_file,
        article_blueprint_file=blueprint_file,
        evidence_coverage_file=coverage_file,
        angle_research_plan_file=angle_plan_file,
        claim_extraction_diagnostics_file=extraction_diagnostics_file,
        duplicate_dirs=tuple(duplicate_dirs),
        slug_aliases=tuple(dict.fromkeys(aliases)),
        missing_files=tuple(missing),
        legacy_reasons=tuple(dict.fromkeys(legacy_reasons)),
        paragraph_count=paragraph_count,
        claim_count=claim_count,
        coverage_score=coverage_score,
        angle_profile=angle_profile,
        required_entity_count=required_entity_count,
        resolved_entity_count=resolved_entity_count,
        entity_coverage_score=entity_coverage_score,
        candidate_claim_count=candidate_claim_count,
        rejected_claim_count=rejected_claim_count,
        mandatory_sections_covered=mandatory_sections_covered,
        mandatory_sections_total=mandatory_sections_total,
        status=status,
        article_ready=article_ready,
        research_level=research_level,
        draft_exportable=draft_exportable,
        critical_safety_violations=critical_safety_violations,
        outstanding_research_tasks=len(
            [row for row in research_tasks if isinstance(row, dict)]
        ),
        weak_sections=weak_sections,
        comparison_status=str(
            report.get("comparison_status") or "NOT_APPLICABLE"
        ),
        estimated_publish_readiness=estimated_publish_readiness,
        revision_count=revision_count,
        total_source_count=total_source_count,
        official_source_count=official_source_count,
        verified_source_count=verified_source_count,
        source_families=source_families,
        source_quality_score=source_quality_score,
        failing_gates=tuple(failing_gates),
    )
