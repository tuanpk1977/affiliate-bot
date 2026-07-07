from __future__ import annotations

import csv
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from config import settings


PUBLISH_STATUSES = {"blocked", "ready_for_publish", "approved_for_publish", "published_local", "publish_failed"}


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


class PublishGate:
    def __init__(self, data_dir: Path | None = None, site_output_dir: Path | None = None, config: dict[str, Any] | None = None) -> None:
        self.data_dir = data_dir or settings.data_dir
        self.site_output_dir = site_output_dir or settings.site_output_dir
        self.config = config or {}
        self.queue_path = self.data_dir / "publish_queue.json"
        self.report_json = self.data_dir / "publish_gate_report.json"
        self.report_csv = self.data_dir / "publish_gate_report.csv"
        self.report_md = self.data_dir / "publish_gate_report.md"

    def load_queue(self) -> list[dict[str, Any]]:
        return _read_json(self.queue_path, [])

    def save_queue(self, rows: list[dict[str, Any]]) -> None:
        _write_json(self.queue_path, rows)

    def evaluate(
        self,
        *,
        topic: dict[str, Any],
        title: str,
        description: str,
        url: str,
        html: str,
        research: dict[str, Any],
        review: dict[str, Any],
        human_approval: dict[str, Any],
        internal_links: list[tuple[str, str]],
    ) -> dict[str, Any]:
        if not bool(self.config.get("enabled", False)):
            return self._record(
                {
                    "slug": str(topic.get("slug") or ""),
                    "topic": str(topic.get("topic") or ""),
                    "status": "approved_for_publish",
                    "checked_at": datetime.now(UTC).isoformat(),
                    "failures": [],
                    "research_quality_passed": True,
                    "verified_source_score_passed": True,
                    "knowledge_freshness_passed": True,
                    "ai_review_passed": True,
                    "human_approval_passed": True,
                    "broken_links": [],
                    "duplicate_title_meta": False,
                    "affiliate_disclosure_present": True,
                    "minimum_business_score_passed": True,
                    "minimum_readability_score_passed": True,
                    "business_score": float(review.get("business_value", 0)),
                    "readability_score": float(review.get("readability", 0)),
                    "publish_ready": True,
                    "url": url,
                    "title": title,
                    "description": description,
                }
            )

        research_quality = research.get("quality") if isinstance(research.get("quality"), dict) else {}
        research_gate = research.get("quality_gate") if isinstance(research.get("quality_gate"), dict) else {}
        checked_at = datetime.now(UTC).isoformat()

        research_quality_passed = bool(research_gate.get("passed", False))
        verified_source_score_passed = float(research_quality.get("total_verified_source_score", 0)) >= float(self.config.get("minimum_verified_source_score", 35))
        knowledge_freshness_passed = float(research_quality.get("source_confidence", 0)) >= float(self.config.get("minimum_knowledge_freshness", 20))
        ai_review_passed = str(review.get("status", "")) in {"ai_review_passed", "needs_human_review", "human_approved"}
        human_required = bool(review.get("requires_human_approval", False)) or bool(self.config.get("require_human_approval", False))
        human_approval_passed = (not human_required) or str(human_approval.get("status", "")) == "human_approved"

        broken_links = [href for href, _ in internal_links if not self._link_exists(href)]
        duplicate_title_meta = self._duplicate_title_or_description(title, description, current_slug=str(topic.get("slug") or ""))
        affiliate_disclosure_present = "affiliate disclosure" in html.lower() and "commission" in html.lower()
        minimum_business_score_passed = float(review.get("business_value", 0)) >= float(self.config.get("minimum_business_score", 35))
        minimum_readability_score_passed = float(review.get("readability", 0)) >= float(self.config.get("minimum_readability_score", 30))

        failures: list[str] = []
        if not research_quality_passed:
            failures.append("research quality gate failed")
        if not verified_source_score_passed:
            failures.append("verified source score failed")
        if not knowledge_freshness_passed:
            failures.append("knowledge freshness failed")
        if not ai_review_passed:
            failures.append("AI review failed")
        if not human_approval_passed:
            failures.append("human approval missing")
        if broken_links:
            failures.append("broken links detected")
        if duplicate_title_meta:
            failures.append("duplicate title/meta detected")
        if not affiliate_disclosure_present:
            failures.append("affiliate disclosure missing")
        if not minimum_business_score_passed:
            failures.append("business score below threshold")
        if not minimum_readability_score_passed:
            failures.append("readability score below threshold")

        status = "approved_for_publish" if not failures else "blocked"
        return self._record(
            {
                "slug": str(topic.get("slug") or ""),
                "topic": str(topic.get("topic") or ""),
                "status": status,
                "checked_at": checked_at,
                "failures": failures,
                "research_quality_passed": research_quality_passed,
                "verified_source_score_passed": verified_source_score_passed,
                "knowledge_freshness_passed": knowledge_freshness_passed,
                "ai_review_passed": ai_review_passed,
                "human_approval_passed": human_approval_passed,
                "broken_links": broken_links,
                "duplicate_title_meta": duplicate_title_meta,
                "affiliate_disclosure_present": affiliate_disclosure_present,
                "minimum_business_score_passed": minimum_business_score_passed,
                "minimum_readability_score_passed": minimum_readability_score_passed,
                "business_score": float(review.get("business_value", 0)),
                "readability_score": float(review.get("readability", 0)),
                "publish_ready": not failures,
                "url": url,
                "title": title,
                "description": description,
            }
        )

    def mark_published_local(self, slug: str, *, url: str, article_file: Path, site_file: Path) -> dict[str, Any] | None:
        rows = self.load_queue()
        for row in rows:
            if str(row.get("slug", "")) != slug:
                continue
            row["status"] = "published_local" if article_file.exists() and site_file.exists() else "publish_failed"
            row["published_at"] = datetime.now(UTC).isoformat()
            row["url"] = url
            self.save_queue(rows)
            self._write_report(rows)
            return row
        return None

    def _record(self, result: dict[str, Any]) -> dict[str, Any]:
        rows = self.load_queue()
        replaced = False
        for index, row in enumerate(rows):
            if str(row.get("slug", "")) == str(result.get("slug", "")):
                rows[index] = result
                replaced = True
                break
        if not replaced:
            rows.append(result)
        self.save_queue(rows)
        self._write_report(rows)
        return result

    def _write_report(self, rows: list[dict[str, Any]]) -> None:
        summary = {
            "items": len(rows),
            "blocked": sum(1 for row in rows if str(row.get("status", "")) == "blocked"),
            "ready_for_publish": sum(1 for row in rows if str(row.get("status", "")) == "ready_for_publish"),
            "approved_for_publish": sum(1 for row in rows if str(row.get("status", "")) == "approved_for_publish"),
            "published_local": sum(1 for row in rows if str(row.get("status", "")) == "published_local"),
            "publish_failed": sum(1 for row in rows if str(row.get("status", "")) == "publish_failed"),
        }
        _write_json(self.report_json, {"summary": summary, "items": rows})
        _write_csv(self.report_csv, rows)
        _write_md(
            self.report_md,
            [
                "# Publish Gate Report",
                "",
                f"- Items: {summary['items']}",
                f"- Blocked: {summary['blocked']}",
                f"- Approved For Publish: {summary['approved_for_publish']}",
                f"- Published Local: {summary['published_local']}",
                f"- Publish Failed: {summary['publish_failed']}",
            ],
        )

    def _link_exists(self, href: str) -> bool:
        clean = "/" + href.strip("/")
        if clean == "/":
            target = self.site_output_dir / "index.html"
        else:
            target = self.site_output_dir / clean.strip("/") / "index.html"
        return target.exists()

    def _duplicate_title_or_description(self, title: str, description: str, *, current_slug: str) -> bool:
        rows = self.load_queue()
        for row in rows:
            if str(row.get("slug", "")) == current_slug:
                continue
            if str(row.get("title", "")).strip().lower() == title.strip().lower():
                return True
            if str(row.get("description", "")).strip().lower() == description.strip().lower():
                return True
        return False
