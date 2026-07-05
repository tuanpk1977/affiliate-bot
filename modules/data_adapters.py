from __future__ import annotations

from typing import Any, Dict, Protocol


class TrendDataAdapter(Protocol):
    def fetch_trend_signals(self, topic: str) -> Dict[str, Any]:
        """Fetch trend signals for a topic from an external source."""
        ...


class SearchIntentAdapter(Protocol):
    def fetch_search_intent(self, topic: str) -> Dict[str, Any]:
        """Fetch search intent data for a topic."""
        ...


class KeywordPlannerAdapter(Protocol):
    def fetch_keyword_metrics(self, topic: str) -> Dict[str, Any]:
        """Fetch CPC and search volume metrics for a topic."""
        ...


class SocialDataAdapter(Protocol):
    def fetch_social_signals(self, topic: str) -> Dict[str, Any]:
        """Fetch social network engagement data for a topic."""
        ...


class VideoDataAdapter(Protocol):
    def fetch_video_signals(self, topic: str) -> Dict[str, Any]:
        """Fetch video discovery and potential metrics for a topic."""
        ...
