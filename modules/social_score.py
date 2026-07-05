from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class SocialScore:
    topic: str
    facebook: int = 0
    linkedin: int = 0
    reddit: int = 0
    quora: int = 0
    x: int = 0
    hashnode: int = 0
    devto: int = 0
    medium: int = 0
    factors: List[str] = field(default_factory=list)

    def normalize(self, value: int) -> int:
        return max(0, min(100, int(value)))

    def as_dict(self) -> Dict[str, int]:
        return {
            "facebook": self.normalize(self.facebook),
            "linkedin": self.normalize(self.linkedin),
            "reddit": self.normalize(self.reddit),
            "quora": self.normalize(self.quora),
            "x": self.normalize(self.x),
            "hashnode": self.normalize(self.hashnode),
            "devto": self.normalize(self.devto),
            "medium": self.normalize(self.medium),
        }


class SocialValueEstimator:
    def estimate(self, topic: str, context: Dict[str, int]) -> SocialScore:
        score = SocialScore(topic=topic)
        score.facebook = self._scale(context.get("social_share_potential", 0) + context.get("freshness", 0) * 0.4)
        score.linkedin = self._scale(context.get("business_relevance", 0) + context.get("brand_fit", 0) * 0.5)
        score.reddit = self._scale(context.get("reddit_discussion_potential", 0) + context.get("trend_score", 0) * 0.3)
        score.quora = self._scale(context.get("quora_potential", 0) + context.get("search_intent", 0) * 0.25)
        score.x = self._scale(context.get("social_share_potential", 0) + context.get("trend_score", 0) * 0.2)
        score.hashnode = self._scale(context.get("evergreen_potential", 0) + context.get("seo_opportunity", 0) * 0.3)
        score.devto = self._scale(context.get("technology_relevance", 0) + context.get("seo_opportunity", 0) * 0.25)
        score.medium = self._scale(context.get("social_share_potential", 0) + context.get("brand_fit", 0) * 0.2)
        score.factors = [k for k, v in score.as_dict().items() if v >= 70]
        return score

    @staticmethod
    def _scale(value: float) -> int:
        return max(0, min(100, int(round(value))))
