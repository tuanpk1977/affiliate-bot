from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class QualityGateResult:
    title_quality: float
    meta_description_quality: float
    search_intent_match: float
    duplicate_keyword_risk: float
    duplicate_h1_title_risk: float
    thin_content: float
    eeat_signals: float
    internal_links: float
    schema_hints: float
    affiliate_cta_quality: float
    overall_score: float
    passed: bool
    report_only: bool = True
    publish_blocked: bool = False
    issues: List[str] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)


class PrePublishQualityGate:
    def __init__(self, minimum_score: float = 85.0, report_only: bool = True) -> None:
        self.minimum_score = float(minimum_score)
        self.report_only = report_only

    def evaluate_article(
        self,
        *,
        title: str,
        content: str,
        meta_description: str,
        slug: str,
        topic: str,
        existing_titles: Optional[List[str]] = None,
        existing_h1s: Optional[List[str]] = None,
        existing_keywords: Optional[List[str]] = None,
        internal_links: Optional[List[str]] = None,
        schema_hints: Optional[List[str]] = None,
    ) -> QualityGateResult:
        title_text = (title or "").strip()
        content_text = (content or "").strip()
        meta_text = (meta_description or "").strip()
        topic_text = (topic or "").strip()
        slug_text = (slug or "").strip()

        title_quality = self._score_title_quality(title_text, content_text, topic_text)
        meta_description_quality = self._score_meta_description(meta_text)
        search_intent_match = self._score_search_intent(title_text, content_text, topic_text)
        duplicate_keyword_risk = self._score_duplicate_keyword_risk(topic_text, slug_text, content_text, existing_keywords or [])
        duplicate_h1_title_risk = self._score_duplicate_h1_title_risk(title_text, existing_titles or [], existing_h1s or [])
        thin_content = self._score_thin_content(content_text)
        eeat_signals = self._score_eeat_signals(content_text)
        internal_links_score = self._score_internal_links(internal_links or [])
        schema_hints_score = self._score_schema_hints(schema_hints or [])
        affiliate_cta_quality = self._score_affiliate_cta(content_text)

        overall_score = round(
            (
                title_quality
                + meta_description_quality
                + search_intent_match
                + duplicate_keyword_risk
                + duplicate_h1_title_risk
                + thin_content
                + eeat_signals
                + internal_links_score
                + schema_hints_score
                + affiliate_cta_quality
            ) / 10.0,
            1,
        )

        issues: List[str] = []
        if title_quality < 70:
            issues.append("title quality below threshold")
        if meta_description_quality < 70:
            issues.append("meta description below threshold")
        if search_intent_match < 70:
            issues.append("search intent mismatch")
        if duplicate_keyword_risk < 70:
            issues.append("duplicate keyword risk")
        if duplicate_h1_title_risk < 70:
            issues.append("duplicate H1/title risk")
        if thin_content < 70:
            issues.append("thin content")
        if eeat_signals < 70:
            issues.append("weak E-E-A-T signals")
        if internal_links_score < 70:
            issues.append("insufficient internal links")
        if schema_hints_score < 70:
            issues.append("weak schema hints")
        if affiliate_cta_quality < 70:
            issues.append("affiliate CTA quality below threshold")

        return QualityGateResult(
            title_quality=round(title_quality, 1),
            meta_description_quality=round(meta_description_quality, 1),
            search_intent_match=round(search_intent_match, 1),
            duplicate_keyword_risk=round(duplicate_keyword_risk, 1),
            duplicate_h1_title_risk=round(duplicate_h1_title_risk, 1),
            thin_content=round(thin_content, 1),
            eeat_signals=round(eeat_signals, 1),
            internal_links=round(internal_links_score, 1),
            schema_hints=round(schema_hints_score, 1),
            affiliate_cta_quality=round(affiliate_cta_quality, 1),
            overall_score=overall_score,
            passed=overall_score >= self.minimum_score,
            report_only=self.report_only,
            publish_blocked=False,
            issues=issues,
            details={
                "minimum_score": self.minimum_score,
                "slug": slug_text,
                "topic": topic_text,
            },
        )

    def _score_title_quality(self, title: str, content: str, topic: str) -> float:
        if not title:
            return 0.0
        score = 70.0
        if len(title) >= 45 and len(title) <= 70:
            score += 15
        elif len(title) >= 25:
            score += 10
        if topic.lower() in title.lower():
            score += 10
        if self._contains_buying_intent(title):
            score += 5
        if len(content.split()) < 120:
            score -= 5
        return min(100.0, max(0.0, score))

    def _score_meta_description(self, meta_description: str) -> float:
        if not meta_description:
            return 0.0
        score = 70.0
        if len(meta_description) >= 120 and len(meta_description) <= 160:
            score += 20
        elif len(meta_description) >= 90:
            score += 10
        if any(term in meta_description.lower() for term in ("compare", "best", "pricing", "guide", "review")):
            score += 10
        return min(100.0, max(0.0, score))

    def _score_search_intent(self, title: str, content: str, topic: str) -> float:
        lower_content = content.lower()
        lower_title = title.lower()
        score = 60.0
        if topic.lower() in lower_title:
            score += 15
        if any(term in lower_content for term in ("compare", "best", "review", "pricing", "guide", "alternatives")):
            score += 15
        if len(content.split()) >= 120:
            score += 10
        return min(100.0, max(0.0, score))

    def _score_duplicate_keyword_risk(self, topic: str, slug: str, content: str, existing_keywords: List[str]) -> float:
        if not topic:
            return 0.0
        normalized_topic = re.sub(r"[^a-z0-9]+", " ", topic.lower()).strip()
        normalized_slug = re.sub(r"[^a-z0-9]+", " ", slug.lower()).strip()
        if not existing_keywords:
            return 90.0
        for keyword in existing_keywords:
            normalized_keyword = re.sub(r"[^a-z0-9]+", " ", str(keyword).lower()).strip()
            if not normalized_keyword:
                continue
            if normalized_keyword == normalized_topic or normalized_topic in normalized_keyword or normalized_keyword in normalized_topic:
                continue
            if normalized_keyword in normalized_slug:
                return 50.0
        if normalized_topic in normalized_slug:
            return 90.0
        if len(content.split()) >= 120:
            return 90.0
        return 80.0

    def _score_duplicate_h1_title_risk(self, title: str, existing_titles: List[str], existing_h1s: List[str]) -> float:
        if not title:
            return 0.0
        normalized_title = re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()
        duplicate_titles = [
            item for item in existing_titles
            if re.sub(r"[^a-z0-9]+", " ", str(item).lower()).strip() == normalized_title
        ]
        duplicate_h1s = [
            item for item in existing_h1s
            if re.sub(r"[^a-z0-9]+", " ", str(item).lower()).strip() == normalized_title
        ]
        if duplicate_titles or duplicate_h1s:
            return 50.0
        return 90.0

    def _score_thin_content(self, content: str) -> float:
        tokens = [token for token in re.split(r"\s+", content.strip()) if token]
        word_count = len(tokens)
        structure_markers = sum(1 for marker in ("##", "###", "- ", "1.", "[", "]", "faq") if marker in content.lower())
        if word_count < 80:
            if structure_markers >= 3:
                return 80.0
            return 40.0
        if word_count < 180:
            if structure_markers >= 3:
                return 85.0
            return 70.0
        if word_count < 400:
            return 85.0
        return 95.0

    def _score_eeat_signals(self, content: str) -> float:
        score = 50.0
        if re.search(r"\b(experience|tested|personally|based on|reviewed|hands-on)\b", content, re.IGNORECASE):
            score += 20
        if re.search(r"\b(pricing|limitations|pros|cons|comparison|alternatives)\b", content, re.IGNORECASE):
            score += 15
        if re.search(r"\b(disclosure|affiliate disclosure|verified|official pricing)\b", content, re.IGNORECASE):
            score += 15
        return min(100.0, max(0.0, score))

    def _score_internal_links(self, internal_links: List[str]) -> float:
        if not internal_links:
            return 40.0
        if len(internal_links) < 2:
            return 70.0
        if len(internal_links) < 4:
            return 85.0
        return 95.0

    def _score_schema_hints(self, schema_hints: List[str]) -> float:
        if not schema_hints:
            return 50.0
        if len(schema_hints) < 2:
            return 70.0
        if len(schema_hints) < 4:
            return 85.0
        return 95.0

    def _score_affiliate_cta(self, content: str) -> float:
        lower = content.lower()
        if "affiliate disclosure" in lower or "disclosure" in lower:
            if any(term in lower for term in ("cta", "verify pricing", "compare alternatives", "read the full review")):
                return 90.0
            return 80.0
        return 40.0

    @staticmethod
    def _contains_buying_intent(text: str) -> bool:
        return any(term in text.lower() for term in ("best", "review", "compare", "pricing", "alternatives", "guide"))
