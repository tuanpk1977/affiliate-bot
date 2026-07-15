from __future__ import annotations

import argparse
import time
from pathlib import Path
from typing import Any

from .base_publisher import BasePublisher, PublishResult
from .bluesky import BlueskyPublisher
from .blogger import BloggerPublisher
from .devto import DevtoPublisher
from .facebook import FacebookPublisher
from .hashnode import HashnodePublisher
from .history import SocialPublishHistory
from .linkedin import LinkedInPublisher
from .medium import MediumPublisher
from .pinterest import PinterestPublisher
from .publish_status import SocialPublishStatusStore
from .telegram import TelegramPublisher
from .threads import ThreadsPublisher
from .twitter_x import TwitterXPublisher
from .utils import (
    CONFIG_PATH,
    DATA_DIR,
    PLATFORMS,
    ROOT,
    PublishedArticle,
    ensure_default_config,
    extract_meta,
    extract_tags,
    extract_title,
    load_simple_yaml,
    read_json,
    slug_from_url,
)


PUBLISHER_CLASSES: dict[str, type[BasePublisher]] = {
    "pinterest": PinterestPublisher,
    "facebook": FacebookPublisher,
    "linkedin": LinkedInPublisher,
    "twitter": TwitterXPublisher,
    "bluesky": BlueskyPublisher,
    "threads": ThreadsPublisher,
    "devto": DevtoPublisher,
    "medium": MediumPublisher,
    "hashnode": HashnodePublisher,
    "blogger": BloggerPublisher,
    "telegram": TelegramPublisher,
}


class SocialPublisherManager:
    def __init__(self, *, root: Path = ROOT, config_path: Path = CONFIG_PATH) -> None:
        self.root = root
        ensure_default_config(config_path)
        self.config = load_simple_yaml(config_path)
        self.status = SocialPublishStatusStore(root / "data" / "social_publish_status.csv")
        self.history = SocialPublishHistory(root / "logs" / "social")
        self.publishers = self._build_publishers()

    def _build_publishers(self) -> dict[str, BasePublisher]:
        platforms = self.config.get("platforms", {}) if isinstance(self.config.get("platforms"), dict) else {}
        result: dict[str, BasePublisher] = {}
        for platform, cls in PUBLISHER_CLASSES.items():
            platform_config = self.config.get(platform, {}) if isinstance(self.config.get(platform), dict) else {}
            config = {"enabled": bool(platforms.get(platform, False)), **platform_config}
            result[platform] = cls(config)
        return result

    def enabled_platforms(self) -> list[str]:
        return [platform for platform in PLATFORMS if self.publishers[platform].enabled()]

    def latest_article(self) -> PublishedArticle:
        rows = read_json(self.root / "data" / "publish_queue.json", [])
        if not isinstance(rows, list):
            rows = []
        candidates = [
            row for row in rows
            if str(row.get("url") or "").startswith("https://")
            and (
                str(row.get("status") or "").lower() in {"live", "published"}
                or bool(row.get("live"))
            )
        ]
        if not candidates:
            raise RuntimeError("No published website article found. Publish an article before social publishing.")
        candidates.sort(key=lambda row: str(row.get("live_at") or row.get("pushed_at") or row.get("updated_at") or ""), reverse=True)
        row = candidates[0]
        url = str(row.get("url") or "")
        slug = str(row.get("slug") or slug_from_url(url))
        html_path = self.root / "docs" / slug / "index.html"
        html = html_path.read_text(encoding="utf-8", errors="ignore") if html_path.exists() else ""
        title = extract_title(html) or str(row.get("title") or slug.replace("-", " ").title())
        description = extract_meta(html, "description") or extract_meta(html, "og:description")
        image = extract_meta(html, "og:image") or extract_meta(html, "twitter:image")
        if image.startswith("/"):
            image = "https://smileaireviewhub.com" + image
        return PublishedArticle(
            article_id=slug,
            title=title,
            url=url,
            description=description,
            image=image,
            tags=extract_tags(title, description),
            publish_date=str(row.get("live_at") or row.get("pushed_at") or row.get("updated_at") or ""),
        )

    def website_status(self) -> dict[str, Any]:
        article = self.latest_article()
        summary = self.status.summary(article)
        return {
            "latest_article": article,
            "unpublished_social_posts": summary["unpublished_count"],
            "enabled_platforms": self.enabled_platforms(),
        }

    def preview(self, platform: str = "pinterest") -> dict[str, Any]:
        article = self.latest_article()
        self.status.ensure_article(article)
        publisher = self.publishers[platform]
        return publisher.preview(article)

    def publish_platform(self, platform: str) -> PublishResult:
        article = self.latest_article()
        self.status.ensure_article(article)
        if platform not in self.enabled_platforms():
            return PublishResult(platform=platform, status="disabled", url=article.url, error="platform disabled in config/social_publish.yaml")
        if platform not in self.status.unpublished_platforms(article, [platform]):
            return PublishResult(platform=platform, status="skipped_already_published", url=article.url, success=True)
        start = time.monotonic()
        result = self.publishers[platform].publish(article)
        result.duration_seconds = round(time.monotonic() - start, 3)
        self.status.mark_result(article, platform, success=result.success, error=result.error)
        self.history.write(article, result)
        return result

    def publish_all(self, *, only_unpublished: bool = True) -> list[PublishResult]:
        article = self.latest_article()
        enabled = self.enabled_platforms()
        platforms = self.status.unpublished_platforms(article, enabled) if only_unpublished else enabled
        return [self.publish_platform(platform) for platform in platforms]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Social publisher for already-live Smile AI Review Hub articles.")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status")
    preview = sub.add_parser("preview")
    preview.add_argument("--platform", default="pinterest", choices=PLATFORMS)
    publish = sub.add_parser("publish")
    publish.add_argument("--platform", required=True, choices=PLATFORMS)
    sub.add_parser("publish-all")
    sub.add_parser("publish-unpublished")
    history = sub.add_parser("history")
    history.add_argument("--limit", type=int, default=20)
    return parser


def main(argv: list[str] | None = None) -> int:
    from .preview import format_preview

    args = build_parser().parse_args(argv)
    manager = SocialPublisherManager()
    if args.command == "status":
        status = manager.website_status()
        article = status["latest_article"]
        print(f"Website status: LIVE")
        print(f"Latest published article: {article.title}")
        print(f"URL: {article.url}")
        print(f"Unpublished social posts: {status['unpublished_social_posts']}")
        print(f"Enabled platforms: {', '.join(status['enabled_platforms']) or 'none'}")
        return 0
    if args.command == "preview":
        print(format_preview(manager.preview(args.platform)))
        return 0
    if args.command == "publish":
        result = manager.publish_platform(args.platform)
        print(f"{result.platform}: {result.status}")
        if result.error:
            print(f"error: {result.error}")
        return 0 if result.success or result.status.startswith("prepared") or result.status.startswith("skipped") else 1
    if args.command == "publish-all":
        for result in manager.publish_all(only_unpublished=False):
            print(f"{result.platform}: {result.status}")
        return 0
    if args.command == "publish-unpublished":
        for result in manager.publish_all(only_unpublished=True):
            print(f"{result.platform}: {result.status}")
        return 0
    if args.command == "history":
        for path in manager.history.latest(args.limit):
            print(path)
        return 0
    return 1
