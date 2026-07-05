from __future__ import annotations

import html
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from modules.opportunity_forecast import FORECAST_FIELDS, build_forecast, write_opportunity_forecast
from modules.performance_tracking import (
    DATA_DIR,
    INTERNAL_LINK_FIELDS,
    REFRESH_FIELDS,
    build_content_lifecycle,
    build_revenue_dashboard,
    load_json_rows,
    numeric,
    read_csv,
    recommend_refresh,
    update_master_workbook,
    write_json,
)
from scripts.build_internal_link_plan import FIELDS as INTERNAL_PLAN_FIELDS
from scripts.build_internal_link_plan import build_plan as build_internal_plan
from scripts.competitor_watch import FIELDS as COMPETITOR_WATCH_FIELDS
from scripts.competitor_watch import build_competitor_watch
from scripts.keyword_gap_analysis import FIELDS as KEYWORD_GAP_FIELDS
from scripts.keyword_gap_analysis import build_keyword_gap


def top(rows: list[dict], field: str, limit: int = 10) -> list[dict]:
    return sorted(rows, key=lambda row: numeric(row.get(field)), reverse=True)[:limit]


def table(rows: list[dict], fields: list[str]) -> str:
    header = "".join(f"<th>{html.escape(field.replace('_', ' ').title())}</th>" for field in fields)
    body = []
    for row in rows:
        body.append("<tr>" + "".join(f"<td>{html.escape(str(row.get(field, '')))}</td>" for field in fields) + "</tr>")
    return f"<table><thead><tr>{header}</tr></thead><tbody>{''.join(body)}</tbody></table>"


def video_ideas(forecast_rows: list[dict]) -> list[dict]:
    topic_scores = {row.get("slug"): row for row in load_json_rows(DATA_DIR / "topic_scores.json")}
    rows = []
    for row in forecast_rows:
        score = topic_scores.get(row.get("slug"), {})
        video_potential = numeric(score.get("youtube_potential"))
        if video_potential >= 55 or row.get("decision") in {"WRITE NOW", "WRITE THIS WEEK"}:
            rows.append(
                {
                    "slug": row.get("slug", ""),
                    "topic": row.get("topic", ""),
                    "video_priority": score.get("video_priority") or ("Video candidate" if video_potential >= 65 else "Optional video"),
                    "youtube_potential": video_potential,
                    "estimated_revenue": row.get("estimated_revenue", ""),
                }
            )
    return sorted(rows, key=lambda item: (numeric(item.get("youtube_potential")), numeric(item.get("estimated_revenue"))), reverse=True)


def write_ceo_html(path: Path, payload: dict) -> None:
    actions = payload["actions"]
    html_doc = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>AI CEO Dashboard</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 0; background: #f4f7fb; color: #172033; }}
    header {{ background: #063b3f; color: white; padding: 28px 36px; }}
    main {{ padding: 28px 36px; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 16px; }}
    .card {{ background: white; border: 1px solid #d9e2ec; border-radius: 8px; padding: 18px; }}
    .metric {{ font-size: 30px; font-weight: 800; color: #0f766e; }}
    table {{ width: 100%; border-collapse: collapse; background: white; margin: 12px 0 28px; }}
    td, th {{ border: 1px solid #d8e1ea; padding: 8px; text-align: left; vertical-align: top; }}
    th {{ background: #e6fffb; }}
    h2 {{ color: #0f766e; margin-top: 34px; }}
  </style>
</head>
<body>
<header>
  <h1>AI CEO Dashboard</h1>
  <p>Recommendation-only dashboard. No publishing, deployment, YouTube upload, or social posting.</p>
</header>
<main>
  <h2>TODAY'S ACTIONS</h2>
  <div class="grid">
    <div class="card"><strong>★★★★★ WRITE TODAY</strong><div class="metric">{len(actions['write_today'])}</div></div>
    <div class="card"><strong>★★★★★ CREATE VIDEO</strong><div class="metric">{len(actions['create_video'])}</div></div>
    <div class="card"><strong>★★★★★ REFRESH ARTICLES</strong><div class="metric">{len(actions['refresh_articles'])}</div></div>
    <div class="card"><strong>★★★★★ SOCIAL POSTS</strong><div class="metric">{len(actions['social_posts'])}</div></div>
    <div class="card"><strong>★★★★★ COMPETITOR ALERTS</strong><div class="metric">{len(actions['competitor_alerts'])}</div></div>
    <div class="card"><strong>★★★★★ KEYWORD GAPS</strong><div class="metric">{len(actions['keyword_gaps'])}</div></div>
    <div class="card"><strong>★★★★★ REVENUE OPPORTUNITIES</strong><div class="metric">{len(actions['revenue_opportunities'])}</div></div>
    <div class="card"><strong>★★★★★ PAGES TO DELETE</strong><div class="metric">{len(actions['pages_to_delete'])}</div></div>
    <div class="card"><strong>★★★★★ ESTIMATED MONTHLY REVENUE</strong><div class="metric">${payload['totals']['estimated_monthly_revenue']}</div></div>
    <div class="card"><strong>★★★★★ ESTIMATED MONTHLY TRAFFIC</strong><div class="metric">{payload['totals']['estimated_monthly_traffic']}</div></div>
  </div>
  <h2>Write Today</h2>{table(actions['write_today'], ['rank','topic','money_score','decision','estimated_monthly_traffic','estimated_revenue','expected_ranking_speed'])}
  <h2>Create Video</h2>{table(actions['create_video'], ['slug','topic','video_priority','youtube_potential','estimated_revenue'])}
  <h2>Refresh Articles</h2>{table(actions['refresh_articles'], REFRESH_FIELDS)}
  <h2>Keyword Gaps</h2>{table(actions['keyword_gaps'], KEYWORD_GAP_FIELDS)}
  <h2>Competitor Alerts</h2>{table(actions['competitor_alerts'], COMPETITOR_WATCH_FIELDS)}
  <h2>Revenue Opportunities</h2>{table(actions['revenue_opportunities'], ['slug','article_url','topic','revenue_estimate','revenue_opportunity'])}
  <h2>Pages To Delete / Avoid</h2>{table(actions['pages_to_delete'], ['rank','topic','money_score','decision','reason'])}
</main>
</body>
</html>"""
    path.write_text(html_doc, encoding="utf-8")


def main() -> int:
    forecast = write_opportunity_forecast()
    lifecycle = build_content_lifecycle()
    refresh = recommend_refresh(lifecycle)
    revenue = build_revenue_dashboard(lifecycle)
    competitor_targets = read_csv(DATA_DIR / "competitor_targets.csv")
    competitor_watch = build_competitor_watch(competitor_targets)
    keyword_gap = build_keyword_gap(competitor_targets)
    internal_plan = build_internal_plan()
    videos = video_ideas(forecast.rows)

    actions = {
        "write_today": [row for row in forecast.rows if row.get("decision") in {"WRITE NOW", "WRITE THIS WEEK"}][:10],
        "create_video": videos[:10],
        "refresh_articles": refresh[:10],
        "social_posts": [row for row in forecast.rows if numeric(row.get("money_score")) >= 65][:10],
        "competitor_alerts": competitor_watch[:10],
        "keyword_gaps": keyword_gap[:10],
        "revenue_opportunities": revenue[:10],
        "pages_to_delete": [row for row in forecast.rows if row.get("decision") == "DELETE"][:10],
    }
    payload = {
        "totals": {
            "estimated_monthly_revenue": forecast.totals["estimated_revenue"],
            "estimated_monthly_traffic": int(forecast.totals["estimated_monthly_traffic"]),
        },
        "actions": actions,
    }
    write_json(DATA_DIR / "daily_ceo_dashboard.json", payload)
    write_ceo_html(DATA_DIR / "daily_ceo_dashboard.html", payload)
    update_master_workbook(
        {
            "Today's Winners": (actions["write_today"], FORECAST_FIELDS),
            "Money Score": (forecast.rows, FORECAST_FIELDS),
            "Revenue Forecast": (top(forecast.rows, "estimated_revenue"), FORECAST_FIELDS),
            "Traffic Forecast": (top(forecast.rows, "estimated_monthly_traffic"), FORECAST_FIELDS),
            "Competitor Watch": (competitor_watch, COMPETITOR_WATCH_FIELDS),
            "Keyword Gap": (keyword_gap, KEYWORD_GAP_FIELDS),
            "Video Ideas": (videos, ["slug", "topic", "video_priority", "youtube_potential", "estimated_revenue"]),
            "Refresh Queue": (refresh, REFRESH_FIELDS),
            "Delete Queue": (actions["pages_to_delete"], FORECAST_FIELDS),
            "Internal Links": (internal_plan, INTERNAL_PLAN_FIELDS),
            "Executive Summary": (
                [
                    {"metric": "Estimated monthly revenue", "value": forecast.totals["estimated_revenue"]},
                    {"metric": "Estimated monthly traffic", "value": int(forecast.totals["estimated_monthly_traffic"])},
                    {"metric": "Write today", "value": len(actions["write_today"])},
                    {"metric": "Video ideas", "value": len(actions["create_video"])},
                    {"metric": "Refresh queue", "value": len(actions["refresh_articles"])},
                    {"metric": "Keyword gaps", "value": len(actions["keyword_gaps"])},
                ],
                ["metric", "value"],
            ),
        }
    )
    print(f"CEO dashboard: {DATA_DIR / 'daily_ceo_dashboard.html'}")
    print(f"Estimated monthly traffic: {int(forecast.totals['estimated_monthly_traffic'])}")
    print(f"Estimated monthly revenue: {forecast.totals['estimated_revenue']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
