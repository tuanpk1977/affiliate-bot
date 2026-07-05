from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class WorkerBotConfig:
    topics_per_day: int
    minimum_score: float
    maximum_similarity: float
    output_folder: Path
    video_duration_seconds: int
    language: str
    voice: str
    image_source: str
    master_dashboard_path: Path
    topic_scores_path: Path
    topic_dashboard_path: Path
    trending_topics_path: Path
    topic_history_path: Path
    existing_article_roots: tuple[Path, ...]
    existing_video_root: Path
    cache_file: Path
    ffmpeg_config: Path
    reuse_unchanged_content: bool


def _path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def load_config(path: str | Path = ROOT / "config" / "content_assistant_bot.json") -> WorkerBotConfig:
    config_path = _path(str(path))
    payload: dict[str, Any] = json.loads(config_path.read_text(encoding="utf-8"))
    return WorkerBotConfig(
        topics_per_day=int(payload.get("topics_per_day", 10)),
        minimum_score=float(payload.get("minimum_score", 45)),
        maximum_similarity=float(payload.get("maximum_similarity", 0.82)),
        output_folder=_path(payload.get("output_folder", "draft-output")),
        video_duration_seconds=int(payload.get("video_duration_seconds", 45)),
        language=str(payload.get("language", "en")),
        voice=str(payload.get("voice", "en-US-GuyNeural")),
        image_source=str(payload.get("image_source", "prompt_only")),
        master_dashboard_path=_path(payload.get("master_dashboard_path", "data/master_dashboard.xlsx")),
        topic_scores_path=_path(payload.get("topic_scores_path", "data/topic_scores.json")),
        topic_dashboard_path=_path(payload.get("topic_dashboard_path", "data/topic_dashboard.json")),
        trending_topics_path=_path(payload.get("trending_topics_path", "data/trending_topics.json")),
        topic_history_path=_path(payload.get("topic_history_path", "data/hottrend_topic_history.csv")),
        existing_article_roots=tuple(_path(item) for item in payload.get("existing_article_roots", [])),
        existing_video_root=_path(payload.get("existing_video_root", "video_output")),
        cache_file=_path(payload.get("cache_file", "data/content_assistant_bot_cache.json")),
        ffmpeg_config=_path(payload.get("ffmpeg_config", "config/video_render.json")),
        reuse_unchanged_content=bool(payload.get("reuse_unchanged_content", True)),
    )
