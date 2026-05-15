from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent
load_dotenv()


@dataclass(frozen=True)
class Settings:
    app_name: str = "AI Affiliate Intelligence Platform"
    base_dir: Path = BASE_DIR
    data_dir: Path = BASE_DIR / "data"
    logs_dir: Path = BASE_DIR / "logs"
    modules_dir: Path = BASE_DIR / "modules"
    dashboard_dir: Path = BASE_DIR / "dashboard"
    landing_root: Path = BASE_DIR / "landing_pages"
    landing_templates_dir: Path = BASE_DIR / "landing_pages" / "templates"
    landing_output_dir: Path = BASE_DIR / "landing_pages" / "output"
    site_output_dir: Path = BASE_DIR / "site_output"
    offers_file: Path = BASE_DIR / "data" / "offers.csv"
    user_offers_file: Path = BASE_DIR / "data" / "user_offers.csv"
    data_sources_file: Path = BASE_DIR / "data" / "data_sources.csv"
    affiliate_links_file: Path = BASE_DIR / "data" / "affiliate_links.csv"
    content_drafts_file: Path = BASE_DIR / "data" / "content_drafts.csv"
    campaigns_file: Path = BASE_DIR / "data" / "campaign_results.csv"
    keywords_file: Path = BASE_DIR / "data" / "keywords.csv"
    google_ads_file: Path = BASE_DIR / "data" / "ads_google.csv"
    bing_ads_file: Path = BASE_DIR / "data" / "ads_bing.csv"
    roi_report_file: Path = BASE_DIR / "data" / "roi_report.csv"
    offer_scores_file: Path = BASE_DIR / "data" / "offer_scores.csv"
    market_insights_file: Path = BASE_DIR / "data" / "market_insights.csv"
    reports_file: Path = BASE_DIR / "data" / "report_summary.md"
    app_log_file: Path = BASE_DIR / "logs" / "app.log"

    @property
    def base_site_url(self) -> str:
        value = os.getenv("BASE_SITE_URL", "").strip().rstrip("/")
        if not value or "yourdomain.com" in value:
            return ""
        return value

    @property
    def site_name(self) -> str:
        return os.getenv("SITE_NAME", "MS Smile AI Review Hub").strip() or "MS Smile AI Review Hub"

    @property
    def site_owner(self) -> str:
        return os.getenv("SITE_OWNER", "").strip()

    @property
    def contact_email(self) -> str:
        return (os.getenv("SITE_CONTACT_EMAIL") or os.getenv("CONTACT_EMAIL", "tuanpk1977@gmail.com")).strip()

    @property
    def site_domain(self) -> str:
        return os.getenv("SITE_DOMAIN", self.base_site_url).strip().rstrip("/")

    @property
    def google_site_verification(self) -> str:
        return os.getenv("GOOGLE_SITE_VERIFICATION", "").strip()

    @property
    def ga_measurement_id(self) -> str:
        return os.getenv("GA_MEASUREMENT_ID", "").strip()

    @property
    def click_webhook_url(self) -> str:
        value = os.getenv("CLICK_WEBHOOK_URL", "").strip()
        invalid_markers = ["your", "xxxxx", "<web app url>", "link_web_app", "example.com"]
        if not value or any(marker in value.lower() for marker in invalid_markers):
            return ""
        return value


settings = Settings()


def ensure_platform_dirs() -> None:
    for path in [
        settings.data_dir,
        settings.logs_dir,
        settings.landing_templates_dir,
        settings.landing_output_dir,
        settings.site_output_dir,
        settings.dashboard_dir,
        settings.modules_dir,
    ]:
        path.mkdir(parents=True, exist_ok=True)


def setup_logging() -> None:
    load_dotenv()
    ensure_platform_dirs()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        handlers=[
            logging.FileHandler(settings.app_log_file, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )
