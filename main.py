from __future__ import annotations

import logging
import os

import pandas as pd
from dotenv import load_dotenv

from config import ensure_platform_dirs, settings, setup_logging
from modules.ads_generator import generate_ads, validate_ads_csv
from modules.action_priority import run_action_priority_report
from modules.affiliate_tracking import run_affiliate_tracking_engine
from modules.affiliate_links import ensure_affiliate_links
from modules.ai_angle_generator import generate_angles
from modules.audience_growth import run_audience_growth_system
from modules.bilingual_site import add_bilingual_pages
from modules.compliance_checker import build_compliance_report
from modules.community_discovery import run_community_discovery
from modules.content_approval import ensure_content_drafts
from modules.competitor_ads_spy import analyze_competitor_ads
from modules.csv_exporter import export_csv
from modules.data_sources import attach_data_confidence, load_data_sources
from modules.decision_engine import decide_campaigns, decide_offers
from modules.facebook_meta import post_process_facebook_meta
from modules.geo_analyzer import suggest_geos
from modules.gsc_performance import run_performance_intelligence
from modules.keyword_analyzer import generate_keywords
from modules.keyword_intelligence import run_keyword_intelligence, run_keyword_intelligence_report
from modules.landing_page_generator import generate_landing_pages
from modules.internal_linker import post_process_internal_links
from modules.market_analyzer import analyze_market
from modules.markdown_publisher import publish_markdown_articles
from modules.offer_loader import load_offers
from modules.offer_scorer import score_offers
from modules.profit_simulator import simulate_all
from modules.post_deploy_kit import run_post_deploy_kit
from modules.report_generator import generate_report
from modules.review_workflow import run_review_workflow_audit
from modules.roi_tracker import build_roi_report
from modules.site_builder import build_site_output
from modules.sitemap_generator import generate_sitemap
from modules.seo_system import run_seo_system
from modules.trust_localization_upgrade import enhance_site
from modules.social_content_generator import ensure_report as ensure_social_post_report
from modules.social_content_generator import write_distribution_summary
from modules.social_distribution import ensure_social_distribution_assets
from modules.social_seo_exporter import generate_social_seo_assets
from modules.social_publish_queue import ensure_queue as ensure_social_publish_queue
from modules.social_publisher import ensure_social_publisher_assets
from modules.scheduler_runner import start_background_scheduler


LOGGER = logging.getLogger(__name__)
load_dotenv()


def env_enabled(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def main() -> None:
    setup_logging()
    ensure_platform_dirs()
    LOGGER.info("Starting %s", settings.app_name)

    offers = load_offers()
    if offers.empty:
        LOGGER.warning("No offers found. Stop pipeline.")
        return
    ensure_affiliate_links(offers)
    ensure_content_drafts()
    ensure_social_post_report()
    ensure_social_distribution_assets()
    run_community_discovery()
    social_queue = ensure_social_publish_queue()
    ensure_social_publisher_assets()
    if env_enabled("AUTO_SOCIAL_POST", False) and start_background_scheduler(interval_seconds=30):
        LOGGER.info("Telegram auto-post scheduler started")
    else:
        LOGGER.info("Automatic social posting disabled; social content remains draft/manual only")

    data_sources = load_data_sources(offers)
    market = analyze_market(offers)
    compliance = build_compliance_report(offers)
    offer_scores = score_offers(offers, market, compliance)
    offer_scores = enrich_with_geo(offer_scores, market)
    offer_scores = attach_data_confidence(offer_scores, data_sources)

    keywords = generate_keywords(offer_scores)
    keyword_opportunities, keyword_summary = run_keyword_intelligence(keywords)
    angles = {
        str(row.get("offer_id", "")): generate_angles(str(row.get("brand_name", "")), str(row.get("niche", "")))
        for _, row in offer_scores.iterrows()
    }
    competitor = build_competitor_insights(keywords, offer_scores)
    simulations = simulate_all(offer_scores)

    landing_index = generate_landing_pages(offer_scores, angles)
    build_site_output(landing_index, settings.base_site_url, offer_scores)
    publish_markdown_articles()
    post_process_internal_links(settings.site_output_dir)
    generate_sitemap(settings.site_output_dir, settings.base_site_url or settings.site_domain)
    google_ads, bing_ads = generate_ads(offer_scores, keywords, landing_index)
    validate_ads_csv(google_ads, "Google Ads")
    validate_ads_csv(bing_ads, "Bing/Microsoft Ads")
    roi_report = build_roi_report()
    roi_decisions = decide_campaigns(roi_report)
    offer_decisions = decide_offers(offer_scores)
    offer_scores = offer_scores.merge(offer_decisions, on=["offer_id", "brand_name"], how="left")

    export_csv(offer_scores, settings.offer_scores_file)
    export_csv(data_sources, settings.data_sources_file)
    export_csv(market, settings.market_insights_file)
    export_csv(keywords, settings.keywords_file)
    export_csv(keyword_opportunities, settings.data_dir / "keyword_opportunities.csv")
    export_csv(keyword_summary, settings.data_dir / "keyword_intelligence_summary.csv")
    export_csv(google_ads, settings.google_ads_file)
    export_csv(bing_ads, settings.bing_ads_file)
    export_csv(roi_decisions, settings.roi_report_file)
    export_csv(competitor, settings.data_dir / "competitor_ads_insights.csv")
    export_csv(pd.DataFrame(flatten_angles(angles)), settings.data_dir / "ai_angles.csv")
    export_csv(simulations, settings.data_dir / "profit_simulations.csv")
    export_csv(landing_index, settings.data_dir / "landing_pages_index.csv")

    generate_report(offer_scores, roi_decisions)
    run_review_workflow_audit()
    write_distribution_summary(social_queue)
    run_post_deploy_kit()
    run_seo_system()
    run_affiliate_tracking_engine(settings.site_output_dir)
    run_keyword_intelligence_report()
    run_action_priority_report()
    post_process_internal_links(settings.site_output_dir)
    add_bilingual_pages(settings.site_output_dir, settings.base_site_url or settings.site_domain)
    run_audience_growth_system(settings.site_output_dir)
    enhance_site(settings.site_output_dir)
    post_process_facebook_meta(settings.site_output_dir, settings.base_site_url or settings.site_domain)
    generate_sitemap(settings.site_output_dir, settings.base_site_url or settings.site_domain)
    run_seo_system()
    generate_social_seo_assets()
    run_performance_intelligence()
    print_keyword_summary(keyword_summary)
    LOGGER.info("Pipeline completed. Dashboard data is ready in %s", settings.data_dir)


def enrich_with_geo(offer_scores: pd.DataFrame, market: pd.DataFrame) -> pd.DataFrame:
    cpc_map = market.set_index("niche")["estimated_cpc"].to_dict() if not market.empty else {}
    rows = []
    for _, row in offer_scores.iterrows():
        geo = suggest_geos(str(row.get("competition", "Medium")), float(cpc_map.get(row.get("niche"), 3.0)))
        rows.append({**row.to_dict(), **geo, "estimated_cpc": cpc_map.get(row.get("niche"), 3.0)})
    return pd.DataFrame(rows)


def build_competitor_insights(keywords: pd.DataFrame, offer_scores: pd.DataFrame) -> pd.DataFrame:
    rows = []
    niche_map = offer_scores.set_index("offer_id")["niche"].to_dict() if not offer_scores.empty else {}
    sample = keywords[keywords["keyword_group"] != "negative_keywords"].groupby("offer_id").head(1)
    for _, row in sample.iterrows():
        insight = analyze_competitor_ads(str(row.get("keyword", "")), str(niche_map.get(row.get("offer_id"), "")))
        rows.append({"offer_id": row.get("offer_id", ""), "keyword": row.get("keyword", ""), **insight})
    return pd.DataFrame(rows)


def flatten_angles(angles: dict[str, dict]) -> list[dict]:
    return [{"offer_id": offer_id, **items} for offer_id, items in angles.items()]


def print_keyword_summary(summary: pd.DataFrame) -> None:
    if summary.empty:
        print("Keyword Intelligence Summary: no keyword data")
        return
    row = summary.iloc[0]
    print("Keyword Intelligence Summary")
    print(f"- total_keywords: {row.get('total_keywords', 0)}")
    print(f"- high_opportunity_keywords: {row.get('high_opportunity_keywords', 0)}")
    print(f"- low_competition_keywords: {row.get('low_competition_keywords', 0)}")
    print(f"- top_affiliate_keywords: {row.get('top_affiliate_keywords', '')}")


if __name__ == "__main__":
    main()
