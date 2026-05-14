from __future__ import annotations

import pandas as pd

from modules.trend_detector import detect_trend


COMPETITION_POINTS = {"Low": 16, "Medium": 10, "High": -12}
TREND_POINTS = {"Rising": 8, "Stable": 4, "Declining": -8}


def score_offers(offers: pd.DataFrame, market: pd.DataFrame, compliance: pd.DataFrame) -> pd.DataFrame:
    market_map = market.set_index("niche").to_dict("index") if not market.empty else {}
    rows = []
    for idx, offer in offers.reset_index(drop=True).iterrows():
        data = offer.to_dict()
        niche = str(data.get("niche", ""))
        market_data = market_map.get(niche, {})
        comp = str(market_data.get("estimated_competition", "Medium"))
        trend = detect_trend(niche)
        competition_score = COMPETITION_POINTS.get(comp, 10)
        trend_score = TREND_POINTS.get(trend, 5)

        commission_rate = float(data.get("commission_rate") or 0)
        flat = float(data.get("flat_commission") or 0)
        cookie = int(float(data.get("cookie_days") or 0))
        trust = float(data.get("vendor_trust") or 50)
        buyer_intent = float(data.get("buyer_intent") or 50)
        recurring = bool(data.get("recurring", False))
        policy = compliance.iloc[idx].to_dict() if idx < len(compliance) else {}

        estimated_epc = round((commission_rate / 100 * 80 + flat * 0.04 + (18 if recurring else 0)) / (1.8 if comp == "High" else 1.2 if comp == "Medium" else 1), 2)
        estimated_cpc = float(market_data.get("estimated_cpc", 3.0) or 3.0)
        expected_commission = estimate_commission_value(commission_rate, flat, recurring)

        economics_score = min(22, commission_rate * 0.45 + flat * 0.035)
        economics_score += 10 if recurring else 0
        economics_score += 6 if cookie >= 60 else 4 if cookie >= 30 else 1 if cookie else 0
        economics_score = min(32, economics_score)

        policy_score = build_policy_score(policy)
        trust_score = min(12, trust / 100 * 12)
        intent_score = min(15, buyer_intent / 100 * 15)
        cpc_score = build_cpc_score(estimated_cpc, expected_commission)
        roi_proxy = estimate_roi_proxy(expected_commission, estimated_cpc, comp, buyer_intent)
        roi_score = 10 if roi_proxy > 35 else 7 if roi_proxy > 10 else 2 if roi_proxy > 0 else -8
        penalty = build_penalty(comp, estimated_cpc, expected_commission, policy)

        raw_total = round(
            max(
                0,
                min(
                    96,
                    economics_score
                    + policy_score
                    + trust_score
                    + intent_score
                    + competition_score
                    + trend_score
                    + cpc_score
                    + roi_score
                    - penalty,
                ),
            )
        )
        total = normalize_public_score(raw_total, trust, buyer_intent, comp, policy)
        estimated_roi = round(roi_proxy + raw_total * 0.18 - penalty, 1)

        grade = "A" if total >= 82 else "B" if total >= 68 else "C" if total >= 52 else "D"
        risk = classify_risk(policy, total, comp, estimated_cpc, expected_commission)

        rows.append(
            {
                **data,
                **policy,
                "total_score": total,
                "economics_score": round(economics_score, 1),
                "policy_score": round(policy_score, 1),
                "trust_score": round(trust_score, 1),
                "buyer_intent_score": round(intent_score, 1),
                "competition_score": round(competition_score, 1),
                "trend_score": round(trend_score, 1),
                "cpc_score": round(cpc_score, 1),
                "roi_score": round(roi_score, 1),
                "penalty_score": round(penalty, 1),
                "grade": grade,
                "risk_level": risk,
                "recommendation": build_recommendation(total, risk, comp, policy),
                "buyer_intent_label": "High" if buyer_intent >= 80 else "Medium" if buyer_intent >= 60 else "Low",
                "competition": comp,
                "estimated_epc": estimated_epc,
                "estimated_roi": estimated_roi,
                "expected_commission_value": round(expected_commission, 2),
                "trend": trend,
                "recommended_channels": market_data.get("recommended_channels", "Google Search, Bing Search"),
                "market_notes": market_data.get("market_notes", ""),
            }
        )
    return pd.DataFrame(rows).sort_values("total_score", ascending=False)


def build_recommendation(total: int, risk: str, competition: str, policy: dict) -> str:
    if policy.get("compliance_status") == "BLOCKED":
        return "Không tạo ads. Chỉ giữ để nghiên cứu hoặc kiểm tra lại terms."
    if total >= 85 and risk == "Low":
        return "Nên test trước bằng Google/Bing Search với ngân sách nhỏ."
    if total >= 70:
        return "Có thể test sau khi kiểm tra policy và tạo landing page riêng."
    if competition == "High":
        return "Chỉ nên test keyword ngách hoặc comparison, tránh broad keyword."
    return "Đưa vào watchlist, cần thêm bằng chứng EPC và policy."


def normalize_public_score(raw_total: int, trust: float, buyer_intent: float, competition: str, policy: dict) -> int:
    if policy.get("compliance_status") == "BLOCKED":
        return round(max(55, min(68, raw_total + 45)))
    base = 62 + trust * 0.16 + buyer_intent * 0.12
    if raw_total >= 75:
        base += 6
    elif raw_total >= 50:
        base += 2
    elif raw_total < 20:
        base -= 3
    if competition == "High":
        base -= 4
    elif competition == "Low":
        base += 3
    if policy.get("compliance_status") == "SAFE":
        base += 2
    return round(max(65, min(92, base)))


def classify_risk(policy: dict, total: int, competition: str, cpc: float, commission: float) -> str:
    if policy.get("compliance_status") == "BLOCKED":
        return "High"
    notes = str(policy.get("policy_notes", "")).lower()
    complex_policy = any(term in notes for term in ["paid search", "misleading", "coupon", "google ads", "bing"])
    if competition == "High" or cpc > max(commission * 0.18, 5):
        return "Medium"
    if total >= 80 and not complex_policy:
        return "Low"
    if policy.get("compliance_status") == "SAFE":
        return "Low"
    return "Medium"


def estimate_commission_value(commission_rate: float, flat: float, recurring: bool = False) -> float:
    if flat > 0:
        return flat
    if commission_rate > 0:
        assumed_order_value = 120
        assumed_months = 4 if recurring else 1
        return max(12.0, commission_rate / 100 * assumed_order_value * assumed_months)
    return 20.0


def build_policy_score(policy: dict) -> float:
    if policy.get("compliance_status") == "BLOCKED":
        return -20
    score = 14 if policy.get("compliance_status") == "SAFE" else 8
    if not policy.get("direct_linking_allowed", False):
        score -= 1
    if not policy.get("brand_bidding_allowed", False):
        score -= 1
    return score


def build_cpc_score(cpc: float, commission: float) -> float:
    if cpc <= 0:
        return 0
    if cpc > commission:
        return -12
    ratio = cpc / max(commission, 1)
    if ratio <= 0.08:
        return 10
    if ratio <= 0.15:
        return 6
    if ratio <= 0.25:
        return 2
    return -6


def estimate_roi_proxy(commission: float, cpc: float, competition: str, buyer_intent: float) -> float:
    if cpc <= 0:
        return -100
    conversion_rate = 0.032 if buyer_intent >= 85 else 0.024 if buyer_intent >= 75 else 0.016
    revenue_per_click = commission * conversion_rate
    competition_drag = 24 if competition == "High" else 10 if competition == "Medium" else 0
    return ((revenue_per_click - cpc) / cpc * 100) - competition_drag


def build_penalty(competition: str, cpc: float, commission: float, policy: dict) -> float:
    penalty = 0
    if competition == "High":
        penalty += 12
    if cpc > commission:
        penalty += 15
    elif cpc > commission * 0.25:
        penalty += 6
    if not policy.get("direct_linking_allowed", False):
        penalty += 1
    if not policy.get("brand_bidding_allowed", False):
        penalty += 1
    return penalty
