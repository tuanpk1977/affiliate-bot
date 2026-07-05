from __future__ import annotations

import csv
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable


BASE_URL = "https://smileaireviewhub.com"


def slugify(value: Any) -> str:
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", str(value or "").lower())).strip("-")


def normalize_topic(value: Any) -> str:
    text = re.sub(r"[^a-z0-9 ]+", " ", str(value or "").lower())
    stop = {"a", "an", "the", "and", "or", "for", "of", "to", "in", "with", "review", "reviews", "2026"}
    return " ".join(word for word in text.split() if word not in stop)


def jaccard_similarity(left: str, right: str) -> float:
    a = set(normalize_topic(left).split())
    b = set(normalize_topic(right).split())
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def content_hash(payload: Any) -> str:
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def clean_words(value: str, limit: int = 58) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else text[: limit - 1].rsplit(" ", 1)[0]


def rows_from_json_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("today_best_topics", "topics", "scores", "selected_topics", "todays_top_10"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


def ensure_unique_slug(base_slug: str, used: Iterable[str]) -> str:
    used_set = set(used)
    if base_slug not in used_set:
        return base_slug
    index = 2
    while f"{base_slug}-{index}" in used_set:
        index += 1
    return f"{base_slug}-{index}"
