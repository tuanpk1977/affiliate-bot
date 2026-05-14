from __future__ import annotations

import logging
import re

import pandas as pd

from config import settings


LOGGER = logging.getLogger(__name__)

AFFILIATE_LINK_COLUMNS = [
    "tool_slug",
    "tool_name",
    "brand",
    "slug",
    "official_url",
    "affiliate_url",
    "affiliate_status",
    "status",
    "notes",
    "commission_note",
    "network",
    "approved",
]


SEED_LINKS = [
    {
        "brand": "Gamma",
        "slug": "gamma",
        "official_url": "https://gamma.app",
        "affiliate_url": "",
        "status": "pending_approval",
        "commission_note": "Affiliate link pending approval.",
        "network": "Other",
        "approved": False,
    },
    {
        "brand": "ElevenLabs",
        "slug": "elevenlabs",
        "official_url": "https://elevenlabs.io",
        "affiliate_url": "",
        "status": "pending_approval",
        "commission_note": "Affiliate link pending approval.",
        "network": "Other",
        "approved": False,
    },
    {
        "brand": "Webflow AI",
        "slug": "webflow-ai",
        "official_url": "https://webflow.com/ai",
        "affiliate_url": "",
        "status": "pending_approval",
        "commission_note": "Affiliate link pending approval.",
        "network": "Other",
        "approved": False,
    },
    {
        "brand": "AdCreative AI",
        "slug": "adcreative-ai",
        "official_url": "https://www.adcreative.ai",
        "affiliate_url": "",
        "status": "pending_approval",
        "commission_note": "Affiliate link pending approval.",
        "network": "Other",
        "approved": False,
    },
    {
        "brand": "Pipedrive CRM",
        "slug": "pipedrive-crm",
        "official_url": "https://www.pipedrive.com",
        "affiliate_url": "",
        "status": "pending_approval",
        "commission_note": "Affiliate link pending approval.",
        "network": "PartnerStack",
        "approved": False,
    },
]


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-") or "offer"


def load_affiliate_links() -> pd.DataFrame:
    ensure_affiliate_links()
    try:
        df = pd.read_csv(settings.affiliate_links_file)
    except Exception:
        LOGGER.exception("Could not load affiliate links file")
        df = pd.DataFrame(columns=AFFILIATE_LINK_COLUMNS)
    return normalize_affiliate_links(df)


def ensure_affiliate_links(offers: pd.DataFrame | None = None) -> pd.DataFrame:
    settings.affiliate_links_file.parent.mkdir(parents=True, exist_ok=True)
    if settings.affiliate_links_file.exists():
        try:
            current = pd.read_csv(settings.affiliate_links_file)
        except Exception:
            LOGGER.exception("Could not read existing affiliate links file")
            current = pd.DataFrame(columns=AFFILIATE_LINK_COLUMNS)
    else:
        current = pd.DataFrame(columns=AFFILIATE_LINK_COLUMNS)

    current = normalize_affiliate_links(current)
    seed = normalize_affiliate_links(pd.DataFrame(SEED_LINKS))
    frames = [current, seed]
    if offers is not None and not offers.empty:
        frames.append(links_from_offers(offers))
    merged = pd.concat(frames, ignore_index=True, sort=False)
    merged["slug"] = merged.apply(lambda row: row["slug"] or slugify(row["brand"]), axis=1)
    merged = merged.drop_duplicates(subset=["slug"], keep="first")
    merged = normalize_affiliate_links(merged)
    merged.to_csv(settings.affiliate_links_file, index=False)
    return merged


def links_from_offers(offers: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, offer in offers.iterrows():
        brand = str(offer.get("brand_name", "")).strip()
        if not brand:
            continue
        rows.append(
            {
                "brand": brand,
                "slug": slugify(brand),
                "official_url": str(offer.get("website", "")).strip(),
                "affiliate_url": "",
                "status": "pending_approval",
                "commission_note": "Affiliate link pending approval.",
                "network": str(offer.get("network", "Other")).strip() or "Other",
                "approved": False,
            }
        )
    return normalize_affiliate_links(pd.DataFrame(rows))


def normalize_affiliate_links(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        df = pd.DataFrame(columns=AFFILIATE_LINK_COLUMNS)
    for column in AFFILIATE_LINK_COLUMNS:
        if column not in df.columns:
            df[column] = "" if column != "approved" else False
    df = df[AFFILIATE_LINK_COLUMNS].fillna("")
    df["tool_slug"] = df.apply(lambda row: str(row.get("tool_slug") or row.get("slug") or slugify(row.get("brand", ""))).strip(), axis=1)
    df["tool_name"] = df.apply(lambda row: str(row.get("tool_name") or row.get("brand") or "").strip(), axis=1)
    df["affiliate_status"] = df.apply(lambda row: normalize_status(row.get("affiliate_status") or row.get("status") or ("approved" if to_bool(row.get("approved")) else "pending")), axis=1)
    df["notes"] = df.apply(lambda row: str(row.get("notes") or row.get("commission_note") or "").strip(), axis=1)
    df["slug"] = df.apply(lambda row: str(row.get("slug") or row.get("tool_slug") or slugify(row.get("brand", ""))).strip(), axis=1)
    df["brand"] = df.apply(lambda row: str(row.get("brand") or row.get("tool_name") or "").strip(), axis=1)
    df["status"] = df.apply(lambda row: str(row.get("status") or row.get("affiliate_status") or "pending").strip(), axis=1)
    df["approved"] = df["approved"].map(to_bool)
    return df


def save_affiliate_links(df: pd.DataFrame) -> pd.DataFrame:
    normalized = normalize_affiliate_links(df)
    normalized["slug"] = normalized.apply(lambda row: row["slug"] or slugify(row["brand"]), axis=1)
    normalized = normalized.drop_duplicates(subset=["slug"], keep="last")
    normalized.to_csv(settings.affiliate_links_file, index=False)
    return normalized


def upsert_affiliate_link(record: dict) -> pd.DataFrame:
    current = load_affiliate_links()
    row = normalize_affiliate_links(pd.DataFrame([record]))
    merged = pd.concat([current, row], ignore_index=True, sort=False)
    return save_affiliate_links(merged)


def link_for_brand(brand: str, links: pd.DataFrame) -> dict:
    if links.empty:
        return default_link(brand)
    slug = slugify(brand)
    match = links[(links["slug"] == slug) | (links["brand"].str.lower() == str(brand).lower())]
    if match.empty:
        return default_link(brand)
    row = match.iloc[0].to_dict()
    approved = to_bool(row.get("approved")) or normalize_status(row.get("affiliate_status")) == "approved"
    affiliate_url = str(row.get("affiliate_url", "")).strip()
    official_url = str(row.get("official_url", "")).strip()
    cta_url = affiliate_url if approved and affiliate_url else official_url
    pending_note = "" if approved and affiliate_url else "Affiliate link pending approval."
    return {**row, "cta_url": cta_url, "pending_note": pending_note}


def default_link(brand: str) -> dict:
    return {
        "brand": brand,
        "slug": slugify(brand),
        "official_url": "",
        "affiliate_url": "",
        "status": "pending_approval",
        "commission_note": "Affiliate link pending approval.",
        "network": "Other",
        "approved": False,
        "cta_url": "",
        "pending_note": "Affiliate link pending approval.",
    }


def to_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "approved"}


def normalize_status(value: object) -> str:
    status = str(value or "").strip().lower().replace("_approval", "").replace("pending_approval", "pending")
    if status in {"approved", "rejected", "official_only", "pending"}:
        return status
    if status in {"true", "yes", "1"}:
        return "approved"
    return "pending"
