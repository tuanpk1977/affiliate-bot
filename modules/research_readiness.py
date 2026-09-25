from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


RESEARCH_LEVELS = (
    "BLOCKED_RESEARCH",
    "RESEARCH_MINIMUM",
    "RESEARCH_GOOD",
    "RESEARCH_STRONG",
    "RESEARCH_COMPLETE",
)
EXPORTABLE_RESEARCH_LEVELS = {
    "RESEARCH_MINIMUM",
    "RESEARCH_GOOD",
    "RESEARCH_STRONG",
    "RESEARCH_COMPLETE",
    "ARTICLE_READY",
}
HARD_STOP_STATES = {
    "BLOCKED_SAFETY",
    "NO_OFFICIAL_SOURCES",
    "ENTITY_COLLISION",
    "FALSE_CLAIM",
    "LEGAL_RISK",
    "COPYRIGHT_RISK",
    "SPAM_RISK",
    "UNSAFE_CONTENT",
    "MALICIOUS_CONTENT",
}


def applicable_source_score_thresholds(
    gate_config: dict[str, Any],
    *,
    article_type: str = "",
    task: dict[str, Any] | None = None,
    claim_categories: set[str] | None = None,
) -> dict[str, float]:
    """Return unchanged source-score thresholds that apply to this article.

    Total verified evidence and first-party evidence are universal. Pricing and
    affiliate evidence are conditional because a page that makes neither kind
    of claim cannot honestly acquire evidence for those claims. This selects
    gates; it never lowers their configured numeric thresholds.
    """
    if not bool(gate_config.get("enabled", True)):
        return {}
    task = task if isinstance(task, dict) else {}
    categories = {str(value or "").strip().casefold() for value in (claim_categories or set())}
    task_text = " ".join(
        str(task.get(key) or "")
        for key in (
            "daily_angle",
            "article_type",
            "content_type",
            "title",
            "search_intent",
            "unique_thesis",
            "affiliate_destination",
            "affiliate_cta",
        )
    ).casefold()
    kind = str(article_type or "").casefold()
    pricing_required = bool(
        categories & {"pricing", "price", "cost", "roi"}
        or any(marker in task_text for marker in ("pricing", "price", "cost", " roi "))
        or kind in {"pricing", "pricing_page"}
    )
    affiliate_required = bool(
        task.get("affiliate_claim_required") is True
        or categories & {"affiliate", "commission", "affiliate_program"}
        or any(marker in task_text for marker in ("affiliate", "commission", "partner program"))
    )
    thresholds = {
        "total_verified_source_score": float(gate_config.get("minimum_total_score", 35)),
        "official_docs_score": float(gate_config.get("minimum_official_docs_score", 20)),
    }
    if pricing_required:
        thresholds["pricing_source_score"] = float(
            gate_config.get("minimum_pricing_source_score", 20)
        )
    if affiliate_required:
        thresholds["affiliate_source_score"] = float(
            gate_config.get("minimum_affiliate_source_score", 10)
        )
    return thresholds


def effective_entity_status(
    *,
    resolver_status: str,
    comparison_plan: bool,
    entity_mismatches: list[Any] | tuple[Any, ...] | None,
) -> str:
    """Avoid reintroducing a generic resolver collision after plan validation."""
    status = str(resolver_status or "").strip()
    if (
        comparison_plan
        and not list(entity_mismatches or [])
        and status.upper() in {"AMBIGUOUS", "ENTITY_MISMATCH", "ENTITY_COLLISION"}
    ):
        return "RESOLVED_COMPARISON_PLAN"
    return status


@dataclass(frozen=True)
class ResearchReadiness:
    level: str
    draft_exportable: bool
    critical_safety_violations: tuple[str, ...] = ()
    research_tasks: tuple[dict[str, Any], ...] = ()
    known_uncertainties: tuple[str, ...] = ()
    weak_sections: tuple[str, ...] = ()
    comparison_status: str = "NOT_APPLICABLE"
    estimated_publish_readiness: float = 0.0
    reasons: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "research_level": self.level,
            "draft_exportable": self.draft_exportable,
            "critical_safety_violations": list(self.critical_safety_violations),
            "research_tasks": list(self.research_tasks),
            "known_uncertainties": list(self.known_uncertainties),
            "weak_sections": list(self.weak_sections),
            "comparison_status": self.comparison_status,
            "estimated_publish_readiness": self.estimated_publish_readiness,
            "readiness_reasons": list(self.reasons),
        }


def normalize_research_level(value: Any, *, article_ready: bool = False) -> str:
    normalized = str(value or "").strip().upper()
    if article_ready or normalized == "ARTICLE_READY":
        return "RESEARCH_COMPLETE"
    if normalized in RESEARCH_LEVELS:
        return normalized
    return "BLOCKED_RESEARCH"


def is_draft_exportable(value: Any, *, article_ready: bool = False) -> bool:
    return (
        normalize_research_level(value, article_ready=article_ready)
        in EXPORTABLE_RESEARCH_LEVELS
    )


def classify_research_readiness(
    *,
    approved_source_count: int,
    paragraph_count: int,
    claim_count: int,
    expected_claim_count: int,
    coverage_score: float,
    article_complete: bool,
    blockers: list[str],
    gaps: list[dict[str, Any]],
    weak_sections: list[str],
    entity_status: str = "",
    comparison_required: bool = False,
    verified_comparator_count: int = 0,
    validation_error_count: int = 0,
) -> ResearchReadiness:
    critical: list[str] = []
    normalized_entity_status = str(entity_status or "").strip().upper()
    joined_blockers = " ".join(str(row) for row in blockers).casefold()

    if approved_source_count <= 0:
        critical.append("NO_OFFICIAL_SOURCES")
    if normalized_entity_status in {"AMBIGUOUS", "ENTITY_MISMATCH", "ENTITY_COLLISION"}:
        critical.append("ENTITY_COLLISION")
    if "legal risk" in joined_blockers:
        critical.append("LEGAL_RISK")
    if "copyright" in joined_blockers:
        critical.append("COPYRIGHT_RISK")
    if "spam" in joined_blockers:
        critical.append("SPAM_RISK")
    if "unsafe" in joined_blockers:
        critical.append("UNSAFE_CONTENT")
    if any(
        marker in joined_blockers
        for marker in ("false claim", "fake claim", "fabricated claim")
    ):
        critical.append("FALSE_CLAIM")
    if "malicious content" in joined_blockers:
        critical.append("MALICIOUS_CONTENT")
    if "prohibited overlap" in joined_blockers:
        critical.append("BLOCKED_SAFETY")

    tasks = build_research_tasks(
        blockers=blockers,
        gaps=gaps,
        comparison_required=comparison_required,
        verified_comparator_count=verified_comparator_count,
    )
    comparison_status = (
        "HELD_WAITING_COMPARATORS"
        if comparison_required and verified_comparator_count < 2
        else "VERIFIED"
        if comparison_required
        else "NOT_APPLICABLE"
    )
    if critical:
        return ResearchReadiness(
            level=critical[0],
            draft_exportable=False,
            critical_safety_violations=tuple(dict.fromkeys(critical)),
            research_tasks=tuple(tasks),
            known_uncertainties=tuple(_uncertainties(tasks)),
            weak_sections=tuple(dict.fromkeys(weak_sections)),
            comparison_status=comparison_status,
            estimated_publish_readiness=0.0,
            reasons=("Critical evidence or entity safety requirement failed.",),
        )

    expected = max(1, int(expected_claim_count or 1))
    claim_ratio = min(1.0, claim_count / expected)
    if comparison_status == "HELD_WAITING_COMPARATORS":
        level = "RESEARCH_MINIMUM"
    elif article_complete:
        level = "RESEARCH_COMPLETE"
    elif coverage_score >= 0.80 and claim_ratio >= 0.85:
        level = "RESEARCH_STRONG"
    elif coverage_score >= 0.60 and claim_ratio >= 0.55:
        level = "RESEARCH_GOOD"
    else:
        level = "RESEARCH_MINIMUM"
    estimate = min(
        0.99 if level != "RESEARCH_COMPLETE" else 1.0,
        max(0.50, (coverage_score * 0.65) + (claim_ratio * 0.35)),
    )
    return ResearchReadiness(
        level=level,
        draft_exportable=True,
        research_tasks=tuple(tasks),
        known_uncertainties=tuple(_uncertainties(tasks)),
        weak_sections=tuple(dict.fromkeys(weak_sections)),
        comparison_status=comparison_status,
        estimated_publish_readiness=round(estimate, 4),
        reasons=(
            "Enough verified evidence exists for a constrained first draft.",
            "Non-critical gaps must be resolved before final approval.",
        ),
    )


def build_research_tasks(
    *,
    blockers: list[str],
    gaps: list[dict[str, Any]],
    comparison_required: bool,
    verified_comparator_count: int,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for gap in gaps:
        if not isinstance(gap, dict):
            continue
        section = str(
            gap.get("section_id") or gap.get("section") or gap.get("gap_type") or "general"
        ).strip()
        reason = str(
            gap.get("reason")
            or gap.get("description")
            or gap.get("gap")
            or f"Evidence is incomplete for {section}."
        ).strip()
        task_type = _task_type(section + " " + reason)
        if (
            comparison_required
            and verified_comparator_count < 2
            and task_type == "MISSING_COMPARATOR"
        ):
            continue
        key = (task_type, section.casefold())
        if key in seen:
            continue
        seen.add(key)
        rows.append(
            {
                "task_id": f"research-{len(rows) + 1:03d}",
                "task_type": task_type,
                "section": section,
                "status": "PENDING",
                "severity": "non_critical",
                "blocks_first_draft": False,
                "reason": reason,
                "recommended_source_families": list(
                    gap.get("recommended_source_families") or []
                ),
                "recommended_wording": _wording(task_type),
            }
        )
    for blocker in blockers:
        reason = str(blocker or "").strip()
        if not reason:
            continue
        task_type = _task_type(reason)
        if (
            comparison_required
            and verified_comparator_count < 2
            and task_type == "MISSING_COMPARATOR"
        ):
            continue
        section = _section(task_type)
        key = (task_type, reason.casefold())
        if key in seen:
            continue
        seen.add(key)
        rows.append(
            {
                "task_id": f"research-{len(rows) + 1:03d}",
                "task_type": task_type,
                "section": section,
                "status": "PENDING",
                "severity": "non_critical",
                "blocks_first_draft": False,
                "reason": reason,
                "recommended_source_families": [],
                "recommended_wording": _wording(task_type),
            }
        )
    if comparison_required and verified_comparator_count < 2:
        rows.insert(
            0,
            {
                "task_id": "research-comparators",
                "task_type": "MISSING_COMPARATOR",
                "section": "comparison",
                "status": "HELD_WAITING_COMPARATORS",
                "severity": "non_critical",
                "blocks_first_draft": False,
                "reason": (
                    f"Comparison requires 2 verified comparators; "
                    f"{verified_comparator_count} currently verified."
                ),
                "recommended_source_families": [
                    "official_docs",
                    "product_page",
                    "integration_page",
                ],
                "recommended_wording": (
                    "Omit rankings and direct comparisons until comparator evidence is verified."
                ),
            },
        )
    return rows


def revision_tasks_from_validation(
    validation_report: dict[str, Any],
    *,
    task_id: str,
    slug: str,
    revision: int,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    raw_items: list[tuple[str, Any]] = []
    for key in (
        "unsupported_claims",
        "missing_citations",
        "missing_sections",
        "weak_sections",
        "missing_pricing",
        "missing_security",
        "missing_integrations",
        "missing_comparison",
        "missing_faq",
        "missing_tables",
        "warnings",
        "errors",
        "revision_tasks",
    ):
        value = validation_report.get(key)
        if isinstance(value, list):
            raw_items.extend((key, item) for item in value)
    status = str(validation_report.get("status") or "").strip().upper()
    if status not in {"PASS", "PASSED"} and not raw_items:
        raw_items.append(
            (
                "validation_status",
                validation_report.get("reason")
                or "The external writer validation report requires editorial revision.",
            )
        )
    key_types = {
        "unsupported_claims": "UNSUPPORTED_CLAIM",
        "missing_citations": "MISSING_CITATION",
        "missing_sections": "WEAK_SECTION",
        "weak_sections": "WEAK_SECTION",
        "missing_pricing": "MISSING_PRICING",
        "missing_security": "MISSING_SECURITY",
        "missing_integrations": "MISSING_INTEGRATION",
        "missing_comparison": "MISSING_COMPARATOR",
        "missing_faq": "WEAK_SECTION",
        "missing_tables": "WEAK_SECTION",
    }
    for index, (source_key, item) in enumerate(raw_items, start=1):
        if isinstance(item, dict):
            reason = str(
                item.get("reason")
                or item.get("message")
                or item.get("claim")
                or item.get("section")
                or "Revision required."
            ).strip()
            section = str(item.get("section") or item.get("section_id") or "general")
            task_type = str(
                item.get("task_type")
                or key_types.get(source_key)
                or _task_type(reason)
            )
        else:
            reason = str(item or "").strip()
            section = _section(_task_type(reason))
            task_type = key_types.get(source_key) or _task_type(reason)
        if not reason:
            continue
        rows.append(
            {
                "revision_task_id": f"{task_id}-r{revision}-{index:03d}",
                "task_id": task_id,
                "slug": slug,
                "revision": revision,
                "task_type": task_type,
                "section": section,
                "status": "PENDING",
                "reason": reason,
                "research_enrichment_required": task_type
                in {
                    "UNSUPPORTED_CLAIM",
                    "MISSING_CITATION",
                    "MISSING_PRICING",
                    "MISSING_COMPARATOR",
                    "MISSING_SECURITY",
                    "MISSING_INTEGRATION",
                },
            }
        )
    return rows


def _task_type(value: str) -> str:
    normalized = str(value or "").casefold()
    if "comparator" in normalized or "alternative" in normalized or "comparison" in normalized:
        return "MISSING_COMPARATOR"
    if "pricing" in normalized or "price" in normalized:
        return "MISSING_PRICING"
    if "security" in normalized:
        return "MISSING_SECURITY"
    if "integration" in normalized:
        return "MISSING_INTEGRATION"
    if "citation" in normalized or "source" in normalized:
        return "MISSING_CITATION"
    if "unsupported" in normalized or "hallucinat" in normalized:
        return "UNSUPPORTED_CLAIM"
    if "section" in normalized or "coverage" in normalized:
        return "WEAK_SECTION"
    return "EVIDENCE_GAP"


def _section(task_type: str) -> str:
    return {
        "MISSING_COMPARATOR": "comparison",
        "MISSING_PRICING": "pricing",
        "MISSING_SECURITY": "security",
        "MISSING_INTEGRATION": "integrations",
        "MISSING_CITATION": "citations",
    }.get(task_type, "general")


def _wording(task_type: str) -> str:
    return {
        "MISSING_COMPARATOR": "Omit direct rankings and state that alternatives require verification.",
        "MISSING_PRICING": "Do not state a price; direct readers to the current official pricing page.",
        "MISSING_SECURITY": "Do not claim compliance, certification, or security guarantees.",
        "MISSING_INTEGRATION": "Do not claim an integration unless the official source confirms it.",
        "MISSING_CITATION": "Omit the claim until an approved source and excerpt are available.",
        "UNSUPPORTED_CLAIM": "Remove or rewrite the claim using only the supplied fact ledger.",
    }.get(task_type, "Use cautious wording and do not infer facts beyond supplied evidence.")


def _uncertainties(tasks: list[dict[str, Any]]) -> list[str]:
    return list(
        dict.fromkeys(
            str(row.get("reason") or "").strip()
            for row in tasks
            if str(row.get("reason") or "").strip()
        )
    )
