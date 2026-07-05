from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol


BUYER_INTENT_TERMS = (
    "review",
    "comparison",
    "best",
    "alternatives",
    "alternative",
    "pricing",
    " vs ",
    "discount",
    "coupon",
    "lifetime deal",
    "promo",
    "features",
    "pros and cons",
    "tutorial",
    "guide",
    "how to",
    "top tools",
)

NEWS_PENALTY_TERMS = (
    "breaking news",
    "funding",
    "launch",
    "launched",
    "announced",
    "announces",
    "unveils",
    "warns",
    "show hn",
    "today",
    "yesterday",
    "aws says",
    "anthropic says",
    "openai says",
    "stock movement",
    "stock",
    "stocks",
    "rallying",
    "buy now",
    "at risk",
    "press release",
)


class TrendDataAdapter(Protocol):
    def fetch_trend_signals(self, topic: str) -> Dict[str, Any]:
        ...


class SearchIntentAdapter(Protocol):
    def fetch_search_intent(self, topic: str) -> Dict[str, Any]:
        ...


class KeywordPlannerAdapter(Protocol):
    def fetch_keyword_metrics(self, topic: str) -> Dict[str, Any]:
        ...


@dataclass
class TopicFeatureSet:
    topic: str
    trend_score: int = 0
    search_intent: int = 0
    seo_opportunity: int = 0
    competition_level: int = 0
    affiliate_value: int = 0
    buyer_intent: int = 0
    cpc_potential: int = 0
    evergreen_potential: int = 0
    freshness: int = 0
    social_share_potential: int = 0
    reddit_discussion_potential: int = 0
    quora_potential: int = 0
    linkedin_potential: int = 0
    youtube_potential: int = 0
    internal_linking_opportunity: int = 0
    brand_fit: int = 0
    difficulty: int = 0
    estimated_traffic: int = 0
    estimated_conversion: int = 0
    tags: List[str] = field(default_factory=list)
    source: str = ""

    def normalized(self, value: int) -> int:
        return max(0, min(100, int(value)))

    def short_content_fit(self) -> bool:
        return self.youtube_potential >= 60 and self.freshness >= 40 and self.social_share_potential >= 55

    def as_dict(self) -> Dict[str, Any]:
        return {
            "topic": self.topic,
            "trend_score": self.normalized(self.trend_score),
            "search_intent": self.normalized(self.search_intent),
            "seo_opportunity": self.normalized(self.seo_opportunity),
            "competition_level": self.normalized(self.competition_level),
            "affiliate_value": self.normalized(self.affiliate_value),
            "buyer_intent": self.normalized(self.buyer_intent),
            "cpc_potential": self.normalized(self.cpc_potential),
            "evergreen_potential": self.normalized(self.evergreen_potential),
            "freshness": self.normalized(self.freshness),
            "social_share_potential": self.normalized(self.social_share_potential),
            "reddit_discussion_potential": self.normalized(self.reddit_discussion_potential),
            "quora_potential": self.normalized(self.quora_potential),
            "linkedin_potential": self.normalized(self.linkedin_potential),
            "youtube_potential": self.normalized(self.youtube_potential),
            "internal_linking_opportunity": self.normalized(self.internal_linking_opportunity),
            "brand_fit": self.normalized(self.brand_fit),
            "difficulty": self.normalized(self.difficulty),
            "estimated_traffic": self.normalized(self.estimated_traffic),
            "estimated_conversion": self.normalized(self.estimated_conversion),
            "tags": self.tags,
            "source": self.source,
        }


@dataclass
class TopicScore:
    topic: str
    features: TopicFeatureSet
    total_score: float
    traffic_score: float
    revenue_score: float
    seo_score: float
    competition: int
    recommendation: str
    reason: str
    content_decision: Optional[str] = None
    social_scores: Dict[str, int] = field(default_factory=dict)
    video_priority: Optional[str] = None

    @staticmethod
    def score_grade_for(total_score: float) -> str:
        if total_score >= 90:
            return "Excellent"
        if total_score >= 80:
            return "Strong"
        if total_score >= 70:
            return "Good"
        if total_score >= 60:
            return "Watch"
        return "Skip"

    def as_dict(self) -> Dict[str, Any]:
        return {
            "topic": self.topic,
            "total_score": round(self.total_score, 1),
            "score_grade": self.score_grade_for(self.total_score),
            "traffic_score": round(self.traffic_score, 1),
            "revenue_score": round(self.revenue_score, 1),
            "seo_score": round(self.seo_score, 1),
            "competition": self.competition,
            "recommendation": self.recommendation,
            "content_decision": self.content_decision,
            "video_priority": self.video_priority,
            "social_scores": self.social_scores,
            "reason": self.reason,
            **self.features.as_dict(),
        }


class TopicScorer:
    def __init__(self, rules_path: Optional[str] = None) -> None:
        self.rules = self.load_rules(rules_path)

    @staticmethod
    def load_rules(rules_path: Optional[str] = None) -> Dict[str, Any]:
        if rules_path:
            path = Path(rules_path)
        else:
            path = Path(__file__).resolve().parents[1] / "data" / "topic_scoring_rules.json"
        if not path.exists():
            return {}
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    @staticmethod
    def normalize(value: int) -> int:
        return max(0, min(100, int(value)))

    def weighted_score(self, features: TopicFeatureSet, category: str) -> float:
        category_weights = self.rules.get("category_weights", {}).get(category, {})
        if not category_weights:
            return 0.0
        score = 0.0
        weight_sum = 0.0
        for field_name, weight in category_weights.items():
            value = getattr(features, field_name, 0)
            score += self.normalize(value) * float(weight)
            weight_sum += float(weight)
        return round(score / max(weight_sum, 1.0), 1)

    def video_score(self, features: TopicFeatureSet) -> float:
        return round(
            features.youtube_potential * 0.55
            + features.search_intent * 0.2
            + features.freshness * 0.15
            + features.social_share_potential * 0.1,
            1,
        )

    def social_score(self, features: TopicFeatureSet) -> float:
        return round(
            features.social_share_potential * 0.45
            + features.reddit_discussion_potential * 0.2
            + features.linkedin_potential * 0.2
            + features.quora_potential * 0.15,
            1,
        )

    @staticmethod
    def commercial_topic_bonus(features: TopicFeatureSet, traffic_score: float, revenue_score: float, seo_score: float) -> float:
        topic = features.topic.lower()
        tags = " ".join(features.tags).lower()
        haystack = f"{topic} {tags}"
        bonus = 0.0
        buyer_hits = sum(1 for term in BUYER_INTENT_TERMS if term in haystack)
        if buyer_hits and (features.affiliate_value >= 45 or features.buyer_intent >= 50):
            bonus += min(14.0, 6.0 + buyer_hits * 2.0)
        if any(term in haystack for term in ("comparison", " vs ", "alternatives", "software comparison")) and revenue_score >= 45 and seo_score >= 35:
            bonus += 9.0
        if any(term in haystack for term in ("review", "pricing", "best", "top tools", "features", "pros and cons")) and features.buyer_intent >= 55:
            bonus += 5.0
        if any(term in haystack for term in ("ai", "seo", "video", "image", "writing", "automation", "coding")) and features.brand_fit >= 65:
            bonus += 3.0
        if any(term in haystack for term in ("saas", "software", "platform", "tool", "tools")) and features.estimated_conversion >= 50:
            bonus += 3.0
        if traffic_score >= 55 and revenue_score >= 55:
            bonus += 3.0
        if features.difficulty >= 85 and seo_score < 55:
            bonus -= 4.0
        if any(term in haystack for term in NEWS_PENALTY_TERMS):
            bonus -= 30.0
        return bonus

    def calculate_total(self, features: TopicFeatureSet) -> float:
        traffic_score = self.weighted_score(features, "traffic")
        revenue_score = self.weighted_score(features, "revenue")
        seo_score = self.weighted_score(features, "seo")
        video_score = self.video_score(features)
        social_score = self.social_score(features)
        weights = self.rules.get("final_score_weights", {})
        if not weights:
            weights = {
                "seo": 0.25,
                "traffic": 0.20,
                "revenue": 0.25,
                "video": 0.15,
                "social": 0.10,
                "freshness": 0.05,
            }
        base_total = (
            seo_score * float(weights.get("seo", 0))
            + traffic_score * float(weights.get("traffic", 0))
            + revenue_score * float(weights.get("revenue", 0))
            + video_score * float(weights.get("video", 0))
            + social_score * float(weights.get("social", 0))
            + self.normalize(features.freshness) * float(weights.get("freshness", 0))
        )
        bonus = self.commercial_topic_bonus(features, traffic_score, revenue_score, seo_score)
        boosted = base_total + bonus
        if boosted >= 60:
            boosted = 60 + (boosted - 60) * 1.25
        return round(max(0.0, min(100.0, boosted)), 1)

    def classify_recommendation(self, total_score: float, features: TopicFeatureSet) -> str:
        thresholds = self.rules.get("recommendation_thresholds", {})
        if total_score >= thresholds.get("high_priority", 85):
            return "Excellent"
        if total_score >= thresholds.get("strong_candidate", 70):
            return "Strong"
        if total_score >= thresholds.get("opportunity", 50):
            return "Good"
        if total_score >= thresholds.get("watch", 35):
            return "Watch"
        return "Skip"

    def build_reason(self, total_score: float, features: TopicFeatureSet, traffic_score: float, revenue_score: float, seo_score: float) -> str:
        reasons: List[str] = []
        if features.trend_score >= 70:
            reasons.append("Strong trend signal")
        if features.buyer_intent >= 65:
            reasons.append("High buyer intent")
        if features.affiliate_value >= 60:
            reasons.append("Solid affiliate value")
        if features.youtube_potential >= 70:
            reasons.append("Video-friendly topic")
        if features.social_share_potential >= 70:
            reasons.append("High social share potential")
        if features.competition_level >= 70:
            reasons.append("Competitive landscape")
        if features.seo_opportunity >= 70:
            reasons.append("Strong SEO opportunity")
        if features.difficulty >= 70:
            reasons.append("Higher difficulty")
        if traffic_score < 40:
            reasons.append("Traffic opportunity is limited")
        if revenue_score < 40:
            reasons.append("Conversion or revenue potential is low")
        if seo_score < 40:
            reasons.append("SEO potential is weak")
        if not reasons:
            reasons.append("Balanced topic opportunity")
        return ", ".join(reasons)

    def score_topic(self, features: TopicFeatureSet) -> TopicScore:
        traffic_score = self.weighted_score(features, "traffic")
        revenue_score = self.weighted_score(features, "revenue")
        seo_score = self.weighted_score(features, "seo")
        total_score = self.calculate_total(features)
        recommendation = self.classify_recommendation(total_score, features)
        reason = self.build_reason(total_score, features, traffic_score, revenue_score, seo_score)
        return TopicScore(
            topic=features.topic,
            features=features,
            total_score=total_score,
            traffic_score=traffic_score,
            revenue_score=revenue_score,
            seo_score=seo_score,
            competition=self.normalize(features.competition_level),
            recommendation=recommendation,
            reason=reason,
        )

    def score_topics(self, features_list: List[TopicFeatureSet]) -> List[TopicScore]:
        return [self.score_topic(features) for features in features_list]
