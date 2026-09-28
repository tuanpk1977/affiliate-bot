from __future__ import annotations

import html
import hashlib
import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from .utils import (
    DATA_DIR,
    PLATFORMS,
    ROOT,
    PublishedArticle,
    configured_social_draft_platforms,
    configured_social_platform_playbooks,
    extract_affiliate_disclosure,
    extract_article_summary,
    extract_canonical,
    extract_headings,
    extract_meta,
    extract_paragraphs,
    extract_publish_date,
    extract_tags,
    extract_title,
    read_json,
    slug_from_url,
    now_iso,
)
from .draft_assets import (
    Image,
    ImageDraw,
    ImageFont,
    PLATFORM_ASSET_NAME,
    SOCIAL_ASSET_FORMATS,
    SocialDraftAssetService,
    _safe_asset_name,
    _sha256_file,
    _wrap_card_text,
)
from .draft_selection import SocialDraftSelectionService
from .draft_root_selection import SocialDraftRootSelectionService
from .draft_review_dashboard_renderer import render_review_dashboard_html
from .draft_source_package import SocialDraftSourcePackageService
from .draft_hot_news import (
    SocialDraftHotNewsService,
    HOT_NEWS_MONITORING_PLATFORMS,
    _hot_news_source_host,
    _hot_news_hashtags,
    _hot_news_summary,
    _hot_news_title_line,
    _hot_news_starter_drafts,
)
from modules.weekly_root_guard import SOCIAL_HOT_UNCONFIRMED
from modules.research_enrichment import ResearchEnrichmentPipeline
from modules.social.content_quality import (
    infer_story_audience,
    official_source_name,
    validate_pinterest_visual,
    validate_social_value,
)
from modules.social.platform_native import PlatformNativeSocialEngine, X_MAX_CHARACTERS

from .draft_contracts import (
    BLUESKY_CHARACTER_LIMIT,
    SOCIAL_DRAFT_STATUSES,
    SOCIAL_STATUS_LABELS,
    SOCIAL_STATUS_ALIASES,
    PLATFORM_LABELS,
    VIETNAMESE_MOJIBAKE_PATTERNS,
    _status_key,
    _status_label,
    _platform_label,
    has_vietnamese_mojibake,
    vietnamese_mojibake_warning,
    _append_unique_warning,
    normalize_pinterest_final_url,
    validate_pinterest_final_url,
    _extract_prefixed_line,
    _strip_pinterest_labels,
    _clean_pin_description,
    _pinterest_fields_from_metadata,
    _public_url,
    _plain_words,
    _word_count,
    _sentence,
    _sentence_list,
    _clean_public_text,
    _slugify,
    _title_case,
    _blogger_title_for_article,
    _blogger_search_description,
    _blogger_permalink_slug,
    _looks_incomplete_sentence,
    _unique,
    _label_from_tag,
    _html_paragraph,
    _html_list,
    _html_link,
    _dedupe_paragraphs,
    _duplicate_items,
    _extract_html_headings,
    _extract_html_paragraph_texts,
    _count_links,
    _blogger_json_ld,
    _blogger_seo_metrics,
    _body_has_internal_text,
    _clip_to_limit,
    _blogger_article_fields,
    validate_blogger_metadata,
    _bluesky_fields,
    validate_bluesky_metadata,
)



DEFAULT_SOCIAL_DRAFT_COUNT = 2
SOCIAL_WEEKLY_ROOT_COUNT = 2
SOCIAL_PLATFORM_GUIDELINES = {
    "facebook": {
        "tone": "friendly conversation-oriented",
        "label": "Facebook",
    },
    "linkedin": {
        "tone": "professional business leadership",
        "label": "LinkedIn",
    },
    "twitter": {
        "tone": "short hook-first",
        "label": "X",
    },
    "threads": {
        "tone": "conversational natural",
        "label": "Threads",
    },
    "pinterest": {
        "tone": "pin title and description",
        "label": "Pinterest",
    },
    "devto": {
        "tone": "developer intro only",
        "label": "Dev.to",
    },
    "medium": {
        "tone": "non-duplicate excerpt",
        "label": "Medium",
    },
    "hashnode": {
        "tone": "developer-focused",
        "label": "Hashnode",
    },
    "telegram": {
        "tone": "short announcement",
        "label": "Telegram",
    },
    "blogger": {
        "tone": "blog teaser",
        "label": "Blogger",
    },
    "bluesky": {
        "tone": "short conversational",
        "label": "Bluesky",
    },
}
SOCIAL_REVIEW_PLATFORMS = configured_social_draft_platforms(ROOT)
NON_SOCIAL_KEYPOINT_HEADINGS = {
    "affiliate disclosure",
    "author and editorial review",
    "about the author",
    "related reading",
    "our community signals",
    "community signals",
    "facebook",
    "linkedin",
    "x",
    "twitter",
    "threads",
    "pinterest",
    "dev.to",
    "medium",
    "hashnode",
    "telegram",
    "blogger",
    "sources",
    "faq",
    "faqs",
}


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _looks_like_iso_date(value: str) -> bool:
    return bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(value or "")))


def _monitoring_slug(title: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", str(title or "").lower()).strip("-")
    return (value[:88] or "hot-news-monitoring").strip("-")


def _week_start(value: str) -> str:
    parsed = datetime.strptime(value, "%Y-%m-%d").date()
    monday = parsed - timedelta(days=parsed.weekday())
    return monday.isoformat()


def _split_tags(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if not value:
        return []
    return [part for part in re.split(r"[\s,]+", str(value)) if part]


def _normalize_platforms(platforms: list[str] | None) -> list[str]:
    if not platforms or platforms == ["all"]:
        return list(SOCIAL_REVIEW_PLATFORMS)
    cleaned: list[str] = []
    for platform in platforms:
        for part in str(platform).split(","):
            candidate = part.strip().lower()
            if not candidate:
                continue
            if candidate not in SOCIAL_REVIEW_PLATFORMS and candidate not in PLATFORMS:
                raise ValueError(f"Unknown social platform: {candidate}")
            if candidate not in cleaned:
                cleaned.append(candidate)
    return cleaned


def _title_from_slug(slug: str) -> str:
    small_words = {"ai", "by", "for", "to", "and", "or", "in", "of"}
    words = []
    for raw in slug.replace("_", "-").split("-"):
        if not raw:
            continue
        if raw in small_words:
            words.append(raw.upper() if raw == "ai" else raw)
        elif raw.isdigit():
            words.append(raw)
        else:
            words.append(raw.capitalize())
    return " ".join(words)


def _best_title(slug: str, extracted: str, fallback: str = "") -> str:
    extracted = html.unescape((extracted or "").strip())
    fallback = html.unescape((fallback or "").strip())
    slug_title = _title_from_slug(slug)
    candidate = extracted or fallback or slug_title
    # Several historical generated pages have truncated title/meta fields.
    if slug_title and len(candidate) + 8 < len(slug_title):
        return slug_title
    return candidate




def _remove_public_url_blocks(text: str, url: str) -> str:
    clean_url = str(url or "").strip()
    body = str(text or "").strip()
    if not clean_url:
        return body
    escaped = re.escape(clean_url)
    patterns = [
        rf"^This adapted draft[^\n]*canonical[^\n]*:\s*\n{escaped}\s*$",
        rf"^The complete article[^\n]*canonical[^\n]*:\s*\n{escaped}\s*$",
        rf"^Read the full source article:\s*\n{escaped}\s*$",
        rf"^Read the full source article:\s*{escaped}\s*$",
        rf"^I wrote a more detailed[^\n]*{escaped}\s*$",
        rf"^Read the full guide here:\s*\n{escaped}\s*$",
        rf"^Read the full guide here:\s*{escaped}\s*$",
        rf"^{escaped}\s*$",
    ]
    for pattern in patterns:
        body = re.sub(pattern, "", body, flags=re.I | re.M)
    return re.sub(r"\n{3,}", "\n\n", body).strip()


def _clean_quora_copy_text(*, body: str, title: str, source_url: str, disclosure: str, hashtags: str) -> str:
    text = re.sub(r"^#\s*Quora answer draft\s*", "", str(body or ""), flags=re.I).strip()
    question = _extract_prefixed_line(text, "Suggested Quora question:") or _extract_prefixed_line(text, "Suggested question:") or title
    text = re.sub(r"^Suggested Quora question:\s*.+$", "", text, flags=re.I | re.M)
    text = re.sub(r"^Suggested question:\s*.+$", "", text, flags=re.I | re.M)
    text = re.sub(r"^Answer title/opening:\s*", "", text, flags=re.I | re.M)
    text = re.sub(r"^Full answer body:\s*$", "", text, flags=re.I | re.M)
    text = re.sub(r"^Website source URL:\s*.+$", "", text, flags=re.I | re.M)
    text = re.sub(r"^Source link:\s*.+$", "", text, flags=re.I | re.M)
    text = re.sub(r"^Disclosure:\s*.+$", "", text, flags=re.I | re.M)
    text = _remove_public_url_blocks(text, source_url)
    clean_disclosure = disclosure or "I am linking to an independent Smile AI Review Hub article."
    parts = [
        f"Suggested question: {question}".strip(),
        text,
        "Read the full guide here:",
        source_url,
        f"Disclosure: {clean_disclosure}".strip(),
        f"Tags: {hashtags}".strip() if hashtags else "",
    ]
    return "\n\n".join(part for part in parts if part).strip()


class SocialDraftWorkflow:
    """Prepare manual social-writing packages from already-live website articles."""

    def __init__(self, *, root: Path = ROOT) -> None:
        self.root = root
        self.data_dir = root / "data"
        self.draft_root = self.data_dir / "social_drafts"
        self.platform_playbooks = configured_social_platform_playbooks(root)
        self.platform_native_engine = PlatformNativeSocialEngine(self.platform_playbooks)

    def _root_selection_service(self) -> SocialDraftRootSelectionService:
        return SocialDraftRootSelectionService(
            root=self.root,
            data_dir=self.data_dir,
            draft_root=self.draft_root,
            article_from_live_row=self.article_from_live_row,
            social_batch_dates=self._social_batch_dates,
            best_title=_best_title,
            looks_like_iso_date=_looks_like_iso_date,
            week_start=_week_start,
            status_key=_status_key,
            write_json=_write_json,
            now_iso=now_iso,
            social_weekly_root_count=SOCIAL_WEEKLY_ROOT_COUNT,
            default_social_draft_count=DEFAULT_SOCIAL_DRAFT_COUNT,
        )

    def _current_cycle_angle_history(
        self,
        *,
        batch_date: str,
        root_topic_id: str,
        platform: str,
    ) -> list[str]:
        return self._root_selection_service()._current_cycle_angle_history(
            batch_date=batch_date, root_topic_id=root_topic_id, platform=platform,
        )

    def _draft_asset_service(self) -> SocialDraftAssetService:
        return SocialDraftAssetService(
            draft_root=self.draft_root,
            read_json=read_json,
            write_json=_write_json,
            now_iso=now_iso,
            official_source_name=official_source_name,
            validate_pinterest_visual=validate_pinterest_visual,
            image=Image,
            image_draw=ImageDraw,
            image_font=ImageFont,
        )

    def _asset_fingerprint(self, article: PublishedArticle) -> str:
        return self._draft_asset_service()._asset_fingerprint(article)

    def _render_social_asset(
        self,
        path: Path,
        *,
        title: str,
        subtitle: str,
        size: tuple[int, int],
        points: list[str] | None = None,
        source_name: str = "",
    ) -> None:
        self._draft_asset_service()._render_social_asset(
            path,
            title=title,
            subtitle=subtitle,
            size=size,
            points=points,
            source_name=source_name,
        )

    def generate_social_assets(self, article: PublishedArticle, *, batch_date: str, force: bool = False) -> dict[str, Any]:
        return self._draft_asset_service().generate_social_assets(
            article,
            batch_date=batch_date,
            force=force,
            asset_fingerprint=self._asset_fingerprint,
            render_social_asset=self._render_social_asset,
        )

    def _ensure_local_social_card(self, *, batch_date: str, slug: str, title: str) -> str:
        return self._draft_asset_service()._ensure_local_social_card(
            batch_date=batch_date,
            slug=slug,
            title=title,
            generate_social_assets=self.generate_social_assets,
        )

    def _draft_selection_service(self) -> SocialDraftSelectionService:
        return SocialDraftSelectionService(
            data_dir=self.data_dir,
            draft_root=self.draft_root,
            read_json=read_json,
            slug_from_url=slug_from_url,
            looks_like_iso_date=_looks_like_iso_date,
        )

    def _live_report_items(self, batch_date: str | None = None) -> tuple[str, list[dict[str, Any]]]:
        return self._draft_selection_service()._live_report_items(
            batch_date,
            is_live_200=self._is_live_200,
        )

    def _social_batch_dates(self) -> list[str]:
        return self._draft_selection_service()._social_batch_dates()

    def resolve_latest_live_batch(self, requested_date: str = "latest") -> str:
        return self._draft_selection_service().resolve_latest_live_batch(
            requested_date,
            live_report_items=self._live_report_items,
            is_live_200=self._is_live_200,
            social_batch_dates=self._social_batch_dates,
        )

    def resolve_latest_social_batch(self, requested_date: str = "latest") -> str:
        return self._draft_selection_service().resolve_latest_social_batch(
            requested_date,
            social_batch_dates=self._social_batch_dates,
            resolve_latest_live_batch=self.resolve_latest_live_batch,
        )

    def _is_live_200(self, row: dict[str, Any]) -> bool:
        return self._draft_selection_service()._is_live_200(row)

    def live_articles(self, batch_date: str = "latest") -> list[dict[str, Any]]:
        return self._draft_selection_service().live_articles(
            batch_date,
            resolve_latest_live_batch=self.resolve_latest_live_batch,
            live_report_items=self._live_report_items,
            is_live_200=self._is_live_200,
        )

    def _research_source_count(self, slug: str) -> int:
        return self._root_selection_service()._research_source_count(slug)

    def rank_articles(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return self._root_selection_service().rank_articles(rows)

    def _weekly_social_roots_path(self, week_start: str) -> Path:
        return self._root_selection_service()._weekly_social_roots_path(week_start)

    def _website_weekly_roots(self, batch_date: str) -> list[dict[str, Any]]:
        return self._root_selection_service()._website_weekly_roots(batch_date)

    def _website_root_bindings(
        self, *, batch_date: str, roots: list[dict[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        return self._root_selection_service()._website_root_bindings(
            batch_date=batch_date, roots=roots,
        )

    def _source_binding(self, slug: str, context: dict[str, Any]) -> dict[str, Any]:
        return self._root_selection_service()._source_binding(slug, context)

    def _read_weekly_social_roots(self, batch_date: str) -> dict[str, Any]:
        return self._root_selection_service()._read_weekly_social_roots(batch_date)

    def _write_weekly_social_roots(
        self, *, batch_date: str, ranking: list[dict[str, Any]], selected: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return self._root_selection_service()._write_weekly_social_roots(
            batch_date=batch_date, ranking=ranking, selected=selected,
        )

    def _live_row_for_weekly_root(
        self, slug: str, resolved: str, live_by_slug: dict[str, dict[str, Any]],
    ) -> dict[str, Any] | None:
        return self._root_selection_service()._live_row_for_weekly_root(
            slug, resolved, live_by_slug,
        )

    def _source_package_service(self) -> SocialDraftSourcePackageService:
        return SocialDraftSourcePackageService(
            root=self.root,
            data_dir=self.data_dir,
            platform_playbooks=self.platform_playbooks,
            best_title=_best_title,
            non_social_keypoint_headings=NON_SOCIAL_KEYPOINT_HEADINGS,
            research_pipeline_cls=ResearchEnrichmentPipeline,
            now_iso=now_iso,
            x_max_characters=X_MAX_CHARACTERS,
        )

    def article_from_live_row(self, row: dict[str, Any]) -> PublishedArticle:
        return self._source_package_service().article_from_live_row(row)

    def source_package(
        self,
        article: PublishedArticle,
        *,
        batch_date: str,
        platforms: list[str],
        social_series: dict[str, Any] | None = None,
        provenance: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self._source_package_service().source_package(
            article,
            batch_date=batch_date,
            platforms=platforms,
            social_series=social_series,
            provenance=provenance,
        )

    def writing_prompt(self, package: dict[str, Any]) -> str:
        return self._source_package_service().writing_prompt(package)

    def _hot_news_service(self) -> SocialDraftHotNewsService:
        return SocialDraftHotNewsService(
            draft_root=self.draft_root,
            generate_social_assets=self.generate_social_assets,
            write_json=_write_json,
            read_json=read_json,
            now_iso=now_iso,
            looks_like_iso_date=_looks_like_iso_date,
            normalize_platforms=_normalize_platforms,
            monitoring_slug=_monitoring_slug,
            safe_asset_name=_safe_asset_name,
        )

    def hot_news_monitoring_package(
        self, *, title: str, batch_date: str, source_urls: list[str],
        discovery_timestamp: str, platforms: list[str], summary: str = "",
        queue_type: str = "SOCIAL_HOT_DRAFT",
        editorial_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self._hot_news_service().hot_news_monitoring_package(
            title=title, batch_date=batch_date, source_urls=source_urls,
            discovery_timestamp=discovery_timestamp, platforms=platforms,
            summary=summary, queue_type=queue_type, editorial_metadata=editorial_metadata,
        )

    def hot_news_monitoring_prompt(self, package: dict[str, Any]) -> str:
        return self._hot_news_service().hot_news_monitoring_prompt(package)

    def prepare_hot_news_monitoring(
        self, *, batch_date: str, title: str, source_urls: list[str],
        discovery_timestamp: str | None = None, platforms: list[str] | None = None,
        summary: str = "", queue_type: str = "SOCIAL_HOT_DRAFT",
        editorial_metadata: dict[str, Any] | None = None,
        create_placeholder_drafts: bool = True,
    ) -> dict[str, Any]:
        return self._hot_news_service().prepare_hot_news_monitoring(
            batch_date=batch_date, title=title, source_urls=source_urls,
            discovery_timestamp=discovery_timestamp, platforms=platforms,
            summary=summary, queue_type=queue_type, editorial_metadata=editorial_metadata,
            create_placeholder_drafts=create_placeholder_drafts,
        )

    def _hashtags(self, article: PublishedArticle, platform: str) -> list[str]:
        base = ["#AI", "#SmallBusiness"]
        for tag in article.tags:
            clean = "".join(part for part in tag.title() if part.isalnum())
            if clean:
                base.append(f"#{clean}")
        if platform in {"devto", "hashnode"}:
            base.append("#DeveloperTools")
        return list(dict.fromkeys(base))[:5]

    def _platform_drafts(self, article: PublishedArticle, platform: str) -> dict[str, str]:
        url = article.canonical_url or article.url
        short_summary = (article.summary or article.description or article.title).strip()
        short_summary = short_summary[:360].rsplit(" ", 1)[0] if len(short_summary) > 360 else short_summary
        key_point = ""
        for candidate in article.key_points or article.headings or []:
            clean = str(candidate).strip()
            if len(clean) >= 28 and clean.lower() not in NON_SOCIAL_KEYPOINT_HEADINGS:
                key_point = clean
                break
        if not key_point:
            key_point = article.title
        hashtags = " ".join(self._hashtags(article, platform))
        disclosure = "\n\nDisclosure: this links to an independent Smile AI Review Hub article." if article.affiliate_disclosure else ""
        if platform == "pinterest":
            title = f"{article.title[:82]}"
            body = f"Pin title: {title}\n\nPin description: {short_summary}\n\nImage: {article.image}\n\nRead the full guide: {url}{disclosure}"
        elif platform == "linkedin":
            body = (
                f"One takeaway from this new buyer guide: {key_point}.\n\n"
                f"For teams comparing AI tools, the useful question is not just feature count. It is whether the tool changes the workflow, reduces handoffs, and fits the way the team actually buys software.\n\n"
                f"Full article: {url}\n\n{hashtags}{disclosure}"
            )
        elif platform == "twitter":
            body = f"{key_point}\n\nPractical buyer notes here: {url}\n\n{hashtags}"
        elif platform == "threads":
            body = f"{key_point}\n\nI pulled the practical buyer notes into a full guide here: {url}\n\nWhat would you check first before adopting this kind of AI tool?"
        elif platform == "facebook":
            body = (
                f"{key_point}\n\n"
                f"This is the kind of AI tool decision where the feature list is only half the story. The full guide looks at practical workflow fit, tradeoffs, and what buyers should verify before committing.\n\n"
                f"Read it here: {url}{disclosure}"
            )
        elif platform == "telegram":
            body = f"New Smile AI Review Hub guide: {article.title}\n\nUseful takeaway: {key_point}\n\nRead: {url}"
        elif platform == "devto":
            body = f"## Quick intro\n\n{short_summary}\n\nThis is only an introduction, not a duplicate repost. The full buyer guide is here: {url}\n\n{hashtags}"
        elif platform == "medium":
            body = f"{short_summary}\n\nThis excerpt is intentionally short so the canonical article remains the source of truth.\n\nRead the full guide: {url}"
        elif platform == "hashnode":
            body = f"Developer/product teams evaluating this space should start with one question: {key_point}\n\nThe full guide covers workflow fit and buyer tradeoffs: {url}\n\n{hashtags}"
        elif platform == "blogger":
            body = f"New guide on Smile AI Review Hub: {article.title}\n\n{short_summary}\n\nContinue reading: {url}{disclosure}"
        else:
            body = f"{key_point}\n\nFull guide: {url}\n\n{hashtags}"
        variant_b = body.replace("One takeaway", "A practical takeaway").replace("New guide", "Fresh guide")
        variant_c = body + "\n\nQuestion: what would make this worth adopting in your workflow?"
        return {"A.md": body.strip() + "\n", "B.md": variant_b.strip() + "\n", "C.md": variant_c.strip() + "\n"}

    def _reusable_excerpts(self, article: PublishedArticle) -> dict[str, str]:
        text = (article.summary or article.description or article.title).strip()
        return {
            "150": text[:150].strip(),
            "250": text[:250].strip(),
            "500": text[:500].strip(),
        }

    def prepare_drafts(
        self,
        *,
        batch_date: str = "latest",
        count: int = DEFAULT_SOCIAL_DRAFT_COUNT,
        platforms: list[str] | None = None,
        slugs: list[str] | None = None,
    ) -> dict[str, Any]:
        source_batch = self.resolve_latest_live_batch(batch_date)
        resolved = source_batch
        if str(batch_date).lower() == "latest":
            current_date = date.today().isoformat()
            if self._website_weekly_roots(current_date):
                resolved = current_date
        existing_manifest = read_json(self.draft_root / resolved / "manifest.json", {})
        raw_existing_items = existing_manifest.get("items") if isinstance(existing_manifest, dict) else []
        existing_items = raw_existing_items if isinstance(raw_existing_items, list) else []
        preserved_hot_items = [
            item
            for item in existing_items
            if isinstance(item, dict) and item.get("content_lane") == SOCIAL_HOT_UNCONFIRMED
        ]
        platform_list = _normalize_platforms(platforms)
        live_rows = self.live_articles(source_batch)
        ranking = self.rank_articles(live_rows)
        live_by_slug = {str(row.get("slug") or ""): row for row in live_rows}
        website_roots = self._website_weekly_roots(resolved)
        root_bindings = self._website_root_bindings(batch_date=resolved, roots=website_roots)
        weekly_roots = self._read_weekly_social_roots(resolved)
        weekly_root_slugs = [
            str(root.get("root_topic_id") or root.get("parent_slug") or root.get("slug") or "")
            for root in website_roots
            if str(root.get("root_topic_id") or root.get("parent_slug") or root.get("slug") or "")
        ]
        if not website_roots:
            weekly_root_slugs = [
                str(slug) for slug in weekly_roots.get("root_slugs", []) if str(slug)
            ]
        selected_slugs = {item["slug"] for item in ranking if item.get("selected")}
        selection_policy = "latest_live_http_200_default_two"
        root_live_rows = [row for row in live_rows if str(row.get("slug") or "") in root_bindings]
        if slugs:
            wanted = {slug.strip() for slug in slugs if slug.strip()}
            explicit_pool = root_live_rows if website_roots else live_rows
            selected = [row for row in explicit_pool if row["slug"] in wanted]
            selection_policy = "explicit_slug_selection"
        elif website_roots:
            selected = []
            for root in website_roots[: max(count, 0)]:
                root_id = str(root.get("root_topic_id") or root.get("parent_slug") or root.get("slug") or "")
                candidates = [
                    row for row in root_live_rows
                    if str(root_bindings.get(str(row.get("slug") or ""), {}).get("root_topic_id") or "") == root_id
                ]
                if candidates:
                    selected.append(candidates[-1])
            selection_policy = "website_weekly_root_manifest"
            weekly_roots = {
                "schema_version": 2,
                "social_week_start": _week_start(resolved),
                "root_slugs": weekly_root_slugs,
                "source_batch_date": source_batch,
                "selection_policy": selection_policy,
                "selection_count": len(weekly_root_slugs),
                "content_origin": "WEBSITE_ROOT_BASED",
            }
            _write_json(self._weekly_social_roots_path(_week_start(resolved)), weekly_roots)
        elif weekly_root_slugs:
            selected = [
                row
                for row in (
                    self._live_row_for_weekly_root(slug, source_batch, live_by_slug)
                    for slug in weekly_root_slugs[: max(count, 0)]
                )
                if row is not None
            ]
            selection_policy = "weekly_social_root_reuse"
        else:
            selected = [row for row in live_rows if row["slug"] in selected_slugs][: max(count, 0)]
        if not selected:
            raise RuntimeError("No live HTTP 200 website articles are available for social draft preparation.")
        if not slugs and not weekly_root_slugs and _looks_like_iso_date(resolved):
            weekly_roots = self._write_weekly_social_roots(batch_date=resolved, ranking=ranking, selected=selected)
            weekly_root_slugs = [str(slug) for slug in weekly_roots.get("root_slugs", []) if str(slug)]
            selection_policy = "monday_or_first_social_root_selection"
        for item in ranking:
            item["selected"] = str(item.get("slug") or "") in {str(row.get("slug") or "") for row in selected}

        _write_json(self.draft_root / resolved / "ranking.json", {"batch_date": resolved, "items": ranking})
        manifest_items: list[dict[str, Any]] = []
        for row in selected:
            article = self.article_from_live_row(row)
            provenance = self._source_binding(
                article.article_id,
                root_bindings.get(article.article_id, {}),
            )
            asset_manifest = self.generate_social_assets(article, batch_date=resolved)
            asset_outputs = asset_manifest.get("outputs", {}) if isinstance(asset_manifest, dict) else {}
            series_context = {
                "social_week_start": _week_start(resolved) if _looks_like_iso_date(resolved) else "",
                "root_slugs": weekly_root_slugs or [str(row.get("slug") or "") for row in selected],
                "selection_policy": selection_policy,
                "source_batch_date": str(weekly_roots.get("source_batch_date") or resolved) if isinstance(weekly_roots, dict) else resolved,
                "next_post_teaser_required": True,
                "advanced_daily_angle_required": selection_policy == "weekly_social_root_reuse",
            }
            package = self.source_package(
                article,
                batch_date=resolved,
                platforms=platform_list,
                social_series=series_context,
                provenance=provenance,
            )
            article_dir = self.draft_root / resolved / article.article_id
            _write_json(article_dir / "source_package.json", package)
            (article_dir / "CODEX_SOCIAL_WRITING_PROMPT.md").write_text(self.writing_prompt(package), encoding="utf-8")
            for platform in platform_list:
                platform_dir = article_dir / platform
                platform_dir.mkdir(parents=True, exist_ok=True)
                metadata_path = platform_dir / "metadata.json"
                existing_metadata = read_json(metadata_path, {})
                if not isinstance(existing_metadata, dict):
                    existing_metadata = {}
                existing_status = _status_key(existing_metadata.get("status"))
                protected_copy = existing_status in {
                    "approved_for_copy",
                    "pending_manual_publish",
                    "published_manual",
                }
                recent_angles = self._current_cycle_angle_history(
                    batch_date=resolved,
                    root_topic_id=str(provenance.get("root_topic_id") or ""),
                    platform=platform,
                )
                if platform in self.platform_playbooks:
                    native = self.platform_native_engine.generate(
                        package=package,
                        platform=platform,
                        recent_angles=recent_angles,
                    )
                else:
                    legacy_drafts = self._platform_drafts(article, platform)
                    legacy_final = self.platform_native_engine.compose_components(
                        platform=platform,
                        components=legacy_drafts,
                        topic=article.title,
                        url=article.canonical_url or article.url,
                    )
                    native = {
                        "drafts": legacy_drafts,
                        "components": legacy_drafts,
                        "content_model": "COMPLEMENTARY_COMPONENTS_V1",
                        "today_social_angle": str(provenance.get("today_social_angle") or provenance.get("social_angle") or "source_article_adaptation"),
                        "final_post": legacy_final["text"],
                        "final_title": legacy_final["title"],
                        "final_metadata": {
                            **legacy_final,
                            "component_inputs": ["A.md", "B.md", "C.md"],
                            "evidence_refs": [],
                            "new_claims": [],
                        },
                        "variant_titles": {
                            name: f"{article.title} - Variant {name[0]}" for name in legacy_drafts
                        },
                        "variant_metadata": {
                            name: {
                                "variant_strategy": strategy,
                                "social_angle": str(provenance.get("social_angle") or "source_article_adaptation"),
                                "character_count": len(text.strip()),
                                "platform_limit": None,
                                "within_limit": True,
                                "platform_validation_status": "PASS",
                                "evidence_refs": [],
                            }
                            for (name, strategy), text in zip(
                                (
                                    ("A.md", "ACTIONABLE"),
                                    ("B.md", "INSIGHT"),
                                    ("C.md", "PROBLEM_SOLUTION"),
                                ),
                                legacy_drafts.values(),
                            )
                        },
                        "playbook": {"structure": "legacy-compatible"},
                        "evidence_refs": [],
                        "new_claims": [],
                        "visual": {
                            "visual_recommended": False,
                            "visual_type": "NO_VISUAL",
                            "visual_concept": "",
                            "visual_source": "NO_VISUAL",
                            "visual_alt_text": "",
                        },
                    }
                legacy_variant_model = bool(existing_metadata) and not existing_metadata.get("content_model")
                if legacy_variant_model and not protected_copy:
                    existing_components = {
                        name: (platform_dir / name).read_text(encoding="utf-8")
                        for name in ("A.md", "B.md", "C.md")
                        if (platform_dir / name).is_file()
                    }
                    if len(existing_components) == 3:
                        legacy_final = self.platform_native_engine.compose_components(
                            platform=platform,
                            components=existing_components,
                            topic=article.title,
                            url=article.canonical_url or article.url,
                            evidence_refs=native.get("evidence_refs") or [],
                        )
                        native["final_post"] = legacy_final["text"]
                        native["final_title"] = legacy_final["title"]
                        native["final_metadata"] = {
                            **legacy_final,
                            "component_inputs": ["A.md", "B.md", "C.md"],
                            "evidence_refs": list(native.get("evidence_refs") or []),
                            "new_claims": [],
                            "legacy_components_recomposed": True,
                        }
                if not protected_copy:
                    if not legacy_variant_model:
                        for filename, content in native["drafts"].items():
                            (platform_dir / filename).write_text(str(content), encoding="utf-8", newline="\n")
                    (platform_dir / "FINAL.md").write_text(
                        str(native["final_post"]), encoding="utf-8", newline="\n"
                    )
                protected = {
                    key: existing_metadata[key]
                    for key in (
                        "status",
                        "status_label",
                        "approved_for_copy",
                        "reviewer_notes",
                        "final_published_url",
                        "published_url",
                        "published_at",
                        "publish_method",
                        "published_by",
                        "history",
                    )
                    if key in existing_metadata
                }
                _write_json(
                    metadata_path,
                    {
                        "status": existing_status if protected_copy else "needs_social_review",
                        "selected_variant": (
                            str(existing_metadata.get("selected_variant") or "A.md")
                            if protected_copy and legacy_variant_model
                            else "FINAL.md"
                        ),
                        "article_slug": article.article_id,
                        "platform": platform,
                        **provenance,
                        "content_origin": "WEBSITE_ROOT_BASED",
                        "social_mode": "SOURCE_BASED_SOCIAL",
                        "claim_verification_contract": "NEW_CLAIMS_REQUIRE_SUPPLIED_EVIDENCE",
                        "website_url": article.url,
                        "image_url": article.image,
                        "local_image_path": str(asset_outputs.get(_safe_asset_name(platform), {}).get("local_path") or asset_outputs.get("og", {}).get("local_path") or ""),
                        "asset_manifest": str(article_dir / "assets" / "manifest.json"),
                        "title": article.title,
                        "variant_titles": native["variant_titles"],
                        "variant_metadata": native["variant_metadata"],
                        "content_model": (
                            "LEGACY_VARIANTS_NEEDS_RECOMPOSE"
                            if protected_copy and legacy_variant_model
                            else "COMPLEMENTARY_COMPONENTS_V1"
                        ),
                        "today_social_angle": str(native.get("today_social_angle") or provenance.get("today_social_angle") or provenance.get("social_angle") or "source_article_adaptation"),
                        "final_post_file": "FINAL.md",
                        "final_title": str(native.get("final_title") or article.title),
                        "final_metadata": dict(native.get("final_metadata") or {}),
                        "legacy_variant_model": bool(protected_copy and legacy_variant_model),
                        "recompose_status": (
                            "NEEDS_RECOMPOSE"
                            if protected_copy and legacy_variant_model
                            else "COMPOSED"
                        ),
                        "platform_playbook": native["playbook"],
                        "platform_native_contract": True,
                        "evidence_refs": native["evidence_refs"],
                        "new_claims": native["new_claims"],
                        **native["visual"],
                        "x_max_characters": X_MAX_CHARACTERS if platform == "x" else None,
                        "x_thread_enabled": False if platform == "x" else None,
                        "social_value_requirements": dict(
                            existing_metadata.get("social_value_requirements") or {"enabled": False}
                        ),
                        "source_render_required": (
                            False
                            if platform == "x"
                            else bool(existing_metadata.get("source_render_required", False))
                        ),
                        "hashtags": self._hashtags(article, platform),
                        "reusable_excerpts": self._reusable_excerpts(article),
                        **protected,
                    },
                )
            manifest_items.append(
                {
                    "slug": article.article_id,
                    "title": article.title,
                    "url": article.url,
                    "status": "writing_package_ready",
                    "platforms": platform_list,
                    "source_package": str(article_dir / "source_package.json"),
                    "prompt": str(article_dir / "CODEX_SOCIAL_WRITING_PROMPT.md"),
                    **provenance,
                }
            )

        manifest = {
            "schema_version": 1,
            "batch_date": resolved,
            "status": "social_writing_package_ready",
            "selection_policy": selection_policy,
            "content_origin": "WEBSITE_ROOT_BASED",
            "social_mode": "SOURCE_BASED_SOCIAL",
            "social_week_start": _week_start(resolved) if _looks_like_iso_date(resolved) else "",
            "weekly_root_slugs": weekly_root_slugs or [item["slug"] for item in manifest_items],
            "series_rule": "Reuse the same weekly social root slugs after the first weekly selection; write distinct advanced angles and include next-post teasers.",
            "selected_count": len(manifest_items),
            "hot_queue_count": len(preserved_hot_items),
            "available_live_count": len(live_rows),
            "unrelated_historical_tasks_loaded": 0,
            "items": [*manifest_items, *preserved_hot_items],
        }
        _write_json(self.draft_root / resolved / "manifest.json", manifest)
        return manifest

    def normalize_source_bindings(self, *, batch_date: str = "latest") -> dict[str, Any]:
        """Bind existing normal-social drafts to canonical Website roots without rewriting copy."""
        resolved = self.resolve_latest_social_batch(batch_date)
        roots = self._website_weekly_roots(resolved)
        bindings = self._website_root_bindings(batch_date=resolved, roots=roots)
        manifest_path = self.draft_root / resolved / "manifest.json"
        manifest = read_json(manifest_path, {})
        items = manifest.get("items") if isinstance(manifest, dict) else []
        if not isinstance(items, list):
            items = []
        bound = 0
        skipped_hot = 0
        for item in items:
            if not isinstance(item, dict):
                continue
            if str(item.get("content_lane") or "") == SOCIAL_HOT_UNCONFIRMED:
                skipped_hot += 1
                continue
            slug = str(item.get("slug") or "")
            context = bindings.get(slug)
            if not context:
                continue
            provenance = self._source_binding(slug, context)
            item.update(provenance)
            item["content_origin"] = "WEBSITE_ROOT_BASED"
            item["social_mode"] = "SOURCE_BASED_SOCIAL"
            package_path = self.draft_root / resolved / slug / "source_package.json"
            package = read_json(package_path, {})
            if isinstance(package, dict):
                package["content_origin"] = "WEBSITE_ROOT_BASED"
                package["social_mode"] = "SOURCE_BASED_SOCIAL"
                package["provenance"] = provenance
                _write_json(package_path, package)
            for metadata_path in (self.draft_root / resolved / slug).glob("*/metadata.json"):
                metadata = read_json(metadata_path, {})
                if not isinstance(metadata, dict):
                    continue
                selected = str(metadata.get("selected_variant") or "A.md")
                if not (metadata_path.parent / selected).is_file():
                    continue
                metadata.update(provenance)
                metadata["content_origin"] = "WEBSITE_ROOT_BASED"
                metadata["social_mode"] = "SOURCE_BASED_SOCIAL"
                metadata["claim_verification_contract"] = "NEW_CLAIMS_REQUIRE_SUPPLIED_EVIDENCE"
                _write_json(metadata_path, metadata)
            bound += 1
        root_ids = [
            str(root.get("root_topic_id") or root.get("parent_slug") or root.get("slug") or "")
            for root in roots
            if str(root.get("root_topic_id") or root.get("parent_slug") or root.get("slug") or "")
        ]
        manifest["content_origin"] = "WEBSITE_ROOT_BASED"
        manifest["social_mode"] = "SOURCE_BASED_SOCIAL"
        manifest["selection_policy"] = "website_weekly_root_manifest"
        manifest["social_week_start"] = _week_start(resolved)
        manifest["weekly_root_slugs"] = root_ids
        manifest["unrelated_historical_tasks_loaded"] = 0
        _write_json(manifest_path, manifest)
        if roots:
            _write_json(
                self._weekly_social_roots_path(_week_start(resolved)),
                {
                    "schema_version": 2,
                    "social_week_start": _week_start(resolved),
                    "root_slugs": root_ids,
                    "source_batch_date": resolved,
                    "selection_policy": "website_weekly_root_manifest",
                    "selection_count": len(root_ids),
                    "content_origin": "WEBSITE_ROOT_BASED",
                },
            )
        return {
            "batch_date": resolved,
            "website_root_count": len(root_ids),
            "bound_social_items": bound,
            "hot_news_items_unchanged": skipped_hot,
            "historical_tasks_loaded": 0,
        }

    def regenerate_structured_platform_drafts(
        self,
        *,
        batch_date: str = "latest",
        platforms: list[str] | None = None,
    ) -> dict[str, Any]:
        resolved = self.resolve_latest_social_batch(batch_date)
        selected_platforms = set(platforms or ["blogger", "bluesky"])
        manifest = read_json(self.draft_root / resolved / "manifest.json", {})
        items = manifest.get("items") if isinstance(manifest, dict) else []
        if not isinstance(items, list):
            raise RuntimeError(f"No social manifest items found for {resolved}")
        results: list[dict[str, Any]] = []
        for item in items:
            slug = str(item.get("slug") or "")
            if not slug:
                continue
            article = self.article_from_live_row(
                {
                    "slug": slug,
                    "title": str(item.get("title") or slug),
                    "url": str(item.get("url") or f"https://smileaireviewhub.com/{slug}/"),
                    "batch_date": resolved,
                }
            )
            asset_manifest = self.generate_social_assets(article, batch_date=resolved)
            outputs = asset_manifest.get("outputs", {}) if isinstance(asset_manifest, dict) else {}
            for platform in selected_platforms:
                if platform not in {"blogger", "bluesky"}:
                    continue
                platform_dir = self.draft_root / resolved / slug / platform
                platform_dir.mkdir(parents=True, exist_ok=True)
                metadata_path = platform_dir / "metadata.json"
                existing = read_json(metadata_path, {})
                if not isinstance(existing, dict):
                    existing = {}
                if _status_key(existing.get("status")) == "published_manual":
                    results.append(
                        {
                            "slug": slug,
                            "platform": platform,
                            "metadata_path": str(metadata_path),
                            "status": "published_manual",
                            "warnings": ["PUBLISHED_HISTORY_NOT_RECOMPOSED"],
                            "word_count": existing.get("blogger_word_count"),
                            "character_count": existing.get("character_count"),
                        }
                    )
                    continue
                asset_info = outputs.get(_safe_asset_name(platform), {}) if isinstance(outputs, dict) else {}
                platform_image_path = str(asset_info.get("local_path") or existing.get("local_image_path") or "")
                protected = {
                    key: existing[key]
                    for key in (
                        "status",
                        "status_label",
                        "approved_for_copy",
                        "reviewer_notes",
                        "final_published_url",
                        "published_url",
                        "published_at",
                        "publish_method",
                        "published_by",
                        "history",
                        "created_at",
                    )
                    if key in existing
                }
                if platform == "blogger":
                    fields = _blogger_article_fields(article, platform_image_path=platform_image_path, existing=existing)
                    preview = "\n\n".join(
                        [
                            f"# {fields['title']}",
                            f"Search description: {fields['search_description']}",
                            f"Labels: {', '.join(fields['labels'])}",
                            f"Recommended permalink slug: {fields['recommended_permalink_slug']}",
                            fields["plain_text_body"],
                        ]
                    ).strip() + "\n"
                    (platform_dir / "A.md").write_text(preview, encoding="utf-8")
                    (platform_dir / "FINAL.md").write_text(preview, encoding="utf-8")
                    (platform_dir / "article.html").write_text(str(fields["html_body"]).strip() + "\n", encoding="utf-8")
                    metadata = {
                        **existing,
                        **fields,
                        **protected,
                        "selected_variant": "FINAL.md",
                        "content_model": "COMPLEMENTARY_COMPONENTS_V1",
                        "final_post_file": "FINAL.md",
                        "final_title": fields["title"],
                        "final_metadata": {
                            "title": fields["title"],
                            "text": preview,
                            "character_count": len(preview.strip()),
                            "within_limit": True,
                            "component_inputs": ["A.md", "B.md", "C.md"],
                            "evidence_refs": list(existing.get("evidence_refs") or []),
                            "new_claims": [],
                            "claim_guard": "SOURCE_AND_COMPONENT_KNOWLEDGE_ONLY",
                        },
                        "recompose_status": "COMPOSED",
                        "article_slug": slug,
                        "platform": platform,
                        "platform_label": _platform_label(platform),
                        "website_url": article.url,
                        "source_url": article.url,
                        "canonical_url": article.canonical_url or article.url,
                        "image_url": article.image,
                        "local_image_path": platform_image_path,
                        "asset_manifest": str(self.draft_root / resolved / slug / "assets" / "manifest.json"),
                        "hashtags": self._hashtags(article, platform),
                        "CTA": "Read the full source article",
                        "cta": "Read the full source article",
                        "updated_at": now_iso(),
                    }
                else:
                    fields = _bluesky_fields(article, platform_image_path=platform_image_path, existing=existing)
                    thread_lines: list[str] = []
                    for index, post in enumerate(fields["thread_posts"], start=1):
                        thread_lines.append(f"Thread post {index}\n{post}")
                    preview = "\n\n".join(["# Bluesky draft", "Standalone post", fields["standalone_post"], *thread_lines]).strip() + "\n"
                    (platform_dir / "A.md").write_text(preview, encoding="utf-8")
                    (platform_dir / "FINAL.md").write_text(preview, encoding="utf-8")
                    metadata = {
                        **existing,
                        **fields,
                        **protected,
                        "selected_variant": "FINAL.md",
                        "content_model": "COMPLEMENTARY_COMPONENTS_V1",
                        "final_post_file": "FINAL.md",
                        "final_title": article.title,
                        "final_metadata": {
                            "title": article.title,
                            "text": preview,
                            "character_count": len(preview.strip()),
                            "within_limit": True,
                            "component_inputs": ["A.md", "B.md", "C.md"],
                            "evidence_refs": list(existing.get("evidence_refs") or []),
                            "new_claims": [],
                            "claim_guard": "SOURCE_AND_COMPONENT_KNOWLEDGE_ONLY",
                        },
                        "recompose_status": "COMPOSED",
                        "article_slug": slug,
                        "platform": platform,
                        "platform_label": _platform_label(platform),
                        "title": article.title,
                        "website_url": article.url,
                        "source_url": article.url,
                        "canonical_url": article.canonical_url or article.url,
                        "image_url": article.image,
                        "local_image_path": platform_image_path,
                        "asset_manifest": str(self.draft_root / resolved / slug / "assets" / "manifest.json"),
                        "CTA": "Read the guide",
                        "cta": "Read the guide",
                        "updated_at": now_iso(),
                    }
                if not metadata.get("status"):
                    metadata["status"] = "needs_social_review"
                metadata["status_label"] = _status_label(metadata.get("status"))
                if not metadata.get("created_at"):
                    metadata["created_at"] = metadata["updated_at"]
                _write_json(metadata_path, metadata)
                results.append(
                    {
                        "slug": slug,
                        "platform": platform,
                        "metadata_path": str(metadata_path),
                        "status": metadata.get("status"),
                        "warnings": metadata.get("validation_warnings") or [],
                        "word_count": metadata.get("blogger_word_count"),
                        "character_count": metadata.get("character_count"),
                    }
                )
        return {"batch_date": resolved, "items": results}

    def _event_log_path(self, batch_date: str) -> Path:
        return self.draft_root / batch_date / "review_events.jsonl"

    def _log_event(
        self,
        *,
        batch_date: str,
        slug: str,
        platform: str,
        action: str,
        previous_status: str = "",
        new_status: str = "",
        reviewer_notes: str = "",
        details: dict[str, Any] | None = None,
    ) -> None:
        path = self._event_log_path(batch_date)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "timestamp": now_iso(),
            "date": batch_date,
            "slug": slug,
            "platform": platform,
            "action": action,
            "previous_status": previous_status,
            "new_status": new_status,
            "reviewer_notes": reviewer_notes,
            "details": details or {},
        }
        with path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
        try:
            from modules.observation_hooks import observe_social_event_best_effort

            observe_social_event_best_effort(
                root=self.root,
                batch_date=batch_date,
                slug=slug,
                platform=platform,
                action=action,
                previous_status=previous_status,
                new_status=new_status,
            )
        except Exception:
            # Observation is a camera: its import/runtime failure cannot change
            # the already-completed production event or caller behavior.
            pass

    def _metadata_path(self, batch_date: str, slug: str, platform: str) -> Path:
        return self.draft_root / batch_date / slug / platform / "metadata.json"

    def _draft_path(self, batch_date: str, slug: str, platform: str, metadata: dict[str, Any]) -> Path:
        selected = str(metadata.get("selected_variant") or "A.md")
        if selected not in {"FINAL.md", "A.md", "B.md", "C.md"}:
            selected = "A.md"
        return self.draft_root / batch_date / slug / platform / selected

    def platform_payload(self, *, batch_date: str, slug: str, platform: str) -> dict[str, Any]:
        resolved = self.resolve_latest_social_batch(batch_date)
        manifest = read_json(self.draft_root / resolved / "manifest.json", {})
        manifest_items = (manifest.get("items") or []) if isinstance(manifest, dict) else []
        item = next((entry for entry in manifest_items if isinstance(entry, dict) and entry.get("slug") == slug), {})
        metadata_path = self._metadata_path(resolved, slug, platform)
        metadata = read_json(metadata_path, {})
        if not isinstance(metadata, dict):
            metadata = {}
        draft_path = self._draft_path(resolved, slug, platform, metadata)
        body = draft_path.read_text(encoding="utf-8") if draft_path.exists() else ""
        tags = metadata.get("hashtags", metadata.get("tags", []))
        selected_variant = (
            draft_path.name
            if draft_path.name in {"FINAL.md", "A.md", "B.md", "C.md"}
            else "A.md"
        )
        variant_metadata = metadata.get("variant_metadata") if isinstance(metadata.get("variant_metadata"), dict) else {}
        variants: list[dict[str, Any]] = []
        for variant_name in ("A.md", "B.md", "C.md"):
            variant_path = draft_path.parent / variant_name
            variant_text = variant_path.read_text(encoding="utf-8") if variant_path.is_file() else ""
            variant_info = dict(variant_metadata.get(variant_name) or {})
            count = len(variant_text.strip())
            limit = X_MAX_CHARACTERS if platform == "x" else variant_info.get("platform_limit")
            within_limit = count <= X_MAX_CHARACTERS if platform == "x" else True
            variants.append(
                {
                    "filename": variant_name,
                    "label": variant_name.removesuffix(".md"),
                    "text": variant_text,
                    "title": str((metadata.get("variant_titles") or {}).get(variant_name) or ""),
                    "variant_strategy": str(variant_info.get("variant_strategy") or ""),
                    "social_angle": str(variant_info.get("social_angle") or ""),
                    "character_count": count,
                    "platform_limit": limit,
                    "within_limit": within_limit,
                    "platform_validation_status": "PASS" if within_limit else "INVALID_PLATFORM_LIMIT",
                    "evidence_refs": list(variant_info.get("evidence_refs") or metadata.get("evidence_refs") or []),
                    "new_claims": list(metadata.get("new_claims") or []),
                    "selected": False,
                }
            )
        variant_titles = metadata.get("variant_titles") if isinstance(metadata.get("variant_titles"), dict) else {}
        selected_variant_title = str(
            metadata.get("final_title")
            if selected_variant == "FINAL.md"
            else variant_titles.get(selected_variant)
            or ""
        ).strip()
        title = str(
            selected_variant_title
            or metadata.get("title")
            or item.get("title")
            or metadata.get("source_title")
            or slug
        )
        source_url = str(
            metadata.get("source_url")
            or metadata.get("website_url")
            or item.get("url")
            or metadata.get("canonical_url")
            or ""
        )
        source_name = official_source_name(
            str(metadata.get("official_source_url") or source_url),
            str(metadata.get("official_source_name") or metadata.get("source_name") or ""),
        )
        canonical = str(metadata.get("canonical_url") or source_url)
        language = str(metadata.get("language") or ("vi" if platform.endswith("_vi") else "en"))
        cta = str(metadata.get("CTA") or metadata.get("cta") or "")
        warnings = metadata.get("validation_warnings") or metadata.get("warnings") or []
        if isinstance(warnings, str):
            warnings = [warnings] if warnings else []
        content_lane = str(metadata.get("content_lane") or item.get("content_lane") or "")
        website_url = "" if content_lane == SOCIAL_HOT_UNCONFIRMED else str(metadata.get("website_url") or item.get("url") or source_url)
        if platform == "facebook_vi" and has_vietnamese_mojibake(f"{title}\n{body}\n{cta}"):
            warnings = _append_unique_warning(warnings, vietnamese_mojibake_warning())
        local_image_path = str(metadata.get("local_image_path") or "")
        asset_manifest_path = self.draft_root / resolved / slug / "assets" / "manifest.json"
        asset_manifest = read_json(asset_manifest_path, {})
        if not local_image_path or (not asset_manifest.get("source_image") and (metadata.get("image_url") or metadata.get("image"))):
            article = PublishedArticle(
                article_id=slug,
                title=str(metadata.get("source_title") or title),
                url=source_url or f"https://smileaireviewhub.com/{slug}/",
                description="",
                image=str(metadata.get("image_url") or metadata.get("image") or ""),
                tags=tags if isinstance(tags, list) else _split_tags(tags),
                publish_date="",
                canonical_url=canonical,
                affiliate_disclosure=str(metadata.get("affiliate_disclosure") or ""),
            )
            asset_manifest = self.generate_social_assets(article, batch_date=resolved, force=not bool(asset_manifest.get("source_image")))
            outputs = asset_manifest.get("outputs", {}) if isinstance(asset_manifest, dict) else {}
            local_image_path = str(outputs.get("og", {}).get("local_path") or local_image_path)
        asset_outputs = asset_manifest.get("outputs") if isinstance(asset_manifest, dict) else {}
        asset_name = _safe_asset_name(platform)
        asset_info = asset_outputs.get(asset_name, {}) if isinstance(asset_outputs, dict) else {}
        if not asset_info and isinstance(asset_outputs, dict):
            asset_info = asset_outputs.get("og", {})
        platform_image_path = str(asset_info.get("local_path") or local_image_path)
        pinterest_fields: dict[str, Any] = {}
        blogger_fields: dict[str, Any] = {}
        bluesky_fields: dict[str, Any] = {}
        if platform == "pinterest":
            pinterest_metadata = dict(metadata)
            has_inline_pin_title = bool(re.search(r"(?im)^\s*pin title\s*:", body))
            if selected_variant_title and not has_inline_pin_title:
                pinterest_metadata["pin_title"] = selected_variant_title
                pinterest_metadata["overlay_text"] = selected_variant_title
                pinterest_metadata["alt_text"] = f"Pinterest graphic for {selected_variant_title}."
            pinterest_fields = _pinterest_fields_from_metadata(
                metadata=pinterest_metadata,
                body=body,
                title=title,
                source_url=source_url,
                platform_image_path=platform_image_path,
            )
            changed = False
            for key, value in pinterest_fields.items():
                if metadata.get(key) != value:
                    metadata[key] = value
                    changed = True
            if metadata.get("body") != pinterest_fields["pin_description"]:
                metadata["body"] = pinterest_fields["pin_description"]
                changed = True
            if changed:
                metadata["updated_at"] = now_iso()
                _write_json(metadata_path, metadata)
            body = pinterest_fields["pin_description"]
            title = pinterest_fields["pin_title"]
        elif platform == "blogger":
            blogger_fields = {
                "blogger_title": str(title if selected_variant_title else metadata.get("blogger_title") or title),
                "seo_title": str(title if selected_variant_title else metadata.get("seo_title") or title),
                "h1": str(title if selected_variant_title else metadata.get("h1") or title),
                "html_body": str(metadata.get("html_body") or ""),
                "plain_text_body": str(metadata.get("plain_text_body") or metadata.get("body") or body),
                "labels": metadata.get("labels") if isinstance(metadata.get("labels"), list) else _split_tags(metadata.get("labels")),
                "search_description": str(metadata.get("search_description") or ""),
                "source_article_url": str(metadata.get("source_article_url") or source_url),
                "recommended_permalink_slug": str(metadata.get("recommended_permalink_slug") or _slugify(title)),
                "json_ld": metadata.get("json_ld") if isinstance(metadata.get("json_ld"), dict) else {},
                "seo_score": int(metadata.get("seo_score") or 0),
                "estimated_reading_time_minutes": int(metadata.get("estimated_reading_time_minutes") or 0),
                "heading_count": int(metadata.get("heading_count") or 0),
                "faq_count": int(metadata.get("faq_count") or 0),
                "internal_link_count": int(metadata.get("internal_link_count") or 0),
                "external_link_count": int(metadata.get("external_link_count") or 0),
                "json_ld_status": str(metadata.get("json_ld_status") or ""),
                "open_graph_title": str(metadata.get("open_graph_title") or ""),
                "open_graph_description": str(metadata.get("open_graph_description") or ""),
                "twitter_card_description": str(metadata.get("twitter_card_description") or ""),
                "image_caption": str(metadata.get("image_caption") or ""),
                "recommended_image_filename": str(metadata.get("recommended_image_filename") or ""),
                "disclosure": str(metadata.get("disclosure") or metadata.get("affiliate_disclosure") or ""),
                "image_path": str(metadata.get("image_path") or platform_image_path),
                "image_alt_text": str(metadata.get("image_alt_text") or f"Social card for {title}."),
                "blogger_word_count": int(metadata.get("blogger_word_count") or _word_count(str(metadata.get("plain_text_body") or ""))),
            }
            body = blogger_fields["plain_text_body"]
            title = blogger_fields["blogger_title"]
        elif platform == "bluesky":
            thread_posts = metadata.get("thread_posts") if isinstance(metadata.get("thread_posts"), list) else []
            character_counts = metadata.get("character_counts") if isinstance(metadata.get("character_counts"), dict) else {}
            bluesky_fields = {
                "standalone_post": str(metadata.get("standalone_post") or metadata.get("body") or body),
                "thread_posts": [str(post) for post in thread_posts],
                "article_url": str(metadata.get("article_url") or source_url),
                "image_path": str(metadata.get("image_path") or platform_image_path),
                "image_alt_text": str(metadata.get("image_alt_text") or f"Social card for {title}."),
                "character_counts": character_counts,
                "bluesky_character_limit": BLUESKY_CHARACTER_LIMIT,
            }
            body = bluesky_fields["standalone_post"]
        strict_social_value = bool((metadata.get("social_value_requirements") or {}).get("enabled")) or content_lane in {
            "SOCIAL_HOT_DRAFT",
            "SOCIAL_HOT_UNCONFIRMED",
        }
        social_value_validation = (
            validate_social_value(
                body,
                platform=platform,
                official_source_name_value=source_name,
                official_source_url=str(metadata.get("official_source_url") or source_url),
                source_render_required=bool(metadata.get("source_render_required", bool(source_url))),
                scheduled_followup_exists=bool(metadata.get("scheduled_followup_exists")),
                title=title,
                story_title=str(metadata.get("source_title") or item.get("title") or ""),
                hashtags=tags if isinstance(tags, list) else _split_tags(tags),
                verified_pricing=bool(metadata.get("verified_pricing")),
                affiliate_claims_supported=bool(metadata.get("affiliate_claims_supported")),
            )
            if strict_social_value
            else dict(metadata.get("social_value_validation") or {})
        )
        pinterest_visual_validation: dict[str, Any] = {}
        if platform == "pinterest":
            pinterest_visual_validation = dict(asset_info.get("visual_validation") or {})
            if not pinterest_visual_validation:
                visual_points = [
                    str(point).strip()
                    for point in metadata.get("pinterest_visual_points") or []
                    if str(point).strip()
                ]
                verified_visual_facts = [
                    str(point).strip()
                    for point in metadata.get("pinterest_visual_facts") or []
                    if str(point).strip()
                ]
                pinterest_visual_validation = validate_pinterest_visual(
                    headline=str(pinterest_fields.get("overlay_text") or title),
                    subhead=str(metadata.get("pinterest_visual_subhead") or ""),
                    points=visual_points,
                    source_name=source_name,
                    verified_facts=verified_visual_facts,
                    empty_area_ratio=0.35 if len(visual_points) >= 2 else 0.8,
                )
        social_value_reasons = list(social_value_validation.get("reasons") or [])
        if metadata.get("platform_native_contract"):
            hard_prefixes = (
                "UNSUPPORTED_",
                "FAKE_URGENCY_",
                "STALE_RELATIVE_DATE_",
                "X_CHARACTER_LIMIT_",
            )
            approval_reasons = [
                reason for reason in social_value_reasons
                if str(reason).startswith(hard_prefixes)
            ]
        else:
            approval_reasons = social_value_reasons
        final_metadata = (
            dict(metadata.get("final_metadata") or {})
            if isinstance(metadata.get("final_metadata"), dict)
            else {}
        )
        selected_variant_payload = (
            final_metadata
            if selected_variant == "FINAL.md"
            else next((row for row in variants if row["filename"] == selected_variant), {})
        )
        legacy_variant_model = selected_variant != "FINAL.md" or not draft_path.is_file()
        if legacy_variant_model and str(metadata.get("content_origin") or "") != "HOT_NEWS":
            approval_reasons.append("NEEDS_RECOMPOSE")
        if platform == "x" and not selected_variant_payload.get("within_limit", False):
            approval_reasons.append("INVALID_PLATFORM_LIMIT")
        if list(metadata.get("new_claims") or []):
            unsupported_new_claims = [
                row for row in list(metadata.get("new_claims") or [])
                if not isinstance(row, dict) or not (row.get("claim_id") or row.get("evidence_url"))
            ]
            if unsupported_new_claims:
                approval_reasons.append("NEW_UNSUPPORTED_FACTUAL_CLAIM")
        if platform == "pinterest" and pinterest_visual_validation.get("status") == "BLOCKED":
            approval_reasons.extend(pinterest_visual_validation.get("reasons") or [])
        approval_blocked = bool(approval_reasons) or bool(
            platform == "pinterest" and pinterest_visual_validation.get("status") == "BLOCKED"
        )
        if strict_social_value and metadata.get("social_value_validation") != social_value_validation:
            metadata["official_source_name"] = source_name
            metadata["official_source_url"] = str(metadata.get("official_source_url") or source_url)
            metadata["social_value_validation"] = social_value_validation
            metadata["approval_blocked"] = approval_blocked
            metadata["approval_block_reasons"] = list(dict.fromkeys(approval_reasons))
            metadata["updated_at"] = now_iso()
            _write_json(metadata_path, metadata)
        raw_status = _status_key(metadata.get("status"))
        display_status = "revision_requested" if approval_blocked and raw_status == "approved_for_copy" else raw_status
        display_status_label = (
            "Source Rendering Required"
            if approval_blocked and "SOURCE_RENDERING_REQUIRED" in approval_reasons
            else "Social Rewrite Required"
            if approval_blocked and raw_status == "approved_for_copy"
            else _status_label(raw_status)
        )
        return {
            "batch_date": resolved,
            "slug": slug,
            "platform": platform,
            "platform_label": _platform_label(platform),
            "article_title": str(item.get("title") or title),
            "source_title": str(metadata.get("source_title") or title),
            "source_url": source_url,
            "official_source_name": source_name,
            "official_source_url": str(metadata.get("official_source_url") or source_url),
            "source_status": "OFFICIAL" if source_name and source_url else "SOURCE_RENDERING_REQUIRED",
            "website_url": website_url,
            "canonical_url": "" if content_lane == SOCIAL_HOT_UNCONFIRMED else canonical,
            "content_lane": content_lane,
            "workflow": str(metadata.get("workflow") or item.get("workflow") or ""),
            "confirmation_status": str(metadata.get("confirmation_status") or ""),
            "discovery_timestamp": str(metadata.get("discovery_timestamp") or ""),
            "language": language,
            "status": display_status,
            "status_label": display_status_label,
            "title": title,
            "body": body,
            "selected_variant": selected_variant,
            "variants": variants,
            "content_model": str(metadata.get("content_model") or "LEGACY_VARIANTS_NEEDS_RECOMPOSE"),
            "components_read_only": True,
            "legacy_variant_model": legacy_variant_model,
            "recompose_status": "NEEDS_RECOMPOSE" if legacy_variant_model else str(metadata.get("recompose_status") or "COMPOSED"),
            "final_post_file": str(metadata.get("final_post_file") or "FINAL.md"),
            "final_post": body if selected_variant == "FINAL.md" else "",
            "final_metadata": final_metadata,
            "variant_strategy": str(selected_variant_payload.get("variant_strategy") or ""),
            "social_angle": str(metadata.get("today_social_angle") or metadata.get("social_angle") or ""),
            "today_social_angle": str(metadata.get("today_social_angle") or metadata.get("social_angle") or ""),
            "root_topic_id": str(metadata.get("root_topic_id") or item.get("root_topic_id") or ""),
            "root_title": str(metadata.get("root_title") or item.get("root_title") or ""),
            "source_article_slug": str(metadata.get("source_article_slug") or item.get("source_article_slug") or slug),
            "source_revision": str(metadata.get("source_revision_id") or item.get("source_revision_id") or ""),
            "source_content_hash": str(metadata.get("source_content_hash") or item.get("source_content_hash") or ""),
            "evidence_refs": list(metadata.get("evidence_refs") or []),
            "new_claims": list(metadata.get("new_claims") or []),
            "evidence_status": "INHERITED" if metadata.get("evidence_inheritance") else "REVIEW_REQUIRED",
            "new_claim_status": "PASS" if not metadata.get("new_claims") else "EVIDENCE_REQUIRED",
            "visual_recommended": bool(metadata.get("visual_recommended")),
            "visual_type": str(metadata.get("visual_type") or "NO_VISUAL"),
            "visual_concept": str(metadata.get("visual_concept") or ""),
            "visual_source": str(metadata.get("visual_source") or ""),
            "visual_alt_text": str(metadata.get("visual_alt_text") or ""),
            "platform_limit": X_MAX_CHARACTERS if platform == "x" else None,
            "within_platform_limit": bool(selected_variant_payload.get("within_limit", True)),
            "cta": cta,
            "hashtags": tags if isinstance(tags, list) else _split_tags(tags),
            "image_url": str(metadata.get("image_url") or metadata.get("image") or ""),
            "local_image_path": local_image_path,
            "platform_image_path": platform_image_path,
            "platform_image_filename": str(asset_info.get("filename") or ""),
            "platform_image_width": int(asset_info.get("width") or 0),
            "platform_image_height": int(asset_info.get("height") or 0),
            "platform_image_size": int(asset_info.get("file_size") or 0),
            "asset_validation_status": str(asset_info.get("validation_status") or asset_manifest.get("validation_status") or "UNKNOWN"),
            "pinterest_visual_validation": pinterest_visual_validation,
            "social_value_validation": social_value_validation,
            "approval_blocked": approval_blocked,
            "approval_block_reasons": list(dict.fromkeys(approval_reasons)),
            **pinterest_fields,
            **blogger_fields,
            **bluesky_fields,
            "final_published_url": str(metadata.get("final_published_url") or metadata.get("published_url") or ""),
            "published_at": str(metadata.get("published_at") or ""),
            "publish_method": str(metadata.get("publish_method") or ""),
            "published_by": str(metadata.get("published_by") or ""),
            "final_url_validation_status": str(metadata.get("final_url_validation_status") or ""),
            "final_url_validation_message": str(metadata.get("final_url_validation_message") or ""),
            "api_used": bool(metadata.get("api_used", False)),
            "oauth_used": bool(metadata.get("oauth_used", False)),
            "browser_automation_used": bool(metadata.get("browser_automation_used", False)),
            "character_count": int(metadata.get("character_count") or len(body)),
            "affiliate_disclosure": str(metadata.get("affiliate_disclosure") or ""),
            "reviewer_notes": str(metadata.get("reviewer_notes") or ""),
            "created_at": str(metadata.get("created_at") or ""),
            "updated_at": str(metadata.get("updated_at") or ""),
            "validation_warnings": warnings,
            "draft_path": str(draft_path),
            "metadata_path": str(metadata_path),
            "draft_exists": draft_path.exists(),
        }

    def dashboard_payload(self, *, batch_date: str = "latest") -> dict[str, Any]:
        resolved = self.resolve_latest_social_batch(batch_date)
        manifest = read_json(self.draft_root / resolved / "manifest.json", {})
        items = manifest.get("items") if isinstance(manifest, dict) else []
        if not isinstance(items, list):
            items = []
        payload_items: list[dict[str, Any]] = []
        for item in items:
            slug = str(item.get("slug") or "")
            platforms = item.get("platforms") if isinstance(item.get("platforms"), list) else []
            platform_payloads: list[dict[str, Any]] = []
            for platform in platforms:
                platform_payloads.append(self.platform_payload(batch_date=resolved, slug=slug, platform=str(platform)))
            payload_items.append(
                {
                    "slug": slug,
                    "title": str(item.get("title") or slug),
                    "url": str(item.get("url") or ""),
                    "status": str(item.get("status") or ""),
                    "platforms": platform_payloads,
                    "source_package": str(item.get("source_package") or ""),
                    "prompt": str(item.get("prompt") or ""),
                }
            )
        return {
            "batch_date": resolved,
            "requested_date": batch_date,
            "items": payload_items,
            "status_options": SOCIAL_STATUS_LABELS,
            "generated_at": now_iso(),
        }

    def build_review_dashboard(self, *, batch_date: str = "latest") -> Path:
        # External writers use drafts/pending as an ingress queue. Registration is
        # idempotent and never changes approval or publishing state.
        from .external_draft_exchange import ExternalDraftExchange

        import_result = ExternalDraftExchange(root=self.root).import_pending(batch_date=batch_date)
        effective_date = batch_date
        if batch_date == "latest" and (
            import_result.get("imported") or import_result.get("unchanged")
        ):
            effective_date = str(import_result.get("batch_date") or batch_date)
        resolved = self.resolve_latest_social_batch(effective_date)
        payload = self.dashboard_payload(batch_date=resolved)
        data_json = json.dumps(payload, ensure_ascii=False)
        output = self.draft_root / resolved / "review_dashboard.html"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            self.render_review_dashboard_html(payload, data_json=data_json),
            encoding="utf-8",
        )
        return output

    def render_review_dashboard_html(self, payload: dict[str, Any], *, data_json: str | None = None) -> str:
        return render_review_dashboard_html(payload, data_json=data_json)

    def save_platform_draft(
        self,
        *,
        batch_date: str,
        slug: str,
        platform: str,
        title: str,
        body: str,
        cta: str = "",
        hashtags: str | list[str] = "",
        image_url: str = "",
        reviewer_notes: str = "",
    ) -> dict[str, Any]:
        resolved = self.resolve_latest_social_batch(batch_date)
        if platform == "facebook_vi" and has_vietnamese_mojibake(f"{title}\n{body}\n{cta}"):
            raise ValueError(vietnamese_mojibake_warning())
        metadata_path = self._metadata_path(resolved, slug, platform)
        metadata = read_json(metadata_path, {})
        if not isinstance(metadata, dict):
            metadata = {}
        draft_path = self._draft_path(resolved, slug, platform, metadata)
        previous_status = _status_key(metadata.get("status"))
        draft_path.parent.mkdir(parents=True, exist_ok=True)
        draft_path.write_text(body, encoding="utf-8")
        variant_titles = metadata.get("variant_titles") if isinstance(metadata.get("variant_titles"), dict) else {}
        if draft_path.name == "FINAL.md":
            metadata["final_title"] = title
            final_metadata = (
                dict(metadata.get("final_metadata") or {})
                if isinstance(metadata.get("final_metadata"), dict)
                else {}
            )
            final_metadata.update(
                {
                    "title": title,
                    "character_count": len(body.strip()),
                    "within_limit": len(body.strip()) <= X_MAX_CHARACTERS if platform == "x" else True,
                    "max_characters": X_MAX_CHARACTERS if platform == "x" else None,
                }
            )
            metadata["final_metadata"] = final_metadata
        else:
            variant_titles[draft_path.name] = title
        metadata.update(
            {
                "title": title,
                "variant_titles": variant_titles,
                "body": body,
                "CTA": cta,
                "cta": cta,
                "hashtags": _split_tags(hashtags),
                "image_url": image_url,
                "reviewer_notes": reviewer_notes,
                "character_count": len(body),
                "updated_at": now_iso(),
                "status": previous_status,
            }
        )
        if not metadata.get("created_at"):
            metadata["created_at"] = metadata["updated_at"]
        _write_json(metadata_path, metadata)
        self._log_event(
            batch_date=resolved,
            slug=slug,
            platform=platform,
            action="save",
            previous_status=previous_status,
            new_status=previous_status,
            reviewer_notes=reviewer_notes,
        )
        return self.platform_payload(batch_date=resolved, slug=slug, platform=platform)

    def select_platform_variant(
        self,
        *,
        batch_date: str,
        slug: str,
        platform: str,
        variant: str,
        approve: bool = False,
        reviewer_notes: str = "",
    ) -> dict[str, Any]:
        if variant not in {"A.md", "B.md", "C.md"}:
            raise ValueError(f"Unsupported social variant: {variant}")
        resolved = self.resolve_latest_social_batch(batch_date)
        metadata_path = self._metadata_path(resolved, slug, platform)
        metadata = read_json(metadata_path, {})
        if not isinstance(metadata, dict):
            metadata = {}
        if not (metadata_path.parent / variant).is_file():
            raise ValueError(f"Missing social variant file: {variant}")
        if _status_key(metadata.get("status")) == "published_manual":
            raise ValueError("Published Manual cannot change selected variant without explicit reset confirmation.")
        metadata["selected_variant"] = variant
        metadata["updated_at"] = now_iso()
        if reviewer_notes:
            metadata["reviewer_notes"] = reviewer_notes
        _write_json(metadata_path, metadata)
        review = self.platform_payload(batch_date=resolved, slug=slug, platform=platform)
        if approve:
            if review.get("approval_blocked"):
                reasons = ", ".join(review.get("approval_block_reasons") or ["SOCIAL_REVIEW_BLOCKED"])
                raise ValueError(f"Approved for Copy blocked: {reasons}")
            self.set_platform_status(
                batch_date=resolved,
                slug=slug,
                platform=platform,
                status="approved_for_copy",
                reviewer_notes=reviewer_notes,
            )
            review = self.platform_payload(batch_date=resolved, slug=slug, platform=platform)
        return review

    def recompose_final_platform_post(
        self,
        *,
        batch_date: str,
        slug: str,
        platform: str,
        reviewer_notes: str = "",
    ) -> dict[str, Any]:
        """Compose FINAL.md from A/B/C without changing evidence or components."""
        resolved = self.resolve_latest_social_batch(batch_date)
        metadata_path = self._metadata_path(resolved, slug, platform)
        metadata = read_json(metadata_path, {})
        if not isinstance(metadata, dict) or not metadata:
            raise ValueError("Missing social metadata for final composition.")
        if _status_key(metadata.get("status")) == "published_manual":
            raise ValueError("Published Manual content cannot be recomposed.")
        platform_dir = metadata_path.parent
        components = {
            name: (platform_dir / name).read_text(encoding="utf-8")
            for name in ("A.md", "B.md", "C.md")
            if (platform_dir / name).is_file()
        }
        if len(components) != 3:
            raise ValueError("Final composition requires components A.md, B.md, and C.md.")
        composed = self.platform_native_engine.compose_components(
            platform=platform,
            components=components,
            topic=str(metadata.get("source_title") or metadata.get("title") or slug),
            url=str(metadata.get("website_url") or metadata.get("source_url") or ""),
            evidence_refs=list(metadata.get("evidence_refs") or []),
        )
        (platform_dir / "FINAL.md").write_text(
            str(composed["text"]), encoding="utf-8", newline="\n"
        )
        metadata.update(
            {
                "selected_variant": "FINAL.md",
                "content_model": "COMPLEMENTARY_COMPONENTS_V1",
                "final_post_file": "FINAL.md",
                "final_title": str(composed["title"]),
                "final_metadata": {
                    **composed,
                    "component_inputs": ["A.md", "B.md", "C.md"],
                    "evidence_refs": list(metadata.get("evidence_refs") or []),
                    "new_claims": [],
                    "claim_guard": "SOURCE_AND_COMPONENT_KNOWLEDGE_ONLY",
                },
                "legacy_variant_model": False,
                "recompose_status": "COMPOSED",
                "approved_for_copy": False,
                "status": "needs_social_review",
                "updated_at": now_iso(),
            }
        )
        if reviewer_notes:
            metadata["reviewer_notes"] = reviewer_notes
        self._append_metadata_history(
            metadata,
            "final_recomposed",
            {"component_inputs": ["A.md", "B.md", "C.md"]},
        )
        _write_json(metadata_path, metadata)
        return self.platform_payload(
            batch_date=resolved, slug=slug, platform=platform
        )

    def set_platform_status(
        self,
        *,
        batch_date: str,
        slug: str,
        platform: str,
        status: str,
        reviewer_notes: str = "",
    ) -> Path:
        normalized = _status_key(status)
        if normalized not in SOCIAL_DRAFT_STATUSES:
            raise ValueError(f"Unsupported social draft status: {status}")
        resolved = self.resolve_latest_social_batch(batch_date)
        metadata_path = self._metadata_path(resolved, slug, platform)
        metadata = read_json(metadata_path, {})
        if not isinstance(metadata, dict):
            metadata = {}
        previous = _status_key(metadata.get("status"))
        if previous == "published_manual" and normalized != "published_manual":
            raise ValueError("Published Manual cannot be downgraded without explicit reset confirmation.")
        if normalized == "approved_for_copy":
            review = self.platform_payload(batch_date=resolved, slug=slug, platform=platform)
            if review.get("approval_blocked"):
                reasons = ", ".join(review.get("approval_block_reasons") or ["SOCIAL_VALUE_REWRITE_REQUIRED"])
                raise ValueError(f"Approved for Copy blocked: {reasons}")
            metadata = read_json(metadata_path, {})
            if not isinstance(metadata, dict):
                metadata = {}
        metadata["status"] = normalized
        metadata["status_label"] = _status_label(normalized)
        metadata["updated_at"] = now_iso()
        if reviewer_notes:
            metadata["reviewer_notes"] = reviewer_notes
        if normalized == "approved_for_copy":
            metadata["approved_for_copy"] = True
        elif normalized in {"rejected", "revision_requested", "not_recommended"}:
            metadata["approved_for_copy"] = False
        _write_json(metadata_path, metadata)
        self._log_event(
            batch_date=resolved,
            slug=slug,
            platform=platform,
            action="status",
            previous_status=previous,
            new_status=normalized,
            reviewer_notes=str(metadata.get("reviewer_notes") or ""),
        )
        return metadata_path

    def write_copy_fallback(
        self,
        *,
        batch_date: str,
        slug: str,
        platform: str,
        field: str,
        text: str,
    ) -> Path:
        resolved = self.resolve_latest_social_batch(batch_date)
        safe_field = re.sub(r"[^a-zA-Z0-9_-]+", "-", field).strip("-") or "all"
        directory = self.root / "artifacts" / "social_clipboard" / resolved / slug / platform
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{safe_field}.txt"
        path.write_text(text, encoding="utf-8")
        self._log_event(
            batch_date=resolved,
            slug=slug,
            platform=platform,
            action="copy",
            details={"field": field, "file_path": str(path)},
        )
        return path

    def _append_metadata_history(self, metadata: dict[str, Any], event: str, details: dict[str, Any] | None = None) -> None:
        history = metadata.get("history")
        if not isinstance(history, list):
            history = []
        history.append({"timestamp": now_iso(), "event": event, "details": details or {}})
        metadata["history"] = history[-100:]

    def _find_duplicate_final_url(
        self,
        *,
        normalized_url: str,
        batch_date: str,
        slug: str,
        platform: str,
    ) -> dict[str, str] | None:
        for metadata_path in self.draft_root.glob("*/**/metadata.json"):
            try:
                relative = metadata_path.relative_to(self.draft_root)
                parts = relative.parts
                if len(parts) < 4:
                    continue
                other_date, other_slug, other_platform = parts[0], parts[1], parts[2]
                payload = read_json(metadata_path, {})
                if not isinstance(payload, dict):
                    continue
                other_url = str(payload.get("final_published_url") or payload.get("published_url") or "")
                if not other_url:
                    continue
                if normalize_pinterest_final_url(other_url) != normalized_url:
                    continue
                if other_date == batch_date and other_slug == slug and other_platform == platform:
                    return {
                        "scope": "same_record",
                        "date": other_date,
                        "slug": other_slug,
                        "platform": other_platform,
                        "path": str(metadata_path),
                    }
                return {
                    "scope": "other_record",
                    "date": other_date,
                    "slug": other_slug,
                    "platform": other_platform,
                    "path": str(metadata_path),
                }
            except Exception:
                continue
        return None

    def mark_pending_manual_publish(
        self,
        *,
        batch_date: str,
        slug: str,
        platform: str,
    ) -> Path:
        if platform != "pinterest":
            raise ValueError("Pending manual publish is currently implemented for Pinterest only.")
        return self.set_platform_status(batch_date=batch_date, slug=slug, platform=platform, status="pending_manual_publish")

    def mark_published_manual(
        self,
        *,
        batch_date: str,
        slug: str,
        platform: str,
        published_url: str,
        allow_duplicate_override: bool = False,
    ) -> Path:
        if platform != "pinterest":
            if not published_url.startswith("http"):
                raise ValueError("published_url is required before marking a social draft Published Manual")
            metadata_path = self._metadata_path(batch_date, slug, platform)
            metadata = read_json(metadata_path, {})
            if not isinstance(metadata, dict):
                metadata = {}
            previous = _status_key(metadata.get("status"))
            metadata["status"] = "published_manual"
            metadata["status_label"] = _status_label("published_manual")
            metadata["published_url"] = published_url
            metadata["updated_at"] = now_iso()
            self._append_metadata_history(metadata, "published_manual", {"published_url": published_url})
            _write_json(metadata_path, metadata)
            self._log_event(
                batch_date=batch_date,
                slug=slug,
                platform=platform,
                action="published_manual",
                previous_status=previous,
                new_status="published_manual",
                details={"published_url": published_url},
            )
            return metadata_path
        resolved = self.resolve_latest_social_batch(batch_date)
        validation = validate_pinterest_final_url(published_url)
        if not validation.get("valid"):
            raise ValueError(str(validation.get("message") or "Invalid Pinterest final URL."))
        normalized_url = str(validation.get("normalized_url") or "")
        duplicate = self._find_duplicate_final_url(normalized_url=normalized_url, batch_date=resolved, slug=slug, platform=platform)
        if duplicate and duplicate.get("scope") == "other_record" and not allow_duplicate_override:
            raise ValueError(
                "This Pinterest URL is already saved for "
                f"{duplicate.get('slug')} / {duplicate.get('platform')} on {duplicate.get('date')}. "
                "Use an explicit duplicate override only after manual review."
            )
        metadata_path = self._metadata_path(resolved, slug, platform)
        metadata = read_json(metadata_path, {})
        if not isinstance(metadata, dict):
            metadata = {}
        previous = _status_key(metadata.get("status"))
        if (
            previous == "published_manual"
            and normalize_pinterest_final_url(str(metadata.get("final_published_url") or metadata.get("published_url") or "")) == normalized_url
        ):
            metadata["final_url_validation_status"] = str(validation.get("status") or "")
            metadata["final_url_validation_message"] = str(validation.get("message") or "")
            metadata["last_updated_at"] = now_iso()
            metadata["updated_at"] = metadata["last_updated_at"]
            self._append_metadata_history(metadata, "final_url_saved_idempotent", {"final_published_url": str(published_url).strip()})
            _write_json(metadata_path, metadata)
            return metadata_path
        published_at = now_iso()
        metadata["status"] = "published_manual"
        metadata["status_label"] = _status_label("published_manual")
        metadata["final_published_url"] = str(published_url).strip()
        metadata["published_url"] = str(published_url).strip()
        metadata["published_at"] = published_at
        metadata["published_platform"] = "pinterest"
        metadata["publish_method"] = "manual"
        metadata["published_by"] = "human"
        metadata["api_used"] = False
        metadata["oauth_used"] = False
        metadata["browser_automation_used"] = False
        metadata.setdefault("impressions", "")
        metadata.setdefault("saves", "")
        metadata.setdefault("outbound_clicks", "")
        metadata.setdefault("pin_clicks", "")
        metadata.setdefault("last_metrics_date", "")
        metadata["metrics_source"] = "manual"
        metadata["final_url_validation_status"] = str(validation.get("status") or "")
        metadata["final_url_validation_message"] = str(validation.get("message") or "")
        metadata["last_updated_at"] = published_at
        metadata["updated_at"] = published_at
        metadata["previous_manual_publish_status"] = previous if previous != "published_manual" else str(metadata.get("previous_manual_publish_status") or "approved_for_copy")
        self._append_metadata_history(
            metadata,
            "final_url_saved",
            {
                "final_published_url": str(published_url).strip(),
                "validation_status": validation.get("status"),
                "duplicate_scope": duplicate.get("scope") if duplicate else "",
            },
        )
        self._append_metadata_history(metadata, "published_manual", {"published_at": published_at})
        _write_json(metadata_path, metadata)
        self._log_event(
            batch_date=resolved,
            slug=slug,
            platform=platform,
            action="published_manual",
            previous_status=previous,
            new_status="published_manual",
            details={
                "final_published_url": str(published_url).strip(),
                "validation_status": validation.get("status"),
                "api_used": False,
                "oauth_used": False,
                "browser_automation_used": False,
            },
        )
        return metadata_path

    def reset_published_manual(
        self,
        *,
        batch_date: str,
        slug: str,
        platform: str,
        confirmed: bool = False,
    ) -> Path:
        if platform != "pinterest":
            raise ValueError("Manual published reset is currently implemented for Pinterest only.")
        if not confirmed:
            raise ValueError("Reset requires explicit confirmation.")
        resolved = self.resolve_latest_social_batch(batch_date)
        metadata_path = self._metadata_path(resolved, slug, platform)
        metadata = read_json(metadata_path, {})
        if not isinstance(metadata, dict):
            metadata = {}
        previous = _status_key(metadata.get("status"))
        next_status = _status_key(metadata.get("previous_manual_publish_status") or "approved_for_copy")
        if next_status == "published_manual":
            next_status = "approved_for_copy"
        old_url = str(metadata.get("final_published_url") or metadata.get("published_url") or "")
        for key in ("final_published_url", "published_url", "published_at", "published_platform"):
            metadata.pop(key, None)
        metadata["status"] = next_status
        metadata["status_label"] = _status_label(next_status)
        metadata["publish_method"] = ""
        metadata["published_by"] = ""
        metadata["final_url_validation_status"] = ""
        metadata["final_url_validation_message"] = ""
        metadata["last_updated_at"] = now_iso()
        metadata["updated_at"] = metadata["last_updated_at"]
        self._append_metadata_history(metadata, "published_status_reset", {"previous_url": old_url, "reset_to": next_status})
        _write_json(metadata_path, metadata)
        self._log_event(
            batch_date=resolved,
            slug=slug,
            platform=platform,
            action="published_status_reset",
            previous_status=previous,
            new_status=next_status,
            details={"previous_url": old_url},
        )
        return metadata_path

    def approved_copy_payload(self, *, batch_date: str = "latest", index: int = 1) -> dict[str, Any]:
        items = self.approved_for_copy_items(batch_date=batch_date)
        if index < 1 or index > len(items):
            raise RuntimeError(f"Approved social draft index {index} is not available.")
        item = items[index - 1]
        resolved = str(item.get("batch_date") or self.resolve_latest_social_batch(batch_date))
        draft_path = Path(str(item["draft_path"]))
        body = draft_path.read_text(encoding="utf-8") if draft_path.exists() else ""
        metadata = read_json(Path(str(item["metadata_path"])), {})
        if not isinstance(metadata, dict):
            metadata = {}
        image_asset_path = str(item.get("platform_image_path") or metadata.get("local_image_path") or "")
        pinterest_fields = {}
        if item.get("platform") == "pinterest":
            pinterest_fields = self.platform_payload(
                batch_date=resolved,
                slug=str(item.get("slug") or ""),
                platform="pinterest",
            )
        platform_payload = self.platform_payload(
            batch_date=resolved,
            slug=str(item.get("slug") or ""),
            platform=str(item.get("platform") or ""),
        )
        blogger_all = "\n\n".join(
            part
            for part in [
                str(platform_payload.get("blogger_title") or ""),
                str(platform_payload.get("plain_text_body") or ""),
                str(platform_payload.get("source_article_url") or platform_payload.get("source_url") or ""),
                str(platform_payload.get("disclosure") or ""),
            ]
            if part
        )
        platform_name = str(item.get("platform") or "")
        hashtags_text = " ".join(str(tag) for tag in metadata.get("hashtags", []))
        quora_all = _clean_quora_copy_text(
            body=body,
            title=str(metadata.get("title") or item.get("title") or ""),
            source_url=str(item.get("website_url") or platform_payload.get("source_url") or ""),
            disclosure=str(metadata.get("affiliate_disclosure") or ""),
            hashtags=hashtags_text,
        )
        bluesky_all = "\n\n".join(
            part
            for part in [
                str(platform_payload.get("standalone_post") or ""),
                "\n\n".join(str(post) for post in (platform_payload.get("thread_posts") or [])),
            ]
            if part
        )
        return {
            **item,
            "title": metadata.get("title") or item.get("title") or "",
            "body": (
                pinterest_fields.get("pin_description")
                if pinterest_fields
                else platform_payload.get("plain_text_body")
                or platform_payload.get("standalone_post")
                or body
            ),
            "post_text": (
                pinterest_fields.get("pin_description")
                if pinterest_fields
                else platform_payload.get("plain_text_body")
                or platform_payload.get("standalone_post")
                or body
            ),
            "url": item.get("website_url") or "",
            "canonical_url": item.get("website_url") or "",
            "image_url": metadata.get("image_url") or "",
            "image_asset_path": image_asset_path,
            "image_asset_filename": str(item.get("platform_image_filename") or ""),
            "pin_title": pinterest_fields.get("pin_title") or "",
            "pin_description": pinterest_fields.get("pin_description") or "",
            "destination_url": pinterest_fields.get("destination_url") or "",
            "suggested_board": pinterest_fields.get("suggested_board") or "",
            "keywords": pinterest_fields.get("keywords") or [],
            "alt_text": pinterest_fields.get("alt_text") or "",
            "cta": metadata.get("CTA") or metadata.get("cta") or "",
            "hashtags": hashtags_text,
            "blogger_title": platform_payload.get("blogger_title") or "",
            "html_body": platform_payload.get("html_body") or "",
            "plain_text_body": platform_payload.get("plain_text_body") or "",
            "labels": platform_payload.get("labels") or [],
            "search_description": platform_payload.get("search_description") or "",
            "source_article_url": platform_payload.get("source_article_url") or "",
            "recommended_permalink_slug": platform_payload.get("recommended_permalink_slug") or "",
            "disclosure": platform_payload.get("disclosure") or "",
            "image_path": platform_payload.get("image_path") or image_asset_path,
            "image_alt_text": platform_payload.get("image_alt_text") or platform_payload.get("alt_text") or "",
            "standalone_post": platform_payload.get("standalone_post") or "",
            "thread_posts": platform_payload.get("thread_posts") or [],
            "article_url": platform_payload.get("article_url") or "",
            "character_counts": platform_payload.get("character_counts") or {},
            "all": (
                "\n\n".join(
                    part
                    for part in [
                        "PIN TITLE",
                        str(pinterest_fields.get("pin_title") or ""),
                        "PIN DESCRIPTION",
                        str(pinterest_fields.get("pin_description") or ""),
                        "DESTINATION URL",
                        str(pinterest_fields.get("destination_url") or ""),
                        "SUGGESTED BOARD",
                        str(pinterest_fields.get("suggested_board") or ""),
                        "ALT TEXT",
                        str(pinterest_fields.get("alt_text") or ""),
                        "KEYWORDS",
                        "\n".join(str(item) for item in (pinterest_fields.get("keywords") or [])),
                    ]
                    if part
                )
                if pinterest_fields
                else blogger_all
                if item.get("platform") == "blogger"
                else quora_all
                if platform_name == "quora"
                else bluesky_all
                if platform_name == "bluesky"
                else "\n\n".join(
                part for part in [
                    str(metadata.get("title") or item.get("title") or ""),
                    body,
                    str(metadata.get("CTA") or metadata.get("cta") or ""),
                    str(item.get("website_url") or ""),
                    str(metadata.get("image_url") or ""),
                    image_asset_path,
                    " ".join(str(tag) for tag in metadata.get("hashtags", [])),
                ]
                if part
                )
            ),
        }

    def approved_for_copy_items(self, *, batch_date: str = "latest") -> list[dict[str, Any]]:
        resolved = self.resolve_latest_social_batch(batch_date)
        manifest = read_json(self.draft_root / resolved / "manifest.json", {})
        items = manifest.get("items") if isinstance(manifest, dict) else []
        if not isinstance(items, list):
            return []
        approved: list[dict[str, Any]] = []
        for item in items:
            slug = str(item.get("slug") or "")
            platforms = item.get("platforms") if isinstance(item.get("platforms"), list) else []
            for platform in platforms:
                metadata_path = self.draft_root / resolved / slug / str(platform) / "metadata.json"
                metadata = read_json(metadata_path, {})
                if not isinstance(metadata, dict):
                    continue
                status = _status_key(metadata.get("status"))
                if status not in {"approved_for_copy", "pending_manual_publish", "published_manual"}:
                    continue
                selected = str(metadata.get("selected_variant") or "A.md")
                draft_path = self.draft_root / resolved / slug / str(platform) / selected
                payload = self.platform_payload(batch_date=resolved, slug=slug, platform=str(platform))
                if status != "published_manual" and payload.get("approval_blocked"):
                    continue
                approved.append(
                    {
                        "batch_date": resolved,
                        "slug": slug,
                        "title": item.get("title") or slug,
                        "platform": platform,
                        "status": status,
                        "status_label": _status_label(status),
                        "website_url": item.get("url") or metadata.get("website_url") or "",
                        "final_published_url": payload.get("final_published_url") or "",
                        "published_at": payload.get("published_at") or "",
                        "selected_variant": selected,
                        "draft_path": str(draft_path),
                        "metadata_path": str(metadata_path),
                        "exists": draft_path.exists(),
                        "platform_image_path": payload.get("platform_image_path") or "",
                        "platform_image_filename": payload.get("platform_image_filename") or "",
                    }
                )
        return approved
