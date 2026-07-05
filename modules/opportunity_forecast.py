from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from modules.performance_tracking import (
    BASE_URL,
    DATA_DIR,
    build_content_lifecycle,
    load_json_rows,
    numeric,
    read_csv,
    slugify,
    write_csv,
    write_json,
)


FORECAST_FIELDS = [
    "rank",
    "topic",
    "slug",
    "article_url",
    "money_score",
    "decision",
    "estimated_monthly_traffic",
    "estimated_affiliate_clicks",
    "estimated_revenue",
    "estimated_difficulty",
    "expected_ranking_speed",
    "confidence_score",
    "buyer_intent",
    "affiliate_program_quality",
    "estimated_cpc",
    "commercial_intent",
    "seo_potential",
    "trend_stability",
    "evergreen_value",
    "reason",
]


@dataclass(frozen=True)
class OpportunityForecast:
    rows: list[dict[str, Any]]
    totals: dict[str, Any]


def inverse(value: Any) -> float:
    return max(0.0, min(100.0, 100.0 - numeric(value)))


def topic_slug(row: dict[str, Any]) -> str:
    return slugify(row.get("slug") or row.get("topic") or "")


def commercial_intent(row: dict[str, Any]) -> float:
    topic = str(row.get("topic") or "").lower()
    text_bonus = 0
    for term in ("review", "pricing", "alternative", "alternatives", " vs ", "best", "comparison", "discount", "coupon"):
        if term in topic:
            text_bonus += 8
    return min(100.0, numeric(row.get("search_intent")) * 0.65 + numeric(row.get("buyer_intent")) * 0.25 + text_bonus)


def trend_stability(row: dict[str, Any]) -> float:
    return round(numeric(row.get("evergreen_potential")) * 0.65 + numeric(row.get("trend_score")) * 0.35, 1)


def money_score(row: dict[str, Any]) -> float:
    return round(
        numeric(row.get("buyer_intent")) * 0.22
        + numeric(row.get("affiliate_value") or row.get("revenue_score")) * 0.18
        + numeric(row.get("cpc_potential")) * 0.13
        + commercial_intent(row) * 0.14
        + inverse(row.get("competition_level") or row.get("competition")) * 0.10
        + numeric(row.get("seo_opportunity") or row.get("seo_score")) * 0.11
        + trend_stability(row) * 0.07
        + numeric(row.get("evergreen_potential")) * 0.05,
        1,
    )


def estimated_monthly_traffic(row: dict[str, Any]) -> int:
    traffic = numeric(row.get("estimated_traffic") or row.get("traffic_score"))
    seo = numeric(row.get("seo_opportunity") or row.get("seo_score"))
    competition = numeric(row.get("competition_level") or row.get("competition"))
    base = 25 + traffic * 18 + seo * 8
    difficulty_discount = max(0.35, 1 - competition / 180)
    return max(0, int(round(base * difficulty_discount)))


def estimated_affiliate_clicks(row: dict[str, Any], monthly_traffic: int) -> float:
    buyer = numeric(row.get("buyer_intent"))
    commercial = commercial_intent(row)
    click_rate = 0.008 + (buyer + commercial) / 10000
    return round(monthly_traffic * click_rate, 1)


def estimated_revenue(row: dict[str, Any], affiliate_clicks: float) -> float:
    cpc = numeric(row.get("cpc_potential"))
    affiliate = numeric(row.get("affiliate_value") or row.get("revenue_score"))
    estimated_epc = 0.8 + cpc / 35 + affiliate / 30
    return round(affiliate_clicks * estimated_epc, 2)


def ranking_speed(row: dict[str, Any]) -> str:
    difficulty = numeric(row.get("competition_level") or row.get("competition"))
    seo = numeric(row.get("seo_opportunity") or row.get("seo_score"))
    if difficulty <= 45 and seo >= 60:
        return "Fast"
    if difficulty <= 65 and seo >= 45:
        return "Medium"
    return "Slow"


def confidence(row: dict[str, Any]) -> float:
    fields = [
        "buyer_intent",
        "affiliate_value",
        "cpc_potential",
        "seo_opportunity",
        "competition_level",
        "estimated_traffic",
        "evergreen_potential",
        "trend_score",
    ]
    available = sum(1 for field in fields if str(row.get(field, "")).strip() not in {"", "0", "0.0", "None"})
    source_bonus = 10 if row.get("source") else 0
    return round(min(100, available / len(fields) * 85 + source_bonus), 1)


def decision_for(row: dict[str, Any], score: float, lifecycle_by_slug: dict[str, dict[str, Any]]) -> str:
    slug = topic_slug(row)
    lifecycle = lifecycle_by_slug.get(slug, {})
    if numeric(lifecycle.get("refresh_score")) >= 60:
        return "REFRESH"
    if score >= 78:
        return "WRITE NOW"
    if score >= 62:
        return "WRITE THIS WEEK"
    if score >= 45:
        return "WATCH"
    return "DELETE"


def build_forecast_rows(topic_rows: list[dict[str, Any]] | None = None, lifecycle_rows: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    topics = topic_rows if topic_rows is not None else load_json_rows(DATA_DIR / "topic_scores.json")
    lifecycle = lifecycle_rows if lifecycle_rows is not None else build_content_lifecycle()
    lifecycle_by_slug = {row.get("slug", ""): row for row in lifecycle}
    rows: list[dict[str, Any]] = []
    for source in topics:
        slug = topic_slug(source)
        traffic = estimated_monthly_traffic(source)
        affiliate_clicks = estimated_affiliate_clicks(source, traffic)
        revenue = estimated_revenue(source, affiliate_clicks)
        score = money_score(source)
        rows.append(
            {
                "topic": source.get("topic", ""),
                "slug": slug,
                "article_url": source.get("article_url") or lifecycle_by_slug.get(slug, {}).get("article_url") or f"{BASE_URL}/{slug}/",
                "money_score": score,
                "decision": decision_for(source, score, lifecycle_by_slug),
                "estimated_monthly_traffic": traffic,
                "estimated_affiliate_clicks": affiliate_clicks,
                "estimated_revenue": revenue,
                "estimated_difficulty": numeric(source.get("difficulty") or source.get("competition_level") or source.get("competition")),
                "expected_ranking_speed": ranking_speed(source),
                "confidence_score": confidence(source),
                "buyer_intent": numeric(source.get("buyer_intent")),
                "affiliate_program_quality": numeric(source.get("affiliate_value") or source.get("revenue_score")),
                "estimated_cpc": numeric(source.get("cpc_potential")),
                "commercial_intent": commercial_intent(source),
                "seo_potential": numeric(source.get("seo_opportunity") or source.get("seo_score")),
                "trend_stability": trend_stability(source),
                "evergreen_value": numeric(source.get("evergreen_potential")),
                "reason": source.get("reason", ""),
            }
        )
    rows.sort(key=lambda row: (numeric(row.get("money_score")), numeric(row.get("estimated_revenue"))), reverse=True)
    for index, row in enumerate(rows, 1):
        row["rank"] = index
    return rows


def build_forecast(topic_rows: list[dict[str, Any]] | None = None, lifecycle_rows: list[dict[str, Any]] | None = None) -> OpportunityForecast:
    rows = build_forecast_rows(topic_rows=topic_rows, lifecycle_rows=lifecycle_rows)
    totals = {
        "topics": len(rows),
        "estimated_monthly_traffic": sum(numeric(row.get("estimated_monthly_traffic")) for row in rows),
        "estimated_affiliate_clicks": round(sum(numeric(row.get("estimated_affiliate_clicks")) for row in rows), 1),
        "estimated_revenue": round(sum(numeric(row.get("estimated_revenue")) for row in rows), 2),
        "write_now": sum(1 for row in rows if row.get("decision") == "WRITE NOW"),
        "write_this_week": sum(1 for row in rows if row.get("decision") == "WRITE THIS WEEK"),
        "watch": sum(1 for row in rows if row.get("decision") == "WATCH"),
        "refresh": sum(1 for row in rows if row.get("decision") == "REFRESH"),
        "delete": sum(1 for row in rows if row.get("decision") == "DELETE"),
    }
    return OpportunityForecast(rows=rows, totals=totals)


def write_opportunity_forecast(
    csv_path: Path = DATA_DIR / "opportunity_forecast.csv",
    json_path: Path = DATA_DIR / "opportunity_forecast.json",
) -> OpportunityForecast:
    forecast = build_forecast()
    write_csv(csv_path, forecast.rows, FORECAST_FIELDS)
    write_json(json_path, {"totals": forecast.totals, "rows": forecast.rows})
    return forecast
