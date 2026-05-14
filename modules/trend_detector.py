from __future__ import annotations


TREND_BY_NICHE = {
    "AI Video": "Rising",
    "AI SEO": "Rising",
    "AI Coding": "Rising",
    "AI Meeting": "Rising",
    "Automation": "Rising",
    "AI Voice": "Stable",
    "AI Writing": "Stable",
    "AI Design": "Stable",
    "CRM": "Stable",
    "Productivity": "Stable",
    "Email Marketing": "Stable",
}


def detect_trend(niche: str) -> str:
    return TREND_BY_NICHE.get(str(niche), "Stable")
