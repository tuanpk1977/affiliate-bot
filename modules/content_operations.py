from __future__ import annotations

import html
import json
import re
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from modules.business_intelligence import build_opportunity_breakdown, infer_intent
from modules.performance_tracking import (
    BASE_URL,
    DATA_DIR,
    build_content_lifecycle,
    load_json_rows,
    load_upload_links,
    numeric,
    read_csv,
    slug_from_url,
    slugify,
    update_master_workbook,
    write_csv,
    write_json,
)

PRIORITY_FORMULA_PATH = DATA_DIR / "ai_priority_formula.json"

DEFAULT_PRIORITY_WEIGHTS = {
    "money_score": 0.20,
    "trend_score": 0.12,
    "affiliate_score": 0.12,
    "competition_score": 0.10,
    "content_gap_score": 0.10,
    "internal_link_score": 0.08,
    "impression_score": 0.08,
    "ctr_score": 0.06,
    "youtube_score": 0.08,
    "social_score": 0.06,
}


DUPLICATE_FIELDS = [
    "topic",
    "slug",
    "matched_slug",
    "matched_url",
    "title_similarity",
    "slug_similarity",
    "keyword_similarity",
    "duplicate_score",
    "decision",
    "reason",
]

MONEY_RANKING_FIELDS = [
    "rank",
    "topic",
    "slug",
    "buyer_intent_score",
    "affiliate_fit_score",
    "product_review_score",
    "comparison_score",
    "pricing_score",
    "conversion_score",
    "revenue_estimate",
    "money_score",
    "decision",
    "reason",
]

PUBLISHING_QUEUE_FIELDS = [
    "topic",
    "slug",
    "article_url",
    "publish_priority",
    "target_publish_date",
    "article_status",
    "video_status",
    "social_status",
    "index_status",
    "last_checked",
    "next_action",
]

AUTHORITY_FIELDS = [
    "cluster",
    "article_count",
    "indexed_count",
    "internal_link_count",
    "impressions",
    "clicks",
    "average_position",
    "authority_score",
    "content_gap_score",
]

CONTENT_GAP_FIELDS = [
    "cluster",
    "base_slug",
    "missing_article_type",
    "suggested_title",
    "suggested_slug",
    "priority",
    "reason",
    "internal_link_target",
]

CONTENT_CLUSTER_FIELDS = [
    "cluster",
    "pillar_page",
    "review_pages",
    "comparison_pages",
    "pricing_pages",
    "tutorial_pages",
    "alternatives_pages",
    "faq_pages",
    "video_ideas",
]

INTERNAL_LINK_CLUSTER_FIELDS = [
    "source_slug",
    "source_url",
    "target_slug",
    "target_url",
    "anchor_text",
    "cluster",
    "reason",
    "priority",
]

TODAY_WRITE_PLAN_FIELDS = [
    "topic",
    "slug",
    "reason",
    "action",
    "priority",
    "article_type",
    "target_keyword",
    "suggested_title",
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
    "final_score",
    "estimated_monthly_traffic",
    "affiliate_conversion_rate",
    "estimated_revenue_score",
    "estimated_value",
    "youtube_action",
    "risk_note",
]

AI_PRIORITY_DASHBOARD_FIELDS = [
    "rank",
    "topic",
    "slug",
    "article_exists",
    "recommended_action",
    "article_type",
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
    "final_score",
    "estimated_monthly_traffic",
    "affiliate_conversion_rate",
    "estimated_revenue_score",
    "estimated_value",
    "reason",
]

REVENUE_OPPORTUNITY_FIELDS = [
    "rank",
    "topic",
    "slug",
    "article_type",
    "estimated_monthly_traffic",
    "affiliate_conversion_rate",
    "estimated_revenue_score",
    "estimated_value",
    "affiliate_score",
    "money_score",
    "final_score",
    "recommended_action",
]

DAILY_PUBLISHING_SCHEDULE_FIELDS = [
    "date",
    "topic",
    "slug",
    "article_type",
    "priority",
    "estimated_value",
    "estimated_revenue_score",
]

WEBSITE_PUBLISHING_QUEUE_FIELDS = [
    "topic",
    "slug",
    "article_url",
    "article_type",
    "priority",
    "status",
    "estimated_value",
    "estimated_revenue_score",
    "next_action",
    "notes",
]

EXECUTIVE_SUMMARY_FIELDS = ["section", "rank", "topic", "slug", "action", "final_score", "estimated_value", "notes"]

AUTO_EDITOR_REPORT_FIELDS = [
    "input_file",
    "output_file",
    "slug",
    "seo_title",
    "meta_description",
    "sections_added",
    "youtube_placeholder",
    "schema_added",
    "status",
]

COMMERCIAL_TERMS = ("review", "pricing", "cost", "alternatives", "alternative", " vs ", "comparison", "best", "coupon", "discount", "free trial")
REVIEW_TERMS = ("review", "pros", "cons", "features")
COMPARISON_TERMS = (" vs ", "comparison", "compare", "alternatives", "alternative", "best")
PRICING_TERMS = ("pricing", "cost", "price", "free trial", "coupon", "discount")
NEWS_TERMS = ("news", "funding", "launch", "announces", "announced", "stock", "rumor")
CLUSTER_KEYWORDS = {
    "AI Coding": ("coding", "developer", "github", "copilot", "cursor", "windsurf", "code", "replit"),
    "AI SEO": ("seo", "surfer", "semrush", "ahrefs", "keyword", "rank", "content optimization", "clearscope", "frase"),
    "AI Writing": ("writing", "writer", "grammarly", "jasper", "copy", "wordtune", "content"),
    "AI Video": ("video", "youtube", "synthesia", "pictory", "runway", "descript"),
    "AI Automation": ("automation", "zapier", "make", "n8n", "workflow", "agent"),
    "AI Productivity": ("productivity", "assistant", "notion", "meeting", "calendar"),
    "AI Search": ("search", "perplexity", "gemini", "chatgpt", "claude"),
    "AI Image": ("image", "design", "canva", "midjourney", "adcreative", "creative"),
    "AI Meeting": ("meeting", "transcription", "minutes", "otter", "fireflies"),
    "AI Agent": ("agent", "agentic", "autonomous"),
    "Reviews": ("review",),
    "Comparisons": (" vs ", "comparison", "compare", "alternatives"),
}


def topic_rows() -> list[dict[str, Any]]:
    return load_json_rows(DATA_DIR / "topic_scores.json")


def words(value: str) -> set[str]:
    return {word for word in re.findall(r"[a-z0-9]+", str(value).lower()) if len(word) > 2}


def similarity(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    return round(SequenceMatcher(None, str(left).lower(), str(right).lower()).ratio() * 100, 1)


def keyword_similarity(left: str, right: str) -> float:
    left_words = words(left)
    right_words = words(right)
    if not left_words or not right_words:
        return 0.0
    return round(len(left_words & right_words) / len(left_words | right_words) * 100, 1)


def content_inventory() -> list[dict[str, Any]]:
    rows = build_content_lifecycle()
    if rows:
        return rows
    return read_csv(DATA_DIR / "content_lifecycle.csv")


def row_slug(row: dict[str, Any]) -> str:
    return slugify(row.get("slug") or row.get("FolderName") or row.get("topic") or slug_from_url(str(row.get("article_url") or row.get("PageUrl") or "")))


def cluster_for(text: str) -> str:
    lowered = f" {str(text).lower()} "
    for cluster, keywords in CLUSTER_KEYWORDS.items():
        if any(keyword in lowered for keyword in keywords):
            return cluster
    return "SaaS Reviews"


def score_from_topic(row: dict[str, Any], *keys: str) -> float:
    for key in keys:
        value = numeric(row.get(key), -1)
        if value >= 0:
            return value
    return 0.0


def load_priority_weights() -> dict[str, float]:
    if PRIORITY_FORMULA_PATH.exists():
        try:
            payload = json.loads(PRIORITY_FORMULA_PATH.read_text(encoding="utf-8"))
            weights = payload.get("weights", payload) if isinstance(payload, dict) else {}
            parsed = {key: float(weights.get(key, value)) for key, value in DEFAULT_PRIORITY_WEIGHTS.items()}
            total = sum(parsed.values()) or 1.0
            return {key: value / total for key, value in parsed.items()}
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            pass
    PRIORITY_FORMULA_PATH.write_text(
        json.dumps({"weights": DEFAULT_PRIORITY_WEIGHTS}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return dict(DEFAULT_PRIORITY_WEIGHTS)


def existing_slug_map(inventory: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {row_slug(row): row for row in inventory if row_slug(row)}


def topic_social_score(row: dict[str, Any]) -> float:
    scores = row.get("social_scores")
    if isinstance(scores, dict) and scores:
        return round(sum(numeric(value) for value in scores.values()) / len(scores), 1)
    return score_from_topic(row, "social_score", "social_share_potential", "quora_potential", "linkedin_potential")


def estimated_monthly_traffic(row: dict[str, Any], inventory_row: dict[str, Any] | None = None) -> int:
    inventory_row = inventory_row or {}
    impressions = numeric(inventory_row.get("impressions"))
    clicks = numeric(inventory_row.get("google_clicks"))
    if impressions:
        return int(max(clicks * 12, impressions * 0.08))
    return int(max(50, score_from_topic(row, "estimated_traffic", "traffic_score") * 18))


def affiliate_conversion_rate(row: dict[str, Any]) -> float:
    conversion = score_from_topic(row, "estimated_conversion", "conversion_score", "buyer_intent")
    return round(max(0.005, min(0.12, conversion / 1000)), 4)


def infer_article_type(topic: str, slug: str = "") -> str:
    kind = article_type_from_slug(slug, topic)
    if kind == "support":
        lowered = f" {topic.lower()} "
        if "best" in lowered:
            return "best list"
        return infer_intent(topic)
    if kind == "alternatives":
        return "alternatives"
    return kind


def priority_from_score(score: float) -> str:
    if score >= 85:
        return "P1"
    if score >= 75:
        return "P2"
    if score >= 65:
        return "P3"
    return "P4"


def priority_action(article_exists: bool, final_score: float) -> str:
    if article_exists:
        return "REFRESH" if final_score >= 55 else "MONITOR"
    return "CREATE" if final_score >= 55 else "WATCH"


def build_ai_priority_dashboard(
    topics: list[dict[str, Any]] | None = None,
    money_rows: list[dict[str, Any]] | None = None,
    duplicate_rows: list[dict[str, Any]] | None = None,
    inventory: list[dict[str, Any]] | None = None,
    authority_rows: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    topics = topics if topics is not None else topic_rows()
    inventory = inventory if inventory is not None else content_inventory()
    money_rows = money_rows if money_rows is not None else build_money_ranking(topics)
    duplicate_rows = duplicate_rows if duplicate_rows is not None else build_duplicate_report(topics, inventory)
    authority_rows = authority_rows if authority_rows is not None else build_authority_score(inventory)
    weights = load_priority_weights()
    existing = existing_slug_map(inventory)
    money_by_slug = {row.get("slug"): row for row in money_rows}
    duplicate_by_slug = {row.get("slug"): row for row in duplicate_rows}
    authority_by_cluster = {row.get("cluster"): row for row in authority_rows}
    output: list[dict[str, Any]] = []
    for topic_row in topics:
        topic = str(topic_row.get("topic", "")).strip()
        slug = row_slug(topic_row)
        inventory_row = existing.get(slug, {})
        article_exists = bool(inventory_row) or duplicate_by_slug.get(slug, {}).get("decision") in {"REFRESH_EXISTING", "MERGE"}
        cluster = cluster_for(f"{topic} {slug}")
        money = numeric(money_by_slug.get(slug, {}).get("money_score"))
        trend = score_from_topic(topic_row, "trend_score", "freshness")
        affiliate = score_from_topic(topic_row, "affiliate_value", "affiliate_opportunity", "revenue_score")
        competition = 100 - score_from_topic(topic_row, "competition", "competition_level", "difficulty")
        content_gap = numeric(authority_by_cluster.get(cluster, {}).get("content_gap_score"), 50)
        internal_link = score_from_topic(topic_row, "internal_linking_opportunity", "internal_link_score")
        impressions = numeric(inventory_row.get("impressions"))
        ctr = numeric(inventory_row.get("ctr"))
        impression = min(100, impressions / 10) if impressions else score_from_topic(topic_row, "traffic_score", "estimated_traffic")
        ctr_score = max(0, 100 - ctr * 20) if impressions else 50
        youtube = score_from_topic(topic_row, "youtube_potential", "video_score")
        social = topic_social_score(topic_row)
        components = {
            "money_score": money,
            "trend_score": trend,
            "affiliate_score": affiliate,
            "competition_score": competition,
            "content_gap_score": content_gap,
            "internal_link_score": internal_link,
            "impression_score": impression,
            "ctr_score": ctr_score,
            "youtube_score": youtube,
            "social_score": social,
        }
        final_score = round(sum(components[key] * weights.get(key, 0) for key in DEFAULT_PRIORITY_WEIGHTS), 1)
        traffic = estimated_monthly_traffic(topic_row, inventory_row)
        conversion_rate = affiliate_conversion_rate(topic_row)
        estimated_value = round(traffic * conversion_rate * max(5, affiliate / 4), 2)
        revenue_score = round(min(100, estimated_value / 8), 1)
        article_type = infer_article_type(topic, slug)
        action = priority_action(article_exists, final_score)
        output.append(
            {
                "topic": topic,
                "slug": slug,
                "article_exists": "YES" if article_exists else "NO",
                "recommended_action": action,
                "article_type": article_type,
                **{key: round(value, 1) for key, value in components.items()},
                "final_score": final_score,
                "estimated_monthly_traffic": traffic,
                "affiliate_conversion_rate": conversion_rate,
                "estimated_revenue_score": revenue_score,
                "estimated_value": estimated_value,
                "reason": f"{action}: {cluster}; duplicate={duplicate_by_slug.get(slug, {}).get('decision', 'unknown')}",
            }
        )
    output = sorted(output, key=lambda item: numeric(item.get("final_score")), reverse=True)
    for index, row in enumerate(output, 1):
        row["rank"] = index
    return output


def build_duplicate_report(topics: list[dict[str, Any]] | None = None, inventory: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    topics = topics if topics is not None else topic_rows()
    inventory = inventory if inventory is not None else content_inventory()
    existing = []
    for row in inventory:
        slug = row_slug(row)
        if slug:
            existing.append({"slug": slug, "topic": row.get("topic") or slug.replace("-", " "), "article_url": row.get("article_url", "")})
    output = []
    for topic_row in topics:
        topic = str(topic_row.get("topic", "")).strip()
        slug = row_slug(topic_row)
        best = {"slug": "", "topic": "", "article_url": "", "title": 0.0, "slug_sim": 0.0, "keyword": 0.0, "score": 0.0}
        for item in existing:
            if item["slug"] == slug:
                title_score = 100.0
                slug_score = 100.0
            else:
                title_score = similarity(topic, str(item["topic"]))
                slug_score = similarity(slug, str(item["slug"]))
            keyword_score = keyword_similarity(topic, str(item["topic"]))
            duplicate_score = round(title_score * 0.45 + slug_score * 0.35 + keyword_score * 0.2, 1)
            if duplicate_score > best["score"]:
                best = {**item, "title": title_score, "slug_sim": slug_score, "keyword": keyword_score, "score": duplicate_score}
        if best["score"] >= 92:
            decision = "REFRESH_EXISTING"
        elif best["score"] >= 85:
            decision = "MERGE"
        elif best["score"] >= 70:
            decision = "WATCH_DUPLICATE_RISK"
        else:
            decision = "NEW_TOPIC_OK"
        output.append(
            {
                "topic": topic,
                "slug": slug,
                "matched_slug": best["slug"],
                "matched_url": best["article_url"],
                "title_similarity": best["title"],
                "slug_similarity": best["slug_sim"],
                "keyword_similarity": best["keyword"],
                "duplicate_score": best["score"],
                "decision": decision,
                "reason": "Existing page is a close match" if best["score"] >= 85 else "No high-risk duplicate found",
            }
        )
    return sorted(output, key=lambda item: numeric(item.get("duplicate_score")), reverse=True)


def money_decision(score: float, duplicate_decision: str) -> str:
    if duplicate_decision in {"REFRESH_EXISTING", "MERGE"} and score >= 65:
        return "REFRESH"
    if score >= 82:
        return "WRITE NOW"
    if score >= 70:
        return "WRITE THIS WEEK"
    if score >= 55:
        return "WATCH"
    if score < 35:
        return "DELETE"
    return "WATCH"


def build_money_ranking(topics: list[dict[str, Any]] | None = None, duplicates: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    topics = topics if topics is not None else topic_rows()
    duplicates = duplicates if duplicates is not None else build_duplicate_report(topics)
    duplicate_by_slug = {row.get("slug"): row for row in duplicates}
    output = []
    for topic_row in topics:
        topic = str(topic_row.get("topic", ""))
        slug = row_slug(topic_row)
        text = f" {topic.lower()} "
        buyer = score_from_topic(topic_row, "buyer_intent", "buyer_intent_score", "search_intent")
        affiliate = score_from_topic(topic_row, "affiliate_value", "affiliate_opportunity", "revenue_score")
        cpc = score_from_topic(topic_row, "cpc_potential", "revenue_score")
        seo = score_from_topic(topic_row, "seo_score", "seo_opportunity")
        trend = score_from_topic(topic_row, "trend_score", "freshness")
        evergreen = score_from_topic(topic_row, "evergreen_potential", "evergreen_value")
        competition = score_from_topic(topic_row, "competition", "competition_level", "difficulty")
        product_review = 90 if any(term in text for term in REVIEW_TERMS) else 45
        comparison = 90 if any(term in text for term in COMPARISON_TERMS) else 35
        pricing = 90 if any(term in text for term in PRICING_TERMS) else 35
        conversion = round(buyer * 0.45 + affiliate * 0.25 + cpc * 0.2 + (100 - competition) * 0.1, 1)
        base = buyer * 0.21 + affiliate * 0.2 + cpc * 0.12 + seo * 0.14 + trend * 0.08 + evergreen * 0.1 + (100 - competition) * 0.15
        if any(term in text for term in COMMERCIAL_TERMS):
            base += 8
        if any(term in text for term in NEWS_TERMS):
            base -= 18
        money_score = round(max(0, min(100, base)), 1)
        revenue = round((score_from_topic(topic_row, "estimated_traffic", "traffic_score") * 18) * (conversion / 100) * 0.035 * 18, 2)
        dup = duplicate_by_slug.get(slug, {})
        decision = money_decision(money_score, str(dup.get("decision", "")))
        output.append(
            {
                "topic": topic,
                "slug": slug,
                "buyer_intent_score": round(buyer, 1),
                "affiliate_fit_score": round(affiliate, 1),
                "product_review_score": product_review,
                "comparison_score": comparison,
                "pricing_score": pricing,
                "conversion_score": conversion,
                "revenue_estimate": revenue,
                "money_score": money_score,
                "decision": decision,
                "reason": f"{infer_intent(topic)} intent; duplicate={dup.get('decision', 'unknown')}",
            }
        )
    output = sorted(output, key=lambda item: (numeric(item.get("money_score")), numeric(item.get("revenue_estimate"))), reverse=True)
    for index, row in enumerate(output, 1):
        row["rank"] = index
    return output


def build_publishing_queue(money_rows: list[dict[str, Any]] | None = None, inventory: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    money_rows = money_rows if money_rows is not None else build_money_ranking()
    inventory = inventory if inventory is not None else content_inventory()
    existing = {row_slug(row): row for row in inventory}
    uploads = load_upload_links()
    today = date.today()
    output = []
    for index, row in enumerate(money_rows, 1):
        slug = str(row.get("slug", ""))
        current = existing.get(slug, {})
        upload = uploads.get(slug, {})
        article_url = current.get("article_url") or upload.get("article_url") or f"{BASE_URL}/{slug}/"
        decision = str(row.get("decision", "WATCH"))
        if decision == "REFRESH":
            article_status = "Needs Refresh"
        elif current:
            article_status = "Published"
        elif decision in {"WRITE NOW", "WRITE THIS WEEK"}:
            article_status = "Candidate"
        else:
            article_status = "Rejected" if decision == "DELETE" else "Candidate"
        output.append(
            {
                "topic": row.get("topic", ""),
                "slug": slug,
                "article_url": article_url,
                "publish_priority": f"P{min(5, max(1, index))}",
                "target_publish_date": (today + timedelta(days=0 if decision == "WRITE NOW" else 3 if decision == "WRITE THIS WEEK" else 14)).isoformat(),
                "article_status": article_status,
                "video_status": "Uploaded" if upload.get("youtube_url") else "Needs video" if decision in {"WRITE NOW", "REFRESH"} else "Optional",
                "social_status": "Draft only",
                "index_status": current.get("index_status", "Not checked"),
                "last_checked": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "next_action": "Refresh existing article" if decision == "REFRESH" else "Write article draft" if decision.startswith("WRITE") else "Monitor",
            }
        )
    return output


def build_authority_score(inventory: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    inventory = inventory if inventory is not None else content_inventory()
    grouped: dict[str, dict[str, Any]] = defaultdict(lambda: {"article_count": 0, "indexed_count": 0, "impressions": 0.0, "clicks": 0.0, "positions": []})
    for row in inventory:
        cluster = cluster_for(f"{row.get('topic', '')} {row.get('slug', '')}")
        item = grouped[cluster]
        item["article_count"] += 1
        if str(row.get("index_status", "")).lower() in {"tracked", "indexed", "published"}:
            item["indexed_count"] += 1
        item["impressions"] += numeric(row.get("impressions"))
        item["clicks"] += numeric(row.get("google_clicks") or row.get("clicks"))
        position = numeric(row.get("avg_position") or row.get("position"))
        if position:
            item["positions"].append(position)
    output = []
    for cluster, item in grouped.items():
        article_count = item["article_count"]
        indexed = item["indexed_count"]
        avg_position = round(sum(item["positions"]) / len(item["positions"]), 1) if item["positions"] else 0
        authority = round(min(100, article_count * 4 + indexed * 6 + min(25, item["impressions"] / 120) + min(20, item["clicks"] * 2) + (15 if avg_position and avg_position <= 20 else 0)), 1)
        gap = round(max(0, 100 - authority), 1)
        output.append(
            {
                "cluster": cluster,
                "article_count": article_count,
                "indexed_count": indexed,
                "internal_link_count": max(0, article_count * 3),
                "impressions": round(item["impressions"], 1),
                "clicks": round(item["clicks"], 1),
                "average_position": avg_position,
                "authority_score": authority,
                "content_gap_score": gap,
            }
        )
    return sorted(output, key=lambda row: numeric(row.get("content_gap_score")), reverse=True)


def article_type_from_slug(slug: str, topic: str = "") -> str:
    text = f" {slug} {topic} ".lower()
    if "pricing" in text or "cost" in text:
        return "pricing"
    if "alternatives" in text or "alternative" in text:
        return "alternatives"
    if " vs " in text or "-vs-" in text or "comparison" in text:
        return "comparison"
    if "tutorial" in text or "how-to" in text or "guide" in text:
        return "tutorial"
    if "faq" in text:
        return "faq"
    if "review" in text:
        return "review"
    return "support"


def build_content_gap(inventory: list[dict[str, Any]] | None = None, authority_rows: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    inventory = inventory if inventory is not None else content_inventory()
    authority_rows = authority_rows if authority_rows is not None else build_authority_score(inventory)
    by_cluster: dict[str, dict[str, set[str] | str]] = defaultdict(lambda: {"types": set(), "target": ""})
    for row in inventory:
        slug = row_slug(row)
        cluster = cluster_for(f"{row.get('topic', '')} {slug}")
        by_cluster[cluster]["types"].add(article_type_from_slug(slug, str(row.get("topic", ""))))  # type: ignore[index]
        if not by_cluster[cluster]["target"]:
            by_cluster[cluster]["target"] = str(row.get("article_url") or f"{BASE_URL}/{slug}/")
    needed = ["review", "pricing", "alternatives", "comparison", "tutorial", "faq", "video"]
    authority_by_cluster = {row["cluster"]: row for row in authority_rows}
    output = []
    for cluster, data in by_cluster.items():
        types = data["types"] if isinstance(data["types"], set) else set()
        for missing in needed:
            if missing in types:
                continue
            priority = "High" if numeric(authority_by_cluster.get(cluster, {}).get("content_gap_score")) >= 70 and missing in {"review", "pricing", "comparison"} else "Medium"
            base = cluster.lower().replace("ai ", "ai ").replace(" ", "-")
            slug = slugify(f"{base}-{missing}-2026")
            title_type = "Video Review" if missing == "video" else missing.title()
            output.append(
                {
                    "cluster": cluster,
                    "base_slug": base,
                    "missing_article_type": missing,
                    "suggested_title": f"{cluster} {title_type} 2026",
                    "suggested_slug": slug,
                    "priority": priority,
                    "reason": f"{cluster} cluster is missing a {missing} asset.",
                    "internal_link_target": data["target"],
                }
            )
    return output


def build_content_clusters(inventory: list[dict[str, Any]] | None = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    inventory = inventory if inventory is not None else content_inventory()
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in inventory:
        grouped[cluster_for(f"{row.get('topic', '')} {row.get('slug', '')}")].append(row)
    clusters = []
    links = []
    for cluster, rows in sorted(grouped.items()):
        typed: dict[str, list[str]] = defaultdict(list)
        urls: dict[str, str] = {}
        for row in rows:
            slug = row_slug(row)
            typed[article_type_from_slug(slug, str(row.get("topic", "")))].append(slug)
            urls[slug] = str(row.get("article_url") or f"{BASE_URL}/{slug}/")
        pillar_slug = (typed.get("best") or typed.get("review") or typed.get("support") or [row_slug(rows[0])])[0]
        pillar_url = urls.get(pillar_slug, f"{BASE_URL}/{pillar_slug}/")
        video_ideas = [slug for slug in typed.get("review", [])[:5] if slug]
        clusters.append(
            {
                "cluster": cluster,
                "pillar_page": pillar_url,
                "review_pages": ", ".join(typed.get("review", [])[:12]),
                "comparison_pages": ", ".join(typed.get("comparison", [])[:12]),
                "pricing_pages": ", ".join(typed.get("pricing", [])[:12]),
                "tutorial_pages": ", ".join(typed.get("tutorial", [])[:12]),
                "alternatives_pages": ", ".join(typed.get("alternatives", [])[:12]),
                "faq_pages": ", ".join(typed.get("faq", [])[:12]),
                "video_ideas": ", ".join(video_ideas),
            }
        )
        for row in rows[:25]:
            source_slug = row_slug(row)
            if source_slug and source_slug != pillar_slug:
                links.append(
                    {
                        "source_slug": source_slug,
                        "source_url": urls.get(source_slug, f"{BASE_URL}/{source_slug}/"),
                        "target_slug": pillar_slug,
                        "target_url": pillar_url,
                        "anchor_text": cluster,
                        "cluster": cluster,
                        "reason": "Child page should reinforce the cluster pillar.",
                        "priority": "High" if article_type_from_slug(source_slug) in {"review", "pricing", "comparison"} else "Medium",
                    }
                )
    return clusters, links


def build_today_write_plan(
    money_rows: list[dict[str, Any]] | None = None,
    duplicate_rows: list[dict[str, Any]] | None = None,
    gap_rows: list[dict[str, Any]] | None = None,
    priority_rows: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    priority_rows = priority_rows if priority_rows is not None else build_ai_priority_dashboard(money_rows=money_rows, duplicate_rows=duplicate_rows)
    money_rows = money_rows if money_rows is not None else build_money_ranking()
    duplicate_rows = duplicate_rows if duplicate_rows is not None else build_duplicate_report()
    gap_rows = gap_rows if gap_rows is not None else build_content_gap()
    duplicate_by_slug = {row.get("slug"): row for row in duplicate_rows}
    plan: list[dict[str, Any]] = []
    seen_slugs: set[str] = set()
    for row in priority_rows:
        slug = str(row.get("slug", ""))
        if slug in seen_slugs:
            continue
        action = str(row.get("recommended_action", "WATCH"))
        if action not in {"CREATE", "REFRESH"}:
            continue
        seen_slugs.add(slug)
        dup = duplicate_by_slug.get(slug, {})
        youtube_action = "CREATE VIDEO" if numeric(row.get("youtube_score")) >= 70 else "OPTIONAL"
        plan.append(
            {
                "topic": row.get("topic", ""),
                "slug": slug,
                "reason": row.get("reason", ""),
                "action": action,
                "priority": priority_from_score(numeric(row.get("final_score"))),
                "article_type": row.get("article_type", ""),
                "target_keyword": str(row.get("topic", "")).lower(),
                "suggested_title": title_for(str(row.get("topic", ""))),
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
                "final_score": row.get("final_score", ""),
                "estimated_monthly_traffic": row.get("estimated_monthly_traffic", ""),
                "affiliate_conversion_rate": row.get("affiliate_conversion_rate", ""),
                "estimated_revenue_score": row.get("estimated_revenue_score", ""),
                "estimated_value": row.get("estimated_value", ""),
                "youtube_action": youtube_action,
                "risk_note": f"Duplicate risk: {dup.get('decision', 'unknown')} ({dup.get('duplicate_score', 0)})",
            }
        )
        if len(plan) >= 25:
            break
    for gap in gap_rows[:5]:
        slug = str(gap.get("suggested_slug", ""))
        if slug in seen_slugs:
            continue
        seen_slugs.add(slug)
        plan.append(
            {
                "topic": gap.get("suggested_title", ""),
                "slug": slug,
                "reason": gap.get("reason", ""),
                "action": "CONTENT GAP",
                "priority": "P3" if gap.get("priority") == "High" else "P4",
                "article_type": gap.get("missing_article_type", ""),
                "target_keyword": str(gap.get("suggested_title", "")).lower(),
                "suggested_title": gap.get("suggested_title", ""),
                "money_score": "",
                "trend_score": "",
                "affiliate_score": "",
                "competition_score": "",
                "content_gap_score": "",
                "internal_link_score": "",
                "impression_score": "",
                "ctr_score": "",
                "youtube_score": "",
                "social_score": "",
                "final_score": "",
                "estimated_monthly_traffic": "",
                "affiliate_conversion_rate": "",
                "estimated_revenue_score": "",
                "estimated_value": "",
                "youtube_action": "OPTIONAL",
                "risk_note": "Create only after duplicate check.",
            }
        )
    return plan


def build_revenue_opportunity(priority_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for row in priority_rows:
        if numeric(row.get("estimated_revenue_score")) <= 0:
            continue
        rows.append(
            {
                "topic": row.get("topic", ""),
                "slug": row.get("slug", ""),
                "article_type": row.get("article_type", ""),
                "estimated_monthly_traffic": row.get("estimated_monthly_traffic", ""),
                "affiliate_conversion_rate": row.get("affiliate_conversion_rate", ""),
                "estimated_revenue_score": row.get("estimated_revenue_score", ""),
                "estimated_value": row.get("estimated_value", ""),
                "affiliate_score": row.get("affiliate_score", ""),
                "money_score": row.get("money_score", ""),
                "final_score": row.get("final_score", ""),
                "recommended_action": row.get("recommended_action", ""),
            }
        )
    rows = sorted(rows, key=lambda item: (numeric(item.get("estimated_revenue_score")), numeric(item.get("final_score"))), reverse=True)
    for index, row in enumerate(rows, 1):
        row["rank"] = index
    return rows


def schedule_bucket(article_type: str) -> str:
    lowered = str(article_type).lower()
    if "review" in lowered:
        return "review"
    if "best" in lowered or "list" in lowered:
        return "best list"
    if "comparison" in lowered or "alternative" in lowered or "pricing" in lowered:
        return "comparison"
    return "review"


def build_daily_publishing_schedule(priority_rows: list[dict[str, Any]], gap_rows: list[dict[str, Any]] | None = None, days: int = 30) -> list[dict[str, Any]]:
    candidates = [row for row in priority_rows if row.get("recommended_action") == "CREATE"]
    for gap in gap_rows or []:
        candidates.append(
            {
                "topic": gap.get("suggested_title", ""),
                "slug": gap.get("suggested_slug", ""),
                "recommended_action": "CREATE",
                "article_type": gap.get("missing_article_type", ""),
                "final_score": 60 if gap.get("priority") == "High" else 52,
                "estimated_value": "",
                "estimated_revenue_score": "",
            }
        )
    buckets: dict[str, list[dict[str, Any]]] = {
        "review": [row for row in candidates if schedule_bucket(str(row.get("article_type", ""))) == "review"],
        "best list": [row for row in candidates if schedule_bucket(str(row.get("article_type", ""))) == "best list"],
        "comparison": [row for row in candidates if schedule_bucket(str(row.get("article_type", ""))) == "comparison"],
    }
    for key in buckets:
        buckets[key] = sorted(buckets[key], key=lambda row: numeric(row.get("final_score")), reverse=True)
    output: list[dict[str, Any]] = []
    today = date.today()
    used: set[str] = set()
    for offset in range(days):
        for bucket in ("review", "best list", "comparison"):
            if not buckets[bucket]:
                continue
            row = buckets[bucket].pop(0)
            slug = str(row.get("slug", ""))
            if slug in used:
                continue
            used.add(slug)
            output.append(
                {
                    "date": (today + timedelta(days=offset)).isoformat(),
                    "topic": row.get("topic", ""),
                    "slug": slug,
                    "article_type": row.get("article_type", ""),
                    "priority": priority_from_score(numeric(row.get("final_score"))),
                    "estimated_value": row.get("estimated_value", ""),
                    "estimated_revenue_score": row.get("estimated_revenue_score", ""),
                }
            )
    return output


def build_website_publishing_queue(today_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for row in today_rows:
        if row.get("action") not in {"CREATE", "CONTENT GAP"}:
            continue
        slug = str(row.get("slug", ""))
        output.append(
            {
                "topic": row.get("topic", ""),
                "slug": slug,
                "article_url": f"{BASE_URL}/{slug}/",
                "article_type": row.get("article_type", ""),
                "priority": row.get("priority", ""),
                "status": "READY_FOR_REVIEW",
                "estimated_value": row.get("estimated_value", ""),
                "estimated_revenue_score": row.get("estimated_revenue_score", ""),
                "next_action": "Human review required before publishing.",
                "notes": "Draft only. Not published by automation.",
            }
        )
    return output


def build_executive_summary(
    priority_rows: list[dict[str, Any]],
    today_rows: list[dict[str, Any]],
    revenue_rows: list[dict[str, Any]],
    gap_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    def add(section: str, source: list[dict[str, Any]], topic_key: str = "topic", action_key: str = "recommended_action") -> None:
        for index, row in enumerate(source[:10], 1):
            rows.append(
                {
                    "section": section,
                    "rank": index,
                    "topic": row.get(topic_key, ""),
                    "slug": row.get("slug") or row.get("suggested_slug", ""),
                    "action": row.get(action_key, row.get("action", "")),
                    "final_score": row.get("final_score", ""),
                    "estimated_value": row.get("estimated_value", ""),
                    "notes": row.get("reason", row.get("risk_note", "")),
                }
            )

    add("Top 10 Topics To Write Today", [row for row in today_rows if row.get("action") == "CREATE"], action_key="action")
    add("Top 10 Revenue Opportunities", revenue_rows)
    add("Top 10 Refresh Opportunities", [row for row in priority_rows if row.get("recommended_action") == "REFRESH"])
    add("Top 10 Content Gaps", gap_rows, topic_key="suggested_title", action_key="missing_article_type")
    return rows


def title_for(topic: str) -> str:
    clean = str(topic).strip()
    if re.search(r"\b2026\b", clean, re.I):
        return clean.title()
    return f"{clean.title()} 2026"


def optimize_article_text(input_text: str, slug: str = "", youtube_url: str = "") -> tuple[str, dict[str, Any]]:
    text = input_text.strip()
    plain = re.sub(r"<[^>]+>", " ", text)
    title_match = re.search(r"<h1[^>]*>(.*?)</h1>", text, re.I | re.S) or re.search(r"^#\s+(.+)$", text, re.M)
    title = re.sub(r"<[^>]+>", "", title_match.group(1)).strip() if title_match else title_for(slug.replace("-", " ") if slug else "AI Software Review")
    meta = f"Independent {title} guide covering features, pricing, pros, cons, alternatives, and buyer fit."
    sections_added = []
    body = text
    if "<h1" not in body.lower() and not re.search(r"^#\s+", body, re.M):
        body = f"<h1>{html.escape(title)}</h1>\n\n{body}"
        sections_added.append("H1")
    for heading, content in [
        ("Table of Contents", "<ul><li>Overview</li><li>Pros and Cons</li><li>Pricing</li><li>Alternatives</li><li>FAQ</li></ul>"),
        ("Pros and Cons", "<p>Add concise buyer-focused pros and cons before publishing.</p>"),
        ("Pricing", "<p>Verify current pricing on the official website before buying.</p>"),
        ("Alternatives", "<p>Compare this option with related tools before making a final decision.</p>"),
        ("FAQ", "<p><strong>Is this tool worth it?</strong> It depends on workflow fit, budget, and current feature limits.</p>"),
    ]:
        if heading.lower() not in body.lower():
            body += f"\n\n<h2>{heading}</h2>\n{content}"
            sections_added.append(heading)
    if youtube_url and "watch the video review" not in body.lower():
        body += f'\n\n<h2>Watch the video review</h2>\n<p><a href="{html.escape(youtube_url)}" rel="noopener">Watch on YouTube</a></p>'
        sections_added.append("YouTube")
    if "application/ld+json" not in body.lower():
        schema = {
            "@context": "https://schema.org",
            "@type": "Article",
            "headline": title,
            "author": {"@type": "Person", "name": "Tuan Nguyen Quoc"},
            "dateModified": datetime.now(timezone.utc).isoformat(),
        }
        body += f'\n\n<script type="application/ld+json">{json.dumps(schema, ensure_ascii=False)}</script>'
        sections_added.append("Schema")
    report = {
        "slug": slug,
        "seo_title": title[:60],
        "meta_description": meta[:155],
        "sections_added": ", ".join(sections_added),
        "youtube_placeholder": "yes" if youtube_url else "no",
        "schema_added": "yes" if "Schema" in sections_added else "already_exists",
        "status": "optimized",
    }
    return body, report


def write_content_operations_outputs() -> dict[str, Any]:
    topics = topic_rows()
    inventory = content_inventory()
    duplicates = build_duplicate_report(topics, inventory)
    money = build_money_ranking(topics, duplicates)
    queue = build_publishing_queue(money, inventory)
    authority = build_authority_score(inventory)
    gap = build_content_gap(inventory, authority)
    clusters, cluster_links = build_content_clusters(inventory)
    priority = build_ai_priority_dashboard(topics, money, duplicates, inventory, authority)
    today = build_today_write_plan(money, duplicates, gap, priority)
    revenue_opportunity = build_revenue_opportunity(priority)
    schedule = build_daily_publishing_schedule(priority, gap)
    website_queue = build_website_publishing_queue(today)
    executive_summary = build_executive_summary(priority, today, revenue_opportunity, gap)
    auto_editor_report = read_csv(DATA_DIR / "ai_auto_editor_report.csv")

    outputs = [
        ("duplicate_report", duplicates, DUPLICATE_FIELDS),
        ("money_ranking", money, MONEY_RANKING_FIELDS),
        ("publishing_queue", queue, PUBLISHING_QUEUE_FIELDS),
        ("ai_priority_dashboard", priority, AI_PRIORITY_DASHBOARD_FIELDS),
        ("revenue_opportunity", revenue_opportunity, REVENUE_OPPORTUNITY_FIELDS),
        ("daily_publishing_schedule", schedule, DAILY_PUBLISHING_SCHEDULE_FIELDS),
        ("website_publishing_queue", website_queue, WEBSITE_PUBLISHING_QUEUE_FIELDS),
        ("executive_content_summary", executive_summary, EXECUTIVE_SUMMARY_FIELDS),
        ("authority_score", authority, AUTHORITY_FIELDS),
        ("content_gap", gap, CONTENT_GAP_FIELDS),
        ("content_clusters", clusters, CONTENT_CLUSTER_FIELDS),
        ("internal_link_cluster_plan", cluster_links, INTERNAL_LINK_CLUSTER_FIELDS),
        ("today_write_plan", today, TODAY_WRITE_PLAN_FIELDS),
    ]
    for name, rows, fields in outputs:
        write_csv(DATA_DIR / f"{name}.csv", rows, fields)
        write_json(DATA_DIR / f"{name}.json", rows)
    if not auto_editor_report:
        write_csv(DATA_DIR / "ai_auto_editor_report.csv", [], AUTO_EDITOR_REPORT_FIELDS)
    update_master_workbook(
        {
            "Today Write Plan": (today, TODAY_WRITE_PLAN_FIELDS),
            "Money Ranking": (money, MONEY_RANKING_FIELDS),
            "AI Priority Dashboard": (priority, AI_PRIORITY_DASHBOARD_FIELDS),
            "Revenue Opportunity": (revenue_opportunity, REVENUE_OPPORTUNITY_FIELDS),
            "Daily Publishing Schedule": (schedule, DAILY_PUBLISHING_SCHEDULE_FIELDS),
            "Website Publishing Queue": (website_queue, WEBSITE_PUBLISHING_QUEUE_FIELDS),
            "Executive Content Summary": (executive_summary, EXECUTIVE_SUMMARY_FIELDS),
            "Publishing Queue": (queue, PUBLISHING_QUEUE_FIELDS),
            "Duplicate Risk": (duplicates, DUPLICATE_FIELDS),
            "Authority Score": (authority, AUTHORITY_FIELDS),
            "Content Gap": (gap, CONTENT_GAP_FIELDS),
            "Content Clusters": (clusters, CONTENT_CLUSTER_FIELDS),
            "Internal Link Cluster Plan": (cluster_links, INTERNAL_LINK_CLUSTER_FIELDS),
            "AI Auto Editor Report": (auto_editor_report, AUTO_EDITOR_REPORT_FIELDS),
        }
    )
    return {
        "topics": len(topics),
        "duplicates": len(duplicates),
        "money": len(money),
        "queue": len(queue),
        "priority": len(priority),
        "revenue_opportunity": len(revenue_opportunity),
        "daily_schedule": len(schedule),
        "website_queue": len(website_queue),
        "authority": len(authority),
        "content_gap": len(gap),
        "clusters": len(clusters),
        "internal_links": len(cluster_links),
        "today_write_plan": len(today),
    }
