from __future__ import annotations

import pandas as pd

from config import settings

BAD_CLAIMS = ["guaranteed income", "100% success", "best forever"]

REQUIRED_AD_COLUMNS = [
    "Campaign",
    "Ad Group",
    "Keyword",
    "Match Type",
    "Final URL",
    "Headline 1",
    "Headline 2",
    "Headline 3",
    "Description 1",
    "Description 2",
    "Status",
]


def generate_ads(
    offer_scores: pd.DataFrame,
    keywords: pd.DataFrame,
    landing_pages: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    google_rows = []
    bing_rows = []
    landing_map = {}
    if landing_pages is not None and not landing_pages.empty:
        landing_map = landing_pages.set_index("offer_id").to_dict("index")
    for _, offer in offer_scores.iterrows():
        if str(offer.get("compliance_status", "")).upper() == "BLOCKED":
            continue
        offer_keywords = keywords[
            (keywords["offer_id"] == offer.get("offer_id"))
            & (keywords["keyword_group"] != "negative_keywords")
        ].head(6)
        headlines = build_headlines(str(offer.get("brand_name", "")), str(offer.get("niche", "")))
        descriptions = build_descriptions(str(offer.get("brand_name", "")), str(offer.get("niche", "")))
        final_url = choose_final_url(offer, landing_map)
        for _, kw in offer_keywords.iterrows():
            row = {
                "Campaign": f"AIIP - {offer.get('brand_name')}",
                "Ad Group": kw["keyword_group"],
                "Keyword": kw["keyword"],
                "Match Type": kw["match_type"],
                "Final URL": final_url,
                "Headline 1": headlines[0],
                "Headline 2": headlines[1],
                "Headline 3": headlines[2],
                "Description 1": descriptions[0],
                "Description 2": descriptions[1],
                "Sitelinks": "Review | Comparison | Pricing | FAQ",
                "Callouts": "Clear comparison | Affiliate disclosure | Policy checked",
                "CTA Ideas": "Compare options | Read review | Check official site",
                "Status": "Paused - manual review required",
            }
            if to_bool(offer.get("can_generate_google_ads", offer.get("can_generate_ads", True))):
                google_rows.append(row)
            if to_bool(offer.get("can_generate_bing_ads", offer.get("can_generate_ads", True))):
                bing_rows.append({**row, "Campaign": f"AIIP Bing - {offer.get('brand_name')}"})
    return normalize_ads_df(pd.DataFrame(google_rows)), normalize_ads_df(pd.DataFrame(bing_rows))


def build_headlines(brand: str, niche: str) -> list[str]:
    candidates = [
        f"{brand} Review",
        f"Compare {niche}",
        f"{niche} Tools",
        "See Pros And Cons",
        "Compare Plans",
        "Read Before You Try",
        "Software Comparison",
        "Find The Right Tool",
        "Review And Pricing",
        "Start With Research",
    ]
    return [trim(item, 30) for item in candidates]


def build_descriptions(brand: str, niche: str) -> list[str]:
    candidates = [
        f"Compare {brand} with key alternatives before choosing a {niche} tool.",
        "Read a clear overview with benefits, limits, pricing notes and disclosure.",
        "Explore use cases and questions to check before you sign up.",
        "No income claims. Review official terms before using paid traffic.",
    ]
    clean = []
    for text in candidates:
        lowered = text.lower()
        if any(claim in lowered for claim in BAD_CLAIMS):
            continue
        clean.append(trim(text, 90))
    return clean


def trim(text: str, limit: int) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "."


def normalize_ads_df(df: pd.DataFrame) -> pd.DataFrame:
    for column in REQUIRED_AD_COLUMNS:
        if column not in df.columns:
            df[column] = ""
    return df


def validate_ads_csv(df: pd.DataFrame, platform: str) -> None:
    missing = [column for column in REQUIRED_AD_COLUMNS if column not in df.columns]
    if missing:
        raise ValueError(f"{platform} ads CSV thiếu cột: {', '.join(missing)}")
    required_non_empty = ["Final URL", "Headline 1", "Description 1"]
    for column in required_non_empty:
        empty_count = df[column].astype(str).str.strip().eq("").sum()
        if empty_count:
            raise ValueError(f"{platform} ads CSV có {empty_count} dòng trống {column}")


def to_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() not in {"0", "false", "no", "blocked", ""}


def choose_final_url(offer: pd.Series, landing_map: dict) -> str:
    if not to_bool(offer.get("direct_linking_allowed", False)):
        landing = landing_map.get(offer.get("offer_id"), {})
        if settings.base_site_url:
            slug = slug_from_landing(landing, offer)
            return f"{settings.base_site_url}/{slug}/"
        return str(landing.get("landing_page_url") or landing.get("landing_page") or offer.get("website", ""))
    return str(offer.get("affiliate_url") or offer.get("website") or "")


def slug_from_landing(landing: dict, offer: pd.Series) -> str:
    landing_path = str(landing.get("landing_page", ""))
    if landing_path:
        parts = landing_path.replace("\\", "/").split("/")
        if len(parts) >= 2:
            return parts[-2]
    return str(offer.get("offer_id", "offer")).strip("/")
