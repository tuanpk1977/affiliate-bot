from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from config import settings


DEFAULT_SITE_STATS: dict[str, Any] = {
    "lastUpdated": "June 2, 2026",
    "author": {
        "name": "Nguyen Quoc Tuan",
        "title": "AI Tools Researcher & Builder of SmileAIReviewHub",
        "lastUpdated": "June 2026",
        "avatarInitials": "NT",
        "avatarImage": "",
    },
    "newsletter": {
        "heading": "Get Weekly AI Tool Updates",
        "description": "Practical AI reviews, pricing checks, comparison guides, and build-in-public notes.",
        "emailPlaceholder": "Email address",
        "buttonLabel": "Subscribe",
        "statusMessage": "Newsletter integration coming soon.",
    },
    "reviewCtas": {
        "officialLabel": "Visit Official Website",
        "pricingLabel": "Check Current Pricing",
        "alternativesLabel": "Compare Alternatives",
        "officialUrlTemplate": "/go/{slug}/?src=review/{slug}&cta=review_page",
        "pricingUrlTemplate": "/go/{slug}/?src=review/{slug}&cta=pricing_check",
        "alternativesUrl": "#alternatives",
    },
    "ratingOverrides": {},
    "socialProof": [
        {"value": "75,000+", "label": "Facebook Views"},
        {"value": "Weekly", "label": "AI Reviews"},
        {"value": "10+", "label": "AI Tools Compared"},
        {"value": "Updated", "label": "Regularly"},
    ],
    "popularToolsThisWeek": [
        {"name": "ChatGPT", "url": "/review/chatgpt/"},
        {"name": "SEMrush", "url": "/review/semrush/"},
        {"name": "Jasper AI", "url": "/review/jasper-ai/"},
        {"name": "Canva AI", "url": "/review/canva/"},
        {"name": "Grammarly", "url": "/pricing/grammarly/"},
    ],
    "reviewComparisonDefaults": {
        "startingPrice": "Check official pricing",
        "freeTrial": "Check current trial terms",
        "easeOfUse": "Beginner-friendly after setup",
        "valueForMoney": "Strong when the workflow fit is clear",
    },
}


def site_stats_path() -> Path:
    return settings.base_dir / "config" / "siteStats.json"


def load_site_stats() -> dict[str, Any]:
    stats = deepcopy(DEFAULT_SITE_STATS)
    path = site_stats_path()
    if not path.exists():
        return stats
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return stats
    if isinstance(loaded, dict):
        deep_merge(stats, {key: value for key, value in loaded.items() if value not in ("", None)})
    return stats


def deep_merge(base: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            deep_merge(base[key], {inner_key: inner_value for inner_key, inner_value in value.items() if inner_value not in ("", None)})
        elif value not in ("", None):
            base[key] = value
    return base
