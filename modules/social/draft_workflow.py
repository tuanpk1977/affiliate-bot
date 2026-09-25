from __future__ import annotations

import html
import hashlib
import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

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
from modules.weekly_root_guard import SOCIAL_HOT_UNCONFIRMED
from modules.revision_binding import binding_for_file
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
HOT_NEWS_MONITORING_PLATFORMS = [
    "facebook_en",
    "facebook_vi",
    "linkedin",
    "x",
    "quora",
    "devto",
    "pinterest",
    "blogger",
]
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


def _hot_news_source_host(url: str) -> str:
    host = urlsplit(str(url or "")).netloc.lower().removeprefix("www.")
    return host or "source"


def _hot_news_hashtags(title: str, summary: str, platform: str) -> list[str]:
    text = f"{title} {summary}".lower()
    if platform == "quora":
        return []
    candidates: list[str] = []
    if "github" in text:
        candidates.append("#GitHub")
    if "copilot" in text:
        candidates.append("#GitHubCopilot")
    if "jetbrains" in text:
        candidates.append("#JetBrains")
    if "agent" in text:
        candidates.append("#AIAgents")
    if not candidates and "ai" in text:
        candidates.append("#AI")
    limits = {"x": 1, "linkedin": 2, "facebook_en": 2, "facebook_vi": 2, "producthunt": 1}
    return list(dict.fromkeys(candidates))[: limits.get(platform, 3)]


def _hot_news_summary(title: str, summary: str) -> str:
    clean = " ".join(str(summary or "").split()).strip()
    if clean:
        return clean
    return (
        f"{title} is showing up in current source monitoring. The topic is worth watching, "
        "but the available details still need confirmation from primary sources."
    )


def _hot_news_title_line(title: str) -> str:
    clean = " ".join(str(title or "").split()).strip()
    if clean:
        return clean
    return "AI hot trend watchlist item"


def _hot_news_starter_drafts(
    *,
    title: str,
    summary: str,
    source_urls: list[str],
    discovery_timestamp: str,
    platform: str,
) -> dict[str, Any]:
    clean_title = _hot_news_title_line(title)
    clean_summary = _hot_news_summary(title, summary)
    urls = [str(url).strip() for url in source_urls if str(url).strip()]
    primary_url = urls[0] if urls else ""
    hashtags = _hot_news_hashtags(clean_title, clean_summary, platform)
    tags_text = " ".join(hashtags)
    source_block = "\n\n".join(
        f"Source: {official_source_name(url)}\n{url}" for url in urls[:2]
    )
    primary_source_name = official_source_name(primary_url)
    audience = infer_story_audience(clean_title, clean_summary)
    vi_audience = {
        "enterprise administrators and engineering leaders": "quản trị viên doanh nghiệp và lãnh đạo kỹ thuật",
        "developers and engineering teams": "lập trình viên và đội ngũ kỹ thuật",
        "marketers and creators": "đội ngũ marketing và nhà sáng tạo",
        "small-business operators": "người vận hành doanh nghiệp nhỏ",
        "product teams and early adopters": "đội ngũ sản phẩm và nhóm thử nghiệm sớm",
        "AI users evaluating the announcement": "người dùng đang đánh giá thông báo AI này",
    }.get(audience, "đội ngũ đang đánh giá thông báo")
    cta = (
        f"For {audience}, the practical question is which decision this announcement creates "
        "and what remains unverified."
    )
    body_a = ""
    body_b = ""
    body_c = ""

    if platform == "facebook_en":
        body_a = (
            f"{clean_title}\n\n{clean_summary}\n\n"
            f"The useful signal for {audience} is operational: confirm the documented scope before changing a team workflow. "
            "The announcement is evidence of the update, not evidence that it fits every organization. "
            "Any details beyond the cited source remain unconfirmed.\n\n"
            f"{cta}\n\n{tags_text}\n\n{source_block}"
        )
        body_b = (
            f"What changed: {clean_title}\n\n{clean_summary}\n\n"
            "What the source establishes is the announcement itself. Adoption value, rollout coverage, and workflow impact still need to be checked against the official details.\n\n"
            f"For {audience}, that makes this a verification task—not a product endorsement.\n\n{tags_text}\n\n{source_block}"
        )
        body_c = (
            f"A practical reading of {clean_title}\n\n{clean_summary}\n\n"
            "What to verify before rollout: who controls the setting, which accounts receive it, and whether the documented behavior matches your governance process. "
            "Those questions matter more than the announcement headline.\n\n"
            f"{tags_text}\n\n{source_block}"
        )
    elif platform == "facebook_vi":
        vi_fact = f"{primary_source_name} đã công bố thông tin chính thức về {clean_title}."
        body_a = (
            f"{clean_title}\n\n{vi_fact}\n\n"
            f"Điểm đáng chú ý với {vi_audience} là tác động vận hành: hãy đối chiếu phạm vi được tài liệu chính thức xác nhận trước khi thay đổi quy trình. "
            "Thông báo này xác nhận có cập nhật, nhưng chưa tự chứng minh rằng cập nhật phù hợp với mọi tổ chức.\n\n"
            f"{tags_text}\n\nNguồn chính thức:\n{source_block}"
        )
        body_b = (
            f"Có gì thay đổi trong {clean_title}?\n\n{vi_fact}\n\n"
            "Nguồn hiện xác nhận thông báo, không phải hiệu quả triển khai. Phạm vi áp dụng, quyền quản trị và ảnh hưởng tới quy trình vẫn là các điểm cần kiểm tra.\n\n"
            f"Vì vậy, đây là thông tin để đánh giá có kiểm chứng, không phải lời khuyên mua dùng.\n\n{tags_text}\n\nNguồn chính thức:\n{source_block}"
        )
        body_c = (
            f"Góc nhìn thực tế về {clean_title}\n\n{vi_fact}\n\n"
            "Trước khi áp dụng, đội ngũ nên xác minh ai kiểm soát thiết lập, tài khoản nào được hỗ trợ và hành vi được mô tả có khớp quy trình quản trị hiện tại hay không. "
            "Đó mới là phần quyết định giá trị của cập nhật.\n\n"
            f"{tags_text}\n\nNguồn chính thức:\n{source_block}"
        )
    elif platform == "linkedin":
        body_a = (
            f"{clean_title}\n\n{clean_summary}\n\n"
            "Verified fact: the official source documents the announcement.\n\n"
            f"Operational interpretation: for {audience}, the change is a prompt to identify who owns the setting and which workflow it affects.\n\n"
            "Still unverified: pricing, performance, organization-wide fit, and any behavior not stated by the source.\n\n"
            f"The useful outcome is a decision record—not a repetition of the headline.\n\n{tags_text}\n\n{source_block}"
        )
        body_b = (
            f"An early AI signal on the watchlist: {clean_title}\n\n"
            "The right posture here is disciplined curiosity. Track the source material, separate verified details from assumptions, and wait for enough evidence to judge workflow fit.\n\n"
            f"For {audience}, the next step is to map the documented change to one real control or workflow decision.\n\n{tags_text}\n\n{source_block}"
        )
        body_c = (
            f"If {clean_title} matters to your team, avoid the usual mistake: repeating the headline before validating the operating details.\n\n"
            f"{clean_summary}\n\n"
            f"The decision point is whether the official scope resolves a real governance constraint for {audience}.\n\n{tags_text}\n\n{source_block}"
        )
    elif platform == "x":
        # X gets no forced hashtags: preserving the primary-source URL and a useful
        # implication is more valuable than spending the 280-character budget on tags.
        hashtags = []
        tags_text = ""
        source_line = f"Source: {primary_source_name} {primary_url}".strip()
        prefix_a = f"{clean_title}. Official update. Before adopting, verify its documented scope and team-control impact."
        prefix_b = f"{clean_title}. Announcement confirmed. Review organization fit and rollout impact before adoption."
        prefix_c = f"{clean_title}. What to verify: does the documented change alter a real governance decision?"
        body_a = f"{prefix_a[: max(0, 278 - len(source_line))].rstrip()}\n{source_line}"
        body_b = f"{prefix_b[: max(0, 278 - len(source_line))].rstrip()}\n{source_line}"
        body_c = f"{prefix_c[: max(0, 278 - len(source_line))].rstrip()}\n{source_line}"
    elif platform == "quora":
        body_a = (
            f"What does {clean_title} mean for teams?\n\n"
            f"Short answer: {clean_summary}\n\n"
            "The official announcement confirms the change, but it does not by itself prove organization-wide fit. Check documented scope, account eligibility, and administrative ownership before changing a workflow.\n\n"
            f"For {audience}, the useful outcome is a specific governance decision, not a general endorsement.\n\n{source_block}"
        )
        body_b = (
            f"What should buyers verify before taking {clean_title} seriously?\n\n"
            "What to verify: what is actually available, who can configure it, and which limitations the documentation names. Those facts determine whether the announcement changes a real buying or governance decision.\n\n"
            f"What remains unknown should stay unknown until another reliable source resolves it.\n\n{source_block}"
        )
        body_c = (
            f"Is {clean_title} enough reason to change a team workflow?\n\n"
            "Not on the headline alone. The practical test is whether the official scope matches the team's account model, control requirements, and current process.\n\n"
            f"That separates a verified product change from an unsupported recommendation.\n\n{source_block}"
        )
    elif platform == "devto":
        body_a = (
            f"# {clean_title}\n\n"
            "## Why this matters\n\n"
            f"{clean_summary}\n\n"
            "## What is confirmed so far\n\n"
            f"- Announcement source family: {_hot_news_source_host(primary_url)}\n"
            "- Confirmation status: official announcement available; broader fit not established\n\n"
            "## Practical takeaway\n\n"
            "Treat this as an engineering or product watchlist note. Do not repeat unsupported details until the primary sources document them clearly.\n\n"
            f"For builders, the useful next step is to test the documented boundary against an actual development or administration workflow.\n\nTags: {tags_text}\n\n{source_block}"
        )
        body_b = (
            f"# Monitoring {clean_title}\n\n"
            f"{clean_summary}\n\n"
            "This is a short monitoring note for builders who want to separate confirmed product evidence from announcement noise.\n\n"
            f"For builders, the key distinction is confirmed behavior versus assumed downstream impact.\n\nTags: {tags_text}\n\n{source_block}"
        )
        body_c = (
            f"# Early note on {clean_title}\n\n"
            "The useful move is to hold this in a watchlist until documentation, access rules, and workflow evidence become clearer.\n\n"
            f"The implementation question is whether the documented change removes a real control or workflow constraint.\n\nTags: {tags_text}\n\n{source_block}"
        )
    elif platform == "pinterest":
        pin_title = clean_title[:90]
        body_a = (
            f"Pin title: {pin_title}\n\nPin description: {clean_summary} Review the documented scope and team-control impact before adoption.\n\n"
            f"Destination URL: {primary_url}\nSuggested board: AI workflow governance\nKeywords: GitHub Copilot, JetBrains, enterprise settings\n"
            f"Overlay text: What enterprise teams should verify\n\n{tags_text}\n\nSource: {primary_source_name}"
        )
        body_b = (
            f"Pin title: {pin_title}\n\nPin description: A source-backed checkpoint for teams evaluating the announcement: availability, admin ownership, and workflow impact.\n\n"
            f"Destination URL: {primary_url}\nSuggested board: AI product updates\nKeywords: AI update, admin controls, developer workflow\n"
            f"Overlay text: Confirm scope before rollout\n\n{tags_text}\n\nSource: {primary_source_name}"
        )
        body_c = (
            f"Pin title: {pin_title}\n\nPin description: The announcement is confirmed; broader organization fit is not. Use the official source to separate fact from assumption.\n\n"
            f"Destination URL: {primary_url}\nSuggested board: Enterprise AI controls\nKeywords: enterprise AI, governance, official documentation\n"
            f"Overlay text: Review fact, implication, and open question\n\n{tags_text}\n\nSource: {primary_source_name}"
        )
    elif platform == "blogger":
        body_a = (
            f"# {clean_title}\n\n"
            "## Why this hot-trend item is worth watching\n\n"
            f"{clean_summary}\n\n"
            "## What is known right now\n\n"
            f"- Source family: {_hot_news_source_host(primary_url)}\n"
            "- Current status: announcement confirmed; broader product-fit claims unverified\n\n"
            "## What readers should do next\n\n"
            "Track the primary sources, wait for clearer documentation, and avoid treating the item as a buying recommendation too early.\n\n"
            f"Disclosure: this post links to source material under review.\n\nTags: {tags_text}\n\n{source_block}"
        )
        body_b = (
            f"# Monitoring note: {clean_title}\n\n"
            f"{clean_summary}\n\n"
            "This is a companion monitoring draft, not a final product review. It exists to help readers track what is known, what is still unclear, and which source links deserve follow-up.\n\n"
            f"For {audience}, the useful output is a documented decision about scope, ownership, or rollout.\n\nTags: {tags_text}\n\n{source_block}"
        )
        body_c = (
            f"# Early watchlist entry for {clean_title}\n\n"
            f"{clean_summary}\n\nGood AI coverage is not just speed. It is disciplined follow-up. Review this item again only when the sources provide enough evidence to support a deeper recommendation.\n\n"
            f"The article should be revisited only when new evidence changes that decision.\n\nTags: {tags_text}\n\n{source_block}"
        )
    elif platform == "producthunt":
        body_a = (
            f"Discussion prompt: {clean_title}\n\n{clean_summary}\n\n"
            "Worth discussing: which documented workflow or administration problem does this solve, and for whom? This is context for the community, not an endorsement or launch claim.\n\n"
            f"{tags_text}\n\n{source_block}"
        )
        body_b = (
            f"Community context: {clean_title}\n\n"
            "The announcement is confirmed by the source below. Product fit, adoption value, and broader availability should remain separate questions until evidence supports them. "
            "What to verify: the documented user, scope, and workflow boundary.\n\n"
            f"{cta}\n\n{tags_text}\n\n{source_block}"
        )
        body_c = (
            f"A source-first look at {clean_title}\n\n{clean_summary}\n\n"
            "What to consider: the specific team decision this changes—not whether the headline sounds exciting.\n\n"
            f"{tags_text}\n\n{source_block}"
        )
    else:
        body_a = f"{clean_title}\n\n{clean_summary}\n\nSources:\n{source_block}\n\n{cta}\n\n{tags_text}"
        body_b = body_a
        body_c = body_a

    platform_title = {
        "linkedin": clean_title,
        "facebook_en": clean_title,
        "facebook_vi": clean_title,
        "x": clean_title[:72],
        "quora": clean_title,
        "devto": clean_title,
        "pinterest": clean_title[:90],
        "blogger": clean_title,
        "producthunt": clean_title,
    }.get(platform, clean_title)
    return {
        "title": platform_title,
        "cta": cta,
        "hashtags": hashtags,
        "drafts": {"A.md": body_a.strip() + "\n", "B.md": body_b.strip() + "\n", "C.md": body_c.strip() + "\n"},
    }


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

    def _current_cycle_angle_history(
        self,
        *,
        batch_date: str,
        root_topic_id: str,
        platform: str,
    ) -> list[str]:
        """Read only same-root metadata in the requested Website cycle."""
        if not _looks_like_iso_date(batch_date):
            return []
        start = date.fromisoformat(_week_start(batch_date))
        end = date.fromisoformat(batch_date)
        angles: list[str] = []
        # Exclude the current batch so rerunning Menu F is idempotent instead of
        # treating its own unapproved drafts as prior-day history.
        for offset in range(max(0, (end - start).days)):
            day = (start + timedelta(days=offset)).isoformat()
            day_root = self.draft_root / day
            if not day_root.is_dir():
                continue
            for metadata_path in day_root.glob(f"*/{platform}/metadata.json"):
                metadata = read_json(metadata_path, {})
                if not isinstance(metadata, dict):
                    continue
                if str(metadata.get("root_topic_id") or "") != root_topic_id:
                    continue
                # A/B/C are internal components.  Consume one daily angle only
                # after the composed FINAL post is approved or published.
                if _status_key(metadata.get("status")) not in {
                    "approved_for_copy", "pending_manual_publish", "published_manual"
                }:
                    continue
                angle = str(
                    metadata.get("today_social_angle")
                    or metadata.get("social_angle")
                    or ""
                )
                if angle:
                    angles.append(angle)
        return list(dict.fromkeys(angles))

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
        research_dir = self.data_dir / "research" / slug
        if not research_dir.exists():
            return 0
        source_urls: set[str] = set()
        for path in research_dir.rglob("*.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            stack: list[Any] = [payload]
            while stack:
                value = stack.pop()
                if isinstance(value, dict):
                    for key, nested in value.items():
                        if key.lower() in {"url", "source_url", "link"} and isinstance(nested, str) and nested.startswith("http"):
                            source_urls.add(nested)
                        else:
                            stack.append(nested)
                elif isinstance(value, list):
                    stack.extend(value)
        return len(source_urls)

    def rank_articles(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        ranked: list[dict[str, Any]] = []
        for row in rows:
            article = self.article_from_live_row(row)
            headings = article.headings or []
            key_points = article.key_points or []
            source_count = self._research_source_count(article.article_id)
            text = f"{article.title} {article.description} {' '.join(headings)}".lower()
            score = 0.0
            reasons: list[str] = []
            if article.description and len(article.description) >= 80:
                score += 12
                reasons.append("strong meta description")
            if len(headings) >= 4:
                score += 12
                reasons.append("clear article structure")
            if article.image:
                score += 8
                reasons.append("featured image available")
            if source_count >= 3:
                score += 16
                reasons.append(f"{source_count} research sources found")
            elif source_count >= 2:
                score += 10
                reasons.append(f"{source_count} research sources found")
            elif source_count == 1:
                score += 4
                reasons.append("one research source found")
            if any(word in text for word in ("pricing", "comparison", "alternatives", "buyer", "workflow", "platform", "software")):
                score += 16
                reasons.append("commercial or workflow intent")
            if any(word in text for word in ("how to", "challenges", "marketing", "automation", "tools", "business")):
                score += 12
                reasons.append("practical usefulness")
            if any(word in text for word in ("2026", "review")):
                score += 6
                reasons.append("evergreen review angle")
            if len(key_points) >= 4:
                score += 8
                reasons.append("multiple reusable takeaways")
            if "healthcare" in text or "financial" in text or "legal" in text:
                score -= 10
                reasons.append("higher review risk")
            ranked.append(
                {
                    "slug": article.article_id,
                    "title": article.title,
                    "url": article.url,
                    "score": round(score, 2),
                    "reason": "; ".join(reasons) or "basic live article metadata",
                    "selected": False,
                    "source_count": source_count,
                }
            )
        ranked.sort(key=lambda item: (-float(item["score"]), str(item["slug"])))
        for item in ranked[:DEFAULT_SOCIAL_DRAFT_COUNT]:
            item["selected"] = True
        return ranked

    def _weekly_social_roots_path(self, week_start: str) -> Path:
        return self.draft_root / "weeks" / f"{week_start}.json"

    def _website_weekly_roots(self, batch_date: str) -> list[dict[str, Any]]:
        """Load only the canonical Website roots for the requested content cycle."""
        if not _looks_like_iso_date(batch_date):
            return []
        manifest = read_json(
            self.data_dir / "editorial_queue" / "weeks" / _week_start(batch_date) / "week.json",
            {},
        )
        if not isinstance(manifest, dict) or str(manifest.get("lock_status") or "").lower() != "locked":
            return []
        roots = [row for row in list(manifest.get("topics") or []) if isinstance(row, dict)]
        return roots[:SOCIAL_WEEKLY_ROOT_COUNT]

    def _website_root_bindings(
        self,
        *,
        batch_date: str,
        roots: list[dict[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        """Resolve source slugs from current-cycle queues without historical scans."""
        if not _looks_like_iso_date(batch_date):
            return {}
        root_lookup: dict[str, dict[str, Any]] = {}
        for root in roots:
            root_id = str(root.get("root_topic_id") or root.get("parent_slug") or root.get("slug") or "")
            if root_id:
                root_lookup[root_id] = root
        bindings: dict[str, dict[str, Any]] = {}
        start = date.fromisoformat(_week_start(batch_date))
        end = date.fromisoformat(batch_date)
        for offset in range(max(0, (end - start).days) + 1):
            day = (start + timedelta(days=offset)).isoformat()
            queue = read_json(self.data_dir / "editorial_queue" / day / "topics.json", {})
            for topic in list(queue.get("topics") or []) if isinstance(queue, dict) else []:
                if not isinstance(topic, dict):
                    continue
                slug = str(topic.get("slug") or "")
                root_id = str(topic.get("root_topic_id") or topic.get("parent_slug") or "")
                if not slug or root_id not in root_lookup:
                    continue
                root = root_lookup[root_id]
                bindings[slug] = {
                    "root_topic_id": root_id,
                    "root_title": str(root.get("root_title") or root.get("title") or ""),
                    "source_article_slug": slug,
                    "source_batch_date": day,
                    "social_angle": str(topic.get("daily_angle") or topic.get("suggested_article_angle") or "source_article_adaptation"),
                    "today_social_angle": str(topic.get("daily_angle") or topic.get("suggested_article_angle") or "source_article_adaptation"),
                    "content_relationship": "website_root_social_adaptation",
                    "content_origin": "WEBSITE_ROOT_BASED",
                    "social_mode": "SOURCE_BASED_SOCIAL",
                }
        for root_id, root in root_lookup.items():
            parent_slug = str(root.get("parent_slug") or root.get("slug") or root_id)
            bindings.setdefault(
                parent_slug,
                {
                    "root_topic_id": root_id,
                    "root_title": str(root.get("root_title") or root.get("title") or ""),
                    "source_article_slug": parent_slug,
                    "source_batch_date": _week_start(batch_date),
                    "social_angle": "root_topic_adaptation",
                    "today_social_angle": "root_topic_adaptation",
                    "content_relationship": "website_root_social_adaptation",
                    "content_origin": "WEBSITE_ROOT_BASED",
                    "social_mode": "SOURCE_BASED_SOCIAL",
                },
            )
        return bindings

    def _source_binding(self, slug: str, context: dict[str, Any]) -> dict[str, Any]:
        metadata = read_json(self.data_dir / "production_article_drafts" / slug / "metadata.json", {})
        if not isinstance(metadata, dict):
            metadata = {}
        html_path = self.data_dir / "production_article_drafts" / slug / "index.html"
        current_hash = ""
        if html_path.is_file():
            current_hash = binding_for_file(html_path)["content_hash"]
        approval = metadata.get("human_approval") if isinstance(metadata.get("human_approval"), dict) else {}
        revision_id = str(
            metadata.get("revision_id")
            or approval.get("revision_id")
            or approval.get("approved_revision_id")
            or (f"website-revision-v1:{current_hash}" if current_hash else "")
        )
        research_dir = self.data_dir / "research" / slug
        research_reference = ""
        for name in ("FACT_LEDGER.json", "fact_ledger.json", "package.json"):
            candidate = research_dir / name
            if candidate.is_file():
                research_reference = str(candidate.relative_to(self.root)).replace("\\", "/")
                break
        enrichment = read_json(research_dir / "enrichment_report.json", {})
        if not isinstance(enrichment, dict):
            enrichment = {}
        research_blockers = list(enrichment.get("blockers") or [])
        research_status = str(enrichment.get("status") or "").upper()
        evidence_verified = bool(
            enrichment
            and not research_blockers
            and (
                enrichment.get("article_ready") is True
                or enrichment.get("draft_exportable") is True
                or research_status in {"ARTICLE_READY", "RESEARCH_GOOD", "RESEARCH_STRONG"}
            )
        )
        return {
            **context,
            "source_article_slug": slug,
            "source_revision_id": revision_id,
            "source_content_hash": current_hash,
            "source_evidence_reference": research_reference,
            "evidence_inheritance": (
                "VERIFIED_SOURCE_ARTICLE" if evidence_verified else "SOURCE_RESEARCH_REVIEW_REQUIRED"
            ),
            "source_research_state": "PASSED" if evidence_verified else "BLOCKED_OR_UNVERIFIED",
            "source_research_blockers": research_blockers,
        }

    def _read_weekly_social_roots(self, batch_date: str) -> dict[str, Any]:
        if not _looks_like_iso_date(batch_date):
            return {}
        week_start = _week_start(batch_date)
        path = self._weekly_social_roots_path(week_start)
        payload = read_json(path, {})
        if isinstance(payload, dict) and isinstance(payload.get("root_slugs"), list):
            return payload
        for existing_date in self._social_batch_dates():
            if existing_date >= batch_date or not _looks_like_iso_date(existing_date) or _week_start(existing_date) != week_start:
                continue
            manifest = read_json(self.draft_root / existing_date / "manifest.json", {})
            items = manifest.get("items") if isinstance(manifest, dict) else []
            if isinstance(items, list) and items:
                root_slugs = [str(item.get("slug") or "") for item in items if isinstance(item, dict) and item.get("slug")]
                if root_slugs:
                    return {
                        "schema_version": 1,
                        "social_week_start": week_start,
                        "root_slugs": root_slugs[:SOCIAL_WEEKLY_ROOT_COUNT],
                        "source_batch_date": existing_date,
                        "selection_policy": "derived_from_earliest_social_manifest",
                    }
        return {}

    def _write_weekly_social_roots(self, *, batch_date: str, ranking: list[dict[str, Any]], selected: list[dict[str, Any]]) -> dict[str, Any]:
        week_start = _week_start(batch_date)
        path = self._weekly_social_roots_path(week_start)
        root_slugs = [str(row.get("slug") or "") for row in selected if row.get("slug")]
        payload = {
            "schema_version": 1,
            "social_week_start": week_start,
            "root_slugs": root_slugs[:SOCIAL_WEEKLY_ROOT_COUNT],
            "source_batch_date": batch_date,
            "selection_policy": "monday_or_first_social_selection",
            "selection_count": len(root_slugs[:SOCIAL_WEEKLY_ROOT_COUNT]),
            "created_at": now_iso(),
            "ranking": ranking,
            "continuation_rule": "Tue-Sun social drafts must reuse these root slugs and add a distinct advanced angle plus next-post teaser.",
        }
        existing = read_json(path, {})
        if isinstance(existing, dict) and existing.get("created_at"):
            payload["created_at"] = existing["created_at"]
        _write_json(path, payload)
        return payload

    def _live_row_for_weekly_root(self, slug: str, resolved: str, live_by_slug: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
        if slug in live_by_slug:
            return live_by_slug[slug]
        html_path = self.root / "docs" / slug / "index.html"
        if not html_path.exists():
            return None
        html_text = html_path.read_text(encoding="utf-8", errors="ignore")
        canonical = extract_canonical(html_text) or f"https://smileaireviewhub.com/{slug}/"
        title = extract_meta(html_text, "og:title") or extract_title(html_text) or slug.replace("-", " ").title()
        return {
            "slug": slug,
            "title": _best_title(slug, title, title),
            "url": canonical,
            "batch_date": resolved,
            "source": "weekly_social_root_docs_fallback",
        }

    def article_from_live_row(self, row: dict[str, Any]) -> PublishedArticle:
        slug = str(row["slug"])
        html_path = self.root / "docs" / slug / "index.html"
        html_text = html_path.read_text(encoding="utf-8", errors="ignore") if html_path.exists() else ""
        title = _best_title(slug, extract_meta(html_text, "og:title") or extract_title(html_text), str(row.get("title") or ""))
        description = html.unescape(extract_meta(html_text, "description") or extract_meta(html_text, "og:description"))
        image = extract_meta(html_text, "og:image") or extract_meta(html_text, "twitter:image")
        if image.startswith("/"):
            image = "https://smileaireviewhub.com" + image
        headings = [
            heading for heading in extract_headings(html_text)
            if heading.strip().lower() not in NON_SOCIAL_KEYPOINT_HEADINGS
        ]
        paragraphs = extract_paragraphs(html_text, limit=8)
        return PublishedArticle(
            article_id=slug,
            title=title,
            url=str(row["url"]),
            description=description,
            image=image,
            tags=extract_tags(title, description),
            publish_date=extract_publish_date(html_text),
            canonical_url=extract_canonical(html_text) or str(row["url"]),
            og_title=extract_meta(html_text, "og:title"),
            og_description=extract_meta(html_text, "og:description"),
            og_image=image,
            summary=extract_article_summary(html_text, description),
            headings=headings,
            key_points=headings[:5] or paragraphs[:5],
            affiliate_disclosure=extract_affiliate_disclosure(html_text),
        )

    def source_package(
        self,
        article: PublishedArticle,
        *,
        batch_date: str,
        platforms: list[str],
        social_series: dict[str, Any] | None = None,
        provenance: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        evidence: dict[str, Any] = {
            "status": "BLOCKED_RESEARCH",
            "source_excerpts": [],
            "fact_ledger": [],
            "warnings": ["Live article HTML was not available for local evidence extraction."],
        }
        html_path = self.root / "docs" / article.article_id / "index.html"
        if not html_path.exists():
            html_path = self.root / "site_output" / article.article_id / "index.html"
        if html_path.exists():
            raw_html = html_path.read_text(encoding="utf-8", errors="replace")
            pipeline = ResearchEnrichmentPipeline(
                root=self.root,
                data_dir=self.data_dir,
                config={"minimum_publishable_claims": 1, "maximum_publishable_claims": 100},
            )
            package_stub = {
                "slug": article.article_id,
                "keyword": article.title,
                "entities": {"products": [article.title]},
                "outline": {},
            }
            task_stub = {"slug": article.article_id, "title": article.title}
            paragraphs, _ = pipeline.extract_paragraphs(
                raw_html,
                content_type="text/html",
                task=task_stub,
                package=package_stub,
            )
            source = {
                "source_id": "live-article-001",
                "title": article.title,
                "canonical_url": article.canonical_url or article.url,
                "url": article.canonical_url or article.url,
                "source_type": "published_live_article",
                "retrieved_at": now_iso(),
                "http_status": 200,
                "content_hash": hashlib.sha256(raw_html.encode("utf-8")).hexdigest(),
                "paragraphs": [
                    {
                        "paragraph_id": f"live-article-001-p{index:03d}",
                        "paragraph_order": index,
                        **row,
                    }
                    for index, row in enumerate(paragraphs, start=1)
                ],
                "extracted_relevant_paragraphs": [row["text"] for row in paragraphs],
                "freshness": article.publish_date or "date_not_available",
                "verification_status": "published_live",
                "confidence": "high",
            }
            claims = pipeline.extract_claims(
                [source],
                package=package_stub,
                task=task_stub,
                maximum=100,
            )
            evidence = {
                "status": "EVIDENCE_VALIDATED" if claims else "BLOCKED_RESEARCH",
                "source_excerpts": [source],
                "fact_ledger": claims,
                "warnings": [] if claims else ["No directly supported social-writing claims were extracted."],
            }
        return {
            "schema_version": 1,
            "status": "writing_package_ready",
            "batch_date": batch_date,
            "content_origin": "WEBSITE_ROOT_BASED",
            "social_mode": "SOURCE_BASED_SOCIAL",
            "social_series": social_series or {},
            "provenance": provenance or {},
            "article": {
                "slug": article.article_id,
                "title": article.title,
                "url": article.url,
                "canonical_url": article.canonical_url or article.url,
                "meta_description": article.description,
                "og_title": article.og_title,
                "og_description": article.og_description,
                "image": article.image,
                "publish_date": article.publish_date,
                "tags": article.tags,
                "summary": article.summary,
                "headings": article.headings or [],
                "key_points": article.key_points or [],
                "affiliate_disclosure": article.affiliate_disclosure,
            },
            "platforms": platforms,
            "required_outputs": {
                platform: ["A.md", "B.md", "C.md", "metadata.json"]
                for platform in platforms
            },
            "requirements": {
                "manual_only": True,
                "no_social_api": True,
                "no_oauth": True,
                "no_browser_automation": True,
                "include_website_url": True,
                "x_link_optional": True,
                "x_max_characters": X_MAX_CHARACTERS,
                "x_thread_enabled": False,
                "semantic_compression_required": True,
                "include_image": True,
                "include_affiliate_disclosure_when_relevant": True,
                "include_reusable_excerpts": [150, 250, 500],
                "weekly_root_topic_lock": True,
                "advanced_daily_angle_required": True,
                "next_post_teaser_required": False,
                "content_model": "COMPLEMENTARY_COMPONENTS_V1",
                "local_platform_composer_authoritative": True,
                "future_angle_reservation": True,
            },
            "platform_playbooks": {
                platform: dict(self.platform_playbooks.get(platform) or {})
                for platform in platforms
            },
            "component_roles": {
                "A.md": "ACTIONABLE",
                "B.md": "INSIGHT",
                "C.md": "PROBLEM_SOLUTION",
            },
            "evidence": evidence,
        }

    def writing_prompt(self, package: dict[str, Any]) -> str:
        article = package["article"]
        social_series = package.get("social_series") if isinstance(package.get("social_series"), dict) else {}
        platform_lines = "\n".join(f"- {platform}: create A.md, B.md, C.md and metadata.json" for platform in package["platforms"])
        series_lines = ""
        if social_series:
            roots = ", ".join(str(slug) for slug in social_series.get("root_slugs") or [])
            series_lines = f"""
Weekly social series:
- Week start: {social_series.get("social_week_start") or ""}
- Locked root slugs: {roots}
- Current batch date: {package.get("batch_date") or ""}
- Rule: do not introduce replacement article topics during Tue-Sun. Keep the same locked roots and write a visibly different advanced angle each day.
- A/B/C remain inside today's social angle and must not consume or fully develop future Website angles.
"""
        return f"""# Codex Social Writing Package

Write manual social post drafts from this already-live website article.

Rules:
- Do not call OpenAI API or any paid API.
- Do not publish, approve, deploy, index, or push.
- Use only the article facts in `source_package.json`.
- Reuse supplied fact-ledger claim IDs. If a draft introduces a new factual claim, declare it in metadata.new_claims with an allowed evidence binding; an unsupported new claim blocks import.
- Preserve the website URL and canonical URL.
- Include the article image URL when the platform supports an image.
- Include affiliate disclosure when the post is promotional or link-forward.
- Create three complementary content components: A = ACTIONABLE, B = INSIGHT, C = PROBLEM_SOLUTION.
- A/B/C are internal building blocks for one final platform post, not competing publication variants.
- Do not concatenate components. The local Platform Composer synthesizes them into FINAL.md after import.
- Apply the platform-specific playbook in `source_package.json`; do not expand one generic post with filler.
- For X, design every draft from the start for HARD_MAX_CHARACTERS=280. Threads are disabled. If a draft is too long, rewrite it semantically; never slice or truncate it. A link is optional when the insight uses the space better.
- Store component_role, the same today_social_angle, evidence_refs, new_claims, character_count, and visual recommendation metadata.
- Save outputs under each platform folder.
- If this is a Tue-Sun continuation, make the post meaningfully different from earlier posts for the same root article.
- Do not spend a future pricing, ROI, security, or measurement angle unless it is today's source angle.

Article:
- Title: {article["title"]}
- URL: {article["url"]}
- Canonical: {article["canonical_url"]}
- Image: {article["image"]}
- Summary: {article["summary"]}

Platforms:
{platform_lines}
{series_lines}
"""

    def hot_news_monitoring_package(
        self,
        *,
        title: str,
        batch_date: str,
        source_urls: list[str],
        discovery_timestamp: str,
        platforms: list[str],
        summary: str = "",
        queue_type: str = "SOCIAL_HOT_DRAFT",
        editorial_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        urls = [str(url).strip() for url in source_urls if str(url).strip()]
        if not urls:
            raise ValueError("SOCIAL_HOT_UNCONFIRMED requires at least one preserved source URL.")
        return {
            "schema_version": 1,
            "status": "writing_package_ready",
            "workflow": "HOT_NEWS_MONITORING",
            "content_origin": "HOT_NEWS",
            "social_mode": "STANDALONE_SOCIAL_RESEARCH",
            "queue_type": queue_type,
            "content_lane": SOCIAL_HOT_UNCONFIRMED,
            "batch_date": batch_date,
            "hot_news": {
                "title": title,
                "summary": summary,
                "source_urls": urls,
                "discovery_timestamp": discovery_timestamp,
                "confirmation_status": "unconfirmed",
            },
            "platforms": platforms,
            "editorial_selection": dict(editorial_metadata or {}),
            "required_outputs": {
                platform: ["A.md", "B.md", "C.md", "metadata.json"]
                for platform in platforms
            },
            "requirements": {
                "manual_only": True,
                "no_social_api": True,
                "no_oauth": True,
                "no_browser_automation": True,
                "include_website_url": False,
                "require_live_website_article": False,
                "must_not_create_website_draft": True,
                "must_not_modify_weekly_roots": True,
                "cautious_unconfirmed_language": True,
                "preserve_source_urls": True,
                "preserve_discovery_timestamp": True,
                "must_include_basic_intro": True,
                "must_include_what_is_known": True,
                "must_include_source_context": True,
                "must_keep_single_source_block": True,
                "must_not_duplicate_source_link_blocks": True,
                "cta_policy": "optional_story_specific_only",
                "generic_cta_forbidden": True,
            },
        }

    def hot_news_monitoring_prompt(self, package: dict[str, Any]) -> str:
        hot_news = package["hot_news"]
        source_lines = "\n".join(f"- {url}" for url in hot_news.get("source_urls") or [])
        platform_lines = "\n".join(f"- {platform}: create A.md, B.md, C.md and metadata.json" for platform in package["platforms"])
        return f"""# Social Hot-News Monitoring Package

Write cautious social-only monitoring drafts.

Rules:
- Content lane: {SOCIAL_HOT_UNCONFIRMED}
- Do not call OpenAI API or any paid API.
- Do not create a website article, website draft, weekly root, canonical URL, or fabricated website link.
- Do not publish, approve, deploy, index, or push.
- Use cautious language: "reported", "appears", "not officially confirmed", "monitoring for confirmation".
- Do not invent facts, pricing, dates, features, quotes, availability, or official confirmation.
- Preserve source URLs and discovery timestamp.
- A CTA is optional. Do not add a generic follow/read/check/visit CTA.
- If a CTA adds value, make it specific to the decision created by this story; otherwise end with an implication, concise observation, decision question, or source.
- Each platform draft must have a real hook or opening line. Do not output bare link-only or citation-only copy.
- Add a short plain-language introduction so the post makes sense even for someone who did not see the source first.
- Separate what is known from what still needs confirmation.
- Keep exactly one source-link block unless the platform format explicitly needs two source fields.
- Do not fabricate a Smile AI Review Hub article URL for this lane.
- Required platform behavior:
  - Facebook EN / VI: conversational hook + 2 short paragraphs + source context; CTA optional.
  - LinkedIn: professional framing + enough context + operational implication; no engagement bait.
  - X: one sharp hook + one source URL + minimal tags.
  - Quora: suggested question + concise answer + source context.
  - Dev.to: short structured note with headings.
  - Pinterest: pin title + pin description + destination URL = primary source URL.
  - Blogger: short companion note with sections, not just a copied link.

Hot-news item:
- Title: {hot_news.get("title") or ""}
- Discovery timestamp: {hot_news.get("discovery_timestamp") or ""}
- Summary: {hot_news.get("summary") or ""}

Source URLs:
{source_lines}

Platforms:
{platform_lines}
"""

    def prepare_hot_news_monitoring(
        self,
        *,
        batch_date: str,
        title: str,
        source_urls: list[str],
        discovery_timestamp: str | None = None,
        platforms: list[str] | None = None,
        summary: str = "",
        queue_type: str = "SOCIAL_HOT_DRAFT",
        editorial_metadata: dict[str, Any] | None = None,
        create_placeholder_drafts: bool = True,
    ) -> dict[str, Any]:
        resolved = batch_date if _looks_like_iso_date(batch_date) else date.today().isoformat()
        platform_list = _normalize_platforms(platforms or HOT_NEWS_MONITORING_PLATFORMS)
        slug = "hot-news-" + _monitoring_slug(title)
        discovery = discovery_timestamp or now_iso()
        package = self.hot_news_monitoring_package(
            title=title,
            batch_date=resolved,
            source_urls=source_urls,
            discovery_timestamp=discovery,
            platforms=platform_list,
            summary=summary,
            queue_type=queue_type,
            editorial_metadata=editorial_metadata,
        )
        article_dir = self.draft_root / resolved / slug
        _write_json(article_dir / "source_package.json", package)
        (article_dir / "CODEX_SOCIAL_WRITING_PROMPT.md").write_text(
            self.hot_news_monitoring_prompt(package),
            encoding="utf-8",
        )
        seed_article = PublishedArticle(
            article_id=slug,
            title=title,
            url=package["hot_news"]["source_urls"][0],
            description=summary,
            image="",
            tags=[],
            publish_date="",
            canonical_url=package["hot_news"]["source_urls"][0],
        )
        asset_manifest = self.generate_social_assets(seed_article, batch_date=resolved)
        asset_outputs = asset_manifest.get("outputs", {}) if isinstance(asset_manifest, dict) else {}
        source_text = "\n".join(package["hot_news"]["source_urls"])
        for platform in platform_list:
            platform_dir = article_dir / platform
            platform_dir.mkdir(parents=True, exist_ok=True)
            starter = _hot_news_starter_drafts(
                title=title,
                summary=summary,
                source_urls=package["hot_news"]["source_urls"],
                discovery_timestamp=discovery,
                platform=platform,
            )
            asset_info = asset_outputs.get(_safe_asset_name(platform), {}) if isinstance(asset_outputs, dict) else {}
            platform_image_path = str(asset_info.get("local_path") or asset_outputs.get("og", {}).get("local_path") or "")
            if create_placeholder_drafts:
                for filename, content in starter["drafts"].items():
                    (platform_dir / filename).write_text(content, encoding="utf-8")
            _write_json(
                platform_dir / "metadata.json",
                {
                    "status": "needs_social_review" if create_placeholder_drafts else "needs_social_draft",
                    "selected_variant": "A.md",
                    "queue_type": queue_type,
                    "content_lane": SOCIAL_HOT_UNCONFIRMED,
                    "workflow": "HOT_NEWS_MONITORING",
                    "article_slug": slug,
                    "platform": platform,
                    "title": starter["title"],
                    "source_title": title,
                    "source_url": package["hot_news"]["source_urls"][0],
                    "source_urls": package["hot_news"]["source_urls"],
                    "website_url": "",
                    "canonical_url": "",
                    "image_url": "",
                    "local_image_path": platform_image_path,
                    "platform_image_path": platform_image_path,
                    "CTA": starter["cta"],
                    "cta": starter["cta"],
                    "hashtags": starter["hashtags"],
                    "discovery_timestamp": discovery,
                    "confirmation_status": "unconfirmed",
                    "editorial_selection": dict(editorial_metadata or {}),
                    "validation_warnings": [
                        "Unconfirmed hot-news monitoring draft. Do not add a website URL unless a website article is later published."
                    ],
                    "created_at": now_iso(),
                },
            )
        manifest_path = self.draft_root / resolved / "manifest.json"
        manifest = read_json(manifest_path, {})
        if not isinstance(manifest, dict):
            manifest = {}
        items = manifest.get("items") if isinstance(manifest.get("items"), list) else []
        items = [item for item in items if not (isinstance(item, dict) and item.get("slug") == slug)]
        items.append(
            {
                "slug": slug,
                "title": title,
                "url": "",
                "content_lane": SOCIAL_HOT_UNCONFIRMED,
                "queue_type": queue_type,
                "workflow": "HOT_NEWS_MONITORING",
                "status": "writing_package_ready" if create_placeholder_drafts else "needs_social_draft",
                "platforms": platform_list,
                "source_package": str(article_dir / "source_package.json"),
                "prompt": str(article_dir / "CODEX_SOCIAL_WRITING_PROMPT.md"),
                "editorial_selection": dict(editorial_metadata or {}),
            }
        )
        manifest.update(
            {
                "schema_version": 1,
                "batch_date": resolved,
                "status": "social_writing_package_ready",
                "workflow_contracts": sorted(
                    set(list(manifest.get("workflow_contracts") or []) + ["HOT_NEWS_MONITORING"])
                ),
                "items": items,
            }
        )
        _write_json(manifest_path, manifest)
        return manifest

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
        resolved = str(payload.get("batch_date") or "")
        data_json = data_json or json.dumps(payload, ensure_ascii=False)
        return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Social Review Dashboard - {html.escape(resolved)}</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    :root {{ --ink:#102033; --muted:#607086; --line:#dbe5f1; --soft:#f6f8fb; --accent:#0f766e; --warn:#a16207; --bad:#b91c1c; --good:#15803d; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; font-family: Arial, sans-serif; color:var(--ink); background:#eef3f8; }}
    header {{ padding:18px 24px; background:#fff; border-bottom:1px solid var(--line); display:flex; gap:14px; align-items:flex-start; justify-content:space-between; }}
    .header-actions {{ display:flex; gap:8px; flex-wrap:wrap; justify-content:flex-end; }}
    h1 {{ margin:0 0 5px; font-size:26px; }}
    .muted {{ color:var(--muted); }}
    .layout {{ display:grid; grid-template-columns:minmax(280px, 340px) minmax(0, 1fr); gap:16px; padding:16px; min-height:calc(100vh - 86px); }}
    aside,.panel {{ background:#fff; border:1px solid var(--line); border-radius:8px; }}
    aside {{ overflow:auto; max-height:calc(100vh - 116px); }}
    .filters {{ position:sticky; top:0; z-index:2; background:#fff; border-bottom:1px solid var(--line); padding:12px; }}
    .filters input,.filters select {{ width:100%; margin:5px 0; padding:8px; border:1px solid var(--line); border-radius:6px; }}
    .article-group {{ border-bottom:1px solid var(--line); padding:10px 10px 12px; }}
    .article-title {{ font-weight:800; margin-bottom:6px; line-height:1.35; }}
    .nav-item {{ display:flex; gap:8px; align-items:center; justify-content:space-between; width:100%; border:1px solid transparent; background:#fff; padding:8px; border-radius:6px; text-align:left; cursor:pointer; color:var(--ink); }}
    .nav-item:hover,.nav-item.active {{ border-color:#93c5fd; background:#f0f7ff; }}
    .badge {{ display:inline-flex; align-items:center; border-radius:999px; padding:3px 8px; font-size:12px; font-weight:800; white-space:nowrap; background:#edf2f7; color:#334155; }}
    .status-approved_for_copy,.status-published_manual {{ background:#dcfce7; color:#166534; }}
    .status-revision_requested,.status-not_recommended {{ background:#fef3c7; color:#92400e; }}
    .status-rejected,.status-failed {{ background:#fee2e2; color:#991b1b; }}
    .panel {{ padding:18px; overflow:auto; }}
    .topline {{ display:flex; gap:10px; flex-wrap:wrap; align-items:center; }}
    .grid {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:10px; margin:14px 0; }}
    .field {{ border:1px solid var(--line); border-radius:8px; padding:10px; background:var(--soft); }}
    .field strong {{ display:block; font-size:12px; color:var(--muted); text-transform:uppercase; margin-bottom:5px; }}
    .draft-body {{ white-space:pre-wrap; line-height:1.55; border:1px solid var(--line); border-radius:8px; padding:14px; background:#fff; }}
    .blogger-article-preview {{ line-height:1.6; border:1px solid var(--line); border-radius:8px; padding:16px; background:#fff; }}
    .blogger-article-preview h2 {{ margin:20px 0 8px; font-size:22px; line-height:1.25; }}
    .blogger-article-preview h3 {{ margin:16px 0 8px; font-size:18px; line-height:1.3; }}
    .blogger-article-preview p {{ margin:0 0 14px; }}
    .blogger-article-preview ul,.blogger-article-preview ol {{ margin:0 0 16px 22px; padding:0; }}
    .callout {{ background:#ecfdf5; border-color:#99f6e4; color:#064e3b; }}
    .preview-card {{ border:1px solid var(--line); border-radius:8px; padding:14px; background:#fbfdff; margin:12px 0; }}
    .preview-card img {{ max-width:100%; max-height:260px; border-radius:8px; border:1px solid var(--line); object-fit:cover; }}
    .actions {{ display:flex; gap:8px; flex-wrap:wrap; margin:12px 0; }}
    button, a.button {{ padding:8px 11px; border:1px solid #c7d2e1; background:#fff; border-radius:7px; color:var(--ink); font-weight:700; cursor:pointer; text-decoration:none; display:inline-block; }}
    button.primary {{ background:#0f766e; border-color:#0f766e; color:#fff; }}
    button.danger {{ border-color:#fecaca; color:#991b1b; background:#fff5f5; }}
    textarea,input {{ width:100%; border:1px solid var(--line); border-radius:7px; padding:9px; font:inherit; }}
    textarea {{ min-height:220px; font-family:Arial, sans-serif; line-height:1.5; }}
    .edit {{ display:none; }}
    .editing .preview {{ display:none; }}
    .editing .edit {{ display:block; }}
    details {{ margin-top:14px; }}
    code {{ white-space:pre-wrap; overflow-wrap:anywhere; }}
    .notice {{ padding:10px; border-radius:7px; background:#ecfdf5; color:#065f46; margin:10px 0; display:none; }}
    .empty {{ padding:32px; }}
    @media(max-width:820px) {{ .layout {{ grid-template-columns:1fr; }} aside {{ max-height:none; }} .grid {{ grid-template-columns:1fr; }} }}
  </style>
</head>
<body>
  <header>
    <div>
      <h1>Social Review Dashboard - {html.escape(resolved)}</h1>
      <div class="muted">Manual-only workflow. Review, edit, approve for copy, then use Menu E for manual publishing.</div>
    </div>
    <div class="header-actions">
      <button onclick="backToRunbot()">Back to Runbot Menu</button>
      <button class="danger" onclick="closeDashboardServer()">Close Dashboard Server</button>
    </div>
  </header>
  <main class="layout">
    <aside>
      <div class="filters">
        <input id="search" placeholder="Search article or platform">
        <select id="statusFilter">
          <option value="all">All</option>
          <option value="needs_social_review">Needs Review</option>
          <option value="approved_for_copy">Approved for Copy</option>
          <option value="pending_manual_publish">Pending Manual Publish</option>
          <option value="revision_requested">Revision Requested</option>
          <option value="rejected">Rejected</option>
          <option value="not_recommended">Not Recommended</option>
          <option value="published_manual">Published Manual</option>
        </select>
        <select id="platformFilter"><option value="all">All platforms</option></select>
        <select id="languageFilter"><option value="all">All languages</option><option value="en">English</option><option value="vi">Vietnamese</option></select>
      </div>
      <nav id="nav"></nav>
    </aside>
    <section class="panel" id="detail"><div class="empty">Select an article/platform draft from the left pane.</div></section>
  </main>
  <script id="dashboard-data" type="application/json">{html.escape(data_json, quote=False)}</script>
  <script>
    const DATA = JSON.parse(document.getElementById('dashboard-data').textContent);
    const API = window.location.protocol === 'file:' ? null : '/api/social';
    let selected = null;
    const statusLabels = DATA.status_options || {{}};
    function h(v) {{ return String(v ?? '').replace(/[&<>"']/g, c => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c])); }}
    function allDrafts() {{ return DATA.items.flatMap(article => article.platforms.map(p => ({{...p, article_title: article.title, article_url: article.url}}))); }}
    function cleanPlatformOptions() {{
      const select = document.getElementById('platformFilter');
      [...new Set(allDrafts().map(p => p.platform))].sort().forEach(platform => {{
        const opt = document.createElement('option'); opt.value = platform; opt.textContent = allDrafts().find(p => p.platform === platform)?.platform_label || platform; select.appendChild(opt);
      }});
    }}
    function filteredDrafts(article) {{
      const q = document.getElementById('search').value.toLowerCase();
      const s = document.getElementById('statusFilter').value;
      const p = document.getElementById('platformFilter').value;
      const l = document.getElementById('languageFilter').value;
      return article.platforms.filter(d => {{
        const hay = `${{article.title}} ${{d.platform_label}} ${{d.title}} ${{d.body}}`.toLowerCase();
        return (!q || hay.includes(q)) && (s === 'all' || d.status === s) && (p === 'all' || d.platform === p) && (l === 'all' || d.language === l);
      }});
    }}
    function renderNav() {{
      const nav = document.getElementById('nav');
      nav.innerHTML = '';
      DATA.items.forEach(article => {{
        const drafts = filteredDrafts(article);
        if (!drafts.length) return;
        const group = document.createElement('div');
        group.className = 'article-group';
        group.innerHTML = `<div class="article-title">${{h(article.title)}}</div>`;
        drafts.forEach(d => {{
          const btn = document.createElement('button');
          btn.className = 'nav-item' + (selected && selected.slug === d.slug && selected.platform === d.platform ? ' active' : '');
          btn.innerHTML = `<span>${{h(d.platform_label)}}</span><span class="badge status-${{h(d.status)}}">${{h(d.status_label)}}</span>`;
          btn.onclick = () => {{ selected = d; renderNav(); renderDetail(d); }};
          group.appendChild(btn);
        }});
        nav.appendChild(group);
      }});
    }}
    function fallbackHashtags(d) {{
      const text = `${{d.article_title || ''}} ${{d.source_title || ''}} ${{d.body || ''}}`.toLowerCase();
      const tags = ['#AI'];
      if (text.includes('marketing')) tags.push('#MarketingAutomation');
      if (text.includes('automation')) tags.push('#Automation');
      if (text.includes('ifttt')) tags.push('#IFTTT');
      if (text.includes('saas') || text.includes('software')) tags.push('#SaaS');
      if (text.includes('workflow')) tags.push('#Workflow');
      if (text.includes('small business')) tags.push('#SmallBusiness');
      return [...new Set(tags)].slice(0, 5).join(' ');
    }}
    function tagsText(d) {{
      const raw = Array.isArray(d.hashtags) ? d.hashtags.join(' ') : String(d.hashtags || '');
      return raw.trim() || fallbackHashtags(d);
    }}
    function stripDraftHeading(text) {{
      return String(text || '').replace(/^#\\s+[^\\n]+\\n+/,'').trim();
    }}
    function cleanTitle(d) {{
      const title = String(d.title || '').trim();
      if (!title || /draft$/i.test(title) || / draft$/i.test(title) || /^quora answer draft$/i.test(title) || /^x draft$/i.test(title)) {{
        return String(d.source_title || d.article_title || '').trim();
      }}
      return title;
    }}
    function extractLine(text, prefix) {{
      const escaped = prefix.replace(/[.*+?^${{}}()|[\\]\\\\]/g, '\\\\$&');
      const m = String(text || '').match(new RegExp('^' + escaped + '\\\\s*(.+)$', 'mi'));
      return m ? m[1].trim() : '';
    }}
    function appendIfMissing(text, value) {{
      const clean = String(value || '').trim();
      if (!clean || String(text || '').includes(clean)) return String(text || '').trim();
      return `${{String(text || '').trim()}}\\n\\n${{clean}}`.trim();
    }}
    function appendLinkBlock(text, label, url) {{
      const cleanUrl = String(url || '').trim();
      let cleanText = String(text || '').trim();
      if (!cleanUrl || cleanText.includes(cleanUrl)) return cleanText;
      return `${{cleanText}}\\n\\n${{label}}\\n${{cleanUrl}}`.trim();
    }}
    function escapeRegExp(value) {{
      return String(value || '').replace(/[.*+?^${{}}()|[\\]\\\\]/g, '\\\\$&');
    }}
    function removeSourceUrlBlocks(text, url) {{
      const cleanUrl = String(url || '').trim();
      let body = String(text || '').trim();
      if (!cleanUrl) return body;
      const escaped = escapeRegExp(cleanUrl);
      [
        new RegExp('^This adapted draft[^\\n]*canonical[^\\n]*:\\\\s*\\n' + escaped + '\\\\s*$', 'gmi'),
        new RegExp('^The complete article[^\\n]*canonical[^\\n]*:\\\\s*\\n' + escaped + '\\\\s*$', 'gmi'),
        new RegExp('^Read the full source article:\\\\s*\\n' + escaped + '\\\\s*$', 'gmi'),
        new RegExp('^Read the full source article:\\\\s*' + escaped + '\\\\s*$', 'gmi'),
        new RegExp('^I wrote a more detailed[^\\n]*' + escaped + '\\\\s*$', 'gmi'),
        new RegExp('^Read the full guide here:\\\\s*\\n' + escaped + '\\\\s*$', 'gmi'),
        new RegExp('^Read the full guide here:\\\\s*' + escaped + '\\\\s*$', 'gmi'),
        new RegExp('^' + escaped + '\\\\s*$', 'gmi')
      ].forEach(pattern => {{ body = body.replace(pattern, ''); }});
      return body.replace(/\\n{{3,}}/g, '\\n\\n').trim();
    }}
    function platformTags(d) {{
      return tagsText(d).replace(/#/g, '').split(/\\s+/).map(t => t.trim().toLowerCase()).filter(Boolean).slice(0, 4).join(', ');
    }}
    function imageWarning(d) {{
      const url = String(d.image_url || '').trim();
      const local = String(d.platform_image_path || d.local_image_path || '').trim();
      if (!url && !local) return 'No image is available for this draft.';
      if (/\\.svg($|\\?)/i.test(url)) return local ? `The website image is SVG, which some social platforms do not render. Use Copy Local Image File and upload this PNG manually: ${{local}}` : 'This image is SVG. Some social platforms do not render SVG previews; use Copy Image URL for manual upload or replace with a PNG/WebP social card.';
      return '';
    }}
    function assetUrl(d, download=false) {{
      const filename = d.platform_image_filename || 'og.png';
      if (!filename) return '';
      const url = `/assets/${{encodeURIComponent(d.batch_date)}}/${{encodeURIComponent(d.slug)}}/${{encodeURIComponent(filename)}}`;
      return download ? `${{url}}?download=1` : url;
    }}
    function cleanShortSocialBody(d) {{
      let body = stripDraftHeading(d.body)
        .replace(/^Title:\\s*/gmi, '')
        .replace(/\\n{{3,}}/g, '\\n\\n')
        .trim();
      body = appendLinkBlock(body, 'Read the full article:', d.source_url);
      const tags = tagsText(d);
      if (tags && !body.includes(tags)) body = `${{body}}\\n\\n${{tags}}`;
      return body.trim();
    }}
    function cleanPinterestText(d) {{
      const pinTitle = d.pin_title || cleanTitle(d);
      const description = d.pin_description || stripDraftHeading(d.body);
      const board = d.suggested_board || 'AI Tools Comparison';
      const keywords = Array.isArray(d.keywords) ? d.keywords.join('\\n') : String(d.keywords || '');
      const alt = d.alt_text || `Pinterest graphic for ${{pinTitle}}.`;
      return [
        'PIN TITLE',
        pinTitle,
        'PIN DESCRIPTION',
        description,
        'DESTINATION URL',
        d.destination_url || d.source_url,
        'SUGGESTED BOARD',
        board,
        'ALT TEXT',
        alt,
        'KEYWORDS',
        keywords
      ].filter(Boolean).join('\\n\\n');
    }}
    function pinterestField(d, field) {{
      if (field === 'pin_title') return d.pin_title || cleanTitle(d);
      if (field === 'pin_description') return d.pin_description || stripDraftHeading(d.body);
      if (field === 'destination_url') return d.destination_url || d.source_url;
      if (field === 'suggested_board') return d.suggested_board || 'AI Tools Comparison';
      if (field === 'keywords') return Array.isArray(d.keywords) ? d.keywords.join('\\n') : String(d.keywords || '');
      if (field === 'alt_text') return d.alt_text || `Pinterest graphic for ${{d.pin_title || cleanTitle(d)}}.`;
      if (field === 'image_path') return d.platform_image_path || d.local_image_path || '';
      return cleanPinterestText(d);
    }}
    function bloggerLabels(d) {{
      return Array.isArray(d.labels) ? d.labels.join(', ') : String(d.labels || tagsText(d));
    }}
    function cleanBloggerText(d) {{
      return String(d.plain_text_body || d.body || '')
        .replace(/^#\\s+.+$/m, '')
        .replace(/^Search description:\\s*.+$/gmi, '')
        .replace(/^Labels:\\s*.+$/gmi, '')
        .replace(/^Recommended permalink slug:\\s*.+$/gmi, '')
        .replace(/<a\\s+[^>]*>(.*?)<\\/a>/gi, '$1')
        .replace(/<\\/?[a-z][^>]*>/gi, '')
        .replace(/\\n{{3,}}/g, '\\n\\n')
        .trim();
    }}
    function bloggerField(d, field) {{
      if (field === 'blogger_title') return d.blogger_title || d.title || '';
      if (field === 'search_description') return d.search_description || '';
      if (field === 'labels') return bloggerLabels(d);
      if (field === 'plain_text_body') return cleanBloggerText(d);
      if (field === 'html_body') return d.html_body || '';
      if (field === 'website_url') return d.source_article_url || d.source_url || '';
      if (field === 'permalink_slug') return d.recommended_permalink_slug || '';
      if (field === 'alt_text') return d.image_alt_text || '';
      if (field === 'image_path') return d.image_path || d.platform_image_path || d.local_image_path || '';
      return cleanBloggerText(d);
    }}
    function bloggerArticlePreviewHtml(d) {{
      const heading2 = new Set([
        'introduction',
        'why this comparison matters',
        'who should read this',
        'how to evaluate marketing automation software',
        'how to evaluate new ai tools by ifttt',
        'key buying checklist',
        'pricing considerations',
        'workflow examples',
        'pros',
        'cons',
        'alternatives',
        'common mistakes',
        'frequently asked questions',
        'final recommendation',
        'what to evaluate before choosing',
        'where the source article helps',
        'practical criteria for small teams',
        'who this is suitable for',
        'who should be cautious',
        'recommended decision workflow',
        'how to use the source guide',
        'common mistakes to avoid',
        'simple implementation notes',
        'conclusion',
        'disclosure'
      ]);
      const heading3 = new Set(['key takeaway', 'verification methods']);
      const blocks = cleanBloggerText(d).split(/\\n\\s*\\n/).map(x => x.trim()).filter(Boolean);
      return blocks.map(block => {{
        const lowered = block.toLowerCase();
        if (heading2.has(lowered)) return `<h2>${{h(block)}}</h2>`;
        if (heading3.has(lowered)) return `<div class="field callout"><strong>${{h(block)}}</strong></div>`;
        if (block.endsWith('?')) return `<h3>${{h(block)}}</h3>`;
        const lines = block.split('\\n').map(x => x.trim()).filter(Boolean);
        if (lines.length > 1 && lines.every(line => /^[-*]\\s+/.test(line))) {{
          return `<ul>${{lines.map(line => `<li>${{h(line.replace(/^[-*]\\s+/, ''))}}</li>`).join('')}}</ul>`;
        }}
        if (lines.length > 1 && lines.every(line => /^\\d+[.)]\\s+/.test(line))) {{
          return `<ol>${{lines.map(line => `<li>${{h(line.replace(/^\\d+[.)]\\s+/, ''))}}</li>`).join('')}}</ol>`;
        }}
        return `<p>${{h(block)}}</p>`;
      }}).join('');
    }}
    function blueskyField(d, field) {{
      const posts = Array.isArray(d.thread_posts) ? d.thread_posts : [];
      if (field === 'standalone_post') return d.standalone_post || d.body || '';
      if (field === 'full_thread') return posts.join('\\n\\n');
      if (field.startsWith('thread_post_')) {{
        const n = Number(field.replace('thread_post_', '')) - 1;
        return posts[n] || '';
      }}
      if (field === 'website_url') return d.article_url || d.source_url || '';
      if (field === 'alt_text') return d.image_alt_text || '';
      if (field === 'image_path') return d.image_path || d.platform_image_path || d.local_image_path || '';
      return [d.standalone_post || d.body || '', posts.join('\\n\\n')].filter(Boolean).join('\\n\\n');
    }}
    function cleanQuoraAnswer(d) {{
      let body = stripDraftHeading(d.body);
      const question = extractLine(body, 'Suggested Quora question:') || extractLine(body, 'Suggested question:') || d.title;
      body = body
        .replace(/^Suggested Quora question:\\s*.+$/gmi, '')
        .replace(/^Suggested question:\\s*.+$/gmi, '')
        .replace(/^Answer title\\/opening:\\s*/gmi, '')
        .replace(/^Full answer body:\\s*$/gmi, '')
        .replace(/^I wrote a more detailed.*$/gmi, '')
        .replace(/^Website source URL:\\s*.+$/gmi, '')
        .replace(/^Source link:\\s*.+$/gmi, '')
        .replace(/^Disclosure:\\s*.+$/gmi, '')
        .replace(/\\n{{3,}}/g, '\\n\\n')
        .trim();
      body = removeSourceUrlBlocks(body, d.source_url);
      const disclosure = d.affiliate_disclosure
        ? `Disclosure: ${{d.affiliate_disclosure}}`
        : 'Disclosure: I am linking to an independent Smile AI Review Hub article.';
      const tags = tagsText(d);
      return [
        `Suggested question: ${{question}}`,
        body,
        'Read the full guide here:',
        d.source_url,
        disclosure,
        tags ? `Tags: ${{tags}}` : ''
      ].filter(Boolean).join('\\n\\n');
    }}
    function cleanLongFormBody(d) {{
      return stripDraftHeading(d.body)
        .replace(/^Canonical URL instruction.*$/gmi, '')
        .replace(/^Read the original review:\\s*.+$/gmi, '')
        .replace(/^Full original guide:\\s*.+$/gmi, '')
        .replace(/^Full review:\\s*.+$/gmi, '')
        .replace(/^Canonical URL note:\\s*.+$/gmi, '')
        .replace(/\\n{{3,}}/g, '\\n\\n')
        .trim();
    }}
    function cleanDevToBody(d) {{
      let body = removeSourceUrlBlocks(cleanLongFormBody(d), d.source_url);
      body = appendLinkBlock(body, 'Read the full source article:', d.source_url);
      const tags = tagsText(d);
      if (tags && !body.includes(tags)) body = `${{body}}\\n\\n${{tags}}`;
      return body.trim();
    }}
    function cleanLongFormPostBody(d) {{
      let body = removeSourceUrlBlocks(cleanLongFormBody(d), d.source_url);
      body = appendLinkBlock(body, 'Read the full source article:', d.source_url);
      const tags = tagsText(d);
      if (tags && !body.includes(tags)) body = `${{body}}\\n\\nTags: ${{tags}}`;
      if (d.affiliate_disclosure && !body.includes(d.affiliate_disclosure)) body = `${{body}}\\n\\nDisclosure: ${{d.affiliate_disclosure}}`;
      return body.trim();
    }}
    function cleanDevToDraft(d) {{
      const tags = platformTags(d);
      const frontMatter = [
        '---',
        `title: "${{cleanTitle(d).replace(/"/g, '\\\\"')}}"`,
        'published: false',
        d.canonical_url ? `canonical_url: ${{d.canonical_url}}` : '',
        d.image_url && !/\\.svg($|\\?)/i.test(d.image_url) ? `cover_image: ${{d.image_url}}` : '',
        tags ? `tags: ${{tags}}` : '',
        '---'
      ].filter(Boolean).join('\\n');
      const body = cleanDevToBody(d);
      const note = imageWarning(d);
      return [
        frontMatter,
        body,
        d.affiliate_disclosure ? `Disclosure: ${{d.affiliate_disclosure}}` : ''
      ].filter(Boolean).join('\\n\\n');
    }}
    function cleanProductHuntText(d) {{
      let body = stripDraftHeading(d.body)
        .replace(/^Discussion title:\\s*/gmi, '')
        .replace(/^Concise introduction:\\s*/gmi, '')
        .replace(/^Website source URL:\\s*.+$/gmi, '')
        .replace(/^Disclosure:\\s*.+$/gmi, '')
        .replace(/\\n{{3,}}/g, '\\n\\n')
        .trim();
      return [
        cleanTitle(d),
        body,
        'Read more:',
        d.source_url,
        d.affiliate_disclosure ? `Disclosure: ${{d.affiliate_disclosure}}` : '',
        tagsText(d)
      ].filter(Boolean).join('\\n\\n');
    }}
    function copyAllText(d) {{
      const tags = tagsText(d);
      if (d.platform === 'pinterest') return cleanPinterestText(d);
      if (d.platform === 'blogger') return bloggerField(d, 'all');
      if (d.platform === 'bluesky') return blueskyField(d, 'all');
      if (d.platform === 'quora') return cleanQuoraAnswer(d);
      if (d.platform === 'producthunt') return cleanProductHuntText(d);
      if (d.platform === 'devto') return cleanDevToDraft(d);
      if (['medium','hashnode','blogger'].includes(d.platform)) return [`Title: ${{cleanTitle(d)}}`, cleanLongFormPostBody(d)].filter(Boolean).join('\\n\\n');
      return cleanShortSocialBody(d);
    }}
    function pinterestPanel(d) {{
      if (d.platform !== 'pinterest') return '';
      const keywords = Array.isArray(d.keywords) ? d.keywords.join(', ') : String(d.keywords || '');
      const published = d.final_published_url || '';
      const publishedActions = published
        ? `<button onclick="window.open('${{h(published)}}', '_blank', 'noopener,noreferrer')">Open Published Pin</button><button onclick="copyPublishedPinUrl()">Copy Published Pin URL</button><button class="danger" onclick="resetPinterestPublished()">Reset Published Status</button>`
        : `<button disabled>Open Published Pin</button><button disabled>Copy Published Pin URL</button>`;
      return `
        <div class="field"><strong>Pinterest manual checklist</strong>
          <ol>
            <li>Upload pinterest.png</li>
            <li>Paste Pin Title</li>
            <li>Paste Pin Description</li>
            <li>Paste Destination URL</li>
            <li>Select Suggested Board</li>
            <li>Add Alt Text if available</li>
            <li>Publish manually</li>
            <li>Paste the final Pinterest Pin URL below</li>
          </ol>
        </div>
        <div class="grid">
          <div class="field"><strong>Pin Title</strong>${{h(d.pin_title || cleanTitle(d))}}</div>
          <div class="field"><strong>Destination URL</strong>${{h(d.destination_url || d.source_url)}}</div>
          <div class="field"><strong>Suggested Board</strong>${{h(d.suggested_board || 'AI Tools Comparison')}}</div>
          <div class="field"><strong>Keywords</strong>${{h(keywords)}}</div>
          <div class="field"><strong>Alt Text</strong>${{h(d.alt_text || '')}}</div>
          <div class="field"><strong>Overlay Text</strong>${{h(d.overlay_text || '')}}</div>
        </div>
        <div class="field"><strong>Pin Description Only</strong><div class="draft-body">${{h(d.pin_description || d.body || '')}}</div></div>
        <div class="field">
          <strong>Post-publication</strong>
          <div class="grid">
            <div><strong>Published status</strong><br><span class="badge status-${{h(d.status)}}">${{h(d.status_label)}}</span></div>
            <div><strong>Published at</strong><br>${{h(d.published_at || '-')}}</div>
            <div><strong>Validation</strong><br>${{h(d.final_url_validation_message || '-')}}</div>
            <div><strong>Published URL</strong><br>${{published ? `<a href="${{h(published)}}" target="_blank" rel="noopener noreferrer">${{h(published)}}</a>` : '-'}}</div>
          </div>
          <label>Final Pinterest URL<input id="finalPinterestUrl" value="${{h(published)}}" placeholder="https://www.pinterest.com/pin/1098526534136812938/"></label>
          <div class="actions"><button class="primary" onclick="savePinterestUrl()">Save Pinterest URL</button><button onclick="markPinterestPending()">Mark Pending</button>${{publishedActions}}</div>
        </div>
      `;
    }}
    function bloggerPanel(d) {{
      if (d.platform !== 'blogger') return '';
      return `
        <div class="topline"><h2>${{h(d.blogger_title || d.title || '')}}</h2><span class="badge">${{h(d.platform_label)}}</span><span class="badge status-${{h(d.status)}}">${{h(d.status_label)}}</span></div>
        <div class="grid">
          <div class="field"><strong>SEO score</strong>${{h(d.seo_score || 0)}}/100</div>
          <div class="field"><strong>Estimated reading time</strong>${{h(d.estimated_reading_time_minutes || 0)}} min</div>
          <div class="field"><strong>Search description</strong>${{h(d.search_description || '')}}</div>
          <div class="field"><strong>Labels</strong>${{h(bloggerLabels(d))}}</div>
          <div class="field"><strong>Recommended permalink slug</strong>${{h(d.recommended_permalink_slug || '')}}</div>
          <div class="field"><strong>Word count</strong>${{h(d.blogger_word_count || 0)}}</div>
          <div class="field"><strong>Heading count</strong>${{h(d.heading_count || 0)}}</div>
          <div class="field"><strong>FAQ count</strong>${{h(d.faq_count || 0)}}</div>
          <div class="field"><strong>Internal links</strong>${{h(d.internal_link_count || 0)}}</div>
          <div class="field"><strong>External links</strong>${{h(d.external_link_count || 0)}}</div>
          <div class="field"><strong>JSON-LD status</strong>${{h(d.json_ld_status || 'missing')}}</div>
          <div class="field"><strong>Source website URL</strong>${{h(d.source_article_url || d.source_url || '')}}</div>
          <div class="field"><strong>Alt text</strong>${{h(d.image_alt_text || '')}}</div>
          <div class="field"><strong>Image caption</strong>${{h(d.image_caption || '')}}</div>
          <div class="field"><strong>Recommended image filename</strong>${{h(d.recommended_image_filename || '')}}</div>
          <div class="field"><strong>OpenGraph title</strong>${{h(d.open_graph_title || '')}}</div>
          <div class="field"><strong>OpenGraph description</strong>${{h(d.open_graph_description || '')}}</div>
          <div class="field"><strong>Twitter card description</strong>${{h(d.twitter_card_description || '')}}</div>
        </div>
        <div class="field"><strong>Article preview</strong><div class="blogger-article-preview">${{bloggerArticlePreviewHtml(d)}}</div></div>
        <details class="field"><summary><strong>HTML preview</strong></summary><textarea readonly>${{h(d.html_body || '')}}</textarea></details>
        <div class="field"><strong>Publishing assets</strong><div>Image file: <code>${{h(d.image_path || d.platform_image_path || d.local_image_path || '')}}</code></div></div>
        <div class="field"><strong>Disclosure</strong>${{h(d.disclosure || '')}}</div>
      `;
    }}
    function blueskyPanel(d) {{
      if (d.platform !== 'bluesky') return '';
      const posts = Array.isArray(d.thread_posts) ? d.thread_posts : [];
      const counts = d.character_counts || {{}};
      const postHtml = posts.map((post, index) => `<div class="field"><strong>Thread post ${{index + 1}} (${{post.length}}/${{d.bluesky_character_limit || 300}})</strong><div class="draft-body">${{h(post)}}</div></div>`).join('');
      return `
        <div class="field"><strong>Standalone post (${{h((d.standalone_post || d.body || '').length)}}/${{h(d.bluesky_character_limit || 300)}})</strong><div class="draft-body">${{h(d.standalone_post || d.body || '')}}</div></div>
        <div class="field"><strong>Thread version</strong>${{postHtml}}</div>
        <div class="grid">
          <div class="field"><strong>Website URL</strong>${{h(d.article_url || d.source_url || '')}}</div>
          <div class="field"><strong>Hashtags</strong>${{h(tagsText(d))}}</div>
          <div class="field"><strong>Alt text</strong>${{h(d.image_alt_text || '')}}</div>
          <div class="field"><strong>Character counts</strong>${{h(JSON.stringify(counts))}}</div>
        </div>
      `;
    }}
    function actionButtons(d) {{
      if (d.platform === 'pinterest') {{
        return `<button onclick="window.open(assetUrl(d), '_blank')">Open Image</button><a class="button" href="${{h(assetUrl(d, true))}}">Download PNG</a><button onclick="copyField('pin_title')">Copy Pin Title</button><button onclick="copyField('pin_description')">Copy Pin Description</button><button onclick="copyField('destination_url')">Copy Destination URL</button><button onclick="copyField('suggested_board')">Copy Suggested Board</button><button onclick="copyField('keywords')">Copy Keywords</button><button onclick="copyField('alt_text')">Copy Alt Text</button><button onclick="copyField('image_path')">Copy Image Path</button><button class="primary" onclick="copyField('all')">Copy All Fields</button>`;
      }}
      if (d.platform === 'blogger') {{
        return `<button onclick="window.open(assetUrl(d), '_blank')">Open Image</button><a class="button" href="${{h(assetUrl(d, true))}}">Download Image</a><button onclick="copyField('blogger_title')">Copy Blogger Title</button><button onclick="copyField('search_description')">Copy Search Description</button><button onclick="copyField('labels')">Copy Labels</button><button onclick="copyField('plain_text_body')">Copy Plain Text Body</button><button title="Paste only in Blogger HTML view" onclick="copyField('html_body')">Copy HTML (HTML mode only)</button><button onclick="copyField('website_url')">Copy Website URL</button><button onclick="copyField('permalink_slug')">Copy Permalink Slug</button><button onclick="copyField('alt_text')">Copy Alt Text</button><button class="primary" onclick="copyField('all')">Copy Compose Body</button>`;
      }}
      if (d.platform === 'bluesky') {{
        const threadButtons = (Array.isArray(d.thread_posts) ? d.thread_posts : []).map((_, index) => `<button onclick="copyField('thread_post_${{index + 1}}')">Copy Thread Post ${{index + 1}}</button>`).join('');
        return `<button onclick="window.open(assetUrl(d), '_blank')">Open Image</button><a class="button" href="${{h(assetUrl(d, true))}}">Download Image</a><button onclick="copyField('standalone_post')">Copy Standalone Post</button><button onclick="copyField('full_thread')">Copy Full Thread</button>${{threadButtons}}<button onclick="copyField('website_url')">Copy Website URL</button><button onclick="copyField('alt_text')">Copy Alt Text</button><button class="primary" onclick="copyField('all')">Copy Bluesky Package</button>`;
      }}
      const urlLabel = d.content_lane === 'SOCIAL_HOT_UNCONFIRMED' ? 'Copy Source URL' : 'Copy Website URL';
      return `<button onclick="window.open(assetUrl(d), '_blank')">Open Image</button><a class="button" href="${{h(assetUrl(d, true))}}">Download Image</a><button onclick="copyField('title')">Copy Title</button><button onclick="copyField('body')">Copy Body</button><button onclick="copyField('cta')">Copy CTA</button><button onclick="copyField('hashtags')">Copy Hashtags</button><button onclick="copyField('url')">${{urlLabel}}</button><button onclick="copyField('image')">Copy Image URL</button><button onclick="copyField('local_image')">Copy Image Path</button><button class="primary" onclick="copyField('all')">Copy All</button>`;
    }}
    function variantComparison(d) {{
      const variants = Array.isArray(d.variants) ? d.variants : [];
      if (!variants.length) return '';
      return `<div class="field"><strong>CONTENT COMPONENTS (read-only review aids)</strong><div class="grid">${{variants.map(v => {{
        const count = v.platform_limit ? `${{v.character_count}} / ${{v.platform_limit}}` : String(v.character_count);
        const invalid = v.platform_validation_status === 'INVALID_PLATFORM_LIMIT';
        return `<div class="field">
          <div class="topline"><strong>Component ${{h(v.label)}} · ${{h(v.variant_strategy)}}</strong></div>
          <div><strong>Today's angle:</strong> ${{h(d.today_social_angle || v.social_angle)}}</div>
          <div><strong>Characters:</strong> ${{h(count)}} · <strong>${{invalid ? 'INVALID_PLATFORM_LIMIT' : 'PASS'}}</strong></div>
          <div><strong>Evidence:</strong> ${{h((v.evidence_refs || []).length ? 'INHERITED' : d.evidence_status)}}</div>
          <div><strong>New claims:</strong> ${{h((v.new_claims || []).length ? 'EVIDENCE_REQUIRED' : 'PASS')}}</div>
          <div class="draft-body">${{h(v.text)}}</div>
        </div>`;
      }}).join('')}}</div></div>`;
    }}
    function renderDetail(d) {{
      document.getElementById('detail').className = 'panel';
      const over = ['x','twitter'].includes(d.platform) && d.character_count > 280 ? '<div class="field"><strong>Warning</strong>X draft is over 280 characters.</div>' : '';
      const imageSrc = assetUrl(d) || d.image_url;
      const img = imageSrc ? `<img src="${{h(imageSrc)}}" alt="" style="object-fit:contain;max-height:360px;width:100%;background:#f8fafc">` : '<span class="muted">No image available</span>';
      const warnings = (d.validation_warnings || []).map(w => `<li>${{h(w)}}</li>`).join('');
      const q = d.social_value_validation || {{}};
      const passWarn = value => value ? 'PASS' : 'WARN';
      const qualityDiagnostics = Object.keys(q).length ? `<div class="field"><strong>Social quality</strong>
        What happened: ${{passWarn(q.what_happened_present)}}<br>
        Why it matters: ${{passWarn(q.why_it_matters_present)}}<br>
        Practical takeaway: ${{passWarn(q.practical_takeaway_present)}}<br>
        Source rendering: ${{q.official_source_present ? 'PASS' : 'BLOCK'}}<br>
        Future promise: ${{q.unsupported_future_promise ? 'BLOCK' : 'PASS'}}<br>
        Generic-content risk: ${{h(q.generic_content_risk || 'LOW')}}<br>
        Value score: ${{h(q.value_score)}} / 100</div>` : '';
      const approveButton = d.approval_blocked
        ? `<button class="primary" disabled title="${{h((d.approval_block_reasons || []).join(', '))}}">Approval Blocked</button>`
        : `<button class="primary" onclick="setStatus('approved_for_copy', true)">Approve Final</button>`;
      const genericHeader = d.platform === 'blogger' ? '' : `<div class="topline"><h2>${{h(d.article_title)}}</h2><span class="badge status-${{h(d.status)}}">${{h(d.status_label)}}</span><span class="badge">${{h(d.platform_label)}}</span></div>`;
      const genericMetaGrid = d.platform === 'blogger' ? '' : `<div class="grid">
            <div class="field"><strong>Language</strong>${{h(d.language)}}</div>
            <div class="field"><strong>Character count</strong>${{h(d.character_count)}}</div>
            <div class="field"><strong>Official source</strong>${{h(d.official_source_name || 'Missing')}}<br><a href="${{h(d.official_source_url)}}" target="_blank">${{h(d.official_source_url)}}</a><br>Status: ${{h(d.source_status)}}</div>
            <div class="field"><strong>Canonical URL</strong><a href="${{h(d.canonical_url)}}" target="_blank">${{h(d.canonical_url)}}</a></div>
            <div class="field"><strong>Image asset</strong>${{h(d.platform_image_filename || '-')}} - ${{h(d.platform_image_width)}}x${{h(d.platform_image_height)}} - ${{h(d.platform_image_size)}} bytes - ${{h(d.asset_validation_status)}}</div>
          </div>`;
      const genericPreviewBody = d.platform === 'pinterest' ? (d.pin_description || d.body) : copyAllText(d);
      const genericPreview = d.platform === 'blogger' ? '' : `<div class="preview-card platform-${{h(d.platform)}}">${{img}}<h3>${{h(cleanTitle(d))}}</h3><div class="draft-body">${{h(genericPreviewBody)}}</div><p><strong>CTA:</strong> ${{h(d.cta)}}</p><p><strong>Hashtags/tags:</strong> ${{h(tagsText(d))}}</p>${{imageWarning(d) ? `<p class="notice" style="display:block"><strong>Image:</strong> ${{h(imageWarning(d))}}</p>` : ''}}</div>`;
      const bloggerImagePreview = d.platform === 'blogger' ? `<div class="preview-card platform-blogger">${{img}}${{imageWarning(d) ? `<p class="notice" style="display:block"><strong>Image:</strong> ${{h(imageWarning(d))}}</p>` : ''}}</div>` : '';
      document.getElementById('detail').innerHTML = `
        <div class="preview">
          ${{genericHeader}}
          <div id="notice" class="notice"></div>
          <div class="grid" style="${{d.platform === 'blogger' ? 'display:none' : ''}}">
            <div class="field"><strong>Language</strong>${{h(d.language)}}</div>
            <div class="field"><strong>Character count</strong>${{h(d.character_count)}}</div>
            <div class="field"><strong>Source website URL</strong><a href="${{h(d.source_url)}}" target="_blank">${{h(d.source_url)}}</a></div>
            <div class="field"><strong>Canonical URL</strong><a href="${{h(d.canonical_url)}}" target="_blank">${{h(d.canonical_url)}}</a></div>
            <div class="field"><strong>Image asset</strong>${{h(d.platform_image_filename || '-')}} · ${{h(d.platform_image_width)}}x${{h(d.platform_image_height)}} · ${{h(d.platform_image_size)}} bytes · ${{h(d.asset_validation_status)}}</div>
          </div>
          ${{bloggerImagePreview}}
          ${{variantComparison(d)}}
          <div class="field"><strong>FINAL ${{h(d.platform_label).toUpperCase()}} POST</strong><div class="draft-body">${{h(d.body || '')}}</div></div>
          ${{genericPreview}}
          ${{pinterestPanel(d)}}
          ${{bloggerPanel(d)}}
          ${{blueskyPanel(d)}}
          ${{over}}
          <div class="field"><strong>Validation warnings</strong>${{warnings ? `<ul>${{warnings}}</ul>` : 'None'}}</div>
          <div class="grid">
            <div class="field"><strong>Website Root</strong>${{h(d.root_title || d.root_topic_id || '-')}}</div>
            <div class="field"><strong>Source Article</strong>${{h(d.source_article_slug || d.slug)}}</div>
            <div class="field"><strong>Today's Social Angle</strong>${{h(d.today_social_angle || d.social_angle || '-')}}</div>
            <div class="field"><strong>Content Model</strong>${{h(d.content_model || '-')}}</div>
            <div class="field"><strong>Evidence Status</strong>${{h(d.evidence_status)}}</div>
            <div class="field"><strong>New Claim Status</strong>${{h(d.new_claim_status)}}</div>
            <div class="field"><strong>Visual Recommendation</strong>${{h(d.visual_recommended ? d.visual_type : 'NO_VISUAL')}}<br>${{h(d.visual_concept || '')}}</div>
          </div>
          ${{qualityDiagnostics}}
          <div class="field"><strong>Reviewer notes</strong><div class="draft-body">${{h(d.reviewer_notes || '')}}</div></div>
          <div class="actions">
            ${{actionButtons(d)}}
          </div>
          <div class="actions">
            <button onclick="startEdit()">Edit Final</button><button onclick="regenerateFinal()">Regenerate Final</button>${{approveButton}}<button class="danger" onclick="setStatus('rejected', true)">Reject Final</button><button onclick="setStatus('revision_requested', false)">Request Revision</button><button onclick="setStatus('not_recommended', true)">Mark Not Recommended</button><button onclick="setStatus('needs_social_review', false)">Reset to Needs Review</button>
          </div>
          <details><summary>Technical details</summary><p><strong>Created:</strong> ${{h(d.created_at) || '-'}}</p><p><strong>Updated:</strong> ${{h(d.updated_at) || '-'}}</p><p><strong>Draft:</strong> <code>${{h(d.draft_path)}}</code></p><p><strong>Metadata:</strong> <code>${{h(d.metadata_path)}}</code></p></details>
        </div>
        <div class="edit">
          <h2>Edit ${{h(d.platform_label)}} Draft</h2>
          <label>Title<input id="editTitle" value="${{h(d.title)}}"></label>
          <label>Body<textarea id="editBody">${{h(d.body)}}</textarea></label>
          <label>CTA<input id="editCta" value="${{h(d.cta)}}"></label>
          <label>Hashtags/tags<input id="editTags" value="${{h(tagsText(d))}}"></label>
          <label>Image URL<input id="editImage" value="${{h(d.image_url)}}"></label>
          <label>Reviewer notes<textarea id="editNotes">${{h(d.reviewer_notes || '')}}</textarea></label>
          <div class="actions"><button class="primary" onclick="saveEdit()">Save Changes</button><button onclick="cancelEdit()">Cancel Edit</button></div>
        </div>`;
    }}
    function selectedKey() {{ return {{date: DATA.batch_date, slug: selected.slug, platform: selected.platform}}; }}
    function show(msg) {{ const n = document.getElementById('notice'); if (n) {{ n.textContent = msg; n.style.display = 'block'; }} }}
    async function post(action, payload) {{
      if (!API) throw new Error('Open this dashboard through Menu G local server for write/copy actions.');
      const res = await fetch(`${{API}}/${{action}}`, {{method:'POST', headers:{{'Content-Type':'application/json; charset=utf-8'}}, body:JSON.stringify(payload)}});
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Request failed');
      return data;
    }}
    function backToRunbot() {{
      alert('Return to the already-running Runbot Menu window. Browsers cannot safely control the original CMD process.');
      try {{ window.close(); }} catch(e) {{}}
    }}
    async function closeDashboardServer() {{
      if (!confirm('Close only the local Social Review Dashboard server?')) return;
      try {{
        const data = await post('stop', {{date: DATA.batch_date, slug: selected?.slug || 'dashboard', platform: selected?.platform || 'dashboard'}});
        document.body.innerHTML = `<main class="panel" style="margin:32px"><h1>Dashboard server stopped</h1><p>${{h(data.message || 'Dashboard server stopped. You may close this browser tab and continue in Runbot Menu.')}}</p></main>`;
      }} catch(e) {{ alert(e.message); }}
    }}
    async function copyField(field) {{
      try {{
        let text = '';
        if (selected.platform === 'pinterest' && ['pin_title','pin_description','destination_url','suggested_board','keywords','alt_text','image_path'].includes(field)) text = pinterestField(selected, field);
        else if (selected.platform === 'pinterest' && field === 'body') text = pinterestField(selected, 'pin_description');
        else if (selected.platform === 'blogger' && ['blogger_title','search_description','labels','plain_text_body','html_body','website_url','permalink_slug','alt_text','image_path','all'].includes(field)) text = bloggerField(selected, field);
        else if (selected.platform === 'bluesky' && (['standalone_post','full_thread','website_url','alt_text','image_path','all'].includes(field) || field.startsWith('thread_post_'))) text = blueskyField(selected, field);
        else if (selected.platform === 'devto' && field === 'body') text = cleanDevToBody(selected);
        else if (['medium','hashnode'].includes(selected.platform) && field === 'body') text = cleanLongFormPostBody(selected);
        else if (selected.platform === 'producthunt' && field === 'body') text = cleanProductHuntText(selected);
        else if (field === 'title') text = selected.title;
        else if (field === 'body') text = selected.body;
        else if (field === 'cta') text = selected.cta;
        else if (field === 'hashtags') text = tagsText(selected);
        else if (field === 'url') text = selected.source_url;
        else if (field === 'image') text = selected.image_url && !/\\.svg($|\\?)/i.test(selected.image_url) ? selected.image_url : '';
        else if (field === 'local_image') text = selected.platform_image_path || selected.local_image_path || selected.image_url;
        else text = copyAllText(selected);
        try {{ await navigator.clipboard.writeText(text); show('Copied successfully'); }}
        catch (e) {{ const data = await post('copy', {{...selectedKey(), field, text}}); show(`Clipboard unavailable. UTF-8 file created at: ${{data.file_path}}`); }}
      }} catch (e) {{ alert(e.message); }}
    }}
    function startEdit() {{ document.getElementById('detail').classList.add('editing'); }}
    function cancelEdit() {{ document.getElementById('detail').classList.remove('editing'); }}
    async function saveEdit() {{
      try {{
        const data = await post('save', {{...selectedKey(), title:editTitle.value, body:editBody.value, cta:editCta.value, hashtags:editTags.value, image_url:editImage.value, reviewer_notes:editNotes.value}});
        Object.assign(selected, data.item);
        renderNav(); renderDetail(selected); show('Saved changes');
      }} catch(e) {{ alert(e.message); }}
    }}
    async function setStatus(status, confirmFirst) {{
      if (confirmFirst && !confirm(`Change status to ${{statusLabels[status] || status}}?`)) return;
      try {{
        const notes = selected.reviewer_notes || '';
        const data = await post('status', {{...selectedKey(), status, reviewer_notes: notes}});
        Object.assign(selected, data.item);
        renderNav(); renderDetail(selected); show('Status updated');
      }} catch(e) {{ alert(e.message); }}
    }}
    async function chooseVariant(variant, approve) {{
      if (approve && !confirm(`Approve variant ${{variant.replace('.md','')}} for copy?`)) return;
      try {{
        const data = await post('select-variant', {{...selectedKey(), variant, approve, reviewer_notes:selected.reviewer_notes || ''}});
        Object.assign(selected, data.item);
        renderNav(); renderDetail(selected); show(approve ? `Approved ${{variant}}` : `Selected ${{variant}}`);
      }} catch(e) {{ alert(e.message); }}
    }}
    async function regenerateFinal() {{
      if (!confirm('Recompose the final platform post from components A/B/C?')) return;
      try {{
        const data = await post('regenerate-final', {{...selectedKey(), reviewer_notes:selected.reviewer_notes || ''}});
        Object.assign(selected, data.item);
        renderNav(); renderDetail(selected); show('Final post recomposed from A/B/C.');
      }} catch(e) {{ alert(e.message); }}
    }}
    async function markPinterestPending() {{
      if (!selected || selected.platform !== 'pinterest') return;
      try {{
        const data = await post('pinterest-pending', selectedKey());
        Object.assign(selected, data.item);
        renderNav(); renderDetail(selected); show('Pinterest draft marked Pending Manual Publish');
      }} catch(e) {{ alert(e.message); }}
    }}
    async function savePinterestUrl() {{
      if (!selected || selected.platform !== 'pinterest') return;
      const input = document.getElementById('finalPinterestUrl');
      const url = (input?.value || '').trim();
      if (!url) {{ alert('Final Pinterest URL is required.'); return; }}
      if (!confirm('Confirm that this Pin has been published manually?')) return;
      try {{
        const data = await post('pinterest-published-url', {{...selectedKey(), final_published_url: url}});
        Object.assign(selected, data.item);
        renderNav(); renderDetail(selected); show('Pinterest URL saved. Status is Published Manual.');
      }} catch(e) {{ alert(e.message); }}
    }}
    async function copyPublishedPinUrl() {{
      if (!selected?.final_published_url) return;
      try {{
        await navigator.clipboard.writeText(selected.final_published_url);
        show('Published Pin URL copied');
      }} catch(e) {{
        const data = await post('copy', {{...selectedKey(), field:'final_published_url', text:selected.final_published_url}});
        show(`Clipboard unavailable. UTF-8 file created at: ${{data.file_path}}`);
      }}
    }}
    async function resetPinterestPublished() {{
      if (!selected || selected.platform !== 'pinterest') return;
      if (!confirm('Reset Published Manual status and clear the saved Pin URL?')) return;
      try {{
        const data = await post('pinterest-reset-published', {{...selectedKey(), confirmed:true}});
        Object.assign(selected, data.item);
        renderNav(); renderDetail(selected); show('Pinterest published status reset');
      }} catch(e) {{ alert(e.message); }}
    }}
    ['search','statusFilter','platformFilter','languageFilter'].forEach(id => document.addEventListener('input', e => {{ if (e.target.id === id) renderNav(); }}));
    cleanPlatformOptions(); renderNav(); const first = allDrafts()[0]; if (first) {{ selected = first; renderNav(); renderDetail(first); }}
  </script>
</body>
</html>
"""

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
