from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

import pandas as pd

from config import settings


GSC_IMPORT_COLUMNS = [
    "date",
    "page",
    "query",
    "clicks",
    "impressions",
    "ctr",
    "position",
    "country",
    "device",
]

GSC_PAGE_COLUMNS = [
    "page",
    "clicks",
    "impressions",
    "average_ctr",
    "average_position",
    "top_queries",
]

GSC_QUERY_COLUMNS = [
    "query",
    "page",
    "clicks",
    "impressions",
    "average_ctr",
    "average_position",
    "country",
    "device",
]

TRAFFIC_COLUMNS = [
    "page",
    "title_or_slug",
    "impressions",
    "clicks",
    "ctr",
    "avg_position",
    "cta_clicks",
    "go_clicks",
    "internal_links_count",
    "priority_score",
    "recommended_action",
]

GO_CLICK_COLUMNS = [
    "slug",
    "destination_url",
    "source_page",
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "clicks",
    "last_click_at",
    "status",
]

PRIORITY_PAGES = [
    "/",
    "/cursor/",
    "/windsurf-review/",
    "/comparisons/cursor-vs-windsurf/",
    "/comparisons/copilot-vs-cursor/",
    "/best-ai-coding-tools-2026/",
    "/blog/chatgpt-windsurf-codex-workflow/",
    "/free-ai-coding-workflow-checklist/",
    "/about/",
    "/category/ai-coding-tools/",
]


def run_performance_intelligence() -> dict[str, int]:
    """Generate local-safe GSC, traffic, and /go/ click intelligence reports."""
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    ensure_gsc_template()
    imported = load_gsc_import()
    page_report = build_gsc_page_report(imported)
    query_report = build_gsc_query_report(imported)
    go_report = build_go_click_performance_report()
    traffic_report = build_traffic_performance_report(page_report, go_report)
    write_tracking_status_report()
    page_report.to_csv(settings.data_dir / "gsc_page_performance_report.csv", index=False, encoding="utf-8-sig")
    query_report.to_csv(settings.data_dir / "gsc_query_performance_report.csv", index=False, encoding="utf-8-sig")
    go_report.to_csv(settings.data_dir / "go_click_performance_report.csv", index=False, encoding="utf-8-sig")
    traffic_report.to_csv(settings.data_dir / "traffic_performance_report.csv", index=False, encoding="utf-8-sig")
    return {
        "gsc_import_rows": len(imported),
        "gsc_pages": len(page_report),
        "gsc_queries": len(query_report),
        "go_click_rows": len(go_report),
        "traffic_rows": len(traffic_report),
    }


def ensure_gsc_template() -> Path:
    path = settings.data_dir / "gsc_performance_import_template.csv"
    if not path.exists():
        pd.DataFrame(columns=GSC_IMPORT_COLUMNS).to_csv(path, index=False, encoding="utf-8-sig")
    return path


def load_gsc_import() -> pd.DataFrame:
    path = settings.data_dir / "gsc_performance_import.csv"
    if not path.exists():
        ensure_gsc_template()
        return pd.DataFrame(columns=GSC_IMPORT_COLUMNS)
    try:
        df = pd.read_csv(path, encoding="utf-8-sig").fillna("")
    except UnicodeDecodeError:
        df = pd.read_csv(path, encoding="utf-8").fillna("")
    except Exception:
        return pd.DataFrame(columns=GSC_IMPORT_COLUMNS)
    df = normalize_gsc_columns(df)
    df["page"] = df["page"].apply(normalize_page_path)
    for column in ["clicks", "impressions", "ctr", "position"]:
        df[column] = pd.to_numeric(df[column].astype(str).str.replace("%", "", regex=False), errors="coerce").fillna(0)
    percent_like = df["ctr"].max() > 1 if not df.empty else False
    if percent_like:
        df["ctr"] = df["ctr"] / 100
    return df[GSC_IMPORT_COLUMNS]


def normalize_gsc_columns(df: pd.DataFrame) -> pd.DataFrame:
    aliases = {
        "url": "page",
        "page_url": "page",
        "queries": "query",
        "keyword": "query",
        "avg_position": "position",
        "average_position": "position",
    }
    renamed = {}
    for column in df.columns:
        clean = str(column).strip().lower().replace(" ", "_")
        renamed[column] = aliases.get(clean, clean)
    df = df.rename(columns=renamed)
    for column in GSC_IMPORT_COLUMNS:
        if column not in df.columns:
            df[column] = ""
    return df


def build_gsc_page_report(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=GSC_PAGE_COLUMNS)
    rows = []
    for page, group in df.groupby("page", dropna=False):
        clicks = int(group["clicks"].sum())
        impressions = int(group["impressions"].sum())
        top_queries = (
            group.groupby("query")["clicks"]
            .sum()
            .sort_values(ascending=False)
            .head(5)
            .index.astype(str)
            .tolist()
        )
        rows.append(
            {
                "page": page,
                "clicks": clicks,
                "impressions": impressions,
                "average_ctr": weighted_ctr(group),
                "average_position": weighted_position(group),
                "top_queries": " | ".join(query for query in top_queries if query),
            }
        )
    return pd.DataFrame(rows, columns=GSC_PAGE_COLUMNS).sort_values(["clicks", "impressions"], ascending=False)


def build_gsc_query_report(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=GSC_QUERY_COLUMNS)
    rows = []
    keys = ["query", "page", "country", "device"]
    for values, group in df.groupby(keys, dropna=False):
        query, page, country, device = values
        rows.append(
            {
                "query": query,
                "page": page,
                "clicks": int(group["clicks"].sum()),
                "impressions": int(group["impressions"].sum()),
                "average_ctr": weighted_ctr(group),
                "average_position": weighted_position(group),
                "country": country,
                "device": device,
            }
        )
    return pd.DataFrame(rows, columns=GSC_QUERY_COLUMNS).sort_values(["clicks", "impressions"], ascending=False)


def build_traffic_performance_report(gsc_pages: pd.DataFrame | None = None, go_report: pd.DataFrame | None = None) -> pd.DataFrame:
    seo = read_csv(settings.data_dir / "seo_tracking_page_report.csv")
    actions = read_csv(settings.data_dir / "action_priority_report.csv")
    if gsc_pages is None:
        gsc_pages = read_csv(settings.data_dir / "gsc_page_performance_report.csv")
    if go_report is None:
        go_report = read_csv(settings.data_dir / "go_click_performance_report.csv")

    pages = set(PRIORITY_PAGES)
    if not seo.empty and "page_url" in seo.columns:
        pages.update(seo["page_url"].astype(str).apply(normalize_page_path).tolist())
    if not gsc_pages.empty and "page" in gsc_pages.columns:
        pages.update(gsc_pages["page"].astype(str).apply(normalize_page_path).tolist())
    pages = {page for page in pages if page and page.startswith("/")}

    rows = []
    for page in sorted(pages, key=priority_sort_key):
        gsc_row = first_row(gsc_pages, "page", page)
        seo_row = first_row(seo, "page_url", page)
        impressions = int(float(gsc_row.get("impressions", 0) or 0))
        clicks = int(float(gsc_row.get("clicks", 0) or 0))
        ctr = float(gsc_row.get("average_ctr", 0) or 0)
        avg_position = float(gsc_row.get("average_position", 0) or 0)
        internal_links = int(float(seo_row.get("internal_links_count", 0) or 0))
        cta_clicks = clicks_for_page(go_report, page)
        score, action = score_page(page, impressions, clicks, ctr, avg_position, cta_clicks, internal_links, actions)
        rows.append(
            {
                "page": page,
                "title_or_slug": seo_row.get("title", "") or page.strip("/") or "home",
                "impressions": impressions,
                "clicks": clicks,
                "ctr": round(ctr, 4),
                "avg_position": round(avg_position, 2),
                "cta_clicks": cta_clicks,
                "go_clicks": cta_clicks,
                "internal_links_count": internal_links,
                "priority_score": score,
                "recommended_action": action,
            }
        )
    return pd.DataFrame(rows, columns=TRAFFIC_COLUMNS).sort_values("priority_score", ascending=False)


def build_go_click_performance_report() -> pd.DataFrame:
    events = read_csv(settings.data_dir / "click_events.csv")
    redirect_map = read_csv(settings.data_dir / "redirect_map.csv")
    rows = []
    if events.empty:
        base_rows = redirect_map.head(100) if not redirect_map.empty else pd.DataFrame()
        for _, row in base_rows.iterrows():
            rows.append(
                {
                    "slug": str(row.get("tracking_id") or row.get("redirect_path") or "").strip("/").split("/")[-1],
                    "destination_url": row.get("tracked_url", "") or row.get("target_url", ""),
                    "source_page": "",
                    "utm_source": row.get("source", ""),
                    "utm_medium": row.get("medium", ""),
                    "utm_campaign": row.get("campaign", ""),
                    "clicks": 0,
                    "last_click_at": "",
                    "status": "no_click_data_yet",
                }
            )
        return pd.DataFrame(rows, columns=GO_CLICK_COLUMNS)

    for column in ["tool_slug", "slug", "target_url", "source_page", "timestamp"]:
        if column not in events.columns:
            events[column] = ""
    events["_slug"] = events["tool_slug"].astype(str).where(events["tool_slug"].astype(str).str.len() > 0, events["slug"].astype(str))
    for (slug, source_page), group in events.groupby(["_slug", "source_page"], dropna=False):
        target_url = str(group["target_url"].dropna().astype(str).replace("", pd.NA).dropna().tail(1).squeeze() if not group.empty else "")
        query = parse_query_fields(target_url)
        rows.append(
            {
                "slug": slug,
                "destination_url": target_url,
                "source_page": source_page,
                "utm_source": query.get("utm_source", ""),
                "utm_medium": query.get("utm_medium", ""),
                "utm_campaign": query.get("utm_campaign", ""),
                "clicks": len(group),
                "last_click_at": str(group["timestamp"].astype(str).max()),
                "status": "has_click_data",
            }
        )
    return pd.DataFrame(rows, columns=GO_CLICK_COLUMNS).sort_values("clicks", ascending=False)


def weighted_ctr(group: pd.DataFrame) -> float:
    impressions = group["impressions"].sum()
    if impressions <= 0:
        return 0.0
    return round(float(group["clicks"].sum() / impressions), 4)


def weighted_position(group: pd.DataFrame) -> float:
    impressions = group["impressions"].sum()
    if impressions <= 0:
        return round(float(group["position"].mean() or 0), 2)
    return round(float((group["position"] * group["impressions"]).sum() / impressions), 2)


def normalize_page_path(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    parsed = urlparse(text)
    path = parsed.path if parsed.scheme or parsed.netloc else text
    if not path.startswith("/"):
        path = "/" + path
    if not path.endswith("/") and "." not in path.split("/")[-1]:
        path += "/"
    return path


def read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path, encoding="utf-8-sig").fillna("")
    except Exception:
        try:
            return pd.read_csv(path, encoding="utf-8").fillna("")
        except Exception:
            return pd.DataFrame()


def first_row(df: pd.DataFrame, column: str, value: str) -> dict:
    if df.empty or column not in df.columns:
        return {}
    normalized = df[column].astype(str).apply(normalize_page_path)
    hit = df[normalized == value]
    if hit.empty:
        return {}
    return hit.iloc[0].to_dict()


def clicks_for_page(go_report: pd.DataFrame, page: str) -> int:
    if go_report.empty or "source_page" not in go_report.columns or "clicks" not in go_report.columns:
        return 0
    normalized = go_report["source_page"].astype(str).apply(normalize_page_path)
    return int(pd.to_numeric(go_report.loc[normalized == page, "clicks"], errors="coerce").fillna(0).sum())


def score_page(
    page: str,
    impressions: int,
    clicks: int,
    ctr: float,
    avg_position: float,
    cta_clicks: int,
    internal_links: int,
    actions: pd.DataFrame,
) -> tuple[int, str]:
    if impressions <= 0 and clicks <= 0:
        base = 40 if page in PRIORITY_PAGES else 10
        return base, "no_data_yet" if page in PRIORITY_PAGES else "monitor"
    score = min(45, impressions // 20) + min(25, clicks * 3)
    if impressions >= 50 and ctr < 0.02:
        return min(100, score + 35), "improve_title_meta"
    if clicks > 0 and cta_clicks == 0:
        return min(100, score + 25), "strengthen_first_screen_cta"
    if internal_links < 5:
        return min(100, score + 15), "add_internal_links"
    if 8 <= avg_position <= 25 and impressions >= 20:
        return min(100, score + 20), "refresh_content"
    if clicks > 0:
        return min(100, score + 10), "promote_on_social"
    return min(100, score), "monitor"


def priority_sort_key(page: str) -> tuple[int, str]:
    return (PRIORITY_PAGES.index(page) if page in PRIORITY_PAGES else 999, page)


def parse_query_fields(url: str) -> dict[str, str]:
    from urllib.parse import parse_qs

    parsed = urlparse(str(url or ""))
    values = parse_qs(parsed.query)
    return {key: values.get(key, [""])[0] for key in ["utm_source", "utm_medium", "utm_campaign"]}


def write_tracking_status_report() -> Path:
    path = settings.data_dir / "tracking_status_report.md"
    webhook_status = "configured" if settings.click_webhook_url else "not_configured"
    text = f"""# Tracking Status Report

## Current status

- Static `/go/` redirect pages: enabled.
- Local CSV click event format: `data/click_events.csv`.
- GSC performance import: manual CSV only.
- GA4: optional, controlled by `config/tracking.json`.
- Webhook persistence: {webhook_status}.

## What works locally/static

- Pages can route outbound CTAs through `/go/<slug>/`.
- UTM tracking URLs can be generated and reported locally.
- Manual GSC exports can be imported from `data/gsc_performance_import.csv`.
- Reports are generated into `data/gsc_page_performance_report.csv`, `data/gsc_query_performance_report.csv`, `data/go_click_performance_report.csv`, and `data/traffic_performance_report.csv`.

## What production persistence needs

GitHub Pages is static and cannot write click events directly to `data/click_events.csv`.
For persistent production click storage, configure a webhook or serverless receiver and keep redirects working even if collection fails.

## Safety rules

- Do not store IP, email, cookies, or personal identifiers in click logs.
- Do not invent traffic, clicks, conversions, or affiliate links.
- Leave webhook and GA4 IDs empty until real accounts are configured.
"""
    path.write_text(text, encoding="utf-8")
    return path
