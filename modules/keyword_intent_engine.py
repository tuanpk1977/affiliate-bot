from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class IntentAnalysisResult:
    keyword: str
    search_intent: str
    article_type: str
    intent_confidence: float
    article_type_confidence: float
    confidence_scores: dict[str, float] = field(default_factory=dict)
    reasoning: list[str] = field(default_factory=list)


class KeywordIntentEngine:
    """Rule-based intent and article-type classifier for SEO content planning."""

    def __init__(self) -> None:
        self.intent_terms = {
            "informational": [
                ("how to", 0.95),
                ("tutorial", 0.95),
                ("guide", 0.8),
                ("what is", 0.9),
                ("why", 0.7),
                ("learn", 0.7),
                ("beginner", 0.6),
                ("examples", 0.6),
            ],
            "commercial": [
                ("best", 0.95),
                ("review", 0.9),
                ("comparison", 0.95),
                ("compare", 0.95),
                ("vs", 0.95),
                ("versus", 0.95),
                ("alternatives", 0.95),
                ("alternative", 0.9),
                ("top", 0.85),
                ("for teams", 0.6),
                ("for business", 0.6),
                ("worth it", 0.8),
            ],
            "transactional": [
                ("pricing", 0.98),
                ("price", 0.95),
                ("plans", 0.9),
                ("cost", 0.95),
                ("buy", 0.9),
                ("free trial", 0.85),
                ("discount", 0.8),
                ("coupon", 0.8),
                ("demo", 0.7),
            ],
            "navigational": [
                ("official", 0.9),
                ("login", 0.95),
                ("sign in", 0.95),
                ("download", 0.8),
                ("docs", 0.7),
                ("home page", 0.7),
                ("site", 0.6),
            ],
        }
        self.article_type_terms = {
            "review": [("review", 0.95), ("worth it", 0.85), ("rating", 0.8)],
            "comparison": [("vs", 0.98), ("versus", 0.98), ("comparison", 0.95), ("compare", 0.95)],
            "alternatives": [("alternatives", 0.95), ("alternative", 0.9), ("other options", 0.8)],
            "best list": [("best", 0.95), ("top", 0.85), ("top 10", 0.9)],
            "tutorial": [("how to", 0.98), ("tutorial", 0.95), ("guide", 0.8), ("step by step", 0.9)],
            "pricing": [("pricing", 0.98), ("price", 0.95), ("plans", 0.9), ("cost", 0.95)],
            "use cases": [("use case", 0.95), ("use cases", 0.95), ("who should use", 0.8)],
        }

    def analyze(self, keyword: str) -> IntentAnalysisResult:
        normalized = self._normalize(keyword)
        intent_scores = self._score_intents(normalized)
        search_intent = self._select_best(intent_scores, fallback="commercial")
        article_type_scores = self._score_article_types(normalized, search_intent)
        article_type = self._select_best(article_type_scores, fallback="review")
        intent_confidence = round(intent_scores.get(search_intent, 0.0), 3)
        article_type_confidence = round(article_type_scores.get(article_type, 0.0), 3)
        reasoning = self._build_reasoning(normalized, search_intent, article_type, intent_scores, article_type_scores)
        return IntentAnalysisResult(
            keyword=keyword.strip(),
            search_intent=search_intent,
            article_type=article_type,
            intent_confidence=intent_confidence,
            article_type_confidence=article_type_confidence,
            confidence_scores={
                "search_intent": intent_confidence,
                "article_type": article_type_confidence,
                **{name: round(score, 3) for name, score in intent_scores.items()},
            },
            reasoning=reasoning,
        )

    def classify(self, keyword: str) -> IntentAnalysisResult:
        return self.analyze(keyword)

    def analyze_many(self, keywords: list[str]) -> list[IntentAnalysisResult]:
        return [self.analyze(keyword) for keyword in keywords]

    def _normalize(self, keyword: str) -> str:
        cleaned = re.sub(r"[^a-z0-9\s-]", " ", (keyword or "").lower())
        return re.sub(r"\s+", " ", cleaned).strip()

    def _score_intents(self, normalized: str) -> dict[str, float]:
        scores: dict[str, float] = {name: 0.0 for name in self.intent_terms}
        for intent, terms in self.intent_terms.items():
            for term, weight in terms:
                if term in normalized:
                    scores[intent] += weight
            if intent == "navigational" and any(token in normalized for token in ("official", "login", "sign in", "download", "docs")):
                scores[intent] += 0.15
        if normalized.startswith("how to"):
            scores["informational"] += 0.2
        if "pricing" in normalized or "price" in normalized or "plans" in normalized:
            scores["transactional"] += 0.2
        if scores["transactional"] >= 0.5 and scores["commercial"] >= 0.5:
            scores["commercial"] = max(scores["commercial"] - 0.1, 0.0)
        if scores["navigational"] >= 0.8 and scores["commercial"] >= 0.4:
            scores["commercial"] = max(scores["commercial"] - 0.1, 0.0)
        return scores

    def _score_article_types(self, normalized: str, search_intent: str) -> dict[str, float]:
        scores: dict[str, float] = {name: 0.0 for name in self.article_type_terms}
        for article_type, terms in self.article_type_terms.items():
            for term, weight in terms:
                if term in normalized:
                    scores[article_type] += weight
        if search_intent == "transactional" and ("pricing" in normalized or "price" in normalized or "plans" in normalized):
            scores["pricing"] += 0.3
        if search_intent == "informational" and ("how to" in normalized or "tutorial" in normalized):
            scores["tutorial"] += 0.3
        if search_intent == "commercial" and ("vs" in normalized or "versus" in normalized or "comparison" in normalized):
            scores["comparison"] += 0.3
        if search_intent == "commercial" and ("alternative" in normalized or "alternatives" in normalized):
            scores["alternatives"] += 0.3
        if search_intent == "commercial" and ("best" in normalized or "top" in normalized):
            scores["best list"] += 0.3
        if search_intent == "commercial" and ("use case" in normalized or "use cases" in normalized):
            scores["use cases"] += 0.3
        if search_intent == "navigational":
            scores["review"] += 0.4
        return scores

    def _select_best(self, scores: dict[str, float], fallback: str) -> str:
        if not scores:
            return fallback
        best_name, best_score = max(scores.items(), key=lambda item: item[1])
        if best_score <= 0.0:
            return fallback
        return best_name

    def _build_reasoning(
        self,
        normalized: str,
        search_intent: str,
        article_type: str,
        intent_scores: dict[str, float],
        article_type_scores: dict[str, float],
    ) -> list[str]:
        matched_intent_terms = [
            term for intent, terms in self.intent_terms.items() if intent == search_intent for term, _ in terms if term in normalized
        ]
        matched_article_terms = [
            term for article_type_name, terms in self.article_type_terms.items() if article_type_name == article_type for term, _ in terms if term in normalized
        ]
        reasons = [f"Detected search intent '{search_intent}' from the query." ]
        if matched_intent_terms:
            reasons.append(f"Matched intent terms: {', '.join(matched_intent_terms[:4])}.")
        if matched_article_terms:
            reasons.append(f"Matched article-type terms: {', '.join(matched_article_terms[:4])}.")
        reasons.append(f"Intent confidence {round(intent_scores.get(search_intent, 0.0), 3)}; article-type confidence {round(article_type_scores.get(article_type, 0.0), 3)}.")
        return reasons
