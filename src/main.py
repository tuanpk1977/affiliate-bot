from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from ads_compliance import build_ads_compliance_precheck
from ad_planner import build_ad_outputs
from collector import Collector
from config import settings
from crypto_listing_watcher import CryptoListingWatcher
from discoverer import Discoverer
from parser import (
    is_recurring,
    normalize_commission_type,
    parse_commission_percent,
    parse_commission_text,
    parse_cookie_days,
    parse_cookie_text,
    parse_flat_commission_amount,
    parse_payout_text,
)
from reporter import build_decision_summary, build_top_report, send_telegram_message
from reviewer import build_review_workflow
from landing_page_generator import build_landing_pages
from roi_tracker import build_roi_report
from scorer import score_project
from utils import ensure_dirs, now_str, setup_logging

INPUT_FILE = "data/input/projects_seed.csv"
RAW_OUTPUT = "data/output/projects_raw.csv"
SCORED_OUTPUT = "data/output/projects_scored.csv"
REPORT_FILE = "data/output/top_report.txt"
SUMMARY_FILE = "data/output/decision_summary.txt"


def main() -> None:
    ensure_dirs()
    setup_logging()

    collector = Collector(
        timeout=settings.request_timeout,
        user_agent=settings.user_agent,
    )
    discoverer = Discoverer(
        timeout=settings.request_timeout,
        user_agent=settings.user_agent,
        limit=settings.discovery_limit,
    )

    discovered_df = discoverer.discover()
    seed_df = load_seed_projects()
    df = merge_projects(seed_df, discovered_df)

    if df.empty:
        logging.info("No projects found from seed or discovery sources.")

    raw_rows = []
    scored_rows = []

    for _, row in df.iterrows():
        brand_name = row.get("brand_name", "")
        website = row.get("website", "")
        category = row.get("category", "")
        source = row.get("source", "")
        notes = row.get("notes", "")

        logging.info("Checking %s - %s", brand_name, website)
        collected = collector.collect_project(website)
        affiliate_text = collected.get("affiliate_text", "")

        commission_text = parse_commission_text(affiliate_text)
        commission_percent = parse_commission_percent(affiliate_text)
        flat_commission_amount = parse_flat_commission_amount(affiliate_text)
        cookie_text = parse_cookie_text(affiliate_text)
        cookie_days = parse_cookie_days(affiliate_text)
        recurring = is_recurring(affiliate_text)
        payout_text = parse_payout_text(affiliate_text)
        commission_type = normalize_commission_type(recurring, commission_text)

        raw_record = {
            "brand_name": brand_name,
            "website": website,
            "category": category,
            "source": source,
            "notes": notes,
            **collected,
            "commission_text": commission_text,
            "commission_percent": commission_percent,
            "flat_commission_amount": flat_commission_amount,
            "cookie_text": cookie_text,
            "cookie_days": cookie_days,
            "recurring": recurring,
            "payout_text": payout_text,
            "commission_type": commission_type,
            "checked_at": now_str(),
        }
        raw_rows.append(raw_record)

        scored_record = {
            **raw_record,
            **score_project(raw_record),
        }
        scored_record = {
            **scored_record,
            **build_review_workflow(scored_record),
        }
        scored_record = {
            **scored_record,
            **build_ads_compliance_precheck(
                scored_record,
                timeout=settings.request_timeout,
                user_agent=settings.user_agent,
            ),
        }
        scored_rows.append(scored_record)

    raw_df = pd.DataFrame(raw_rows)
    scored_df = pd.DataFrame(scored_rows)

    safe_to_csv(raw_df, RAW_OUTPUT)
    safe_to_csv(scored_df, SCORED_OUTPUT)

    report = build_top_report(scored_df)
    with open(REPORT_FILE, "w", encoding="utf-8") as file:
        file.write(report)

    summary = build_decision_summary(scored_df)
    with open(SUMMARY_FILE, "w", encoding="utf-8") as file:
        file.write(summary)

    ad_outputs = build_ad_outputs(scored_df)
    build_landing_pages(ad_outputs["plan"])
    build_roi_report()
    CryptoListingWatcher(
        timeout=settings.request_timeout,
        user_agent=settings.user_agent,
        limit=settings.discovery_limit,
    ).run()

    telegram_error = send_telegram_message(
        settings.telegram_bot_token,
        settings.telegram_chat_id,
        summary,
    )
    if telegram_error:
        logging.info("Telegram skipped: %s", telegram_error)

def load_seed_projects() -> pd.DataFrame:
    try:
        return pd.read_csv(INPUT_FILE)
    except FileNotFoundError:
        return pd.DataFrame(columns=["brand_name", "website", "category", "source", "notes"])


def merge_projects(seed_df: pd.DataFrame, discovered_df: pd.DataFrame) -> pd.DataFrame:
    columns = ["brand_name", "website", "category", "source", "notes"]
    frames = []
    for df in [discovered_df, seed_df]:
        if df.empty:
            continue
        frames.append(df.reindex(columns=columns).fillna(""))

    if not frames:
        return pd.DataFrame(columns=columns)

    merged = pd.concat(frames, ignore_index=True)
    merged["website_key"] = merged["website"].astype(str).str.lower().str.rstrip("/")
    merged = merged[merged["website_key"] != ""]
    merged = merged.drop_duplicates(subset=["website_key"])
    return merged.drop(columns=["website_key"])


def safe_to_csv(df: pd.DataFrame, output_path: str) -> str:
    try:
        df.to_csv(output_path, index=False)
        return output_path
    except PermissionError:
        path = Path(output_path)
        fallback = path.with_name(f"{path.stem}_{now_str().replace(':', '-').replace(' ', '_')}{path.suffix}")
        df.to_csv(fallback, index=False)
        logging.warning("Output file locked, wrote fallback CSV: %s", fallback)
        return str(fallback)


if __name__ == "__main__":
    main()
