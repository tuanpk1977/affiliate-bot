from __future__ import annotations

import json
import uuid
import webbrowser
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

from .calibration import Phase2Calibration


def _review(count: int, review_reason: str, skip_reason: str) -> dict[str, Any]:
    return {
        "status": "REVIEW" if count else "SKIP",
        "reason": review_reason if count else skip_reason,
        "count": count,
    }


@dataclass
class WeeklyCalibrationPreflight:
    root: Path
    now: datetime | None = None

    def __post_init__(self) -> None:
        self.root = self.root.resolve()
        self.now = (self.now or datetime.now(UTC)).astimezone(UTC)

    def detect(self) -> dict[str, Any]:
        run_id = f"weekly-calibration-{self.now:%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:8]}"
        try:
            calibration = Phase2Calibration(root=self.root, now=self.now).run(mode="dry-run")
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            return {
                "schema_version": "weekly_calibration_preflight_v1",
                "run_id": run_id,
                "timestamp": self.now.isoformat(),
                "mode": "dry-run",
                "status": "ERROR",
                "reason": str(exc),
                "sections": {},
                "blocked": True,
            }
        quality_counts = calibration.get("quality", {}).get("after", {})
        sections = {
            "hubs": _review(
                int(calibration.get("hubs", {}).get("suspicious_entity_count") or 0)
                + int(calibration.get("hubs", {}).get("excluded_count") or 0),
                "Uncertain or excluded hub classifications require operator review.",
                "No uncertain hub classifications were detected.",
            ),
            "aliases": _review(
                int(calibration.get("alias_review_queue", {}).get("count") or 0),
                "Alias conflicts require human resolution; no automatic merge is allowed.",
                "No alias conflict requires review.",
            ),
            "memory": _review(
                int(calibration.get("memory", {}).get("summary", {}).get("shortlist_count") or 0),
                "New editorial-memory candidates or duplication signals require review.",
                "No editorial-memory candidate is waiting for review.",
            ),
            "evergreen": _review(
                len(calibration.get("evergreen", {}).get("items") or []),
                "Evergreen articles need freshness or evidence review.",
                "No evergreen priority is currently detected.",
            ),
            "links": _review(
                int(calibration.get("internal_links", {}).get("after", {}).get("suggestion_count") or 0),
                "Internal-link recommendations exist; they remain recommendation-only.",
                "No internal-link recommendation requires review.",
            ),
            "orphans": _review(
                int(calibration.get("orphans", {}).get("production_true_orphan_unique_count") or 0),
                "Production pages classified as true orphans require review.",
                "No production true orphan was detected.",
            ),
            "quality": _review(
                int(quality_counts.get("BLOCKING") or 0) + int(quality_counts.get("HIGH_PRIORITY") or 0),
                "Blocking or high-priority editorial quality warnings require review.",
                "No blocking or high-priority quality warning was detected.",
            ),
            "gaps": _review(
                int(calibration.get("content_gaps", {}).get("counts", {}).get("STRONG_GAP") or 0),
                "High-confidence content gaps related to known clusters require review.",
                "No strong content gap was detected.",
            ),
        }
        priorities = [
            {"section": key, **value}
            for key, value in sections.items()
            if value["status"] == "REVIEW"
        ]
        if not calibration.get("hubs") and not calibration.get("quality"):
            status, reason, blocked = "BLOCKED", "Required calibration inventory is missing.", True
        else:
            status, reason, blocked = "REVIEW" if priorities else "SKIP", (
                "Open the dashboard with review sections prioritized."
                if priorities else "No calibration section currently requires review."
            ), False
        return {
            "schema_version": "weekly_calibration_preflight_v1",
            "run_id": run_id,
            "timestamp": self.now.isoformat(),
            "mode": "dry-run",
            "status": status,
            "reason": reason,
            "sections": sections,
            "priority_sections": priorities,
            "blocked": blocked,
            "calibration": calibration,
            "weekly_roots_changed": False,
            "recommendation_only": True,
            "production_content_modified": False,
            "queue_modified": False,
            "approval_changed": False,
            "published": False,
        }

    def execute(self, report: dict[str, Any], *, open_dashboard: bool = True) -> dict[str, Any]:
        if report.get("blocked"):
            return {**report, "execution_status": "BLOCKED"}
        payload = dict(report["calibration"])
        payload["mode"] = "write"
        payload["weekly_preflight"] = {
            key: report[key]
            for key in ("run_id", "timestamp", "status", "reason", "sections", "priority_sections")
        }
        engine = Phase2Calibration(root=self.root, now=self.now)
        outputs = engine.write(payload)
        payload["outputs"] = outputs
        report_path = self.root / "data/reports/weekly_preflight/calibration" / f"{report['run_id']}.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        final = {
            **{key: value for key, value in report.items() if key != "calibration"},
            "mode": "write",
            "execution_status": "DASHBOARD_READY",
            "dashboard": outputs["operator_dashboard"],
            "report_path": str(report_path),
            "calibration_outputs": outputs,
        }
        report_path.write_text(json.dumps(final, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        if open_dashboard:
            webbrowser.open(Path(outputs["operator_dashboard"]).resolve().as_uri())
            final["dashboard_opened"] = True
        else:
            final["dashboard_opened"] = False
        return final

    def run(
        self,
        *,
        dry_run: bool = False,
        yes: bool = False,
        verbose: bool = False,
        open_dashboard: bool = True,
        confirm: Callable[[str], str] = input,
    ) -> dict[str, Any]:
        report = self.detect()
        if dry_run or report.get("blocked"):
            return report
        approved = yes or confirm("Mở dashboard với các mục cần ưu tiên? [Y/N] ").strip().casefold() == "y"
        if not approved:
            return {
                **{key: value for key, value in report.items() if key != "calibration"},
                "execution_status": "CANCELLED",
                "reason": "Operator selected N; no data was written and dashboard was not opened.",
            }
        return self.execute(report, open_dashboard=open_dashboard)


def render_console(report: dict[str, Any], *, verbose: bool = False) -> str:
    labels = (
        ("Hub classifications", "hubs"),
        ("Alias conflicts", "aliases"),
        ("Editorial memory", "memory"),
        ("Evergreen priorities", "evergreen"),
        ("Internal links", "links"),
        ("Orphans", "orphans"),
        ("Quality warnings", "quality"),
        ("Strong content gaps", "gaps"),
    )
    lines = ["WEEKLY CALIBRATION PREFLIGHT", ""]
    for label, key in labels:
        row = report.get("sections", {}).get(key, {"status": "ERROR", "count": 0, "reason": "Detection failed."})
        lines.append(f"- {label}: {row['status']} ({row['count']}) - {row['reason']}")
    lines.append(f"- Recommended next action: {report.get('reason', '')}")
    if verbose:
        lines.append(f"- Priority order: {[row['section'] for row in report.get('priority_sections', [])]}")
    return "\n".join(lines)
