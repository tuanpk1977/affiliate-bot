from __future__ import annotations

import pandas as pd


NEGATIVES = ["free", "crack", "nulled", "coupon code", "torrent", "job", "salary"]


def generate_keywords(offer_scores: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, offer in offer_scores.iterrows():
        brand = str(offer.get("brand_name", "")).strip()
        niche = str(offer.get("niche", "")).strip()
        generic = niche.lower().replace("ai ", "ai ").replace("crm", "crm")
        allow_brand = bool(offer.get("brand_bidding_allowed", False))
        base_cpc = estimated_cpc_by_competition(str(offer.get("competition", "Medium")))

        groups = {
            "buyer_keywords": [f"best {generic} software", f"{generic} tool for business"],
            "review_keywords": [f"{generic} software review", f"{generic} tool reviews"],
            "comparison_keywords": [f"best {generic} tools", f"{generic} software comparison"],
            "alternatives_keywords": [f"{generic} alternatives", f"affordable {generic} platform"],
            "problem_solution_keywords": [f"how to automate {generic}", f"solve {generic} workflow"],
            "negative_keywords": NEGATIVES,
        }
        if allow_brand and brand:
            groups["review_keywords"].append(f"{brand} review")
            groups["alternatives_keywords"].append(f"{brand} alternatives")

        for group, keywords in groups.items():
            for keyword in keywords:
                rows.append(
                    {
                        "offer_id": offer.get("offer_id", ""),
                        "brand_name": brand,
                        "niche": niche,
                        "keyword_group": group,
                        "keyword": keyword,
                        "intent_score": intent_score(group),
                        "competition_level": offer.get("competition", "Medium"),
                        "estimated_cpc": 0 if group == "negative_keywords" else base_cpc,
                        "match_type": "negative" if group == "negative_keywords" else "phrase",
                    }
                )
    return pd.DataFrame(rows)


def intent_score(group: str) -> int:
    return {
        "buyer_keywords": 90,
        "review_keywords": 84,
        "comparison_keywords": 82,
        "alternatives_keywords": 78,
        "problem_solution_keywords": 68,
        "negative_keywords": 0,
    }.get(group, 50)


def estimated_cpc_by_competition(level: str) -> float:
    return {"Low": 1.8, "Medium": 3.2, "High": 5.4}.get(level, 3.0)
