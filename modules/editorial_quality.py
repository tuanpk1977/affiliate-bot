from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


def _clamp(value: float, minimum: float = 0.0, maximum: float = 100.0) -> float:
    return max(minimum, min(maximum, value))


def _strip_html(value: str) -> str:
    return re.sub(r"<[^>]+>", " ", value or "")


def _domain(url: str) -> str:
    parsed = urlparse(str(url))
    host = parsed.netloc.lower()
    return host[4:] if host.startswith("www.") else host


def _issue(
    *,
    code: str,
    severity: str,
    category: str,
    message: str,
    section_id: str = "article",
    suggested_fix: str = "",
    auto_fixable: bool = False,
    hard_blocker: bool = False,
) -> dict[str, Any]:
    return asdict(
        EditorialIssue(
            code=code,
            severity=severity,
            category=category,
            section_id=section_id,
            message=message,
            suggested_fix=suggested_fix,
            auto_fixable=auto_fixable,
            hard_blocker=hard_blocker,
        )
    )


@dataclass(frozen=True)
class EditorialIssue:
    code: str
    severity: str
    category: str
    section_id: str
    message: str
    suggested_fix: str
    auto_fixable: bool
    hard_blocker: bool


@dataclass(frozen=True)
class SourceQualityRecord:
    url: str
    domain: str
    source_type: str
    authority_score: float
    freshness_score: float
    relevance_score: float
    primary_source: bool
    verified: bool
    risk_flags: list[str]
    overall_source_score: float


@dataclass(frozen=True)
class FactClaim:
    claim_id: str
    claim_text: str
    section_id: str
    importance: str
    claim_type: str
    matched_sources: list[str]
    support_status: str
    confidence: float
    requires_human_review: bool


@dataclass(frozen=True)
class StructuredAIReview:
    schema_version: int
    status: str
    overall_score: float
    hard_blockers: list[str]
    warnings: list[str]
    critical_issues: list[dict[str, Any]]
    suggested_fixes: list[str]
    section_reviews: list[dict[str, Any]]
    fact_risks: list[dict[str, Any]]
    seo_review: dict[str, Any]
    readability_review: dict[str, Any]
    business_value_review: dict[str, Any]
    source_quality_review: dict[str, Any]
    duplicate_risk: dict[str, Any]
    recommended_action: str
    issues: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class JudgeDecision:
    decision: str
    confidence: float
    reasoning_summary: list[str]
    remaining_risks: list[str]
    hard_blockers: list[str]
    warnings: list[str]
    recommended_human_focus: list[str]


@dataclass(frozen=True)
class PublishingConfidence:
    score: float
    status: str
    components: dict[str, float]
    reasons: list[str]
    recommended_action: str


@dataclass(frozen=True)
class CapacitySnapshot:
    target: int
    minimum: int
    maximum: int
    topics_discovered: int
    research_started: int
    drafts_generated: int
    rewrite_in_progress: int
    review_ready: int
    blocked: int
    held_for_enrichment: int
    approved: int
    published: int
    bottleneck: str


@dataclass(frozen=True)
class LearningFeedbackRecord:
    article_id: str
    topic_cluster: str
    content_type: str
    pre_publish_scores: dict[str, Any]
    human_changes: dict[str, Any]
    post_publish_metrics: dict[str, Any]
    lessons: list[str]
    recommended_policy_adjustments: list[dict[str, Any]]


class SourceQualityRanker:
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = config or {}

    def rank(self, sources: list[str | dict[str, Any]]) -> list[dict[str, Any]]:
        rows: list[SourceQualityRecord] = []
        for item in sources:
            source = item if isinstance(item, dict) else {"url": str(item)}
            url = str(source.get("url") or "").strip()
            if not url:
                continue
            domain = _domain(url)
            source_type, authority, primary = self._classify(domain, url)
            freshness = float(source.get("freshness_score", source.get("freshness", 75)))
            relevance = float(source.get("relevance_score", source.get("relevance", 70)))
            verified = str(source.get("status", "verified")).lower() in {"verified", "validated", "validated_topic_source"}
            risk_flags: list[str] = []
            if source_type == "forum":
                risk_flags.append("community_source_not_for_critical_claims")
            if not verified:
                risk_flags.append("unverified")
            overall = _clamp(authority * 0.45 + freshness * 0.20 + relevance * 0.25 + (10 if primary else 0) - len(risk_flags) * 5)
            rows.append(
                SourceQualityRecord(
                    url=url,
                    domain=domain,
                    source_type=source_type,
                    authority_score=round(authority, 2),
                    freshness_score=round(freshness, 2),
                    relevance_score=round(relevance, 2),
                    primary_source=primary,
                    verified=verified,
                    risk_flags=risk_flags,
                    overall_source_score=round(overall, 2),
                )
            )
        return [asdict(row) for row in sorted(rows, key=lambda row: row.overall_source_score, reverse=True)]

    def _classify(self, domain: str, url: str) -> tuple[str, float, bool]:
        if domain.endswith(".gov") or domain.endswith(".edu"):
            return "government_or_academic", 95, True
        if domain in {"github.com", "docs.github.com"} or "/docs" in url or "docs." in domain:
            return "official_docs", 88, True
        if domain in {"arxiv.org", "doi.org", "nature.com", "acm.org", "ieee.org"}:
            return "research_paper", 90, True
        if domain in {"reddit.com", "news.ycombinator.com", "x.com", "twitter.com"}:
            return "forum", 45, False
        if domain in {"wikipedia.org"} or domain.endswith(".wikipedia.org"):
            return "reference", 60, False
        if any(part in domain for part in ("blog", "medium", "substack")):
            return "expert_commentary", 58, False
        return "industry_or_company", 72, domain.count(".") <= 2


class FactVerificationEngine:
    CLAIM_PATTERN = re.compile(r"([^.!?]*(?:\d+|pricing|price|released|launch|compare|versus|vs\.?|percent|%|commission)[^.!?]*[.!?])", re.I)

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = config or {}
        self.cache: dict[str, dict[str, Any]] = {}

    def verify(self, *, html: str, sources: list[str | dict[str, Any]]) -> dict[str, Any]:
        text = _strip_html(html)
        source_urls = [str(item.get("url") if isinstance(item, dict) else item) for item in sources if str(item.get("url") if isinstance(item, dict) else item).strip()]
        source_domains = sorted({_domain(url) for url in source_urls})
        claims = self._extract_claims(text)
        verified_claims: list[FactClaim] = []
        hard_blockers: list[str] = []
        warnings: list[str] = []
        for claim_text in claims:
            claim_type = self._claim_type(claim_text)
            importance = self._importance(claim_text, claim_type)
            key = hashlib.sha256((claim_text + "|" + "|".join(source_urls)).encode("utf-8")).hexdigest()
            if key in self.cache:
                cached = self.cache[key]
                verified_claims.append(FactClaim(**cached))
                continue
            matched = source_urls[:3]
            if not source_urls:
                status = "unsupported"
                confidence = 0.0
            elif len(source_domains) >= 2:
                status = "supported"
                confidence = 0.86 if importance == "critical" else 0.76
            else:
                status = "partially_supported"
                confidence = 0.58
            requires_human = status in {"unsupported", "conflicting"} or (importance == "critical" and status != "supported")
            claim = FactClaim(
                claim_id=key[:12],
                claim_text=claim_text.strip(),
                section_id="article",
                importance=importance,
                claim_type=claim_type,
                matched_sources=matched,
                support_status=status,
                confidence=confidence,
                requires_human_review=requires_human,
            )
            self.cache[key] = asdict(claim)
            verified_claims.append(claim)
            if importance == "critical" and status == "unsupported":
                hard_blockers.append("critical claim unsupported")
            elif importance == "critical" and status != "supported":
                warnings.append("critical claim needs stronger source support")
            elif status != "supported":
                warnings.append("minor or important claim needs review")
        return {
            "schema_version": 2,
            "claim_count": len(verified_claims),
            "claims": [asdict(claim) for claim in verified_claims],
            "hard_blockers": list(dict.fromkeys(hard_blockers)),
            "warnings": list(dict.fromkeys(warnings)),
            "cache_size": len(self.cache),
        }

    def _extract_claims(self, text: str) -> list[str]:
        matches = [match.group(1).strip() for match in self.CLAIM_PATTERN.finditer(text)]
        if matches:
            return matches[:20]
        sentences = [segment.strip() + "." for segment in re.split(r"[.!?]+", text) if segment.strip()]
        return sentences[:5]

    def _claim_type(self, text: str) -> str:
        lower = text.lower()
        if any(token in lower for token in ("price", "pricing", "$", "commission")):
            return "number"
        if any(token in lower for token in ("released", "launch", "updated", "202")):
            return "date"
        if any(token in lower for token in ("vs", "versus", "compare", "alternative")):
            return "comparison"
        return "general"

    def _importance(self, text: str, claim_type: str) -> str:
        lower = text.lower()
        if claim_type in {"number", "date", "comparison"} or any(token in lower for token in ("best", "must", "guarantee")):
            return "critical"
        if len(text) > 120:
            return "important"
        return "minor"


class PublishingConfidenceEngine:
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        config = config or {}
        self.pass_min = float(config.get("pass_min", 90))
        self.review_ready_min = float(config.get("review_ready_min", 75))
        self.rewrite_min = float(config.get("rewrite_min", 50))

    def calculate(
        self,
        *,
        review: dict[str, Any],
        research: dict[str, Any],
        fact_verification: dict[str, Any],
        source_quality: list[dict[str, Any]],
        hard_blockers: list[str],
        warnings: list[str],
    ) -> dict[str, Any]:
        research_quality = research.get("quality") if isinstance(research.get("quality"), dict) else {}
        avg_source = sum(float(row.get("overall_source_score", 0)) for row in source_quality) / max(1, len(source_quality))
        supported_claims = sum(1 for claim in fact_verification.get("claims", []) if claim.get("support_status") == "supported")
        claim_count = int(fact_verification.get("claim_count", 0))
        fact_confidence = 80.0 if claim_count == 0 else (supported_claims / claim_count) * 100
        components = {
            "research_quality": float(research_quality.get("overall_score", 0) or 0),
            "source_quality": avg_source,
            "fact_confidence": fact_confidence,
            "intent_coverage": float(review.get("seo_title_meta_quality", 0) or 0),
            "entity_coverage": float(research_quality.get("entity_coverage_score", research_quality.get("entity_coverage", 0)) or 0),
            "readability": float(review.get("readability", 0) or 0),
            "seo": float(review.get("seo_title_meta_quality", 0) or 0),
            "business_value": float(review.get("business_value", 0) or 0),
            "duplicate_safety": max(0.0, 100.0 - float(review.get("duplicate_content_risk", 0) or 0)),
        }
        score = round(
            components["research_quality"] * 0.14
            + components["source_quality"] * 0.14
            + components["fact_confidence"] * 0.16
            + components["intent_coverage"] * 0.10
            + components["entity_coverage"] * 0.08
            + components["readability"] * 0.10
            + components["seo"] * 0.08
            + components["business_value"] * 0.10
            + components["duplicate_safety"] * 0.10,
            2,
        )
        if hard_blockers:
            status = "blocked"
            action = "block_until_critical_issues_resolved"
        elif score >= self.pass_min:
            status = "pass"
            action = "send_to_human_review"
        elif score >= self.review_ready_min:
            status = "warning"
            action = "send_to_human_review"
        elif score >= self.rewrite_min:
            status = "rewrite_or_enrich"
            action = "targeted_rewrite_or_enrichment"
        else:
            status = "blocked"
            action = "block_until_quality_improves"
        return asdict(PublishingConfidence(score=score, status=status, components={key: round(value, 2) for key, value in components.items()}, reasons=[*hard_blockers, *warnings], recommended_action=action))


class EditorialJudge:
    def evaluate(self, *, structured_review: dict[str, Any], fact_verification: dict[str, Any], publishing_confidence: dict[str, Any]) -> dict[str, Any]:
        hard_blockers = list(dict.fromkeys([*structured_review.get("hard_blockers", []), *fact_verification.get("hard_blockers", [])]))
        warnings = list(dict.fromkeys([*structured_review.get("warnings", []), *fact_verification.get("warnings", [])]))
        confidence = float(publishing_confidence.get("score", 0))
        if hard_blockers:
            decision = "block"
        elif warnings or confidence < 90:
            decision = "warning_to_human"
        else:
            decision = "pass_to_human"
        return asdict(
            JudgeDecision(
                decision=decision,
                confidence=confidence,
                reasoning_summary=[f"confidence={confidence}", f"hard_blockers={len(hard_blockers)}", f"warnings={len(warnings)}"],
                remaining_risks=warnings,
                hard_blockers=hard_blockers,
                warnings=warnings,
                recommended_human_focus=warnings[:5] or ["Confirm source-backed claims and affiliate fit before approval."],
            )
        )


class TargetedRewriteLoop:
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = config or {}
        self.max_rewrite_attempts = int(float(self.config.get("max_rewrite_attempts", 2)))
        self.max_review_cycles = int(float(self.config.get("max_review_cycles", 3)))

    def plan(self, *, structured_review: dict[str, Any]) -> dict[str, Any]:
        issues = [issue for issue in structured_review.get("issues", []) if isinstance(issue, dict)]
        fixable = [issue for issue in issues if issue.get("auto_fixable") and not issue.get("hard_blocker")]
        return {
            "schema_version": 2,
            "max_rewrite_attempts": self.max_rewrite_attempts,
            "max_review_cycles": self.max_review_cycles,
            "rewrite_required": bool(fixable),
            "target_sections": sorted({str(issue.get("section_id", "article")) for issue in fixable}),
            "issues": fixable,
            "history": [],
            "quality_guard": "keep_previous_section_when_rewrite_score_declines",
        }

    def choose_better_section(self, *, previous_text: str, rewritten_text: str, previous_score: float, rewritten_score: float) -> dict[str, Any]:
        if rewritten_score < previous_score:
            return {"selected": "previous", "text": previous_text, "reason": "rewrite score declined"}
        return {"selected": "rewritten", "text": rewritten_text, "reason": "rewrite score improved_or_equal"}


class StructuredReviewBuilder:
    def build(
        self,
        *,
        legacy_review: dict[str, Any],
        failures: list[str],
        warnings: list[str],
        hard_blockers: list[str],
        fact_verification: dict[str, Any],
        source_quality: list[dict[str, Any]],
    ) -> dict[str, Any]:
        issues: list[dict[str, Any]] = []
        for reason in hard_blockers:
            issues.append(_issue(code=self._code(reason), severity="critical", category=self._category(reason), message=reason, suggested_fix="Resolve before human approval.", hard_blocker=True))
        for reason in warnings:
            issues.append(_issue(code=self._code(reason), severity="medium", category=self._category(reason), message=reason, suggested_fix="Review or improve when practical.", auto_fixable=self._auto_fixable(reason), hard_blocker=False))
        for reason in failures:
            if reason not in hard_blockers and reason not in warnings:
                issues.append(_issue(code=self._code(reason), severity="medium", category=self._category(reason), message=reason, suggested_fix="Review before approval.", auto_fixable=self._auto_fixable(reason), hard_blocker=False))
        status = "blocked" if hard_blockers else ("warning" if warnings or failures else "pass")
        recommended_action = "block" if hard_blockers else "send_to_human_review"
        review = StructuredAIReview(
            schema_version=2,
            status=status,
            overall_score=float(legacy_review.get("publish_readiness", 0) or 0),
            hard_blockers=hard_blockers,
            warnings=list(dict.fromkeys([*warnings, *[failure for failure in failures if failure not in hard_blockers]])),
            critical_issues=[issue for issue in issues if issue.get("hard_blocker")],
            suggested_fixes=[issue["suggested_fix"] for issue in issues],
            section_reviews=[{"section_id": "article", "status": status, "issues": len(issues)}],
            fact_risks=fact_verification.get("claims", []),
            seo_review={"score": legacy_review.get("seo_title_meta_quality", 0), "status": self._check_status("seo", legacy_review)},
            readability_review={"score": legacy_review.get("readability", 0), "status": self._check_status("readability", legacy_review)},
            business_value_review={"score": legacy_review.get("business_value", 0), "status": self._check_status("business", legacy_review)},
            source_quality_review={"average_score": self._average_source_score(source_quality), "sources": source_quality},
            duplicate_risk={"score": legacy_review.get("duplicate_content_risk", 0), "status": "warning" if float(legacy_review.get("duplicate_content_risk", 0) or 0) > 65 else "pass"},
            recommended_action=recommended_action,
            issues=issues,
        )
        return asdict(review)

    def _code(self, reason: str) -> str:
        return re.sub(r"[^A-Z0-9]+", "_", reason.upper()).strip("_")[:64] or "EDITORIAL_ISSUE"

    def _category(self, reason: str) -> str:
        lower = reason.lower()
        if "source" in lower or "claim" in lower:
            return "source"
        if "seo" in lower or "title" in lower or "meta" in lower:
            return "seo"
        if "readability" in lower or "word count" in lower:
            return "readability"
        if "business" in lower or "affiliate" in lower:
            return "business"
        if "duplicate" in lower:
            return "structure"
        return "fact"

    def _auto_fixable(self, reason: str) -> bool:
        lower = reason.lower()
        return any(token in lower for token in ("seo", "readability", "word count", "internal links"))

    def _check_status(self, name: str, review: dict[str, Any]) -> str:
        if name == "seo":
            value = float(review.get("seo_title_meta_quality", 0) or 0)
            return "warning" if value < 60 else "pass"
        if name == "readability":
            value = float(review.get("readability", 0) or 0)
            return "warning" if value < 45 else "pass"
        value = float(review.get("business_value", 0) or 0)
        return "warning" if value < 45 else "pass"

    def _average_source_score(self, rows: list[dict[str, Any]]) -> float:
        return round(sum(float(row.get("overall_source_score", 0)) for row in rows) / max(1, len(rows)), 2)


class CapacityManager:
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        config = config or {}
        self.minimum = int(float(config.get("minimum_daily_review_ready", 5)))
        self.target = int(float(config.get("target_daily_review_ready", 10)))
        self.maximum = int(float(config.get("maximum_daily_drafts", 15)))

    def summarize(self, rows: list[dict[str, Any]]) -> dict[str, Any]:
        status_values = [str(row.get("status", "")).lower() for row in rows]
        review_ready = sum(1 for row in rows if str(row.get("status", "")).lower() in {"drafted", "needs_human_review", "warning_to_human"})
        blocked = sum(1 for value in status_values if value in {"needs_enrichment", "draft_failed", "blocked"})
        held = sum(1 for value in status_values if value in {"needs_enrichment", "hold"})
        bottleneck = "none"
        if review_ready < self.minimum:
            bottleneck = "review_ready_below_minimum"
        if held > blocked and review_ready < self.target:
            bottleneck = "research_enrichment"
        snapshot = CapacitySnapshot(
            target=self.target,
            minimum=self.minimum,
            maximum=self.maximum,
            topics_discovered=len(rows),
            research_started=sum(1 for row in rows if row.get("research_quality_gate")),
            drafts_generated=sum(1 for value in status_values if value == "drafted"),
            rewrite_in_progress=sum(1 for value in status_values if value == "rewrite_in_progress"),
            review_ready=review_ready,
            blocked=blocked,
            held_for_enrichment=held,
            approved=sum(1 for value in status_values if value == "approved"),
            published=sum(1 for value in status_values if value == "published"),
            bottleneck=bottleneck,
        )
        return asdict(snapshot)


def build_learning_feedback_record(
    *,
    article_id: str,
    topic_cluster: str,
    content_type: str,
    pre_publish_scores: dict[str, Any],
    human_changes: dict[str, Any] | None = None,
    post_publish_metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    lessons: list[str] = []
    if float((post_publish_metrics or {}).get("ctr", 0) or 0) < 2:
        lessons.append("Low CTR: review title/meta before proposing policy changes.")
    if float((pre_publish_scores or {}).get("warning_count", 0) or 0) > 0:
        lessons.append("Track warning count against post-publish performance.")
    return asdict(
        LearningFeedbackRecord(
            article_id=article_id,
            topic_cluster=topic_cluster,
            content_type=content_type,
            pre_publish_scores=pre_publish_scores,
            human_changes=human_changes or {},
            post_publish_metrics=post_publish_metrics or {},
            lessons=lessons,
            recommended_policy_adjustments=[],
        )
    )


def write_capacity_report(path: Path, snapshot: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Daily Capacity Report",
        "",
        f"- Generated at: {datetime.now(UTC).isoformat()}",
        f"- Target: {snapshot.get('target')}",
        f"- Minimum: {snapshot.get('minimum')}",
        f"- Maximum: {snapshot.get('maximum')}",
        f"- Review-ready: {snapshot.get('review_ready')}",
        f"- Blocked: {snapshot.get('blocked')}",
        f"- Enrichment: {snapshot.get('held_for_enrichment')}",
        f"- Bottleneck: {snapshot.get('bottleneck')}",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
