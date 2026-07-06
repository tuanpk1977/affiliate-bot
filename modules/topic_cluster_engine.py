from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from modules.keyword_intent_engine import KeywordIntentEngine
from modules.search_intent_analyzer import SearchIntentAnalyzer


@dataclass(frozen=True)
class TopicClusterAnalysisResult:
    seed_topic: str
    parent_topic: str
    clusters: list[dict[str, Any]]
    supporting_topics: list[str]
    buyer_keywords: list[str]
    informational_keywords: list[str]
    comparison_keywords: list[str]
    pillar_page_suggestion: str
    supporting_article_ideas: list[str]
    confidence: float
    reasoning: list[str] = field(default_factory=list)


class TopicClusterEngine:
    """Rule-based topic clustering engine for content planning."""

    def __init__(self) -> None:
        self.intent_engine = KeywordIntentEngine()
        self.search_analyzer = SearchIntentAnalyzer()

    def analyze(self, keywords: list[str], seed_topic: str | None = None) -> TopicClusterAnalysisResult:
        seed = (seed_topic or "").strip() or self._infer_seed_topic(keywords)
        normalized_keywords = [self._normalize(keyword) for keyword in keywords if keyword and str(keyword).strip()]

        clusters = self._build_clusters(normalized_keywords, seed)
        supporting_topics = self._detect_supporting_topics(normalized_keywords, seed)
        buyer_keywords = self._detect_keyword_group(normalized_keywords, ["best", "top", "review", "pricing", "plans", "buy", "trial"])
        informational_keywords = self._detect_keyword_group(normalized_keywords, ["how to", "guide", "tutorial", "what is", "learn", "beginner", "use cases"])
        comparison_keywords = self._detect_keyword_group(normalized_keywords, ["vs", "versus", "compare", "comparison", "alternatives", "alternative"])
        pillar_page_suggestion = self._suggest_pillar_page(seed, supporting_topics)
        supporting_article_ideas = self._suggest_supporting_articles(seed, supporting_topics, buyer_keywords, informational_keywords, comparison_keywords)
        confidence = self._score_confidence(clusters, supporting_topics, buyer_keywords, informational_keywords, comparison_keywords)
        reasoning = self._build_reasoning(seed, clusters, supporting_topics, buyer_keywords, informational_keywords, comparison_keywords)

        return TopicClusterAnalysisResult(
            seed_topic=seed,
            parent_topic=seed,
            clusters=clusters,
            supporting_topics=supporting_topics,
            buyer_keywords=buyer_keywords,
            informational_keywords=informational_keywords,
            comparison_keywords=comparison_keywords,
            pillar_page_suggestion=pillar_page_suggestion,
            supporting_article_ideas=supporting_article_ideas,
            confidence=confidence,
            reasoning=reasoning,
        )

    def _infer_seed_topic(self, keywords: list[str]) -> str:
        if not keywords:
            return "topic"
        return self._normalize(keywords[0]).split()[0] if self._normalize(keywords[0]) else "topic"

    def _normalize(self, keyword: str) -> str:
        cleaned = re.sub(r"[^a-z0-9\s-]", " ", (keyword or "").lower())
        return re.sub(r"\s+", " ", cleaned).strip()

    def _build_clusters(self, keywords: list[str], seed_topic: str) -> list[dict[str, Any]]:
        cluster = {
            "name": seed_topic,
            "keywords": keywords,
            "weight": 1.0,
            "reason": "Primary topic cluster derived from seed topic and related keywords.",
        }
        return [cluster]

    def _detect_supporting_topics(self, keywords: list[str], seed_topic: str) -> list[str]:
        support: list[str] = []
        seed_norm = self._normalize(seed_topic)
        for keyword in keywords:
            normalized = self._normalize(keyword)
            if not normalized:
                continue
            if seed_norm and normalized == seed_norm:
                continue
            if any(marker in normalized for marker in ("pricing", "plans", "use cases", "tutorial", "guide", "best", "alternatives", "comparison", "vs", "review", "price")):
                support.append(keyword)
        if not support:
            support = [keyword for keyword in keywords if keyword][:3]
        return support[:5]

    def _detect_keyword_group(self, keywords: list[str], markers: list[str]) -> list[str]:
        matched: list[str] = []
        for keyword in keywords:
            if any(marker in keyword for marker in markers):
                matched.append(keyword)
        return matched

    def _suggest_pillar_page(self, seed_topic: str, supporting_topics: list[str]) -> str:
        if not seed_topic:
            return "Pillar page: Topic hub"
        return f"Pillar page: {seed_topic} hub with supporting guides, comparisons, and buyer-intent content"

    def _suggest_supporting_articles(self, seed_topic: str, supporting_topics: list[str], buyer_keywords: list[str], informational_keywords: list[str], comparison_keywords: list[str]) -> list[str]:
        ideas: list[str] = []
        if buyer_keywords:
            ideas.append(f"Buyer-guide article for {seed_topic} with pricing and comparison context")
        if informational_keywords:
            ideas.append(f"How-to article for {seed_topic} with practical setup and beginner guidance")
        if comparison_keywords:
            ideas.append(f"Comparison article for {seed_topic} versus top alternatives")
        if supporting_topics:
            ideas.append(f"Supporting article on {supporting_topics[0]} for deeper topical coverage")
        return ideas[:4]

    def _score_confidence(self, clusters: list[dict[str, Any]], supporting_topics: list[str], buyer_keywords: list[str], informational_keywords: list[str], comparison_keywords: list[str]) -> float:
        score = 0.4
        if clusters:
            score += 0.2
        if supporting_topics:
            score += 0.15
        if buyer_keywords:
            score += 0.1
        if informational_keywords:
            score += 0.1
        if comparison_keywords:
            score += 0.1
        return round(min(score, 0.95), 3)

    def _build_reasoning(self, seed_topic: str, clusters: list[dict[str, Any]], supporting_topics: list[str], buyer_keywords: list[str], informational_keywords: list[str], comparison_keywords: list[str]) -> list[str]:
        reasons = [f"Clustered keywords around the seed topic '{seed_topic}'."]
        reasons.append(f"Created {len(clusters)} cluster(s) with the primary topic as the parent topic.")
        if supporting_topics:
            reasons.append(f"Detected supporting topics: {', '.join(supporting_topics[:3])}.")
        if buyer_keywords:
            reasons.append(f"Detected buyer keywords: {', '.join(buyer_keywords[:3])}.")
        if informational_keywords:
            reasons.append(f"Detected informational keywords: {', '.join(informational_keywords[:3])}.")
        if comparison_keywords:
            reasons.append(f"Detected comparison keywords: {', '.join(comparison_keywords[:3])}.")
        return reasons
