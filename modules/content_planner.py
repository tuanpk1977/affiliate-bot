from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from modules.topic_scorer import TopicScore
from modules.topic_ranker import TopicRanker


@dataclass
class PlannerConfig:
    days: List[str] = (
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
    )
    max_articles_per_day: int = 1
    max_videos_per_day: int = 1
    max_social_posts_per_day: int = 2
    max_quora_answers_per_day: int = 1
    max_x_threads_per_day: int = 1


class DailyContentPlanner:
    def __init__(self, config: Optional[PlannerConfig] = None) -> None:
        self.config = config or PlannerConfig()
        self.ranker = TopicRanker()

    def build_plan(self, topics: List[TopicScore]) -> Dict[str, List[str]]:
        ranked = self.ranker.rank_topics([topic for topic in topics if topic.recommendation != "Skip"])
        plan: Dict[str, List[str]] = {}
        topic_index = 0
        for day in self.config.days:
            activities: List[str] = []
            article_slots = self.config.max_articles_per_day
            video_slots = self.config.max_videos_per_day
            social_slots = self.config.max_social_posts_per_day
            quora_slots = self.config.max_quora_answers_per_day
            x_slots = self.config.max_x_threads_per_day
            while topic_index < len(ranked) and (article_slots > 0 or video_slots > 0 or social_slots > 0):
                topic = ranked[topic_index]
                topic_index += 1
                if "Website" in (topic.content_decision or "") and article_slots > 0:
                    activities.append(f"Article: {topic.topic}")
                    article_slots -= 1
                if "YouTube" in (topic.content_decision or "") and video_slots > 0:
                    activities.append(f"Video: {topic.topic} ({topic.video_priority or 'Standard'})")
                    video_slots -= 1
                if topic.content_decision == "Social Only" and social_slots > 0:
                    activities.append(f"Social Draft: {topic.topic}")
                    social_slots -= 1
                if topic.content_decision == "Website + Shorts" and social_slots > 0:
                    activities.append(f"Short-form Video: {topic.topic}")
                    social_slots -= 1
                if quora_slots > 0:
                    activities.append(f"Quora Answer: {topic.topic}")
                    quora_slots -= 1
                if x_slots > 0:
                    activities.append(f"X Thread: {topic.topic}")
                    x_slots -= 1
            plan[day] = activities
        return plan

    def summarize_plan(self, plan: Dict[str, List[str]]) -> List[Dict[str, object]]:
        return [{"day": day, "tasks": tasks} for day, tasks in plan.items()]
