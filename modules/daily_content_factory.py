from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
import re
from pathlib import Path
from typing import Any

from modules.content_operations import (
    build_ai_priority_dashboard,
    build_authority_score,
    build_content_gap,
    build_duplicate_report,
    cluster_for,
    content_inventory,
    priority_from_score,
    row_slug,
)
from modules.performance_tracking import (
    BASE_URL,
    DATA_DIR,
    load_json_rows,
    numeric,
    read_csv,
    slugify,
    update_master_workbook,
    write_csv,
    write_json,
)


TODAY_SELECTED_TOPICS_FIELDS = [
    "rank",
    "topic",
    "slug",
    "decision",
    "reason",
    "final_score",
    "money_score",
    "trend_score",
    "affiliate_score",
    "competition_score",
    "content_gap_score",
    "internal_link_score",
    "impression_score",
    "ctr_score",
    "youtube_score",
    "social_score",
    "article_type",
    "priority",
    "article_url",
    "youtube_action",
]

TOPICAL_AUTHORITY_FIELDS = [
    "cluster",
    "total_articles",
    "published_articles",
    "missing_articles",
    "authority_score",
    "recommended_next_articles",
    "internal_link_gaps",
]

INTERNAL_LINK_INSERTION_FIELDS = [
    "source_slug",
    "source_url",
    "target_slug",
    "target_url",
    "anchor_text",
    "reason",
    "status",
]

REFRESH_QUEUE_FIELDS = [
    "rank",
    "topic",
    "slug",
    "article_url",
    "reason",
    "final_score",
    "priority",
    "status",
]

WORKFLOW_TZ = timezone(timedelta(hours=7))
DEEP_DIVE_TYPES = ("pricing", "alternatives", "comparison", "tutorial", "faq")
DEEP_DIVE_LABELS = {
    "pricing": "Pricing",
    "alternatives": "Alternatives",
    "comparison": "Comparison",
    "tutorial": "Tutorial",
    "faq": "FAQ",
}
BOOTSTRAP_WEEKLY_TYPES = ("pricing", "alternatives", "comparison", "tutorial", "faq")


def _article_url(slug: str) -> str:
    return f"{BASE_URL}/{slug.strip('/')}/"


def _selected_decision(row: dict[str, Any], duplicate_row: dict[str, Any] | None = None) -> str:
    duplicate_row = duplicate_row or {}
    exists = str(row.get("article_exists", "")).upper() == "YES" or duplicate_row.get("decision") in {"REFRESH_EXISTING", "MERGE"}
    final_score = numeric(row.get("final_score"))
    youtube_score = numeric(row.get("youtube_score"))
    if exists and final_score >= 50:
        return "REFRESH_EXISTING"
    if exists and youtube_score >= 70:
        return "VIDEO_ONLY"
    if exists:
        return "WATCH"
    if final_score >= 55:
        return "WRITE_NOW"
    if final_score >= 42:
        return "WATCH"
    return "SKIP"


def _workflow_weekday() -> int:
    return datetime.now(WORKFLOW_TZ).weekday()


def _title_case(value: str) -> str:
    words = re.sub(r"[-_/]+", " ", str(value or "")).strip().split()
    if not words:
        return ""
    special = {"ai", "seo", "crm", "faq", "api", "llm"}
    return " ".join(word.upper() if word.lower() in special else word.capitalize() for word in words)


def _base_name_from_text(text: str) -> str:
    slug = str(text or "").strip().rstrip("/")
    if not slug:
        return ""
    slug = slug.split("/")[-1]
    slug = slug.replace(".html", "")
    slug = re.sub(r"[-_]?review(?:-2026)?$", "", slug, flags=re.I)
    slug = re.sub(r"^review[-_]", "", slug, flags=re.I)
    slug = re.sub(r"[-_]?reviews?$", "", slug, flags=re.I)
    slug = re.sub(r"[-_]?2026$", "", slug, flags=re.I)
    slug = re.sub(r"[-_]+", " ", slug).strip()
    return _title_case(slug)


def _cluster_base_name(cluster: str, cluster_rows: list[dict[str, Any]] | None = None) -> str:
    cluster_rows = cluster_rows or []
    for row in cluster_rows:
        if str(row.get("cluster", "")).strip() != cluster:
            continue
        for candidate in (
            row.get("pillar_page", ""),
            str(row.get("review_pages", "")).split(",")[0].strip(),
            str(row.get("comparison_pages", "")).split(",")[0].strip(),
            str(row.get("pricing_pages", "")).split(",")[0].strip(),
        ):
            base = _base_name_from_text(candidate)
            if base and base.lower() not in {"reviews", "comparisons", "saas reviews"}:
                return base
    base = _base_name_from_text(cluster)
    return base or _title_case(cluster)


def _weekly_cluster_rows() -> list[dict[str, Any]]:
    csv_path = DATA_DIR / "weekly_topic_cluster.csv"
    json_path = DATA_DIR / "weekly_topic_cluster.json"
    rows = read_csv(csv_path)
    if rows:
        return rows
    return load_json_rows(json_path)


def _competitor_priority_rows() -> list[dict[str, Any]]:
    rows = load_json_rows(DATA_DIR / "competitor_topic_candidates.json")
    output: list[dict[str, Any]] = []
    for row in rows:
        score = numeric(row.get("trend_score"))
        action = str(row.get("recommended_action", "")).lower()
        if score < 70 or action not in {"create", "refresh"}:
            continue
        topic = str(row.get("suggested_article_title") or row.get("keyword") or "").strip()
        slug = slugify(topic)
        if not topic or not slug:
            continue
        keyword = str(row.get("keyword", "")).lower()
        article_type = "Comparison" if any(value in keyword.split() for value in ("vs", "comparison")) else (
            "Alternatives" if "alternatives" in keyword else "Review"
        )
        output.append(
            {
                "topic": topic,
                "slug": slug,
                "final_score": score,
                "money_score": row.get("affiliate_potential", score),
                "trend_score": score,
                "affiliate_score": row.get("affiliate_potential", ""),
                "competition_score": max(0, 100 - numeric(row.get("competitor_frequency")) * 10),
                "content_gap_score": row.get("content_gap_score", ""),
                "internal_link_score": row.get("internal_link_score", ""),
                "impression_score": "",
                "ctr_score": row.get("commercial_intent_score", ""),
                "youtube_score": "",
                "social_score": "",
                "article_type": article_type,
                "article_exists": "YES" if action == "refresh" else "NO",
                "reason": f"Competitor trend: {row.get('competitor', '')}; keyword: {row.get('keyword', '')}.",
            }
        )
    return output


def _deep_dive_rows_from_clusters(limit: int, cluster_rows: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    inventory = content_inventory()
    authority_rows = build_authority_score(inventory)
    authority_by_cluster = {str(row.get("cluster", "")): row for row in authority_rows}
    cluster_meta = cluster_rows if cluster_rows is not None else read_csv(DATA_DIR / "content_clusters.csv")
    gap_rows = build_content_gap(inventory, authority_rows)
    gaps_by_cluster: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in gap_rows:
        gaps_by_cluster[str(row.get("cluster", ""))].append(row)

    selected: list[dict[str, Any]] = []
    seen_slugs: set[str] = set()

    source_clusters: list[str] = []
    if cluster_rows:
        for row in cluster_rows:
            cluster = str(row.get("cluster", "")).strip()
            if cluster and cluster not in source_clusters:
                source_clusters.append(cluster)
    else:
        source_clusters = sorted(gaps_by_cluster)

    cluster_scores = sorted(
        ((cluster, numeric(authority_by_cluster.get(cluster, {}).get("content_gap_score"))) for cluster in source_clusters),
        key=lambda item: item[1],
        reverse=True,
    )

    for cluster, cluster_score in cluster_scores:
        cluster_gaps = gaps_by_cluster.get(cluster, [])
        if not cluster_gaps:
            continue
        base_name = _cluster_base_name(cluster, cluster_meta)
        chosen_gap = None
        for article_type in DEEP_DIVE_TYPES:
            for gap in cluster_gaps:
                if str(gap.get("missing_article_type", "")).strip().lower() != article_type:
                    continue
                chosen_gap = gap
                break
            if chosen_gap:
                break
        if not chosen_gap:
            continue
        article_type = str(chosen_gap.get("missing_article_type", "")).strip().lower()
        title_type = DEEP_DIVE_LABELS.get(article_type, article_type.title())
        topic = f"{base_name} {title_type} 2026".strip()
        slug = slugify(chosen_gap.get("suggested_slug") or topic)
        if not slug or slug in seen_slugs:
            continue
        seen_slugs.add(slug)
        selected.append(
            {
                "rank": len(selected) + 1,
                "topic": topic,
                "slug": slug,
                "decision": "WRITE_NOW",
                "reason": chosen_gap.get("reason", ""),
                "final_score": round(min(100, max(45, cluster_score)), 1),
                "money_score": round(min(100, max(45, cluster_score)), 1),
                "trend_score": "",
                "affiliate_score": "",
                "competition_score": "",
                "content_gap_score": round(min(100, max(45, cluster_score)), 1),
                "internal_link_score": "",
                "impression_score": "",
                "ctr_score": "",
                "youtube_score": "",
                "social_score": "",
                "article_type": article_type,
                "priority": priority_from_score(round(min(100, max(45, cluster_score)), 1)),
                "article_url": _article_url(slug),
                "youtube_action": "OPTIONAL",
            }
        )
        if len(selected) >= limit:
            break
    return selected


def _deep_dive_rows_from_weekly_topics(weekly_rows: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    seen_slugs: set[str] = set()
    for index, row in enumerate(weekly_rows):
        source_topic = str(row.get("topic") or row.get("suggested_title") or row.get("slug") or "").strip()
        base_name = _base_name_from_text(source_topic) or _title_case(str(row.get("slug", "")).replace("-", " "))
        if not base_name:
            continue
        source_type = str(row.get("article_type", "")).strip().lower()
        if source_type in {"pricing", "comparison", "tutorial", "faq", "alternatives"}:
            article_type = source_type
        else:
            article_type = BOOTSTRAP_WEEKLY_TYPES[index % len(BOOTSTRAP_WEEKLY_TYPES)]
        title_type = DEEP_DIVE_LABELS.get(article_type, article_type.title())
        topic = f"{base_name} {title_type} 2026".strip()
        slug = slugify(f"{base_name} {title_type} 2026")
        if not slug or slug in seen_slugs:
            slug = slugify(f"{base_name}-{article_type}-2026")
        if not slug or slug in seen_slugs:
            continue
        seen_slugs.add(slug)
        score = numeric(row.get("final_score")) or numeric(row.get("money_score")) or 50.0
        selected.append(
            {
                "rank": len(selected) + 1,
                "topic": topic,
                "slug": slug,
                "decision": "WRITE_NOW",
                "reason": f"Weekly cluster deep dive derived from {source_topic}.",
                "final_score": round(min(100, max(45, score)), 1),
                "money_score": round(min(100, max(45, score)), 1),
                "trend_score": row.get("trend_score", ""),
                "affiliate_score": row.get("affiliate_score", ""),
                "competition_score": row.get("competition_score", ""),
                "content_gap_score": row.get("content_gap_score", ""),
                "internal_link_score": row.get("internal_link_score", ""),
                "impression_score": row.get("impression_score", ""),
                "ctr_score": row.get("ctr_score", ""),
                "youtube_score": row.get("youtube_score", ""),
                "social_score": row.get("social_score", ""),
                "article_type": article_type,
                "priority": priority_from_score(round(min(100, max(45, score)), 1)),
                "article_url": _article_url(slug),
                "youtube_action": "OPTIONAL",
            }
        )
        if len(selected) >= limit:
            break
    return selected


def build_weekly_cluster_topics(limit: int = 10, weekly_rows: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    weekly_rows = weekly_rows if weekly_rows is not None else _weekly_cluster_rows()
    if weekly_rows:
        rows = _deep_dive_rows_from_weekly_topics(weekly_rows, limit=limit)
        if rows:
            return rows
    return _deep_dive_rows_from_clusters(limit=limit)


def build_today_selected_topics(limit: int = 10, priority_rows: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    if priority_rows is None:
        priority_rows = [*build_ai_priority_dashboard(), *_competitor_priority_rows()]
    else:
        priority_rows = list(priority_rows)
    duplicate_rows = build_duplicate_report()
    duplicate_by_slug = {str(row.get("slug", "")): row for row in duplicate_rows}
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in sorted(priority_rows, key=lambda item: numeric(item.get("final_score")), reverse=True):
        slug = str(row.get("slug") or slugify(row.get("topic", "")))
        if not slug or slug in seen:
            continue
        seen.add(slug)
        decision = _selected_decision(row, duplicate_by_slug.get(slug))
        if decision == "SKIP":
            continue
        youtube_action = "CREATE VIDEO" if numeric(row.get("youtube_score")) >= 65 else "OPTIONAL"
        selected.append(
            {
                "rank": len(selected) + 1,
                "topic": row.get("topic", ""),
                "slug": slug,
                "decision": decision,
                "reason": row.get("reason", ""),
                "final_score": row.get("final_score", ""),
                "money_score": row.get("money_score", ""),
                "trend_score": row.get("trend_score", ""),
                "affiliate_score": row.get("affiliate_score", ""),
                "competition_score": row.get("competition_score", ""),
                "content_gap_score": row.get("content_gap_score", ""),
                "internal_link_score": row.get("internal_link_score", ""),
                "impression_score": row.get("impression_score", ""),
                "ctr_score": row.get("ctr_score", ""),
                "youtube_score": row.get("youtube_score", ""),
                "social_score": row.get("social_score", ""),
                "article_type": row.get("article_type", ""),
                "priority": priority_from_score(numeric(row.get("final_score"))),
                "article_url": _article_url(slug),
                "youtube_action": youtube_action,
            }
        )
        if len(selected) >= limit:
            break
    return selected


def build_topical_authority_dashboard(selected_rows: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    inventory = content_inventory()
    authority = {row.get("cluster"): row for row in build_authority_score(inventory)}
    gaps = defaultdict(list)
    for gap in build_content_gap(inventory):
        gaps[str(gap.get("cluster", "SaaS Reviews"))].append(str(gap.get("suggested_title", "")))
    clusters = sorted(set(authority) | {cluster_for(row.get("topic", "")) for row in selected_rows or []})
    output: list[dict[str, Any]] = []
    for cluster in clusters:
        row = authority.get(cluster, {})
        missing = [title for title in gaps.get(cluster, []) if title][:5]
        output.append(
            {
                "cluster": cluster,
                "total_articles": row.get("article_count", 0),
                "published_articles": row.get("indexed_count", row.get("article_count", 0)),
                "missing_articles": len(missing),
                "authority_score": row.get("authority_score", 0),
                "recommended_next_articles": "; ".join(missing),
                "internal_link_gaps": row.get("content_gap_score", ""),
            }
        )
    return output


def build_internal_link_insertions(selected_rows: list[dict[str, Any]], max_links: int = 8) -> list[dict[str, Any]]:
    inventory = content_inventory()
    candidates: list[dict[str, Any]] = []
    for source in selected_rows:
        source_slug = str(source.get("slug", ""))
        source_cluster = cluster_for(f"{source.get('topic', '')} {source_slug}")
        links = []
        for target in inventory:
            target_slug = row_slug(target)
            if not target_slug or target_slug == source_slug:
                continue
            target_cluster = cluster_for(f"{target.get('topic', '')} {target_slug}")
            source_tokens = set(source_slug.split("-"))
            target_tokens = set(target_slug.split("-"))
            overlap = len(source_tokens & target_tokens)
            cluster_match = source_cluster == target_cluster
            score = overlap * 12 + (30 if cluster_match else 0) + numeric(target.get("impressions")) / 100
            if score <= 0:
                continue
            links.append((score, target, target_slug, target_cluster))
        for _, target, target_slug, target_cluster in sorted(links, key=lambda item: item[0], reverse=True)[:max_links]:
            candidates.append(
                {
                    "source_slug": source_slug,
                    "source_url": source.get("article_url") or _article_url(source_slug),
                    "target_slug": target_slug,
                    "target_url": target.get("article_url") or _article_url(target_slug),
                    "anchor_text": target.get("topic") or target_slug.replace("-", " ").title(),
                    "reason": f"Related {target_cluster} buyer journey page.",
                    "status": "planned",
                }
            )
    return candidates


def build_refresh_queue(selected_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for row in selected_rows:
        if row.get("decision") != "REFRESH_EXISTING":
            continue
        rows.append(
            {
                "rank": len(rows) + 1,
                "topic": row.get("topic", ""),
                "slug": row.get("slug", ""),
                "article_url": row.get("article_url", ""),
                "reason": row.get("reason", "Existing page has renewed opportunity."),
                "final_score": row.get("final_score", ""),
                "priority": row.get("priority", ""),
                "status": "READY_FOR_REVIEW",
            }
        )
    return rows


def write_daily_factory_outputs(limit: int = 10, workflow_mode: str = "auto") -> dict[str, Any]:
    weekday = _workflow_weekday()
    use_weekly_cluster = workflow_mode == "weekly_cluster" or (workflow_mode == "auto" and weekday != 0)
    priority_rows = build_ai_priority_dashboard()
    weekly_source_rows = _weekly_cluster_rows()
    cluster_bootstrap = False
    if use_weekly_cluster and weekly_source_rows:
        selected = build_weekly_cluster_topics(limit=limit, weekly_rows=weekly_source_rows)
    elif use_weekly_cluster:
        cluster_bootstrap = True
        weekly_source_rows = build_today_selected_topics(limit=limit, priority_rows=priority_rows)
        selected = build_weekly_cluster_topics(limit=limit, weekly_rows=weekly_source_rows)
    else:
        weekly_source_rows = build_today_selected_topics(limit=limit, priority_rows=priority_rows)
        selected = build_today_selected_topics(limit=limit, priority_rows=priority_rows)
    topical_authority = build_topical_authority_dashboard(selected)
    internal_links = build_internal_link_insertions(selected)
    refresh_queue = build_refresh_queue(selected)

    write_csv(DATA_DIR / "today_selected_topics.csv", selected, TODAY_SELECTED_TOPICS_FIELDS)
    write_json(DATA_DIR / "today_selected_topics.json", selected)
    write_csv(DATA_DIR / "topical_authority.csv", topical_authority, TOPICAL_AUTHORITY_FIELDS)
    write_json(DATA_DIR / "topical_authority.json", topical_authority)
    write_csv(DATA_DIR / "internal_link_insertions.csv", internal_links, INTERNAL_LINK_INSERTION_FIELDS)
    write_json(DATA_DIR / "internal_link_insertions.json", internal_links)
    write_csv(DATA_DIR / "refresh_queue.csv", refresh_queue, REFRESH_QUEUE_FIELDS)
    write_json(DATA_DIR / "refresh_queue.json", refresh_queue)
    if not use_weekly_cluster or cluster_bootstrap:
        write_csv(DATA_DIR / "weekly_topic_cluster.csv", weekly_source_rows, TODAY_SELECTED_TOPICS_FIELDS)
        write_json(DATA_DIR / "weekly_topic_cluster.json", weekly_source_rows)

    update_master_workbook(
        {
            "Today Selected Topics": (selected, TODAY_SELECTED_TOPICS_FIELDS),
            "Topical Authority": (topical_authority, TOPICAL_AUTHORITY_FIELDS),
            "Internal Link Insertions": (internal_links, INTERNAL_LINK_INSERTION_FIELDS),
            "Refresh Queue": (refresh_queue, REFRESH_QUEUE_FIELDS),
            "Weekly Topic Cluster": (weekly_source_rows or selected, TODAY_SELECTED_TOPICS_FIELDS),
        }
    )
    return {
        "selected_topics": len(selected),
        "topical_authority": len(topical_authority),
        "internal_links": len(internal_links),
        "refresh_queue": len(refresh_queue),
        "workflow_mode": "weekly_cluster" if use_weekly_cluster and weekly_source_rows else ("weekly_cluster_bootstrap" if cluster_bootstrap else "hottrend"),
    }
