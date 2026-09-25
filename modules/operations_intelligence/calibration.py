from __future__ import annotations

import html
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

from .content_gap_engine import ContentGapEngine
from .editorial_memory import EditorialMemoryStore
from .entity_graph import EntityGraphBuilder
from .evergreen_engine import EvergreenEngine
from .graph_validator import EntityGraphQualityGate
from .internal_link_engine import InternalLinkRecommendationEngine
from .inventory import PUBLIC_BASE_URL, article_inventory, internal_slug, read_json
from .quality_engine import EditorialQualityEngine
from .storage import atomic_write_json, atomic_write_text


SCHEMA_VERSION = "phase2_calibration_v1"
HUB_CLASSES = {
    "VALID_PRODUCT_HUB",
    "VALID_COMPANY_HUB",
    "VALID_TOPIC_HUB",
    "NAVIGATION_PAGE",
    "LEGAL_PAGE",
    "TAG_OR_ARCHIVE_PAGE",
    "SHARED_BOILERPLATE",
    "GENERIC_ENTITY",
    "SUSPICIOUS_ENTITY",
}
EXCLUDED_HUB_CLASSES = {
    "NAVIGATION_PAGE",
    "LEGAL_PAGE",
    "TAG_OR_ARCHIVE_PAGE",
    "SHARED_BOILERPLATE",
    "GENERIC_ENTITY",
    "SUSPICIOUS_ENTITY",
}
LEGAL_TERMS = {
    "privacy",
    "affiliate disclosure",
    "editorial policy",
    "terms",
    "contact",
    "about",
}
NAVIGATION_TERMS = {"home", "homepage", "menu", "navigation", "site"}
ARCHIVE_TERMS = {"archive", "tag", "category", "feed", "rss", "sitemap"}
BOILERPLATE_TERMS = {
    "related reading",
    "read more",
    "learn more",
    "source link",
    "affiliate",
    "disclosure",
}
GENERIC_TERMS = {
    "ai",
    "software",
    "tool",
    "tools",
    "review",
    "business",
    "small business",
    "product",
    "company",
}


def _norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").casefold()).strip()


def _unique_strings(values: list[Any]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        output.append(text)
    return output


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _load_config(root: Path) -> dict[str, Any]:
    payload = read_json(root / "config" / "operations_intelligence.json", {})
    return payload if isinstance(payload, dict) else {}


def classify_hubs(
    graph: dict[str, Any], quality_gate: dict[str, Any]
) -> dict[str, Any]:
    entities = {
        str(row.get("entity_id") or ""): row
        for row in graph.get("entities", [])
        if isinstance(row, dict)
    }
    rows: list[dict[str, Any]] = []
    for hub in quality_gate.get("top_entities_by_degree", [])[:50]:
        entity_id = str(hub.get("entity_id") or "")
        entity = entities.get(entity_id, {})
        name = _norm(entity.get("canonical_name") or hub.get("canonical_name"))
        entity_type = str(entity.get("entity_type") or hub.get("entity_type") or "")
        urls = _unique_strings(
            [
                value
                for key in ("official_urls", "repository_urls", "documentation_urls")
                for value in entity.get(key, [])
            ]
            + [
                hub.get("url"),
                hub.get("canonical"),
                *_as_list(hub.get("urls")),
                *_as_list(hub.get("related_urls")),
            ]
        )
        url_text = " ".join(_norm(value) for value in urls)
        evidence = [f"entity_type={entity_type}", f"degree={hub.get('degree', 0)}"]
        if name in GENERIC_TERMS or len(name) < 3:
            classification = "GENERIC_ENTITY"
            evidence.append("canonical name is generic")
        elif any(term == name or f" {term} " in f" {name} " for term in LEGAL_TERMS):
            classification = "LEGAL_PAGE"
            evidence.append("legal/operator page vocabulary")
        elif (
            any(term == name for term in NAVIGATION_TERMS)
            or name in {"reviews", "comparisons", "ai tool review center"}
        ):
            classification = "NAVIGATION_PAGE"
            evidence.append("navigation vocabulary")
        elif any(term in name or term in url_text for term in ARCHIVE_TERMS):
            classification = "TAG_OR_ARCHIVE_PAGE"
            evidence.append("archive/tag/feed vocabulary")
        elif any(term == name for term in BOILERPLATE_TERMS):
            classification = "SHARED_BOILERPLATE"
            evidence.append("shared boilerplate label")
        elif entity_type == "company":
            classification = "VALID_COMPANY_HUB"
            evidence.append("typed company entity")
        elif entity_type in {"product", "model", "developer_tool"}:
            classification = "VALID_PRODUCT_HUB"
            evidence.append("typed product/model/tool entity")
        elif entity_type in {"topic", "root_topic", "category"}:
            classification = "VALID_TOPIC_HUB"
            evidence.append("typed editorial topic entity")
        elif entity_type == "article" and any(
            token in f" {name} "
            for token in (" review ", " vs ", " pricing ", " comparison ", " alternatives ")
        ):
            classification = "VALID_TOPIC_HUB"
            evidence.append("specific published review/comparison editorial hub")
        elif entity_type == "article":
            classification = "SUSPICIOUS_ENTITY"
            evidence.append("article-derived entity needs human review before editorial reasoning")
        else:
            classification = "SUSPICIOUS_ENTITY"
            evidence.append("unsupported hub type")
        suggested = (
            "HUMAN_REVIEW_REQUIRED"
            if classification == "SUSPICIOUS_ENTITY"
            else "KEEP_EXCLUDED_FROM_EDITORIAL_REASONING"
            if classification in EXCLUDED_HUB_CLASSES
            else "ELIGIBLE_FOR_EDITORIAL_REASONING"
        )
        rows.append(
            {
                **hub,
                "classification": classification,
                "excluded_from_editorial_reasoning": classification in EXCLUDED_HUB_CLASSES,
                "evidence": evidence,
                "entity_type": entity_type,
                "degree": hub.get("degree", 0),
                "related_urls": urls,
                "suggested_classification": suggested,
                "auto_resolved": False,
            }
        )
    counts = Counter(row["classification"] for row in rows)
    suspicious = [row for row in rows if row["classification"] == "SUSPICIOUS_ENTITY"]
    return {
        "count": len(rows),
        "classifications": rows,
        "counts": {name: counts[name] for name in sorted(HUB_CLASSES)},
        "suspicious_entity_count": len(suspicious),
        "suspicious_entities": suspicious,
        "excluded_count": sum(row["excluded_from_editorial_reasoning"] for row in rows),
        "entities_deleted": False,
        "auto_resolved": False,
    }


def build_alias_review_queue(
    graph: dict[str, Any], quality_gate: dict[str, Any]
) -> dict[str, Any]:
    entities = {
        str(row.get("entity_id") or ""): row
        for row in graph.get("entities", [])
        if isinstance(row, dict)
    }
    rows: list[dict[str, Any]] = []
    for index, conflict in enumerate(quality_gate.get("alias_conflicts", []), start=1):
        candidates = []
        for entity_id in conflict.get("entity_ids", []):
            entity = entities.get(str(entity_id), {})
            candidates.append(
                {
                    "entity_id": entity_id,
                    "canonical_name": entity.get("canonical_name", ""),
                    "entity_type": entity.get("entity_type", ""),
                    "official_domain": entity.get("official_domain", ""),
                    "official_urls": entity.get("official_urls", []),
                    "repository_urls": entity.get("repository_urls", []),
                    "evidence": entity.get("source_evidence", [])[:5],
                    "confidence": entity.get("confidence", 0),
                }
            )
        types = {str(row.get("entity_type") or "") for row in candidates}
        names = {_norm(row.get("canonical_name")) for row in candidates}
        has_official_evidence = all(
            row.get("official_domain")
            or row.get("official_urls")
            or row.get("repository_urls")
            for row in candidates
        )
        if not has_official_evidence:
            suggested_action = "NEEDS_EVIDENCE"
        elif len(types) > 1:
            suggested_action = "KEEP_SEPARATE"
        elif len(names) == 1:
            suggested_action = "MERGE_REVIEW"
        else:
            suggested_action = "RENAME_REVIEW"
        rows.append(
            {
                "conflict_id": f"alias-conflict-{index:03d}",
                "alias": conflict.get("alias", ""),
                "candidate_entity_ids": [
                    str(row.get("entity_id") or "") for row in candidates
                ],
                "canonical_names": [
                    str(row.get("canonical_name") or "") for row in candidates
                ],
                "entity_types": [
                    str(row.get("entity_type") or "") for row in candidates
                ],
                "candidates": candidates,
                "reason": "one normalized alias resolves to multiple entity IDs",
                "confidence": max(
                    (float(row.get("confidence") or 0) for row in candidates),
                    default=0,
                ),
                "suggested_action": suggested_action,
                "human_action_required": True,
                "auto_merge_performed": False,
            }
        )
    return {
        "count": len(rows),
        "items": rows,
        "human_action_required": bool(rows),
        "auto_merge_performed": False,
    }


def _is_excluded_route(slug: str, title: str) -> str:
    value = f"{_norm(slug)} {_norm(title)}"
    if any(term in value for term in LEGAL_TERMS):
        return "legal target"
    if any(term in value for term in ARCHIVE_TERMS):
        return "archive/tag/report target"
    if any(term == _norm(title) for term in NAVIGATION_TERMS):
        return "navigation target"
    if any(term == _norm(title) for term in BOILERPLATE_TERMS):
        return "shared boilerplate target"
    return ""


def calibrate_internal_links(
    records: list[dict[str, Any]],
    raw: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, Any]:
    settings = config.get("internal_links") if isinstance(config.get("internal_links"), dict) else {}
    maximum = int(settings.get("maximum_suggestions_per_article", 5))
    minimum = float(settings.get("minimum_confidence", 0.55))
    high_minimum = float(settings.get("high_priority_minimum_confidence", 0.78))
    medium_minimum = float(settings.get("medium_priority_minimum_confidence", 0.65))
    high_cap = int(settings.get("maximum_high_priority_per_article", 3))
    by_slug = {str(row.get("slug") or ""): row for row in records}
    accepted: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    per_source: Counter[str] = Counter()
    high_per_source: Counter[str] = Counter()
    seen_pairs: set[tuple[str, str]] = set()
    seen_anchors: set[tuple[str, str]] = set()

    for item in sorted(
        raw.get("suggestions", []),
        key=lambda row: (-float(row.get("score") or 0), str(row.get("source_slug") or ""), str(row.get("target_slug") or "")),
    ):
        source = str(item.get("source_slug") or "")
        target = str(item.get("target_slug") or "")
        target_record = by_slug.get(target, {})
        reason = ""
        if source == target:
            reason = "self link"
        elif (source, target) in seen_pairs:
            reason = "duplicate source-target pair"
        elif not target_record.get("is_published_local"):
            reason = "target is draft, staging, missing local, or unpublished"
        elif any(
            token in str(target_record.get("editorial_state") or "").casefold()
            for token in ("block", "reject")
        ):
            reason = "target has an active blocked or rejected editorial state"
        elif not str(target_record.get("canonical") or "").startswith(PUBLIC_BASE_URL):
            reason = "target lacks a public canonical"
        else:
            reason = _is_excluded_route(target, str(target_record.get("title") or ""))
        evidence = str(item.get("evidence") or "")
        score = float(item.get("score") or 0)
        confidence = min(1.0, score / 9.0)
        if (
            not reason
            and "shared title terms" in evidence
            and "root topic" not in evidence
            and "editorial angle" not in evidence
        ):
            reason = "generic title overlap without verified editorial relationship"
        anchor = _norm(item.get("suggested_anchor"))
        if not reason and (source, anchor) in seen_anchors:
            reason = "repeated anchor for source article"
        if not reason and confidence < minimum:
            reason = "below configurable confidence threshold"
        if not reason and per_source[source] >= maximum:
            reason = "per-source suggestion cap reached"
        if reason:
            excluded.append({**item, "confidence": round(confidence, 4), "exclusion_reason": reason})
            continue
        if confidence >= high_minimum and high_per_source[source] < high_cap:
            priority = "HIGH_PRIORITY"
        elif confidence >= medium_minimum:
            priority = "MEDIUM_PRIORITY"
        else:
            priority = "LOW_PRIORITY"
        row = {
            **item,
            "confidence": round(confidence, 4),
            "priority": priority,
            "apply": False,
        }
        accepted.append(row)
        seen_pairs.add((source, target))
        seen_anchors.add((source, anchor))
        per_source[source] += 1
        if priority == "HIGH_PRIORITY":
            high_per_source[source] += 1

    distribution = Counter(per_source.values())
    target_counts = Counter(str(row.get("target_slug") or "") for row in accepted)
    anchor_counts = Counter(_norm(row.get("suggested_anchor")) for row in accepted)
    published_count = sum(bool(row.get("is_published_local")) for row in records)
    distribution[0] += max(0, published_count - len(per_source))
    return {
        "before": raw.get("summary", {}),
        "after": {
            "suggestion_count": len(accepted),
            "excluded_count": len(excluded),
            "high_priority_count": sum(row["priority"] == "HIGH_PRIORITY" for row in accepted),
            "medium_priority_count": sum(row["priority"] == "MEDIUM_PRIORITY" for row in accepted),
            "low_priority_count": sum(row["priority"] == "LOW_PRIORITY" for row in accepted),
        },
        "settings": {
            "minimum_confidence": minimum,
            "medium_priority_minimum_confidence": medium_minimum,
            "high_priority_minimum_confidence": high_minimum,
            "maximum_suggestions_per_article": maximum,
            "maximum_high_priority_per_article": high_cap,
        },
        "suggestions": accepted,
        "console_suggestions": [
            row for row in accepted if row["priority"] != "LOW_PRIORITY"
        ][:20],
        "excluded": excluded,
        "suggestion_distribution_0_to_5": {str(i): distribution[i] for i in range(6)},
        "top_20": accepted[:20],
        "excluded_20": excluded[:20],
        "repeated_targets": [
            {"target_slug": key, "count": value}
            for key, value in target_counts.most_common(20)
            if value > 1
        ],
        "repeated_anchors": [
            {"anchor": key, "count": value}
            for key, value in anchor_counts.most_common(20)
            if value > 1
        ],
        "html_modified": False,
    }


def validate_orphans(records: list[dict[str, Any]], minimum_inbound: int = 2) -> dict[str, Any]:
    published = {
        str(row.get("slug") or ""): row
        for row in records
        if row.get("is_published_local")
        and str(row.get("canonical") or "").startswith(PUBLIC_BASE_URL)
    }
    inbound: Counter[str] = Counter()
    evidence: defaultdict[str, list[dict[str, str]]] = defaultdict(list)
    for source_slug, record in published.items():
        page = record.get("html") if isinstance(record.get("html"), dict) else {}
        for link in page.get("links") or []:
            if not isinstance(link, dict):
                continue
            href = str(link.get("href") or "")
            target = internal_slug(urljoin(str(record.get("canonical") or ""), href))
            if target in published and target != source_slug:
                inbound[target] += 1
                evidence[target].append({"source_slug": source_slug, "href": href})
    items: list[dict[str, Any]] = []
    for record in records:
        slug = str(record.get("slug") or "")
        page = record.get("html") if isinstance(record.get("html"), dict) else {}
        count = inbound[slug]
        if not record.get("is_published_local"):
            classification = "DRAFT_OR_UNPUBLISHED"
        elif _is_excluded_route(slug, str(record.get("title") or "")):
            classification = "NAVIGATION_ONLY"
        elif not page.get("raw"):
            classification = "INVENTORY_MISMATCH"
        elif not page.get("canonical"):
            classification = "PARSER_UNCERTAIN"
        elif count == 0:
            classification = "TRUE_ORPHAN"
        elif count < minimum_inbound:
            classification = "WEAK_INBOUND"
        else:
            continue
        items.append(
            {
                "slug": slug,
                "canonical": record.get("canonical", ""),
                "classification": classification,
                "inbound_count": count,
                "inbound_evidence": evidence[slug][:10],
                "recommendation_only": True,
            }
        )
    counts = Counter(row["classification"] for row in items)
    unique_pages = {str(row.get("slug") or "") for row in items}
    true_orphan_pages = {
        str(row.get("slug") or "")
        for row in items
        if row.get("classification") == "TRUE_ORPHAN"
    }
    category_unique_counts = {
        key: len({str(row.get("slug") or "") for row in items if row.get("classification") == key})
        for key in sorted(counts)
    }
    return {
        "items": items,
        "counts": dict(sorted(counts.items())),
        "finding_count": len(items),
        "unique_page_count": len(unique_pages),
        "category_unique_page_counts": category_unique_counts,
        "category_count_total": sum(counts.values()),
        "categories_mutually_exclusive": True,
        "production_true_orphan_unique_count": len(true_orphan_pages),
        "metrics_note": (
            "Orphan categories are mutually exclusive per page. "
            "Category totals are finding counts and equal unique page count for this validator."
        ),
        "before_orphan_count": sum(inbound[slug] < minimum_inbound for slug in published),
        "after_true_orphan_count": counts["TRUE_ORPHAN"],
        "drafts_counted_as_production_orphans": 0,
        "content_modified": False,
    }


def _quality_reason_code(finding: str) -> str:
    value = finding.casefold()
    checks = [
        ("UNSUPPORTED_FACT", ("unsupported fact",)),
        ("REQUIRED_SOURCE", ("required source",)),
        ("AFFILIATE_DISCLOSURE", ("affiliate disclosure",)),
        ("PUBLIC_WORKFLOW_MARKER", ("workflow marker",)),
        ("CANONICAL", ("canonical is missing", "canonical mismatch")),
        ("RENDER_MISSING", ("rendered html is missing",)),
        ("MALFORMED_HTML", ("malformed",)),
        ("UTF8_MOJIBAKE", ("mojibake",)),
        ("SECURITY", ("security", "path traversal")),
        ("MISSING_H1", ("h1 is missing",)),
        ("BROKEN_LINK", ("broken link",)),
        ("COMMERCIAL_FRESHNESS", ("stale commercial", "pricing content is older")),
        ("ENTITY_EVIDENCE", ("entity-specific evidence",)),
        ("DUPLICATE_CONTENT", ("duplicate",)),
        ("MISSING_IMAGE", ("no image", "image missing")),
        ("SCHEMA_MISSING", ("schema was not detected", "schema missing")),
        ("SOURCE_URL_MISSING", ("no source url",)),
        ("VERIFICATION_DATE", ("verification date",)),
        ("OLD_REVIEW", ("old review",)),
        ("IMAGE_OPTIMIZATION", ("image optimization",)),
        ("WEAK_LINK", ("weak link",)),
        ("OPTIONAL_METADATA", ("optional metadata",)),
    ]
    for code, tokens in checks:
        if any(token in value for token in tokens):
            return code
    return "OTHER"


def _quality_class(finding: str) -> str:
    code = _quality_reason_code(finding)
    if code in {
        "UNSUPPORTED_FACT",
        "REQUIRED_SOURCE",
        "AFFILIATE_DISCLOSURE",
        "PUBLIC_WORKFLOW_MARKER",
        "CANONICAL",
        "RENDER_MISSING",
        "MALFORMED_HTML",
        "UTF8_MOJIBAKE",
        "SECURITY",
        "MISSING_H1",
    }:
        return "BLOCKING"
    if code in {"BROKEN_LINK", "COMMERCIAL_FRESHNESS", "ENTITY_EVIDENCE"}:
        return "HIGH_PRIORITY"
    if code in {
        "DUPLICATE_CONTENT",
        "MISSING_IMAGE",
        "SCHEMA_MISSING",
        "SOURCE_URL_MISSING",
        "VERIFICATION_DATE",
        "OLD_REVIEW",
        "IMAGE_OPTIMIZATION",
        "WEAK_LINK",
        "OPTIONAL_METADATA",
    }:
        return "MAINTENANCE"
    return "INFORMATIONAL"


def _severity_rank(value: str) -> int:
    return {"BLOCKING": 0, "HIGH_PRIORITY": 1, "MAINTENANCE": 2, "INFORMATIONAL": 3}.get(value, 4)


def _max_severity(categories: list[str]) -> str:
    if "BLOCKING" in categories:
        return "BLOCKING"
    if "HIGH_PRIORITY" in categories:
        return "HIGH_PRIORITY"
    if "MAINTENANCE" in categories:
        return "MAINTENANCE"
    return "INFORMATIONAL"


def _legacy_quality_class(finding: str) -> str:
    value = finding.casefold()
    if any(
        token in value
        for token in (
            "unsupported fact",
            "required source",
            "affiliate disclosure",
            "workflow marker",
            "canonical is missing",
            "canonical mismatch",
            "rendered html is missing",
            "malformed",
            "mojibake",
            "security",
            "path traversal",
            "h1 is missing",
        )
    ):
        return "BLOCKING"
    if any(
        token in value
        for token in (
            "no image",
            "duplicate",
            "schema was not detected",
            "broken link",
            "stale commercial",
            "entity-specific evidence",
        )
    ):
        return "HIGH_PRIORITY"
    if any(
        token in value
        for token in (
            "no source url",
            "verification date",
            "old review",
            "image optimization",
            "weak link",
            "optional metadata",
        )
    ):
        return "MAINTENANCE"
    return "INFORMATIONAL"


def calibrate_quality(raw: dict[str, Any]) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    all_counts: Counter[str] = Counter()
    before_counts: Counter[str] = Counter()
    reason_counts: Counter[str] = Counter()
    severity_to_slugs: defaultdict[str, set[str]] = defaultdict(set)
    item_severity_counts: Counter[str] = Counter()
    for item in raw.get("items", []):
        findings = []
        for finding in item.get("blocking", []) + item.get("warnings", []) + item.get("informational", []):
            category = _quality_class(str(finding))
            before_counts[_legacy_quality_class(str(finding))] += 1
            all_counts[category] += 1
            reason_code = _quality_reason_code(str(finding))
            reason_counts[reason_code] += 1
            slug = str(item.get("slug") or "")
            severity_to_slugs[category].add(slug)
            findings.append({"message": finding, "category": category, "reason_code": reason_code})
        active = [row["category"] for row in findings]
        severity = _max_severity(active)
        item_severity_counts[severity] += 1
        items.append(
            {
                "slug": item.get("slug", ""),
                "title": item.get("title", ""),
                "severity": severity,
                "findings": findings,
                "metrics": item.get("metrics", {}),
            }
        )
    console_findings = [
        row
        for row in sorted(items, key=lambda item: (_severity_rank(str(item.get("severity") or "")), str(item.get("slug") or "")))
        if row["severity"] in {"BLOCKING", "HIGH_PRIORITY"}
    ][:50]
    severity_summary = {
        level: {
            "finding_count": all_counts[level],
            "unique_article_count": len(severity_to_slugs[level]),
            "item_severity_count": item_severity_counts[level],
        }
        for level in ("BLOCKING", "HIGH_PRIORITY", "MAINTENANCE", "INFORMATIONAL")
    }
    return {
        "before": raw.get("summary", {}),
        "before_calibrated_counts": dict(sorted(before_counts.items())),
        "after": dict(sorted(all_counts.items())),
        "reason_code_counts": dict(reason_counts.most_common()),
        "top_reason_codes": [
            {"reason_code": key, "finding_count": value}
            for key, value in reason_counts.most_common(20)
        ],
        "severity_summary": severity_summary,
        "console_limit": 50,
        "items": items,
        "console_findings": console_findings,
        "content_modified": False,
    }


def build_memory_shortlist(
    raw: dict[str, Any], quality: dict[str, Any], config: dict[str, Any]
) -> dict[str, Any]:
    settings = config.get("editorial_memory") if isinstance(config.get("editorial_memory"), dict) else {}
    cap = min(
        int(settings.get("shortlist_maximum", 30)),
        max(int(settings.get("shortlist_minimum", 10)), int(settings.get("shortlist_default", 20))),
    )
    quality_by_slug = {row["slug"]: row for row in quality.get("items", [])}
    eligible: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for candidate in raw.get("candidates", []):
        state = str(candidate.get("origin_state") or "").casefold()
        q = quality_by_slug.get(str(candidate.get("slug") or ""), {})
        reasons: list[str] = []
        score = 0
        if any(token in state for token in ("published", "approved")):
            score += 30
            reasons.append("approved/published origin")
        if q.get("severity") == "BLOCKING" or not candidate.get("eligible_for_best"):
            excluded.append({**candidate, "exclusion_reason": "blocked or rejected origin"})
            continue
        if candidate.get("source_domains"):
            score += min(20, 5 * len(candidate["source_domains"]))
            reasons.append("source-backed")
        if candidate.get("schema_types"):
            score += min(15, 3 * len(candidate["schema_types"]))
            reasons.append("structured data present")
        if candidate.get("root_topic_id"):
            score += 10
        if candidate.get("daily_angle"):
            score += 10
        if candidate.get("heading_patterns"):
            score += 10
        if candidate.get("faq_themes"):
            score += 5
        eligible.append({**candidate, "shortlist_score": score, "shortlist_reasons": reasons})
    eligible.sort(key=lambda row: (-row["shortlist_score"], str(row.get("slug") or "")))
    shortlist = eligible[:cap]
    excluded.extend(
        {**row, "exclusion_reason": "outside configured shortlist cap"}
        for row in eligible[cap:]
    )
    return {
        "all_candidates": raw.get("candidates", []),
        "shortlist": shortlist,
        "excluded_candidates": excluded,
        "summary": {
            "all_candidate_count": len(raw.get("candidates", [])),
            "shortlist_count": len(shortlist),
            "excluded_count": len(excluded),
            "configured_cap": cap,
        },
        "auto_approved": False,
        "full_body_stored": False,
    }


def calibrate_evergreen(raw: dict[str, Any]) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    for item in raw.get("items", []):
        action = str(item.get("action") or "")
        reasons = [str(value) for value in item.get("reasons", [])]
        reason_text = " ".join(reasons).casefold()
        if action == "UPDATE_PRICING" or "pricing" in reason_text:
            classification, priority = "VERIFY_PRICING_OR_ACCESS", 100
        elif "discontinued" in reason_text or "product status" in reason_text:
            classification, priority = "VERIFY_PRODUCT_STATUS", 95
        elif action == "UPDATE_LINKS":
            classification, priority = "VERIFY_SOURCE", 90
        elif action == "UPDATE_IMAGE":
            classification, priority = "UPDATE_IMAGE", 60
        elif action == "UPDATE_SCHEMA":
            classification, priority = "UPDATE_SCHEMA", 80
        elif "no reliable verification date" in reason_text:
            classification, priority = "VERIFY_DATE_METADATA", 35
        elif action in {"VERIFY", "UPDATE_FACTS", "REWRITE"}:
            classification, priority = "VERIFY_FACT", 70
        else:
            classification, priority = "REVIEW_ONLY", 10
        items.append({**item, "classification": classification, "priority": priority, "task_created": False})
    items.sort(key=lambda row: (-row["priority"], str(row.get("slug") or "")))
    return {
        "items": items,
        "counts": dict(Counter(row["classification"] for row in items)),
        "tasks_created": 0,
        "content_modified": False,
    }


def calibrate_content_gaps(
    raw: dict[str, Any], excluded_entity_ids: set[str] | None = None
) -> dict[str, Any]:
    excluded_entity_ids = excluded_entity_ids or set()
    items: list[dict[str, Any]] = []
    for item in raw.get("suggestions", []):
        name = _norm(item.get("entity_name"))
        entity_type = str(item.get("entity_type") or "")
        reason_text = _norm(item.get("reason") or item.get("evidence") or "")
        if str(item.get("entity_id") or "") in excluded_entity_ids:
            classification = "INSUFFICIENT_EVIDENCE"
            evidence = "entity is excluded from editorial reasoning by hub calibration"
        elif item.get("duplicate_coverage") or "duplicate coverage" in reason_text:
            classification = "DUPLICATE_COVERAGE"
            evidence = "existing coverage already satisfies this entity and intent"
        elif name in GENERIC_TERMS or len(name) < 4:
            classification = "LOW_VALUE"
            evidence = "generic or underspecified entity"
        elif not item.get("weekly_root_locked"):
            classification = "INSUFFICIENT_EVIDENCE"
            evidence = "no active weekly-root context"
        elif entity_type in {"product", "model", "developer_tool"}:
            classification = "STRONG_GAP"
            evidence = "specific entity lacks explicit review/compare coverage"
        elif entity_type == "topic":
            classification = "POSSIBLE_GAP"
            evidence = "topic gap needs human value review"
        else:
            classification = "LOW_VALUE"
            evidence = "unsupported gap type"
        items.append({**item, "classification": classification, "calibration_evidence": evidence})
    return {
        "items": items,
        "counts": dict(Counter(row["classification"] for row in items)),
        "console_findings": [row for row in items if row["classification"] == "STRONG_GAP"],
        "queue_modified": False,
        "weekly_root_changed": False,
    }


def build_sample_validation(payload: dict[str, Any]) -> dict[str, Any]:
    """Deterministic local sample checks; no semantic/API scoring is used."""
    internal_links = payload.get("internal_links", {}).get("suggestions", [])[:20]
    memory = payload.get("memory", {}).get("shortlist", [])[:20]
    orphans = payload.get("orphans", {}).get("items", [])[:20]
    gaps = [
        row
        for row in payload.get("content_gaps", {}).get("items", [])
        if row.get("classification") == "STRONG_GAP"
    ][:5]

    def precision(rows: list[dict[str, Any]], predicate) -> float:
        if not rows:
            return 0.0
        return round(sum(1 for row in rows if predicate(row)) / len(rows), 4)

    return {
        "method": "fixture/local deterministic inspection; no semantic API; no paid API",
        "internal_link_suggestions": {
            "sample_size": len(internal_links),
            "estimated_precision": precision(
                internal_links,
                lambda row: bool(row.get("source_slug"))
                and bool(row.get("target_slug"))
                and str(row.get("target_url") or "").startswith(PUBLIC_BASE_URL)
                and not row.get("apply"),
            ),
        },
        "memory_shortlist_candidates": {
            "sample_size": len(memory),
            "estimated_precision": precision(
                memory,
                lambda row: bool(row.get("slug"))
                and row.get("eligible_for_best", True) is not False
                and bool(row.get("shortlist_reasons")),
            ),
        },
        "orphan_classifications": {
            "sample_size": len(orphans),
            "estimated_precision": precision(
                orphans,
                lambda row: row.get("classification")
                in {
                    "DRAFT_OR_UNPUBLISHED",
                    "NAVIGATION_ONLY",
                    "INVENTORY_MISMATCH",
                    "PARSER_UNCERTAIN",
                    "TRUE_ORPHAN",
                    "WEAK_INBOUND",
                }
                and row.get("recommendation_only") is True,
            ),
        },
        "strong_content_gaps": {
            "sample_size": len(gaps),
            "estimated_precision": precision(
                gaps,
                lambda row: row.get("classification") == "STRONG_GAP"
                and str(row.get("entity_type") or "") in {"product", "model", "developer_tool"},
            ),
        },
    }


class Phase2Calibration:
    def __init__(self, *, root: Path, now: datetime | None = None) -> None:
        self.root = root.resolve()
        self.now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)

    def run(self, *, mode: str = "dry-run") -> dict[str, Any]:
        config = _load_config(self.root)
        records = article_inventory(self.root)
        graph = EntityGraphBuilder(root=self.root, now=self.now).build(mode="dry-run")
        gate = EntityGraphQualityGate(root=self.root).validate(graph)
        raw_links = InternalLinkRecommendationEngine(root=self.root).analyze(records)
        raw_quality = EditorialQualityEngine(root=self.root).build(records)
        quality = calibrate_quality(raw_quality)
        raw_memory = EditorialMemoryStore(root=self.root).build_candidates(records, mode="dry-run")
        hubs = classify_hubs(graph, gate)
        excluded_entity_ids = {
            str(row.get("entity_id") or "")
            for row in hubs["classifications"]
            if row["excluded_from_editorial_reasoning"]
        }
        payload = {
            "schema_version": SCHEMA_VERSION,
            "mode": mode,
            "generated_at": self.now.isoformat(),
            "quality_gate_result": gate.get("quality_gate_result"),
            "verified_facts": {
                "known_fact_count": sum(
                    len(row.get("known_facts") or {})
                    for row in graph.get("entities", [])
                    if isinstance(row, dict)
                    and str(row.get("entity_id") or "") not in excluded_entity_ids
                ),
                "unknown_or_unverified_count": sum(
                    len(row.get("unknown_or_unverified") or [])
                    for row in graph.get("entities", [])
                    if isinstance(row, dict)
                    and str(row.get("entity_id") or "") not in excluded_entity_ids
                ),
                "excluded_hub_count": len(excluded_entity_ids),
            },
            "hubs": hubs,
            "alias_review_queue": build_alias_review_queue(graph, gate),
            "internal_links": calibrate_internal_links(records, raw_links, config),
            "orphans": validate_orphans(records),
            "quality": quality,
            "memory": build_memory_shortlist(raw_memory, quality, config),
            "evergreen": calibrate_evergreen(EvergreenEngine(root=self.root, now=self.now).scan(records)),
            "content_gaps": calibrate_content_gaps(
                ContentGapEngine(root=self.root).suggest(graph, records),
                excluded_entity_ids,
            ),
            "safety": {
                "recommendation_only": True,
                "production_content_modified": False,
                "queue_modified": False,
                "sitemap_modified": False,
                "approval_changed": False,
                "published": False,
                "alias_auto_merge": False,
                "internal_links_applied": False,
                "evergreen_tasks_created": False,
            },
            "outputs": {},
        }
        payload["sample_validation"] = build_sample_validation(payload)
        if mode == "write":
            payload["outputs"] = self.write(payload)
        return payload

    def write(self, payload: dict[str, Any]) -> dict[str, str]:
        date = self.now.date().isoformat()
        intelligence_root = self.root / "data" / "intelligence"
        output = intelligence_root / "calibration" / date
        report_root = self.root / "data" / "reports" / "operations_intelligence"
        paths = {
            "calibration": output / "calibration.json",
            "hub_classification": output / "hub_classification.json",
            "alias_review_queue": output / "alias_review_queue.json",
            "internal_links": output / "internal_link_calibration.json",
            "orphans": output / "orphan_validation.json",
            "quality": output / "quality_calibration.json",
            "memory_all_candidates": output / "memory" / "all_candidates.json",
            "memory_shortlist": output / "memory" / "shortlist.json",
            "memory_excluded": output / "memory" / "excluded_candidates.json",
            "evergreen": output / "evergreen_calibration.json",
            "content_gaps": output / "content_gap_calibration.json",
        }
        mapping = {
            "calibration": payload,
            "hub_classification": payload["hubs"],
            "alias_review_queue": payload["alias_review_queue"],
            "internal_links": payload["internal_links"],
            "orphans": payload["orphans"],
            "quality": payload["quality"],
            "memory_all_candidates": payload["memory"]["all_candidates"],
            "memory_shortlist": payload["memory"]["shortlist"],
            "memory_excluded": payload["memory"]["excluded_candidates"],
            "evergreen": payload["evergreen"],
            "content_gaps": payload["content_gaps"],
        }
        for key, path in paths.items():
            atomic_write_json(path, mapping[key], intelligence_root=intelligence_root)
        report_path = report_root / f"phase2_calibration_{date}.md"
        dashboard_path = report_root / f"phase2_operator_dashboard_{date}.html"
        memory_report = report_root / f"memory_shortlist_{date}.md"
        alias_report = report_root / f"alias_conflicts_{date}.md"
        links_report = report_root / f"internal_link_calibration_{date}.md"
        orphan_report = report_root / f"orphan_validation_{date}.md"
        quality_report = report_root / f"quality_calibration_{date}.md"
        evergreen_report = report_root / f"evergreen_calibration_{date}.md"
        gaps_report = report_root / f"content_gap_calibration_{date}.md"
        atomic_write_text(
            report_path,
            build_calibration_report(payload),
            intelligence_root=self.root / "data",
        )
        atomic_write_text(
            memory_report,
            build_memory_report(payload["memory"]),
            intelligence_root=self.root / "data",
        )
        report_payloads = {
            alias_report: build_alias_report(payload["alias_review_queue"]),
            links_report: build_internal_link_report(payload["internal_links"]),
            orphan_report: build_simple_report(
                "Orphan Validation",
                {
                    **payload["orphans"]["counts"],
                    "finding_count": payload["orphans"]["finding_count"],
                    "unique_page_count": payload["orphans"]["unique_page_count"],
                    "production_true_orphan_unique_count": payload["orphans"]["production_true_orphan_unique_count"],
                    "categories_mutually_exclusive": payload["orphans"]["categories_mutually_exclusive"],
                },
                payload["orphans"]["items"],
            ),
            quality_report: build_simple_report(
                "Quality Calibration", payload["quality"]["severity_summary"], payload["quality"]["console_findings"]
            ),
            evergreen_report: build_simple_report(
                "Evergreen Calibration", payload["evergreen"]["counts"], payload["evergreen"]["items"][:50]
            ),
            gaps_report: build_simple_report(
                "Content Gap Calibration", payload["content_gaps"]["counts"], payload["content_gaps"]["items"]
            ),
        }
        for path, content in report_payloads.items():
            atomic_write_text(path, content, intelligence_root=self.root / "data")
        result = {key: str(path) for key, path in paths.items()}
        result.update(
            {
                "report": str(report_path),
                "memory_shortlist_report": str(memory_report),
                "alias_report": str(alias_report),
                "internal_link_report": str(links_report),
                "orphan_report": str(orphan_report),
                "quality_report": str(quality_report),
                "evergreen_report": str(evergreen_report),
                "content_gap_report": str(gaps_report),
                "operator_dashboard": str(dashboard_path),
            }
        )
        dashboard_payload = {**payload, "outputs": result}
        atomic_write_text(
            dashboard_path,
            build_operator_dashboard(dashboard_payload),
            intelligence_root=self.root / "data",
        )
        atomic_write_json(
            paths["calibration"],
            dashboard_payload,
            intelligence_root=intelligence_root,
        )
        return result


def build_memory_report(payload: dict[str, Any]) -> str:
    lines = [
        "# Editorial Memory Shortlist",
        "",
        f"- Candidates: {payload['summary']['all_candidate_count']}",
        f"- Shortlist: {payload['summary']['shortlist_count']}",
        f"- Excluded: {payload['summary']['excluded_count']}",
        "- Auto-approved: NO",
        "- Full article body stored: NO",
        "",
        "## Shortlist",
        "",
    ]
    lines.extend(
        f"- `{row['slug']}`: {row['shortlist_score']} - {', '.join(row['shortlist_reasons'])}"
        for row in payload["shortlist"]
    )
    return "\n".join(lines).rstrip() + "\n"


def build_calibration_report(payload: dict[str, Any]) -> str:
    sections = [
        "# Phase 2 Calibration & Operator Readiness",
        "",
        f"- Generated: `{payload['generated_at']}`",
        f"- Mode: `{payload['mode']}`",
        f"- Graph gate: **{payload['quality_gate_result']}**",
        "",
        "## Counts",
        "",
        f"- Hubs classified: {payload['hubs']['count']}",
        f"- Hubs excluded from editorial reasoning: {payload['hubs']['excluded_count']}",
        f"- Alias conflicts requiring human action: {payload['alias_review_queue']['count']}",
        f"- Internal links before: {payload['internal_links']['before'].get('suggestion_count', 0)}",
        f"- Internal links after: {payload['internal_links']['after']['suggestion_count']}",
        f"- Orphan findings: {payload['orphans']['finding_count']}",
        f"- Unique orphan pages: {payload['orphans']['unique_page_count']}",
        f"- Production true orphan unique pages: {payload['orphans']['production_true_orphan_unique_count']}",
        f"- Orphan categories mutually exclusive: {str(payload['orphans']['categories_mutually_exclusive']).upper()}",
        f"- Suspicious entities requiring human review: {payload['hubs'].get('suspicious_entity_count', 0)}",
        f"- Memory shortlist: {payload['memory']['summary']['shortlist_count']}",
        f"- Strong content gaps: {payload['content_gaps']['counts'].get('STRONG_GAP', 0)}",
        "",
        "## Quality Priority Calibration",
        "",
    ]
    for level, stats in payload["quality"].get("severity_summary", {}).items():
        sections.append(
            f"- {level}: {stats['finding_count']} findings across "
            f"{stats['unique_article_count']} unique articles"
        )
    sections.extend(
        [
            "",
            "### Top Reason Codes",
            "",
        ]
    )
    sections.extend(
        f"- {row['reason_code']}: {row['finding_count']}"
        for row in payload["quality"].get("top_reason_codes", [])[:10]
    )
    sections.extend(
        [
            "",
            "## Sample Validation",
            "",
        ]
    )
    for key, stats in payload.get("sample_validation", {}).items():
        if not isinstance(stats, dict) or "estimated_precision" not in stats:
            continue
        sections.append(
            f"- {key}: sample={stats['sample_size']}, estimated_precision={stats['estimated_precision']}"
        )
    sections.extend(
        [
            "",
            "## Safety",
            "",
        ]
    )
    sections.extend(f"- {key}: {str(value).upper()}" for key, value in payload["safety"].items())
    sections.extend(["", "## Next Action", "", "- Review aliases and top HIGH_PRIORITY recommendations manually."])
    return "\n".join(sections).rstrip() + "\n"


def build_alias_report(payload: dict[str, Any]) -> str:
    lines = [
        "# Alias Conflict Review Queue",
        "",
        "- Human action required: YES",
        "- Automatic merge performed: NO",
        f"- Conflicts: {payload['count']}",
        "",
    ]
    for row in payload["items"]:
        candidates = ", ".join(
            f"{candidate['canonical_name']} ({candidate['entity_type']}; "
            f"{candidate['official_domain'] or 'no official domain'})"
            for candidate in row["candidates"]
        )
        lines.append(
            f"- `{row['conflict_id']}` alias **{row['alias']}**: {candidates}. "
            f"Action: {row['suggested_action']}."
        )
    return "\n".join(lines).rstrip() + "\n"


def build_internal_link_report(payload: dict[str, Any]) -> str:
    lines = [
        "# Internal Link Calibration",
        "",
        "- Recommendation only: YES",
        "- HTML modified: NO",
        f"- Suggestions before: {payload['before'].get('suggestion_count', 0)}",
        f"- Suggestions after: {payload['after']['suggestion_count']}",
        f"- Excluded: {payload['after']['excluded_count']}",
        f"- High priority: {payload['after']['high_priority_count']}",
        "",
        "## Best 20",
        "",
    ]
    lines.extend(
        f"- `{row['source_slug']}` -> `{row['target_slug']}` "
        f"({row['priority']}, {row['confidence']:.2f}): {row['evidence']}"
        for row in payload["top_20"]
    )
    lines.extend(["", "## Excluded 20", ""])
    lines.extend(
        f"- `{row.get('source_slug', '')}` -> `{row.get('target_slug', '')}`: "
        f"{row['exclusion_reason']}"
        for row in payload["excluded_20"]
    )
    return "\n".join(lines).rstrip() + "\n"


def build_simple_report(
    title: str, counts: dict[str, Any], rows: list[dict[str, Any]]
) -> str:
    lines = [f"# {title}", "", "- Recommendation only: YES", "- Automatic action: NO", "", "## Counts", ""]
    lines.extend(f"- {key}: {value}" for key, value in sorted(counts.items()))
    lines.extend(["", "## Review Items", "", "```json"])
    lines.append(json.dumps(rows, ensure_ascii=False, indent=2))
    lines.extend(["```", ""])
    return "\n".join(lines)


def build_operator_dashboard(payload: dict[str, Any]) -> str:
    summary = {
        "Quality Gate status": payload["quality_gate_result"],
        "High-degree hubs": payload["hubs"]["count"],
        "Excluded hubs": payload["hubs"]["excluded_count"],
        "Alias conflicts": payload["alias_review_queue"]["count"],
        "Verified-fact coverage": payload.get("verified_facts", {}).get("known_fact_count", 0),
        "Editorial Memory shortlist": payload["memory"]["summary"]["shortlist_count"],
        "Evergreen priorities": len(payload["evergreen"]["items"]),
        "Internal-link top suggestions": payload["internal_links"]["after"]["suggestion_count"],
        "Production true orphan pages": payload["orphans"].get(
            "production_true_orphan_unique_count",
            payload["orphans"]["counts"].get("TRUE_ORPHAN", 0),
        ),
        "Quality blockers / high-priority": (
            payload["quality"]["after"].get("BLOCKING", 0)
            + payload["quality"]["after"].get("HIGH_PRIORITY", 0)
        ),
        "Suspicious entities": payload["hubs"].get("suspicious_entity_count", 0),
        "Strong content gaps": payload["content_gaps"]["counts"].get("STRONG_GAP", 0),
    }
    cards = "".join(
        f"<section><h2>{html.escape(str(key))}</h2><strong>{html.escape(str(value))}</strong></section>"
        for key, value in summary.items()
    )
    outputs = payload.get("outputs") or {}
    output_rows = "".join(
        f"<li><b>{html.escape(key)}</b>: <code>{html.escape(str(value))}</code></li>"
        for key, value in sorted(outputs.items())
    )
    priority_rows = "".join(
        "<tr><td>" + html.escape(str(row.get("section") or "")) + "</td><td>" 
        + html.escape(str(row.get("status") or "")) + "</td><td>"
        + html.escape(str(row.get("count") or 0)) + "</td><td>"
        + html.escape(str(row.get("reason") or "")) + "</td></tr>"
        for row in (payload.get("weekly_preflight") or {}).get("priority_sections", [])
    )
    priority_block = (
        "<h2>Preflight priorities</h2><table><thead><tr><th>Section</th><th>Status</th>"
        "<th>Count</th><th>Reason</th></tr></thead><tbody>" + priority_rows + "</tbody></table>"
        if priority_rows else ""
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="robots" content="noindex,nofollow">
<title>Phase 2 Operator Readiness</title>
<style>body{{font-family:Arial,sans-serif;margin:2rem;color:#142033;background:#f4f7fa}}
main{{max-width:1200px;margin:auto}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px}}
section{{background:white;border:1px solid #d7e0e8;padding:16px;border-radius:6px}}h2{{font-size:15px}}strong{{font-size:24px}}
table{{width:100%;border-collapse:collapse;background:#fff;margin:1rem 0}}th,td{{padding:9px;border:1px solid #d7e0e8;text-align:left}}
code{{overflow-wrap:anywhere}}</style></head><body><main><h1>Phase 2 Operator Readiness</h1>
<p>Read-only recommendations. No action on this page changes content, queues, approval, or publish state.</p>
{priority_block}<div class="grid">{cards}</div><h2>Report paths</h2><ul>{output_rows}</ul>
<h2>Next operator action</h2><p>Review alias conflicts and HIGH_PRIORITY recommendations manually.</p>
</main></body></html>
"""
