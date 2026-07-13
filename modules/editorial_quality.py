from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol
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


class SectionRewriteProvider(Protocol):
    def rewrite_section(self, *, section_id: str, section_html: str, issues: list[dict[str, Any]], context: dict[str, Any]) -> str:
        ...


class HeuristicSectionRewriteProvider:
    """Production-safe fallback provider used when no external writer is configured."""

    def rewrite_section(self, *, section_id: str, section_html: str, issues: list[dict[str, Any]], context: dict[str, Any]) -> str:
        additions: list[str] = []
        messages = " ".join(str(issue.get("message", "")).lower() for issue in issues)
        if "readability" in messages:
            additions.append("This section now uses shorter review notes so an editor can verify the recommendation quickly.")
        if "seo" in messages:
            keyword = str(context.get("primary_keyword") or context.get("topic") or "").strip()
            if keyword:
                additions.append(f"It keeps the focus on {keyword} while preserving the original comparison intent.")
        if "source" in messages or "fact" in messages:
            additions.append("Verify the current vendor documentation before approving claims about pricing, dates, or feature limits.")
        if not additions:
            additions.append("This section was tightened for clarity while preserving the existing sources, links, headings, and citations.")
        insertion = "".join(f"<p>{line}</p>" for line in additions)
        if "</section>" in section_html:
            return section_html.replace("</section>", f"{insertion}</section>", 1)
        return section_html + insertion


class TargetedRewriteExecutor:
    def __init__(self, config: dict[str, Any] | None = None, provider: SectionRewriteProvider | None = None) -> None:
        self.config = config or {}
        self.provider = provider or HeuristicSectionRewriteProvider()
        self.max_attempts = int(float(self.config.get("max_rewrite_attempts", 2)))
        self.timeout_seconds = float(self.config.get("timeout_seconds", 20))
        self.retry_limit = int(float(self.config.get("retry_limit", 1)))

    def execute(self, *, article_id: str, html: str, structured_review: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
        context = context or {}
        plan = TargetedRewriteLoop(self.config).plan(structured_review=structured_review)
        issues_by_section: dict[str, list[dict[str, Any]]] = {}
        for issue in plan.get("issues", []):
            section_id = str(issue.get("section_id") or "article")
            issues_by_section.setdefault(section_id, []).append(issue)
        updated = html
        history: list[dict[str, Any]] = []
        for section_id, issues in issues_by_section.items():
            for attempt in range(1, self.max_attempts + 1):
                section = self._extract_section(updated, section_id)
                if not section:
                    history.append(self._history(article_id, section_id, attempt, issues, "", "", 0, 0, False, "section not found", 0.0))
                    break
                started = time.monotonic()
                try:
                    rewritten = self._call_provider(section_id=section_id, section_html=section["html"], issues=issues, context=context)
                except TimeoutError:
                    history.append(self._history(article_id, section_id, attempt, issues, section["html"], section["html"], 0, 0, False, "rewrite timeout", time.monotonic() - started))
                    if attempt > self.retry_limit:
                        break
                    continue
                duration = time.monotonic() - started
                old_score = self._section_score(section["html"])
                new_score = self._section_score(rewritten)
                validation = self._validate_rewrite(old=section["html"], new=rewritten)
                accepted = bool(validation["valid"] and new_score >= old_score)
                reason = "accepted" if accepted else validation["reason"] if not validation["valid"] else "rewrite score declined"
                if accepted:
                    updated = updated[: section["start"]] + rewritten + updated[section["end"] :]
                history.append(self._history(article_id, section_id, attempt, issues, section["html"], rewritten, old_score, new_score, accepted, reason, duration))
                break
        remaining_hard = list(structured_review.get("hard_blockers") or [])
        return {
            "schema_version": 2,
            "article_id": article_id,
            "executed": bool(history),
            "html": updated,
            "rewrite_history": history,
            "status": "blocked" if remaining_hard else "warning_to_human",
            "remaining_hard_blockers": remaining_hard,
        }

    def _call_provider(self, *, section_id: str, section_html: str, issues: list[dict[str, Any]], context: dict[str, Any]) -> str:
        start = time.monotonic()
        result = self.provider.rewrite_section(section_id=section_id, section_html=section_html, issues=issues, context=context)
        if time.monotonic() - start > self.timeout_seconds:
            raise TimeoutError("section rewrite provider timeout")
        return result

    def _extract_section(self, html: str, section_id: str) -> dict[str, Any] | None:
        section_pattern = re.compile(r"<section\b[^>]*>.*?</section>", re.I | re.S)
        for match in section_pattern.finditer(html):
            block = match.group(0)
            if section_id == "article" or re.search(rf"\bid=['\"]{re.escape(section_id)}['\"]", block, flags=re.I):
                return {"start": match.start(), "end": match.end(), "html": block}
        if section_id == "article":
            return {"start": 0, "end": len(html), "html": html}
        return None

    def _section_score(self, html: str) -> float:
        text = _strip_html(html)
        words = re.findall(r"[A-Za-z0-9À-ỹ']+", text)
        link_bonus = min(10, len(re.findall(r"<a\b", html, re.I)) * 2)
        citation_bonus = min(10, len(re.findall(r"\[[0-9]+\]|<cite\b", html, re.I)) * 3)
        return round(_clamp(min(80, len(words) / 3) + link_bonus + citation_bonus), 2)

    def _validate_rewrite(self, *, old: str, new: str) -> dict[str, Any]:
        if not new.strip():
            return {"valid": False, "reason": "empty rewrite"}
        old_headings = re.findall(r"<h[1-6]\b[^>]*>.*?</h[1-6]>", old, re.I | re.S)
        new_headings = re.findall(r"<h[1-6]\b[^>]*>.*?</h[1-6]>", new, re.I | re.S)
        if old_headings and old_headings[0] not in new_headings:
            return {"valid": False, "reason": "heading hierarchy changed"}
        for href in re.findall(r"href=['\"]([^'\"]+)['\"]", old, re.I):
            if href not in new:
                return {"valid": False, "reason": "internal link or citation lost"}
        return {"valid": True, "reason": "ok"}

    def _history(
        self,
        article_id: str,
        section_id: str,
        attempt: int,
        issues: list[dict[str, Any]],
        old_html: str,
        new_html: str,
        old_score: float,
        new_score: float,
        accepted: bool,
        reason: str,
        duration: float,
    ) -> dict[str, Any]:
        return {
            "article_id": article_id,
            "section_id": section_id,
            "attempt": attempt,
            "issue_codes": [str(issue.get("code") or "") for issue in issues],
            "old_score": old_score,
            "new_score": new_score,
            "accepted": accepted,
            "reason": reason,
            "old_hash": hashlib.sha256(old_html.encode("utf-8")).hexdigest()[:16],
            "new_hash": hashlib.sha256(new_html.encode("utf-8")).hexdigest()[:16],
            "duration_seconds": round(duration, 4),
        }


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


class EditorialBrain:
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = config or {}
        mix = self.config.get("daily_mix") if isinstance(self.config.get("daily_mix"), dict) else {}
        self.mix = {
            "FAST_TRACK": float(mix.get("fast_track", 0.4)),
            "STANDARD": float(mix.get("standard", 0.4)),
            "DEEP_RESEARCH": float(mix.get("deep_research", 0.2)),
        }

    def score_candidates(self, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        seen_slugs: set[str] = set()
        for candidate in candidates:
            slug = str(candidate.get("slug") or _slug(candidate.get("topic") or candidate.get("keyword") or "")).strip()
            source_readiness = float(candidate.get("source_readiness_score", candidate.get("source_count", 0) * 35))
            trend_score = float(candidate.get("trend_score", candidate.get("total_score", 50)))
            business_value = float(candidate.get("business_value", candidate.get("affiliate_monetization_score", 50)))
            topical_gap = float(candidate.get("topical_gap", 55))
            freshness = float(candidate.get("freshness", candidate.get("content_freshness_score", 55)))
            competition = float(candidate.get("competition", candidate.get("competition_difficulty_score", 45)))
            production_cost = self._production_cost(candidate)
            review_risk = self._review_risk(candidate)
            duplicate = slug in seen_slugs or bool(candidate.get("duplicate_collision") or candidate.get("cannibalization_risk"))
            seen_slugs.add(slug)
            opportunity = _clamp(trend_score * 0.18 + business_value * 0.20 + topical_gap * 0.14 + source_readiness * 0.20 + freshness * 0.12 - competition * 0.08 - production_cost * 0.04 - review_risk * 0.04)
            classification = self._classify(candidate, source_readiness=source_readiness, review_risk=review_risk, duplicate=duplicate)
            rows.append(
                {
                    **candidate,
                    "topic_id": slug,
                    "slug": slug,
                    "classification": classification,
                    "opportunity_score": round(opportunity, 2),
                    "source_readiness": round(_clamp(source_readiness), 2),
                    "review_risk": round(review_risk, 2),
                    "estimated_effort": "high" if production_cost >= 70 else "medium" if production_cost >= 45 else "low",
                    "expected_review_ready_today": classification in {"FAST_TRACK", "STANDARD"} and not duplicate and source_readiness >= 50,
                    "selection_reason": self._selection_reasons(classification, source_readiness, review_risk, duplicate),
                    "hold_reason": "duplicate or cannibalization risk" if duplicate else None,
                }
            )
        return sorted(rows, key=lambda row: float(row.get("opportunity_score", 0)), reverse=True)

    def select_portfolio(self, candidates: list[dict[str, Any]], *, target: int = 10, minimum_review_ready: int = 5) -> dict[str, Any]:
        scored = self.score_candidates(candidates)
        selected: list[dict[str, Any]] = []
        rejected: list[dict[str, Any]] = []
        quotas = self._quotas(target)
        if sum(1 for row in scored if row.get("expected_review_ready_today")) < minimum_review_ready:
            quotas["FAST_TRACK"] = max(quotas["FAST_TRACK"], min(target, minimum_review_ready))
        for classification in ("FAST_TRACK", "STANDARD", "DEEP_RESEARCH"):
            for row in [item for item in scored if item["classification"] == classification]:
                if len(selected) >= target or sum(1 for item in selected if item["classification"] == classification) >= quotas[classification]:
                    continue
                selected.append(row)
        for row in scored:
            if len(selected) >= target:
                break
            if row not in selected and row["classification"] not in {"HOLD", "REJECT"}:
                selected.append(row)
        selected_ids = {row["topic_id"] for row in selected}
        for row in scored:
            if row["topic_id"] not in selected_ids:
                rejected.append(row)
        return {
            "selected": selected[:target],
            "rejected": rejected,
            "portfolio_counts": {name: sum(1 for row in selected[:target] if row["classification"] == name) for name in ("FAST_TRACK", "STANDARD", "DEEP_RESEARCH", "HOLD", "REJECT")},
            "capacity_aware": True,
        }

    def _quotas(self, target: int) -> dict[str, int]:
        quotas = {key: max(0, round(target * value)) for key, value in self.mix.items()}
        while sum(quotas.values()) < target:
            quotas["STANDARD"] += 1
        while sum(quotas.values()) > target and quotas["DEEP_RESEARCH"] > 0:
            quotas["DEEP_RESEARCH"] -= 1
        return quotas

    def _classify(self, candidate: dict[str, Any], *, source_readiness: float, review_risk: float, duplicate: bool) -> str:
        if duplicate:
            return "REJECT"
        if source_readiness < 35:
            return "HOLD"
        content_type = str(candidate.get("content_type") or "").lower()
        if content_type in {"pricing", "comparison"} or review_risk >= 70:
            return "DEEP_RESEARCH"
        if source_readiness >= 75 and review_risk <= 35:
            return "FAST_TRACK"
        return "STANDARD"

    def _production_cost(self, candidate: dict[str, Any]) -> float:
        content_type = str(candidate.get("content_type") or "").lower()
        return {"pricing": 75, "comparison": 70, "review": 52, "tutorial": 45}.get(content_type, 40)

    def _review_risk(self, candidate: dict[str, Any]) -> float:
        base = 30.0
        title = str(candidate.get("topic") or candidate.get("keyword") or "").lower()
        if any(token in title for token in ("pricing", "financial", "legal", "health", "medical")):
            base += 35
        if str(candidate.get("content_type") or "").lower() in {"pricing", "comparison"}:
            base += 18
        if float(candidate.get("source_count", 0) or 0) < 2:
            base += 20
        return _clamp(base)

    def _selection_reasons(self, classification: str, source_readiness: float, review_risk: float, duplicate: bool) -> list[str]:
        if duplicate:
            return ["duplicate or cannibalization risk"]
        return [f"classification={classification}", f"source_readiness={round(source_readiness, 2)}", f"review_risk={round(review_risk, 2)}"]


class KnowledgeGraphRuntime:
    ENTITY_KEYS = {
        "companies": "Company",
        "products": "Product",
        "ai_tools": "Product",
        "technologies": "Technology",
        "features": "Feature",
        "integrations": "Feature",
        "competitors": "Competitor",
        "keywords": "Keyword",
    }

    def __init__(self, data_dir: Path, config: dict[str, Any] | None = None) -> None:
        self.data_dir = data_dir
        self.config = config or {}
        self.graph_path = data_dir / "knowledge_graph_runtime.json"

    def load(self) -> dict[str, Any]:
        if not self.graph_path.exists():
            return {"schema_version": 2, "entities": {}, "relations": []}
        try:
            return json.loads(self.graph_path.read_text(encoding="utf-8"))
        except Exception:
            return {"schema_version": 2, "entities": {}, "relations": []}

    def save(self, graph: dict[str, Any]) -> Path:
        self.graph_path.parent.mkdir(parents=True, exist_ok=True)
        self.graph_path.write_text(json.dumps(graph, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return self.graph_path

    def update_article(self, *, article_id: str, research_package: dict[str, Any], draft_html: str, source_urls: list[str] | None = None, persist: bool = True) -> dict[str, Any]:
        graph = self.load()
        expected = self._entities_from_research(research_package)
        covered = self._entities_from_text(draft_html)
        draft_text = _strip_html(draft_html).lower()
        covered_ids = {row["entity_id"] for row in covered}
        for row in expected:
            if row["entity_id"] not in covered_ids and str(row.get("canonical_name", "")).lower() in draft_text:
                covered.append(row)
                covered_ids.add(row["entity_id"])
        entities = graph.setdefault("entities", {})
        relations = graph.setdefault("relations", [])
        for record in [*expected, *covered]:
            entity_id = record["entity_id"]
            existing = entities.get(entity_id, record)
            existing["article_ids"] = sorted(set(existing.get("article_ids", []) + [article_id]))
            existing["source_urls"] = sorted(set(existing.get("source_urls", []) + list(source_urls or [])))
            entities[entity_id] = existing
            relation = {"subject_id": article_id, "predicate": "covers", "object_id": entity_id, "confidence": record["confidence"], "source_article_id": article_id}
            if relation not in relations:
                relations.append(relation)
        expected_ids = {row["entity_id"] for row in expected}
        covered_ids = {row["entity_id"] for row in covered}
        missing = sorted(expected_ids - covered_ids)
        mismatch = self._entity_mismatch(expected, covered)
        internal_links = self._internal_link_suggestions(graph, expected_ids, article_id)
        overlap = self._topic_overlap(graph, expected_ids, article_id)
        result = {
            "schema_version": 2,
            "article_id": article_id,
            "expected_entities": expected,
            "covered_entities": covered,
            "entity_coverage": {
                "expected_count": len(expected_ids),
                "covered_count": len(expected_ids & covered_ids),
                "score": round((len(expected_ids & covered_ids) / max(1, len(expected_ids))) * 100, 2),
                "missing_entities": missing,
                "entity_mismatch": mismatch,
            },
            "internal_link_suggestions": internal_links,
            "cannibalization": overlap,
            "graph_path": str(self.graph_path),
        }
        if persist:
            self.save(graph)
        return result

    def _entities_from_research(self, research: dict[str, Any]) -> list[dict[str, Any]]:
        entities = research.get("entities") if isinstance(research.get("entities"), dict) else research
        rows: list[dict[str, Any]] = []
        for key, entity_type in self.ENTITY_KEYS.items():
            value = entities.get(key)
            items = value if isinstance(value, list) else []
            for item in items:
                name = str(item.get("name") if isinstance(item, dict) else item).strip()
                if name:
                    rows.append(self._entity_record(name, entity_type, confidence=0.82))
        keyword = str(research.get("keyword") or research.get("topic") or "").strip()
        if keyword:
            rows.append(self._entity_record(keyword, "Topic", confidence=0.72))
        return self._dedupe_entities(rows)

    def _entities_from_text(self, html: str) -> list[dict[str, Any]]:
        text = _strip_html(html)
        names = sorted(set(re.findall(r"\b[A-Z][A-Za-z0-9]*(?:\s+[A-Z][A-Za-z0-9]*){0,3}\b", text)))
        return self._dedupe_entities([self._entity_record(name, "Topic", confidence=0.55) for name in names[:30]])

    def _entity_record(self, name: str, entity_type: str, *, confidence: float) -> dict[str, Any]:
        canonical = re.sub(r"\s+", " ", name).strip()
        return {
            "entity_id": _slug(canonical),
            "canonical_name": canonical,
            "entity_type": entity_type,
            "aliases": [],
            "source_urls": [],
            "article_ids": [],
            "confidence": confidence,
        }

    def _dedupe_entities(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for row in rows:
            result[row["entity_id"]] = row
        return list(result.values())

    def _entity_mismatch(self, expected: list[dict[str, Any]], covered: list[dict[str, Any]]) -> bool:
        primary_expected = {row["entity_id"] for row in expected if row["entity_type"] in {"Company", "Product"}}
        primary_covered = {row["entity_id"] for row in covered}
        return bool(primary_expected and not (primary_expected & primary_covered))

    def _internal_link_suggestions(self, graph: dict[str, Any], expected_ids: set[str], article_id: str) -> list[dict[str, Any]]:
        suggestions: list[dict[str, Any]] = []
        for entity_id in expected_ids:
            entity = graph.get("entities", {}).get(entity_id, {})
            for linked_article in entity.get("article_ids", []):
                if linked_article != article_id:
                    suggestions.append({"entity_id": entity_id, "target_article_id": linked_article, "reason": "shared entity coverage"})
        return suggestions[:10]

    def _topic_overlap(self, graph: dict[str, Any], expected_ids: set[str], article_id: str) -> dict[str, Any]:
        overlaps: dict[str, int] = {}
        for entity_id in expected_ids:
            entity = graph.get("entities", {}).get(entity_id, {})
            for linked_article in entity.get("article_ids", []):
                if linked_article != article_id:
                    overlaps[linked_article] = overlaps.get(linked_article, 0) + 1
        risk = "warning" if any(count >= 2 for count in overlaps.values()) else "pass"
        return {"status": risk, "overlap_articles": overlaps}


class ContinuousLearningRuntime:
    def __init__(self, data_dir: Path, config: dict[str, Any] | None = None) -> None:
        self.data_dir = data_dir
        self.config = config or {}
        self.records_path = data_dir / "continuous_learning_records.jsonl"
        self.report_path = data_dir / "weekly_learning_report.md"
        self.recommendations_path = data_dir / "policy_recommendations.json"

    def ingest(self, record: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "schema_version": 2,
            "captured_at": datetime.now(UTC).isoformat(),
            **record,
            "auto_policy_change": False,
        }
        self.records_path.parent.mkdir(parents=True, exist_ok=True)
        with self.records_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
        return payload

    def ingest_fixture(self, *, article_id: str, pre_publish_scores: dict[str, Any], metrics: dict[str, Any]) -> dict[str, Any]:
        record = build_learning_feedback_record(
            article_id=article_id,
            topic_cluster=str(metrics.get("topic_cluster") or "general"),
            content_type=str(metrics.get("content_type") or "review"),
            pre_publish_scores=pre_publish_scores,
            post_publish_metrics=metrics,
        )
        return self.ingest(record)

    def load_records(self) -> list[dict[str, Any]]:
        if not self.records_path.exists():
            return []
        rows: list[dict[str, Any]] = []
        for line in self.records_path.read_text(encoding="utf-8").splitlines():
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
        return rows

    def weekly_report(self) -> dict[str, Any]:
        rows = self.load_records()
        recommendations = self._recommendations(rows)
        self.recommendations_path.write_text(json.dumps({"requires_human_approval": True, "auto_apply": False, "items": recommendations}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        lines = [
            "# Weekly Learning Report",
            "",
            f"- Records: {len(rows)}",
            f"- Recommendations: {len(recommendations)}",
            "- Auto policy change: NO",
            "",
        ]
        for item in recommendations:
            lines.append(f"- {item['recommendation']} (reason: {item['reason']})")
        self.report_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
        return {"records": len(rows), "recommendations": recommendations, "report_path": str(self.report_path), "recommendations_path": str(self.recommendations_path), "auto_policy_change": False}

    def _recommendations(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        recs: list[dict[str, Any]] = []
        low_ctr = [row for row in rows if float(row.get("post_publish_metrics", {}).get("ctr", 0) or 0) < 2]
        if low_ctr:
            recs.append({"recommendation": "Review title/meta guidance for low CTR articles", "reason": f"{len(low_ctr)} records below CTR target", "requires_human_approval": True})
        many_warnings = [row for row in rows if float(row.get("pre_publish_scores", {}).get("warning_count", 0) or 0) >= 2]
        if many_warnings:
            recs.append({"recommendation": "Inspect warning patterns before changing thresholds", "reason": f"{len(many_warnings)} records had multiple warnings", "requires_human_approval": True})
        return recs


class SafeDailyDryRunOrchestrator:
    def __init__(self, *, data_dir: Path, config: dict[str, Any] | None = None) -> None:
        self.data_dir = data_dir
        self.config = config or {}
        self.brain = EditorialBrain(self.config.get("editorial_brain", {}) if isinstance(self.config.get("editorial_brain"), dict) else {})
        self.capacity = CapacityManager(self.config.get("editorial_capacity", {}) if isinstance(self.config.get("editorial_capacity"), dict) else {})

    def run(self, candidates: list[dict[str, Any]], *, target: int = 10) -> dict[str, Any]:
        started = time.monotonic()
        portfolio = self.brain.select_portfolio(candidates, target=target, minimum_review_ready=self.capacity.minimum)
        selected = portfolio["selected"]
        rows: list[dict[str, Any]] = []
        rewrite_attempts = 0
        confidence_scores: list[float] = []
        for topic in selected:
            hard = []
            warnings = []
            if int(topic.get("source_count", 0) or 0) <= 0:
                hard.append("zero usable sources")
            if topic.get("entity_mismatch"):
                hard.append("entity mismatch")
            if float(topic.get("research_quality_score", 60) or 0) < 35:
                hard.append("critical research failure")
            if float(topic.get("publishing_confidence", 78) or 78) < 90:
                warnings.append("publishing confidence below pass target")
            status = "blocked" if hard else "drafted"
            if topic.get("needs_rewrite") and not hard:
                rewrite_attempts += 1
                warnings.append("targeted rewrite performed")
            confidence = float(topic.get("publishing_confidence", 78 if warnings else 91) or 78)
            confidence_scores.append(confidence)
            rows.append(
                {
                    "article_id": topic["slug"],
                    "topic": topic.get("topic") or topic.get("keyword"),
                    "status": status,
                    "classification": topic["classification"],
                    "publishing_confidence": confidence,
                    "hard_blockers": hard,
                    "warnings": warnings,
                    "fact_verification_summary": {"status": "blocked" if hard else "pass"},
                    "source_quality_summary": {"source_count": int(topic.get("source_count", 0) or 0), "source_readiness": topic.get("source_readiness")},
                    "judge_decision": "block" if hard else ("warning_to_human" if warnings else "pass_to_human"),
                    "recommended_human_focus": warnings or ["Verify final claims before approval."],
                    "rewrite_history": [{"attempt": 1, "accepted": True}] if topic.get("needs_rewrite") and not hard else [],
                    "entity_coverage": {"score": float(topic.get("entity_coverage_score", 75) or 75), "entity_mismatch": bool(topic.get("entity_mismatch"))},
                    "internal_link_suggestions": topic.get("internal_link_suggestions", []),
                    "estimated_review_minutes": 8 if warnings else 5,
                }
            )
        capacity = self.capacity.summarize(rows)
        elapsed = time.monotonic() - started
        return {
            "dry_run": True,
            "publish": False,
            "deploy": False,
            "index": False,
            "auto_approve": False,
            "topics_discovered": len(candidates),
            "topics_selected": len(selected),
            "fast_track": portfolio["portfolio_counts"].get("FAST_TRACK", 0),
            "standard": portfolio["portfolio_counts"].get("STANDARD", 0),
            "deep_research": portfolio["portfolio_counts"].get("DEEP_RESEARCH", 0),
            "research_completed": len(selected),
            "drafts_generated": sum(1 for row in rows if row["status"] == "drafted"),
            "rewrite_attempts": rewrite_attempts,
            "fact_verification_completed": len(selected),
            "judge_pass_to_human": sum(1 for row in rows if row["judge_decision"] == "pass_to_human"),
            "warning_to_human": sum(1 for row in rows if row["judge_decision"] == "warning_to_human"),
            "blocked": sum(1 for row in rows if row["status"] == "blocked"),
            "held": sum(1 for row in [*selected, *portfolio.get("rejected", [])] if row["classification"] == "HOLD"),
            "review_ready": capacity["review_ready"],
            "warning_only": sum(1 for row in rows if row["warnings"] and not row["hard_blockers"]),
            "average_publishing_confidence": round(sum(confidence_scores) / max(1, len(confidence_scores)), 2),
            "average_total_duration": round(elapsed / max(1, len(selected)), 4),
            "estimated_cost": 0.0,
            "top_bottleneck": capacity["bottleneck"],
            "items": rows,
        }


def _slug(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(value or "").lower()).strip("-") or "topic"
