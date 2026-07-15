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
    *[f"{platform}_status" for platform in PLATFORMS],
    "last_publish_time",
    "last_platform",
    "last_status",
    "published_url",
    "retry_count",
    "notes",
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
            **{f"{platform}_status": "READY" for platform in PLATFORMS},
            "last_publish_time": "",
            "last_platform": "",
            "last_status": "READY",
            "published_url": "",
            "retry_count": "0",
            "notes": "",
            "last_error": "",
        }
        rows.append(row)
        self.save(rows)
        return row

    def _increment_retry_count(self, row: dict[str, str]) -> None:
        try:
            count = int(row.get("retry_count") or "0")
        except ValueError:
            count = 0
        row["retry_count"] = str(count + 1)

    def mark_status(
        self,
        article: PublishedArticle,
        platform: str,
        status: str,
        *,
        published_url: str = "",
        notes: str = "",
        error: str = "",
    ) -> None:
        rows = self.load()
        for row in rows:
            if row.get("article_id") == article.article_id or row.get("url") == article.url:
                row.setdefault(f"{platform}_status", "READY")
                row[f"{platform}_status"] = status
                row["last_publish_time"] = now_iso()
                row["last_platform"] = platform
                row["last_status"] = status
                row["published_url"] = published_url or row.get("published_url", "")
                row["notes"] = notes
                row["last_error"] = error
                if status in {"PENDING", "FAILED"}:
                    self._increment_retry_count(row)
                if status == "PUBLISHED_MANUAL":
                    row[platform] = "TRUE"
                self.save(rows)
                return
        self.ensure_article(article)
        self.mark_status(article, platform, status, published_url=published_url, notes=notes, error=error)

    def mark_previewed(self, article: PublishedArticle, platform: str) -> None:
        self.mark_status(article, platform, "PREVIEWED")

    def mark_pending(self, article: PublishedArticle, platform: str, *, error: str = "") -> None:
        self.mark_status(article, platform, "PENDING", error=error)

    def mark_manual_published(self, article: PublishedArticle, platform: str, *, published_url: str = "", notes: str = "") -> None:
        self.mark_status(article, platform, "PUBLISHED_MANUAL", published_url=published_url, notes=notes)

    def mark_failed(self, article: PublishedArticle, platform: str, *, error: str = "", notes: str = "") -> None:
        self.mark_status(article, platform, "FAILED", error=error, notes=notes)

    def mark_result(self, article: PublishedArticle, platform: str, *, success: bool, error: str = "") -> None:
        if success:
            self.mark_manual_published(article, platform)
        else:
            self.mark_failed(article, platform, error=error)

    def unpublished_platforms(self, article: PublishedArticle, enabled_platforms: list[str]) -> list[str]:
        row = self.ensure_article(article)
        return [platform for platform in enabled_platforms if str(row.get(platform) or "FALSE").upper() != "TRUE"]

    def summary(self, article: PublishedArticle) -> dict[str, Any]:
        row = self.ensure_article(article)
        unpublished = [platform for platform in PLATFORMS if str(row.get(platform) or "FALSE").upper() != "TRUE"]
        return {"row": row, "unpublished": unpublished, "unpublished_count": len(unpublished)}
