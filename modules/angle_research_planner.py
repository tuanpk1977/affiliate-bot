from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from modules.comparator_discovery import ComparatorDiscoveryEngine
from modules.entity_knowledge_base import EntityKnowledgeBase, entity_id
from modules.official_source_registry import OfficialSourceRegistry, normalize_family
from modules.source_classification import (
    OFFICIAL_SOURCE_TYPES,
    classify_source,
    comparison_entity_names,
    flatten_source_rows,
    source_status,
)


def _write_json(path: Path, payload: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


ANGLE_PROFILES: dict[str, dict[str, Any]] = {
    "comparison_and_alternatives": {
        "required_entity_roles": {"root": 1, "comparator": 2},
        "required_source_families": ["official_website", "docs", "github", "pricing"],
        "required_claim_categories": [
            "identity", "workflow", "feature", "limitation", "pricing", "alternative"
        ],
        "mandatory_sections": [
            "product-identity", "core-workflow", "feature-scope", "limitations",
            "pricing", "alternatives", "final-recommendation",
        ],
        "minimum_claims_per_entity": 5,
        "minimum_sources_per_entity": 1,
        "minimum_entity_coverage": 0.60,
        "allowed_cautious_substitutions": ["pricing", "limitations"],
    },
    "pricing_and_value": {
        "required_entity_roles": {"root": 1},
        "required_source_families": ["pricing", "faq", "support", "official_website"],
        "required_claim_categories": ["identity", "pricing", "limitation", "workflow"],
        "mandatory_sections": ["product-identity", "pricing", "limitations", "final-recommendation"],
        "minimum_claims_per_entity": 8,
        "minimum_sources_per_entity": 1,
        "minimum_entity_coverage": 0.65,
        "allowed_cautious_substitutions": ["pricing"],
    },
    "setup_and_installation": {
        "required_entity_roles": {"root": 1},
        "required_source_families": ["readme", "docs", "github", "support"],
        "required_claim_categories": ["identity", "workflow", "feature", "limitation"],
        "mandatory_sections": ["product-identity", "core-workflow", "feature-scope", "limitations"],
        "minimum_claims_per_entity": 8,
        "minimum_sources_per_entity": 1,
        "minimum_entity_coverage": 0.65,
        "allowed_cautious_substitutions": ["limitations"],
    },
    "workflow_and_use_cases": {
        "required_entity_roles": {"root": 1},
        "required_source_families": ["docs", "tutorial", "examples", "official_website"],
        "required_claim_categories": ["identity", "workflow", "feature", "limitation"],
        "mandatory_sections": ["product-identity", "core-workflow", "feature-scope", "limitations"],
        "minimum_claims_per_entity": 8,
        "minimum_sources_per_entity": 1,
        "minimum_entity_coverage": 0.65,
        "allowed_cautious_substitutions": ["limitations"],
    },
    "integrations": {
        "required_entity_roles": {"root": 1},
        "required_source_families": ["docs", "api_docs", "marketplace", "github"],
        "required_claim_categories": ["identity", "integration", "limitation"],
        "mandatory_sections": ["product-identity", "feature-scope", "limitations"],
        "minimum_claims_per_entity": 8,
        "minimum_sources_per_entity": 1,
        "minimum_entity_coverage": 0.65,
        "allowed_cautious_substitutions": ["limitations"],
    },
    "limitations_and_risks": {
        "required_entity_roles": {"root": 1},
        "required_source_families": ["docs", "faq", "support", "github"],
        "required_claim_categories": ["identity", "limitation", "workflow"],
        "mandatory_sections": ["product-identity", "limitations", "cons", "final-recommendation"],
        "minimum_claims_per_entity": 8,
        "minimum_sources_per_entity": 1,
        "minimum_entity_coverage": 0.65,
        "allowed_cautious_substitutions": ["limitations"],
    },
    "security_and_privacy": {
        "required_entity_roles": {"root": 1},
        "required_source_families": ["docs", "security", "privacy", "support"],
        "required_claim_categories": ["identity", "security", "limitation"],
        "mandatory_sections": ["product-identity", "feature-scope", "limitations", "final-recommendation"],
        "minimum_claims_per_entity": 8,
        "minimum_sources_per_entity": 1,
        "minimum_entity_coverage": 0.70,
        "allowed_cautious_substitutions": ["security", "limitations"],
    },
    "performance_and_scalability": {
        "required_entity_roles": {"root": 1},
        "required_source_families": ["docs", "github", "release_notes", "support"],
        "required_claim_categories": ["identity", "performance", "limitation"],
        "mandatory_sections": ["product-identity", "feature-scope", "limitations", "final-recommendation"],
        "minimum_claims_per_entity": 8,
        "minimum_sources_per_entity": 1,
        "minimum_entity_coverage": 0.70,
        "allowed_cautious_substitutions": ["performance", "limitations"],
    },
    "team_adoption": {
        "required_entity_roles": {"root": 1},
        "required_source_families": ["docs", "tutorial", "support", "pricing"],
        "required_claim_categories": ["identity", "workflow", "pricing", "limitation"],
        "mandatory_sections": ["product-identity", "core-workflow", "pricing", "limitations"],
        "minimum_claims_per_entity": 8,
        "minimum_sources_per_entity": 1,
        "minimum_entity_coverage": 0.65,
        "allowed_cautious_substitutions": ["pricing", "limitations"],
    },
    "advanced_features": {
        "required_entity_roles": {"root": 1},
        "required_source_families": ["docs", "api_docs", "examples", "release_notes"],
        "required_claim_categories": ["identity", "feature", "integration", "limitation"],
        "mandatory_sections": ["product-identity", "feature-scope", "limitations"],
        "minimum_claims_per_entity": 8,
        "minimum_sources_per_entity": 1,
        "minimum_entity_coverage": 0.65,
        "allowed_cautious_substitutions": ["limitations"],
    },
}


def _text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _unique(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = _text(value)
        key = entity_id(cleaned)
        if not cleaned or key in seen:
            continue
        seen.add(key)
        result.append(cleaned)
    return result


def classify_angle(task: dict[str, Any]) -> str:
    text = " ".join(
        _text(task.get(key))
        for key in ("daily_angle", "title", "keyword", "reader_question", "unique_thesis")
    ).casefold()
    rules = (
        ("comparison_and_alternatives", ("comparison", "alternative", " versus ", " vs ")),
        ("pricing_and_value", ("pricing", "billing", "cost", "value")),
        ("setup_and_installation", ("setup", "installation", "install", "requirements")),
        ("workflow_and_use_cases", ("workflow", "use case", "tutorial", "how to")),
        ("integrations", ("integration", "api", "connector")),
        ("limitations_and_risks", ("limitation", "risk", "troubleshoot", "cons")),
        ("security_and_privacy", ("security", "privacy", "compliance")),
        ("performance_and_scalability", ("performance", "scalability", "benchmark")),
        ("team_adoption", ("team adoption", "collaboration", "onboarding")),
        ("advanced_features", ("advanced", "feature")),
    )
    return next((profile for profile, markers in rules if any(marker in text for marker in markers)), "advanced_features")


class AngleResearchPlanner:
    def __init__(self, *, root: Path, data_dir: Path | None = None) -> None:
        self.root = root
        self.data_dir = data_dir or root / "data"
        self.registry = OfficialSourceRegistry(self.data_dir / "official_source_registry.json")
        self.kb = EntityKnowledgeBase(self.data_dir / "entity_knowledge_base")
        self.comparators = ComparatorDiscoveryEngine(root=root, data_dir=self.data_dir)

    def build(
        self,
        package: dict[str, Any],
        task: dict[str, Any],
        *,
        persist_report: bool = True,
    ) -> dict[str, Any]:
        profile_name = classify_angle(task)
        profile = ANGLE_PROFILES[profile_name]
        root_name = self._root_entity(package, task)
        comparison_subject = root_name
        required_comparators = int(profile["required_entity_roles"].get("comparator", 0))
        required_entities = 1 + required_comparators
        # Resolve concrete products/vendors for every angle.  A broad article
        # subject (for example "AI healthcare marketing") is a TOPIC, not a
        # commercial entity that can own Make/Zapier pricing pages.
        product_entities = comparison_entity_names(package, task)
        explicit_comparison_entities = any(
            task.get(key)
            for key in ("comparison_entities", "products_compared", "comparator_entities")
        )
        entity_selection_reason = "explicit_or_named_root"
        broad_comparison_blocker = ""
        if required_comparators and not explicit_comparison_entities and entity_id(root_name) not in {
            entity_id(name) for name in product_entities
        }:
            if len(product_entities) == required_entities:
                root_name = product_entities[0]
                entity_selection_reason = "exact_product_set_from_research_entities"
            elif len(product_entities) < required_entities:
                broad_comparison_blocker = (
                    f"Comparison topic identifies only {len(product_entities)} concrete product entities; "
                    f"exactly {required_entities} are required before evidence acquisition."
                )
            else:
                broad_comparison_blocker = (
                    f"Comparison topic has {len(product_entities)} plausible product entities; "
                    f"operator must select exactly {required_entities} before evidence acquisition."
                )
        package_sources = package.get("sources") if isinstance(package.get("sources"), dict) else {}
        root_profile_path = self.kb.entity_dir(root_name) / "profile.json"
        root_profile = self.kb.load(root_name)
        # A named KB entity with owned domains is concrete even when the task's
        # explicit comparison list contains only its comparators.  Broad topic
        # labels remain topics: merely having candidate URLs is not enough to
        # promote them to product/vendor ownership.
        root_is_concrete_entity = entity_id(root_name) in {
            entity_id(name) for name in product_entities
        } or (
            root_profile_path.is_file()
            and bool(root_profile.get("product_category"))
            and bool(root_profile.get("official_domains"))
        )
        # If the root is a broad TOPIC (not a concrete product/vendor), it cannot
        # own first-party official sources.  The strict in-memory entity record
        # below enforces that rule; planning must not rewrite the entity KB,
        # especially when the caller requested a read-only/dry-run plan.
        root = self._entity_record(
            root_name,
            "product" if root_is_concrete_entity else "topic",
            package_sources=package_sources,
            # Ownership is always strict.  Topic titles must never inherit
            # first-party ownership from unrelated product URLs.
            strict_ownership=True,
        )
        fixed_comparators = (
            product_entities[1:required_entities]
            if entity_selection_reason == "exact_product_set_from_research_entities"
            else []
        )
        comparator_report = (
            {
                "status": "READY",
                "approval_mode": "AUTO_VERIFIED_PRODUCT_SET",
                "decision_reason": "Exactly the required number of concrete product entities has owned official-source evidence.",
                "candidates": [
                    {
                        "candidate_entity_id": entity_id(name),
                        "canonical_name": name,
                        "verification_status": "VERIFIED",
                    }
                    for name in fixed_comparators
                ],
                "selected_comparators": [
                    {"candidate_entity_id": entity_id(name), "canonical_name": name}
                    for name in fixed_comparators
                ],
                "operator_candidates": [],
            }
            if fixed_comparators
            else
            self.comparators.discover(
                root_entity=root_name,
                article_slug=_text(task.get("slug")) or entity_id(root_name),
                package=package,
                task=task,
                required_count=required_comparators,
                persist_report=persist_report,
            )
            if required_comparators
            else {
                "status": "NOT_REQUIRED",
                "approval_mode": "AUTO_VERIFIED",
                "candidates": [],
                "selected_comparators": [],
                "operator_candidates": [],
            }
        )
        selected_comparators = [
            self._entity_record(
                row["canonical_name"],
                "comparator",
                package_sources=package_sources,
                strict_ownership=True,
            )
            for row in comparator_report.get("selected_comparators") or []
        ]
        required_evidence_entities = (
            []
            if root_is_concrete_entity or required_comparators
            else [
                self._entity_record(
                    name,
                    "evidence_entity",
                    package_sources=package_sources,
                    strict_ownership=True,
                )
                for name in product_entities
            ]
        )
        selected_ids = {row["entity_id"] for row in selected_comparators}
        unresolved = [
            row["canonical_name"]
            for row in comparator_report.get("candidates") or []
            if row["candidate_entity_id"] not in selected_ids
        ]
        entities = (
            required_evidence_entities
            if required_evidence_entities
            else [root, *selected_comparators]
        )
        completion: list[str] = [
            f"At least {profile['minimum_claims_per_entity']} accepted claims per required entity.",
            f"At least {profile['minimum_sources_per_entity']} approved official source(s) per required entity.",
            f"Per-entity coverage score must be at least {profile['minimum_entity_coverage']:.2f}.",
            "Every mandatory section must have direct evidence or an explicitly allowed cautious caveat.",
        ]
        blockers: list[str] = []
        if len(selected_comparators) < required_comparators:
            blockers.append(
                f"Angle requires {required_comparators} verified comparator entities; "
                f"resolved {len(selected_comparators)}."
            )
            if comparator_report.get("approval_mode") == "HUMAN_CONFIRM_REQUIRED":
                blockers.append(
                    "Comparator confirmation required; review comparator_candidate_report.md "
                    "and confirm exactly two verified entities."
                )
        if root_is_concrete_entity and not root["official_sources"]:
            blockers.append(f"Root entity {root_name} has no approved official source.")
        if not root_is_concrete_entity and not required_evidence_entities:
            blockers.append(
                f"Topic {root_name} has no concrete product, vendor, service, or platform evidence entity."
            )
        if broad_comparison_blocker:
            blockers.append(broad_comparison_blocker)
        return {
            "schema_version": 1,
            "angle_profile": profile_name,
            "comparison_subject": comparison_subject,
            "identified_comparison_entities": [row["canonical_name"] for row in entities],
            "entity_selection_reason": entity_selection_reason,
            "daily_angle": _text(task.get("daily_angle")),
            "reader_question": _text(task.get("reader_question")),
            "unique_thesis": _text(task.get("unique_thesis")),
            "root_entity": root,
            "subject_entity_class": "PRODUCT" if root_is_concrete_entity else "TOPIC",
            "required_comparator_entities": selected_comparators,
            "required_evidence_entities": required_evidence_entities,
            "comparator_discovery": comparator_report,
            "required_entity_count": len(entities),
            "resolved_entity_count": len(entities),
            "unresolved_or_ambiguous_comparators": _unique(unresolved),
            "required_source_families": list(profile["required_source_families"]),
            "required_claim_categories": list(profile["required_claim_categories"]),
            "mandatory_sections": list(profile["mandatory_sections"]),
            "section_evidence_targets": {
                section: {"minimum_claims": 1, "required_entities": [row["entity_id"] for row in entities]}
                for section in profile["mandatory_sections"]
            },
            "entity_evidence_targets": {
                row["entity_id"]: {
                    "entity_name": row["canonical_name"],
                    "entity_role": row["entity_role"],
                    "minimum_claims": profile["minimum_claims_per_entity"],
                    "minimum_official_sources": profile["minimum_sources_per_entity"],
                    "minimum_coverage_score": profile["minimum_entity_coverage"],
                }
                for row in entities
            },
            "reused_knowledge_base_evidence": {
                row["entity_id"]: {
                    "sources": len(self.kb.load(row["canonical_name"]).get("sources") or []),
                    "claims": len(self.kb.load(row["canonical_name"]).get("claims") or []),
                }
                for row in entities
            },
            "new_evidence_required": blockers,
            "allowed_cautious_substitutions": list(profile["allowed_cautious_substitutions"]),
            "prohibited_overlap": list(task.get("prohibited_overlap") or []),
            "completion_criteria": completion,
            "planning_status": "READY_TO_RETRIEVE" if not blockers else "NEEDS_ENTITY_REVIEW",
            "planning_blockers": blockers,
        }

    def inventory_sources(self, plan: dict[str, Any]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        entities = list(plan.get("required_evidence_entities") or []) or [
            plan["root_entity"],
            *plan.get("required_comparator_entities", []),
        ]
        for entity in entities:
            for source in entity.get("official_sources") or []:
                rows.append(
                    {
                        **source,
                        "canonical_entity_id": entity["entity_id"],
                        "canonical_entity_name": entity["canonical_name"],
                        "entity_role": entity["entity_role"],
                        "source_family": normalize_family(_text(source.get("source_type"))),
                    }
                )
        return rows

    def _entity_record(
        self,
        name: str,
        role: str,
        *,
        package_sources: dict[str, Any] | None = None,
        strict_ownership: bool = True,
    ) -> dict[str, Any]:
        profile = self.kb.load(name)
        sources = self.registry.sources_for(name)
        if not sources:
            sources = [
                {
                    **row,
                    "source_url": row.get("canonical_url") or row.get("source_url"),
                    "canonical_url": row.get("canonical_url") or row.get("source_url"),
                    "source_type": row.get("source_type") or "official_website",
                    "verification_status": row.get("verification_status") or "verified",
                }
                for row in profile.get("sources") or []
                if row.get("canonical_url") or row.get("source_url")
            ]
        package_rows = flatten_source_rows(package_sources or {})
        classified = []
        for row in package_rows:
            if source_status(row) not in {"verified", "approved", "supplied"}:
                continue
            classified_row = classify_source(row, [name])
            if (
                not strict_ownership
                and not classified_row.get("official_ownership_verified")
                and classified_row.get("source_type") in OFFICIAL_SOURCE_TYPES
            ):
                classified_row.update(
                    {
                        "canonical_entity_id": entity_id(name),
                        "canonical_entity_name": name,
                        "official_classification": "official",
                        "official_ownership_verified": True,
                    }
                )
            classified.append(classified_row)
        sources.extend(
            row
            for row in classified
            if row.get("official_ownership_verified")
            and row.get("canonical_entity_id") == entity_id(name)
        )
        deduped: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for row in sources:
            classified_row = classify_source(row, [name])
            if (
                not strict_ownership
                and not classified_row.get("official_ownership_verified")
                and classified_row.get("source_type") in OFFICIAL_SOURCE_TYPES
            ):
                classified_row.update(
                    {
                        "canonical_entity_id": entity_id(name),
                        "canonical_entity_name": name,
                        "official_classification": "official",
                        "official_ownership_verified": True,
                    }
                )
            if not classified_row.get("official_ownership_verified"):
                continue
            key = (
                _text(classified_row.get("canonical_url")).casefold().rstrip("/"),
                _text(classified_row.get("source_type")),
            )
            if not key[0] or key in seen:
                continue
            seen.add(key)
            deduped.append(classified_row)
        sources = deduped
        domains = sorted(
            {
                re.sub(r"^www\.", "", re.sub(r"^https?://", "", _text(row.get("canonical_url"))).split("/", 1)[0]).casefold()
                for row in sources
                if _text(row.get("canonical_url"))
            }
        )
        return {
            "entity_id": entity_id(profile.get("canonical_name") or name),
            "canonical_name": _text(profile.get("canonical_name") or name),
            "entity_role": role,
            "product_category": _text(profile.get("product_category")),
            "official_domains": domains or list(profile.get("official_domains") or []),
            "official_sources": sources,
        }

    def _comparator_candidates(
        self, package: dict[str, Any], task: dict[str, Any], root_name: str
    ) -> list[str]:
        values: list[str] = []
        for key in ("comparison_entities", "comparator_entities", "competitors", "alternatives"):
            raw = task.get(key)
            values.extend(raw if isinstance(raw, list) else [raw] if raw else [])
        entities = package.get("entities") if isinstance(package.get("entities"), dict) else {}
        for key in ("competitors", "alternatives"):
            values.extend(entities.get(key) or [])
        profile = self.kb.load(root_name)
        values.extend(profile.get("known_competitors") or [])
        values.extend(profile.get("related_entities") or [])
        cleaned: list[str] = []
        root_key = entity_id(root_name)
        for value in _unique([_text(row) for row in values]):
            key = entity_id(value)
            if key == root_key or root_key in key or any(
                marker in value.casefold()
                for marker in (" pricing", " review", " free trial", " comparison")
            ):
                continue
            cleaned.append(value)
        return cleaned

    @staticmethod
    def _ambiguous_weekly_candidates(task: dict[str, Any], root_name: str) -> list[str]:
        strategy = task.get("content_strategy") if isinstance(task.get("content_strategy"), dict) else {}
        return [
            _text(row.get("title"))
            for row in strategy.get("related_weekly_topics") or []
            if isinstance(row, dict) and _text(row.get("title")) != root_name
        ]

    @staticmethod
    def _root_entity(package: dict[str, Any], task: dict[str, Any]) -> str:
        explicit = _text(task.get("primary_entity") or task.get("root_title") or task.get("parent_keyword"))
        value = explicit or _text(package.get("keyword") or task.get("title") or task.get("slug"))
        value = re.sub(
            r"\b(review|pricing|comparison|alternatives?|pros|cons|20\d{2})\b",
            " ",
            value,
            flags=re.I,
        )
        value = re.sub(r"\b(and|versus|vs)\s*$", "", value, flags=re.I)
        return re.sub(r"\s+", " ", value).strip(" -:|") or _text(task.get("slug"))
