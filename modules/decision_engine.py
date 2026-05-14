from __future__ import annotations

import pandas as pd


def decide_campaigns(roi_report: pd.DataFrame) -> pd.DataFrame:
    if roi_report.empty:
        return roi_report
    rows = []
    for _, row in roi_report.iterrows():
        roi = float(row.get("ROI") or 0)
        cpc = float(row.get("CPC") or 0)
        conversions = float(row.get("conversions") or 0)
        action = "PAUSE" if roi < -20 else "WATCH" if roi <= 10 else "OPTIMIZE" if roi <= 30 else "SCALE"
        reasons = []
        if cpc > 5:
            reasons.append("CPC cao")
        if conversions <= 0:
            reasons.append("chưa có conversion")
        if roi < 0:
            reasons.append("đang lỗ")
        if roi > 30:
            reasons.append("ROI tốt, có thể tăng budget từng bước")
        if not reasons:
            reasons.append("cần thêm dữ liệu trước khi tăng ngân sách")
        rows.append({**row.to_dict(), "decision": action, "decision_reason": " | ".join(reasons)})
    return pd.DataFrame(rows)


def decide_offers(offer_scores: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, offer in offer_scores.iterrows():
        if offer.get("compliance_status") == "BLOCKED":
            decision = "BLOCKED"
        elif float(offer.get("total_score") or 0) >= 85 and offer.get("risk_level") == "Low":
            decision = "TEST_FIRST"
        elif float(offer.get("total_score") or 0) >= 70:
            decision = "VERIFY_THEN_TEST"
        else:
            decision = "WATCHLIST"
        rows.append({"offer_id": offer.get("offer_id", ""), "brand_name": offer.get("brand_name", ""), "offer_decision": decision})
    return pd.DataFrame(rows)
