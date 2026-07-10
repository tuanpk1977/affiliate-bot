from __future__ import annotations

import csv
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from config import settings


PUBLISH_STATUSES = {
    "blocked",
    "needs_human_review",
    "ready_for_publish",
    "approved_for_publish",
    "published_local",
    "publish_failed",
}

REVIEW_STATES = {"not_run", "passed", "warning", "failed", "error"}

WARNING_LEGACY_FAILURES = {
    "verified source score failed",
    "verified source score too low",
    "knowledge freshness failed",
    "ai review failed",
    "business score below threshold",
    "readability score below threshold",
    "internal links missing",
    "source quality below threshold",
    "publish readiness below threshold",
}

HUMAN_APPROVAL_REASONS = {"human approval missing", "waiting for editor approval"}


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


def _unique_append(items: list[str], value: str) -> None:
    clean = value.strip()
    if not clean:
        return
    normalized = clean.lower()
    if normalized not in {item.lower() for item in items}:
        items.append(clean)


def _coerce_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _score_band(score: float) -> str:
    if score >= 80:
        return "high_confidence"
    if score >= 65:
        return "human_review_required"
    if score >= 50:
        return "needs_revision"
    return "blocked"


def _legacy_failure_severity(reason: str) -> str:
    normalized = reason.strip().lower()
    if normalized in HUMAN_APPROVAL_REASONS:
        return "pending"
    if normalized in WARNING_LEGACY_FAILURES:
        return "warning"
    return "block"


class PublishGate:
    def __init__(self, data_dir: Path | None = None, site_output_dir: Path | None = None, config: dict[str, Any] | None = None) -> None:
        self.data_dir = data_dir or settings.data_dir
        self.site_output_dir = site_output_dir or settings.site_output_dir
        self.config = config or {}
        self.queue_path = self.data_dir / "publish_queue.json"
        self.report_json = self.data_dir / "publish_gate_report.json"
        self.report_csv = self.data_dir / "publish_gate_report.csv"
        self.report_md = self.data_dir / "publish_gate_report.md"

    @staticmethod
    def normalize_existing_row(row: dict[str, Any]) -> dict[str, Any]:
        """Return a severity-aware view of old and new publish queue rows."""
        hard_blockers = [str(item).strip() for item in list(row.get("hard_blockers") or []) if str(item).strip()]
        warnings = [str(item).strip() for item in list(row.get("warnings") or []) if str(item).strip()]
        pending_reviews = [str(item).strip() for item in list(row.get("pending_reviews") or []) if str(item).strip()]
        legacy_failures = [str(item).strip() for item in list(row.get("failures") or []) if str(item).strip()]
        if not hard_blockers and not warnings and not pending_reviews and legacy_failures:
            for reason in legacy_failures:
                severity = _legacy_failure_severity(reason)
                if severity == "pending":
                    _unique_append(pending_reviews, reason)
                elif severity == "warning":
                    _unique_append(warnings, reason)
                else:
                    _unique_append(hard_blockers, reason)
        human_passed = bool(row.get("human_approval_passed", False)) or str(row.get("status") or "") in {"approved_for_publish", "published_local", "published"}
        status = str(row.get("status") or "missing")
        if status == "published_local":
            final_gate = "Published"
            normalized_status = "published_local"
        elif hard_blockers:
            final_gate = "Publish Blocked"
            normalized_status = "blocked"
        elif human_passed:
            final_gate = "Ready for Publish"
            normalized_status = "approved_for_publish"
        else:
            final_gate = "Human Approval Required"
            normalized_status = "needs_human_review"
            if not any(reason.lower() in HUMAN_APPROVAL_REASONS for reason in pending_reviews):
                _unique_append(pending_reviews, "human approval missing")
        return {
            "hard_blockers": hard_blockers,
            "warnings": warnings,
            "pending_reviews": pending_reviews,
            "final_gate": final_gate,
            "normalized_status": normalized_status,
            "publish_ready": normalized_status == "approved_for_publish",
        }

    def load_queue(self) -> list[dict[str, Any]]:
        return _read_json(self.queue_path, [])

    def save_queue(self, rows: list[dict[str, Any]]) -> None:
        _write_json(self.queue_path, rows)

    def refresh_reports(self) -> None:
        self._write_report(self.load_queue())

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

        hard_blockers: list[str] = []
        warnings: list[str] = []
        pending_reviews: list[str] = []

        bands = self.config.get("scoring_bands") if isinstance(self.config.get("scoring_bands"), dict) else {}
        high_confidence_min = _coerce_float(bands.get("high_confidence_min"), 80)
        human_review_min = _coerce_float(bands.get("human_review_min"), 65)
        needs_revision_min = _coerce_float(bands.get("needs_revision_min"), 50)

        verified_score = _coerce_float(research_quality.get("total_verified_source_score"), 0)
        freshness_score = _coerce_float(research_quality.get("source_confidence"), 0)
        business_score = _coerce_float(review.get("business_value"), 0)
        readability_score = _coerce_float(review.get("readability"), 0)
        publish_readiness_score = _coerce_float(review.get("publish_readiness"), 0)
        total_score = publish_readiness_score or round((verified_score + freshness_score + business_score + readability_score) / 4, 2)
        score_band = _score_band(total_score)

        research_quality_passed = bool(research_gate.get("passed", False))
        verified_source_score_passed = verified_score >= float(self.config.get("minimum_verified_source_score", 35))
        knowledge_freshness_passed = freshness_score >= float(self.config.get("minimum_knowledge_freshness", 20))
        review_status = str(review.get("status", "")).strip()
        ai_review_passed = review_status in {"ai_review_passed", "needs_human_review", "human_approved"}
        human_required = bool(review.get("requires_human_approval", False)) or bool(self.config.get("require_human_approval", False))
        human_approval_passed = (not human_required) or str(human_approval.get("status", "")) == "human_approved"

        broken_links = [href for href, _ in internal_links if not self._link_exists(href)]
        duplicate_title_meta = self._duplicate_title_or_description(title, description, current_slug=str(topic.get("slug") or ""))
        affiliate_disclosure_present = "affiliate disclosure" in html.lower() and "commission" in html.lower()
        minimum_business_score_passed = business_score >= float(self.config.get("minimum_business_score", 35))
        minimum_readability_score_passed = readability_score >= float(self.config.get("minimum_readability_score", 30))

        title_present = bool(title.strip())
        description_present = bool(description.strip())
        canonical_present = bool(re.search(r"<link\b[^>]*rel=['\"]canonical['\"]", html, flags=re.I)) or bool(url.strip())
        meta_present = bool(re.search(r"<meta\b[^>]*name=['\"]description['\"]", html, flags=re.I)) or description_present
        forbidden_marker_leak = any(marker in html for marker in ("{{", "}}", "Research package snapshot", "Affiliate placeholder fields"))
        english_page_has_vietnamese_labels = bool(re.search(r"<html\b[^>]*lang=['\"]en", html, flags=re.I)) and any(
            label in html for label in ("Đăng", "Duyệt", "Chưa", "Bài viết", "Nguồn")
        )

        if not html.strip():
            _unique_append(hard_blockers, "missing article output")
        if not title_present or not description_present or not meta_present or not canonical_present:
            _unique_append(hard_blockers, "missing title/meta/canonical")
        if forbidden_marker_leak:
            _unique_append(hard_blockers, "public workflow marker leakage")
        if english_page_has_vietnamese_labels:
            _unique_append(hard_blockers, "English page contains Vietnamese public labels")
        if research_quality and verified_score <= 0 and float(self.config.get("minimum_verified_source_score", 35)) > 0:
            _unique_append(hard_blockers, "zero usable sources")
        if score_band == "blocked" and review:
            _unique_append(hard_blockers, "AI review score below minimum")
        if not research_quality_passed:
            _unique_append(warnings, "research quality gate needs review")
        if not verified_source_score_passed:
            _unique_append(warnings, "verified source score failed")
        if not knowledge_freshness_passed:
            _unique_append(warnings, "knowledge freshness failed")
        if not ai_review_passed:
            if not review:
                _unique_append(pending_reviews, "AI review not_run")
            elif review_status in {"error", "review_error"}:
                _unique_append(hard_blockers, "AI review error")
            elif total_score >= needs_revision_min:
                _unique_append(warnings, "AI review failed")
            else:
                _unique_append(hard_blockers, "AI review failed")
        if not human_approval_passed:
            _unique_append(pending_reviews, "human approval missing")
        if broken_links:
            _unique_append(warnings, "broken links detected")
        if duplicate_title_meta:
            _unique_append(warnings, "duplicate title/meta detected")
        if not affiliate_disclosure_present:
            _unique_append(hard_blockers, "affiliate disclosure missing")
        if not minimum_business_score_passed:
            _unique_append(warnings, "business score below threshold")
        if not minimum_readability_score_passed:
            _unique_append(warnings, "readability score below threshold")

        if total_score < high_confidence_min and total_score >= human_review_min:
            _unique_append(warnings, "AI quality below high-confidence target")
        elif total_score < human_review_min and total_score >= needs_revision_min:
            _unique_append(warnings, "AI quality review required")

        review_states = {
            "ai_review": self._review_state(review, passed=ai_review_passed, warning=bool(warnings), failed=any("AI review" in item for item in hard_blockers)),
            "source_review": "failed" if research_quality and verified_score <= 0 and float(self.config.get("minimum_verified_source_score", 35)) > 0 else ("warning" if not verified_source_score_passed else "passed"),
            "freshness_review": "not_run" if "source_confidence" not in research_quality else ("warning" if not knowledge_freshness_passed else "passed"),
        }
        if not review:
            review_states["ai_review"] = "not_run"
        if not research_quality:
            review_states["source_review"] = "not_run"
            review_states["freshness_review"] = "not_run"
            _unique_append(pending_reviews, "source review not_run")
            _unique_append(pending_reviews, "freshness review not_run")

        status = "blocked" if hard_blockers else ("approved_for_publish" if human_approval_passed else "needs_human_review")
        failures = list(hard_blockers)
        return self._record(
            {
                "slug": str(topic.get("slug") or ""),
                "topic": str(topic.get("topic") or ""),
                "status": status,
                "checked_at": checked_at,
                "failures": failures,
                "hard_blockers": hard_blockers,
                "warnings": warnings,
                "pending_reviews": pending_reviews,
                "review_states": review_states,
                "severity_counts": {
                    "BLOCK": len(hard_blockers),
                    "WARNING": len(warnings),
                    "HUMAN_REVIEW_REQUIRED": len(pending_reviews),
                },
                "total_score": total_score,
                "score_band": score_band,
                "final_gate": "Publish Blocked" if hard_blockers else ("Ready for Publish" if human_approval_passed else "Human Approval Required"),
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
                "business_score": business_score,
                "readability_score": readability_score,
                "verified_source_score": verified_score,
                "knowledge_freshness_score": freshness_score,
                "publish_ready": status == "approved_for_publish",
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
            "needs_human_review": sum(1 for row in rows if str(row.get("status", "")) == "needs_human_review"),
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
                f"- Needs Human Review: {summary['needs_human_review']}",
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

    def _review_state(self, review: dict[str, Any], *, passed: bool, warning: bool, failed: bool) -> str:
        status = str(review.get("status") or "").strip().lower()
        if not review or not status:
            return "not_run"
        if status in {"error", "review_error"}:
            return "error"
        if failed:
            return "failed"
        if warning or status == "needs_revision":
            return "warning"
        if passed:
            return "passed"
        return "failed"
