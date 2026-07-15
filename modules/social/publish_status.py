from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from .utils import PLATFORMS, STATUS_PATH, PublishedArticle, now_iso


FIELDNAMES = [
    "article_id",
    "url",
    "title",
    "website",
    *PLATFORMS,
    "last_publish_time",
    "last_error",
]


class SocialPublishStatusStore:
    def __init__(self, path: Path = STATUS_PATH) -> None:
        self.path = path

    def load(self) -> list[dict[str, str]]:
        if not self.path.exists():
            return []
        with self.path.open("r", encoding="utf-8-sig", newline="") as handle:
            return list(csv.DictReader(handle))

    def save(self, rows: list[dict[str, str]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=FIELDNAMES, extrasaction="ignore")
            writer.writeheader()
            for row in rows:
                writer.writerow({field: row.get(field, "") for field in FIELDNAMES})

    def ensure_article(self, article: PublishedArticle) -> dict[str, str]:
        rows = self.load()
        for row in rows:
            if row.get("article_id") == article.article_id or row.get("url") == article.url:
                changed = False
                for field, value in {
                    "article_id": article.article_id,
                    "url": article.url,
                    "title": article.title,
                    "website": "TRUE",
                }.items():
                    if row.get(field) != value:
                        row[field] = value
                        changed = True
                if changed:
                    self.save(rows)
                return row
        row = {
            "article_id": article.article_id,
            "url": article.url,
            "title": article.title,
            "website": "TRUE",
            **{platform: "FALSE" for platform in PLATFORMS},
            "last_publish_time": "",
            "last_error": "",
        }
        rows.append(row)
        self.save(rows)
        return row

    def mark_result(self, article: PublishedArticle, platform: str, *, success: bool, error: str = "") -> None:
        rows = self.load()
        for row in rows:
            if row.get("article_id") == article.article_id or row.get("url") == article.url:
                row[platform] = "TRUE" if success else row.get(platform, "FALSE") or "FALSE"
                row["last_publish_time"] = now_iso()
                row["last_error"] = error
                self.save(rows)
                return
        self.ensure_article(article)
        self.mark_result(article, platform, success=success, error=error)

    def unpublished_platforms(self, article: PublishedArticle, enabled_platforms: list[str]) -> list[str]:
        row = self.ensure_article(article)
        return [platform for platform in enabled_platforms if str(row.get(platform) or "FALSE").upper() != "TRUE"]

    def summary(self, article: PublishedArticle) -> dict[str, Any]:
        row = self.ensure_article(article)
        unpublished = [platform for platform in PLATFORMS if str(row.get(platform) or "FALSE").upper() != "TRUE"]
        return {"row": row, "unpublished": unpublished, "unpublished_count": len(unpublished)}

