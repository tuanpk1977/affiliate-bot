from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from config import settings


class CompetitorSnapshotIngestion:
    def __init__(
        self,
        *,
        json_path: Path | None = None,
        csv_path: Path | None = None,
    ) -> None:
        self.json_path = json_path or settings.data_dir / "competitor_snapshots.json"
        self.csv_path = csv_path or settings.data_dir / "competitor_snapshots.csv"

    def load(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        if self.json_path.exists():
            try:
                payload = json.loads(self.json_path.read_text(encoding="utf-8"))
                if isinstance(payload, list):
                    rows.extend(item for item in payload if isinstance(item, dict))
            except Exception:
                pass
        if self.csv_path.exists():
            with self.csv_path.open("r", encoding="utf-8", newline="") as handle:
                rows.extend(dict(row) for row in csv.DictReader(handle))
        return rows

    def for_keyword(self, keyword: str) -> dict[str, Any]:
        snapshots = [self._normalize(row) for row in self.load() if self._matches_keyword(row, keyword)]
        if not snapshots:
            return {
                "keyword": keyword,
                "coverage_status": "missing",
                "profiles": [],
                "report": "competitor coverage is missing",
            }
        return {
            "keyword": keyword,
            "coverage_status": "available",
            "profiles": snapshots,
            "report": f"loaded {len(snapshots)} competitor snapshots",
        }

    def _matches_keyword(self, row: dict[str, Any], keyword: str) -> bool:
        value = str(row.get("keyword", "")).strip().lower()
        target = keyword.strip().lower()
        return bool(value) and (value == target or value in target or target in value)

    def _normalize(self, row: dict[str, Any]) -> dict[str, Any]:
        def items(value: Any) -> list[str]:
            if isinstance(value, list):
                return [str(item).strip() for item in value if str(item).strip()]
            if isinstance(value, str):
                return [part.strip() for part in value.split(";") if part.strip()]
            return []

        return {
            "keyword": str(row.get("keyword", "")).strip(),
            "competitor_url": str(row.get("competitor_url", "")).strip(),
            "title": str(row.get("title", "")).strip(),
            "meta_description": str(row.get("meta_description", "")).strip(),
            "headings": items(row.get("headings")),
            "word_count": int(str(row.get("word_count", "0")).strip() or 0),
            "content_angle": str(row.get("content_angle", "")).strip(),
            "strengths": items(row.get("strengths")),
            "weaknesses": items(row.get("weaknesses")),
            "missing_topics": items(row.get("missing_topics")),
            "affiliate_elements": items(row.get("affiliate_elements")),
            "last_checked": str(row.get("last_checked", "")).strip(),
        }
