from __future__ import annotations


def analyze_competitor_ads(keyword: str, niche: str) -> dict:
    lower = f"{keyword} {niche}".lower()
    if "crm" in lower:
        angle = "pipeline visibility and sales productivity"
        pain = "lost leads, scattered customer data"
    elif "seo" in lower:
        angle = "rank faster with guided content optimization"
        pain = "slow content planning, weak rankings"
    elif "video" in lower:
        angle = "create training or marketing videos faster"
        pain = "expensive video production"
    else:
        angle = "save time with a focused software workflow"
        pain = "manual work and tool overload"
    return {
        "common_headlines": "Compare top tools | Save time | Start faster",
        "common_cta": "Try today | Compare plans | See demo",
        "common_angle": angle,
        "pain_points_used": pain,
        "style_analysis": "Competitors use direct benefit-led headlines, short proof points, and low-friction CTAs.",
    }
