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
from .manual_actions import copy_or_write, open_platform_target
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
    extract_affiliate_disclosure,
    extract_article_summary,
    extract_canonical,
    extract_headings,
    extract_paragraphs,
    extract_publish_date,
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

    def _row_has_live_confirmation(self, row: dict[str, Any]) -> bool:
        live_fields = [
            row.get("live_http_status"),
            row.get("http_status"),
            row.get("live_status"),
            row.get("display_status"),
        ]
        present = [str(value).lower() for value in live_fields if value not in (None, "")]
        if present:
            return any(value == "200" or "live 200" in value for value in present)
        return str(row.get("status") or "").lower() in {"live", "published"} or bool(row.get("live"))

    def live_article_rows(self) -> list[dict[str, Any]]:
        rows = read_json(self.root / "data" / "publish_queue.json", [])
        if not isinstance(rows, list):
            rows = []
        candidates: list[dict[str, Any]] = [
            row for row in rows
            if str(row.get("url") or "").startswith("https://")
            and self._row_has_live_confirmation(row)
        ]
        candidates.sort(key=lambda row: str(row.get("live_at") or row.get("pushed_at") or row.get("updated_at") or ""), reverse=True)
        return candidates

    def article_from_row(self, row: dict[str, Any]) -> PublishedArticle:
        url = str(row.get("url") or "")
        slug = str(row.get("slug") or slug_from_url(url))
        html_path = self.root / "docs" / slug / "index.html"
        html = html_path.read_text(encoding="utf-8", errors="ignore") if html_path.exists() else ""
        og_title = extract_meta(html, "og:title")
        og_description = extract_meta(html, "og:description")
        og_image = extract_meta(html, "og:image") or extract_meta(html, "twitter:image")
        title = og_title or extract_title(html) or str(row.get("title") or slug.replace("-", " ").title())
        description = extract_meta(html, "description") or og_description or str(row.get("description") or "")
        canonical = extract_canonical(html) or url
        image = og_image
        if image.startswith("/"):
            image = "https://smileaireviewhub.com" + image
        headings = extract_headings(html)
        paragraphs = extract_paragraphs(html, limit=6)
        return PublishedArticle(
            article_id=slug,
            title=title,
            url=url,
            description=description,
            image=image,
            tags=extract_tags(title, description),
            publish_date=extract_publish_date(html) or str(row.get("live_at") or row.get("pushed_at") or row.get("updated_at") or ""),
            canonical_url=canonical,
            og_title=og_title,
            og_description=og_description,
            og_image=image,
            summary=extract_article_summary(html, description),
            headings=headings,
            key_points=headings[:5] or paragraphs[:5],
            affiliate_disclosure=extract_affiliate_disclosure(html),
        )

    def latest_article(self) -> PublishedArticle:
        candidates = self.live_article_rows()
        if not candidates:
            raise RuntimeError("No published website article found. Publish an article before social publishing.")
        return self.article_from_row(candidates[0])

    def list_articles(self, limit: int = 25) -> list[dict[str, Any]]:
        items = []
        for index, row in enumerate(self.live_article_rows()[:limit], start=1):
            article = self.article_from_row(row)
            summary = self.status.summary(article)
            published_platforms = [platform for platform in PLATFORMS if str(summary["row"].get(platform) or "FALSE").upper() == "TRUE"]
            remaining_platforms = [platform for platform in PLATFORMS if platform not in published_platforms]
            items.append(
                {
                    "index": index,
                    "article": article,
                    "website": "LIVE",
                    "published_social": len(published_platforms),
                    "total_social": len(PLATFORMS),
                    "published_platforms": published_platforms,
                    "remaining_platforms": remaining_platforms,
                    "row": summary["row"],
                }
            )
        return items

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
        payload = publisher.preview(article)
        self.status.mark_previewed(article, platform)
        return payload

    def preview_platform(self, platform: str, *, article: PublishedArticle | None = None) -> dict[str, Any]:
        article = article or self.latest_article()
        self.status.ensure_article(article)
        payload = self.publishers[platform].preview(article)
        self.status.mark_previewed(article, platform)
        return payload

    def prepare_platform(self, platform: str, *, article: PublishedArticle | None = None) -> PublishResult:
        article = article or self.latest_article()
        self.status.ensure_article(article)
        if platform not in self.enabled_platforms():
            return PublishResult(platform=platform, status="disabled", url=article.url, error="platform disabled in config/social_publish.yaml")
        if platform not in self.status.unpublished_platforms(article, [platform]):
            return PublishResult(platform=platform, status="skipped_already_published", url=article.url, success=True)
        start = time.monotonic()
        result = self.publishers[platform].publish(article)
        result.duration_seconds = round(time.monotonic() - start, 3)
        if result.status.startswith("prepared"):
            self.status.mark_pending(article, platform, error=result.error)
        else:
            self.status.mark_result(article, platform, success=result.success, error=result.error)
        self.history.write(article, result)
        return result

    def publish_platform(self, platform: str, *, article: PublishedArticle | None = None) -> PublishResult:
        return self.prepare_platform(platform, article=article)

    def prepare_all(self, *, article: PublishedArticle | None = None, only_unpublished: bool = True) -> list[PublishResult]:
        article = article or self.latest_article()
        enabled = self.enabled_platforms()
        platforms = self.status.unpublished_platforms(article, enabled) if only_unpublished else enabled
        return [self.prepare_platform(platform, article=article) for platform in platforms]

    def publish_all(self, *, only_unpublished: bool = True) -> list[PublishResult]:
        return self.prepare_all(only_unpublished=only_unpublished)

    def confirm_manual_publish(
        self,
        platform: str,
        *,
        article: PublishedArticle | None = None,
        published_url: str = "",
        notes: str = "",
    ) -> PublishResult:
        article = article or self.latest_article()
        self.status.ensure_article(article)
        if platform not in PLATFORMS:
            return PublishResult(platform=platform, status="invalid_platform", url=article.url, error="unknown platform")
        self.status.mark_manual_published(article, platform, published_url=published_url, notes=notes)
        result = PublishResult(
            platform=platform,
            status="PUBLISHED_MANUAL",
            url=article.url,
            success=True,
            metadata={"published_url": published_url, "notes": notes},
        )
        self.history.write(article, result)
        return result

    def mark_pending(self, platform: str, *, article: PublishedArticle | None = None, notes: str = "") -> PublishResult:
        article = article or self.latest_article()
        self.status.ensure_article(article)
        self.status.mark_pending(article, platform, error=notes)
        result = PublishResult(platform=platform, status="PENDING", url=article.url, success=False, error=notes)
        self.history.write(article, result)
        return result

    def mark_failed(self, platform: str, *, article: PublishedArticle | None = None, notes: str = "") -> PublishResult:
        article = article or self.latest_article()
        self.status.ensure_article(article)
        self.status.mark_failed(article, platform, error=notes, notes=notes)
        result = PublishResult(platform=platform, status="FAILED", url=article.url, success=False, error=notes)
        self.history.write(article, result)
        return result

    def copy_prepared_content(
        self,
        platform: str,
        *,
        article: PublishedArticle | None = None,
        field: str = "all",
        use_clipboard: bool = True,
    ) -> Any:
        article = article or self.latest_article()
        payload = self.preview_platform(platform, article=article)
        return copy_or_write(payload, field=field, root=self.root, use_clipboard=use_clipboard)

    def platform_target(self, platform: str, *, article: PublishedArticle | None = None, open_browser: bool = False) -> str:
        article = article or self.latest_article()
        payload = self.preview_platform(platform, article=article)
        return open_platform_target(platform, payload, open_browser=open_browser)

    def article_by_index(self, index: int) -> PublishedArticle:
        items = self.list_articles(limit=max(index, 1))
        if index < 1 or index > len(items):
            raise RuntimeError(f"Article index {index} is not available.")
        return items[index - 1]["article"]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Social publisher for already-live Smile AI Review Hub articles.")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status")
    listing = sub.add_parser("list")
    listing.add_argument("--limit", type=int, default=25)
    preview = sub.add_parser("preview")
    preview.add_argument("--platform", default="pinterest", choices=PLATFORMS)
    preview.add_argument("--index", type=int)
    prepare = sub.add_parser("prepare")
    prepare.add_argument("--platform", required=True, choices=PLATFORMS)
    prepare.add_argument("--index", type=int)
    publish = sub.add_parser("publish")
    publish.add_argument("--platform", required=True, choices=PLATFORMS)
    publish.add_argument("--index", type=int)
    publish.add_argument("--confirm", action="store_true")
    confirm = sub.add_parser("confirm")
    confirm.add_argument("--platform", required=True, choices=PLATFORMS)
    confirm.add_argument("--index", type=int)
    confirm.add_argument("--published-url", default="")
    confirm.add_argument("--notes", default="")
    copy_cmd = sub.add_parser("copy")
    copy_cmd.add_argument("--platform", required=True, choices=PLATFORMS)
    copy_cmd.add_argument("--index", type=int)
    copy_cmd.add_argument("--field", default="all", choices=["title", "body", "url", "image", "all"])
    copy_cmd.add_argument("--no-clipboard", action="store_true")
    open_cmd = sub.add_parser("open-target")
    open_cmd.add_argument("--platform", required=True, choices=PLATFORMS)
    open_cmd.add_argument("--index", type=int)
    open_cmd.add_argument("--open", action="store_true")
    pending = sub.add_parser("mark-pending")
    pending.add_argument("--platform", required=True, choices=PLATFORMS)
    pending.add_argument("--index", type=int)
    pending.add_argument("--notes", default="")
    failed = sub.add_parser("mark-failed")
    failed.add_argument("--platform", required=True, choices=PLATFORMS)
    failed.add_argument("--index", type=int)
    failed.add_argument("--notes", default="")
    publish_all = sub.add_parser("publish-all")
    publish_all.add_argument("--confirm", action="store_true")
    publish_unpublished = sub.add_parser("publish-unpublished")
    publish_unpublished.add_argument("--confirm", action="store_true")
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
    if args.command == "list":
        for item in manager.list_articles(args.limit):
            article = item["article"]
            print("-" * 49)
            print(f"{item['index']:03d}")
            print(article.title)
            print("Website")
            print(item["website"])
            print("Already published platforms")
            print(", ".join(item["published_platforms"]) or "none")
            print("Remaining platforms")
            print(", ".join(item["remaining_platforms"]) or "none")
            print("Published")
            print(f"{item['published_social']}/{item['total_social']}")
        print("-" * 49)
        return 0
    if args.command == "preview":
        article = manager.article_by_index(args.index) if args.index else None
        print(format_preview(manager.preview_platform(args.platform, article=article)))
        return 0
    if args.command == "prepare":
        article = manager.article_by_index(args.index) if args.index else manager.latest_article()
        print(format_preview(manager.preview_platform(args.platform, article=article)))
        result = manager.prepare_platform(args.platform, article=article)
        print(f"{result.platform}: {result.status}")
        if result.error:
            print(f"note: {result.error}")
        print("After manually publishing on the platform, run confirm with the same platform/index.")
        return 0
    if args.command == "publish":
        article = manager.article_by_index(args.index) if args.index else manager.latest_article()
        if not args.confirm:
            print(format_preview(manager.preview_platform(args.platform, article=article)))
            print("This command only prepares a manual post. Re-run with --confirm to mark it PENDING after operator approval.")
            return 2
        result = manager.prepare_platform(args.platform, article=article)
        print(f"{result.platform}: {result.status}")
        if result.error:
            print(f"note: {result.error}")
        return 0 if result.success or result.status.startswith("prepared") or result.status.startswith("skipped") else 1
    if args.command == "confirm":
        article = manager.article_by_index(args.index) if args.index else manager.latest_article()
        result = manager.confirm_manual_publish(
            args.platform,
            article=article,
            published_url=args.published_url,
            notes=args.notes,
        )
        print(f"{result.platform}: {result.status}")
        if args.published_url:
            print(f"published_url: {args.published_url}")
        return 0
    if args.command == "copy":
        article = manager.article_by_index(args.index) if args.index else manager.latest_article()
        result = manager.copy_prepared_content(
            args.platform,
            article=article,
            field=args.field,
            use_clipboard=not args.no_clipboard,
        )
        print(f"copied_to_clipboard: {'YES' if result.copied_to_clipboard else 'NO'}")
        print(f"file_path: {result.file_path}")
        return 0
    if args.command == "open-target":
        article = manager.article_by_index(args.index) if args.index else manager.latest_article()
        target = manager.platform_target(args.platform, article=article, open_browser=args.open)
        print(f"target_url: {target}")
        return 0
    if args.command == "mark-pending":
        article = manager.article_by_index(args.index) if args.index else manager.latest_article()
        result = manager.mark_pending(args.platform, article=article, notes=args.notes)
        print(f"{result.platform}: {result.status}")
        return 0
    if args.command == "mark-failed":
        article = manager.article_by_index(args.index) if args.index else manager.latest_article()
        result = manager.mark_failed(args.platform, article=article, notes=args.notes)
        print(f"{result.platform}: {result.status}")
        return 0
    if args.command == "publish-all":
        if not args.confirm:
            print("Confirmation required before publishing all enabled platforms. Re-run with --confirm.")
            return 2
        for result in manager.prepare_all(only_unpublished=False):
            print(f"{result.platform}: {result.status}")
        return 0
    if args.command == "publish-unpublished":
        if not args.confirm:
            print("Confirmation required before publishing unpublished platforms. Re-run with --confirm.")
            return 2
        for result in manager.prepare_all(only_unpublished=True):
            print(f"{result.platform}: {result.status}")
        return 0
    if args.command == "history":
        for path in manager.history.latest(args.limit):
            print(path)
        return 0
    return 1
