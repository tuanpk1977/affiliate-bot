from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd

from config import settings


USER_OFFER_COLUMNS = [
    "offer_id",
    "brand_name",
    "website",
    "affiliate_program_url",
    "affiliate_url",
    "terms_url",
    "network",
    "niche",
    "commission_type",
    "commission_rate",
    "flat_commission",
    "cookie_days",
    "recurring",
    "traffic_policy",
    "brand_bidding_allowed",
    "direct_linking_allowed",
    "country_allowed",
    "data_confidence",
    "data_source_note",
    "last_checked",
    "manual_note",
]


def normalize_url(url: str) -> str:
    value = str(url or "").strip()
    if not value:
        return ""
    if not re.match(r"^https?://", value, flags=re.I):
        value = "https://" + value
    parsed = urlparse(value)
    if not parsed.netloc:
        return ""
    return value.rstrip("/")


def extract_brand_name(url: str) -> str:
    parsed = urlparse(normalize_url(url))
    host = parsed.netloc.lower().removeprefix("www.")
    if not host:
        return "UNKNOWN"
    if "partnerstack.com" in host:
        parts = [part for part in parsed.path.split("/") if part]
        return prettify_brand(parts[0]) if parts else "PartnerStack Offer"
    domain = host.split(".")[0]
    return prettify_brand(domain)


def guess_niche(url: str, brand_name: str = "", note: str = "") -> str:
    text = f"{url} {brand_name} {note}".lower()
    if any(term in text for term in ["seo", "rank", "content"]):
        return "AI SEO"
    if any(term in text for term in ["video", "avatar"]):
        return "AI Video"
    if any(term in text for term in ["voice", "audio", "tts"]):
        return "AI Voice"
    if any(term in text for term in ["crm", "sales"]):
        return "CRM"
    if any(term in text for term in ["email", "newsletter"]):
        return "Email Marketing"
    if any(term in text for term in ["automation", "workflow", "zapier", "make"]):
        return "Automation"
    if any(term in text for term in ["design", "image", "canva"]):
        return "AI Design"
    if any(term in text for term in ["meeting", "calendar"]):
        return "AI Meeting"
    if any(term in text for term in ["ai", "write", "writer", "copy"]):
        return "AI Writing"
    return "UNKNOWN"


def create_offer_id(brand_name: str, url: str = "") -> str:
    base = brand_name if brand_name and brand_name != "UNKNOWN" else extract_brand_name(url)
    slug = re.sub(r"[^a-z0-9]+", "-", str(base).lower()).strip("-")
    return slug or "user-offer"


def validate_required_fields(record: dict) -> list[str]:
    errors = []
    if not str(record.get("brand_name", "")).strip() or record.get("brand_name") == "UNKNOWN":
        errors.append("Thiếu Brand name.")
    if not normalize_url(str(record.get("affiliate_program_url", ""))):
        errors.append("Thiếu Affiliate program URL hợp lệ.")
    return errors


def build_offer_record(
    *,
    brand_name: str = "",
    affiliate_program_url: str = "",
    affiliate_url: str = "",
    terms_url: str = "",
    network: str = "Other",
    commission: str = "",
    cookie_days: str | int = "",
    country_allowed: str = "UNKNOWN",
    manual_note: str = "",
) -> dict:
    program_url = normalize_url(affiliate_program_url)
    aff_url = normalize_url(affiliate_url) or program_url
    terms = normalize_url(terms_url) or program_url
    brand = brand_name.strip() or extract_brand_name(program_url)
    commission_type, commission_rate, flat_commission, recurring = parse_commission(commission)
    cookie_value = parse_int(cookie_days)
    traffic_policy = "NEED_REVIEW - Chưa xác minh chính sách affiliate terms"
    return {
        "offer_id": create_offer_id(brand, program_url),
        "brand_name": brand or "UNKNOWN",
        "website": website_from_url(program_url),
        "affiliate_program_url": program_url,
        "affiliate_url": aff_url,
        "terms_url": terms,
        "network": network or "Other",
        "niche": guess_niche(program_url, brand, manual_note),
        "commission_type": commission_type,
        "commission_rate": commission_rate,
        "flat_commission": flat_commission,
        "cookie_days": cookie_value,
        "recurring": recurring,
        "traffic_policy": traffic_policy,
        "brand_bidding_allowed": "NEED_REVIEW",
        "direct_linking_allowed": "NEED_REVIEW",
        "country_allowed": country_allowed or "UNKNOWN",
        "data_confidence": "LOW",
        "data_source_note": "User nhập link thủ công. Bot chưa xác minh policy, payout, cookie hoặc traffic source.",
        "last_checked": date.today().isoformat(),
        "manual_note": manual_note or "",
    }


def save_user_offer(record: dict, path: Path | None = None) -> pd.DataFrame:
    output = path or settings.user_offers_file
    output.parent.mkdir(parents=True, exist_ok=True)
    normalized = {column: record.get(column, "UNKNOWN") for column in USER_OFFER_COLUMNS}
    validate_required_fields(normalized)
    existing = load_user_offers(output)
    df = pd.concat([existing, pd.DataFrame([normalized])], ignore_index=True)
    df = df.drop_duplicates(subset=["offer_id"], keep="last")
    df = df.reindex(columns=USER_OFFER_COLUMNS).fillna("UNKNOWN")
    df.to_csv(output, index=False)
    return df


def save_many_from_links(
    links: str,
    *,
    network: str = "Other",
    manual_note: str = "",
) -> pd.DataFrame:
    rows = []
    for line in str(links or "").splitlines():
        url = normalize_url(line)
        if not url:
            continue
        rows.append(
            build_offer_record(
                affiliate_program_url=url,
                network=network,
                manual_note=manual_note,
            )
        )
    existing = load_user_offers()
    if rows:
        df = pd.concat([existing, pd.DataFrame(rows)], ignore_index=True)
        df = df.drop_duplicates(subset=["offer_id"], keep="last")
        df = df.reindex(columns=USER_OFFER_COLUMNS).fillna("UNKNOWN")
        df.to_csv(settings.user_offers_file, index=False)
        return df
    return existing


def load_user_offers(path: Path | None = None) -> pd.DataFrame:
    source = path or settings.user_offers_file
    if not source.exists():
        return pd.DataFrame(columns=USER_OFFER_COLUMNS)
    try:
        return pd.read_csv(source).reindex(columns=USER_OFFER_COLUMNS).fillna("UNKNOWN")
    except Exception:
        return pd.DataFrame(columns=USER_OFFER_COLUMNS)


def parse_commission(value: str) -> tuple[str, float, float, bool]:
    text = str(value or "").lower().strip()
    recurring = "recurring" in text or "monthly" in text or "mrr" in text
    percent = re.search(r"(\d+(?:\.\d+)?)\s*%", text)
    money = re.search(r"\$?\s*(\d+(?:\.\d+)?)", text)
    if percent:
        return ("recurring" if recurring else "percentage", float(percent.group(1)), 0.0, recurring)
    if money:
        return ("flat", 0.0, float(money.group(1)), recurring)
    return ("UNKNOWN", 0.0, 0.0, recurring)


def parse_int(value: object) -> int:
    match = re.search(r"\d+", str(value or ""))
    return int(match.group(0)) if match else 0


def website_from_url(url: str) -> str:
    parsed = urlparse(normalize_url(url))
    if not parsed.netloc:
        return "UNKNOWN"
    return f"{parsed.scheme}://{parsed.netloc}"


def prettify_brand(value: str) -> str:
    clean = re.sub(r"[-_]+", " ", value).strip()
    if not clean:
        return "UNKNOWN"
    return " ".join(part.capitalize() for part in clean.split())
