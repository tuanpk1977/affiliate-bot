from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class SerpCoverageAnalysisResult:
    topic: str
    coverage_score: int
    planned_sections: list[str]
    missing_subtopics: list[str]
    missing_entities: list[str]
    faq_opportunities: list[str]
    comparison_gaps: list[str]
    missing_sections: list[str]
    improvement_suggestions: list[str]
    reasoning: list[str] = field(default_factory=list)


class SerpCoverageAnalyzer:
    """Rule-based analyzer for estimating topical coverage of a planned article."""

    def __init__(self) -> None:
        self.subtopic_markers = [
            "pricing",
            "use cases",
            "alternatives",
            "comparison",
            "tutorial",
            "review",
            "best",
            "faq",
            "pros and cons",
            "limitations",
        ]
        self.entity_markers = ["copilot", "cursor", "windsurf", "chatgpt", "claude"]
        self.faq_markers = ["what", "how", "why", "when", "who"]
        self.comparison_markers = ["vs", "versus", "compare", "alternatives", "alternative"]
        self.buyer_question_markers = ["pricing", "plans", "cost", "best", "review", "worth it", "compare"]

    def analyze(self, planned_sections: list[str], entities: list[str], keywords: list[str], topic: str | None = None) -> SerpCoverageAnalysisResult:
        topic_name = (topic or "topic").strip() or "topic"
        normalized_sections = [self._normalize(section) for section in planned_sections if section and str(section).strip()]
        normalized_keywords = [self._normalize(keyword) for keyword in keywords if keyword and str(keyword).strip()]
        normalized_entities = [self._normalize(entity) for entity in entities if entity and str(entity).strip()]

        missing_subtopics = self._detect_missing_subtopics(normalized_sections)
        missing_entities = self._detect_missing_entities(normalized_entities, normalized_keywords)
        faq_opportunities = self._detect_faq_opportunities(normalized_keywords, normalized_sections)
        comparison_gaps = self._detect_comparison_gaps(normalized_keywords, normalized_sections)
        missing_sections = self._detect_missing_sections(normalized_sections)
        improvement_suggestions = self._build_improvement_suggestions(missing_subtopics, missing_entities, faq_opportunities, comparison_gaps, missing_sections)
        coverage_score = self._score_coverage(normalized_sections, normalized_entities, normalized_keywords, missing_subtopics, missing_entities, faq_opportunities, comparison_gaps)
        reasoning = self._build_reasoning(topic_name, coverage_score, missing_subtopics, missing_entities, faq_opportunities, comparison_gaps, missing_sections)

        return SerpCoverageAnalysisResult(
            topic=topic_name,
            coverage_score=coverage_score,
            planned_sections=planned_sections,
            missing_subtopics=missing_subtopics,
            missing_entities=missing_entities,
            faq_opportunities=faq_opportunities,
            comparison_gaps=comparison_gaps,
            missing_sections=missing_sections,
            improvement_suggestions=improvement_suggestions,
            reasoning=reasoning,
        )

    def _normalize(self, text: str) -> str:
        cleaned = re.sub(r"[^a-z0-9\s-]", " ", (text or "").lower())
        return re.sub(r"\s+", " ", cleaned).strip()

    def _detect_missing_subtopics(self, planned_sections: list[str]) -> list[str]:
        covered = set(planned_sections)
        missing = []
        for marker in self.subtopic_markers:
            if marker not in covered:
                missing.append(marker)
        return missing

    def _detect_missing_entities(self, entities: list[str], keywords: list[str]) -> list[str]:
        keyword_text = " ".join(keywords)
        candidate_entities = [entity for entity in entities if entity]
        if not candidate_entities:
            candidate_entities = [entity for entity in self.entity_markers if entity in keyword_text]
        if not candidate_entities:
            return []

        missing = []
        for entity in candidate_entities:
            if entity not in keyword_text:
                missing.append(entity)
        return missing[:3]

    def _detect_faq_opportunities(self, keywords: list[str], planned_sections: list[str]) -> list[str]:
        opportunities = []
        for keyword in keywords:
            normalized = self._normalize(keyword)
            if normalized.startswith("what ") or normalized.startswith("how ") or normalized.startswith("why ") or normalized.startswith("when ") or normalized.startswith("who ") or "faq" in normalized or "what is" in normalized or "how to" in normalized:
                opportunities.append(keyword)
        return opportunities[:4]

    def _detect_comparison_gaps(self, keywords: list[str], planned_sections: list[str]) -> list[str]:
        gaps = []
        if not any(marker in " ".join(planned_sections) for marker in self.comparison_markers):
            for keyword in keywords:
                if any(marker in keyword for marker in self.comparison_markers):
                    gaps.append(keyword)
        return gaps[:4]

    def _detect_missing_sections(self, planned_sections: list[str]) -> list[str]:
        missing = []
        if "pricing" not in planned_sections:
            missing.append("pricing")
        if not any(section in planned_sections for section in ("comparison", "vs", "alternatives")):
            missing.append("comparison")
        if "faq" not in planned_sections:
            missing.append("faq")
        return missing

    def _build_improvement_suggestions(self, missing_subtopics: list[str], missing_entities: list[str], faq_opportunities: list[str], comparison_gaps: list[str], missing_sections: list[str]) -> list[str]:
        suggestions = []
        if missing_subtopics:
            suggestions.append("Add a dedicated section for the missing subtopics to improve topical depth.")
        if missing_entities:
            suggestions.append("Add entity coverage for the missing competitors or alternatives to strengthen topical context.")
        if faq_opportunities:
            suggestions.append("Add FAQ-style buyer questions to address common concerns and support intent matching.")
        if comparison_gaps:
            suggestions.append("Add comparison content or a comparison table to cover buyer decision questions.")
        if missing_sections:
            suggestions.append("Include buyer-oriented sections such as pricing, comparison, and FAQ to improve coverage.")
        return suggestions

    def _score_coverage(self, planned_sections: list[str], entities: list[str], keywords: list[str], missing_subtopics: list[str], missing_entities: list[str], faq_opportunities: list[str], comparison_gaps: list[str]) -> int:
        score = 60
        section_hits = 0
        for section in ["what is", "how to", "best", "pricing", "faq"]:
            if any(section in planned_section for planned_section in planned_sections):
                section_hits += 1
        score += min(section_hits * 6, 24)
        if entities:
            score += 6
        if keywords:
            score += 4
        if not missing_subtopics:
            score += 4
        if not missing_entities:
            score += 4
        if not faq_opportunities:
            score += 4
        if not comparison_gaps:
            score += 4
        return max(0, min(100, score))

    def _build_reasoning(self, topic: str, coverage_score: int, missing_subtopics: list[str], missing_entities: list[str], faq_opportunities: list[str], comparison_gaps: list[str], missing_sections: list[str]) -> list[str]:
        reasons = [f"Estimated SERP coverage for '{topic}' at {coverage_score}/100."]
        if missing_subtopics:
            reasons.append(f"Missing subtopics: {', '.join(missing_subtopics)}.")
        if missing_entities:
            reasons.append(f"Missing entity coverage: {', '.join(missing_entities)}.")
        if faq_opportunities:
            reasons.append(f"FAQ opportunities: {', '.join(faq_opportunities[:3])}.")
        if comparison_gaps:
            reasons.append(f"Comparison gaps: {', '.join(comparison_gaps[:3])}.")
        if missing_sections:
            reasons.append(f"Missing sections: {', '.join(missing_sections)}.")
        return reasons
