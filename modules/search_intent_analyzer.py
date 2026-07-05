from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class SearchIntentAnalysisResult:
    keyword: str
    search_intent: str
    intent_depth: str
    scope: str
    buyer_journey_stage: str
    funnel_stage: str
    scores: dict[str, float] = field(default_factory=dict)
    reasoning: list[str] = field(default_factory=list)


class SearchIntentAnalyzer:
    """Rule-based analyzer for search intent depth, scope, and funnel stage."""

    def __init__(self) -> None:
        self.intent_terms = {
            "informational": [
                "what is",
                "how to",
                "guide",
                "tutorial",
                "learn",
                "beginner",
                "examples",
                "overview",
            ],
            "commercial": [
                "best",
                "top",
                "review",
                "compare",
                "comparison",
                "vs",
                "versus",
                "alternatives",
                "alternative",
                "worth it",
                "for teams",
                "for business",
            ],
            "transactional": [
                "buy",
                "pricing",
                "price",
                "plans",
                "cost",
                "free trial",
                "demo",
                "sign up",
                "coupon",
                "discount",
            ],
            "navigational": [
                "official",
                "login",
                "sign in",
                "download",
                "docs",
                "home page",
                "site",
            ],
        }

    def analyze(self, keyword: str) -> SearchIntentAnalysisResult:
        normalized = self._normalize(keyword)
        search_intent = self._detect_intent(normalized)
        intent_depth = self._detect_depth(normalized, search_intent)
        scope = self._detect_scope(normalized, search_intent)
        buyer_journey_stage = self._detect_buyer_journey(normalized, search_intent, scope)
        funnel_stage = self._detect_funnel_stage(buyer_journey_stage)
        scores = self._build_scores(normalized, search_intent, intent_depth, scope, buyer_journey_stage, funnel_stage)
        reasoning = self._build_reasoning(normalized, search_intent, intent_depth, scope, buyer_journey_stage, funnel_stage)
        return SearchIntentAnalysisResult(
            keyword=keyword.strip(),
            search_intent=search_intent,
            intent_depth=intent_depth,
            scope=scope,
            buyer_journey_stage=buyer_journey_stage,
            funnel_stage=funnel_stage,
            scores=scores,
            reasoning=reasoning,
        )

    def classify(self, keyword: str) -> SearchIntentAnalysisResult:
        return self.analyze(keyword)

    def analyze_many(self, keywords: list[str]) -> list[SearchIntentAnalysisResult]:
        return [self.analyze(keyword) for keyword in keywords]

    def _normalize(self, keyword: str) -> str:
        cleaned = re.sub(r"[^a-z0-9\s-]", " ", (keyword or "").lower())
        return re.sub(r"\s+", " ", cleaned).strip()

    def _detect_intent(self, normalized: str) -> str:
        scores: dict[str, float] = {name: 0.0 for name in self.intent_terms}
        for intent, terms in self.intent_terms.items():
            for term in terms:
                if term in normalized:
                    scores[intent] += 1.0

        if "pricing" in normalized or "price" in normalized or "plans" in normalized or "buy" in normalized:
            scores["transactional"] += 1.0
        if normalized.startswith("how to") or normalized.startswith("what is"):
            scores["informational"] += 0.5
        if "official" in normalized or "login" in normalized or "sign in" in normalized:
            scores["navigational"] += 1.0

        best_intent, best_score = max(scores.items(), key=lambda item: item[1])
        if best_score <= 0.0:
            return "informational"
        return best_intent

    def _detect_depth(self, normalized: str, search_intent: str) -> str:
        if search_intent == "transactional":
            return "deep"
        if search_intent == "commercial":
            if any(term in normalized for term in ("best", "top", "comparison", "compare", "vs", "versus", "alternatives")):
                return "medium"
            return "shallow"
        if search_intent == "navigational":
            return "shallow"
        if any(term in normalized for term in ("how to", "guide", "tutorial", "step by step", "what is")):
            return "medium"
        return "shallow"

    def _detect_scope(self, normalized: str, search_intent: str) -> str:
        narrow_markers = [
            "for teams",
            "for business",
            "pricing",
            "price",
            "plans",
            "cost",
            "buy",
            "comparison",
            "compare",
            "vs",
            "versus",
            "alternatives",
            "alternative",
            "official",
            "login",
            "sign in",
        ]
        if any(marker in normalized for marker in narrow_markers):
            return "narrow"
        if search_intent == "commercial" and any(term in normalized for term in ("best", "top")):
            return "narrow"
        return "broad"

    def _detect_buyer_journey(self, normalized: str, search_intent: str, scope: str) -> str:
        if search_intent == "transactional" or "pricing" in normalized or "plans" in normalized or "buy" in normalized:
            return "decision"
        if search_intent == "commercial" or scope == "narrow":
            return "consideration"
        return "awareness"

    def _detect_funnel_stage(self, buyer_journey_stage: str) -> str:
        mapping = {
            "awareness": "top",
            "consideration": "middle",
            "decision": "bottom",
        }
        return mapping.get(buyer_journey_stage, "top")

    def _build_scores(
        self,
        normalized: str,
        search_intent: str,
        intent_depth: str,
        scope: str,
        buyer_journey_stage: str,
        funnel_stage: str,
    ) -> dict[str, float]:
        depth_score = {"shallow": 0.35, "medium": 0.6, "deep": 0.85}[intent_depth]
        scope_score = 0.8 if scope == "narrow" else 0.35
        buyer_score = {"awareness": 0.4, "consideration": 0.7, "decision": 0.9}[buyer_journey_stage]
        funnel_score = {"top": 0.35, "middle": 0.7, "bottom": 0.9}[funnel_stage]
        if search_intent == "transactional":
            depth_score += 0.1
            scope_score += 0.1
        elif search_intent == "commercial":
            scope_score += 0.05
        return {
            "intent_depth": round(depth_score, 3),
            "scope": round(scope_score, 3),
            "buyer_journey": round(buyer_score, 3),
            "funnel": round(funnel_score, 3),
        }

    def _build_reasoning(
        self,
        normalized: str,
        search_intent: str,
        intent_depth: str,
        scope: str,
        buyer_journey_stage: str,
        funnel_stage: str,
    ) -> list[str]:
        reasons = [f"Detected search intent '{search_intent}' from the query."]
        reasons.append(f"Intent depth classified as {intent_depth} based on query specificity.")
        reasons.append(f"Scope classified as {scope} based on narrowing terms and product intent.")
        reasons.append(f"Buyer journey stage is {buyer_journey_stage} and funnel stage is {funnel_stage}.")
        if normalized:
            reasons.append(f"Normalized query: {normalized}.")
        return reasons
