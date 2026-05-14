from __future__ import annotations

import pandas as pd

from config import settings


def ensure_sample_campaign_results() -> None:
    if settings.campaigns_file.exists():
        return
    rows = []
    brands = ["Jasper AI", "Surfer SEO", "Synthesia", "ElevenLabs", "Make", "HubSpot", "Canva", "Reclaim AI", "Notion", "ActiveCampaign"]
    for idx in range(20):
        brand = brands[idx % len(brands)]
        impressions = 1200 + idx * 140
        clicks = 38 + idx * 4
        cost = round(clicks * (2.1 + (idx % 5) * 0.45), 2)
        conversions = max(0, (idx % 6) + (1 if idx % 3 == 0 else 0))
        revenue = round(conversions * (35 + (idx % 4) * 25), 2)
        rows.append({"campaign": f"AIIP - {brand} - Test {idx+1}", "offer_name": brand, "impressions": impressions, "clicks": clicks, "cost": cost, "conversions": conversions, "revenue": revenue})
    pd.DataFrame(rows).to_csv(settings.campaigns_file, index=False)


def build_roi_report() -> pd.DataFrame:
    ensure_sample_campaign_results()
    df = pd.read_csv(settings.campaigns_file).fillna(0)
    if df.empty:
        return pd.DataFrame()
    df["CTR"] = (df["clicks"] / df["impressions"] * 100).round(2)
    df["CPC"] = (df["cost"] / df["clicks"].replace(0, pd.NA)).fillna(0).round(2)
    df["CPA"] = (df["cost"] / df["conversions"].replace(0, pd.NA)).fillna(0).round(2)
    df["EPC"] = (df["revenue"] / df["clicks"].replace(0, pd.NA)).fillna(0).round(2)
    df["profit"] = (df["revenue"] - df["cost"]).round(2)
    df["ROI"] = (df["profit"] / df["cost"].replace(0, pd.NA) * 100).fillna(0).round(2)
    return df
