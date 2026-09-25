from __future__ import annotations

import json
import hashlib
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse

from modules.content_opportunity_fallback import (
    ExistingContentInventory,
    ThreeLevelContentOpportunityFallback,
)
from modules.source_classification import (
    classify_source,
    source_content_matches_type,
    source_directly_relevant,
    source_status,
    source_url,
)


SIGNAL_SCHEMA = "affiliate_opportunity_signal_v1"
PROGRAM_SCHEMA = "affiliate_program_evidence_v1"
SCORE_SCHEMA = "affiliate_opportunity_score_v1"
STRATEGY_SCHEMA = "affiliate_content_strategy_v1"
BRIEF_SCHEMA = "affiliate_opportunity_brief_v1"

AFFILIATE_TERMS = (
    "affiliate", "affiliate program", "partner program", "referral", "commission",
    "recurring commission", "cookie", "payout", "creator program", "ambassador",
    "revenue share", "revshare", "affiliate offer",
)
TREND_TERMS = (
    "new ai tool", "fast-growing", "new product launch", "vibe coding", "ai agents",
    "ai automation", "ai saas", "developer tools", "creator tools",
)
UNSUPPORTED_MARKET_PATTERNS = (
    r"\b(?:market|industry)\b.{0,45}\b(?:worth|reach|reaching|valued)\b.{0,45}(?:\$|usd\s*)?[\d,.]+\s*(?:billion|million|trillion|bn|m|b)\b",
    r"\b[\d.]+\s*%\s*(?:cagr|growth)\b",
    r"\b(?:best affiliate offer|huge earning potential|high converting|most profitable|top program)\b",
)
WEBSITE_STRATEGIES = {
    "REVIEW", "COMPARISON", "ALTERNATIVES", "TUTORIAL", "HOW_TO", "USE_CASE",
    "PRICING_ANALYSIS", "FEATURE_DEEP_DIVE", "INTEGRATION_GUIDE", "BUYER_GUIDE",
    "UPDATE_EXISTING_ARTICLE",
}
SOCIAL_STRATEGIES = {
    "SOCIAL_HOT", "SOCIAL_EDUCATIONAL", "SOCIAL_COMPARISON", "SOCIAL_TUTORIAL",
    "SOCIAL_SERIES",
}


def _text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")[:120]


def _tokens(value: str) -> set[str]:
    ignored = {"the", "and", "for", "with", "best", "review", "guide", "2026", "software", "tool", "tools"}
    return {
        token for token in re.findall(r"[a-z0-9]+", value.casefold())
        if len(token) > 2 and token not in ignored
    }


def _read(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError):
        return default


def _rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [dict(row) for row in payload if isinstance(row, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("opportunities", "items", "signals", "records"):
        if isinstance(payload.get(key), list):
            return [dict(row) for row in payload[key] if isinstance(row, dict)]
    return []


def _unknown_program(entity: str) -> dict[str, Any]:
    return {
        "schema_version": PROGRAM_SCHEMA,
        "entity": entity,
        "affiliate_program_status": "UNKNOWN",
        "affiliate_program_url": None,
        "commission_type": "UNKNOWN",
        "commission_value": None,
        "commission_currency": None,
        "recurring_commission": None,
        "commission_duration": None,
        "cookie_window_days": None,
        "minimum_payout": None,
        "payout_method": None,
        "payout_frequency": None,
        "approval_requirement": None,
        "affiliate_network": None,
        "geographic_restrictions": None,
        "program_terms_url": None,
        "last_verified_at": None,
        "verified_sources": [],
        "missing_evidence": ["verified_official_affiliate_program_page"],
        "commercial_boost_eligible": False,
    }


class AffiliateOpportunityDiscovery:
    """Evidence-first affiliate discovery and two-stage content planning."""

    def __init__(self, root: Path, *, now: datetime | None = None) -> None:
        self.root = root.resolve()
        self.now = (now or datetime.now(UTC)).astimezone(UTC)
        config = _read(self.root / "config/editorial_system.json", {})
        self.config = (
            config.get("affiliate_opportunity_discovery", {})
            if isinstance(config, dict) else {}
        )

    def extract_signal(
        self,
        text: str,
        *,
        source_url_value: str,
        source_platform: str,
        entity: str = "",
        product: str = "",
        category: str = "",
        trend_context: str = "",
    ) -> dict[str, Any] | None:
        clean = _text(text)
        lowered = clean.casefold()
        mentions = sorted({term for term in AFFILIATE_TERMS if term in lowered})
        if not mentions:
            return None
        trends = sorted({term for term in TREND_TERMS if term in lowered})
        claims: list[dict[str, Any]] = []
        for pattern in UNSUPPORTED_MARKET_PATTERNS:
            for match in re.finditer(pattern, clean, re.IGNORECASE):
                claims.append(
                    {
                        "claim": _text(match.group(0)),
                        "claim_status": "UNVERIFIED_SOCIAL_CLAIM",
                        "eligible_as_article_evidence": False,
                        "required_evidence": "original report, official terms, or reputable primary source",
                    }
                )
        return {
            "schema_version": SIGNAL_SCHEMA,
            "signal_type": "AFFILIATE_OPPORTUNITY_SIGNAL",
            "entity": _text(entity or product),
            "product": _text(product or entity),
            "category": _text(category),
            "trend_context": _text(trend_context or ", ".join(trends)),
            "signal_source_url": _text(source_url_value),
            "signal_source_platform": _text(source_platform),
            "signal_claims": claims,
            "affiliate_mentions": mentions,
            "affiliate_mention": True,
            "discovered_at": self.now.isoformat(),
            "verification_status": "UNVERIFIED",
            "official_site": None,
            "affiliate_program_url": None,
            "pricing_url": None,
            "docs_url": None,
            "social_signal_is_evidence": False,
            "commercial_boost_eligible": False,
            "next_action": "VERIFY_AFFILIATE_OPPORTUNITY",
        }

    def verify_program(
        self,
        signal: dict[str, Any],
        sources: Iterable[dict[str, Any]],
    ) -> dict[str, Any]:
        entity = _text(signal.get("entity") or signal.get("product"))
        result = _unknown_program(entity)
        verified_rows: list[dict[str, Any]] = []
        for raw in sources:
            if not isinstance(raw, dict):
                continue
            content = _text(raw.get("content") or raw.get("excerpt") or raw.get("text"))
            mapped_entity = _text(raw.get("canonical_entity_name") or raw.get("brand") or entity)
            classified = classify_source(raw, [mapped_entity])
            if source_status(classified) not in {"verified", "approved"}:
                continue
            if classified.get("source_type") != "affiliate_program_page":
                continue
            if not classified.get("official_ownership_verified"):
                continue
            if not source_content_matches_type(classified, content):
                continue
            verified_rows.append({**classified, "content": content})
        if not verified_rows:
            return result

        primary = verified_rows[0]
        result["entity"] = _text(primary.get("canonical_entity_name") or entity)
        content = " ".join(_text(row.get("content")) for row in verified_rows)
        commission_percent = re.search(
            r"(?:commission|revenue share|revshare)[^\d%$]{0,40}(\d+(?:\.\d+)?)\s*%",
            content,
            re.IGNORECASE,
        )
        if not commission_percent:
            commission_percent = re.search(
                r"(\d+(?:\.\d+)?)\s*%[^.]{0,40}(?:commission|revenue share|revshare)",
                content,
                re.IGNORECASE,
            )
        commission_money = re.search(
            r"(?:commission|payout|earn)[^\d%$]{0,40}\$\s*(\d+(?:\.\d+)?)",
            content,
            re.IGNORECASE,
        )
        cookie = re.search(r"\b(\d{1,4})\s*[- ]?day\s+cookie\b", content, re.IGNORECASE)
        minimum = re.search(r"minimum payout[^\d$]{0,30}\$\s*(\d+(?:\.\d+)?)", content, re.IGNORECASE)
        commission_type = "UNKNOWN"
        commission_value: float | None = None
        currency: str | None = None
        if commission_percent:
            commission_type = "PERCENTAGE"
            commission_value = float(commission_percent.group(1))
        elif commission_money:
            commission_type = "FIXED"
            commission_value = float(commission_money.group(1))
            currency = "USD"
        recurring = True if re.search(r"\brecurring\s+(?:commission|revenue share|payout)\b", content, re.IGNORECASE) else None
        verified_at = _text(primary.get("verification_date") or primary.get("last_verified_at")) or self.now.isoformat()
        result.update(
            {
                "affiliate_program_status": "VERIFIED",
                "affiliate_program_url": source_url(primary),
                "commission_type": commission_type,
                "commission_value": commission_value,
                "commission_currency": currency,
                "recurring_commission": recurring,
                "cookie_window_days": int(cookie.group(1)) if cookie else None,
                "minimum_payout": float(minimum.group(1)) if minimum else None,
                "last_verified_at": verified_at,
                "verified_sources": [
                    {
                        "url": source_url(row),
                        "source_family": row.get("source_type"),
                        "provenance": row.get("provenance") or row.get("discovery_method") or "CANONICAL_RESEARCH",
                        "verification_status": "verified",
                        "official_ownership_verified": True,
                    }
                    for row in verified_rows
                ],
                "missing_evidence": [
                    key for key, value in {
                        "commission": commission_value,
                        "cookie_window": int(cookie.group(1)) if cookie else None,
                        "payout_method": None,
                        "payout_frequency": None,
                        "program_terms": None,
                    }.items() if value is None
                ],
                "commercial_boost_eligible": True,
            }
        )
        return result

    def score(
        self,
        signal: dict[str, Any],
        program: dict[str, Any],
        *,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        context = context or {}
        weights = {
            "program_verified": 20.0,
            "commercial_intent": 12.0,
            "product_relevance": 12.0,
            "trend_momentum": 8.0,
            "commission_quality": 8.0,
            "recurring_revenue": 7.0,
            "cookie_quality": 5.0,
            "evidence_quality": 10.0,
            "official_source_quality": 8.0,
            "content_gap": 5.0,
            "existing_site_authority": 3.0,
            "freshness": 2.0,
            **(self.config.get("weights", {}) if isinstance(self.config.get("weights"), dict) else {}),
        }
        penalties_cfg = {
            "unverified_program": 30.0,
            "social_only_evidence": 20.0,
            "weak_official_evidence": 15.0,
            "stale_information": 12.0,
            "duplicate_coverage": 18.0,
            "high_cannibalization": 25.0,
            "unsupported_claims": 15.0,
            "unknown_entity": 20.0,
            **(self.config.get("penalties", {}) if isinstance(self.config.get("penalties"), dict) else {}),
        }
        verified = program.get("affiliate_program_status") == "VERIFIED"
        evidence_count = len(program.get("verified_sources") or [])
        components = {
            "program_verified": float(weights["program_verified"]) if verified else 0.0,
            "commercial_intent": float(weights["commercial_intent"]) * min(1.0, float(context.get("commercial_intent", 70)) / 100.0),
            "product_relevance": float(weights["product_relevance"]) * min(1.0, float(context.get("audience_fit", 75)) / 100.0),
            "trend_momentum": float(weights["trend_momentum"]) * min(1.0, float(context.get("trend_momentum", 55)) / 100.0),
            "commission_quality": float(weights["commission_quality"]) if program.get("commission_value") is not None else 0.0,
            "recurring_revenue": float(weights["recurring_revenue"]) if program.get("recurring_commission") is True else 0.0,
            "cookie_quality": float(weights["cookie_quality"]) if program.get("cookie_window_days") is not None else 0.0,
            "evidence_quality": float(weights["evidence_quality"]) * min(1.0, evidence_count / 2.0),
            "official_source_quality": float(weights["official_source_quality"]) if verified else 0.0,
            "content_gap": float(weights["content_gap"]) * min(1.0, float(context.get("content_gap", 50)) / 100.0),
            "existing_site_authority": float(weights["existing_site_authority"]) * min(1.0, float(context.get("existing_authority", 0)) / 100.0),
            "freshness": float(weights["freshness"]) if program.get("last_verified_at") else 0.0,
        }
        penalties: dict[str, float] = {}
        if not verified:
            penalties["unverified_program"] = -float(penalties_cfg["unverified_program"])
        if not evidence_count:
            penalties["social_only_evidence"] = -float(penalties_cfg["social_only_evidence"])
        if signal.get("signal_claims"):
            penalties["unsupported_claims"] = -float(penalties_cfg["unsupported_claims"])
        if not _text(signal.get("entity") or signal.get("product")):
            penalties["unknown_entity"] = -float(penalties_cfg["unknown_entity"])
        if context.get("duplicate_existing_coverage"):
            penalties["duplicate_coverage"] = -float(penalties_cfg["duplicate_coverage"])
        if context.get("high_cannibalization"):
            penalties["high_cannibalization"] = -float(penalties_cfg["high_cannibalization"])
        score = max(0.0, min(100.0, sum(components.values()) + sum(penalties.values())))
        evidence_score = min(100.0, evidence_count * 40.0 + (20.0 if verified else 0.0))
        return {
            "schema_version": SCORE_SCHEMA,
            "affiliate_opportunity_score": round(score, 2),
            "evidence_score": round(evidence_score, 2),
            "components": {key: round(value, 2) for key, value in components.items()},
            "penalties": penalties,
            "program_verified": verified,
            "commercial_boost_eligible": bool(verified and evidence_score >= float(self.config.get("minimum_evidence_score", 45))),
            "commercial_boost": round(min(float(self.config.get("weekly_score_boost_max", 8)), score / 100.0 * float(self.config.get("weekly_score_boost_max", 8))), 2) if verified else 0.0,
            "reasoning": [
                *[f"{key}=+{value:.2f}" for key, value in sorted(components.items()) if value > 0],
                *[f"{key}={value:.2f}" for key, value in penalties.items()],
            ],
        }

    def recommend_strategy(
        self,
        signal: dict[str, Any],
        program: dict[str, Any],
        score: dict[str, Any],
        *,
        inventory: dict[str, Any] | None = None,
        proposed_intent: str = "commercial research",
    ) -> dict[str, Any]:
        entity = _text(signal.get("entity") or signal.get("product"))
        snapshot = inventory or ExistingContentInventory(self.root, self.now).scan()
        articles = [row for row in snapshot.get("articles", []) if isinstance(row, dict)]
        entity_tokens = _tokens(entity)
        related = [
            row for row in articles
            if entity_tokens and entity_tokens & _tokens(f"{row.get('title')} {row.get('slug')} {row.get('entity')}")
        ]
        minimum_score = float(self.config.get("minimum_opportunity_score", 55))
        minimum_evidence = float(self.config.get("minimum_evidence_score", 45))
        verified = program.get("affiliate_program_status") == "VERIFIED"
        evidence_pass = float(score.get("evidence_score") or 0) >= minimum_evidence
        score_pass = float(score.get("affiliate_opportunity_score") or 0) >= minimum_score
        result = {
            "schema_version": STRATEGY_SCHEMA,
            "entity": entity,
            "opportunity_status": "VERIFIED" if verified else "UNVERIFIED",
            "stage_1": {
                "real_entity": bool(entity),
                "affiliate_program_verified": verified,
                "relevant_to_site": bool(entity),
                "evidence_passed": evidence_pass,
                "commercial_score_passed": score_pass,
                "existing_coverage_count": len(related),
                "passed": bool(entity and verified and evidence_pass and score_pass),
            },
            "stage_2_ran": False,
            "recommended_action": "HOLD_FOR_REVIEW",
            "fallback_level": 0,
            "recommended_content_type": None,
            "secondary_content_types": [],
            "reasoning": [],
            "affiliate_opportunity_score": score.get("affiliate_opportunity_score", 0),
            "evidence_score": score.get("evidence_score", 0),
            "cannibalization_risk": "unknown",
            "existing_related_urls": [row.get("canonical_url") or f"/{row.get('slug')}/" for row in related],
            "required_sources": ["official product page", "official affiliate/partner terms", "pricing/docs when claims require them"],
            "missing_evidence": list(program.get("missing_evidence") or []),
            "human_approval_required": True,
            "auto_publish": False,
        }
        if not result["stage_1"]["passed"]:
            result["reasoning"] = [
                "Stage 2 was not run because affiliate verification, evidence, or score gates did not pass.",
                "The product may still enter the ordinary editorial workflow without an affiliate boost.",
            ]
            result["research_state"] = "BLOCKED_RESEARCH" if not evidence_pass else "OPERATOR_REVIEW"
            return result

        result["stage_2_ran"] = True
        proposed = {
            "topic": f"{entity} Review",
            "title": f"{entity} Review",
            "slug": _slug(f"{entity}-review"),
            "primary_keyword": f"{entity} review".casefold(),
            "search_intent": proposed_intent,
            "parent_root_id": related[0].get("root_topic_id") if related else "",
        }
        guard = ThreeLevelContentOpportunityFallback(self.root, now=self.now).cannibalization_guard(proposed, articles)
        exact_intent = next(
            (row for row in related if _text(row.get("search_intent")).casefold() == proposed_intent.casefold()),
            None,
        )
        if exact_intent:
            age_days = self._age_days(exact_intent)
            if age_days >= int(self.config.get("outdated_after_days", 180)):
                action, level, content_type = "UPDATE_EXISTING_URL", 3, "UPDATE_EXISTING_ARTICLE"
                reason = f"Existing same-intent article is {age_days} days old; update its canonical URL."
            else:
                action, level, content_type = "REJECT_DUPLICATE", 0, None
                reason = "Existing article already covers the same entity and decision question."
        elif related:
            action, level, content_type = "EXPAND_EXISTING_ROOT", 2, self._content_type(proposed_intent)
            reason = "Existing root has authority, while the proposed decision question is meaningfully different."
        elif guard.get("cannibalization_risk"):
            action, level, content_type = "HOLD_FOR_REVIEW", 0, None
            reason = "Cannibalization guard found a high-risk overlap outside the direct entity match."
        else:
            action, level, content_type = "CREATE_NEW", 1, self._content_type(proposed_intent)
            reason = "Verified, evidence-ready opportunity has no matching canonical site coverage."
        result.update(
            {
                "recommended_action": action,
                "fallback_level": level,
                "recommended_content_type": content_type,
                "secondary_content_types": self._secondary_types(content_type, program),
                "reasoning": [reason, "Affiliate status did not bypass research or cannibalization gates."],
                "cannibalization_risk": guard.get("duplicate_risk", "low"),
                "source_article_slug": exact_intent.get("slug") if exact_intent else (related[0].get("slug") if related else None),
                "deep_dive_eligible": level in {1, 2},
                "preserve_slug": level == 3,
                "create_new_url": level in {1, 2},
                "research_state": "RESEARCH_READY",
            }
        )
        return result

    def analyze(
        self,
        text: str,
        *,
        source_url_value: str,
        source_platform: str,
        entity: str,
        sources: Iterable[dict[str, Any]] = (),
        inventory: dict[str, Any] | None = None,
        proposed_intent: str = "commercial research",
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        signal = self.extract_signal(
            text,
            source_url_value=source_url_value,
            source_platform=source_platform,
            entity=entity,
        )
        if signal is None:
            return {"signal_detected": False, "existing_behavior_unchanged": True}
        program = self.verify_program(signal, sources)
        score = self.score(signal, program, context=context)
        strategy = self.recommend_strategy(
            signal, program, score, inventory=inventory, proposed_intent=proposed_intent
        )
        return {
            "schema_version": "affiliate_opportunity_analysis_v1",
            "signal_detected": True,
            "signal": signal,
            "program": program,
            "score": score,
            "strategy": strategy,
            "lifecycle_status": "OPERATOR_REVIEW" if strategy.get("stage_2_ran") else "UNVERIFIED",
        }

    def save_analysis(self, analysis: dict[str, Any]) -> dict[str, Any]:
        """Idempotently store a discovery record; never create editorial tasks."""
        if not analysis.get("signal_detected"):
            return {"saved": False, "reason": "NO_AFFILIATE_SIGNAL"}
        signal = analysis.get("signal") or {}
        program = analysis.get("program") or {}
        score = analysis.get("score") or {}
        strategy = analysis.get("strategy") or {}
        identity = "|".join(
            (
                _text(signal.get("entity") or signal.get("product")).casefold(),
                _text(signal.get("signal_source_url")).casefold().rstrip("/"),
            )
        )
        opportunity_id = "affiliate-opportunity-" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]
        path = self.root / "data/affiliate_opportunity_discovery.json"
        payload = _read(path, {})
        if not isinstance(payload, dict):
            payload = {}
        items = [row for row in payload.get("items", []) if isinstance(row, dict)]
        existing = next((row for row in items if row.get("opportunity_id") == opportunity_id), None)
        row = {
            "opportunity_id": opportunity_id,
            "entity": signal.get("entity") or signal.get("product"),
            "product": signal.get("product") or signal.get("entity"),
            "category": signal.get("category"),
            "signal_type": "AFFILIATE_OPPORTUNITY_SIGNAL",
            "signal_source_url": signal.get("signal_source_url"),
            "signal_source_platform": signal.get("signal_source_platform"),
            "signal_claims": list(signal.get("signal_claims") or []),
            "verification_status": program.get("affiliate_program_status", "UNKNOWN"),
            "affiliate_program_status": program.get("affiliate_program_status", "UNKNOWN"),
            "affiliate_program_url": program.get("affiliate_program_url"),
            "verified_sources": list(program.get("verified_sources") or []),
            "affiliate_opportunity_score": score.get("affiliate_opportunity_score", 0),
            "evidence_score": score.get("evidence_score", 0),
            "commercial_boost": score.get("commercial_boost", 0),
            "commercial_boost_eligible": score.get("commercial_boost_eligible", False),
            "content_strategy": strategy,
            "lifecycle_status": (
                "CONTENT_STRATEGY_RECOMMENDED"
                if strategy.get("stage_2_ran")
                else "UNVERIFIED" if program.get("affiliate_program_status") != "VERIFIED" else "OPERATOR_REVIEW"
            ),
            "operator_review_status": "PENDING",
            "human_approval_required": True,
            "auto_publish": False,
            "updated_at": self.now.isoformat(),
        }
        if existing:
            items[items.index(existing)] = {**existing, **row}
            created = False
        else:
            row["discovered_at"] = signal.get("discovered_at") or self.now.isoformat()
            items.append(row)
            created = True
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(".json.tmp")
        temp.write_text(
            json.dumps(
                {
                    "schema_version": "affiliate_opportunity_discovery_inventory_v1",
                    "updated_at": self.now.isoformat(),
                    "items": sorted(items, key=lambda item: str(item.get("opportunity_id"))),
                    "human_approval_required": True,
                    "auto_publish": False,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        temp.replace(path)
        return {"saved": True, "created": created, "opportunity_id": opportunity_id, "path": str(path)}

    def _age_days(self, article: dict[str, Any]) -> int:
        raw = _text(article.get("updated_at") or article.get("published_at") or article.get("date"))
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)
            return max(0, (self.now - parsed.astimezone(UTC)).days)
        except ValueError:
            return 365

    @staticmethod
    def _content_type(intent: str) -> str:
        lowered = intent.casefold()
        if "comparison" in lowered or " vs " in f" {lowered} ":
            return "COMPARISON"
        if "alternative" in lowered:
            return "ALTERNATIVES"
        if "pricing" in lowered or "cost" in lowered:
            return "PRICING_ANALYSIS"
        if "integration" in lowered:
            return "INTEGRATION_GUIDE"
        if "how to" in lowered:
            return "HOW_TO"
        if "tutorial" in lowered:
            return "TUTORIAL"
        if "use case" in lowered:
            return "USE_CASE"
        return "REVIEW"

    @staticmethod
    def _secondary_types(primary: str | None, program: dict[str, Any]) -> list[str]:
        choices = ["COMPARISON", "TUTORIAL"]
        if program.get("commission_value") is not None:
            choices.append("PRICING_ANALYSIS")
        return [item for item in choices if item != primary][:2]


def apply_verified_affiliate_boost(root: Path, candidates: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Apply a bounded boost from an evidence-first local report, never social-only claims."""
    engine = AffiliateOpportunityDiscovery(root)
    report_path = root / "data/affiliate_opportunity_discovery.json"
    rows = _rows(_read(report_path, {})) if report_path.is_file() else []
    verified = [
        row for row in rows
        if row.get("affiliate_program_status") == "VERIFIED"
        and row.get("commercial_boost_eligible") is True
        and row.get("verified_sources")
    ]
    boosted = 0
    for candidate in candidates:
        haystack = _tokens(f"{candidate.get('topic')} {candidate.get('slug')} {candidate.get('primary_keyword')}")
        match = next(
            (row for row in verified if _tokens(_text(row.get("entity") or row.get("product"))) & haystack),
            None,
        )
        if not match:
            candidate["affiliate_commercial_boost"] = 0.0
            continue
        max_boost = float(engine.config.get("weekly_score_boost_max", 8))
        boost = min(max_boost, float(match.get("commercial_boost") or max_boost))
        candidate["opportunity_score"] = min(100.0, float(candidate.get("opportunity_score") or 0) + boost)
        candidate["affiliate_commercial_boost"] = boost
        candidate["affiliate_opportunity_signal"] = {
            "entity": match.get("entity") or match.get("product"),
            "affiliate_program_status": "VERIFIED",
            "score": match.get("affiliate_opportunity_score"),
            "evidence_score": match.get("evidence_score"),
            "source": report_path.relative_to(root).as_posix(),
        }
        boosted += 1
    return candidates, {
        "schema_version": "weekly_affiliate_signal_input_v1",
        "verified_opportunities_available": len(verified),
        "candidates_boosted": boosted,
        "maximum_boost": float(engine.config.get("weekly_score_boost_max", 8)),
        "quality_gates_bypassed": False,
    }


def research_affiliate_program(root: Path, slug: str, *, now: datetime | None = None) -> dict[str, Any]:
    """Read canonical research artifacts and return verified program facts only."""
    research = root / "data/research" / slug
    sources_payload = _read(research / "sources.json", {})
    source_rows: list[dict[str, Any]] = []
    if isinstance(sources_payload, dict):
        source_rows.extend(row for row in sources_payload.get("verified_sources", []) if isinstance(row, dict))
        trusted = sources_payload.get("trusted_sources", {})
        if isinstance(trusted, dict):
            for rows in trusted.values():
                source_rows.extend(row for row in rows if isinstance(row, dict))
    excerpts = _read(research / "SOURCE_EXCERPTS.json", {})
    excerpt_by_url = {
        source_url(row): " ".join(
            _text(paragraph.get("text"))
            for paragraph in row.get("paragraphs", []) if isinstance(paragraph, dict)
        ) or _text(row.get("extracted_relevant_paragraphs"))
        for row in (excerpts.get("sources", []) if isinstance(excerpts, dict) else [])
        if isinstance(row, dict)
    }
    deduped: dict[str, dict[str, Any]] = {}
    for row in source_rows:
        url = source_url(row)
        if not url:
            continue
        deduped[url.casefold().rstrip("/")] = {**row, "content": excerpt_by_url.get(url, _text(row.get("content") or row.get("evidence")))}
    package = _read(research / "package.json", {})
    topic = _text(package.get("topic") or package.get("keyword") or slug.replace("-", " ")) if isinstance(package, dict) else slug.replace("-", " ")
    entity = _text(package.get("primary_entity") if isinstance(package, dict) else "") or topic
    engine = AffiliateOpportunityDiscovery(root, now=now)
    signal = {
        "entity": entity,
        "product": entity,
        "signal_claims": [],
        "verification_status": "UNVERIFIED",
    }
    return engine.verify_program(signal, deduped.values())


def build_affiliate_opportunity_brief(root: Path, slug: str) -> dict[str, Any]:
    program = research_affiliate_program(root, slug)
    facts = {
        key: value for key, value in program.items()
        if key not in {"verified_sources", "missing_evidence"}
        and (value is not None or key in {"commission_type", "affiliate_program_status"})
    }
    return {
        "schema_version": BRIEF_SCHEMA,
        "slug": slug,
        "verified_facts": facts if program.get("affiliate_program_status") == "VERIFIED" else {},
        "unknown_or_unverified": list(program.get("missing_evidence") or ["affiliate_program"]),
        "verified_sources": list(program.get("verified_sources") or []),
        "writer_safety": {
            "do_not_invent": [
                "commission", "cookie duration", "pricing", "features", "affiliate terms",
                "market size", "performance claims",
            ],
            "all_commercial_claims_require_supplied_evidence": True,
            "human_approval_required": True,
            "auto_publish": False,
        },
    }
