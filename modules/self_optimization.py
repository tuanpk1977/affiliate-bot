from __future__ import annotations

import csv
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from config import settings
from modules.content_analytics import ContentAnalytics


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write_json(path: Path, payload: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return path
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        for row in rows:
            writer.writerow({key: json.dumps(value, ensure_ascii=False) if isinstance(value, (list, dict)) else value for key, value in row.items()})
    return path


def _write_md(path: Path, lines: list[str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return path


class SelfOptimization:
    def __init__(self, data_dir: Path | None = None, config: dict[str, Any] | None = None, analytics: ContentAnalytics | None = None) -> None:
        self.data_dir = data_dir or settings.data_dir
        self.config = config or {}
        self.analytics = analytics or ContentAnalytics(self.data_dir, config=self.config)
        self.report_json = self.data_dir / "optimization_report.json"
        self.report_csv = self.data_dir / "optimization_report.csv"
        self.report_md = self.data_dir / "optimization_report.md"

    def generate_report(self) -> dict[str, Any]:
        performance = self.analytics.build_performance_report()
        evergreen = _read_json(self.data_dir / "evergreen_report.json", [])
        opportunities = _read_json(self.data_dir / "affiliate_opportunities.json", [])
        gaps = _read_json(self.data_dir / "content_gap_report.json", [])

        actions: list[dict[str, Any]] = []
        for row in performance:
            slug = str(row.get("slug", ""))
            action = str(row.get("next_recommended_action", "hold / do nothing"))
            reason_parts = [f"ROI {row.get('topic_roi_score', 0)}", f"freshness decay {row.get('freshness_decay', 0)}"]
            if any(str(item.get("slug", "")) == slug and str(item.get("status", "")) in {"Needs Update", "Outdated", "Deprecated"} for item in evergreen if isinstance(item, dict)):
                action = "update old article"
                reason_parts.append("evergreen manager flagged article")
            if any(str(item.get("slug", "")) == slug and int(item.get("broken_links", 0)) > 0 for item in evergreen if isinstance(item, dict)):
                action = "add internal links"
                reason_parts.append("broken links found")
            if any(str(item.get("slug", "")) == slug and str(item.get("monetization_priority", "")) == "High" for item in opportunities if isinstance(item, dict)):
                reason_parts.append("affiliate opportunity is high")
            if any(str(item.get("slug", "")) == slug for item in gaps if isinstance(item, dict)):
                reason_parts.append("content gap exists")
            actions.append(
                {
                    "slug": slug,
                    "topic": str(row.get("topic", "")),
                    "topic_roi_score": float(row.get("topic_roi_score", 0)),
                    "update_priority": str(row.get("update_priority", "low")),
                    "next_recommended_action": action,
                    "reason": "; ".join(reason_parts),
                }
            )

        _write_json(self.report_json, {"actions": actions})
        _write_csv(self.report_csv, actions)
        _write_md(
            self.report_md,
            ["# Self Optimization Report", "", *[f"- `{row['slug']}`: {row['next_recommended_action']} ({row['update_priority']})" for row in actions[:20]]],
        )
        return {"actions": actions, "report_json": str(self.report_json)}

    def reweight_candidates(self, candidates: list[Any]) -> list[Any]:
        if not bool(self.config.get("enabled", True)):
            return candidates
        adjustments = self.analytics.score_adjustments()
        weighted: list[Any] = []
        for candidate in candidates:
            slug = str(getattr(candidate, "slug", ""))
            adjustment = adjustments.get(slug, {})
            if not adjustment:
                weighted.append(candidate)
                continue
            payload = asdict(candidate)
            payload["score"] = round(float(payload.get("score", 0)) + float(adjustment.get("score_delta", 0)), 2)
            reasoning = list(payload.get("planning_reasoning", []))
            reasoning.append(f"Analytics feedback: {adjustment.get('next_recommended_action', 'hold / do nothing')} (ROI {adjustment.get('topic_roi_score', 0)}).")
            payload["planning_reasoning"] = reasoning[:8]
            weighted.append(type(candidate)(**payload))
        return weighted
