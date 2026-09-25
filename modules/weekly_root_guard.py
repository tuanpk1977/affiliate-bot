from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any


MAX_FOUNDATION_ROOTS = 2
MAX_WEEKLY_ROOTS = MAX_FOUNDATION_ROOTS
MIN_WEEKLY_ROOTS = 1
FOUNDATION_MAIN = "FOUNDATION_MAIN"
FOUNDATION_ADVANCED = "FOUNDATION_ADVANCED"
SOCIAL_HOT_UNCONFIRMED = "SOCIAL_HOT_UNCONFIRMED"
OFFICIAL_NEWS_STANDALONE = "OFFICIAL_NEWS_STANDALONE"
LOCKED_STATUSES = {"locked", "LOCKED"}
ACTIVE_ROOT_STATUSES = {"active", "weekly_selected", "selected"}
WATCHLIST_STATUSES = {"watchlist", "watchlist_next_week", "monitoring"}
SOCIAL_ONLY_HOT_STATES = {
    "social_watchlist",
    "social_monitoring",
    "monitoring",
    "watchlist",
    "rejected_for_website",
}
OFFICIAL_NEWS_ALLOWED_CONFIRMATION = {"official_confirmed", "vendor_confirmed", "primary_source_confirmed"}


class WeeklyRootValidationError(ValueError):
    """Raised when a weekly root or daily-series contract is unsafe."""


@dataclass(frozen=True)
class WeeklyValidationResult:
    passed: bool
    blockers: tuple[str, ...]
    warnings: tuple[str, ...] = ()


def week_start_for(batch_date: str) -> str:
    current = date.fromisoformat(batch_date)
    return (current - timedelta(days=current.weekday())).isoformat()


def editorial_week_id(week_start: str) -> str:
    current = date.fromisoformat(week_start)
    iso = current.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def stable_root_topic_id(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    if normalized:
        return normalized[:96]
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def planned_weekly_series(*, root_topic_id: str, root_title: str, week_start: str) -> list[dict[str, Any]]:
    start = date.fromisoformat(week_start)
    angles = [
        ("main_review", "category overview", "commercial research"),
        ("implementation_guide", "implementation workflow", "implementation guide"),
        ("comparison", "comparison and alternatives", "comparison"),
        ("pricing", "pricing, cost, and ROI", "commercial investigation"),
        ("use_cases", "workflows and use cases", "informational"),
        ("troubleshooting", "mistakes and troubleshooting", "informational"),
        ("buying_decision", "small-business buying decision", "commercial research"),
    ]
    planned: list[dict[str, Any]] = []
    for sequence, (angle, reader_question, intent) in enumerate(angles, start=1):
        article_date = (start + timedelta(days=sequence - 1)).isoformat()
        next_angle = angles[sequence][0] if sequence < len(angles) else ""
        planned.append(
            {
                "root_topic_id": root_topic_id,
                "root_title": root_title,
                "content_lane": FOUNDATION_MAIN if sequence == 1 else FOUNDATION_ADVANCED,
                "article_id": f"{root_topic_id}-{angle}",
                "sequence_number": sequence,
                "scheduled_date": article_date,
                "planned_publishing_day": article_date,
                "daily_angle": angle,
                "primary_search_intent": intent,
                "search_intent": intent,
                "reader_question": f"How should a small business evaluate {root_title} for {reader_question}?",
                "unique_thesis": f"{root_title} should be judged through {reader_question}, not a repeated feature checklist.",
                "decision_objective": f"Help the reader decide how to use {root_title} for {reader_question}.",
                "required_evidence": ["prepared sources", "official source where available", "same-root article history"],
                "key_evidence": ["prepared sources", "official source where available", "same-root article history"],
                "unique_sections": [
                    f"{reader_question.title()} context",
                    "Verification checklist",
                    "Operational risks",
                ],
                "table_purpose": f"Compare {reader_question} options without repeating the Monday table.",
                "faq_set": [f"{angle}_faq_{number}" for number in range(1, 4)],
                "cta_intent": "continue the same-root editorial series" if next_angle else "close the same-root editorial series",
                "previous_article": "" if sequence == 1 else angles[sequence - 2][0],
                "prohibited_overlap": [
                    "same search intent as an earlier article",
                    "same FAQ set as an earlier article",
                    "same table purpose as an earlier article",
                    "same conclusion/CTA purpose as an earlier article",
                ],
                "next_scheduled_article": {
                    "daily_angle": next_angle,
                    "bridge_state": "NEXT_SCHEDULED_NOT_LIVE" if next_angle else "SERIES_COMPLETE",
                },
                "next_article": next_angle,
                "bridge_state": "NEXT_SCHEDULED_NOT_LIVE" if next_angle else "SERIES_COMPLETE",
                "series_status": "planned",
                "article_state": "planned",
            }
        )
    return planned


def normalize_weekly_root_manifest(payload: dict[str, Any], *, week_start: str, selection_source: str = "menu_1") -> dict[str, Any]:
    manifest = dict(payload)
    week_start_date = date.fromisoformat(week_start)
    topics: list[dict[str, Any]] = []
    for index, raw in enumerate(list(payload.get("topics") or []), start=1):
        topic = dict(raw)
        title = str(topic.get("root_title") or topic.get("title") or topic.get("keyword") or "").strip()
        root_topic_id = str(topic.get("root_topic_id") or topic.get("parent_slug") or topic.get("slug") or stable_root_topic_id(title)).strip()
        topic.setdefault("root_topic_id", root_topic_id)
        topic.setdefault("normalized_root_topic", stable_root_topic_id(title or root_topic_id))
        topic.setdefault("root_title", title)
        topic.setdefault("topic_category", str(topic.get("category") or topic.get("content_type") or "EVERGREEN").upper())
        topic.setdefault("content_lane", FOUNDATION_MAIN)
        topic.setdefault("primary_entity", str(topic.get("primary_entity") or topic.get("parent_keyword") or title))
        topic.setdefault("primary_search_intent", str(topic.get("primary_search_intent") or topic.get("search_intent") or "commercial research"))
        topic.setdefault("reason_selected", topic.get("why_selected") or [])
        topic.setdefault("selection_score", float(topic.get("total_score") or topic.get("selection_score") or 0))
        topic.setdefault("freshness_score", float(topic.get("content_freshness_score") or topic.get("freshness_score") or 0))
        topic.setdefault("official_source_confidence", str(topic.get("official_source_confidence") or "unknown"))
        topic.setdefault("likely_search_demand", float(topic.get("likely_search_demand") or topic.get("search_intent_score") or 0))
        topic.setdefault("commercial_relevance", float(topic.get("commercial_relevance") or topic.get("affiliate_monetization_score") or 0))
        topic.setdefault("depth_potential", float(topic.get("depth_potential") or topic.get("selection_score") or topic.get("total_score") or 0))
        topic.setdefault("source_references", list(topic.get("sources") or topic.get("source_urls") or []))
        topic.setdefault("selected", True)
        topic.setdefault("selected_status", "selected")
        topic.setdefault("series_status", "active")
        topic.setdefault("maximum_useful_article_angles", 7)
        topic.setdefault("series_plan", planned_weekly_series(root_topic_id=root_topic_id, root_title=title, week_start=week_start))
        topic.setdefault("rank", index)
        topics.append(topic)

    manifest.update(
        {
            "editorial_week_id": str(manifest.get("editorial_week_id") or editorial_week_id(week_start)),
            "week_start_date": str(manifest.get("week_start_date") or week_start),
            "week_start": str(manifest.get("week_start") or week_start),
            "week_end": str(manifest.get("week_end") or (week_start_date + timedelta(days=6)).isoformat()),
            "selection_source": str(manifest.get("selection_source") or selection_source),
            "manifest_version": int(manifest.get("manifest_version") or 1),
            "lock_status": str(manifest.get("lock_status") or "locked"),
            "locked_at": str(manifest.get("locked_at") or manifest.get("selected_at") or manifest.get("generated_at") or ""),
            "selected_root_count": len(topics),
            "maximum_root_count": min(int(manifest.get("maximum_root_count") or MAX_WEEKLY_ROOTS), MAX_FOUNDATION_ROOTS),
            "topics": topics,
            "watchlist_topics": list(manifest.get("watchlist_topics") or []),
            "rejected_candidates": list(manifest.get("rejected_candidates") or manifest.get("source_rejected_candidates") or []),
            "human_override_history": list(manifest.get("human_override_history") or []),
        }
    )
    return manifest


def _root_maps(manifest: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    by_id: dict[str, dict[str, Any]] = {}
    by_slug: dict[str, dict[str, Any]] = {}
    for raw in list(manifest.get("topics") or []):
        if not isinstance(raw, dict):
            continue
        root_id = str(raw.get("root_topic_id") or "").strip()
        parent_slug = str(raw.get("parent_slug") or raw.get("slug") or "").strip()
        if root_id:
            by_id[root_id] = raw
        if parent_slug:
            by_slug[parent_slug] = raw
    return by_id, by_slug


def validate_weekly_root_manifest(
    manifest: dict[str, Any],
    *,
    batch_date: str,
    enforce_max_roots: bool = True,
) -> WeeklyValidationResult:
    blockers: list[str] = []
    warnings: list[str] = []
    week_start = week_start_for(batch_date)
    if str(manifest.get("week_start") or manifest.get("week_start_date") or "") != week_start:
        blockers.append("root manifest belongs to another editorial week")
    if str(manifest.get("lock_status") or "").lower() not in LOCKED_STATUSES:
        blockers.append("root manifest is not locked")
    topics = [item for item in list(manifest.get("topics") or []) if isinstance(item, dict)]
    if enforce_max_roots and len(topics) > int(manifest.get("maximum_root_count") or MAX_WEEKLY_ROOTS):
        blockers.append("weekly root count exceeds maximum")
    if len(topics) < MIN_WEEKLY_ROOTS:
        blockers.append("weekly root manifest has no selected foundation roots")
    ids = [str(item.get("root_topic_id") or "").strip() for item in topics]
    if any(not root_id for root_id in ids):
        blockers.append("one or more selected roots are missing root_topic_id")
    if len(set(ids)) != len(ids):
        blockers.append("duplicate root_topic_id values in manifest")
    for item in topics:
        lane = str(item.get("content_lane") or "").strip()
        if lane and lane != FOUNDATION_MAIN:
            blockers.append("weekly root manifest may only contain FOUNDATION_MAIN roots")
    return WeeklyValidationResult(not blockers, tuple(blockers), tuple(warnings))


def _planned_for_date(root: dict[str, Any], batch_date: str) -> dict[str, Any]:
    for item in list(root.get("series_plan") or []):
        if isinstance(item, dict) and str(item.get("scheduled_date") or "") == batch_date:
            return item
    return {}


def _angle_history(root: dict[str, Any], *, exclude_date: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    daily_angles = root.get("daily_angles") if isinstance(root.get("daily_angles"), dict) else {}
    for day, value in sorted(daily_angles.items()):
        if str(day) == exclude_date or not isinstance(value, dict):
            continue
        rows.append(dict(value, date=str(day)))
    return rows


def _token_set(value: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]+", value.lower()) if len(token) > 2}


def _overlap_ratio(left: str, right: str) -> float:
    left_tokens = _token_set(left)
    right_tokens = _token_set(right)
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / max(1, min(len(left_tokens), len(right_tokens)))


def validate_daily_topic_against_weekly_roots(topic: dict[str, Any], *, manifest: dict[str, Any], batch_date: str) -> WeeklyValidationResult:
    blockers: list[str] = []
    warnings: list[str] = []
    manifest_result = validate_weekly_root_manifest(manifest, batch_date=batch_date, enforce_max_roots=False)
    blockers.extend(manifest_result.blockers)
    warnings.extend(manifest_result.warnings)

    by_id, by_slug = _root_maps(manifest)
    root_id = str(topic.get("root_topic_id") or "").strip()
    parent_slug = str(topic.get("parent_slug") or "").strip()
    root = by_id.get(root_id) or by_slug.get(parent_slug)
    if not root_id:
        blockers.append("daily topic missing root_topic_id")
    if root is None:
        blockers.append("daily topic root_topic_id is not in the active weekly root manifest")
        return WeeklyValidationResult(False, tuple(blockers), tuple(warnings))
    if str(root.get("selected_status") or root.get("selection_status") or "selected").lower() in WATCHLIST_STATUSES:
        blockers.append("watchlist topic cannot enter website production")
    if str(root.get("series_status") or "active").lower() not in ACTIVE_ROOT_STATUSES:
        blockers.append("weekly root is not active")
    lane = str(topic.get("content_lane") or FOUNDATION_ADVANCED).strip()
    if lane not in {FOUNDATION_MAIN, FOUNDATION_ADVANCED}:
        blockers.append("daily website article has an invalid content lane")
    if date.fromisoformat(batch_date).weekday() > 0 and lane != FOUNDATION_ADVANCED:
        blockers.append("Tuesday-Sunday website articles must use FOUNDATION_ADVANCED lane")

    planned = _planned_for_date(root, batch_date)
    if not planned:
        blockers.append("daily article is not scheduled in the active root series plan")
    daily_angle = str(topic.get("daily_angle") or "").strip()
    if not daily_angle:
        blockers.append("daily topic missing daily_angle")
    elif planned and daily_angle != str(planned.get("daily_angle") or ""):
        blockers.append("daily_angle does not match the scheduled series angle")

    root_title = str(topic.get("root_title") or "").strip()
    immutable_title = str(root.get("root_title") or root.get("title") or "").strip()
    if root_title and immutable_title and root_title != immutable_title:
        blockers.append("daily topic changed immutable root title")

    search_intent = str(topic.get("search_intent") or topic.get("primary_search_intent") or "").strip()
    for previous in _angle_history(root, exclude_date=batch_date):
        previous_angle = str(previous.get("angle") or previous.get("daily_angle") or "")
        previous_intent = str(previous.get("search_intent") or previous.get("primary_search_intent") or "")
        if daily_angle and previous_angle == daily_angle:
            blockers.append("daily angle already used under the same root")
        if search_intent and previous_intent and search_intent == previous_intent:
            warnings.append("primary search intent duplicates an earlier same-root article")
        heading_overlap = _overlap_ratio(str(topic.get("heading_signature") or topic.get("keyword") or ""), str(previous.get("heading_signature") or previous.get("title") or ""))
        if heading_overlap >= 0.82:
            warnings.append("same-root heading/title overlap exceeds threshold")

    bridge = topic.get("next_article_bridge") if isinstance(topic.get("next_article_bridge"), dict) else {}
    if planned:
        expected = planned.get("next_scheduled_article") if isinstance(planned.get("next_scheduled_article"), dict) else {}
        expected_angle = str(expected.get("daily_angle") or "")
        expected_state = str(expected.get("bridge_state") or ("SERIES_COMPLETE" if not expected_angle else "NEXT_SCHEDULED_NOT_LIVE"))
        if expected_state != "SERIES_COMPLETE":
            if not bridge:
                blockers.append("non-final article missing next-article bridge")
            elif str(bridge.get("root_topic_id") or root_id) != str(root.get("root_topic_id") or ""):
                blockers.append("next-article bridge points to another root")
            elif str(bridge.get("daily_angle") or "") != expected_angle:
                blockers.append("next-article bridge does not match the actual next scheduled angle")
            elif str(bridge.get("state") or "") == "NEXT_LIVE" and not str(bridge.get("canonical_url") or "").startswith("https://"):
                blockers.append("live next-article bridge missing verified canonical URL")
        elif bridge and str(bridge.get("state") or "") not in {"SERIES_COMPLETE", "SERIES_PAUSED"}:
            blockers.append("final series article fabricates a successor")

    return WeeklyValidationResult(not blockers, tuple(dict.fromkeys(blockers)), tuple(dict.fromkeys(warnings)))


def validate_daily_topics_against_weekly_roots(topics: list[dict[str, Any]], *, manifest: dict[str, Any], batch_date: str) -> WeeklyValidationResult:
    blockers: list[str] = []
    warnings: list[str] = []
    for topic in topics:
        result = validate_daily_topic_against_weekly_roots(topic, manifest=manifest, batch_date=batch_date)
        prefix = str(topic.get("slug") or topic.get("root_topic_id") or "unknown")
        blockers.extend(f"{prefix}: {blocker}" for blocker in result.blockers)
        warnings.extend(f"{prefix}: {warning}" for warning in result.warnings)
    return WeeklyValidationResult(not blockers, tuple(blockers), tuple(warnings))


def validate_hot_news_routing(candidate: dict[str, Any]) -> WeeklyValidationResult:
    blockers: list[str] = []
    warnings: list[str] = []
    lane = str(candidate.get("content_lane") or "").strip()
    status = str(candidate.get("status") or candidate.get("routing_status") or "").strip().lower()
    creates_website = bool(
        candidate.get("creates_website_article")
        or candidate.get("create_website_article")
        or candidate.get("website_candidate")
    )
    official_status = str(candidate.get("official_confirmation_status") or "").strip().lower()
    if official_status not in OFFICIAL_NEWS_ALLOWED_CONFIRMATION:
        if lane and lane != SOCIAL_HOT_UNCONFIRMED:
            blockers.append("unconfirmed hot news must use SOCIAL_HOT_UNCONFIRMED lane")
        if creates_website:
            blockers.append("unconfirmed hot news cannot create a website article")
        if str(candidate.get("root_topic_id") or "").strip():
            blockers.append("unconfirmed hot news cannot become or replace a weekly foundation root")
        if status and status not in SOCIAL_ONLY_HOT_STATES:
            blockers.append("unconfirmed hot news must stay in social/watchlist/monitoring state")
        warnings.append("route unconfirmed hot news to social watchlist only")
    return WeeklyValidationResult(not blockers, tuple(dict.fromkeys(blockers)), tuple(dict.fromkeys(warnings)))


def validate_official_news_candidate(candidate: dict[str, Any]) -> WeeklyValidationResult:
    blockers: list[str] = []
    official_status = str(candidate.get("official_confirmation_status") or "").strip().lower()
    lane = str(candidate.get("content_lane") or OFFICIAL_NEWS_STANDALONE).strip()
    if official_status not in OFFICIAL_NEWS_ALLOWED_CONFIRMATION:
        blockers.append("official news website candidate lacks official confirmation")
    if lane != OFFICIAL_NEWS_STANDALONE:
        blockers.append("official news website candidate must use OFFICIAL_NEWS_STANDALONE lane by default")
    if candidate.get("replace_weekly_root") or candidate.get("root_topic_id"):
        blockers.append("official news standalone article cannot replace the locked weekly foundation roots")
    if candidate.get("auto_publish") or candidate.get("publish_automatically"):
        blockers.append("official news standalone article cannot auto-publish")
    return WeeklyValidationResult(not blockers, tuple(dict.fromkeys(blockers)), ())
