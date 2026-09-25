from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


def _tokens(value: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", value.casefold()))


def _bounded(value: Any, low: float = 0.0, high: float = 100.0) -> float:
    try:
        return max(low, min(high, float(value or 0)))
    except (TypeError, ValueError):
        return low


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().casefold() in {"1", "true", "yes", "y"}


@dataclass(frozen=True)
class TopicClassification:
    allowed: bool
    tier: int
    tier_id: str
    category: str
    subcategory: str
    reason: str


class EditorialTopicStrategy:
    """Controlled topic-universe and optional local commercial-signal layer.

    This augments the existing weekly planner.  It does not discover topics,
    approve roots, or write plans independently.
    """

    def __init__(self, root: Path):
        self.root = root.resolve()
        taxonomy_path = self.root / "config/editorial_topic_taxonomy.json"
        if not taxonomy_path.exists():
            taxonomy_path = Path(__file__).resolve().parents[1] / "config/editorial_topic_taxonomy.json"
        self.config = self._read_json(taxonomy_path, {})
        self.partner_registry = self._load_partner_registry()

    @staticmethod
    def _read_json(path: Path, default: Any) -> Any:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return default

    def classify(self, value: str) -> TopicClassification:
        normalized = " ".join(str(value or "").casefold().split())
        if any(term in normalized for term in self.config.get("excluded_topics", [])):
            return TopicClassification(False, 0, "OUT_OF_SCOPE", "excluded", "excluded", "Explicitly excluded topic")
        for tier in self.config.get("tiers", []):
            for category, phrases in (tier.get("categories") or {}).items():
                for phrase in phrases:
                    phrase_value = str(phrase).casefold()
                    if phrase_value in normalized or _tokens(phrase_value).issubset(_tokens(normalized)):
                        return TopicClassification(
                            True,
                            int(tier.get("tier") or 0),
                            str(tier.get("id") or ""),
                            str(category),
                            phrase_value.replace(" ", "_"),
                            f"Matched controlled taxonomy phrase: {phrase_value}",
                        )
        return TopicClassification(False, 0, "OUT_OF_SCOPE", "unclassified", "unclassified", "No controlled taxonomy match")

    def _load_partner_registry(self) -> list[dict[str, Any]]:
        json_path = self.root / "config/partner_opportunities.json"
        payload = self._read_json(json_path, {})
        rows = list(payload.get("opportunities") or []) if isinstance(payload, dict) else []
        csv_path = self.root / "data/imports/partner_opportunities.csv"
        if csv_path.is_file():
            try:
                with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
                    rows.extend(dict(row) for row in csv.DictReader(handle))
            except OSError:
                pass
        deduped: dict[str, dict[str, Any]] = {}
        for row in rows:
            if not isinstance(row, dict):
                continue
            key = str(
                row.get("opportunity_id") or row.get("program_name") or row.get("program") or row.get("name") or ""
            ).strip().casefold()
            if key:
                deduped[key] = dict(row)
        return list(deduped.values())

    def matching_partner_signals(self, candidate: dict[str, Any]) -> list[dict[str, Any]]:
        text = " ".join(str(candidate.get(key) or "") for key in ("topic", "primary_keyword", "category", "subcategory")).casefold()
        candidate_tokens = _tokens(text)
        matches = []
        for row in self.partner_registry:
            status = str(row.get("program_status") or row.get("status") or "active").casefold()
            if status not in {"active", "approved", "available"}:
                continue
            if not _as_bool(row.get("human_verified", False)):
                continue
            terms = " ".join(
                str(row.get(key) or "")
                for key in ("program_name", "program", "name", "vendor", "product", "category", "subcategory", "keywords")
            )
            overlap = candidate_tokens & _tokens(terms)
            if overlap:
                matches.append({**row, "matched_terms": sorted(overlap)})
        return matches

    def enrich_score(self, candidate: dict[str, Any]) -> dict[str, Any]:
        classification = self.classify(str(candidate.get("primary_keyword") or candidate.get("topic") or ""))
        base = _bounded(candidate.get("opportunity_score"))
        search_demand = _bounded(candidate.get("search_demand_score") or candidate.get("likely_search_demand") or base)
        commercial = _bounded(candidate.get("commercial_intent_score") or candidate.get("commercial_relevance") or (65 if "commercial" in str(candidate.get("search_intent")) else 45))
        affiliate = _bounded(candidate.get("affiliate_fit_score") or candidate.get("affiliate_monetization_score") or 0)
        research = _bounded(candidate.get("research_depth_score") or candidate.get("source_readiness", {}).get("verified_source_count", 0) * 20)
        freshness = _bounded(candidate.get("freshness_score") or 60)
        saturation = _bounded(candidate.get("saturation_penalty") or (25 if candidate.get("duplicate_risk", "").startswith("medium") else 0))
        drift = 0.0 if classification.allowed else 100.0
        matches = self.matching_partner_signals(candidate) if classification.allowed else []
        cap = _bounded(self.config.get("partner_signal_max_points", 8), 0, 8)
        partner_points = min(cap, len(matches) * 3.0)
        # Partner value is deliberately bounded and cannot rescue a weak base.
        non_partner = round(base * 0.45 + search_demand * 0.12 + commercial * 0.12 + affiliate * 0.08 + research * 0.13 + freshness * 0.10 - saturation * 0.20 - drift * 0.50, 2)
        minimum = _bounded(self.config.get("minimum_non_partner_score", 40), 0, 100)
        final = round(max(0.0, min(100.0, non_partner + (partner_points if non_partner >= minimum else 0.0))), 2)
        return {
            **candidate,
            "topic_tier": classification.tier,
            "topic_tier_id": classification.tier_id,
            "category": classification.category,
            "subcategory": classification.subcategory,
            "taxonomy_allowed": classification.allowed,
            "taxonomy_reason": classification.reason,
            "search_demand_score": search_demand,
            "commercial_intent_score": commercial,
            "affiliate_fit_score": affiliate,
            "research_depth_score": research,
            "freshness_score": freshness,
            "saturation_penalty": saturation,
            "topical_drift_penalty": drift,
            "partner_signal_points": partner_points if non_partner >= minimum else 0.0,
            "partner_signal_matches": matches,
            "non_partner_score": non_partner,
            "opportunity_score": final,
        }

    def fallback_inventory(self, candidates: Iterable[dict[str, Any]], minimum: int = 2) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        allowed = [self.enrich_score(row) for row in candidates]
        allowed = [row for row in allowed if row.get("taxonomy_allowed")]
        selected: list[dict[str, Any]] = []
        level_used = 0
        counts: dict[str, int] = {}
        for tier in (1, 2, 3):
            tier_rows = [row for row in allowed if int(row.get("topic_tier") or 0) == tier]
            counts[str(tier)] = len(tier_rows)
            selected.extend(tier_rows)
            if tier_rows:
                level_used = tier
            if len(selected) >= minimum:
                break
        selected.sort(key=lambda row: (-float(row.get("opportunity_score") or 0), int(row.get("topic_tier") or 9), str(row.get("slug") or "")))
        return selected, {
            "fallback_level_used": level_used,
            "tier_candidate_counts": counts,
            "partial_week": len(selected) == 1,
            "all_levels_exhausted": len(selected) == 0,
            "out_of_scope_rejected": len(list(candidates)) - len(allowed) if isinstance(candidates, list) else 0,
        }

    def partner_report(self) -> dict[str, Any]:
        candidates = []
        for row in self.partner_registry:
            classification = self.classify(" ".join(str(row.get(key) or "") for key in ("category", "subcategory", "keywords", "program_name")))
            status = str(row.get("program_status") or row.get("status") or "active").casefold()
            candidates.append({
                "opportunity_id": row.get("opportunity_id"),
                "program_name": row.get("program_name") or row.get("program") or row.get("name"),
                "status": status,
                "topic_tier": classification.tier,
                "category": classification.category,
                "eligible_as_signal": (
                    classification.allowed
                    and status in {"active", "approved", "available"}
                    and _as_bool(row.get("human_verified", False))
                ),
                "recommendation_only": True,
            })
        return {
            "schema_version": "partner_opportunity_report_v1",
            "input_method": "manual_local_json_or_csv",
            "paid_api_used": False,
            "api_key_required": False,
            "candidate_count": len(candidates),
            "candidates": candidates,
            "weekly_plan_changed": False,
        }
