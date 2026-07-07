from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from modules.content_outline_engine import ContentOutlineResult, ContentOutlineEngine
from modules.keyword_intent_engine import IntentAnalysisResult, KeywordIntentEngine
from modules.search_intent_analyzer import SearchIntentAnalysisResult, SearchIntentAnalyzer
from modules.serp_coverage_analyzer import SerpCoverageAnalysisResult, SerpCoverageAnalyzer
from modules.topic_cluster_engine import TopicClusterAnalysisResult, TopicClusterEngine
@dataclass(frozen=True)
class ContentPlanResult:
    """Structured content plan with all planning components."""
    keyword: str
    search_intent: str
    article_type: str
    cluster: dict[str, Any]
    coverage_score: int
    outline_sections: list[str]
    recommended_cta: str
    confidence: float
    reasoning: list[str] = field(default_factory=list)
class ContentPlanningEngine:
    """Orchestrator that coordinates all content planning engines to produce a complete plan."""

    def __init__(self) -> None:
        self.keyword_engine = KeywordIntentEngine()
        self.search_analyzer = SearchIntentAnalyzer()
        self.topic_clusterer = TopicClusterEngine()
        self.coverage_analyzer = SerpCoverageAnalyzer()
        self.outline_engine = ContentOutlineEngine()

    def create_plan(self, keyword: str, related_keywords: list[str] | None = None, entities: list[str] | None = None) -> ContentPlanResult:
        """Create a comprehensive content plan using all available engines."""
        related = list({kw for kw in (related_keywords or []) if kw})

        keyword_result = self.keyword_engine.analyze(keyword)
        search_result = self.search_analyzer.analyze(keyword)

        cluster_result = self.topic_clusterer.analyze(related, seed_topic=keyword)

        outline_result = self.outline_engine.build_outline(
            topic=keyword,
            intent=keyword_result.search_intent,
            keywords=related,
        )

        coverage_result = self.coverage_analyzer.analyze(
            planned_sections=[s.name for s in outline_result.sections],
            entities=entities or ["copilot", "cursor", "windsurf", "chatgpt", "claude"],
            keywords=[keyword] + related,
            topic=keyword,
        )

        plan = self._build_result(
            keyword_result=keyword_result,
            search_result=search_result,
            cluster_result=cluster_result,
            outline_result=outline_result,
            coverage_result=coverage_result,
        )
        return plan

    def create_plan_many(self, keywords: list[str], related_keywords_per_keyword: dict[str, list[str]] | None = None, entities_per_keyword: dict[str, list[str]] | None = None) -> list[ContentPlanResult]:
        """Create plans for multiple keywords, returning a plan for each."""
        related_keywords_per_keyword = related_keywords_per_keyword or {}
        entities_per_keyword = entities_per_keyword or {}
        return [
            self.create_plan(
                keyword=kw,
                related_keywords=related_keywords_per_keyword.get(kw, []),
                entities=entities_per_keyword.get(kw, []),
            )
            for kw in keywords
        ]

    def _build_result(
        self,
        keyword_result: IntentAnalysisResult,
        search_result: SearchIntentAnalysisResult,
        cluster_result: TopicClusterAnalysisResult,
        outline_result: ContentOutlineResult,
        coverage_result: SerpCoverageAnalysisResult,
    ) -> ContentPlanResult:
        cluster_keywords = cluster_result.clusters[0].get("keywords") if cluster_result.clusters else []

        return ContentPlanResult(
            keyword=keyword_result.keyword,
            search_intent=search_result.search_intent,
            article_type=keyword_result.article_type,
            cluster={
                "name": keyword_result.keyword,
                "seed_topic": cluster_result.seed_topic,
                "clusters": cluster_result.clusters,
                "supporting_topics": cluster_result.supporting_topics,
                "keywords": cluster_keywords if cluster_keywords else [keyword_result.keyword],
                "confidence": cluster_result.confidence,
                "reasoning": cluster_result.reasoning,
            },
            coverage_score=coverage_result.coverage_score,
            outline_sections=[s.name for s in outline_result.sections],
            recommended_cta=outline_result.recommended_cta,
            confidence=self._calculate_overall_confidence(
                keyword_result, search_result, coverage_result, outline_result,
            ),
            reasoning=self._build_reasoning(
                keyword_result, search_result, cluster_result, outline_result, coverage_result,
            ),
        )

    def _calculate_overall_confidence(
        self,
        keyword_result: IntentAnalysisResult,
        search_result: SearchIntentAnalysisResult,
        coverage_result: SerpCoverageAnalysisResult,
        outline_result: ContentOutlineResult,
    ) -> float:
        intent_conf = (keyword_result.intent_confidence + keyword_result.article_type_confidence) / 2.0
        search_conf = search_result.scores["buyer_journey"] if search_result.scores else 0.5
        coverage_conf = coverage_result.coverage_score / 100.0
        outline_conf = outline_result.confidence

        avg_conf = (intent_conf + search_conf + coverage_conf + outline_conf) / 4.0
        return round(min(max(avg_conf, 0.0), 1.0), 3)

    def _build_reasoning(
        self,
        keyword_result: IntentAnalysisResult,
        search_result: SearchIntentAnalysisResult,
        cluster_result: TopicClusterAnalysisResult,
        outline_result: ContentOutlineResult,
        coverage_result: SerpCoverageAnalysisResult,
    ) -> list[str]:
        reasoning: list[str] = []
        reasoning.extend(keyword_result.reasoning)
        reasoning.extend(search_result.reasoning)
        reasoning.append(f"Topic clustering confidence: {cluster_result.confidence}")
        reasoning.extend(cluster_result.reasoning)
        reasoning.extend(outline_result.reasoning)
        reasoning.extend(coverage_result.reasoning)
        reasoning.append(f"Overall planning confidence: {self._calculate_overall_confidence(keyword_result, search_result, coverage_result, outline_result)}")
        return reasoning