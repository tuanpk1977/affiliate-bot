from __future__ import annotations

import csv
import html
import json
import math
import re
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from modules.opportunity_forecast import FORECAST_FIELDS, build_forecast
from modules.performance_tracking import DATA_DIR, numeric, read_csv, slugify, update_master_workbook, write_csv, write_json


GOOGLE_TRENDS_FIELDS = ["date", "keyword", "growth", "country", "category", "trend_score", "source"]
GOOGLE_NEWS_FIELDS = ["date", "title", "url", "topic", "category", "freshness_score", "authority_score", "virality_score", "trend_score", "source"]
YOUTUBE_TRENDS_FIELDS = [
    "date",
    "title",
    "channel",
    "video_url",
    "views",
    "subscribers",
    "upload_time",
    "estimated_velocity",
    "keywords",
    "potential_blog_topic",
    "potential_review_topic",
    "trend_score",
    "source",
]
REDDIT_FIELDS = ["date", "subreddit", "topic", "discussion_url", "upvotes", "comments", "growth", "tracked_entity", "trend_score", "source"]
PRODUCTHUNT_FIELDS = [
    "date",
    "product",
    "url",
    "category",
    "votes",
    "comments",
    "votes_per_hour",
    "comments_per_hour",
    "hunter_count",
    "launch_momentum",
    "funding",
    "competitors",
    "potential_review_article",
    "potential_comparison_article",
    "potential_youtube_video",
    "trend_score",
    "source",
]
X_TRENDS_FIELDS = ["date", "tracked_entity", "keyword", "linked_website", "shared_product", "mentions", "engagement", "trend_score", "source"]
LINKEDIN_FIELDS = ["date", "topic", "category", "company", "url", "mentions", "engagement", "trend_score", "source"]
NEWSLETTER_FIELDS = ["date", "newsletter", "topic", "product", "url", "category", "signal_type", "trend_score", "source"]
AI_MEMORY_FIELDS = ["slug", "topic", "category", "publish_date", "traffic", "clicks", "affiliate_clicks", "revenue", "ctr", "ranking", "rpm", "recommendation"]
INTELLIGENCE_TOPIC_FIELDS = [
    "topic",
    "slug",
    "source",
    "category",
    "trend_score",
    "freshness",
    "estimated_traffic",
    "buyer_intent",
    "affiliate_value",
    "competition_level",
    "seo_opportunity",
    "youtube_potential",
    "reason",
]
AUTO_PRIORITY_FIELDS = [
    "rank",
    "topic",
    "slug",
    "recommended_action",
    "daily_priority",
    "money_score",
    "estimated_monthly_traffic",
    "estimated_revenue",
    "confidence_score",
    "risk_level",
    "source",
    "reason",
]

DEFAULT_TREND_KEYWORDS = [
    ("AI coding agents", "Programming"),
    ("AI website builder", "SaaS"),
    ("AI SEO software", "Marketing"),
    ("AI video software", "Marketing"),
    ("AI productivity tools", "Productivity"),
    ("AI agents for business", "SaaS"),
    ("marketing automation AI", "Marketing"),
    ("AI education tools", "Education"),
]
TRACKED_ENTITIES = ["ChatGPT", "Claude", "Gemini", "Cursor", "Copilot", "Lovable", "Bolt", "Replit", "OpenAI", "Anthropic"]


def today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def clean_topic(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def clamp(value: float, low: float = 0, high: float = 100) -> float:
    return max(low, min(high, value))


def scaled_log(value: Any, factor: float = 18) -> float:
    return round(clamp(math.log10(max(numeric(value), 0) + 1) * factor), 1)


def parse_growth(value: Any) -> float:
    text = str(value or "").strip().lower()
    if "breakout" in text:
        return 100.0
    if text.endswith("%"):
        return clamp(numeric(text[:-1]))
    return clamp(numeric(text))


def score_text_terms(text: str, terms: Iterable[str], points: float = 8) -> float:
    lower = text.lower()
    return sum(points for term in terms if term.lower() in lower)


def inferred_buyer_intent(topic: str) -> float:
    return clamp(38 + score_text_terms(topic, ("review", "pricing", "alternative", "alternatives", " vs ", "best", "software", "tool"), 7))


def inferred_affiliate_value(topic: str) -> float:
    return clamp(35 + score_text_terms(topic, ("software", "saas", "platform", "review", "pricing", "affiliate", "automation"), 8))


def inferred_competition(topic: str) -> float:
    generic = score_text_terms(topic, ("best", "software", "tools", "ai"), 8)
    long_tail_discount = max(0, len(topic.split()) - 3) * 4
    return clamp(58 + generic - long_tail_discount)


def to_topic_record(topic: str, source: str, category: str = "", trend_score: Any = 50, reason: str = "") -> dict[str, Any]:
    topic = clean_topic(topic)
    trend = clamp(numeric(trend_score, 50))
    competition = inferred_competition(topic)
    return {
        "topic": topic,
        "slug": slugify(topic),
        "source": source,
        "category": category,
        "trend_score": trend,
        "freshness": trend,
        "estimated_traffic": clamp(35 + trend * 0.35),
        "buyer_intent": inferred_buyer_intent(topic),
        "affiliate_value": inferred_affiliate_value(topic),
        "competition_level": competition,
        "seo_opportunity": clamp(100 - competition * 0.45 + trend * 0.35),
        "youtube_potential": clamp(40 + trend * 0.35 + score_text_terms(topic, ("review", "comparison", "best", "vs"), 5)),
        "reason": reason,
    }


def read_any_input(path: Path | None) -> list[dict[str, Any]]:
    if not path or not path.exists():
        return []
    if path.suffix.lower() == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            return [row for row in payload if isinstance(row, dict)]
        if isinstance(payload, dict):
            for key in ("items", "rows", "topics", "selected_topics", "all_candidates"):
                rows = payload.get(key)
                if isinstance(rows, list):
                    return [row for row in rows if isinstance(row, dict)]
        return []
    return read_csv(path)


def write_dual_outputs(csv_path: Path, json_path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    write_csv(csv_path, rows, fields)
    write_json(json_path, rows)


def normalize_google_trends(rows: list[dict[str, Any]] | None = None, country: str = "US") -> list[dict[str, Any]]:
    source_rows = rows or [{"keyword": keyword, "category": category, "growth": 50 + index * 4} for index, (keyword, category) in enumerate(DEFAULT_TREND_KEYWORDS)]
    normalized = []
    for row in source_rows:
        keyword = clean_topic(row.get("keyword") or row.get("topic") or row.get("query") or row.get("title"))
        if not keyword:
            continue
        growth = row.get("growth") or row.get("trend_score") or row.get("score") or 50
        normalized.append(
            {
                "date": row.get("date") or today(),
                "keyword": keyword,
                "growth": growth,
                "country": row.get("country") or country,
                "category": row.get("category") or "AI/SaaS",
                "trend_score": parse_growth(growth),
                "source": row.get("source") or "google_trends_manual_or_seed",
            }
        )
    return normalized


def parse_google_news_rss(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    root = ET.fromstring(path.read_text(encoding="utf-8"))
    rows = []
    for item in root.findall(".//item"):
        title = clean_topic(item.findtext("title"))
        url = clean_topic(item.findtext("link"))
        pub_date = clean_topic(item.findtext("pubDate"))
        if title:
            rows.append({"title": title, "url": url, "date": pub_date})
    return rows


def normalize_google_news(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = []
    for row in rows:
        title = clean_topic(row.get("title") or row.get("topic"))
        if not title:
            continue
        topic = clean_topic(row.get("topic") or title)
        freshness = clamp(numeric(row.get("freshness_score") or row.get("freshness"), 70))
        authority = clamp(numeric(row.get("authority_score"), 55) + score_text_terms(str(row.get("url", "")), (".edu", ".gov", "techcrunch", "theverge", "venturebeat"), 6))
        virality = clamp(numeric(row.get("virality_score") or row.get("mentions") or row.get("comments"), 40))
        trend = round(clamp(freshness * 0.45 + authority * 0.25 + virality * 0.30), 1)
        normalized.append(
            {
                "date": row.get("date") or today(),
                "title": title,
                "url": row.get("url", ""),
                "topic": topic,
                "category": row.get("category") or "AI/SaaS News",
                "freshness_score": freshness,
                "authority_score": authority,
                "virality_score": virality,
                "trend_score": trend,
                "source": row.get("source") or "google_news_manual_or_rss",
            }
        )
    return normalized


def normalize_youtube_trends(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = []
    for row in rows:
        title = clean_topic(row.get("title") or row.get("topic"))
        if not title:
            continue
        views = numeric(row.get("views"))
        subscribers = numeric(row.get("subscribers"))
        velocity = numeric(row.get("estimated_velocity"), scaled_log(views) + scaled_log(subscribers, 8))
        trend = clamp(velocity + score_text_terms(title, ("ai", "review", "tool", "agent", "automation"), 5))
        normalized.append(
            {
                "date": row.get("date") or today(),
                "title": title,
                "channel": row.get("channel", ""),
                "video_url": row.get("video_url") or row.get("url") or "",
                "views": views,
                "subscribers": subscribers,
                "upload_time": row.get("upload_time", ""),
                "estimated_velocity": round(velocity, 1),
                "keywords": row.get("keywords") or extract_keywords(title),
                "potential_blog_topic": row.get("potential_blog_topic") or f"{title} explained",
                "potential_review_topic": row.get("potential_review_topic") or f"{title} review",
                "trend_score": round(trend, 1),
                "source": row.get("source") or "youtube_manual",
            }
        )
    return normalized


def normalize_reddit(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = []
    for row in rows:
        topic = clean_topic(row.get("topic") or row.get("title"))
        if not topic:
            continue
        upvotes = numeric(row.get("upvotes"))
        comments = numeric(row.get("comments"))
        entity = row.get("tracked_entity") or next((entity for entity in TRACKED_ENTITIES if entity.lower() in topic.lower()), "")
        trend = clamp(scaled_log(upvotes) + scaled_log(comments, 14) + numeric(row.get("growth"), 0))
        normalized.append(
            {
                "date": row.get("date") or today(),
                "subreddit": row.get("subreddit", ""),
                "topic": topic,
                "discussion_url": row.get("discussion_url") or row.get("url") or "",
                "upvotes": upvotes,
                "comments": comments,
                "growth": row.get("growth", ""),
                "tracked_entity": entity,
                "trend_score": round(trend, 1),
                "source": row.get("source") or "reddit_manual",
            }
        )
    return normalized


def normalize_producthunt(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = []
    for row in rows:
        product = clean_topic(row.get("product") or row.get("topic") or row.get("title"))
        if not product:
            continue
        votes_per_hour = numeric(row.get("votes_per_hour"), numeric(row.get("votes")) / 24 if numeric(row.get("votes")) else 0)
        comments_per_hour = numeric(row.get("comments_per_hour"), numeric(row.get("comments")) / 24 if numeric(row.get("comments")) else 0)
        trend = clamp(votes_per_hour * 2.5 + comments_per_hour * 4 + numeric(row.get("hunter_count")) * 0.8 + numeric(row.get("launch_momentum"), 0))
        normalized.append(
            {
                "date": row.get("date") or today(),
                "product": product,
                "url": row.get("url", ""),
                "category": row.get("category") or "AI/SaaS",
                "votes": numeric(row.get("votes")),
                "comments": numeric(row.get("comments")),
                "votes_per_hour": round(votes_per_hour, 1),
                "comments_per_hour": round(comments_per_hour, 1),
                "hunter_count": numeric(row.get("hunter_count")),
                "launch_momentum": round(trend, 1),
                "funding": row.get("funding", ""),
                "competitors": row.get("competitors", ""),
                "potential_review_article": row.get("potential_review_article") or f"{product} Review 2026",
                "potential_comparison_article": row.get("potential_comparison_article") or f"{product} Alternatives",
                "potential_youtube_video": row.get("potential_youtube_video") or f"{product} Review Video",
                "trend_score": round(trend, 1),
                "source": row.get("source") or "producthunt_manual",
            }
        )
    return normalized


def normalize_simple_entity_rows(rows: list[dict[str, Any]], fields: list[str], source_name: str) -> list[dict[str, Any]]:
    normalized = []
    for row in rows:
        topic = clean_topic(row.get("topic") or row.get("keyword") or row.get("product") or row.get("title") or row.get("shared_product"))
        if not topic:
            continue
        mentions = numeric(row.get("mentions") or row.get("engagement") or row.get("score"))
        trend = clamp(numeric(row.get("trend_score"), 0) or scaled_log(mentions) + score_text_terms(topic, ("ai", "software", "saas", "tool"), 6))
        output = {field: row.get(field, "") for field in fields}
        output["date"] = output.get("date") or today()
        output["topic"] = output.get("topic") or topic
        if "keyword" in fields:
            output["keyword"] = output.get("keyword") or topic
        if "product" in fields:
            output["product"] = output.get("product") or topic
        output["trend_score"] = round(trend, 1)
        output["source"] = output.get("source") or source_name
        normalized.append(output)
    return normalized


def extract_keywords(text: str, limit: int = 8) -> str:
    words = [word.lower() for word in re.findall(r"[a-zA-Z][a-zA-Z0-9+.-]{2,}", text)]
    stop = {"the", "and", "for", "with", "review", "video", "this", "that", "from", "into", "best"}
    seen = []
    for word in words:
        if word not in stop and word not in seen:
            seen.append(word)
    return ", ".join(seen[:limit])


def source_csv_to_topics() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in read_csv(DATA_DIR / "google_trends.csv"):
        rows.append(to_topic_record(row.get("keyword", ""), row.get("source", "google_trends"), row.get("category", ""), row.get("trend_score"), "Google Trends signal"))
    for row in read_csv(DATA_DIR / "google_news.csv"):
        rows.append(to_topic_record(row.get("topic") or row.get("title", ""), row.get("source", "google_news"), row.get("category", ""), row.get("trend_score"), "Fresh Google News signal"))
    for row in read_csv(DATA_DIR / "youtube_trends.csv"):
        rows.append(to_topic_record(row.get("potential_review_topic") or row.get("title", ""), row.get("source", "youtube"), "YouTube", row.get("trend_score"), "YouTube velocity signal"))
    for row in read_csv(DATA_DIR / "reddit_intelligence.csv"):
        rows.append(to_topic_record(row.get("topic", ""), row.get("source", "reddit"), row.get("subreddit", ""), row.get("trend_score"), "Reddit discussion signal"))
    for row in read_csv(DATA_DIR / "producthunt_dashboard.csv"):
        rows.append(to_topic_record(row.get("potential_review_article") or row.get("product", ""), row.get("source", "producthunt"), row.get("category", ""), row.get("trend_score"), "Product Hunt launch signal"))
    for row in read_csv(DATA_DIR / "x_trends.csv"):
        rows.append(to_topic_record(row.get("keyword") or row.get("shared_product", ""), row.get("source", "x"), "X", row.get("trend_score"), "X entity signal"))
    for row in read_csv(DATA_DIR / "linkedin_trends.csv"):
        rows.append(to_topic_record(row.get("topic", ""), row.get("source", "linkedin"), row.get("category", ""), row.get("trend_score"), "LinkedIn business signal"))
    for row in read_csv(DATA_DIR / "newsletter_intelligence.csv"):
        rows.append(to_topic_record(row.get("topic") or row.get("product", ""), row.get("source", "newsletter"), row.get("category", ""), row.get("trend_score"), "AI newsletter signal"))
    deduped: dict[str, dict[str, Any]] = {}
    for row in rows:
        slug = row.get("slug")
        if not slug:
            continue
        current = deduped.get(slug)
        if not current or numeric(row.get("trend_score")) > numeric(current.get("trend_score")):
            deduped[slug] = row
    return sorted(deduped.values(), key=lambda row: numeric(row.get("trend_score")), reverse=True)


def write_intelligence_topics() -> list[dict[str, Any]]:
    rows = source_csv_to_topics()
    write_dual_outputs(DATA_DIR / "intelligence_topics.csv", DATA_DIR / "intelligence_topics.json", rows, INTELLIGENCE_TOPIC_FIELDS)
    return rows


def build_ai_memory_rows() -> list[dict[str, Any]]:
    lifecycle = read_csv(DATA_DIR / "content_lifecycle.csv")
    rows = []
    for row in lifecycle:
        traffic = numeric(row.get("impressions")) or numeric(row.get("google_clicks"))
        clicks = numeric(row.get("google_clicks"))
        revenue = numeric(row.get("revenue_estimate"))
        affiliate_clicks = numeric(row.get("affiliate_clicks"))
        rpm = round(revenue / max(traffic, 1) * 1000, 2) if traffic else 0
        if revenue > 20 or rpm > 20:
            recommendation = "Write more in this cluster"
        elif traffic > 100 and clicks < 3:
            recommendation = "Refresh title/meta and improve snippet"
        elif traffic < 10 and revenue <= 0:
            recommendation = "Monitor or avoid similar topics"
        else:
            recommendation = "Keep tracking"
        rows.append(
            {
                "slug": row.get("slug", ""),
                "topic": row.get("topic", ""),
                "category": infer_category(row.get("slug", "")),
                "publish_date": row.get("publish_date", ""),
                "traffic": traffic,
                "clicks": clicks,
                "affiliate_clicks": affiliate_clicks,
                "revenue": revenue,
                "ctr": row.get("ctr", ""),
                "ranking": row.get("avg_position", ""),
                "rpm": rpm,
                "recommendation": recommendation,
            }
        )
    return rows


def infer_category(slug: str) -> str:
    text = str(slug).lower()
    if "seo" in text or "semrush" in text or "ahrefs" in text:
        return "SEO"
    if "email" in text or "activecampaign" in text or "hubspot" in text:
        return "Email/CRM"
    if "website" in text or "webflow" in text or "framer" in text:
        return "Website Builder"
    if "coding" in text or "cursor" in text or "copilot" in text:
        return "AI Coding"
    if "video" in text:
        return "Video AI"
    return "AI/SaaS"


def write_ai_memory() -> list[dict[str, Any]]:
    rows = build_ai_memory_rows()
    write_dual_outputs(DATA_DIR / "ai_memory.csv", DATA_DIR / "ai_memory.json", rows, AI_MEMORY_FIELDS)
    return rows


def build_auto_priority_rows() -> list[dict[str, Any]]:
    forecast = build_forecast()
    intelligence = {row.get("slug"): row for row in source_csv_to_topics()}
    rows = []
    for row in forecast.rows:
        slug = row.get("slug", "")
        signal = intelligence.get(slug, {})
        action = action_for_forecast(row)
        risk = "Low" if numeric(row.get("confidence_score")) >= 70 and numeric(row.get("estimated_difficulty")) <= 55 else "Medium" if numeric(row.get("money_score")) >= 60 else "High"
        rows.append(
            {
                "rank": row.get("rank", ""),
                "topic": row.get("topic", ""),
                "slug": slug,
                "recommended_action": action,
                "daily_priority": priority_for_action(action, row),
                "money_score": row.get("money_score", ""),
                "estimated_monthly_traffic": row.get("estimated_monthly_traffic", ""),
                "estimated_revenue": row.get("estimated_revenue", ""),
                "confidence_score": row.get("confidence_score", ""),
                "risk_level": risk,
                "source": signal.get("source", ""),
                "reason": row.get("reason", ""),
            }
        )
    rows.sort(key=lambda item: (priority_sort(item.get("daily_priority")), numeric(item.get("money_score"))), reverse=True)
    return rows


def action_for_forecast(row: dict[str, Any]) -> str:
    decision = str(row.get("decision", ""))
    topic = str(row.get("topic", "")).lower()
    if decision == "REFRESH":
        return "Refresh"
    if decision in {"WRITE NOW", "WRITE THIS WEEK"}:
        return "Article"
    if "video" in topic or numeric(row.get("estimated_revenue")) >= 20:
        return "Video"
    if decision == "DELETE":
        return "Skip"
    return "Monitor"


def priority_for_action(action: str, row: dict[str, Any]) -> str:
    score = numeric(row.get("money_score"))
    if action in {"Article", "Refresh"} and score >= 78:
        return "P1 Today"
    if action in {"Article", "Video", "Refresh"} and score >= 62:
        return "P2 This Week"
    if action == "Skip":
        return "P5 Avoid"
    return "P3 Monitor"


def priority_sort(priority: Any) -> int:
    return {"P1 Today": 5, "P2 This Week": 4, "P3 Monitor": 3, "P5 Avoid": 1}.get(str(priority), 0)


def write_auto_priority_engine() -> list[dict[str, Any]]:
    rows = build_auto_priority_rows()
    write_dual_outputs(DATA_DIR / "auto_priority_engine.csv", DATA_DIR / "auto_priority_engine.json", rows, AUTO_PRIORITY_FIELDS)
    return rows


def build_content_intelligence_summary() -> dict[str, Any]:
    intelligence_topics = write_intelligence_topics()
    ai_memory = write_ai_memory()
    auto_priority = write_auto_priority_engine()
    forecast = build_forecast()
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "intelligence_topics": len(intelligence_topics),
        "ai_memory_rows": len(ai_memory),
        "auto_priority_rows": len(auto_priority),
        "estimated_monthly_traffic": int(forecast.totals.get("estimated_monthly_traffic", 0)),
        "estimated_monthly_revenue": forecast.totals.get("estimated_revenue", 0),
        "today_winners": auto_priority[:10],
        "weekly_winners": [row for row in auto_priority if row.get("daily_priority") in {"P1 Today", "P2 This Week"}][:20],
        "refresh_candidates": [row for row in auto_priority if row.get("recommended_action") == "Refresh"][:20],
        "video_candidates": [row for row in auto_priority if row.get("recommended_action") == "Video"][:20],
        "risk_alerts": [row for row in auto_priority if row.get("risk_level") == "High"][:20],
    }
    write_json(DATA_DIR / "content_intelligence_summary.json", summary)
    write_content_intelligence_html(DATA_DIR / "content_intelligence_dashboard.html", summary)
    update_intelligence_master_workbook(intelligence_topics, ai_memory, auto_priority)
    return summary


def write_content_intelligence_html(path: Path, summary: dict[str, Any]) -> None:
    def table(rows: list[dict[str, Any]], fields: list[str]) -> str:
        head = "".join(f"<th>{html.escape(field.replace('_', ' ').title())}</th>" for field in fields)
        body = "".join("<tr>" + "".join(f"<td>{html.escape(str(row.get(field, '')))}</td>" for field in fields) + "</tr>" for row in rows)
        return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"

    doc = f"""<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>AI Content Intelligence Dashboard</title>
<style>body{{font-family:Arial,sans-serif;margin:32px;background:#f8fafc;color:#172033}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:14px}}.card{{background:white;border:1px solid #d8e1ea;border-radius:8px;padding:16px}}.metric{{font-size:28px;font-weight:800;color:#0f766e}}table{{width:100%;border-collapse:collapse;background:white;margin:12px 0 28px}}td,th{{border:1px solid #d8e1ea;padding:8px;text-align:left}}th{{background:#e6fffb}}</style></head>
<body><h1>AI Content Intelligence Dashboard</h1><p>Generated: {html.escape(str(summary.get('generated_at', '')))}</p>
<div class="grid">
<div class="card"><strong>Estimated Monthly Traffic</strong><div class="metric">{summary.get('estimated_monthly_traffic')}</div></div>
<div class="card"><strong>Estimated Monthly Revenue</strong><div class="metric">${summary.get('estimated_monthly_revenue')}</div></div>
<div class="card"><strong>Intelligence Topics</strong><div class="metric">{summary.get('intelligence_topics')}</div></div>
<div class="card"><strong>Auto Priority Rows</strong><div class="metric">{summary.get('auto_priority_rows')}</div></div>
</div>
<h2>Today's Winners</h2>{table(summary.get('today_winners', []), AUTO_PRIORITY_FIELDS)}
<h2>This Week</h2>{table(summary.get('weekly_winners', []), AUTO_PRIORITY_FIELDS)}
<h2>Video Candidates</h2>{table(summary.get('video_candidates', []), AUTO_PRIORITY_FIELDS)}
<h2>Refresh Candidates</h2>{table(summary.get('refresh_candidates', []), AUTO_PRIORITY_FIELDS)}
<h2>Risk Alerts</h2>{table(summary.get('risk_alerts', []), AUTO_PRIORITY_FIELDS)}
</body></html>"""
    path.write_text(doc, encoding="utf-8")


def update_intelligence_master_workbook(intelligence_topics: list[dict[str, Any]], ai_memory: list[dict[str, Any]], auto_priority: list[dict[str, Any]]) -> bool:
    return update_master_workbook(
        {
            "Google Trends": (read_csv(DATA_DIR / "google_trends.csv"), GOOGLE_TRENDS_FIELDS),
            "Google News": (read_csv(DATA_DIR / "google_news.csv"), GOOGLE_NEWS_FIELDS),
            "YouTube Trends": (read_csv(DATA_DIR / "youtube_trends.csv"), YOUTUBE_TRENDS_FIELDS),
            "Reddit Intelligence": (read_csv(DATA_DIR / "reddit_intelligence.csv"), REDDIT_FIELDS),
            "Product Hunt": (read_csv(DATA_DIR / "producthunt_dashboard.csv"), PRODUCTHUNT_FIELDS),
            "X Trends": (read_csv(DATA_DIR / "x_trends.csv"), X_TRENDS_FIELDS),
            "LinkedIn Trends": (read_csv(DATA_DIR / "linkedin_trends.csv"), LINKEDIN_FIELDS),
            "Newsletter Intel": (read_csv(DATA_DIR / "newsletter_intelligence.csv"), NEWSLETTER_FIELDS),
            "Intelligence Topics": (intelligence_topics, INTELLIGENCE_TOPIC_FIELDS),
            "AI Memory": (ai_memory, AI_MEMORY_FIELDS),
            "Auto Priority": (auto_priority, AUTO_PRIORITY_FIELDS),
            "Executive Summary": (
                [
                    {"metric": "Today's winners", "value": len([row for row in auto_priority if row.get("daily_priority") == "P1 Today"])},
                    {"metric": "This week candidates", "value": len([row for row in auto_priority if row.get("daily_priority") == "P2 This Week"])},
                    {"metric": "Intelligence source topics", "value": len(intelligence_topics)},
                    {"metric": "Tracked memory rows", "value": len(ai_memory)},
                ],
                ["metric", "value"],
            ),
        }
    )


def write_collector_output(kind: str, input_path: Path | None = None, rss_path: Path | None = None, country: str = "US") -> list[dict[str, Any]]:
    if kind == "google_trends":
        rows = normalize_google_trends(read_any_input(input_path), country=country)
        write_dual_outputs(DATA_DIR / "google_trends.csv", DATA_DIR / "google_trends.json", rows, GOOGLE_TRENDS_FIELDS)
        return rows
    if kind == "google_news":
        raw = parse_google_news_rss(rss_path) if rss_path else read_any_input(input_path)
        rows = normalize_google_news(raw)
        write_dual_outputs(DATA_DIR / "google_news.csv", DATA_DIR / "google_news.json", rows, GOOGLE_NEWS_FIELDS)
        return rows
    if kind == "youtube":
        rows = normalize_youtube_trends(read_any_input(input_path))
        write_dual_outputs(DATA_DIR / "youtube_trends.csv", DATA_DIR / "youtube_trends.json", rows, YOUTUBE_TRENDS_FIELDS)
        return rows
    if kind == "reddit":
        rows = normalize_reddit(read_any_input(input_path))
        write_dual_outputs(DATA_DIR / "reddit_intelligence.csv", DATA_DIR / "reddit_intelligence.json", rows, REDDIT_FIELDS)
        return rows
    if kind == "producthunt":
        rows = normalize_producthunt(read_any_input(input_path))
        write_dual_outputs(DATA_DIR / "producthunt_dashboard.csv", DATA_DIR / "producthunt_dashboard.json", rows, PRODUCTHUNT_FIELDS)
        return rows
    if kind == "x":
        rows = normalize_simple_entity_rows(read_any_input(input_path), X_TRENDS_FIELDS, "x_manual")
        write_dual_outputs(DATA_DIR / "x_trends.csv", DATA_DIR / "x_trends.json", rows, X_TRENDS_FIELDS)
        return rows
    if kind == "linkedin":
        rows = normalize_simple_entity_rows(read_any_input(input_path), LINKEDIN_FIELDS, "linkedin_manual")
        write_dual_outputs(DATA_DIR / "linkedin_trends.csv", DATA_DIR / "linkedin_trends.json", rows, LINKEDIN_FIELDS)
        return rows
    if kind == "newsletter":
        rows = normalize_simple_entity_rows(read_any_input(input_path), NEWSLETTER_FIELDS, "newsletter_manual")
        write_dual_outputs(DATA_DIR / "newsletter_intelligence.csv", DATA_DIR / "newsletter_intelligence.json", rows, NEWSLETTER_FIELDS)
        return rows
    raise ValueError(f"Unknown collector kind: {kind}")
