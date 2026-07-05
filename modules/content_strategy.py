from __future__ import annotations

from typing import Tuple

from modules.topic_scorer import TopicScore


class ContentStrategyEngine:
    _MIN_SCORE = 60
    _GOOD_SCORE = 70
    _STRONG_SCORE = 80
    _EXCELLENT_SCORE = 90

    def decide_content_type(self, score: TopicScore) -> Tuple[str, str]:
        total = score.total_score
        if total < self._MIN_SCORE or score.recommendation == "Skip":
            return self._ignore_result()

        if total >= self._EXCELLENT_SCORE:
            return self._excellent_result()

        if total >= self._STRONG_SCORE:
            return self._strong_result()

        if total >= self._GOOD_SCORE:
            return self._good_result()

        return self._manual_review_result()

    @staticmethod
    def _ignore_result() -> Tuple[str, str]:
        return "Ignore", "Topic score is below the daily planning threshold."

    @staticmethod
    def _excellent_result() -> Tuple[str, str]:
        return "Website + YouTube + Social", "Excellent buyer intent and cross-channel value."

    @staticmethod
    def _strong_result() -> Tuple[str, str]:
        return "Website + YouTube", "Strong topic for article and video planning."

    @staticmethod
    def _good_result() -> Tuple[str, str]:
        return "Website", "Good topic for website content."

    @staticmethod
    def _manual_review_result() -> Tuple[str, str]:
        return "Website Only (manual review)", "Watch-list topic that needs manual review before content generation."


# Use a monkeypatch-friendly helper that keeps the content strategy engine isolated.
def _patch_topic_feature_helpers() -> None:
    if not hasattr(TopicScore, "short_content_fit"):
        def short_content_fit(self: TopicScore) -> bool:
            return self.features.youtube_potential >= 60 and self.features.freshness >= 40 and self.features.social_share_potential >= 55

        setattr(TopicScore, "short_content_fit", short_content_fit)


_patch_topic_feature_helpers()
