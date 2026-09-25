from __future__ import annotations

import html
import json
import math
import os
import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, quote_plus, unquote, urlparse
from xml.etree import ElementTree as ET

import requests
from bs4 import BeautifulSoup

from config import settings
from modules.keyword_intelligence import score_affiliate_intent, score_competition


PREFERRED_TERMS = {
    "ai tools", "ai coding", "ai agent", "ai agents", "productivity", "marketing ai",
    "video ai", "image ai", "saas", "seo", "automation", "developer tools", "llm",
}
AI_SIGNAL_TERMS = {
    "ai", "artificial intelligence", "llm", "machine learning", "agentic", "copilot",
    "vector database", "generative", "prompt", "model hosting", "inference", "gpu",
}
COMMERCIAL_TERMS = {
    "review", "pricing", "alternatives", "alternative", "vs", "software", "platform",
    "tool", "tools", "automation", "builder", "assistant", "agent", "api", "saas",
}
EVERGREEN_TERMS = {
    "review", "pricing", "alternatives", "vs", "guide", "how to", "workflow", "software",
    "tool", "platform", "automation", "builder", "assistant",
}
NOISE_TERMS = {
    "stock", "shares", "lawsuit", "politics", "election", "war", "celebrity", "sports",
    "movie", "music", "crypto price", "earnings call",
}
SOURCE_WEIGHTS = {
    "google_trends": 1.0,
    "bing_trending": 0.9,
    "reddit": 0.95,
    "hacker_news": 1.0,
    "product_hunt": 1.0,
    "github_trending": 1.0,
    "x_twitter": 0.85,
    "linkedin": 0.75,
    "youtube_trending": 0.9,
    "ai_newsletters": 0.9,
    "local_keyword_intelligence": 0.55,
}

CANONICAL_TOPIC_SCORING_OWNER = "modules.ai_trend_discovery"
TOPIC_SCORING_VERSION = "topic_scoring_v2"
SCORE_SCALE = "0-100"
FOUNDATION_MAIN = "FOUNDATION_MAIN"
SOCIAL_HOT_UNCONFIRMED = "SOCIAL_HOT_UNCONFIRMED"
OFFICIAL_NEWS_STANDALONE = "OFFICIAL_NEWS_STANDALONE"

SELECTED_THRESHOLD_PASS = "SELECTED_THRESHOLD_PASS"
SELECTED_QUALITY_LIMITED = "SELECTED_QUALITY_LIMITED"
REJECTED_HARD_GATE = "REJECTED_HARD_GATE"
REJECTED_BELOW_ABSOLUTE_FLOOR = "REJECTED_BELOW_ABSOLUTE_FLOOR"
REJECTED_LOWER_RANK = "REJECTED_LOWER_RANK"
REJECTED_MAX_CAP_REACHED = "REJECTED_MAX_CAP_REACHED"

DEFAULT_TOPIC_SCORING_CONFIG: dict[str, Any] = {
    "version": TOPIC_SCORING_VERSION,
    "scale": SCORE_SCALE,
    "profiles": {
        FOUNDATION_MAIN: {
            "recommended_threshold": 65.0,
            "absolute_minimum_floor": 50.0,
            "maximum_roots": 5,
            "component_weights": {
                "search_volume_potential": 0.22,
                "low_competition_opportunity": 0.16,
                "affiliate_opportunity": 0.20,
                "evergreen_value": 0.14,
                "news_freshness": 0.16,
                "cpc_potential": 0.12,
            },
            "missing_data_policy": {
                "source_evidence": "REQUIRED",
                "search_volume_potential": "OPTIONAL",
                "low_competition_opportunity": "OPTIONAL",
                "affiliate_opportunity": "OPTIONAL",
                "evergreen_value": "OPTIONAL",
                "news_freshness": "OPTIONAL",
                "cpc_potential": "OPTIONAL",
            },
        },
        SOCIAL_HOT_UNCONFIRMED: {
            "social_interest_threshold": 60.0,
            "evidence_confidence_threshold": 35.0,
            "website_eligible_without_official_confirmation": False,
            "component_weights": {
                "freshness": 0.28,
                "discussion_velocity": 0.24,
                "audience_interest": 0.20,
                "novelty": 0.14,
                "source_traceability": 0.14,
            },
            "missing_data_policy": {
                "source_evidence": "REQUIRED",
                "official_confirmation": "OPTIONAL",
                "discussion_velocity": "OPTIONAL",
            },
        },
        OFFICIAL_NEWS_STANDALONE: {
            "recommended_threshold": 70.0,
            "absolute_minimum_floor": 60.0,
            "requires_official_confirmation": True,
            "component_weights": {
                "official_confirmation": 0.30,
                "user_impact": 0.22,
                "freshness": 0.18,
                "confirmed_detail_depth": 0.14,
                "novelty": 0.10,
                "commercial_significance": 0.06,
            },
            "missing_data_policy": {
                "official_confirmation": "REQUIRED",
                "source_evidence": "REQUIRED",
                "commercial_significance": "OPTIONAL",
            },
        },
    },
}


@dataclass
class TrendSignal:
    title: str
    source: str
    url: str = ""
    published_at: str = ""
    engagement: float = 0
    description: str = ""


@dataclass
class TopicCandidate:
    topic: str
    slug: str
    sources: list[str]
    source_urls: list[str]
    signals: int
    trend_score: int
    search_intent: str
    content_type: str
    affiliate_potential: str
    competition_level: str
    freshness_level: str
    estimated_business_value: str
    recommended_priority: str
    suggested_internal_links: list[str]
    suggested_article_angle: str
    suggested_video_angle: str
    classifications: list[str]
    search_volume_potential: int
    competition: int
    affiliate_opportunity: int
    evergreen_value: int
    news_freshness: int
    cpc_potential: int
    total_score: float
    confidence: str
    why_selected: list[str]
    already_published: bool = False


@dataclass
class DiscoveryResult:
    generated_at: str
    selected_topics: list[TopicCandidate]
    source_status: dict[str, dict[str, object]]
    candidates_evaluated: int
    published_topics_checked: int
    methodology: dict[str, object] = field(default_factory=dict)


def topic_scoring_config(config: dict[str, Any] | None = None) -> dict[str, Any]:
    configured = (config or {}).get("topic_scoring") if isinstance(config, dict) else None
    if not isinstance(configured, dict):
        return json.loads(json.dumps(DEFAULT_TOPIC_SCORING_CONFIG))
    merged = json.loads(json.dumps(DEFAULT_TOPIC_SCORING_CONFIG))
    for key, value in configured.items():
        if key != "profiles":
            merged[key] = value
    profiles = configured.get("profiles")
    if isinstance(profiles, dict):
        for lane, profile in profiles.items():
            if not isinstance(profile, dict):
                continue
            base = merged["profiles"].setdefault(lane, {})
            for key, value in profile.items():
                if isinstance(value, dict) and isinstance(base.get(key), dict):
                    base[key].update(value)
                else:
                    base[key] = value
    return merged


def topic_scoring_profile(content_lane: str = FOUNDATION_MAIN, config: dict[str, Any] | None = None) -> dict[str, Any]:
    scoring = topic_scoring_config(config)
    profiles = scoring.get("profiles") if isinstance(scoring.get("profiles"), dict) else {}
    profile = profiles.get(content_lane) or profiles.get(FOUNDATION_MAIN) or {}
    result = dict(profile)
    result["content_lane"] = content_lane
    result["version"] = str(scoring.get("version") or TOPIC_SCORING_VERSION)
    result["scale"] = str(scoring.get("scale") or SCORE_SCALE)
    return result


def normalize_component_values(values: list[float]) -> list[float]:
    if not values:
        return []
    numeric = [float(value) for value in values]
    low = min(numeric)
    high = max(numeric)
    if high == low:
        return [50.0 for _ in numeric]
    return [round((value - low) * 100.0 / (high - low), 1) for value in numeric]


def _candidate_value(candidate: Any, *keys: str, default: Any = None) -> Any:
    for key in keys:
        if isinstance(candidate, dict) and key in candidate:
            return candidate.get(key)
        if not isinstance(candidate, dict) and hasattr(candidate, key):
            return getattr(candidate, key)
    return default


def _float_or_none(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def _normalize_score_value(value: Any) -> tuple[float | None, str, str]:
    number = _float_or_none(value)
    if number is None:
        return None, "missing", "missing component value"
    if 0.0 <= number <= 1.0:
        return round(number * 100.0, 1), "normalized_0_1_to_0_100", "0-1 value normalized to 0-100 scale"
    return round(max(0.0, min(100.0, number)), 1), "available", "0-100 value"


def _source_count(candidate: Any) -> int:
    explicit = _float_or_none(_candidate_value(candidate, "source_count"))
    if explicit is not None:
        return int(explicit)
    readiness = _candidate_value(candidate, "source_readiness", default={})
    if isinstance(readiness, dict):
        ready_count = _float_or_none(readiness.get("source_count"))
        if ready_count is not None:
            return int(ready_count)
    urls = _candidate_value(candidate, "source_urls", "sources", default=[])
    return len(list(urls or []))


def _component_raw_value(candidate: Any, component: str) -> Any:
    if component == "low_competition_opportunity":
        value = _candidate_value(candidate, "low_competition_opportunity")
        if value is not None:
            return value
        competition = _candidate_value(candidate, "competition_difficulty_score", "competition")
        competition_score = _float_or_none(competition)
        return None if competition_score is None else 100.0 - competition_score
    aliases = {
        "search_volume_potential": ("search_volume_potential", "search_intent_score"),
        "affiliate_opportunity": ("affiliate_opportunity", "affiliate_monetization_score"),
        "evergreen_value": ("evergreen_value", "product_availability_score"),
        "news_freshness": ("news_freshness", "content_freshness_score", "freshness"),
        "cpc_potential": ("cpc_potential", "commercial_significance"),
        "freshness": ("freshness", "news_freshness", "content_freshness_score"),
        "discussion_velocity": ("discussion_velocity", "engagement", "trend_score"),
        "audience_interest": ("audience_interest", "search_volume_potential", "search_intent_score"),
        "novelty": ("novelty", "news_freshness", "content_freshness_score"),
        "source_traceability": ("source_traceability", "verified_source_score"),
        "official_confirmation": ("official_confirmation_score", "official_confirmation"),
        "user_impact": ("user_impact", "search_volume_potential", "search_intent_score"),
        "confirmed_detail_depth": ("confirmed_detail_depth", "product_availability_score"),
        "commercial_significance": ("commercial_significance", "affiliate_opportunity", "affiliate_monetization_score"),
    }
    return _candidate_value(candidate, *aliases.get(component, (component,)))


def _is_true(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "confirmed", "pass", "passed"}


def score_topic_candidate(
    candidate: Any,
    *,
    content_lane: str = FOUNDATION_MAIN,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    profile = topic_scoring_profile(content_lane, config)
    weights = dict(profile.get("component_weights") or {})
    missing_policy = dict(profile.get("missing_data_policy") or {})
    not_applicable = set(_candidate_value(candidate, "not_applicable_components", default=[]) or [])
    components: dict[str, dict[str, Any]] = {}
    hard_gate_results: list[dict[str, Any]] = []
    total_weight = 0.0
    weighted_total = 0.0
    available_weight = 0.0
    missing_fields: list[str] = []
    scale_warnings: list[str] = []

    for component, raw_weight in weights.items():
        weight = float(raw_weight)
        if component in not_applicable:
            components[component] = {
                "raw_value": None,
                "normalized_value": None,
                "weight": weight,
                "status": "NOT_APPLICABLE",
                "missing_policy": "NOT_APPLICABLE",
                "reason": "Excluded from denominator for this candidate.",
            }
            continue
        total_weight += weight
        normalized, status, reason = _normalize_score_value(_component_raw_value(candidate, component))
        policy = str(missing_policy.get(component) or "OPTIONAL")
        raw_value = _component_raw_value(candidate, component)
        if normalized is None:
            if policy == "REQUIRED":
                hard_gate_results.append({"gate": component, "passed": False, "reason": f"required {component} missing"})
                normalized = 0.0
            else:
                missing_fields.append(component)
                normalized = 50.0
                reason = "Optional component missing; neutral 50 used and score confidence reduced."
        else:
            available_weight += weight
            if status == "normalized_0_1_to_0_100":
                scale_warnings.append(f"{component}: {reason}")
        weighted_total += normalized * weight
        components[component] = {
            "raw_value": raw_value,
            "normalized_value": normalized,
            "weight": weight,
            "status": status if raw_value is not None else "OPTIONAL_MISSING_NEUTRAL",
            "missing_policy": policy,
            "reason": reason,
        }

    source_count = _source_count(candidate)
    if missing_policy.get("source_evidence") == "REQUIRED" and source_count < 1:
        hard_gate_results.append({"gate": "source_evidence", "passed": False, "reason": "missing required source evidence"})
    if _is_true(_candidate_value(candidate, "duplicate_collision")):
        hard_gate_results.append({"gate": "duplicate_collision", "passed": False, "reason": "duplicate root or canonical collision"})
    readiness = _candidate_value(candidate, "source_readiness", default={})
    if isinstance(readiness, dict) and isinstance(readiness.get("collision_result"), dict):
        if readiness["collision_result"].get("has_collision"):
            hard_gate_results.append({"gate": "duplicate_collision", "passed": False, "reason": "source-readiness collision result is true"})
    if _candidate_value(candidate, "relevant_to_site", default=True) is False:
        hard_gate_results.append({"gate": "site_relevance", "passed": False, "reason": "topic is not relevant to this site"})
    if content_lane == OFFICIAL_NEWS_STANDALONE and bool(profile.get("requires_official_confirmation", True)):
        if not _is_true(_candidate_value(candidate, "official_confirmation", "official_confirmation_status")):
            hard_gate_results.append({"gate": "official_confirmation", "passed": False, "reason": "official confirmation is required for website news candidacy"})

    denominator = total_weight or 1.0
    computed_total_score = round(max(0.0, min(100.0, weighted_total / denominator)), 1)
    total_score = computed_total_score
    scoring_adjustments: list[str] = []
    existing_total = _float_or_none(_candidate_value(candidate, "total_score"))
    if existing_total is not None and abs(existing_total - computed_total_score) > 0.05:
        total_score = round(max(0.0, min(100.0, existing_total)), 1)
        scoring_adjustments.append(
            f"workflow-adjusted total_score {total_score} used instead of component recompute {computed_total_score}"
        )
    score_confidence = round(available_weight / denominator, 2) if denominator else 0.0
    recommended_threshold = float(profile.get("recommended_threshold", profile.get("social_interest_threshold", 0)) or 0)
    absolute_floor = float(profile.get("absolute_minimum_floor", 0) or 0)
    hard_gates_passed = not hard_gate_results
    return {
        "candidate_id": str(_candidate_value(candidate, "candidate_id", "slug", default="")),
        "content_lane": content_lane,
        "title": str(_candidate_value(candidate, "title", "keyword", "topic", default="")),
        "scoring_owner": CANONICAL_TOPIC_SCORING_OWNER,
        "scoring_version": str(profile.get("version") or TOPIC_SCORING_VERSION),
        "score_scale": str(profile.get("scale") or SCORE_SCALE),
        "raw_component_values": {name: data["raw_value"] for name, data in components.items()},
        "normalized_component_values": {name: data["normalized_value"] for name, data in components.items()},
        "component_weights": {name: data["weight"] for name, data in components.items()},
        "component_reports": components,
        "missing_fields": missing_fields,
        "weights_applied": round(total_weight, 4),
        "weights_available": round(available_weight, 4),
        "weights_redistributed": False,
        "hard_gate_results": hard_gate_results or [{"gate": "all_required_gates", "passed": True, "reason": "PASS"}],
        "hard_gates_passed": hard_gates_passed,
        "score_confidence": score_confidence,
        "total_score": total_score,
        "computed_total_score": computed_total_score,
        "scoring_adjustments": scoring_adjustments,
        "recommended_threshold": recommended_threshold,
        "absolute_minimum_floor": absolute_floor,
        "rank": 0,
        "selection_result": "",
        "reason": "",
        "scale_warnings": scale_warnings,
    }


def select_topic_candidates(
    candidates: list[dict[str, Any]],
    *,
    count: int,
    content_lane: str = FOUNDATION_MAIN,
    config: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    max_count = min(int(count), int(topic_scoring_profile(content_lane, config).get("maximum_roots", count) or count))
    scored: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for item in candidates:
        report = score_topic_candidate(item, content_lane=content_lane, config=config)
        scored.append((item, report))
    scored.sort(key=lambda row: (-float(row[1]["total_score"]), str(row[1]["title"]).lower()))
    for rank, (_, report) in enumerate(scored, start=1):
        report["rank"] = rank

    selected: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    eligible: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for item, report in scored:
        if not report["hard_gates_passed"]:
            report["selection_result"] = REJECTED_HARD_GATE
            report["reason"] = "; ".join(str(gate.get("reason") or "") for gate in report["hard_gate_results"] if not gate.get("passed"))
            rejected.append(_candidate_rejection(item, report))
            continue
        if float(report["total_score"]) < float(report["absolute_minimum_floor"]):
            report["selection_result"] = REJECTED_BELOW_ABSOLUTE_FLOOR
            report["reason"] = f"score {report['total_score']} below absolute minimum floor {report['absolute_minimum_floor']}"
            rejected.append(_candidate_rejection(item, report))
            continue
        eligible.append((item, report))

    threshold_pass = [row for row in eligible if float(row[1]["total_score"]) >= float(row[1]["recommended_threshold"])]
    quality_limited = [row for row in eligible if row not in threshold_pass]
    for item, report in [*threshold_pass, *quality_limited]:
        if len(selected) >= max_count:
            report["selection_result"] = REJECTED_MAX_CAP_REACHED
            report["reason"] = f"maximum foundation roots {max_count} already selected"
            rejected.append(_candidate_rejection(item, report))
            continue
        selected_item = dict(item)
        if float(report["total_score"]) >= float(report["recommended_threshold"]):
            report["selection_result"] = SELECTED_THRESHOLD_PASS
            report["reason"] = "Passed hard gates and met the recommended quality threshold."
        else:
            report["selection_result"] = SELECTED_QUALITY_LIMITED
            report["reason"] = "Passed hard gates and stayed above the absolute floor; selected as quality-limited fill from the strongest available candidates."
        selected_item["topic_score_report"] = report
        selected_item["selection_result"] = report["selection_result"]
        selected_item["selection_reason"] = report["reason"]
        selected_item["rank"] = report["rank"]
        selected.append(selected_item)

    selected_ids = {str(item.get("slug") or item.get("keyword") or "") for item in selected}
    for item, report in eligible:
        item_id = str(item.get("slug") or item.get("keyword") or "")
        if item_id in selected_ids or report.get("selection_result"):
            continue
        report["selection_result"] = REJECTED_LOWER_RANK
        report["reason"] = "Eligible but ranked below selected candidates."
        rejected.append(_candidate_rejection(item, report))

    summary = {
        "scoring_owner": CANONICAL_TOPIC_SCORING_OWNER,
        "scoring_profile": content_lane,
        "scoring_version": TOPIC_SCORING_VERSION,
        "recommended_threshold": float(topic_scoring_profile(content_lane, config).get("recommended_threshold", 0) or 0),
        "absolute_minimum_floor": float(topic_scoring_profile(content_lane, config).get("absolute_minimum_floor", 0) or 0),
        "max_foundation_roots": max_count,
        "candidates_scored": len(scored),
        "candidates_hard_gate_passed": len(eligible),
        "candidates_threshold_passed": len(threshold_pass),
        "candidates_above_absolute_floor": len(eligible),
        "foundation_roots_selected": len(selected),
        "selected_threshold_pass_count": sum(1 for item in selected if item.get("selection_result") == SELECTED_THRESHOLD_PASS),
        "selected_quality_limited_count": sum(1 for item in selected if item.get("selection_result") == SELECTED_QUALITY_LIMITED),
        "quality_limited": any(item.get("selection_result") == SELECTED_QUALITY_LIMITED for item in selected),
        "ranked_candidates": [report for _, report in scored],
    }
    return selected, rejected, summary


def _candidate_rejection(item: dict[str, Any], report: dict[str, Any]) -> dict[str, Any]:
    return {
        "keyword": str(item.get("keyword") or item.get("topic") or ""),
        "slug": str(item.get("slug") or ""),
        "source_count": _source_count(item),
        "unique_source_domains": list((item.get("source_readiness") or {}).get("unique_source_domains") or []),
        "reason": str(report.get("reason") or report.get("selection_result") or "rejected"),
        "selection_result": str(report.get("selection_result") or ""),
        "rank": int(report.get("rank") or 0),
        "total_score": float(report.get("total_score") or 0),
        "topic_score_report": report,
    }


def score_social_hot_candidate(candidate: dict[str, Any], *, config: dict[str, Any] | None = None) -> dict[str, Any]:
    report = score_topic_candidate(candidate, content_lane=SOCIAL_HOT_UNCONFIRMED, config=config)
    evidence = report["normalized_component_values"].get("source_traceability")
    social_interest = report["total_score"]
    official_status = "CONFIRMED" if _is_true(candidate.get("official_confirmation_status") or candidate.get("official_confirmation")) else "UNCONFIRMED"
    return {
        "hot_topic_id": str(candidate.get("candidate_id") or candidate.get("slug") or ""),
        "social_interest_score": social_interest,
        "evidence_confidence_score": float(evidence if evidence is not None else 0),
        "official_confirmation_status": official_status,
        "routing_result": SOCIAL_HOT_UNCONFIRMED,
        "website_eligible": False,
        "score_report": report,
    }


def score_official_news_candidate(candidate: dict[str, Any], *, config: dict[str, Any] | None = None) -> dict[str, Any]:
    report = score_topic_candidate(candidate, content_lane=OFFICIAL_NEWS_STANDALONE, config=config)
    website_eligible = bool(report["hard_gates_passed"] and report["total_score"] >= report["absolute_minimum_floor"])
    return {
        "candidate_id": str(candidate.get("candidate_id") or candidate.get("slug") or ""),
        "official_news_score": report["total_score"],
        "official_confirmation_status": "CONFIRMED" if _is_true(candidate.get("official_confirmation_status") or candidate.get("official_confirmation")) else "UNCONFIRMED",
        "routing_result": OFFICIAL_NEWS_STANDALONE,
        "website_eligible": website_eligible,
        "score_report": report,
    }


class TrendDiscoveryEngine:
    def __init__(self, timeout: int | None = None, max_per_source: int = 40, read_only: bool = False) -> None:
        self.timeout = timeout or int(os.getenv("REQUEST_TIMEOUT", "20"))
        self.max_per_source = max_per_source
        self.read_only = read_only
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": os.getenv("USER_AGENT", "SmileAIReviewHub-TrendDiscovery/1.0")})
        self.source_status: dict[str, dict[str, object]] = {}
        self.published = list(discover_published_topics())
        self.affiliate_brands = set(load_affiliate_brands())

    def run(self, limit: int = 10) -> DiscoveryResult:
        signals: list[TrendSignal] = []
        connectors: list[tuple[str, Callable[[], list[TrendSignal]]]] = [
            ("google_trends", self.google_trends),
            ("bing_trending", self.bing_trending),
            ("reddit", self.reddit),
            ("hacker_news", self.hacker_news),
            ("product_hunt", self.product_hunt),
            ("github_trending", self.github_trending),
            ("x_twitter", self.x_twitter),
            ("linkedin", self.linkedin),
            ("youtube_trending", self.youtube_trending),
            ("ai_newsletters", self.ai_newsletters),
            ("local_keyword_intelligence", self.local_keyword_intelligence),
        ]
        for name, connector in connectors:
            try:
                found = connector()[: self.max_per_source]
                signals.extend(found)
                self.source_status[name] = {"status": "ok" if found else "empty", "signals": len(found)}
            except MissingCredential as exc:
                self.source_status[name] = {"status": "unavailable", "signals": 0, "detail": str(exc)}
            except Exception as exc:
                self.source_status[name] = {"status": "error", "signals": 0, "detail": f"{type(exc).__name__}: {exc}"}

        candidates = self.enrich_candidate_sources(self.aggregate(signals), pool_limit=max(limit * 2, limit))
        eligible = [candidate for candidate in candidates if not candidate.already_published]
        selected = sorted(eligible, key=lambda item: (-item.total_score, item.competition, item.topic))[:limit]
        return DiscoveryResult(
            generated_at=datetime.now(timezone.utc).isoformat(),
            selected_topics=selected,
            source_status=self.source_status,
            candidates_evaluated=len(candidates),
            published_topics_checked=len(self.published),
            methodology={
                "weights": {
                    "search_volume_potential": 0.22,
                    "low_competition_opportunity": 0.16,
                    "affiliate_opportunity": 0.20,
                    "evergreen_value": 0.14,
                    "news_freshness": 0.16,
                    "cpc_potential": 0.12,
                },
                "published_content_filter": "Exact slug, normalized title, and token similarity >= 0.72 are excluded.",
                "note": "Scores are directional opportunity estimates, not paid keyword-volume measurements.",
            },
        )

    def aggregate(self, signals: list[TrendSignal]) -> list[TopicCandidate]:
        groups: dict[str, list[TrendSignal]] = defaultdict(list)
        for signal in signals:
            topic = normalize_topic(signal.title)
            if not is_relevant(topic + " " + signal.description):
                continue
            key = topic_key(topic)
            if key:
                groups[key].append(signal)
        candidates = [self.score_group(items) for items in groups.values()]
        return sorted(candidates, key=lambda item: (-item.total_score, item.topic))

    def enrich_candidate_sources(self, candidates: list[TopicCandidate], *, pool_limit: int) -> list[TopicCandidate]:
        enriched: list[TopicCandidate] = []
        for candidate in candidates[:pool_limit]:
            supplemental = [
                signal
                for signal in self.bing_sources_for_topic(candidate.topic)
                if supplemental_source_matches_topic(candidate.topic, signal)
            ]
            official_homepages = [
                homepage
                for url in candidate.source_urls
                if source_domain(url) == "github.com"
                for homepage in [self.github_repository_homepage(url)]
                if homepage
            ]
            if supplemental:
                candidate.source_urls = independent_source_urls(
                    [*candidate.source_urls, *official_homepages, *[signal.url for signal in supplemental if signal.url]]
                )
                candidate.sources = sorted(set([*candidate.sources, *[signal.source for signal in supplemental]]))
                candidate.signals += len(supplemental)
                if len(candidate.source_urls) >= 2 and candidate.confidence == "low":
                    candidate.confidence = "medium"
                    candidate.why_selected = [*candidate.why_selected, "Supplemental Bing source aggregation found at least two independent source domains."]
            else:
                candidate.source_urls = independent_source_urls([*candidate.source_urls, *official_homepages])
            if official_homepages:
                candidate.sources = sorted(set([*candidate.sources, "official_project_homepage"]))
                if len(candidate.source_urls) >= 2 and candidate.confidence == "low":
                    candidate.confidence = "medium"
                    candidate.why_selected = [*candidate.why_selected, "Official project homepage confirmed from GitHub repository metadata."]
            enriched.append(candidate)
        enriched.extend(candidates[pool_limit:])
        return enriched

    def github_repository_homepage(self, repository_url: str) -> str:
        parsed = urlparse(normalize_source_url(repository_url))
        if source_domain(repository_url) != "github.com":
            return ""
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) < 2:
            return ""
        try:
            payload = self.get_json(f"https://api.github.com/repos/{parts[0]}/{parts[1]}")
        except Exception:
            return ""
        homepage = normalize_source_url(str(payload.get("homepage") or ""))
        homepage_domain = source_domain(homepage)
        if not homepage or not homepage_domain or homepage_domain == "github.com":
            return ""
        return homepage

    def score_group(self, signals: list[TrendSignal]) -> TopicCandidate:
        representative = choose_representative(signals)
        topic = editorial_topic(representative)
        scoring_text = " ".join([topic, *[signal.description for signal in signals]])
        sources = sorted({signal.source for signal in signals})
        source_strength = sum(SOURCE_WEIGHTS.get(source, 0.5) for source in sources)
        engagement = sum(max(0, signal.engagement) for signal in signals)
        preferred = keyword_hits(scoring_text, PREFERRED_TERMS)
        commercial = keyword_hits(scoring_text, COMMERCIAL_TERMS)
        evergreen_hits = keyword_hits(scoring_text, EVERGREEN_TERMS)

        search = clamp(35 + len(sources) * 9 + min(25, math.log10(engagement + 1) * 8) + preferred * 4)
        competition = score_competition(topic.lower(), {})
        if len(sources) >= 3:
            competition = clamp(competition + 8)
        affiliate = score_affiliate_intent(topic.lower(), {})
        if any(brand in topic.lower() for brand in self.affiliate_brands):
            affiliate = clamp(affiliate + 22)
        affiliate = clamp(affiliate + commercial * 5 + min(12, len(sources) * 2))
        evergreen = clamp(35 + evergreen_hits * 12 + commercial * 4 - (10 if looks_like_news_only(topic) else 0))
        freshness = clamp(30 + len(sources) * 12 + source_strength * 5 + min(20, math.log10(engagement + 1) * 6))
        cpc = clamp(25 + affiliate * 0.45 + commercial * 7 + preferred * 3)
        low_competition = 100 - competition
        total = round(
            search * 0.22
            + low_competition * 0.16
            + affiliate * 0.20
            + evergreen * 0.14
            + freshness * 0.16
            + cpc * 0.12,
            1,
        )
        published_match = published_match_for(topic, self.published)
        reasons = build_reasons(topic, sources, search, competition, affiliate, evergreen, freshness, cpc)
        content_type = classify_content_type(topic)
        classifications = classify_topic(topic, content_type, freshness, evergreen)
        confidence = "high" if len(sources) >= 3 else "medium" if len(sources) >= 2 else "low"
        return TopicCandidate(
            topic=topic,
            slug=slugify(topic),
            sources=sources,
            source_urls=independent_source_urls([signal.url for signal in signals if signal.url]),
            signals=len(signals),
            trend_score=freshness,
            search_intent=classify_search_intent(topic),
            content_type=content_type,
            affiliate_potential=level_from_score(affiliate),
            competition_level=competition_level(competition),
            freshness_level=level_from_score(freshness),
            estimated_business_value=business_value_level(affiliate, cpc, evergreen),
            recommended_priority=priority_level(total),
            suggested_internal_links=suggest_internal_links(topic, content_type),
            suggested_article_angle=suggest_article_angle(topic, content_type),
            suggested_video_angle=suggest_video_angle(topic, content_type),
            classifications=classifications,
            search_volume_potential=search,
            competition=competition,
            affiliate_opportunity=affiliate,
            evergreen_value=evergreen,
            news_freshness=freshness,
            cpc_potential=cpc,
            total_score=total,
            confidence=confidence,
            why_selected=reasons,
            already_published=bool(published_match),
        )

    def google_trends(self) -> list[TrendSignal]:
        return self.rss("https://trends.google.com/trending/rss?geo=US", "google_trends")

    def bing_trending(self) -> list[TrendSignal]:
        queries = ("AI software", "AI agent SaaS", "AI coding tools", "marketing automation AI")
        result: list[TrendSignal] = []
        for query in queries:
            result.extend(self.rss(f"https://www.bing.com/news/search?q={quote_plus(query)}&format=rss", "bing_trending"))
        return result

    def bing_sources_for_topic(self, topic: str) -> list[TrendSignal]:
        query = clean_topic_query(topic)
        if not query:
            return []
        try:
            return self.rss(f"https://www.bing.com/news/search?q={quote_plus(query)}&format=rss", "bing_topic_source")
        except Exception:
            return []

    def reddit(self) -> list[TrendSignal]:
        result: list[TrendSignal] = []
        for subreddit in ("artificial", "LocalLLaMA", "SaaS", "SEO", "productivity", "ChatGPTCoding"):
            try:
                data = self.get_json(f"https://www.reddit.com/r/{subreddit}/hot.json?limit=15")
                for child in data.get("data", {}).get("children", []):
                    item = child.get("data", {})
                    result.append(TrendSignal(item.get("title", ""), "reddit", "https://reddit.com" + item.get("permalink", ""), engagement=float(item.get("score", 0))))
            except Exception:
                try:
                    result.extend(self.rss(f"https://www.reddit.com/r/{subreddit}/hot/.rss", "reddit"))
                except Exception:
                    continue
        return result

    def hacker_news(self) -> list[TrendSignal]:
        result: list[TrendSignal] = []
        ids = self.get_json("https://hacker-news.firebaseio.com/v0/topstories.json")[:60]
        for item_id in ids:
            item = self.get_json(f"https://hacker-news.firebaseio.com/v0/item/{item_id}.json")
            result.append(TrendSignal(item.get("title", ""), "hacker_news", item.get("url", ""), engagement=float(item.get("score", 0))))
        return result

    def product_hunt(self) -> list[TrendSignal]:
        return self.rss("https://www.producthunt.com/feed", "product_hunt")

    def github_trending(self) -> list[TrendSignal]:
        response = self.get("https://github.com/trending?since=daily")
        soup = BeautifulSoup(response.text, "html.parser")
        result: list[TrendSignal] = []
        for article in soup.select("article.Box-row"):
            link = article.select_one("h2 a")
            if not link:
                continue
            repo = clean_text(link.get_text(" "))
            desc = clean_text(article.select_one("p").get_text(" ") if article.select_one("p") else "")
            stars = clean_text(article.select_one("span.d-inline-block.float-sm-right").get_text(" ") if article.select_one("span.d-inline-block.float-sm-right") else "")
            result.append(TrendSignal(f"{repo}: {desc}", "github_trending", "https://github.com" + link.get("href", ""), engagement=parse_number(stars), description=desc))
        return result

    def x_twitter(self) -> list[TrendSignal]:
        bearer = os.getenv("TWITTER_BEARER_TOKEN", "").strip()
        if not bearer:
            raise MissingCredential("Set TWITTER_BEARER_TOKEN to enable X recent-search discovery.")
        headers = {"Authorization": f"Bearer {bearer}"}
        query = "(AI tool OR AI agent OR SaaS OR AI coding) lang:en -is:retweet"
        data = self.get_json("https://api.twitter.com/2/tweets/search/recent?max_results=50&tweet.fields=public_metrics&query=" + quote_plus(query), headers=headers)
        return [
            TrendSignal(item.get("text", ""), "x_twitter", engagement=sum(item.get("public_metrics", {}).values()))
            for item in data.get("data", [])
        ]

    def linkedin(self) -> list[TrendSignal]:
        token = os.getenv("LINKEDIN_ACCESS_TOKEN", "").strip()
        if not token:
            raise MissingCredential("LinkedIn does not expose public trending search; set LINKEDIN_ACCESS_TOKEN and a permitted discovery endpoint.")
        raise MissingCredential("LinkedIn token exists, but no approved organization-post discovery endpoint is configured.")

    def youtube_trending(self) -> list[TrendSignal]:
        key = os.getenv("YOUTUBE_API_KEY", "").strip()
        if not key:
            raise MissingCredential("Set YOUTUBE_API_KEY to enable YouTube trending discovery.")
        params = f"part=snippet,statistics&chart=mostPopular&regionCode=US&videoCategoryId=28&maxResults=50&key={key}"
        data = self.get_json("https://www.googleapis.com/youtube/v3/videos?" + params)
        return [
            TrendSignal(
                item.get("snippet", {}).get("title", ""),
                "youtube_trending",
                f"https://www.youtube.com/watch?v={item.get('id', '')}",
                engagement=float(item.get("statistics", {}).get("viewCount", 0)),
                description=item.get("snippet", {}).get("description", ""),
            )
            for item in data.get("items", [])
        ]

    def ai_newsletters(self) -> list[TrendSignal]:
        feeds = [
            "https://www.deeplearning.ai/the-batch/feed/",
            "https://importai.substack.com/feed",
            "https://www.bensbites.com/feed",
            "https://www.therundown.ai/feed",
        ]
        result: list[TrendSignal] = []
        for feed in feeds:
            try:
                result.extend(self.rss(feed, "ai_newsletters"))
            except Exception:
                continue
        return result

    def local_keyword_intelligence(self) -> list[TrendSignal]:
        path = settings.data_dir / "keyword_intelligence_report.csv"
        if not path.exists():
            return []
        import csv

        result: list[TrendSignal] = []
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                if str(row.get("current_page_exists", "")).lower() == "true":
                    continue
                priority = parse_number(row.get("priority_score", "0"))
                if priority >= 55:
                    result.append(TrendSignal(row.get("keyword", ""), "local_keyword_intelligence", engagement=priority))
        return result

    def rss(self, url: str, source: str) -> list[TrendSignal]:
        response = self.get(url)
        root = ET.fromstring(response.content)
        result: list[TrendSignal] = []
        for item in root.findall(".//item") + root.findall(".//{http://www.w3.org/2005/Atom}entry"):
            title = xml_text(item, ("title", "{http://www.w3.org/2005/Atom}title"))
            link = xml_text(item, ("link", "{http://www.w3.org/2005/Atom}link"))
            if not link:
                atom_link = item.find("{http://www.w3.org/2005/Atom}link")
                link = atom_link.get("href", "") if atom_link is not None else ""
            published = xml_text(item, ("pubDate", "published", "{http://www.w3.org/2005/Atom}published"))
            description = xml_text(
                item,
                ("description", "summary", "{http://www.w3.org/2005/Atom}summary", "{http://purl.org/rss/1.0/modules/content/}encoded"),
            )
            result.append(TrendSignal(title, source, link, published, description=clean_text(description)))
        return result

    def get(self, url: str, headers: dict[str, str] | None = None) -> requests.Response:
        response = self.session.get(url, headers=headers, timeout=self.timeout)
        response.raise_for_status()
        return response

    def get_json(self, url: str, headers: dict[str, str] | None = None) -> object:
        return self.get(url, headers=headers).json()


class MissingCredential(RuntimeError):
    pass


@lru_cache(maxsize=1)
def discover_published_topics() -> tuple[dict[str, object], ...]:
    roots = [settings.site_output_dir, settings.base_dir / "docs", settings.data_dir / "published_static_pages"]
    records: dict[str, dict[str, object]] = {}
    for root in roots:
        if not root.exists():
            continue
        for page in root.rglob("index.html"):
            rel = page.relative_to(root).as_posix()
            if rel.startswith(("go/", "vi/")):
                continue
            source = page.read_text(encoding="utf-8", errors="ignore")
            title = clean_text(first_match(source, r"<h1\b[^>]*>(.*?)</h1>") or first_match(source, r"<title\b[^>]*>(.*?)</title>"))
            slug = rel[: -len("/index.html")] if rel != "index.html" else "home"
            key = slugify(slug)
            if title and key not in records:
                records[key] = {"slug": key, "title": title, "tokens": token_set(title + " " + slug)}
    return tuple(records.values())


@lru_cache(maxsize=1)
def load_affiliate_brands() -> frozenset[str]:
    import csv

    brands: set[str] = set()
    for filename in ("offer_scores.csv", "affiliate_links.csv", "offers.csv"):
        path = settings.data_dir / filename
        if not path.exists():
            continue
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                brand = str(row.get("brand_name") or row.get("offer_id") or "").strip().lower()
                if brand:
                    brands.add(brand)
    return frozenset(brands)


def published_match_for(topic: str, published: list[dict[str, object]]) -> str:
    slug = slugify(topic)
    tokens = token_set(topic)
    for page in published:
        if slug == page["slug"] or slug in str(page["slug"]) or str(page["slug"]) in slug:
            return str(page["slug"])
        page_tokens = set(page["tokens"])
        union = tokens | page_tokens
        if union and len(tokens & page_tokens) / len(union) >= 0.72:
            return str(page["slug"])
    return ""


def normalize_topic(value: str) -> str:
    text = clean_text(value)
    text = re.sub(r"\s+[-|]\s+[^-|]{3,80}$", "", text)
    return text[:180].strip(" -:|")


def editorial_topic(signal: TrendSignal) -> str:
    topic = normalize_topic(signal.title)
    if signal.source == "github_trending" and ":" in topic:
        repo = re.sub(r"\s+/\s+", "/", topic.split(":", 1)[0]).strip()
        repo = repo.split("/", 1)[-1].strip()
        return f"{repo} Review 2026"
    if len(topic) > 110:
        first = re.split(r"[.!?]", topic, maxsplit=1)[0].strip()
        return (first if len(first) >= 20 else topic[:100]).strip(" -:|")
    return topic


def topic_key(topic: str) -> str:
    tokens = [token for token in token_set(topic) if token not in {"the", "a", "an", "new", "launches", "launch"}]
    return " ".join(sorted(tokens))


def is_relevant(topic: str) -> bool:
    lower = topic.lower()
    if len(topic) < 8 or any(phrase_present(lower, term) for term in NOISE_TERMS):
        return False
    return bool(keyword_hits(lower, PREFERRED_TERMS) or keyword_hits(lower, AI_SIGNAL_TERMS))


def choose_representative(signals: list[TrendSignal]) -> TrendSignal:
    return max(signals, key=lambda item: (item.engagement, len(item.title)))


def build_reasons(topic: str, sources: list[str], search: int, competition: int, affiliate: int, evergreen: int, freshness: int, cpc: int) -> list[str]:
    reasons = [f"Detected across {len(sources)} source(s): {', '.join(sources)}."]
    if search >= 65:
        reasons.append("Strong directional search-demand potential.")
    if competition <= 50:
        reasons.append("Competition estimate is low-to-medium.")
    if affiliate >= 65:
        reasons.append("High commercial and affiliate-content fit.")
    if evergreen >= 65:
        reasons.append("Can remain useful after the current news cycle.")
    if freshness >= 65:
        reasons.append("Recent multi-source activity indicates timely interest.")
    if cpc >= 65:
        reasons.append("Commercial terminology suggests above-average CPC potential.")
    return reasons


def looks_like_news_only(topic: str) -> bool:
    return bool(re.search(r"\b(raises|funding|acquires|announces|launches|released today|breaking)\b", topic.lower()))


def classify_search_intent(topic: str) -> str:
    lower = topic.lower()
    if any(term in lower for term in ("pricing", "cost", "free trial", "trial")):
        return "commercial investigation"
    if any(term in lower for term in ("alternatives", "alternative", "vs", "compare", "comparison")):
        return "comparison"
    if any(term in lower for term in ("review", "software", "platform", "tool", "tools")):
        return "commercial research"
    if any(term in lower for term in ("how to", "guide", "workflow", "tutorial")):
        return "informational"
    return "mixed informational and commercial"


def classify_content_type(topic: str) -> str:
    lower = topic.lower()
    if "alternatives" in lower or "alternative" in lower:
        return "alternative"
    if " vs " in lower or "comparison" in lower or "compare" in lower:
        return "comparison"
    if "pricing" in lower or "cost" in lower or "free trial" in lower or "trial" in lower:
        return "pricing"
    if "how to" in lower or "guide" in lower or "tutorial" in lower or "workflow" in lower:
        return "tutorial"
    if "best" in lower or "top " in lower or "tools" in lower:
        return "listicle"
    if "review" in lower:
        return "review"
    if looks_like_news_only(topic):
        return "news/update"
    return "review"


def classify_topic(topic: str, content_type: str, freshness: int, evergreen: int) -> list[str]:
    labels = {content_type}
    lower = topic.lower()
    if freshness >= 70:
        labels.add("hot trend")
    elif freshness >= 55:
        labels.add("rising trend")
    if evergreen >= 65:
        labels.add("evergreen")
    for label in ("comparison", "pricing", "alternative", "tutorial", "review", "listicle", "news/update"):
        if label == content_type:
            labels.add(label)
    if "agent" in lower or "agents" in lower:
        labels.add("ai agents")
    if "seo" in lower:
        labels.add("seo")
    if "coding" in lower or "developer" in lower:
        labels.add("ai coding")
    return sorted(labels)


def level_from_score(score: int) -> str:
    if score >= 75:
        return "high"
    if score >= 55:
        return "medium"
    return "low"


def competition_level(score: int) -> str:
    if score >= 70:
        return "high"
    if score >= 45:
        return "medium"
    return "low"


def business_value_level(affiliate: int, cpc: int, evergreen: int) -> str:
    blended = round(affiliate * 0.45 + cpc * 0.35 + evergreen * 0.20)
    return level_from_score(blended)


def priority_level(total_score: float) -> str:
    if total_score >= 70:
        return "P1"
    if total_score >= 55:
        return "P2"
    return "P3"


def suggest_internal_links(topic: str, content_type: str) -> list[str]:
    lower = topic.lower()
    links = ["/", "/reviews/", "/comparisons/"]
    if "seo" in lower:
        links.extend(["/category/seo-tools/", "/review/surfer-seo/", "/compare/semrush-vs-ahrefs/"])
    if "coding" in lower or "developer" in lower or "github" in lower or "cursor" in lower:
        links.extend(["/category/ai-coding-tools/", "/compare/cursor-vs-github-copilot-2026/", "/review/windsurf-review-2026/"])
    if "video" in lower:
        links.extend(["/category/video-tools/", "/best-ai-video-tools-2026/", "/review/synthesia/"])
    if "writing" in lower or "assistant" in lower:
        links.extend(["/category/ai-writing-tools/", "/grammarly-review-2026/", "/jasper-ai-review-2026/"])
    if "automation" in lower or "zapier" in lower:
        links.extend(["/category/automation-tools/", "/zapier-pricing/", "/compare/make-vs-zapier/"])
    if "website" in lower or "builder" in lower:
        links.extend(["/category/website-builder-tools/", "/best-website-builder-2026/", "/website-builder-software-review/"])
    if content_type == "pricing":
        links.append("/pricing/")
    return unique(links)[:10]


def suggest_article_angle(topic: str, content_type: str) -> str:
    if content_type == "comparison":
        return f"Compare {topic} through buyer-fit, workflow limits, pricing checks, and practical use cases."
    if content_type == "pricing":
        return f"Explain {topic} with current-plan verification steps, hidden cost risks, and who should pay."
    if content_type == "alternative":
        return f"Position {topic} as a shortlist guide with clear decision criteria and safer alternatives."
    if content_type == "tutorial":
        return f"Turn {topic} into a practical workflow guide with checks, examples, and mistakes to avoid."
    if content_type == "listicle":
        return f"Build {topic} as a curated buyer guide, not a generic ranked list."
    return f"Review {topic} with independent methodology, use cases, pricing cautions, pros, cons, and alternatives."


def suggest_video_angle(topic: str, content_type: str) -> str:
    if content_type == "comparison":
        return f"Fast side-by-side explainer: where each option wins, what to verify, and the safer buyer choice for {topic}."
    if content_type == "pricing":
        return f"Short pricing explainer for {topic}: what to check before paying and which users should wait."
    if content_type == "listicle":
        return f"Quick shortlist video for {topic}, with one practical use case per tool."
    return f"Three-to-five minute review video for {topic}: overview, features, pricing cautions, pros, cons, alternatives, verdict."


def keyword_hits(text: str, terms: set[str]) -> int:
    lower = text.lower()
    return sum(phrase_present(lower, term) for term in terms)


def phrase_present(text: str, term: str) -> bool:
    return bool(re.search(rf"(?<![a-z0-9]){re.escape(term.lower())}(?![a-z0-9])", text.lower()))


def slugify(value: str) -> str:
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", value.lower())).strip("-")


def token_set(value: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", value.lower())) - {"2025", "2026", "review", "guide", "best", "the", "and", "for", "with"}


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", BeautifulSoup(html.unescape(value or ""), "html.parser").get_text(" ")).strip()


def first_match(source: str, pattern: str) -> str:
    match = re.search(pattern, source, flags=re.I | re.S)
    return match.group(1) if match else ""


def xml_text(node: ET.Element, names: tuple[str, ...]) -> str:
    for name in names:
        child = node.find(name)
        if child is not None and child.text:
            return child.text.strip()
    return ""


def parse_number(value: object) -> float:
    match = re.search(r"[\d,.]+", str(value or "").replace(",", ""))
    return float(match.group(0)) if match else 0


def clamp(value: float) -> int:
    return int(max(0, min(100, round(value))))


def unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def normalize_source_url(url: str) -> str:
    clean = str(url or "").strip()
    parsed = urlparse(clean)
    host = parsed.netloc.lower().removeprefix("www.")
    if host == "bing.com" and parsed.path.startswith("/news/apiclick"):
        target = parse_qs(parsed.query).get("url", [""])[0]
        if target:
            return unquote(target).strip()
    return clean


def source_domain(url: str) -> str:
    host = urlparse(normalize_source_url(url)).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def independent_source_urls(urls: list[str]) -> list[str]:
    result: list[str] = []
    seen_domains: set[str] = set()
    for url in urls:
        clean = normalize_source_url(url)
        domain = source_domain(clean)
        if not clean or not domain or domain in seen_domains:
            continue
        seen_domains.add(domain)
        result.append(clean)
    return result[:8]


def clean_topic_query(topic: str) -> str:
    query = re.sub(r"\bReview\s+20\d{2}\b", "", str(topic or ""), flags=re.I)
    query = re.sub(r"\b(best|pricing|alternatives|comparison)\b", "", query, flags=re.I)
    return re.sub(r"\s+", " ", query.replace("_", " ").replace("-", " ")).strip()


def supplemental_source_matches_topic(topic: str, signal: TrendSignal) -> bool:
    query = clean_topic_query(topic)
    query_text = re.sub(r"[^a-z0-9]+", " ", query.lower()).strip()
    evidence_text = re.sub(
        r"[^a-z0-9]+",
        " ",
        f"{signal.title} {signal.description} {unquote(urlparse(signal.url).path)}".lower(),
    ).strip()
    if not query_text or not evidence_text:
        return False
    if query_text in evidence_text:
        return True

    ignored = {"ai", "the", "a", "an", "and", "for", "of", "to", "in", "tool", "tools", "software"}
    query_tokens = [token for token in query_text.split() if token not in ignored]
    if len(query_tokens) < 4:
        return False
    evidence_tokens = set(evidence_text.split())
    matched = sum(1 for token in query_tokens if token in evidence_tokens)
    return matched >= 4 and matched / len(query_tokens) >= 0.7


def save_discovery_result(result: DiscoveryResult, output: Path | None = None) -> tuple[Path, Path]:
    target = output or settings.data_dir / "trending_topics.json"
    report = settings.data_dir / "trending_topics_daily_report.md"
    archive = settings.data_dir / "trend_reports" / f"{result.generated_at[:10]}.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    archive.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(result)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report_content = daily_report(result)
    report.write_text(report_content, encoding="utf-8")
    archive.write_text(report_content, encoding="utf-8")
    return target, report


def daily_report(result: DiscoveryResult) -> str:
    lines = [
        "# AI Trend Discovery Daily Report",
        "",
        f"Generated: {result.generated_at}",
        f"Candidates evaluated: {result.candidates_evaluated}",
        f"Published topics checked: {result.published_topics_checked}",
        "",
        "## Selected Topics",
        "",
    ]
    for rank, topic in enumerate(result.selected_topics, 1):
        lines.extend(
            [
                f"### {rank}. {topic.topic}",
                "",
                f"- Score: **{topic.total_score}/100** | Confidence: **{topic.confidence}**",
                f"- Priority: **{topic.recommended_priority}** | Intent: **{topic.search_intent}** | Type: **{topic.content_type}**",
                f"- Business value: **{topic.estimated_business_value}** | Affiliate potential: **{topic.affiliate_potential}** | Competition level: **{topic.competition_level}**",
                f"- Classifications: {', '.join(topic.classifications)}",
                f"- Sources: {', '.join(topic.sources)}",
                f"- Search potential: {topic.search_volume_potential}; Competition: {topic.competition}; Affiliate: {topic.affiliate_opportunity}",
                f"- Evergreen: {topic.evergreen_value}; Freshness: {topic.news_freshness}; CPC potential: {topic.cpc_potential}",
                f"- Article angle: {topic.suggested_article_angle}",
                f"- Video angle: {topic.suggested_video_angle}",
                f"- Suggested internal links: {', '.join(topic.suggested_internal_links)}",
                *[f"- {reason}" for reason in topic.why_selected],
                "",
            ]
        )
    lines.extend(["## Source Status", ""])
    for source, status in result.source_status.items():
        lines.append(f"- **{source}**: {status.get('status')} ({status.get('signals', 0)} signals){' - ' + str(status.get('detail')) if status.get('detail') else ''}")
    lines.extend(["", "## Methodology", "", "Scores are directional opportunity estimates. No articles were generated."])
    return "\n".join(lines) + "\n"
