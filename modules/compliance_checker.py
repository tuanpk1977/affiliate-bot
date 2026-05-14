from __future__ import annotations

import re

import pandas as pd


PPC_BLOCK_PATTERNS = [
    (r"\bno ppc\b|\bppc prohibited\b|\bpaid search prohibited\b", "Không được chạy PPC."),
]

GOOGLE_BLOCK_PATTERNS = [
    (r"\bno google ads\b|\bgoogle ads prohibited\b", "Không được chạy Google Ads."),
]

BING_BLOCK_PATTERNS = [
    (r"\bno bing ads\b|\bbing ads prohibited\b|\bno microsoft ads\b", "Không được chạy Bing Ads."),
]

WARNING_PATTERNS = [
    (r"\bno direct linking\b|direct linking (is )?not allowed", "Không được dùng link affiliate trực tiếp."),
    (r"\bno trademark bidding\b|brand bidding restricted|trademark", "Không được bid từ khóa thương hiệu."),
    (r"\bcoupon restrictions?\b|coupon abuse", "Có giới hạn coupon/deal keyword."),
    (r"\bmisleading\b|no misleading", "Cần tránh claim gây hiểu nhầm."),
    (r"paid search restricted", "Paid search có hạn chế, cần kiểm tra terms trước khi upload."),
]


def check_offer_compliance(offer: dict) -> dict:
    text = str(offer.get("traffic_policy", "")).lower()
    notes = []
    google_blocked = False
    bing_blocked = False

    for pattern, note in PPC_BLOCK_PATTERNS:
        if re.search(pattern, text):
            notes.append(note)
            google_blocked = True
            bing_blocked = True

    for pattern, note in GOOGLE_BLOCK_PATTERNS:
        if re.search(pattern, text):
            notes.append(note)
            google_blocked = True

    for pattern, note in BING_BLOCK_PATTERNS:
        if re.search(pattern, text):
            notes.append(note)
            bing_blocked = True

    for pattern, note in WARNING_PATTERNS:
        if re.search(pattern, text):
            notes.append(note)

    direct = to_bool(offer.get("direct_linking_allowed", False))
    brand = to_bool(offer.get("brand_bidding_allowed", False))
    if not direct and not any("link affiliate trực tiếp" in note for note in notes):
        notes.append("Không được dùng link affiliate trực tiếp.")
    if not brand and not any("từ khóa thương hiệu" in note for note in notes):
        notes.append("Không được bid từ khóa thương hiệu.")

    status = "BLOCKED" if google_blocked and bing_blocked else "WARNING" if notes or google_blocked or bing_blocked else "SAFE"
    return {
        "compliance_status": status,
        "policy_notes": " | ".join(notes) if notes else "Không thấy tín hiệu chặn trong dữ liệu hiện tại.",
        "can_generate_ads": not (google_blocked and bing_blocked),
        "can_generate_google_ads": not google_blocked,
        "can_generate_bing_ads": not bing_blocked,
        "google_ads_policy": "BLOCKED" if google_blocked else "ALLOWED_WITH_REVIEW",
        "bing_ads_policy": "BLOCKED" if bing_blocked else "ALLOWED_WITH_REVIEW",
        "direct_linking_allowed": direct,
        "brand_bidding_allowed": brand,
    }


def build_compliance_report(offers: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame([check_offer_compliance(row.to_dict()) for _, row in offers.iterrows()])


def to_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "allowed"}
