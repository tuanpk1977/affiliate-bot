from __future__ import annotations

import pandas as pd


def simulate_offer_profit(
    offer: dict,
    daily_budget: float = 25.0,
    ctr: float = 0.045,
    conversion_rate: float = 0.035,
    cpc: float | None = None,
) -> dict:
    cpc = float(cpc if cpc is not None else offer.get("estimated_cpc") or {"Low": 1.8, "Medium": 3.2, "High": 5.4}.get(offer.get("competition"), 3.0))
    clicks = daily_budget / cpc if cpc else 0
    conversions = clicks * conversion_rate
    commission = float(offer.get("expected_commission_value") or 0)
    if commission <= 0:
        commission = float(offer.get("flat_commission") or 0)
    if commission <= 0:
        commission = max(20.0, float(offer.get("commission_rate") or 0) / 100 * 120)
    revenue = conversions * commission
    profit = revenue - daily_budget
    roi = (profit / daily_budget * 100) if daily_budget else 0
    return {
        "daily_budget": round(daily_budget, 2),
        "assumed_cpc": round(cpc, 2),
        "assumed_ctr": ctr,
        "assumed_conversion_rate": conversion_rate,
        "expected_clicks": round(clicks, 2),
        "expected_conversions": round(conversions, 2),
        "expected_revenue": round(revenue, 2),
        "expected_roi": round(roi, 2),
        "expected_profit": round(profit, 2),
        "break_even_cpa": round(commission, 2),
    }


def simulate_scenarios(offer: dict, daily_budget: float = 25.0, base_cpc: float | None = None) -> pd.DataFrame:
    base = float(base_cpc if base_cpc is not None else offer.get("estimated_cpc") or {"Low": 1.8, "Medium": 3.2, "High": 5.4}.get(offer.get("competition"), 3.0))
    scenarios = [
        ("Conservative", base * 1.25, 0.012),
        ("Normal", base, 0.025),
        ("Aggressive", base * 0.85, 0.045),
    ]
    rows = []
    for name, cpc, conversion_rate in scenarios:
        result = simulate_offer_profit(
            offer,
            daily_budget=daily_budget,
            ctr=0.04,
            conversion_rate=conversion_rate,
            cpc=cpc,
        )
        rows.append(
            {
                "scenario": name,
                "CPC": result["assumed_cpc"],
                "Conversion Rate": conversion_rate,
                "ROI": result["expected_roi"],
                "Profit": result["expected_profit"],
            }
        )
    return pd.DataFrame(rows)


def simulate_all(offer_scores: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, offer in offer_scores.iterrows():
        for _, scenario in simulate_scenarios(offer.to_dict()).iterrows():
            rows.append({"offer_id": offer.get("offer_id", ""), "brand_name": offer.get("brand_name", ""), **scenario.to_dict()})
    return pd.DataFrame(rows)
