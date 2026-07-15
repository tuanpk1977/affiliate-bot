from __future__ import annotations

import json
from pathlib import Path

from .base_publisher import PublishResult
from .utils import LOG_DIR, PublishedArticle, now_iso


class SocialPublishHistory:
    def __init__(self, log_dir: Path = LOG_DIR) -> None:
        self.log_dir = log_dir

    def write(self, article: PublishedArticle, result: PublishResult) -> Path:
        self.log_dir.mkdir(parents=True, exist_ok=True)
        stamp = now_iso().replace(":", "").replace("+", "Z")
        path = self.log_dir / f"{stamp}-{result.platform}-{article.article_id}.json"
        payload = {
            "platform": result.platform,
            "time": now_iso(),
            "status": result.status,
            "url": article.url,
            "duration": result.duration_seconds,
            "error": result.error,
            "success": result.success,
            "metadata": result.metadata,
        }
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return path

    def latest(self, limit: int = 20) -> list[Path]:
        if not self.log_dir.exists():
            return []
        return sorted(self.log_dir.glob("*.json"), reverse=True)[:limit]

