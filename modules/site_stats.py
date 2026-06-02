from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from config import settings


DEFAULT_SITE_STATS: dict[str, Any] = {
    "lastUpdated": "June 2, 2026",
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
        stats.update({key: value for key, value in loaded.items() if value not in ("", None)})
    return stats
