from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class OutlineSection:
    name: str
    purpose: str
    priority: int


@dataclass(frozen=True)
class ContentOutlineResult:
    topic: str
    intent: str
    sections: list[OutlineSection]
    recommended_cta: str
    confidence: float
    reasoning: list[str] = field(default_factory=list)


class ContentOutlineEngine:
    """Rule-based content outline builder for planning-only workflows."""

    def __init__(self) -> None:
        self.intent_templates = {
            "informational": [
                OutlineSection("What is it", "Define the topic clearly", 1),
                OutlineSection("How to use", "Provide actionable steps", 2),
                OutlineSection("Use cases", "Show practical scenarios", 3),
                OutlineSection("FAQ", "Answer common questions", 4),
            ],
            "commercial": [
                OutlineSection("Quick verdict", "State the top recommendation early", 1),
                OutlineSection("Comparison", "Compare options and tradeoffs", 2),
                OutlineSection("Pros and cons", "Cover strengths and drawbacks", 3),
                OutlineSection("Pricing", "Explain cost and value", 4),
                OutlineSection("FAQ", "Address buyer concerns", 5),
            ],
            "transactional": [
                OutlineSection("Pricing", "Clarify plans and value", 1),
                OutlineSection("Best fit", "Explain who should buy", 2),
                OutlineSection("Pros and cons", "Highlight tradeoffs", 3),
                OutlineSection("CTA", "Guide the next step", 4),
            ],
        }

    def build_outline(self, topic: str, intent: str, keywords: list[str] | None = None) -> ContentOutlineResult:
        normalized_intent = (intent or "informational").lower()
        sections = self.intent_templates.get(normalized_intent, self.intent_templates["informational"])
        keyword_list = keywords or []
        cta = self._recommend_cta(normalized_intent)
        confidence = self._score_confidence(normalized_intent, keyword_list, sections)
        reasoning = self._build_reasoning(topic, normalized_intent, keyword_list, sections)
        return ContentOutlineResult(
            topic=topic.strip() or "topic",
            intent=normalized_intent,
            sections=list(sections),
            recommended_cta=cta,
            confidence=confidence,
            reasoning=reasoning,
        )

    def _recommend_cta(self, intent: str) -> str:
        if intent == "transactional":
            return "Compare plans and choose the option that fits your needs."
        if intent == "commercial":
            return "Review the comparison and shortlist the best option for your workflow."
        return "Read through the guide and apply the steps that match your use case."

    def _score_confidence(self, intent: str, keywords: list[str], sections: list[OutlineSection]) -> float:
        score = 0.55
        if keywords:
            score += 0.15
        if sections:
            score += 0.15
        if intent in self.intent_templates:
            score += 0.1
        return round(min(score, 0.95), 3)

    def _build_reasoning(self, topic: str, intent: str, keywords: list[str], sections: list[OutlineSection]) -> list[str]:
        reasons = [f"Built an outline for '{topic}' using the '{intent}' template."]
        if keywords:
            reasons.append(f"Used keyword signals: {', '.join(keywords[:3])}.")
        reasons.append(f"Included {len(sections)} planned sections for the article structure.")
        return reasons
