from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any, Iterable


def normalize_keyword(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9+.# -]", " ", value.lower())).strip()


def slugify(value: str) -> str:
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", normalize_keyword(value))).strip("-")


def load_keyword_file(path: Path) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        rows = payload if isinstance(payload, list) else payload.get("keywords", [])
    elif path.suffix.lower() == ".csv":
        with path.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
    else:
        rows = [{"keyword": line} for line in path.read_text(encoding="utf-8").splitlines()]
    return [dict(row) if isinstance(row, dict) else {"keyword": str(row)} for row in rows]


def collect_candidates(seeds: Iterable[str] = (), imports: Iterable[Path] = ()) -> list[dict[str, Any]]:
    raw: list[dict[str, Any]] = [{"keyword": seed, "source": "manual_seed"} for seed in seeds]
    for path in imports:
        for row in load_keyword_file(path):
            row.setdefault("source", f"import:{path.name}")
            raw.append(row)
    unique: dict[str, dict[str, Any]] = {}
    for row in raw:
        keyword = normalize_keyword(str(row.get("keyword") or row.get("query") or ""))
        if not keyword:
            continue
        current = unique.setdefault(keyword, {"keyword": keyword, "slug": slugify(keyword), "sources": [], "source_status": "verified"})
        source = str(row.get("source") or "manual_seed")
        if source not in current["sources"]:
            current["sources"].append(source)
        for key in ("search_volume", "difficulty", "cpc", "notes"):
            if row.get(key) not in (None, ""):
                current[key] = row[key]
    return sorted(unique.values(), key=lambda item: item["keyword"])
