from __future__ import annotations

import argparse
import json
import time
import webbrowser
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
from .draft_workflow import DEFAULT_SOCIAL_DRAFT_COUNT, SocialDraftWorkflow
from .external_draft_exchange import ExternalDraftExchange
from modules.external_writer_pipeline import UniversalWriteQueue
from .hot_news_editor import SocialHotEditor
from .review_dashboard_server import SocialReviewDashboardLauncher, SocialReviewDashboardServer, dashboard_health


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
    prepare_drafts = sub.add_parser("prepare-drafts")
    prepare_drafts.add_argument("--date", default="latest")
    prepare_drafts.add_argument("--count", type=int, default=DEFAULT_SOCIAL_DRAFT_COUNT)
    prepare_drafts.add_argument("--platforms", nargs="*", default=["all"])
    prepare_drafts.add_argument("--slug", action="append", default=[])
    normalize_bindings = sub.add_parser("normalize-source-bindings")
    normalize_bindings.add_argument("--date", default="latest")
    export_external = sub.add_parser("export-chatgpt-package")
    export_external.add_argument("--date", default="latest")
    import_external = sub.add_parser("import-external-drafts")
    import_external.add_argument("--date", default="latest")
    import_external.add_argument("--refresh-dashboard", action="store_true")
    hot_news = sub.add_parser("prepare-hot-news-monitoring")
    hot_news.add_argument("--date", required=True)
    hot_news.add_argument("--title", required=True)
    hot_news.add_argument("--source-url", action="append", required=True)
    hot_news.add_argument("--discovery-timestamp", default="")
    hot_news.add_argument("--summary", default="")
    hot_news.add_argument("--platforms", nargs="*", default=None)
    hot_news_auto = sub.add_parser("prepare-hot-news-auto")
    hot_news_auto.add_argument("--date", default="")
    hot_news_auto.add_argument("--dry-run", action="store_true")
    hot_news_auto.add_argument(
        "--require-selected",
        action="store_true",
        help="Return status 3 when discovery succeeds but selects no eligible hot-news item.",
    )
    review_dashboard = sub.add_parser("review-dashboard")
    review_dashboard.add_argument("--date", default="latest")
    review_dashboard.add_argument("--open", action="store_true")
    review_dashboard.add_argument("--serve", action="store_true")
    review_dashboard.add_argument("--port", type=int, default=8776)
    launch_dashboard = sub.add_parser("launch-review-dashboard")
    launch_dashboard.add_argument("--date", default="latest")
    launch_dashboard.add_argument("--port", type=int, default=8776)
    launch_dashboard.add_argument("--open", action="store_true")
    health_dashboard = sub.add_parser("dashboard-health")
    health_dashboard.add_argument("--port", type=int, default=8776)
    stop_dashboard = sub.add_parser("stop-review-dashboard")
    stop_dashboard.add_argument("--port", type=int, default=8776)
    approved_for_copy = sub.add_parser("approved-for-copy")
    approved_for_copy.add_argument("--date", default="latest")
    approve_draft = sub.add_parser("approve-draft")
    approve_draft.add_argument("--date", required=True)
    approve_draft.add_argument("--slug", required=True)
    approve_draft.add_argument("--platform", required=True)
    reject_draft = sub.add_parser("reject-draft")
    reject_draft.add_argument("--date", required=True)
    reject_draft.add_argument("--slug", required=True)
    reject_draft.add_argument("--platform", required=True)
    revision = sub.add_parser("request-revision")
    revision.add_argument("--date", required=True)
    revision.add_argument("--slug", required=True)
    revision.add_argument("--platform", required=True)
    revision.add_argument("--notes", default="")
    copy_approved = sub.add_parser("copy-approved")
    copy_approved.add_argument("--date", default="latest")
    copy_approved.add_argument("--index", type=int, default=1)
    copy_approved.add_argument(
        "--field",
        default="all",
        choices=[
            "title",
            "body",
            "cta",
            "hashtags",
            "url",
            "image",
            "all",
            "pin_description",
            "destination_url",
            "suggested_board",
            "keywords",
            "alt_text",
            "image_path",
            "blogger_title",
            "html_body",
            "plain_text_body",
            "labels",
            "search_description",
            "source_article_url",
            "permalink_slug",
            "recommended_permalink_slug",
            "image_alt_text",
            "standalone_post",
            "full_thread",
            "thread_post_1",
            "thread_post_2",
            "thread_post_3",
            "thread_post_4",
            "thread_post_5",
            "article_url",
        ],
    )
    copy_approved.add_argument("--no-clipboard", action="store_true")
    mark_social = sub.add_parser("mark-approved-published")
    mark_social.add_argument("--date", default="latest")
    mark_social.add_argument("--index", type=int, default=1)
    mark_social.add_argument("--published-url", required=True)
    mark_manual = sub.add_parser("mark-published-manual")
    mark_manual.add_argument("--date", required=True)
    mark_manual.add_argument("--slug", required=True)
    mark_manual.add_argument("--platform", default="pinterest")
    mark_manual.add_argument("--url", required=True)
    mark_manual.add_argument("--allow-duplicate-override", action="store_true")
    pending_manual = sub.add_parser("mark-pending-manual")
    pending_manual.add_argument("--date", required=True)
    pending_manual.add_argument("--slug", required=True)
    pending_manual.add_argument("--platform", default="pinterest")
    reset_manual = sub.add_parser("reset-published-manual")
    reset_manual.add_argument("--date", required=True)
    reset_manual.add_argument("--slug", required=True)
    reset_manual.add_argument("--platform", default="pinterest")
    reset_manual.add_argument("--confirm", action="store_true")
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
    if args.command == "prepare-drafts":
        workflow = SocialDraftWorkflow(root=manager.root)
        manifest = workflow.prepare_drafts(
            batch_date=args.date,
            count=args.count,
            platforms=args.platforms,
            slugs=args.slug,
        )
        print(f"Batch date: {manifest['batch_date']}")
        print(f"Social mode: {manifest.get('content_origin') or 'WEBSITE_ROOT_BASED'}")
        print(f"Content cycle: {manifest.get('social_week_start') or '-'}")
        print(f"Website root topics: {len(manifest.get('weekly_root_slugs') or [])}")
        print(f"Unrelated historical tasks loaded: {manifest.get('unrelated_historical_tasks_loaded', 0)}")
        print(f"Available live articles: {manifest['available_live_count']}")
        print(f"Selected for social drafts: {manifest['selected_count']}")
        print("Selected articles:")
        for item in manifest["items"]:
            print(f"- {item['slug']} | {item['title']}")
            print(f"  URL: {item['url']}")
            print(f"  Root: {item.get('root_topic_id') or '-'}")
            print(f"  Evidence: {item.get('evidence_inheritance') or 'SOURCE_PACKAGE'}")
            print(f"  Source package: {item['source_package']}")
            print(f"  Legacy repository-writer prompt: {item['prompt']}")
        synced = UniversalWriteQueue(root=manager.root).sync_social(batch_date=manifest["batch_date"])
        print(f"External writer tasks synchronized: {len(synced)}")
        print("Next step: use Menu X to export the external ChatGPT writing package.")
        return 0
    if args.command == "normalize-source-bindings":
        result = SocialDraftWorkflow(root=manager.root).normalize_source_bindings(batch_date=args.date)
        UniversalWriteQueue(root=manager.root).sync_social(batch_date=result["batch_date"])
        print(json.dumps(result, indent=2, ensure_ascii=False))
        print("No draft copy, approval, or publish status was changed.")
        return 0
    if args.command == "export-chatgpt-package":
        result = ExternalDraftExchange(root=manager.root).export_chatgpt_package(
            batch_date=args.date
        )
        print(f"Batch date: {result['batch_date']}")
        print(f"Writing tasks exported: {result['items_exported']}")
        print(f"ChatGPT package: {result['package_path']}")
        print(f"Ready-to-copy prompt: {result['prompt_path']}")
        print("No API, approval, publish, deployment, or indexing action occurred.")
        return 0
    if args.command == "import-external-drafts":
        result = ExternalDraftExchange(root=manager.root).import_pending(
            batch_date=args.date
        )
        print(f"Batch date: {result['batch_date']}")
        print(f"Pending packages scanned: {result['scanned']}")
        print(f"Imported: {len(result['imported'])}")
        print(f"Unchanged: {len(result['unchanged'])}")
        print(f"Rejected: {len(result['rejected'])}")
        for item in result["imported"]:
            print(f"- IMPORTED {item['slug']} -> {item['path']}")
        for item in result["rejected"]:
            print(f"- REJECTED {item['path']}: {item['reason']}")
        if args.refresh_dashboard:
            path = SocialDraftWorkflow(root=manager.root).build_review_dashboard(
                batch_date=result["batch_date"]
            )
            print(f"Dashboard refreshed: {path}")
        print("All imported drafts remain needs_social_review. Nothing was published.")
        return 2 if result["rejected"] else 0
    if args.command == "prepare-hot-news-monitoring":
        workflow = SocialDraftWorkflow(root=manager.root)
        manifest = workflow.prepare_hot_news_monitoring(
            batch_date=args.date,
            title=args.title,
            source_urls=args.source_url,
            discovery_timestamp=args.discovery_timestamp or None,
            platforms=args.platforms,
            summary=args.summary,
        )
        item = manifest["items"][-1]
        print(f"Batch date: {manifest['batch_date']}")
        print("Content lane: SOCIAL_HOT_UNCONFIRMED")
        print(f"Selected item: {item['slug']} | {item['title']}")
        print(f"Source package: {item['source_package']}")
        print(f"Codex prompt: {item['prompt']}")
        print("No website URL was created. Open Menu G to review the social-only monitoring draft.")
        return 0
    if args.command == "prepare-hot-news-auto":
        editor = SocialHotEditor(root=manager.root)
        report = editor.select() if args.dry_run else editor.prepare_auto(batch_date=args.date or None)
        print("Menu H - AI News Editor")
        print(f"Sources scanned: {report['sources_scanned']}")
        print(f"Raw items discovered: {report['signals_found']}")
        print(f"Normalized candidates: {report['normalized_candidates']}")
        print(f"Event clusters: {report['clusters_created']}")
        print(f"Tier A eligible: {report['tier_a_eligible']}")
        print(f"Tier B eligible: {report['tier_b_eligible']}")
        portfolio = report.get("daily_editorial_portfolio") or {}
        print(f"Eligible candidates: {portfolio.get('eligible_count', 0)}")
        print(f"Distinct company families: {portfolio.get('distinct_company_families', 0)}")
        print(f"Distinct editorial ecosystems: {portfolio.get('distinct_editorial_ecosystems', 0)}")
        print(f"Selected: {report['selected_count']}")
        print(f"Rejected: {report['rejected_count']}")
        signal_advisory = report.get("social_signal_advisory") or {}
        print(
            "Human-approved social-signal advisories: "
            f"{signal_advisory.get('count', 0)} (recommendation-only; queue unchanged)"
        )
        print("\nDaily Editorial Portfolio:")
        print(f"Selection policy: {portfolio.get('selection_policy', 'NO_ELIGIBLE_CANDIDATES')}")
        families = ", ".join(portfolio.get("selected_families") or [])
        ecosystems = ", ".join(portfolio.get("selected_ecosystems") or [])
        print(f"Families selected: {families or 'none'}")
        print(f"Ecosystems selected: {ecosystems or 'none'}")
        print(
            "Breaking exception applied: "
            + ("YES" if portfolio.get("breaking_exception_applied") else "NO")
        )
        print("\nSelected items:")
        for index, item in enumerate(report["selected"], start=1):
            print(f"{index}. [Tier {item['selection_tier']}] [{item['final_score']:.1f}] {item['title']}")
            print(f"   Reason: {item.get('portfolio_selection_reason', item.get('selection_reason', ''))}")
        print("\nTop rejected:")
        for index, item in enumerate(report["rejected"][:10], start=1):
            print(f"{index}. [{item['primary_reason']}] [{item['final_score']:.1f}] {item['title']}")
        if args.dry_run:
            print("Queue generated: 0 (dry-run)")
        else:
            print(f"Queue generated: {report['queue_generated']}")
            if report.get("report_path"):
                print(f"\nFull report: {report['report_path']}")
            print("\nNext step:")
            print("Open data/ai_tasks/CURRENT_AI_TASK.md (or legacy data/codex_tasks/CURRENT_TASK.md)")
            print("and ask the repository AI writer to complete the hot-news social draft task.")
            print("Then use Menu G for review and Menu E for manual copy.")
            print("No website article, approval, publish, deploy, index, OAuth, or paid API action occurred.")
            if int(report.get("selected_count") or 0) > 0:
                synced = UniversalWriteQueue(root=manager.root).sync_social(
                    batch_date=str(report.get("batch_date") or args.date or "latest")
                )
                print(f"External writer tasks synchronized: {len(synced)}")
            else:
                print("External writer tasks synchronized: 0 (no eligible hot-news item selected)")
        if args.require_selected and int(report.get("selected_count") or 0) == 0:
            return 3
        return 0
    if args.command == "review-dashboard":
        workflow = SocialDraftWorkflow(root=manager.root)
        path = workflow.build_review_dashboard(batch_date=args.date)
        print(f"Social review dashboard: {path}")
        if args.serve:
            server = SocialReviewDashboardServer(root=manager.root, date=args.date, port=args.port)
            server.serve(open_browser=args.open)
        elif args.open:
            result = SocialReviewDashboardLauncher(root=manager.root, date=args.date, port=args.port).launch(open_browser=True)
            print(f"dashboard_status: {result['status']}")
            print(f"dashboard_url: {result['url']}")
        return 0
    if args.command == "launch-review-dashboard":
        result = SocialReviewDashboardLauncher(root=manager.root, date=args.date, port=args.port).launch(open_browser=args.open)
        print(f"dashboard_status: {result['status']}")
        print(f"dashboard_url: {result['url']}")
        print(f"dashboard_port: {result['port']}")
        if result.get("pid"):
            print(f"dashboard_pid: {result['pid']}")
        if result.get("note"):
            print(f"note: {result['note']}")
        return 0
    if args.command == "dashboard-health":
        health = dashboard_health(port=args.port)
        print(json.dumps(health, indent=2, ensure_ascii=False))
        return 0 if health.get("healthy") else 1
    if args.command == "stop-review-dashboard":
        import json as _json
        import urllib.request

        request = urllib.request.Request(
            f"http://127.0.0.1:{args.port}/api/social/stop",
            data=_json.dumps({"date": "latest", "slug": "dashboard", "platform": "dashboard"}).encode("utf-8"),
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=2) as response:
            print(response.read().decode("utf-8"))
        return 0
    if args.command == "approved-for-copy":
        workflow = SocialDraftWorkflow(root=manager.root)
        items = workflow.approved_for_copy_items(batch_date=args.date)
        if not items:
            print("No approved social drafts are ready for manual copy.")
            print("Run Menu F to prepare social writing packages, then Menu G to review and approve drafts.")
            return 0
        print("Approved social drafts ready for manual copy:")
        for index, item in enumerate(items, start=1):
            print("-" * 49)
            print(f"{index:03d}. {item['title']}")
            print(f"slug: {item['slug']}")
            print(f"platform: {item['platform']}")
            print(f"status: {item.get('status_label') or item.get('status')}")
            print(f"website_url: {item['website_url']}")
            if item.get("final_published_url"):
                print(f"final_published_url: {item['final_published_url']}")
                print(f"published_at: {item.get('published_at') or ''}")
            print(f"draft: {item['draft_path']}")
            print(f"draft_exists: {'YES' if item['exists'] else 'NO'}")
        print("-" * 49)
        return 0
    if args.command == "approve-draft":
        workflow = SocialDraftWorkflow(root=manager.root)
        path = workflow.set_platform_status(
            batch_date=args.date,
            slug=args.slug,
            platform=args.platform,
            status="approved_for_copy",
        )
        print(f"approved_for_copy: {args.slug} / {args.platform}")
        print(f"metadata: {path}")
        return 0
    if args.command == "reject-draft":
        workflow = SocialDraftWorkflow(root=manager.root)
        path = workflow.set_platform_status(
            batch_date=args.date,
            slug=args.slug,
            platform=args.platform,
            status="rejected",
        )
        print(f"rejected: {args.slug} / {args.platform}")
        print(f"metadata: {path}")
        return 0
    if args.command == "request-revision":
        workflow = SocialDraftWorkflow(root=manager.root)
        path = workflow.set_platform_status(
            batch_date=args.date,
            slug=args.slug,
            platform=args.platform,
            status="revision_requested",
            reviewer_notes=args.notes,
        )
        print(f"revision_requested: {args.slug} / {args.platform}")
        print(f"metadata: {path}")
        return 0
    if args.command == "copy-approved":
        workflow = SocialDraftWorkflow(root=manager.root)
        payload = workflow.approved_copy_payload(batch_date=args.date, index=args.index)
        result = copy_or_write(
            {
                "platform": payload["platform"],
                "title": payload["title"],
                "post_text": payload["body"],
                "url": payload["url"],
                "canonical_url": payload["url"],
                "image_url": payload["image_url"],
                "image_asset_path": payload.get("image_asset_path") or "",
                "pin_title": payload.get("pin_title") or "",
                "pin_description": payload.get("pin_description") or "",
                "destination_url": payload.get("destination_url") or "",
                "suggested_board": payload.get("suggested_board") or "",
                "keywords": payload.get("keywords") or [],
                "alt_text": payload.get("alt_text") or "",
                "blogger_title": payload.get("blogger_title") or "",
                "html_body": payload.get("html_body") or "",
                "plain_text_body": payload.get("plain_text_body") or "",
                "labels": payload.get("labels") or [],
                "search_description": payload.get("search_description") or "",
                "source_article_url": payload.get("source_article_url") or "",
                "recommended_permalink_slug": payload.get("recommended_permalink_slug") or "",
                "disclosure": payload.get("disclosure") or "",
                "image_path": payload.get("image_path") or payload.get("image_asset_path") or "",
                "image_alt_text": payload.get("image_alt_text") or "",
                "standalone_post": payload.get("standalone_post") or "",
                "thread_posts": payload.get("thread_posts") or [],
                "article_url": payload.get("article_url") or "",
                "character_counts": payload.get("character_counts") or {},
                "hashtags": str(payload["hashtags"]).split(),
                "cta": payload.get("cta") or "",
                "clean_social_copy": True,
            },
            field=args.field,
            root=manager.root,
            use_clipboard=not args.no_clipboard,
        )
        print(f"copied_to_clipboard: {'YES' if result.copied_to_clipboard else 'NO'}")
        print(f"file_path: {result.file_path}")
        return 0
    if args.command == "mark-approved-published":
        workflow = SocialDraftWorkflow(root=manager.root)
        payload = workflow.approved_copy_payload(batch_date=args.date, index=args.index)
        path = workflow.mark_published_manual(
            batch_date=str(payload["batch_date"]),
            slug=str(payload["slug"]),
            platform=str(payload["platform"]),
            published_url=args.published_url,
        )
        print(f"published_manual: {payload['slug']} / {payload['platform']}")
        print(f"published_url: {args.published_url}")
        print(f"metadata: {path}")
        return 0
    if args.command == "mark-published-manual":
        workflow = SocialDraftWorkflow(root=manager.root)
        path = workflow.mark_published_manual(
            batch_date=args.date,
            slug=args.slug,
            platform=args.platform,
            published_url=args.url,
            allow_duplicate_override=args.allow_duplicate_override,
        )
        print(f"published_manual: {args.slug} / {args.platform}")
        print(f"final_published_url: {args.url}")
        print(f"metadata: {path}")
        return 0
    if args.command == "mark-pending-manual":
        workflow = SocialDraftWorkflow(root=manager.root)
        path = workflow.mark_pending_manual_publish(batch_date=args.date, slug=args.slug, platform=args.platform)
        print(f"pending_manual_publish: {args.slug} / {args.platform}")
        print(f"metadata: {path}")
        return 0
    if args.command == "reset-published-manual":
        if not args.confirm:
            print("Reset requires explicit confirmation. Re-run with --confirm.")
            return 2
        workflow = SocialDraftWorkflow(root=manager.root)
        path = workflow.reset_published_manual(batch_date=args.date, slug=args.slug, platform=args.platform, confirmed=True)
        print(f"published_manual_reset: {args.slug} / {args.platform}")
        print(f"metadata: {path}")
        return 0
    return 1
