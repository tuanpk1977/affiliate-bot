from __future__ import annotations

from datetime import date

import pandas as pd

from config import settings


def ensure_data_sources(offers: pd.DataFrame) -> None:
    existing = pd.DataFrame()
    if settings.data_sources_file.exists():
        try:
            existing = pd.read_csv(settings.data_sources_file).fillna("")
        except Exception:
            existing = pd.DataFrame()
    existing_brands = set(existing.get("brand_name", pd.Series(dtype=str)).astype(str))
    rows = []
    for _, offer in offers.iterrows():
        brand = str(offer.get("brand_name", ""))
        if brand in existing_brands:
            continue
        affiliate_url = str(offer.get("affiliate_url", ""))
        rows.append(
            {
                "brand_name": brand,
                "affiliate_program_url": affiliate_url,
                "terms_url": affiliate_url,
                "payout_source": "Dữ liệu mẫu, chưa xác minh payout thật",
                "policy_source": "Dữ liệu mẫu, chưa xác minh affiliate terms thật",
                "last_checked": date.today().isoformat(),
                "confidence": "LOW",
            }
        )
    if rows:
        output = pd.concat([existing, pd.DataFrame(rows)], ignore_index=True)
    else:
        output = existing
    if output.empty:
        output = pd.DataFrame(columns=["brand_name", "affiliate_program_url", "terms_url", "payout_source", "policy_source", "last_checked", "confidence"])
    output.to_csv(settings.data_sources_file, index=False)


def load_data_sources(offers: pd.DataFrame) -> pd.DataFrame:
    ensure_data_sources(offers)
    try:
        sources = pd.read_csv(settings.data_sources_file).fillna("")
    except Exception:
        sources = pd.DataFrame()
    return sources


def attach_data_confidence(offer_scores: pd.DataFrame, data_sources: pd.DataFrame) -> pd.DataFrame:
    if data_sources.empty:
        offer_scores["data_confidence"] = "LOW"
        offer_scores["data_source_note"] = "Dữ liệu mẫu/rule-based, chưa xác minh."
        return offer_scores

    source_map = data_sources.set_index("brand_name").to_dict("index")
    rows = []
    for _, offer in offer_scores.iterrows():
        source = source_map.get(offer.get("brand_name"), {})
        confidence = str(source.get("confidence", "LOW")).upper() or "LOW"
        rows.append(
            {
                **offer.to_dict(),
                "data_confidence": confidence,
                "data_source_note": build_source_note(confidence, source),
            }
        )
    return pd.DataFrame(rows)


def build_source_note(confidence: str, source: dict) -> str:
    if confidence == "HIGH":
        return "Có nguồn xác minh/API hoặc dữ liệu đã kiểm chứng."
    if confidence == "MEDIUM":
        return "Dữ liệu nhập thủ công, cần kiểm tra định kỳ."
    return "Dữ liệu mẫu/rule-based, chưa xác minh affiliate policy và payout thật."
