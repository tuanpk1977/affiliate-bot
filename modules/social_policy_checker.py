from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import parse_qs, urlparse

import pandas as pd


X_MAX_CHARS = 260
COMMUNITY_FIRST_PLATFORMS = {"facebook_group", "reddit", "quora"}
GROUP_LIKE_PLATFORMS = {"facebook_group", "reddit", "quora", "linkedin_group"}


@dataclass(frozen=True)
class PolicyResult:
    valid: bool
    warnings: list[str]
    errors: list[str]

    @property
    def status(self) -> str:
        return "pass" if self.valid else "fail"


def normalize_platform(value: object) -> str:
    raw = str(value or "").strip().lower().replace(" ", "_").replace("/", "_")
    aliases = {
        "x": "twitter",
        "x_twitter": "twitter",
        "twitter_x": "twitter",
        "facebook": "facebook_page",
        "facebook_page_profile_group": "facebook_page",
        "linkedin": "linkedin",
        "telegram_channel": "telegram",
    }
    return aliases.get(raw, raw)


def has_required_utm(url: str) -> bool:
    parsed = urlparse(str(url or ""))
    query = parse_qs(parsed.query)
    required = {"utm_source", "utm_medium", "utm_campaign", "utm_content"}
    return required.issubset(set(query))


def contains_direct_affiliate_link(text: str) -> bool:
    value = str(text or "").lower()
    if "/go/" in value:
        return True
    risky_domains = ["partnerstack", "impact.com", "shareasale", "cj.com", "awin1.com"]
    return any(domain in value for domain in risky_domains)


def split_x_thread(content: str, max_chars: int = X_MAX_CHARS) -> list[str]:
    text = re.sub(r"\s+", " ", str(content or "")).strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]
    sentences = re.split(r"(?<=[.!?])\s+", text)
    posts: list[str] = []
    current = ""
    for sentence in sentences:
        if not sentence:
            continue
        candidate = f"{current} {sentence}".strip()
        if len(candidate) <= max_chars:
            current = candidate
            continue
        if current:
            posts.append(current)
        if len(sentence) <= max_chars:
            current = sentence
        else:
            words = sentence.split()
            current = ""
            for word in words:
                candidate = f"{current} {word}".strip()
                if len(candidate) <= max_chars:
                    current = candidate
                else:
                    if current:
                        posts.append(current)
                    current = word[:max_chars]
    if current:
        posts.append(current)
    numbered: list[str] = []
    total = len(posts)
    for index, post in enumerate(posts, start=1):
        prefix = f"{index}/{total} "
        available = max_chars - len(prefix)
        numbered.append(prefix + post[:available].rstrip())
    return numbered


def validate_post(row: dict[str, object], queue: pd.DataFrame | None = None) -> PolicyResult:
    platform = normalize_platform(row.get("platform", ""))
    content = str(row.get("content", "") or row.get("post_body", ""))
    tracked_url = str(row.get("tracked_url", "") or row.get("target_url", ""))
    current_queue_id = str(row.get("queue_id", "") or "").strip()
    current_post_id = str(row.get("post_id", "") or row.get("id", "") or "").strip()
    warnings: list[str] = []
    errors: list[str] = []

    if not content.strip():
        errors.append("missing_content")
    if not tracked_url.strip():
        errors.append("missing_tracked_url")
    elif not has_required_utm(tracked_url):
        errors.append("missing_utm")

    if platform == "twitter":
        for part in split_x_thread(content):
            if len(part) > X_MAX_CHARS:
                errors.append("x_post_over_limit")
                break

    if platform in COMMUNITY_FIRST_PLATFORMS:
        warnings.append("community_first_no_spam")
        if contains_direct_affiliate_link(content):
            errors.append("direct_affiliate_link_not_allowed_for_community")

    if platform in GROUP_LIKE_PLATFORMS and str(row.get("link_allowed", "")).lower() in {"unknown", "no", ""}:
        if tracked_url and tracked_url in content:
            warnings.append("link_allowed_unknown_use_no_link_variant_first")

    if queue is not None and not queue.empty:
        comparable_queue = queue.copy()
        if current_queue_id and "queue_id" in comparable_queue.columns:
            comparable_queue = comparable_queue[comparable_queue["queue_id"].astype(str) != current_queue_id]
        if current_post_id and "post_id" in comparable_queue.columns:
            comparable_queue = comparable_queue[comparable_queue["post_id"].astype(str) != current_post_id]
        if current_post_id and "id" in comparable_queue.columns:
            comparable_queue = comparable_queue[comparable_queue["id"].astype(str) != current_post_id]
        today = datetime.now().date().isoformat()
        url_col = "tracked_url" if "tracked_url" in queue.columns else "article_url"
        platform_col = "platform" if "platform" in queue.columns else ""
        scheduled_col = "scheduled_time" if "scheduled_time" in queue.columns else ""
        if url_col and platform_col and scheduled_col:
            same_today = comparable_queue[
                (comparable_queue[url_col].astype(str) == tracked_url)
                & (comparable_queue[platform_col].astype(str).map(normalize_platform) == platform)
                & (comparable_queue[scheduled_col].astype(str).str.startswith(today))
            ]
            if len(same_today) >= 2:
                warnings.append("same_url_posted_too_often_today")
        content_col = "content" if "content" in comparable_queue.columns else "title"
        if content_col in comparable_queue.columns and platform_col:
            duplicate = comparable_queue[
                (comparable_queue[platform_col].astype(str).map(normalize_platform) == platform)
                & (comparable_queue[content_col].astype(str).str.strip() == content.strip())
            ]
            if len(duplicate) > 0:
                status = str(row.get("status", "") or "").strip().lower()
                if status in {"approved", "scheduled", "ready_to_post", "published"}:
                    errors.append("duplicate_content_same_platform")
                else:
                    warnings.append("duplicate_content_same_platform")

    return PolicyResult(valid=not errors, warnings=warnings, errors=errors)


def policy_summary(row: dict[str, object], queue: pd.DataFrame | None = None) -> str:
    result = validate_post(row, queue=queue)
    parts = []
    if result.errors:
        parts.append("errors=" + "|".join(result.errors))
    if result.warnings:
        parts.append("warnings=" + "|".join(result.warnings))
    return "; ".join(parts) if parts else "pass"
