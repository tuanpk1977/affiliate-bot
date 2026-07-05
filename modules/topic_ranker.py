from __future__ import annotations

from typing import Dict, List

from modules.topic_scorer import TopicScore


class TopicRanker:
    def rank_topics(self, topics: List[TopicScore]) -> List[TopicScore]:
        return sorted(topics, key=lambda topic: topic.total_score, reverse=True)

    def top_groups(self, topics: List[TopicScore]) -> Dict[str, List[TopicScore]]:
        ranked = self.rank_topics(topics)
        return {
            "top_10": ranked[:10],
            "top_20": ranked[:20],
            "top_50": ranked[:50],
        }

    def dashboard_summary(self, topics: List[TopicScore]) -> Dict[str, List[Dict[str, object]]]:
        ranked = self.rank_topics(topics)
        top_revenue = sorted(topics, key=lambda topic: topic.revenue_score, reverse=True)[:10]
        top_seo = sorted(topics, key=lambda topic: topic.seo_score, reverse=True)[:10]
        top_social = sorted(topics, key=lambda topic: max(topic.social_scores.values()) if topic.social_scores else 0, reverse=True)[:10]
        return {
            "today_best_topics": [topic.as_dict() for topic in ranked[:10]],
            "top_revenue_topics": [topic.as_dict() for topic in top_revenue],
            "highest_seo_score": [topic.as_dict() for topic in top_seo],
            "highest_social_score": [topic.as_dict() for topic in top_social],
            "video_candidates": [topic.as_dict() for topic in topics if topic.video_priority and topic.video_priority != "No video"][0:10],
            "skipped_topics": [topic.as_dict() for topic in topics if topic.recommendation == "Skip"],
        }
