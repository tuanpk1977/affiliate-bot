from __future__ import annotations

from typing import Dict, Optional

from modules.topic_scorer import TopicScore


class VideoPriorityEngine:
    def prioritize(self, score: TopicScore) -> str:
        features = score.features
        if score.recommendation == "Skip" or score.total_score < 40:
            return "No video"

        if features.youtube_potential >= 80 and features.difficulty <= 60 and features.buyer_intent >= 50:
            return "Long review"

        if features.youtube_potential >= 75 and features.search_intent >= 55 and features.affiliate_value >= 50:
            return "Comparison"

        if features.youtube_potential >= 65 and features.social_share_potential >= 70:
            return "Tutorial"

        if features.youtube_potential >= 60 and features.freshness >= 60:
            return "Demo"

        if features.youtube_potential >= 55 and features.social_share_potential >= 65:
            return "Short"

        return "No video"

    def should_create_video(self, score: TopicScore) -> bool:
        return self.prioritize(score) not in ("No video",)
