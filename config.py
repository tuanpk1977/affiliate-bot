from __future__ import annotations

import logging
import os
import json
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent
load_dotenv()


def load_json_config(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


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
        return (os.getenv("SITE_CONTACT_EMAIL") or os.getenv("CONTACT_EMAIL", "contact@smileaireviewhub.com")).strip()

    @property
    def admin_email(self) -> str:
        return os.getenv("SITE_ADMIN_EMAIL", "admin@smileaireviewhub.com").strip()

    @property
    def site_domain(self) -> str:
        return os.getenv("SITE_DOMAIN", self.base_site_url).strip().rstrip("/")

    @property
    def google_site_verification(self) -> str:
        tracking = load_json_config(BASE_DIR / "config" / "tracking.json")
        return (os.getenv("GOOGLE_SITE_VERIFICATION") or tracking.get("GOOGLE_SITE_VERIFICATION", "")).strip()

    @property
    def ga_measurement_id(self) -> str:
        tracking = load_json_config(BASE_DIR / "config" / "tracking.json")
        return (os.getenv("GA4_MEASUREMENT_ID") or os.getenv("GA_MEASUREMENT_ID") or tracking.get("GA4_MEASUREMENT_ID", "")).strip()

    @property
    def enable_tracking(self) -> bool:
        tracking = load_json_config(BASE_DIR / "config" / "tracking.json")
        raw = os.getenv("ENABLE_TRACKING")
        if raw is None:
            raw = tracking.get("ENABLE_TRACKING", False)
        return str(raw).strip().lower() in {"1", "true", "yes", "on"}

    @property
    def click_webhook_url(self) -> str:
        value = os.getenv("CLICK_WEBHOOK_URL", "").strip()
        invalid_markers = ["your", "xxxxx", "<web app url>", "link_web_app", "example.com"]
        if not value or any(marker in value.lower() for marker in invalid_markers):
            return ""
        return value

    @property
    def editorial_config(self) -> dict:
        return load_json_config(BASE_DIR / "config" / "editorial_system.json")

    @property
    def editorial_candidate_limit(self) -> int:
        value = os.getenv("EDITORIAL_CANDIDATE_LIMIT") or self.editorial_config.get("candidate_limit", 200)
        return max(25, min(500, int(value)))

    @property
    def editorial_max_per_source(self) -> int:
        value = os.getenv("EDITORIAL_MAX_PER_SOURCE") or self.editorial_config.get("max_per_source", 40)
        return max(10, min(100, int(value)))

    @property
    def editorial_top_topics(self) -> int:
        value = os.getenv("EDITORIAL_TOP_TOPICS") or self.editorial_config.get("top_topics", 10)
        return max(1, min(50, int(value)))

    @property
    def editorial_calendar_days(self) -> int:
        value = os.getenv("EDITORIAL_CALENDAR_DAYS") or self.editorial_config.get("calendar_days", 7)
        return max(1, min(14, int(value)))

    @property
    def editorial_validation_keywords(self) -> int:
        value = os.getenv("EDITORIAL_VALIDATION_KEYWORDS") or self.editorial_config.get("validation_keywords", 10)
        return max(5, min(30, int(value)))

    @property
    def editorial_business_intelligence_config(self) -> dict:
        return dict(self.editorial_config.get("business_intelligence", {}))


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
