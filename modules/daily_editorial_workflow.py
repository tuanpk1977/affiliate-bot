from __future__ import annotations

import html
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.parse
import urllib.error
import urllib.request
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable

from build_site import incremental_build
from config import settings
from modules.affiliate_links import load_affiliate_links
from modules.ai_trend_discovery import TrendDiscoveryEngine, classify_content_type, classify_search_intent, load_affiliate_brands, slugify
from modules.content_growth_pipeline import generate_production_article_draft_from_package, get_research_platform, is_near_duplicate
from modules.editorial_operations_console import EditorialOperationsConsole
from modules.publishing_indexing import normalize_public_url, validate_page


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


def _score_search_intent(intent: str) -> int:
    normalized = intent.strip().lower()
    if normalized == "commercial research":
        return 90
    if normalized == "commercial investigation":
        return 88
    if normalized == "comparison":
        return 86
    if normalized == "informational":
        return 70
    return 64


def _score_product_availability(topic: str, brands: set[str]) -> tuple[int, list[str]]:
    lower = topic.lower()
    matched = sorted({brand for brand in brands if brand and brand in lower})
    if matched:
        return min(100, 65 + len(matched) * 15), matched[:5]
    if any(term in lower for term in ("software", "tool", "tools", "platform", "assistant", "builder", "review", "pricing", "alternatives", "comparison")):
        return 58, []
    return 40, []


def _score_topic_total(item: dict[str, Any]) -> float:
    search_intent_score = float(item["search_intent_score"])
    affiliate_score = float(item["affiliate_monetization_score"])
    competition_difficulty = float(item["competition_difficulty_score"])
    product_availability = float(item["product_availability_score"])
    freshness = float(item["content_freshness_score"])
    competition_opportunity = 100 - competition_difficulty
    return round(
        search_intent_score * 0.22
        + affiliate_score * 0.24
        + competition_opportunity * 0.18
        + product_availability * 0.20
        + freshness * 0.16,
        1,
    )


def _normalize_space(text: str) -> str:
    return " ".join(text.split())


def _normalize_duplicate_key(text: str) -> str:
    return slugify(_normalize_space(text).lower())


def _clamp_score(value: float) -> float:
    return round(max(0.0, value), 1)


ADVANCED_WEEKDAY_PATTERNS: dict[int, tuple[str, str]] = {
    1: ("pricing", "{topic} pricing"),
    2: ("alternatives", "{topic} alternatives"),
    3: ("comparison", "{topic} comparison"),
    4: ("tutorial", "how to use {topic}"),
    5: ("best_for_use_case", "best {topic} for small business"),
    6: ("review", "{topic} review 2026"),
}


class DailyEditorialWorkflow:
    def __init__(
        self,
        *,
        root: Path | None = None,
        data_dir: Path | None = None,
        site_output_dir: Path | None = None,
    ) -> None:
        self.root = root or settings.base_dir
        self.data_dir = data_dir or settings.data_dir
        self.site_output_dir = site_output_dir or settings.site_output_dir
        self.queue_root = self.data_dir / "editorial_queue"
        self.review_root = self.site_output_dir / "review"
        self.upload_root = self.root / "upload"
        self.console = EditorialOperationsConsole(
            data_dir=self.data_dir,
            site_output_dir=self.site_output_dir,
            published_dir=self.data_dir / "published_static_pages",
        )
        config_path = self.root / "config" / "editorial_system.json"
        self.editorial_config = _read_json(config_path, {}) or dict(getattr(settings, "editorial_config", {}) or {})
        self.progress_reporter: Callable[[str], None] | None = None
        self.current_progress_message = ""
        self.command_timeout_seconds = 600
        self.post_push_live_waits = (15, 45, 120)
        self.sleep_fn: Callable[[float], None] = time.sleep

    def set_progress_reporter(self, reporter: Callable[[str], None] | None) -> None:
        self.progress_reporter = reporter

    def _report_progress(self, message: str) -> None:
        self.current_progress_message = message
        if self.progress_reporter is not None:
            self.progress_reporter(message)

    def trend(self, *, count: int = 10, mode: str = "standard", batch_date: str | None = None) -> dict[str, Any]:
        target_date = batch_date or date.today().isoformat()
        weekly_batch = self._load_or_create_weekly_batch(batch_date=target_date, count=count)
        selected = self._build_daily_topics_from_weekly_batch(
            weekly_topics=weekly_batch.get("topics", []),
            batch_date=target_date,
            mode=mode,
        )[:count]
        payload = {
            "generated_at": datetime.now(UTC).isoformat(),
            "date": target_date,
            "week_start": weekly_batch["week_start"],
            "week_end": weekly_batch["week_end"],
            "mode": mode,
            "count": len(selected),
            "source_status": weekly_batch.get("source_status", {}),
            "duplicate_warning_count": int(weekly_batch.get("duplicate_warning_count", 0)),
            "duplicate_warning_slugs": list(weekly_batch.get("duplicate_warning_slugs", []) or []),
            "topics": selected,
        }
        _write_json(self._queue_dir(target_date) / "topics.json", payload)
        return payload

    def morning_run(self, *, count: int = 10, mode: str = "standard", batch_date: str | None = None) -> dict[str, Any]:
        target_date = batch_date or date.today().isoformat()
        trend_payload = self.trend(count=count, mode=mode, batch_date=target_date)
        draft_payload = self.draft(batch_date=target_date)
        upload_summary = self._sync_upload_batch(batch_date=target_date)
        master_dashboard = self._build_upload_master_dashboard()
        return {
            "date": target_date,
            "mode": mode,
            "count": int(trend_payload.get("count", 0)),
            "trend": trend_payload,
            "draft": draft_payload,
            "dashboard_file": str(self.review_root / target_date / "index.html"),
            "operator_console": str(self.console.console_html),
            "upload_dir": str(self.upload_root / target_date),
            "master_dashboard": str(master_dashboard),
            "upload_summary": upload_summary,
        }

    def draft(self, *, batch_date: str) -> dict[str, Any]:
        payload = self._load_queue(batch_date)
        topics = payload.get("topics", [])
        drafted = 0
        blocked = 0
        results: list[dict[str, Any]] = []
        for item in topics:
            slug = str(item.get("slug") or "")
            topic_record = {
                "topic": str(item.get("keyword") or slug.replace("-", " ")),
                "slug": slug,
                "title": str(item.get("keyword") or slug.replace("-", " ")),
                "content_type": str(item.get("content_type") or classify_content_type(str(item.get("keyword") or ""))),
                "search_intent": str(item.get("search_intent") or classify_search_intent(str(item.get("keyword") or ""))),
                "related_keywords": list(item.get("related_keywords") or []),
                "suggested_internal_links": list(item.get("suggested_internal_links") or []),
                "suggested_article_angle": str(item.get("suggested_article_angle") or ""),
            }
            try:
                platform = get_research_platform()
                package = platform.build_research_package(topic_record)
                allow_override = bool(getattr(settings, "editorial_research_config", {}).get("allow_generation_override", False))
                gate = platform.evaluate_quality_gate(package, topic=topic_record, allow_override=allow_override)
                item["research_quality_gate"] = {
                    "passed": gate.passed,
                    "score": gate.score,
                    "threshold": gate.threshold,
                    "override_used": gate.override_used,
                    "status": gate.status,
                }
                if not gate.passed:
                    item["status"] = "needs_enrichment"
                    item["draft_dir"] = ""
                    item["review_preview"] = ""
                    item["error"] = f"Research quality gate blocked draft generation: {gate.score} < {gate.threshold}"
                    blocked += 1
                    results.append({"slug": slug, "status": item["status"], "error": item["error"]})
                    continue
                result = generate_production_article_draft_from_package(slug)
                preview_path = self._copy_review_preview(slug=slug, batch_date=batch_date)
                metadata = _read_json(Path(result["metadata_file"]), {})
                item["status"] = "drafted"
                item["draft_dir"] = result["draft_dir"]
                item["draft_file"] = str(Path(result["draft_dir"]) / "index.html")
                item["review_preview"] = str(preview_path)
                item["metadata_file"] = result["metadata_file"]
                item["article_title"] = str(metadata.get("title") or item.get("keyword") or slug)
                item["review_status"] = str((metadata.get("review") or {}).get("status") or "draft")
                item["human_approval_status"] = str((metadata.get("human_approval") or {}).get("status") or "missing")
                item["publish_gate_status"] = str((metadata.get("publish_gate") or {}).get("status") or "missing")
                item["error"] = ""
                drafted += 1
                results.append({"slug": slug, "status": item["status"], "preview": str(preview_path)})
            except Exception as exc:
                item["status"] = "draft_failed"
                item["error"] = str(exc)
                blocked += 1
                results.append({"slug": slug, "status": item["status"], "error": str(exc)})
        payload["topics"] = topics
        payload["drafted_at"] = datetime.now(UTC).isoformat()
        _write_json(self._queue_dir(batch_date) / "topics.json", payload)
        dashboard = self.build_review_dashboard(batch_date=batch_date)
        upload_summary = self._sync_upload_batch(batch_date=batch_date)
        master_dashboard = self._build_upload_master_dashboard()
        return {
            "date": batch_date,
            "drafted": drafted,
            "blocked": blocked,
            "topics": results,
            "dashboard": dashboard,
            "upload_dir": str(self.upload_root / batch_date),
            "master_dashboard": str(master_dashboard),
            "upload_summary": upload_summary,
        }

    def request_custom_topic(
        self,
        *,
        topic_name: str,
        official_url: str = "",
        affiliate_url: str = "",
        pricing_url: str = "",
        category: str = "",
        intent: str = "commercial research",
        count: int = 1,
        batch_date: str | None = None,
    ) -> dict[str, Any]:
        target_date = batch_date or date.today().isoformat()
        requests = self._build_custom_topic_requests(topic_name=topic_name, category=category, intent=intent, count=count)
        queue_entries: list[dict[str, Any]] = []
        results: list[dict[str, Any]] = []
        history = _read_json(self.data_dir / "custom_topic_history.json", [])
        generated_at = datetime.now(UTC).isoformat()
        for index, request in enumerate(requests, start=1):
            result = self.console.request_custom_topic(
                request["topic"],
                category=category,
                intent=intent,
                source_url=official_url,
                official_url=official_url,
                affiliate_url=affiliate_url,
                pricing_url=pricing_url,
                source_type="custom_topic",
                cluster_article_number=index,
                cluster_article_total=len(requests),
                extra_context={
                    "requested_batch_date": target_date,
                    "custom_topic_root": topic_name.strip(),
                },
            )
            slug = str(result.get("slug") or "")
            queue_entry = self._queue_entry_from_request_result(
                keyword=request["topic"],
                slug=slug,
                result=result,
                batch_date=target_date,
                category=category,
                intent=intent,
                content_type=request["content_type"],
                source_type="custom_topic",
                partner_name="",
                official_url=official_url,
                affiliate_url=affiliate_url,
                pricing_url=pricing_url,
                cluster_article_number=index,
                cluster_article_total=len(requests),
                suggested_article_angle=request["suggested_article_angle"],
            )
            queue_entries.append(queue_entry)
            results.append(result)
            history.append(
                {
                    "created_at": generated_at,
                    "batch_date": target_date,
                    "topic": request["topic"],
                    "slug": slug,
                    "official_url": official_url.strip(),
                    "affiliate_url": affiliate_url.strip(),
                    "pricing_url": pricing_url.strip(),
                    "category": category.strip(),
                    "intent": intent.strip(),
                    "count": len(requests),
                    "status": queue_entry["status"],
                }
            )
        _write_json(self.data_dir / "custom_topic_history.json", history)
        self._upsert_topics_into_batch(batch_date=target_date, topics=queue_entries, mode="custom")
        upload_summary = self._sync_upload_batch(batch_date=target_date)
        master_dashboard = self._build_upload_master_dashboard()
        return {
            "date": target_date,
            "requested_topic": topic_name.strip(),
            "count": len(results),
            "results": results,
            "dashboard_file": str(self.review_root / target_date / "index.html"),
            "operator_console": str(self.console.console_html),
            "upload_dir": str(self.upload_root / target_date),
            "master_dashboard": str(master_dashboard),
            "upload_summary": upload_summary,
            "history_file": str(self.data_dir / "custom_topic_history.json"),
        }

    def partner_intake(
        self,
        *,
        partner_name: str,
        official_url: str = "",
        affiliate_url: str = "",
        pricing_url: str = "",
        contact_note: str = "",
        commission_note: str = "",
        payout_note: str = "",
        count: int = 8,
        batch_date: str | None = None,
    ) -> dict[str, Any]:
        target_date = batch_date or date.today().isoformat()
        partner_slug = slugify(partner_name.strip())
        partner_dir = self.data_dir / "partners" / partner_slug
        partner_profile = {
            "name": partner_name.strip(),
            "slug": partner_slug,
            "official_url": official_url.strip(),
            "affiliate_url": affiliate_url.strip(),
            "pricing_url": pricing_url.strip(),
            "contact_note": contact_note.strip(),
            "commission_note": commission_note.strip(),
            "payout_note": payout_note.strip(),
            "updated_at": datetime.now(UTC).isoformat(),
        }
        _write_json(partner_dir / "partner.json", partner_profile)
        history = _read_json(self.data_dir / "partner_intake_history.json", [])
        history.append({**partner_profile, "batch_date": target_date, "count": int(count or 8)})
        _write_json(self.data_dir / "partner_intake_history.json", history)
        self._upsert_affiliate_partner_record(partner_profile)

        cluster_topics = self._build_partner_cluster_topics(partner_name=partner_name.strip(), count=count)
        queue_entries: list[dict[str, Any]] = []
        results: list[dict[str, Any]] = []
        for index, topic in enumerate(cluster_topics, start=1):
            result = self.console.request_custom_topic(
                topic["topic"],
                category=topic.get("category", "Affiliate Partner"),
                intent="commercial research",
                source_url=official_url,
                official_url=official_url,
                affiliate_url=affiliate_url,
                pricing_url=pricing_url,
                source_type="affiliate_partner",
                partner_name=partner_name.strip(),
                cluster_article_number=index,
                cluster_article_total=len(cluster_topics),
                extra_context={
                    "requested_batch_date": target_date,
                    "partner_slug": partner_slug,
                    "contact_note": contact_note.strip(),
                    "commission_note": commission_note.strip(),
                    "payout_note": payout_note.strip(),
                },
            )
            slug = str(result.get("slug") or "")
            queue_entries.append(
                self._queue_entry_from_request_result(
                    keyword=topic["topic"],
                    slug=slug,
                    result=result,
                    batch_date=target_date,
                    category=topic.get("category", "Affiliate Partner"),
                    intent="commercial research",
                    content_type=topic["content_type"],
                    source_type="affiliate_partner",
                    partner_name=partner_name.strip(),
                    official_url=official_url,
                    affiliate_url=affiliate_url,
                    pricing_url=pricing_url,
                    cluster_article_number=index,
                    cluster_article_total=len(cluster_topics),
                    suggested_article_angle=topic["suggested_article_angle"],
                )
            )
            results.append(result)
        self._upsert_topics_into_batch(batch_date=target_date, topics=queue_entries, mode="partner")
        upload_summary = self._sync_upload_batch(batch_date=target_date)
        if partner_dir.exists():
            self._copy_tree_contents(partner_dir, self.upload_root / target_date / partner_slug / "partner")
        for entry in queue_entries:
            slug = str(entry.get("slug") or "")
            if not slug:
                continue
            draft_dir = self.data_dir / "production_article_drafts" / slug
            upload_draft_dir = self.upload_root / target_date / partner_slug / slug
            for name in ("index.html", "article.md", "metadata.json", "review_summary.md", "publish_readiness_report.md"):
                source = draft_dir / name
                if source.exists():
                    self._copy_file(source, upload_draft_dir / name)
        master_dashboard = self._build_upload_master_dashboard()
        return {
            "date": target_date,
            "partner_name": partner_name.strip(),
            "partner_slug": partner_slug,
            "count": len(results),
            "results": results,
            "partner_profile": str(partner_dir / "partner.json"),
            "history_file": str(self.data_dir / "partner_intake_history.json"),
            "dashboard_file": str(self.review_root / target_date / "index.html"),
            "operator_console": str(self.console.console_html),
            "upload_dir": str(self.upload_root / target_date / partner_slug),
            "master_dashboard": str(master_dashboard),
            "upload_summary": upload_summary,
        }

    def approve(self, *, slug: str, batch_date: str, approver: str = "editor") -> dict[str, Any]:
        result = self.console.approve_slug(slug, approver=approver)
        self._update_batch_status(batch_date=batch_date, slug=slug, status="approved", extra={"approved_by": approver})
        dashboard = self.build_review_dashboard(batch_date=batch_date)
        return {"date": batch_date, "slug": slug, "result": result, "dashboard": dashboard}

    def reject(self, *, slug: str, batch_date: str, reason: str, approver: str = "editor") -> dict[str, Any]:
        result = self.console.reject_slug(slug, reason=reason, approver=approver)
        self._update_batch_status(batch_date=batch_date, slug=slug, status="rejected", extra={"rejected_by": approver, "rejection_reason": reason})
        dashboard = self.build_review_dashboard(batch_date=batch_date)
        return {"date": batch_date, "slug": slug, "result": result, "dashboard": dashboard}

    def publish(self, *, batch_date: str) -> dict[str, Any]:
        payload = self._load_queue(batch_date)
        topics = payload.get("topics", [])
        if not topics:
            raise ValueError(f"No topics found for {batch_date}.")
        self._report_progress(f"[0/6] Preparing full-batch publish for {batch_date}")
        unapproved = [item for item in topics if str(item.get("status") or "") not in {"approved", "published"}]
        if unapproved:
            raise ValueError(
                f"Cannot publish batch {batch_date}. Every topic must be approved first. Remaining: {', '.join(str(item.get('slug') or '') for item in unapproved[:10])}"
            )
        publish_rows = {
            str(row.get("slug") or ""): row
            for row in _read_json(self.data_dir / "publish_queue.json", [])
        }
        blocked_for_publish: list[str] = []
        for item in topics:
            slug = str(item.get("slug") or "")
            publish_row = publish_rows.get(slug) or {}
            publish_status = str(publish_row.get("status") or "missing")
            if publish_status not in {"approved_for_publish", "published_local"}:
                failures = list(publish_row.get("failures") or [])
                reason = ", ".join(str(part) for part in failures if str(part).strip()) or publish_status
                blocked_for_publish.append(f"{slug} ({reason})")
        if blocked_for_publish:
            raise ValueError(
                f"Cannot publish batch {batch_date}. Publish gate is still blocking: {', '.join(blocked_for_publish[:10])}"
            )
        published: list[dict[str, Any]] = []
        total_topics = len(topics)
        for index, item in enumerate(topics, start=1):
            slug = str(item.get("slug") or "")
            self._report_progress(f"[prepare {index}/{total_topics}] Processing publish item: {slug}")
            publish_row = publish_rows.get(slug) or {}
            if str(publish_row.get("status") or "") == "published_local":
                metadata = self.console._load_metadata(slug)
                site_file = self.site_output_dir / slug / "index.html"
                article_file = self.data_dir / "published_static_pages" / slug / "index.html"
                self._update_batch_status(batch_date=batch_date, slug=slug, status="published", extra={"published_at": datetime.now(UTC).isoformat()})
                if site_file.exists():
                    self._copy_file(site_file, self.upload_root / batch_date / "published" / slug / "index.html")
                published.append(
                    {
                        "slug": slug,
                        "site_file": str(site_file),
                        "article_file": str(article_file),
                        "url": str(metadata.get("url") or publish_row.get("url") or ""),
                        "already_published": True,
                    }
                )
                continue
            publish_result = self.console.publish_slug(slug)
            self._update_batch_status(batch_date=batch_date, slug=slug, status="published", extra={"published_at": datetime.now(UTC).isoformat()})
            self._copy_file(Path(publish_result["site_file"]), self.upload_root / batch_date / "published" / slug / "index.html")
            published.append({"slug": slug, "site_file": publish_result["site_file"], "article_file": publish_result["article_file"]})
        return self._finalize_production_publish(
            batch_date=batch_date,
            published=published,
            commit_message=f"Publish daily batch {batch_date}",
        )

    def publish_ready(self, *, batch_date: str, validation_mode: str = "smart") -> dict[str, Any]:
        payload = self._load_queue(batch_date)
        topics = payload.get("topics", [])
        if not topics:
            raise ValueError(f"No topics found for {batch_date}.")
        self._report_progress(f"[0/6] Preparing publish-ready run for {batch_date} ({validation_mode})")
        publish_rows = {
            str(row.get("slug") or ""): row
            for row in _read_json(self.data_dir / "publish_queue.json", [])
        }
        ready_items = [
            item
            for item in topics
            if str((publish_rows.get(str(item.get("slug") or "")) or {}).get("status") or "") in {"approved_for_publish", "published_local"}
        ]
        carry_forward_items = self._carry_forward_publish_candidates(batch_date=batch_date, topics=topics, publish_rows=publish_rows)
        selected_items = ready_items + [item for item in carry_forward_items if str(item.get("slug") or "") not in {str(row.get("slug") or "") for row in ready_items}]
        if not selected_items:
            blocked_items = [
                item
                for item in topics
                if str((publish_rows.get(str(item.get("slug") or "")) or {}).get("status") or "") == "blocked"
            ]
            if blocked_items:
                raise ValueError(
                    f"No articles are ready for publish in batch {batch_date}. Blocked: {', '.join(str(item.get('slug') or '') for item in blocked_items[:10])}"
                )
            raise ValueError(f"No articles are ready for publish in batch {batch_date}.")

        published_candidates: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []
        selected_slugs = {str(item.get("slug") or "") for item in selected_items}
        for item in topics:
            slug = str(item.get("slug") or "")
            if slug in selected_slugs:
                continue
            publish_row = publish_rows.get(slug) or {}
            publish_status = str(publish_row.get("status") or "missing")
            skipped.append(
                {
                    "slug": slug,
                    "status": publish_status,
                    "failures": list(publish_row.get("failures") or []),
                }
            )
        total_topics = len(selected_items)
        for index, item in enumerate(selected_items, start=1):
            slug = str(item.get("slug") or "")
            self._report_progress(f"[prepare {index}/{total_topics}] Checking publish readiness for: {slug}")
            publish_row = publish_rows.get(slug) or {}
            publish_status = str(publish_row.get("status") or "missing")
            if publish_status not in {"approved_for_publish", "published_local"}:
                skipped.append(
                    {
                        "slug": slug,
                        "status": publish_status,
                        "failures": list(publish_row.get("failures") or []),
                        "reason": ", ".join(str(part).strip() for part in list(publish_row.get("failures") or []) if str(part).strip()) or publish_status,
                    }
                )
                continue
            if publish_status == "published_local":
                metadata = self.console._load_metadata(slug)
                site_file = self.site_output_dir / slug / "index.html"
                article_file = self.data_dir / "published_static_pages" / slug / "index.html"
                if site_file.exists():
                    self._copy_file(site_file, self.upload_root / batch_date / "published" / slug / "index.html")
                published_candidates.append(
                    {
                        "slug": slug,
                        "site_file": str(site_file),
                        "article_file": str(article_file),
                        "url": str(metadata.get("url") or publish_row.get("url") or ""),
                        "already_published": True,
                    }
                )
                continue
            publish_result = self.console.publish_slug(slug)
            self._copy_file(Path(publish_result["site_file"]), self.upload_root / batch_date / "published" / slug / "index.html")
            published_candidates.append({"slug": slug, "site_file": publish_result["site_file"], "article_file": publish_result["article_file"]})

        if not published_candidates:
            raise ValueError(f"No new articles were published for batch {batch_date}.")

        payload = self._finalize_production_publish(
            batch_date=batch_date,
            published=published_candidates,
            commit_message=f"Publish ready daily articles {batch_date}",
            validation_mode=validation_mode,
        )
        payload["skipped"] = skipped + list(payload.get("skipped") or [])
        payload["skipped_count"] = len(payload["skipped"])
        payload["carry_forward_count"] = len(carry_forward_items)
        return payload

    def autofix_batch(self, *, batch_date: str) -> dict[str, Any]:
        candidates = self._publish_validation_candidates(batch_date=batch_date)
        items: list[dict[str, Any]] = []
        total_fixed = 0
        for candidate in candidates:
            result = self._autofix_article_bundle(slug=candidate["slug"])
            items.append(result)
            total_fixed += int(result.get("fix_count", 0))
            self._update_batch_status_if_present(batch_date=batch_date, slug=candidate["slug"], extra=self._validation_dashboard_fields(result, mode="smart"))
        dashboard = self.build_review_dashboard(batch_date=batch_date)
        return {
            "date": batch_date,
            "mode": "smart",
            "total_candidates": len(candidates),
            "total_auto_fixed": total_fixed,
            "items": items,
            "dashboard": dashboard,
        }

    def validate_batch(self, *, batch_date: str, mode: str = "smart") -> dict[str, Any]:
        candidates = self._publish_validation_candidates(batch_date=batch_date)
        if mode == "strict":
            self._validate_html_tree(self.site_output_dir, scope="site_output")
            self._validate_html_tree(self.root / "docs", scope="docs")
        report = self._run_publish_validation(batch_date=batch_date, published=candidates, mode=mode)
        for item in list(report.get("items") or []):
            self._update_batch_status_if_present(batch_date=batch_date, slug=str(item.get("slug") or ""), extra=self._validation_dashboard_fields(item, mode=mode))
        dashboard = self.build_review_dashboard(batch_date=batch_date)
        return {**report, "dashboard": dashboard}

    def status(self, *, batch_date: str) -> dict[str, Any]:
        resolved_date = batch_date
        try:
            payload = self._load_queue(batch_date)
        except FileNotFoundError:
            fallback = self.latest_queue_date()
            if not fallback:
                return {
                    "date": batch_date,
                    "status": "missing_queue",
                    "message": f"Chua co editorial queue cho ngay {batch_date}.",
                    "how_to_fix": [
                        "Neu la dau tuan, chay menu 1 de tao 10 chu de va draft.",
                        "Neu la Tue-Sun, chay menu 2 de tao bai chuyen sau.",
                        "Neu la bai rieng, chay menu 3 hoac menu 9.",
                    ],
                    "next_recommended_command": f"python editorial_console.py morning --count 10 --date {batch_date}",
                    "latest_available_queue": "",
                }
            resolved_date = fallback
            payload = self._load_queue(fallback)
        topics = payload.get("topics", [])
        week_start = str(payload.get("week_start") or self._week_start(resolved_date))
        week_end = str(payload.get("week_end") or (date.fromisoformat(week_start) + timedelta(days=6)).isoformat())
        summary = {
            "date": resolved_date,
            "requested_date": batch_date,
            "week_start": week_start,
            "week_end": week_end,
            "daily_angle": self._daily_angle_label(batch_date=resolved_date, mode=str(payload.get("mode") or "standard")),
            "total_topics": len(topics),
            "drafted": sum(1 for item in topics if str(item.get("status") or "") == "drafted"),
            "approved": sum(1 for item in topics if str(item.get("status") or "") == "approved"),
            "rejected": sum(1 for item in topics if str(item.get("status") or "") == "rejected"),
            "published": sum(1 for item in topics if str(item.get("status") or "") == "published"),
            "missing_files": sum(1 for item in topics if not self._topic_files_exist(item)),
            "dashboard_file": str(self.review_root / resolved_date / "index.html"),
            "operator_console": str(self.console.console_html),
            "upload_dir": str(self.upload_root / resolved_date),
            "master_dashboard": str(self.upload_root / "dashboard.html"),
        }
        if resolved_date != batch_date:
            summary["message"] = f"Ngay {batch_date} chua co queue. Dang hien thi batch gan nhat: {resolved_date}."
        publish_rows = {
            str(row.get("slug") or ""): row
            for row in _read_json(self.data_dir / "publish_queue.json", [])
        }
        batch_publish_rows = [publish_rows.get(str(item.get("slug") or ""), {}) for item in topics]
        summary["ready_for_publish"] = sum(1 for row in batch_publish_rows if str(row.get("status") or "") == "approved_for_publish")
        summary["publish_blocked"] = sum(1 for row in batch_publish_rows if str(row.get("status") or "") == "blocked")
        summary["published_local"] = sum(1 for row in batch_publish_rows if str(row.get("status") or "") == "published_local")
        summary["top_block_reasons"] = self._top_block_reasons(batch_publish_rows)
        summary["next_recommended_command"] = self._recommended_command(summary, batch_date=resolved_date)
        return summary

    def _publish_validation_candidates(self, *, batch_date: str) -> list[dict[str, Any]]:
        payload = self._load_queue(batch_date)
        topics = payload.get("topics", [])
        publish_rows = {
            str(row.get("slug") or ""): row
            for row in _read_json(self.data_dir / "publish_queue.json", [])
        }
        candidates: list[dict[str, Any]] = []
        for item in topics:
            slug = str(item.get("slug") or "")
            if not slug:
                continue
            publish_row = publish_rows.get(slug) or {}
            publish_status = str(publish_row.get("status") or "")
            if publish_status not in {"approved_for_publish", "published_local"}:
                continue
            metadata = self.console._load_metadata(slug)
            url = normalize_public_url(str(metadata.get("url") or publish_row.get("url") or f"{settings.base_site_url.rstrip('/')}/{slug}/"))
            paths = self._article_bundle_paths(slug)
            candidates.append(
                {
                    "slug": slug,
                    "title": str(item.get("article_title") or item.get("keyword") or slug),
                    "url": url,
                    "publish_status": publish_status,
                    "publish_row": publish_row,
                    "paths": {key: str(value) for key, value in paths.items()},
                }
            )
        return candidates

    def _article_bundle_paths(self, slug: str) -> dict[str, Path]:
        return {
            "draft_html": self.data_dir / "production_article_drafts" / slug / "index.html",
            "published_static": self.data_dir / "published_static_pages" / slug / "index.html",
            "site_output": self.site_output_dir / slug / "index.html",
            "docs": self.root / "docs" / slug / "index.html",
            "metadata": self.data_dir / "production_article_drafts" / slug / "metadata.json",
        }

    def _article_bundle_files(self, slug: str) -> list[Path]:
        return [path for key, path in self._article_bundle_paths(slug).items() if key != "metadata" and path.exists()]

    def _autofix_article_bundle(self, *, slug: str) -> dict[str, Any]:
        paths = self._article_bundle_paths(slug)
        metadata = _read_json(paths["metadata"], {})
        official_url = str(
            metadata.get("request_context", {}).get("official_url")
            or metadata.get("official_url")
            or metadata.get("source_url")
            or ""
        ).strip()
        fix_count = 0
        touched_files: list[str] = []
        fix_labels: list[str] = []
        for path in self._article_bundle_files(slug):
            original = path.read_text(encoding="utf-8", errors="ignore")
            updated = original
            updated, changed = self._remove_forbidden_sections(updated)
            if changed:
                fix_count += changed
                fix_labels.append("removed_forbidden_markers")
            updated, changed = self._replace_placeholder_braces(updated, official_url=official_url)
            if changed:
                fix_count += changed
                fix_labels.append("replaced_placeholders")
            updated, changed = self._ensure_person_schema(updated)
            if changed:
                fix_count += changed
                fix_labels.append("person_schema")
            updated, changed = self._ensure_meta_description(updated, slug=slug)
            if changed:
                fix_count += changed
                fix_labels.append("meta_description")
            updated, changed = self._rewrite_direct_ctas(updated, slug=slug)
            if changed:
                fix_count += changed
                fix_labels.append("cta_redirects")
            updated, changed = self._ensure_faq_schema(updated)
            if changed:
                fix_count += changed
                fix_labels.append("faq_schema")
            updated, changed = self._ensure_cta_block(updated, slug=slug, official_url=official_url)
            if changed:
                fix_count += changed
                fix_labels.append("cta_block")
            if updated != original:
                path.write_text(updated, encoding="utf-8")
                touched_files.append(str(path))
        unique_labels = sorted(set(fix_labels))
        return {
            "slug": slug,
            "fix_count": fix_count,
            "files_touched": touched_files,
            "autofix_status": "fixed" if fix_count else "no_changes",
            "cta_status": "fixed" if "cta_block" in unique_labels or "cta_redirects" in unique_labels else "ok",
            "faq_schema_status": "fixed" if "faq_schema" in unique_labels else "ok",
            "meta_description_status": "fixed" if "meta_description" in unique_labels else "ok",
            "redirect_status": "fixed" if "cta_redirects" in unique_labels else "ok",
            "forbidden_marker_status": "fixed" if "removed_forbidden_markers" in unique_labels or "replaced_placeholders" in unique_labels else "ok",
        }

    def _remove_forbidden_sections(self, html_text: str) -> tuple[str, int]:
        markers = (
            "Research package snapshot",
            "Content planning snapshot",
            "Affiliate placeholder fields",
            "{{",
        )
        total_changed = 0
        updated = html_text
        for marker in markers:
            if marker not in updated:
                continue
            escaped = re.escape(marker)
            section_pattern = re.compile(rf"<section\b[^>]*>.*?{escaped}.*?</section>", flags=re.I | re.S)
            card_pattern = re.compile(rf"<div\b[^>]*class=['\"][^'\"]*card[^'\"]*['\"][^>]*>.*?{escaped}.*?</div>", flags=re.I | re.S)
            new_value, section_count = section_pattern.subn("", updated)
            updated = new_value
            total_changed += section_count
            new_value, card_count = card_pattern.subn("", updated)
            updated = new_value
            total_changed += card_count
            if marker in updated:
                updated = updated.replace(marker, "")
                total_changed += 1
        return updated, total_changed

    def _replace_placeholder_braces(self, html_text: str, *, official_url: str) -> tuple[str, int]:
        replacements = 0
        updated = html_text
        placeholder_pattern = re.compile(r"\{\{[^{}]+\}\}")
        matches = placeholder_pattern.findall(updated)
        if not matches:
            return updated, 0
        fallback = html.escape(official_url or settings.base_site_url, quote=True)
        updated = placeholder_pattern.sub(fallback, updated)
        replacements += len(matches)
        updated = updated.replace("{{", "").replace("}}", "")
        return updated, replacements

    def _strip_json_ld_by_type(self, html_text: str, *, schema_type: str) -> tuple[str, int]:
        pattern = re.compile(
            rf"""<script\s+type=(['"])application/ld\+json\1>.*?"@type"\s*:\s*"{re.escape(schema_type)}".*?</script>\s*""",
            flags=re.I | re.S,
        )
        return pattern.subn("", html_text)

    def _ensure_person_schema(self, html_text: str) -> tuple[str, int]:
        updated, removed = self._strip_json_ld_by_type(html_text, schema_type="Person")
        base_url = settings.base_site_url.rstrip("/")
        person_payload = json.dumps(
            {
                "@context": "https://schema.org",
                "@type": "Person",
                "@id": f"{base_url}/about-author/#person",
                "name": "Tuan Nguyen Quoc",
                "url": f"{base_url}/about-author/",
                "jobTitle": "Founder - MS Smile AI Review Hub",
                "worksFor": {"@id": f"{base_url}/#organization"},
            },
            ensure_ascii=False,
        )
        block = f'<script type="application/ld+json">{person_payload}</script>\n'
        if "</head>" in updated:
            return updated.replace("</head>", f"  {block}</head>", 1), removed + 1
        return block + updated, removed + 1

    def _ensure_meta_description(self, html_text: str, *, slug: str) -> tuple[str, int]:
        if re.search(r"<meta\b(?=[^>]*name=['\"]description['\"])", html_text, flags=re.I):
            return html_text, 0
        title_match = re.search(r"<title[^>]*>(.*?)</title>", html_text, flags=re.I | re.S)
        heading_match = re.search(r"<h1[^>]*>(.*?)</h1>", html_text, flags=re.I | re.S)
        title = re.sub(r"<[^>]+>", "", (title_match.group(1) if title_match else heading_match.group(1) if heading_match else slug.replace("-", " "))).strip()
        description = f"{title}. Compare pricing, pros, cons, alternatives, FAQs, and the best next step before you buy."
        description = _normalize_space(description)
        description = description[:157].rstrip(" ,.;:") + ("..." if len(description) > 157 else "")
        meta_tag = f'<meta name="description" content="{html.escape(description, quote=True)}">\n'
        if "</head>" in html_text:
            return html_text.replace("</head>", f"  {meta_tag}</head>", 1), 1
        return meta_tag + html_text, 1

    def _rewrite_direct_ctas(self, html_text: str, *, slug: str) -> tuple[str, int]:
        links = load_affiliate_links()
        replacements = 0
        updated = html_text
        for _, row in links.iterrows():
            target_slug = str(row.get("tool_slug") or row.get("slug") or "").strip()
            if not target_slug:
                continue
            tracked = f"/go/{target_slug}/?src=review/{slug}&cta=official_site"
            for column in ("affiliate_url", "official_url"):
                url = str(row.get(column) or "").strip()
                if not url or "/go/" in url:
                    continue
                new_value, changed = re.subn(
                    rf"""href=(['"])({re.escape(url)}|{re.escape(html.escape(url, quote=True))})\1""",
                    lambda match: f"href={match.group(1)}{html.escape(tracked, quote=True)}{match.group(1)}",
                    updated,
                    flags=re.I,
                )
                updated = new_value
                replacements += changed
        return updated, replacements

    def _ensure_faq_schema(self, html_text: str) -> tuple[str, int]:
        faq_matches = re.findall(
            r"<details[^>]*>\s*<summary[^>]*>(.*?)</summary>\s*(?:<p[^>]*>)?(.*?)(?:</p>)?\s*</details>",
            html_text,
            flags=re.I | re.S,
        )
        if not faq_matches and "FAQPage" in html_text:
            return html_text, 0
        updated, removed = self._strip_json_ld_by_type(html_text, schema_type="FAQPage")
        entities = []
        for question, answer in faq_matches[:10]:
            q = _normalize_space(re.sub(r"<[^>]+>", "", question))
            a = _normalize_space(re.sub(r"<[^>]+>", "", answer))
            if q and a:
                entities.append(
                    {
                        "@type": "Question",
                        "name": q,
                        "acceptedAnswer": {"@type": "Answer", "text": a},
                    }
                )
        if not entities:
            return updated, removed
        payload = json.dumps({"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": entities}, ensure_ascii=False)
        block = f'<script type="application/ld+json">{payload}</script>\n'
        if "</head>" in updated:
            return updated.replace("</head>", f"  {block}</head>", 1), removed + 1
        return block + updated, removed + 1

    def _ensure_cta_block(self, html_text: str, *, slug: str, official_url: str) -> tuple[str, int]:
        if re.search(r"Visit official website|Check current pricing", html_text, flags=re.I):
            return html_text, 0
        cta_url = official_url.strip() or f"{settings.base_site_url.rstrip('/')}/{slug}/"
        cta_block = (
            "\n<section class='card cta-final'>"
            "<h2>Ready to take the next step?</h2>"
            f"<p><a class='btn' href='{html.escape(cta_url, quote=True)}'>Visit official website</a></p>"
            "</section>\n"
        )
        if "</main>" in html_text:
            return html_text.replace("</main>", f"{cta_block}</main>", 1), 1
        if "</body>" in html_text:
            return html_text.replace("</body>", f"{cta_block}</body>", 1), 1
        return html_text + cta_block, 1

    def _validate_single_html_file(self, path: Path, *, scope: str) -> list[str]:
        if not path.exists():
            return [f"{scope} file is missing: {path.name}"]
        errors: list[str] = []
        text = path.read_text(encoding="utf-8", errors="ignore")
        faq_schema_present = False
        json_ld_pattern = re.compile(r"""<script\s+type=(['"])application/ld\+json\1>(.*?)</script>""", flags=re.I | re.S)
        for match in json_ld_pattern.finditer(text):
            payload_text = match.group(2).strip()
            try:
                payload = json.loads(payload_text)
            except json.JSONDecodeError as exc:
                errors.append(f"{scope} contains invalid JSON-LD: {exc.msg}")
                continue
            if isinstance(payload, dict) and payload.get("@type") == "FAQPage":
                faq_schema_present = True
        forbidden_markers = (
            "Research package snapshot",
            "Content planning snapshot",
            "Affiliate placeholder fields",
            "{{",
            "internal debug",
            "planning block",
            "debug block",
        )
        for marker in forbidden_markers:
            if marker in text:
                errors.append(f"{scope} contains forbidden marker: {marker}")
        workflow_markers = (
            "needs_human_review",
            "human_approved",
            "published_local",
            "approved_for_publish",
            "needs_revision",
            "needs_enrichment",
            "research_score",
            "source_confidence",
            "publish_queue_status",
        )
        for marker in workflow_markers:
            if re.search(re.escape(marker), text, flags=re.I):
                errors.append(f"{scope} contains internal workflow status: {marker}")
        if not re.search(r"<html\b[^>]*\blang=['\"][a-zA-Z-]+['\"]", text, flags=re.I):
            errors.append(f"{scope} html lang attribute is missing")
        if not re.search(r"<title[^>]*>[^<]+</title>", text, flags=re.I | re.S):
            errors.append(f"{scope} title is missing")
        if not re.search(r"<link\b(?=[^>]*\brel=['\"]canonical['\"])", text, flags=re.I):
            errors.append(f"{scope} canonical link is missing")
        stylesheet_matches = re.findall(r"<link\b(?=[^>]*\brel=['\"]stylesheet['\"])[^>]*\bhref=['\"]([^'\"]+)['\"]", text, flags=re.I)
        if not stylesheet_matches:
            errors.append(f"{scope} stylesheet link is missing")
        elif not any("/assets/article.css" in href or "/assets/public-article.css" in href for href in stylesheet_matches):
            errors.append(f"{scope} canonical article stylesheet is missing")
        if "site-header" not in text:
            errors.append(f"{scope} site header class is missing")
        if "article-layout" not in text:
            errors.append(f"{scope} article layout class is missing")
        if "site-footer" not in text:
            errors.append(f"{scope} canonical site footer is missing")
        for footer_class in ("footer-grid", "footer-column", "footer-links", "footer-bottom", "footer-brand", "footer-description", "footer-social-links"):
            if footer_class not in text:
                errors.append(f"{scope} footer class is missing: {footer_class}")
        if re.search(r"Affiliate Disclosure\s*Privacy Policy\s*About", _normalize_space(re.sub(r"<[^>]+>", " ", html.unescape(text))), flags=re.I):
            errors.append(f"{scope} footer links appear concatenated")
        if "community-signals" in text:
            for community_class in ("community-signals-grid", "community-signal-card", "community-signal-value", "community-signal-label", "community-signals-note"):
                if community_class not in text:
                    errors.append(f"{scope} community signals class is missing: {community_class}")
            if "Metrics reflect public content activity" not in text:
                errors.append(f"{scope} community signals note is missing")
        hero_images = re.findall(r"<img\b(?=[^>]*\bclass=['\"][^'\"]*\barticle-hero-image\b)[^>]*>", text, flags=re.I)
        for image_tag in hero_images:
            src_match = re.search(r"\bsrc=['\"]([^'\"]*)['\"]", image_tag, flags=re.I)
            src = src_match.group(1).strip() if src_match else ""
            if not src:
                errors.append(f"{scope} hero image src is empty")
            if re.search(r"placeholder|undefined|null|example\.com", src, flags=re.I):
                errors.append(f"{scope} hero image src is invalid placeholder: {src}")
            if not re.search(r"\bwidth=['\"]\d+['\"]", image_tag, flags=re.I) or not re.search(r"\bheight=['\"]\d+['\"]", image_tag, flags=re.I):
                errors.append(f"{scope} hero image must include width and height")
            if 'decoding="async"' not in image_tag.lower():
                errors.append(f"{scope} hero image must include decoding async")
            if src.startswith("/"):
                candidates = [
                    self.site_output_dir / src.lstrip("/"),
                    self.root / "docs" / src.lstrip("/"),
                ]
                if not any(candidate.exists() and candidate.is_file() for candidate in candidates):
                    errors.append(f"{scope} hero image local path is missing: {src}")
        if "<table" in text.lower() and ("table-wrapper" not in text or "article-table" not in text):
            errors.append(f"{scope} comparison tables must use table-wrapper and article-table")
        if re.search(r">\s*Visit official website\s*</a>", text, flags=re.I) and "cta-button" not in text:
            errors.append(f"{scope} CTA links must use cta-button classes")
        if re.search(r"<html\b[^>]*\blang=['\"]en", text, flags=re.I):
            vietnamese_markers = (
                "Đánh giá",
                "Giá",
                "những điểm cần kiểm tra",
                "lựa chọn thay thế",
                "trước khi mua",
                "ÄÃ¡nh giÃ¡",
                "nhá»¯ng Ä‘iá»ƒm",
                "lá»±a chá»n thay tháº¿",
            )
            for marker in vietnamese_markers:
                if marker.lower() in text.lower():
                    errors.append(f"{scope} English page contains Vietnamese public label: {marker}")
                    break
        related_cards = re.findall(r"<article\b[^>]*class=['\"][^'\"]*\brelated-card\b[^'\"]*['\"][\s\S]*?</article>", text, flags=re.I)
        if len(related_cards) > 6:
            errors.append(f"{scope} has more than 6 related cards")
        related_titles = []
        related_urls = []
        for card in related_cards:
            title_match = re.search(r"<h[34][^>]*>(.*?)</h[34]>", card, flags=re.I | re.S)
            href_match = re.search(r"<a\b[^>]*href=['\"]([^'\"]+)['\"]", card, flags=re.I)
            if title_match:
                related_titles.append(_normalize_space(re.sub(r"<[^>]+>", " ", html.unescape(title_match.group(1)))).lower())
            if href_match:
                related_urls.append(href_match.group(1).strip().lower())
        if len(related_titles) != len(set(related_titles)):
            errors.append(f"{scope} related titles are duplicated")
        if len(related_urls) != len(set(related_urls)):
            errors.append(f"{scope} related URLs are duplicated")
        if "Visit official website" not in text and "Check current pricing" not in text:
            errors.append(f"{scope} is missing CTA block")
        if "<details" in text.lower() and not faq_schema_present:
            errors.append(f"{scope} visible FAQ exists but FAQPage schema is missing")
        if not re.search(r"<meta\b(?=[^>]*name=['\"]description['\"])", text, flags=re.I):
            errors.append(f"{scope} meta description is missing")
        return errors

    def _run_publish_validation(self, *, batch_date: str, published: list[dict[str, Any]], mode: str) -> dict[str, Any]:
        items: list[dict[str, Any]] = []
        published_ok: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []
        total_auto_fixed = 0
        docs_root = self.root / "docs"
        for candidate in published:
            slug = str(candidate.get("slug") or "")
            autofix = self._autofix_article_bundle(slug=slug)
            total_auto_fixed += int(autofix.get("fix_count", 0))
            paths = self._article_bundle_paths(slug)
            url = normalize_public_url(str(candidate.get("url") or f"{settings.base_site_url.rstrip('/')}/{slug}/"))
            errors = []
            errors.extend(self._validate_single_html_file(paths["site_output"], scope="site_output"))
            errors.extend(self._validate_single_html_file(paths["docs"], scope="docs"))
            if mode == "strict" and url and paths["docs"].exists():
                page_validation = validate_page(url, docs_root)
                errors.extend(list(page_validation.errors))
            status = "passed" if not errors else "failed"
            item = {
                **candidate,
                **autofix,
                "validation_mode": mode,
                "validation_status": status,
                "errors": errors,
                "block_reason": "; ".join(errors[:5]),
                "next_action": "" if not errors else f"python editorial_console.py autofix-batch --date {batch_date}",
            }
            items.append(item)
            if errors:
                skipped.append({"slug": slug, "status": "validation_failed", "reason": item["block_reason"], "errors": errors})
            else:
                published_ok.append(candidate)
        return {
            "date": batch_date,
            "mode": mode,
            "total_approved": len(published),
            "total_auto_fixed": total_auto_fixed,
            "total_published": len(published_ok),
            "total_skipped": len(skipped),
            "published": published_ok,
            "skipped": skipped,
            "items": items,
            "next_action_command": f"python editorial_console.py publish-ready --date {batch_date} --validation-mode {mode}",
        }

    def _validation_dashboard_fields(self, item: dict[str, Any], *, mode: str) -> dict[str, Any]:
        errors = [str(value).strip() for value in list(item.get("errors") or []) if str(value).strip()]
        return {
            "validation_mode": mode,
            "validation_status": str(item.get("validation_status") or ""),
            "autofix_status": str(item.get("autofix_status") or ""),
            "cta_status": str(item.get("cta_status") or ""),
            "faq_schema_status": str(item.get("faq_schema_status") or ""),
            "meta_description_status": str(item.get("meta_description_status") or ""),
            "redirect_status": str(item.get("redirect_status") or ""),
            "block_reason": str(item.get("block_reason") or ""),
            "validation_errors": errors,
            "next_action": str(item.get("next_action") or ""),
        }

    def _sync_docs_for_published(self, published: list[dict[str, Any]]) -> list[str]:
        synced: list[str] = []
        for item in published:
            slug = str(item.get("slug") or "")
            if not slug:
                continue
            source = self.site_output_dir / slug / "index.html"
            target = self.root / "docs" / slug / "index.html"
            if source.exists():
                self._copy_file(source, target)
                synced.append(slug)
        return synced

    def get_dashboard_paths(self, *, batch_date: str) -> dict[str, str]:
        upload_dir = self.upload_root / batch_date
        return {
            "date": batch_date,
            "review_dashboard": str(self.review_root / batch_date / "index.html"),
            "master_dashboard": str(self.upload_root / "dashboard.html"),
            "operator_console": str(self.console.console_html),
            "upload_dir": str(upload_dir),
            "open_dashboard_cmd": str(upload_dir / "open_dashboard.cmd"),
            "publish_approved_cmd": str(upload_dir / "publish_approved.cmd"),
            "status_cmd": str(upload_dir / "status.cmd"),
        }

    def check_live(self, *, batch_date: str | None = None, include_all: bool = False, blocked_only: bool = False) -> dict[str, Any]:
        target_date = batch_date or date.today().isoformat()
        items = self._check_live_items(batch_date=target_date, include_all=include_all)
        if blocked_only:
            items = [item for item in items if str(item.get("publish_queue_status") or "") == "blocked"]
        summary = {
            "date": target_date,
            "include_all": include_all,
            "blocked_only": blocked_only,
            "total_items": len(items),
            "local_only": sum(1 for item in items if item["local_status"] == "local_only"),
            "docs_synced": sum(1 for item in items if item["docs_synced"]),
            "git_pushed": sum(1 for item in items if item["git_status"] == "pushed"),
            "live_ok": sum(1 for item in items if item["live_status"] == "live"),
            "live_404": sum(1 for item in items if item["live_status"] == "404"),
            "live_unknown": sum(1 for item in items if item["live_status"] == "unknown"),
            "published": sum(1 for item in items if item["display_status"] == "Published"),
            "awaiting_publish": sum(1 for item in items if item["display_status"] == "Awaiting Publish"),
            "awaiting_push": sum(1 for item in items if item["display_status"] == "Awaiting Push"),
            "missing_docs": sum(1 for item in items if item["display_status"] == "Docs Pending"),
            "blocked": sum(1 for item in items if item["display_status"] == "Blocked"),
            "ready": sum(1 for item in items if item["display_status"] == "Ready"),
            "unknown": sum(1 for item in items if item["display_status"] == "Unknown"),
        }
        report = {
            "generated_at": datetime.now(UTC).isoformat(),
            "date": target_date,
            "summary": summary,
            "items": items,
            "repo_sync": self._git_branch_sync_status(),
        }
        json_path = self.data_dir / "live_status_report.json"
        md_path = self.data_dir / "live_status_report.md"
        html_path = self.data_dir / "live_status_report.html"
        _write_json(json_path, report)
        md_path.write_text(self._render_live_status_markdown(report), encoding="utf-8")
        html_path.write_text(self._render_live_status_html(report), encoding="utf-8")
        return {
            **report,
            "json_report": str(json_path),
            "md_report": str(md_path),
            "html_report": str(html_path),
        }

    def next_pending_slug(self, batch_date: str, *, current_slug: str = "") -> str:
        payload = self._load_queue(batch_date)
        topics = payload.get("topics", [])
        pending = [
            str(item.get("slug") or "")
            for item in topics
            if self._has_reviewable_preview(item) and str(item.get("status") or "") in {"drafted", "selected"}
        ]
        if current_slug in pending:
            index = pending.index(current_slug)
            if index + 1 < len(pending):
                return pending[index + 1]
        return pending[0] if pending else ""

    def render_interactive_dashboard(self, *, batch_date: str, selected_slug: str = "", message: str = "") -> str:
        return self._render_interactive_dashboard_v2(batch_date=batch_date, selected_slug=selected_slug, message=message)

    def _legacy_render_interactive_dashboard(self, *, batch_date: str, selected_slug: str = "", message: str = "") -> str:
        payload = self._load_queue(batch_date)
        topics = payload.get("topics", [])
        summary = self.status(batch_date=batch_date)
        publish_rows = {
            str(row.get("slug") or ""): row
            for row in _read_json(self.data_dir / "publish_queue.json", [])
        }
        selected = next((item for item in topics if str(item.get("slug") or "") == selected_slug), None)
        if selected is None and topics:
            selected = next(
                (item for item in topics if self._has_reviewable_preview(item) and str(item.get("status") or "") in {"drafted", "selected"}),
                topics[0],
            )
        rows = []
        for item in topics:
            slug = str(item.get("slug") or "")
            status = str(item.get("status") or "selected")
            href = f"/?date={batch_date}&slug={slug}"
            has_preview = self._has_reviewable_preview(item)
            view_cell = (
                f"<a class='button' href='{html.escape(href, quote=True)}'>Xem nội dung</a>"
                if has_preview
                else "<span class='button disabled'>Chưa có draft</span>"
            )
            rows.append(
                "<tr>"
                f"<td><a href='{html.escape(href, quote=True)}'><strong>{html.escape(str(item.get('article_title') or item.get('keyword') or slug))}</strong></a><br><code>{html.escape(slug)}</code></td>"
                f"<td>{html.escape(str(item.get('keyword') or ''))}</td>"
                f"<td>{html.escape(str(item.get('total_score') or ''))}</td>"
                f"<td><span class='status {html.escape(self._status_class(status))}'>{html.escape(status)}</span></td>"
                f"<td>{view_cell}</td>"
                "</tr>"
            )
        detail_html = "<p>Không có bài nào trong batch.</p>"
        if selected is not None:
            selected_slug_value = str(selected.get("slug") or "")
            preview_src = f"/preview?date={batch_date}&slug={urllib.parse.quote(selected_slug_value)}"
            selected_status = str(selected.get("status") or "selected")
            has_preview = self._has_reviewable_preview(selected)
            status_message = str(selected.get("error") or "").strip()
            if not status_message and not has_preview:
                status_message = "Topic này chưa có draft để duyệt. Nó vẫn đang bị chặn ở research/source quality gate."
            approve_disabled = selected_status not in {"drafted", "selected"} or not has_preview
            reject_disabled = selected_status == "published"
            preview_block = (
                f"""
            <div class="detail-actions">
              <a class="button" href="{html.escape(preview_src, quote=True)}" target="article-preview">Xem nội dung</a>
            </div>
            <iframe class="preview-frame" name="article-preview" src="{html.escape(preview_src, quote=True)}" title="Article preview"></iframe>
            """
                if has_preview
                else f"<div class='empty-preview'><strong>Chưa có draft preview.</strong><br>{html.escape(status_message)}</div>"
            )
            detail_html = f"""
            <h2>{html.escape(str(selected.get('article_title') or selected.get('keyword') or selected_slug_value))}</h2>
            <p><code>{html.escape(selected_slug_value)}</code></p>
            <p>Keyword: <strong>{html.escape(str(selected.get('keyword') or ''))}</strong></p>
            <p>Status: <span class="status {html.escape(self._status_class(selected_status))}">{html.escape(selected_status)}</span></p>
            <p>Publish gate: <strong>{html.escape(str((publish_rows.get(selected_slug_value) or {}).get('status') or 'missing'))}</strong></p>
            {f"<p class='detail-note'>{html.escape(status_message)}</p>" if status_message else ""}
            {preview_block}
            <div class="form-row">
              <form method="post" action="/approve">
                <input type="hidden" name="date" value="{html.escape(batch_date, quote=True)}">
                <input type="hidden" name="slug" value="{html.escape(selected_slug_value, quote=True)}">
                <button class="button success" {'disabled' if approve_disabled else ''}>Approve</button>
              </form>
              <form method="post" action="/reject">
                <input type="hidden" name="date" value="{html.escape(batch_date, quote=True)}">
                <input type="hidden" name="slug" value="{html.escape(selected_slug_value, quote=True)}">
                <input type="text" name="reason" value="Need revision" aria-label="Reject reason">
                <button class="button danger" {'disabled' if reject_disabled else ''}>Reject</button>
              </form>
            </div>
            """
        publish_disabled = summary["ready_for_publish"] == 0
        notice = f"<div class='notice'>{html.escape(message)}</div>" if message else ""
        return f"""<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Interactive Editorial Review Dashboard {html.escape(batch_date)}</title>
  <style>
    body{{font-family:Arial,sans-serif;background:#f6f8fb;color:#152033;margin:0;padding:24px}}
    .wrap{{max-width:1400px;margin:0 auto}}
    .card{{background:#fff;border:1px solid #d8e1ec;border-radius:14px;padding:20px;margin:16px 0}}
    .layout{{display:grid;grid-template-columns:1fr 1.2fr;gap:18px;align-items:start}}
    table{{width:100%;border-collapse:collapse}}
    th,td{{border-bottom:1px solid #e5edf6;padding:12px;text-align:left;vertical-align:top}}
    th{{background:#f1f5f9}}
    .button{{display:inline-block;padding:10px 14px;border-radius:8px;border:1px solid #cbd5e1;background:#fff;color:#17324d;text-decoration:none;font-weight:700}}
    .button.success{{background:#dcfce7;border-color:#86efac;color:#166534}}
    .button.danger{{background:#fee2e2;border-color:#fca5a5;color:#991b1b}}
    .button.primary{{background:#17324d;border-color:#17324d;color:#fff}}
    .button.disabled{{opacity:.55;pointer-events:none;background:#e2e8f0;color:#64748b}}
    .button:disabled{{opacity:.45}}
    .status{{display:inline-block;padding:4px 10px;border-radius:999px;font-weight:700}}
    .status.selected,.status.drafted{{background:#fef3c7;color:#92400e}}
    .status.approved,.status.published{{background:#dcfce7;color:#166534}}
    .status.rejected,.status.needs_enrichment,.status.draft_failed{{background:#fee2e2;color:#991b1b}}
    .preview-frame{{width:100%;height:720px;border:1px solid #d8e1ec;border-radius:10px;background:#fff}}
    .empty-preview{{border:1px dashed #cbd5e1;border-radius:10px;padding:18px;background:#f8fafc;color:#475569}}
    .detail-note{{color:#991b1b;font-weight:600}}
    .form-row{{display:flex;gap:12px;flex-wrap:wrap;margin-top:14px}}
    .form-row form{{display:flex;gap:8px;align-items:center}}
    .actions{{display:flex;gap:10px;flex-wrap:wrap}}
    .notice{{background:#e0f2fe;color:#075985;border:1px solid #7dd3fc;padding:10px 12px;border-radius:8px;margin:12px 0}}
    input[type=text]{{padding:10px 12px;border:1px solid #cbd5e1;border-radius:8px;min-width:220px}}
    @media (max-width:1100px){{.layout{{grid-template-columns:1fr}} .preview-frame{{height:520px}}}}
  </style>
</head>
<body>
  <main class="wrap">
    <section class="card">
      <h1>Editorial Review Dashboard - {html.escape(batch_date)}</h1>
      <p>Weekly batch: <strong>{html.escape(summary['week_start'])}</strong> -> <strong>{html.escape(summary['week_end'])}</strong></p>
      <p>Today's angle: <strong>{html.escape(summary['daily_angle'])}</strong></p>
      <p>Total topics: <strong>{summary['total_topics']}</strong> - Drafted: <strong>{summary['drafted']}</strong> - Human Approved: <strong>{summary['approved']}</strong> - Ready for Publish: <strong>{summary['ready_for_publish']}</strong> - Publish Blocked: <strong>{summary['publish_blocked']}</strong> - Published: <strong>{summary['published']}</strong></p>
      <div class="actions">
        <a class="button" href="/?date={html.escape(batch_date, quote=True)}">Quay về danh sách</a>
        <a class="button" href="/?date={html.escape(batch_date, quote=True)}&slug={html.escape(self.next_pending_slug(batch_date), quote=True)}">Tới bài cần duyệt tiếp theo</a>
        <a class="button" href="/shutdown">Đóng local dashboard</a>
      </div>
      {notice}
    </section>
    <section class="layout">
      <section class="card">
        <h2>Danh sách bài</h2>
        <table>
          <thead>
            <tr>
              <th>Title</th>
              <th>Keyword</th>
              <th>Score</th>
              <th>Status</th>
              <th>View</th>
            </tr>
          </thead>
          <tbody>{''.join(rows)}</tbody>
        </table>
        <form method="post" action="/publish" style="margin-top:16px">
          <input type="hidden" name="date" value="{html.escape(batch_date, quote=True)}">
          <button class="button primary" {'disabled' if publish_disabled else ''}>Publish Ready Articles</button>
        </form>
      </section>
      <section class="card">
        {detail_html}
      </section>
    </section>
  </main>
</body>
</html>"""

    def build_review_dashboard(self, *, batch_date: str) -> dict[str, Any]:
        return self._build_review_dashboard_v2(batch_date=batch_date)

    def _legacy_build_review_dashboard(self, *, batch_date: str) -> dict[str, Any]:
        payload = self._load_queue(batch_date)
        topics = payload.get("topics", [])
        summary = self.status(batch_date=batch_date)
        dashboard_dir = self.review_root / batch_date
        dashboard_dir.mkdir(parents=True, exist_ok=True)
        publish_batch_launcher = self._build_batch_launcher(batch_date=batch_date, file_name="publish-batch.cmd", command=f"python editorial_console.py publish-ready --date {batch_date}")
        refresh_launcher = self._build_batch_launcher(batch_date=batch_date, file_name="refresh-status.cmd", command=f"python editorial_console.py status --date {batch_date}")
        open_console_launcher = self._build_batch_launcher(batch_date=batch_date, file_name="open-operator-console.cmd", command=f'explorer "{self.console.console_html}"', shell_only=True)
        upload_dir = self.upload_root / batch_date
        rows: list[str] = []
        for item in topics:
            slug = str(item.get("slug") or "")
            preview_href = f"./{slug}/index.html" if (dashboard_dir / slug / "index.html").exists() else ""
            draft_file = str(item.get("draft_file") or "")
            upload_preview = upload_dir / "review" / slug / "index.html"
            approve_cmd = f"python editorial_console.py approve --slug {slug} --date {batch_date}"
            reject_cmd = f"python editorial_console.py reject --slug {slug} --date {batch_date} --reason \"Needs fixes\""
            approve_launcher = self._build_batch_launcher(batch_date=batch_date, file_name=f"approve-{slug}.cmd", command=approve_cmd)
            reject_launcher = self._build_batch_launcher(batch_date=batch_date, file_name=f"reject-{slug}.cmd", command=reject_cmd)
            status = str(item.get("status") or "selected")
            can_review = self._has_reviewable_preview(item)
            preview_cell = f'<a class="button" href="{html.escape(preview_href, quote=True)}">Open Preview</a>' if preview_href else '<span class="button disabled">No draft yet</span>'
            approve_cell = (
                f"<a class='button success' href='{html.escape(self._relative_review_link(batch_date, approve_launcher), quote=True)}'>Approve</a><br><code>{html.escape(approve_cmd)}</code>"
                if can_review
                else "<span class='button disabled'>Blocked</span><br><code>Research/source gate must pass first</code>"
            )
            reject_cell = (
                f"<a class='button danger' href='{html.escape(self._relative_review_link(batch_date, reject_launcher), quote=True)}'>Reject</a><br><code>{html.escape(reject_cmd)}</code>"
                if can_review
                else "<span class='button disabled'>Blocked</span><br><code>No draft to review</code>"
            )
            rows.append(
                "<tr>"
                f"<td><strong>{html.escape(str(item.get('article_title') or item.get('keyword') or slug))}</strong><br><code>{html.escape(slug)}</code></td>"
                f"<td>{html.escape(str(item.get('keyword') or ''))}</td>"
                f"<td>{html.escape(str(item.get('total_score') or ''))}</td>"
                f"<td><span class='status {html.escape(self._status_class(status))}'>{html.escape(status)}</span></td>"
                f"<td>{preview_cell}</td>"
                f"<td>{approve_cell}</td>"
                f"<td>{reject_cell}</td>"
                f"<td><code>{html.escape(draft_file)}</code></td>"
                f"<td><code>{html.escape(str(upload_preview))}</code></td>"
                "</tr>"
            )
        html_text = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Editorial Review Dashboard {html.escape(batch_date)}</title>
  <style>
    body{{font-family:Arial,sans-serif;background:#f6f8fb;color:#152033;margin:0;padding:24px}}
    .wrap{{max-width:1200px;margin:0 auto}}
    .card{{background:#fff;border:1px solid #d8e1ec;border-radius:12px;padding:20px;margin:16px 0}}
    table{{width:100%;border-collapse:collapse}}
    th,td{{border-bottom:1px solid #e5edf6;padding:12px;text-align:left;vertical-align:top}}
    th{{background:#f1f5f9}}
    code{{white-space:pre-wrap;word-break:break-word}}
    a{{color:#0f766e;text-decoration:none}}
    .button{{display:inline-block;padding:8px 12px;border-radius:8px;border:1px solid #cbd5e1;background:#fff;text-decoration:none;font-weight:600}}
    .button.success{{background:#dcfce7;border-color:#86efac;color:#166534}}
    .button.danger{{background:#fee2e2;border-color:#fca5a5;color:#991b1b}}
    .button.primary{{background:#17324d;border-color:#17324d;color:#fff}}
    .button.warn{{background:#fef3c7;border-color:#fcd34d;color:#92400e}}
    .button.disabled{{opacity:.55;pointer-events:none;background:#e2e8f0;color:#64748b}}
    .status{{display:inline-block;padding:4px 10px;border-radius:999px;font-weight:700}}
    .status.selected,.status.drafted{{background:#fef3c7;color:#92400e}}
    .status.approved,.status.published{{background:#dcfce7;color:#166534}}
    .status.rejected,.status.needs_enrichment,.status.draft_failed{{background:#fee2e2;color:#991b1b}}
    .actions{{display:flex;gap:10px;flex-wrap:wrap}}
  </style>
</head>
<body>
  <main class="wrap">
    <section class="card">
      <h1>Editorial Review Dashboard - {html.escape(batch_date)}</h1>
      <p>Weekly batch: <strong>{html.escape(summary['week_start'])}</strong> -> <strong>{html.escape(summary['week_end'])}</strong></p>
      <p>Today's angle: <strong>{html.escape(summary['daily_angle'])}</strong></p>
      <p>Total topics: <strong>{summary['total_topics']}</strong> - Drafted: <strong>{summary['drafted']}</strong> - Human Approved: <strong>{summary['approved']}</strong> - Ready for Publish: <strong>{summary['ready_for_publish']}</strong> - Publish Blocked: <strong>{summary['publish_blocked']}</strong> - Published: <strong>{summary['published']}</strong></p>
      <p>Next recommended command: <code>{html.escape(summary['next_recommended_command'])}</code></p>
      <div class="actions">
        <a class="button warn" href="{html.escape(self._relative_review_link(batch_date, open_console_launcher), quote=True)}">Open Operator Console</a>
        <a class="button primary" href="{html.escape(self._relative_review_link(batch_date, publish_batch_launcher), quote=True)}">Publish Ready Articles</a>
        <a class="button" href="{html.escape(self._relative_review_link(batch_date, refresh_launcher), quote=True)}">Refresh Status</a>
      </div>
      <p>Open each preview, review it, approve or reject it, then click <strong>Publish Ready Articles</strong>. Only rows that already passed the publish gate will go live.</p>
    </section>
    <section class="card">
      <table>
        <thead>
          <tr>
            <th>Title</th>
            <th>Keyword</th>
            <th>Score</th>
            <th>Status</th>
            <th>Actions</th>
            <th>Approve</th>
            <th>Reject</th>
            <th>Source file path</th>
            <th>Upload file path</th>
          </tr>
        </thead>
        <tbody>{''.join(rows)}</tbody>
      </table>
    </section>
  </main>
        </body>
</html>
"""
        html_text = self._clean_dashboard_text(html_text)
        dashboard_file = dashboard_dir / "index.html"
        dashboard_file.write_text(html_text, encoding="utf-8")
        data = {
            "date": batch_date,
            "summary": summary,
            "topics": topics,
            "dashboard_file": str(dashboard_file),
            "operator_console": str(self.console.console_html),
            "publish_launcher": str(publish_batch_launcher),
            "upload_dir": str(upload_dir),
        }
        _write_json(self._queue_dir(batch_date) / "dashboard.json", data)
        return data

    def _render_interactive_row(self, item: dict[str, Any], *, publish_rows: dict[str, dict[str, Any]], batch_date: str) -> str:
        slug = str(item.get("slug") or "")
        status = str(item.get("status") or "selected")
        publish_row = publish_rows.get(slug) or {}
        publish_status = str(publish_row.get("status") or "missing")
        row_filter = "ready" if publish_status == "approved_for_publish" else "published" if publish_status == "published_local" or status == "published" else "needs-revision" if status == "rejected" else "blocked" if publish_status == "blocked" else "waiting"
        block_reason = self._row_block_reason(item, publish_row)
        next_action = self._next_action_for_item(item, publish_row, batch_date=batch_date)
        upload_path = str(self.upload_root / batch_date / "review" / slug / "index.html")
        href = f"/?date={batch_date}&slug={slug}"
        has_preview = self._has_reviewable_preview(item)
        validation_bits = [
            f"validation={str(item.get('validation_status') or '-')}",
            f"autofix={str(item.get('autofix_status') or '-')}",
            f"cta={str(item.get('cta_status') or '-')}",
            f"faq={str(item.get('faq_schema_status') or '-')}",
            f"meta={str(item.get('meta_description_status') or '-')}",
        ]
        view_cell = (
            f"<a class='button' href='{html.escape(href, quote=True)}'>Open Review</a>"
            if has_preview
            else "<span class='button disabled'>No draft yet</span>"
        )
        return (
            f"<tr data-filter='{html.escape(row_filter, quote=True)}'>"
            f"<td><a href='{html.escape(href, quote=True)}'><strong>{html.escape(str(item.get('article_title') or item.get('keyword') or slug))}</strong></a><br><code>{html.escape(slug)}</code></td>"
            f"<td>{html.escape(str(item.get('keyword') or ''))}</td>"
            f"<td>{html.escape(str(item.get('total_score') or ''))}</td>"
            f"<td><span class='status {html.escape(self._status_class(status))}'>{html.escape(self._operator_status_label(status))}</span></td>"
            f"<td>{html.escape(block_reason)}<br><small>{html.escape(' | '.join(validation_bits))}</small></td>"
            f"<td><code>{html.escape(str(item.get('next_action') or next_action))}</code></td>"
            f"<td><code>{html.escape(upload_path)}</code></td>"
            f"<td>{view_cell}</td>"
            "</tr>"
        )

    def _render_interactive_detail(self, selected: dict[str, Any], *, publish_rows: dict[str, dict[str, Any]], batch_date: str) -> str:
        selected_slug_value = str(selected.get("slug") or "")
        preview_src = f"/preview?date={batch_date}&slug={urllib.parse.quote(selected_slug_value)}"
        selected_status = str(selected.get("status") or "selected")
        has_preview = self._has_reviewable_preview(selected)
        status_message = str(selected.get("error") or "").strip()
        if not status_message and not has_preview:
            status_message = "This topic does not have a reviewable draft yet. It is still waiting on the research/source quality gate."
        approve_disabled = selected_status not in {"drafted", "selected"} or not has_preview
        reject_disabled = selected_status == "published"
        publish_row = publish_rows.get(selected_slug_value) or {}
        block_reason = self._row_block_reason(selected, publish_row)
        next_action = self._next_action_for_item(selected, publish_row, batch_date=batch_date)
        validation_status = str(selected.get("validation_status") or "-")
        autofix_status = str(selected.get("autofix_status") or "-")
        cta_status = str(selected.get("cta_status") or "-")
        faq_status = str(selected.get("faq_schema_status") or "-")
        meta_status = str(selected.get("meta_description_status") or "-")
        redirect_status = str(selected.get("redirect_status") or "-")
        preview_block = (
            f"""
            <div class="detail-actions">
              <a class="button" href="{html.escape(preview_src, quote=True)}" target="article-preview">Open Review</a>
            </div>
            <iframe class="preview-frame" name="article-preview" src="{html.escape(preview_src, quote=True)}" title="Article preview"></iframe>
            """
            if has_preview
            else f"<div class='empty-preview'><strong>ChÆ°a cÃ³ draft preview.</strong><br>{html.escape(status_message)}</div>"
        )
        if not has_preview:
            preview_block = f"<div class='empty-preview'><strong>No draft preview yet.</strong><br>{html.escape(status_message)}</div>"
        return f"""
            <h2>{html.escape(str(selected.get('article_title') or selected.get('keyword') or selected_slug_value))}</h2>
            <p><code>{html.escape(selected_slug_value)}</code></p>
            <p>Keyword: <strong>{html.escape(str(selected.get('keyword') or ''))}</strong></p>
            <p>Status: <span class="status {html.escape(self._status_class(selected_status))}">{html.escape(self._operator_status_label(selected_status))}</span></p>
            <p>Publish gate: <strong>{html.escape(self._operator_status_label(str(publish_row.get('status') or 'missing')))}</strong></p>
            <p>Block reason: <strong>{html.escape(block_reason)}</strong></p>
            <p>Validation: <strong>{html.escape(validation_status)}</strong> | Autofix: <strong>{html.escape(autofix_status)}</strong> | CTA: <strong>{html.escape(cta_status)}</strong> | FAQ schema: <strong>{html.escape(faq_status)}</strong> | Meta: <strong>{html.escape(meta_status)}</strong> | Redirect: <strong>{html.escape(redirect_status)}</strong></p>
            <p>Next action: <code>{html.escape(str(selected.get('next_action') or next_action))}</code></p>
            {f"<p class='detail-note'>{html.escape(status_message)}</p>" if status_message else ""}
            {preview_block}
            <div class="form-row">
              <form method="post" action="/approve">
                <input type="hidden" name="date" value="{html.escape(batch_date, quote=True)}">
                <input type="hidden" name="slug" value="{html.escape(selected_slug_value, quote=True)}">
                <button class="button success" {'disabled' if approve_disabled else ''}>Approve</button>
              </form>
              <form method="post" action="/reject">
                <input type="hidden" name="date" value="{html.escape(batch_date, quote=True)}">
                <input type="hidden" name="slug" value="{html.escape(selected_slug_value, quote=True)}">
                <input type="text" name="reason" value="Need revision" aria-label="Reject reason">
                <button class="button danger" {'disabled' if reject_disabled else ''}>Reject</button>
              </form>
            </div>
            """

    def _render_kpi_grid(self, summary: dict[str, Any]) -> str:
        top_block_reasons = "; ".join(summary.get("top_block_reasons", [])) or "none"
        return (
            "<div class='kpis'>"
            f"<div class='kpi'>Total drafts<strong>{summary['drafted']}</strong></div>"
            f"<div class='kpi'>Human Approved<strong>{summary['approved']}</strong></div>"
            f"<div class='kpi'>Publish Blocked<strong>{summary['publish_blocked']}</strong></div>"
            f"<div class='kpi'>Ready for Publish<strong>{summary['ready_for_publish']}</strong></div>"
            f"<div class='kpi'>Published<strong>{summary['published']}</strong></div>"
            f"<div class='kpi'>Top block reasons<strong class='small'>{html.escape(top_block_reasons)}</strong></div>"
            "</div>"
        )

    def _render_filter_controls(self) -> str:
        return """
        <div class="filters">
          <button type="button" class="button filter-btn active" data-filter-target="all">All</button>
          <button type="button" class="button filter-btn" data-filter-target="ready">Ready for Publish</button>
          <button type="button" class="button filter-btn" data-filter-target="blocked">Publish Blocked</button>
          <button type="button" class="button filter-btn" data-filter-target="needs-revision">Needs revision</button>
          <button type="button" class="button filter-btn" data-filter-target="published">Published</button>
        </div>
        """

    def _render_filter_script(self) -> str:
        return """
  <script>
    const filterButtons = Array.from(document.querySelectorAll('.filter-btn'));
    const rowsEl = Array.from(document.querySelectorAll('#article-rows tr'));
    filterButtons.forEach((button) => {
      button.addEventListener('click', () => {
        const target = button.getAttribute('data-filter-target') || 'all';
        filterButtons.forEach((item) => item.classList.toggle('active', item === button));
        rowsEl.forEach((row) => {
          const rowFilter = row.getAttribute('data-filter') || 'all';
          row.style.display = target === 'all' || rowFilter === target ? '' : 'none';
        });
      });
    });
  </script>
        """

    def _dashboard_style_block(self) -> str:
        return """
    body{font-family:Arial,sans-serif;background:#f6f8fb;color:#152033;margin:0;padding:24px}
    .wrap{max-width:1600px;margin:0 auto}
    .card{background:#fff;border:1px solid #d8e1ec;border-radius:14px;padding:20px;margin:16px 0}
    .layout{display:grid;grid-template-columns:1.15fr 1fr;gap:18px;align-items:start}
    table{width:100%;border-collapse:collapse}
    th,td{border-bottom:1px solid #e5edf6;padding:12px;text-align:left;vertical-align:top}
    th{background:#f1f5f9}
    .button{display:inline-block;padding:10px 14px;border-radius:8px;border:1px solid #cbd5e1;background:#fff;color:#17324d;text-decoration:none;font-weight:700}
    .button.success{background:#dcfce7;border-color:#86efac;color:#166534}
    .button.danger{background:#fee2e2;border-color:#fca5a5;color:#991b1b}
    .button.primary{background:#17324d;border-color:#17324d;color:#fff}
    .button.warn{background:#fef3c7;border-color:#fcd34d;color:#92400e}
    .button.disabled{opacity:.55;pointer-events:none;background:#e2e8f0;color:#64748b}
    .button:disabled{opacity:.45}
    .filter-btn{cursor:pointer}
    .filter-btn.active{background:#17324d;border-color:#17324d;color:#fff}
    .status{display:inline-block;padding:4px 10px;border-radius:999px;font-weight:700}
    .status.selected,.status.drafted{background:#fef3c7;color:#92400e}
    .status.approved,.status.published{background:#dcfce7;color:#166534}
    .status.rejected,.status.needs_enrichment,.status.draft_failed{background:#fee2e2;color:#991b1b}
    .preview-frame{width:100%;height:720px;border:1px solid #d8e1ec;border-radius:10px;background:#fff}
    .empty-preview{border:1px dashed #cbd5e1;border-radius:10px;padding:18px;background:#f8fafc;color:#475569}
    .detail-note{color:#991b1b;font-weight:600}
    .form-row{display:flex;gap:12px;flex-wrap:wrap;margin-top:14px}
    .form-row form{display:flex;gap:8px;align-items:center}
    .actions{display:flex;gap:10px;flex-wrap:wrap}
    .filters{display:flex;gap:8px;flex-wrap:wrap;margin:14px 0}
    .kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin:16px 0}
    .kpi{background:#f8fafc;border:1px solid #d8e1ec;border-radius:10px;padding:12px}
    .kpi strong{display:block;font-size:1.5rem;margin-top:6px}
    .kpi .small{font-size:.9rem;line-height:1.35}
    .notice{background:#e0f2fe;color:#075985;border:1px solid #7dd3fc;padding:10px 12px;border-radius:8px;margin:12px 0}
    input[type=text]{padding:10px 12px;border:1px solid #cbd5e1;border-radius:8px;min-width:220px}
    code{white-space:pre-wrap;word-break:break-word}
    @media (max-width:1100px){.layout{grid-template-columns:1fr} .preview-frame{height:520px}}
        """

    def _clean_dashboard_text(self, html_text: str) -> str:
        replacements = {
            "Xem ná»™i dung": "Open Review",
            "ChÆ°a cÃ³ draft": "No draft yet",
            "ChÃ†Â°a cÃƒÂ³ draft preview.": "No draft preview yet.",
            "KhÃ´ng cÃ³ bÃ i nÃ o trong batch.": "No articles found in this batch.",
            "Quay vá» danh sÃ¡ch": "Back to list",
            "TÃ¡Â»â€ºi bÃƒÂ i cÃ¡ÂºÂ§n duyÃ¡Â»â€¡t tiÃ¡ÂºÂ¿p theo": "Next article to review",
            "Tá»›i bÃ i cáº§n duyá»‡t tiáº¿p theo": "Next article to review",
            "ÄÃ³ng local dashboard": "Close local dashboard",
            "Danh sÃ¡ch bÃ i": "Article list",
            "Approved by human": "Human Approved",
            "Ready for publish": "Ready for Publish",
            "Publish blocked": "Publish Blocked",
        }
        cleaned = html_text
        for before, after in replacements.items():
            cleaned = cleaned.replace(before, after)
        return cleaned

    def _render_interactive_dashboard_v2(self, *, batch_date: str, selected_slug: str = "", message: str = "") -> str:
        payload = self._load_queue(batch_date)
        topics = payload.get("topics", [])
        summary = self.status(batch_date=batch_date)
        publish_rows = {
            str(row.get("slug") or ""): row
            for row in _read_json(self.data_dir / "publish_queue.json", [])
        }
        selected = next((item for item in topics if str(item.get("slug") or "") == selected_slug), None)
        if selected is None and topics:
            selected = next(
                (item for item in topics if self._has_reviewable_preview(item) and str(item.get("status") or "") in {"drafted", "selected"}),
                topics[0],
            )
        rows = [self._render_interactive_row(item, publish_rows=publish_rows, batch_date=batch_date) for item in topics]
        detail_html = self._render_interactive_detail(selected, publish_rows=publish_rows, batch_date=batch_date) if selected is not None else "<p>No articles found in this batch.</p>"
        publish_disabled = summary["ready_for_publish"] == 0
        notice = f"<div class='notice'>{html.escape(message)}</div>" if message else ""
        html_text = f"""<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Interactive Editorial Review Dashboard {html.escape(batch_date)}</title>
  <style>{self._dashboard_style_block()}</style>
</head>
<body>
  <main class="wrap">
    <section class="card">
      <h1>Editorial Review Dashboard - {html.escape(batch_date)}</h1>
      <p>Weekly batch: <strong>{html.escape(summary['week_start'])}</strong> -> <strong>{html.escape(summary['week_end'])}</strong></p>
      <p>Today's angle: <strong>{html.escape(summary['daily_angle'])}</strong></p>
      {self._render_kpi_grid(summary)}
      <p>Total topics: <strong>{summary['total_topics']}</strong> - Drafted: <strong>{summary['drafted']}</strong> - Human Approved: <strong>{summary['approved']}</strong> - Ready for Publish: <strong>{summary['ready_for_publish']}</strong> - Publish Blocked: <strong>{summary['publish_blocked']}</strong> - Published: <strong>{summary['published']}</strong></p>
      <div class="actions">
        <a class="button" href="/?date={html.escape(batch_date, quote=True)}">Back to list</a>
        <a class="button" href="/?date={html.escape(batch_date, quote=True)}&slug={html.escape(self.next_pending_slug(batch_date), quote=True)}">Tá»›i bÃ i cáº§n duyá»‡t tiáº¿p theo</a>
        <a class="button" href="/shutdown">Close local dashboard</a>
      </div>
      {notice}
    </section>
    <section class="layout">
      <section class="card">
        <h2>Danh sÃ¡ch bÃ i</h2>
        {self._render_filter_controls()}
        <table>
          <thead>
            <tr>
              <th>Title</th>
              <th>Keyword</th>
              <th>Score</th>
              <th>Status</th>
              <th>Block reason</th>
              <th>Next action</th>
              <th>Upload path</th>
              <th>View</th>
            </tr>
          </thead>
          <tbody id="article-rows">{''.join(rows)}</tbody>
        </table>
        <form method="post" action="/publish" style="margin-top:16px">
          <input type="hidden" name="date" value="{html.escape(batch_date, quote=True)}">
          <button class="button primary" {'disabled' if publish_disabled else ''}>Publish Ready Articles</button>
        </form>
      </section>
      <section class="card">
        {detail_html}
      </section>
    </section>
  </main>
  {self._render_filter_script()}
</body>
</html>"""
        return self._clean_dashboard_text(html_text)

    def _build_review_dashboard_v2(self, *, batch_date: str) -> dict[str, Any]:
        payload = self._load_queue(batch_date)
        topics = payload.get("topics", [])
        summary = self.status(batch_date=batch_date)
        dashboard_dir = self.review_root / batch_date
        dashboard_dir.mkdir(parents=True, exist_ok=True)
        publish_batch_launcher = self._build_batch_launcher(batch_date=batch_date, file_name="publish-batch.cmd", command=f"python editorial_console.py publish-ready --date {batch_date}")
        refresh_launcher = self._build_batch_launcher(batch_date=batch_date, file_name="refresh-status.cmd", command=f"python editorial_console.py status --date {batch_date}")
        open_console_launcher = self._build_batch_launcher(batch_date=batch_date, file_name="open-operator-console.cmd", command=f'explorer "{self.console.console_html}"', shell_only=True)
        upload_dir = self.upload_root / batch_date
        publish_rows = {
            str(row.get("slug") or ""): row
            for row in _read_json(self.data_dir / "publish_queue.json", [])
        }
        rows: list[str] = []
        for item in topics:
            slug = str(item.get("slug") or "")
            preview_href = f"./{slug}/index.html" if (dashboard_dir / slug / "index.html").exists() else ""
            draft_file = str(item.get("draft_file") or "")
            upload_preview = upload_dir / "review" / slug / "index.html"
            draft_dir = self.data_dir / "production_article_drafts" / slug
            metadata = self.console._load_metadata(slug)
            live_url = str(metadata.get("url") or publish_rows.get(slug, {}).get("url") or "")
            approve_cmd = f"python editorial_console.py approve --slug {slug} --date {batch_date}"
            reject_cmd = f"python editorial_console.py reject --slug {slug} --date {batch_date} --reason \"Needs fixes\""
            approve_launcher = self._build_batch_launcher(batch_date=batch_date, file_name=f"approve-{slug}.cmd", command=approve_cmd)
            reject_launcher = self._build_batch_launcher(batch_date=batch_date, file_name=f"reject-{slug}.cmd", command=reject_cmd)
            open_folder_launcher = self._build_batch_launcher(batch_date=batch_date, file_name=f"open-folder-{slug}.cmd", command=f'explorer "{draft_dir}"', shell_only=True)
            copy_url_launcher = self._build_batch_launcher(
                batch_date=batch_date,
                file_name=f"copy-url-{slug}.cmd",
                command=f'powershell -NoProfile -Command "Set-Clipboard -Value \\"{live_url}\\""',
                shell_only=True,
            )
            status = str(item.get("status") or "selected")
            publish_row = publish_rows.get(slug) or {}
            publish_status = str(publish_row.get("status") or "missing")
            row_filter = "ready" if publish_status == "approved_for_publish" else "published" if publish_status == "published_local" or status == "published" else "needs-revision" if status == "rejected" else "blocked" if publish_status == "blocked" else "waiting"
            can_review = self._has_reviewable_preview(item)
            draft_link = self._review_file_link(batch_date, draft_dir / "article.md")
            html_link = self._review_file_link(batch_date, draft_dir / "index.html")
            review_link = self._review_file_link(batch_date, draft_dir / "review_summary.md")
            ai_report_link = self._review_file_link(batch_date, draft_dir / "publish_readiness_report.md")
            source_review_path = self.data_dir / "research" / slug / "sources.json"
            if not source_review_path.exists():
                source_review_path = self.data_dir / "source_review_report.md"
            source_review_link = self._review_file_link(batch_date, source_review_path)
            action_buttons = " ".join(
                [
                    self._button_link(draft_link, "Open Draft"),
                    self._button_link(html_link or preview_href, "Open HTML"),
                    self._button_link(preview_href, "Open Review"),
                    self._button_link(ai_report_link or review_link, "Open AI Report"),
                    self._button_link(source_review_link, "Open Source Review"),
                    self._button_link(self._relative_review_link(batch_date, open_folder_launcher), "Open Folder"),
                    self._button_link(live_url, "Preview Live", "warn"),
                    self._button_link(self._relative_review_link(batch_date, copy_url_launcher), "Copy URL"),
                ]
            )
            approve_cell = (
                f"<a class='button success' href='{html.escape(self._relative_review_link(batch_date, approve_launcher), quote=True)}'>Approve</a><br><code>{html.escape(approve_cmd)}</code>"
                if can_review
                else "<span class='button disabled'>Publish Blocked</span><br><code>Research/source gate must pass first</code>"
            )
            reject_cell = (
                f"<a class='button danger' href='{html.escape(self._relative_review_link(batch_date, reject_launcher), quote=True)}'>Reject</a><br><code>{html.escape(reject_cmd)}</code>"
                if can_review
                else "<span class='button disabled'>Publish Blocked</span><br><code>No draft to review</code>"
            )
            rows.append(
                f"<tr data-filter='{html.escape(row_filter, quote=True)}'>"
                f"<td><strong>{html.escape(str(item.get('article_title') or item.get('keyword') or slug))}</strong><br><code>{html.escape(slug)}</code></td>"
                f"<td>{html.escape(str(item.get('keyword') or ''))}</td>"
                f"<td>{html.escape(str(item.get('total_score') or ''))}</td>"
                f"<td><span class='status {html.escape(self._status_class(status))}'>{html.escape(self._operator_status_label(status))}</span></td>"
                f"<td>{html.escape(self._row_block_reason(item, publish_row))}</td>"
                f"<td><code>{html.escape(self._next_action_for_item(item, publish_row, batch_date=batch_date))}</code></td>"
                f"<td><div class='actions'>{action_buttons}</div></td>"
                f"<td>{approve_cell}</td>"
                f"<td>{reject_cell}</td>"
                f"<td><code>{html.escape(draft_file)}</code></td>"
                f"<td><code>{html.escape(str(upload_preview))}</code></td>"
                "</tr>"
            )
        html_text = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Editorial Review Dashboard {html.escape(batch_date)}</title>
  <style>{self._dashboard_style_block()}</style>
</head>
<body>
  <main class="wrap">
    <section class="card">
      <h1>Editorial Review Dashboard - {html.escape(batch_date)}</h1>
      <p>Weekly batch: <strong>{html.escape(summary['week_start'])}</strong> -> <strong>{html.escape(summary['week_end'])}</strong></p>
      <p>Today's angle: <strong>{html.escape(summary['daily_angle'])}</strong></p>
      {self._render_kpi_grid(summary)}
      <p>Total topics: <strong>{summary['total_topics']}</strong> - Drafted: <strong>{summary['drafted']}</strong> - Human Approved: <strong>{summary['approved']}</strong> - Ready for Publish: <strong>{summary['ready_for_publish']}</strong> - Publish Blocked: <strong>{summary['publish_blocked']}</strong> - Published: <strong>{summary['published']}</strong></p>
      <p>Next recommended command: <code>{html.escape(summary['next_recommended_command'])}</code></p>
      <div class="actions">
        <a class="button warn" href="{html.escape(self._relative_review_link(batch_date, open_console_launcher), quote=True)}">Open Operator Console</a>
        <a class="button primary" href="{html.escape(self._relative_review_link(batch_date, publish_batch_launcher), quote=True)}">Publish Ready Articles</a>
        <a class="button" href="{html.escape(self._relative_review_link(batch_date, refresh_launcher), quote=True)}">Refresh Status</a>
      </div>
      <p>Open each preview, review it, approve or reject it, then click <strong>Publish Ready Articles</strong>. Only rows that already passed the publish gate will go live.</p>
    </section>
    <section class="card">
      {self._render_filter_controls()}
      <table>
        <thead>
          <tr>
            <th>Title</th>
            <th>Keyword</th>
            <th>Score</th>
            <th>Status</th>
            <th>Block reason</th>
            <th>Next action</th>
            <th>Preview</th>
            <th>Approve</th>
            <th>Reject</th>
            <th>Source file path</th>
            <th>Upload file path</th>
          </tr>
        </thead>
        <tbody id="article-rows">{''.join(rows)}</tbody>
      </table>
    </section>
  </main>
  {self._render_filter_script()}
</body>
</html>
"""
        dashboard_file = dashboard_dir / "index.html"
        dashboard_file.write_text(html_text, encoding="utf-8")
        data = {
            "date": batch_date,
            "summary": summary,
            "topics": topics,
            "dashboard_file": str(dashboard_file),
            "operator_console": str(self.console.console_html),
            "publish_launcher": str(publish_batch_launcher),
            "upload_dir": str(upload_dir),
        }
        _write_json(self._queue_dir(batch_date) / "dashboard.json", data)
        return data

    def _expand_advanced_candidates(self, discovery: Any, *, count: int, brands: set[str]) -> list[dict[str, Any]]:
        advanced: list[dict[str, Any]] = []
        patterns = (
            ("comparison", "{topic} comparison"),
            ("pricing", "{topic} pricing"),
            ("alternatives", "{topic} alternatives"),
            ("tutorial", "how to use {topic}"),
            ("best_for_use_case", "best {topic} for small business"),
            ("review", "{topic} review 2026"),
        )
        for candidate in discovery.selected_topics[: max(4, count)]:
            base = self._candidate_to_queue_item(candidate, brands=brands)
            for content_type, template in patterns:
                keyword = self._build_advanced_keyword(str(base["keyword"]), content_type=content_type, template=template)
                variant = dict(base)
                variant["keyword"] = keyword
                variant["slug"] = slugify(keyword)
                variant["content_type"] = content_type
                variant["search_intent"] = classify_search_intent(keyword)
                variant["search_intent_score"] = _score_search_intent(variant["search_intent"])
                variant["content_freshness_score"] = max(50, int(base["content_freshness_score"]) - (8 if content_type == "tutorial" else 0))
                variant["total_score"] = _score_topic_total(variant)
                variant["why_selected"] = list(base.get("why_selected") or []) + [f"Advanced mode expanded this topic into a {content_type} article."]
                advanced.append(variant)
        deduped: dict[str, dict[str, Any]] = {}
        for item in advanced:
            slug = str(item["slug"])
            existing = deduped.get(slug)
            if existing is None or float(item["total_score"]) > float(existing["total_score"]):
                deduped[slug] = item
        return list(deduped.values())

    def _load_or_create_weekly_batch(self, *, batch_date: str, count: int) -> dict[str, Any]:
        week_start = self._week_start(batch_date)
        manifest_path = self._week_manifest_path(week_start)
        existing = _read_json(manifest_path, {})
        if existing:
            return existing
        discovery = TrendDiscoveryEngine().run(limit=max(count * 3, 30))
        brands = set(load_affiliate_brands())
        candidates = [self._candidate_to_queue_item(candidate, brands=brands) for candidate in discovery.selected_topics]
        published_history = self._load_published_live_history()
        for item in candidates:
            duplicate_warning = self._find_published_live_duplicate(item, published_history)
            item["published_live_duplicate_warning"] = duplicate_warning.get("warning", "")
            item["published_live_duplicate_match"] = duplicate_warning.get("match", {})
            self._apply_duplicate_penalty(item)
        selected = sorted(candidates, key=lambda row: (-float(row["total_score"]), row["keyword"]))[:count]
        for index, item in enumerate(selected, start=1):
            item["rank"] = index
            item["status"] = "weekly_selected"
            item["week_start"] = week_start
            item["parent_keyword"] = str(item.get("keyword") or "")
            item["parent_slug"] = str(item.get("slug") or "")
        week_start_date = date.fromisoformat(week_start)
        duplicate_warning_count = sum(1 for item in selected if str(item.get("published_live_duplicate_warning") or "").strip())
        payload = {
            "generated_at": datetime.now(UTC).isoformat(),
            "week_start": week_start,
            "week_end": (week_start_date + timedelta(days=6)).isoformat(),
            "count": len(selected),
            "source_status": discovery.source_status,
            "duplicate_warning_count": duplicate_warning_count,
            "duplicate_warning_slugs": [str(item.get("slug") or "") for item in selected if str(item.get("published_live_duplicate_warning") or "").strip()],
            "topics": selected,
        }
        _write_json(manifest_path, payload)
        _write_json(self.queue_root / "current_week.json", {"week_start": week_start, "batch_date": batch_date})
        return payload

    def _build_daily_topics_from_weekly_batch(self, *, weekly_topics: list[dict[str, Any]], batch_date: str, mode: str) -> list[dict[str, Any]]:
        week_start = self._week_start(batch_date)
        if mode == "advanced":
            content_type, template = self._advanced_pattern_for_date(batch_date)
            topics: list[dict[str, Any]] = []
            for base in weekly_topics:
                parent_keyword = str(base.get("parent_keyword") or base.get("keyword") or "")
                parent_slug = str(base.get("parent_slug") or base.get("slug") or slugify(parent_keyword))
                keyword = self._build_advanced_keyword(parent_keyword, content_type=content_type, template=template)
                item = dict(base)
                item["keyword"] = keyword
                item["slug"] = slugify(keyword)
                item["content_type"] = content_type
                item["search_intent"] = classify_search_intent(keyword)
                item["search_intent_score"] = _score_search_intent(item["search_intent"])
                item["parent_keyword"] = parent_keyword
                item["parent_slug"] = parent_slug
                item["suggested_article_angle"] = f"{content_type} follow-up for {parent_keyword}"
                item["batch_date"] = batch_date
                item["week_start"] = week_start
                item["mode"] = mode
                item["status"] = "selected"
                item["total_score"] = _score_topic_total(item)
                topics.append(item)
            return topics
        topics = []
        for base in weekly_topics:
            item = dict(base)
            item["keyword"] = str(base.get("parent_keyword") or base.get("keyword") or "")
            item["slug"] = str(base.get("parent_slug") or base.get("slug") or "")
            item["parent_keyword"] = str(base.get("parent_keyword") or item["keyword"])
            item["parent_slug"] = str(base.get("parent_slug") or item["slug"])
            item["batch_date"] = batch_date
            item["week_start"] = week_start
            item["mode"] = mode
            item["status"] = "selected"
            topics.append(item)
        return topics

    def _week_start(self, batch_date: str) -> str:
        current = date.fromisoformat(batch_date)
        return (current - timedelta(days=current.weekday())).isoformat()

    def _week_manifest_path(self, week_start: str) -> Path:
        return self.queue_root / "weeks" / week_start / "week.json"

    def _advanced_pattern_for_date(self, batch_date: str) -> tuple[str, str]:
        weekday = date.fromisoformat(batch_date).weekday()
        return ADVANCED_WEEKDAY_PATTERNS.get(weekday, ("comparison", "{topic} comparison"))

    def _daily_angle_label(self, *, batch_date: str, mode: str) -> str:
        if mode != "advanced":
            return "Week-start hottrend / pillar batch"
        content_type, _ = self._advanced_pattern_for_date(batch_date)
        labels = {
            "pricing": "Deep dive: pricing",
            "alternatives": "Deep dive: alternatives",
            "comparison": "Deep dive: comparison",
            "tutorial": "Deep dive: tutorial",
            "best_for_use_case": "Deep dive: best for use case",
            "review": "Deep dive: review",
        }
        return labels.get(content_type, f"Deep dive: {content_type}")

    def _candidate_to_queue_item(self, candidate: Any, *, brands: set[str]) -> dict[str, Any]:
        keyword = str(getattr(candidate, "topic", ""))
        search_intent = str(getattr(candidate, "search_intent", classify_search_intent(keyword)))
        product_availability, matched_brands = _score_product_availability(keyword, brands)
        item = {
            "keyword": keyword,
            "slug": str(getattr(candidate, "slug", slugify(keyword))),
            "search_intent": search_intent,
            "search_intent_score": _score_search_intent(search_intent),
            "affiliate_monetization_score": int(getattr(candidate, "affiliate_opportunity", 0)),
            "competition_difficulty_score": int(getattr(candidate, "competition", 0)),
            "product_availability_score": product_availability,
            "content_freshness_score": int(getattr(candidate, "news_freshness", 0)),
            "content_type": str(getattr(candidate, "content_type", classify_content_type(keyword))),
            "matched_products": matched_brands,
            "related_keywords": [],
            "source_urls": list(getattr(candidate, "source_urls", []) or []),
            "suggested_internal_links": list(getattr(candidate, "suggested_internal_links", []) or []),
            "suggested_article_angle": str(getattr(candidate, "suggested_article_angle", "")),
            "why_selected": list(getattr(candidate, "why_selected", []) or []),
            "signals": int(getattr(candidate, "signals", 0)),
            "confidence": str(getattr(candidate, "confidence", "")),
        }
        item["total_score"] = _score_topic_total(item)
        item["raw_total_score"] = float(item["total_score"])
        item["duplicate_penalty_applied"] = 0.0
        return item

    def _load_published_live_history(self) -> list[dict[str, Any]]:
        path = self.data_dir / "published_live_urls.jsonl"
        if not path.exists():
            return []
        rows: list[dict[str, Any]] = []
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                rows.append(payload)
        return rows

    def _find_published_live_duplicate(self, item: dict[str, Any], history_rows: list[dict[str, Any]]) -> dict[str, Any]:
        keyword = str(item.get("keyword") or "")
        slug = str(item.get("slug") or "")
        keyword_key = _normalize_duplicate_key(keyword)
        slug_key = _normalize_duplicate_key(slug)
        for row in reversed(history_rows):
            history_slug = str(row.get("slug") or "")
            history_url = str(row.get("url") or "")
            history_title = str(row.get("title") or "")
            history_keyword = str(row.get("keyword") or history_title or history_slug.replace("-", " "))
            history_slug_key = _normalize_duplicate_key(history_slug)
            history_keyword_key = _normalize_duplicate_key(history_keyword)
            url_slug_key = _normalize_duplicate_key(Path(urllib.parse.urlparse(history_url).path).name or Path(urllib.parse.urlparse(history_url).path).parent.name)

            match_reason = ""
            if slug_key and history_slug_key and slug_key == history_slug_key:
                match_reason = "slug_exact_match"
            elif slug_key and history_slug_key and is_near_duplicate(slug_key, history_slug_key):
                match_reason = "slug_near_duplicate"
            elif keyword_key and history_keyword_key and keyword_key == history_keyword_key:
                match_reason = "keyword_exact_match"
            elif keyword_key and history_keyword_key and is_near_duplicate(keyword_key, history_keyword_key):
                match_reason = "keyword_near_duplicate"
            elif slug_key and url_slug_key and (slug_key == url_slug_key or is_near_duplicate(slug_key, url_slug_key)):
                match_reason = "url_slug_duplicate"

            if not match_reason:
                continue
            matched_slug = history_slug or url_slug_key
            matched_title = history_title or history_keyword or matched_slug.replace("-", " ")
            warning = (
                f"Published-live duplicate warning: {match_reason} with "
                f"{matched_slug or matched_title}"
            )
            return {
                "warning": warning,
                "match": {
                    "reason": match_reason,
                    "matched_slug": matched_slug,
                    "matched_keyword": history_keyword,
                    "matched_title": matched_title,
                    "matched_url": history_url,
                    "checked_at": str(row.get("checked_at") or ""),
                    "live_status": str(row.get("live_status") or ""),
                },
            }
        return {"warning": "", "match": {}}

    def _duplicate_penalty_points(self) -> float:
        duplicate_config = dict(self.editorial_config.get("published_live_duplicate_guard", {}) or {})
        penalty = duplicate_config.get("score_penalty", 4.0)
        try:
            return max(0.0, float(penalty))
        except (TypeError, ValueError):
            return 4.0

    def _apply_duplicate_penalty(self, item: dict[str, Any]) -> None:
        raw_score = float(item.get("raw_total_score", item.get("total_score", 0.0)) or 0.0)
        item["raw_total_score"] = raw_score
        warning = str(item.get("published_live_duplicate_warning") or "").strip()
        if not warning:
            item["duplicate_penalty_applied"] = 0.0
            item["total_score"] = _clamp_score(raw_score)
            return
        penalty = self._duplicate_penalty_points()
        item["duplicate_penalty_applied"] = penalty
        item["total_score"] = _clamp_score(raw_score - penalty)

    def _queue_dir(self, batch_date: str) -> Path:
        return self.queue_root / batch_date

    def _load_queue(self, batch_date: str) -> dict[str, Any]:
        path = self._queue_dir(batch_date) / "topics.json"
        payload = _read_json(path, {})
        if not payload:
            raise FileNotFoundError(f"Editorial queue not found for {batch_date}: {path}")
        return payload

    def latest_queue_date(self) -> str:
        if not self.queue_root.exists():
            return ""
        candidates: list[str] = []
        for path in self.queue_root.iterdir():
            if not path.is_dir():
                continue
            if path.name == "weeks":
                continue
            try:
                date.fromisoformat(path.name)
            except ValueError:
                continue
            if (path / "topics.json").exists():
                candidates.append(path.name)
        return max(candidates) if candidates else ""

    def _save_queue(self, batch_date: str, payload: dict[str, Any]) -> None:
        _write_json(self._queue_dir(batch_date) / "topics.json", payload)

    def _copy_review_preview(self, *, slug: str, batch_date: str) -> Path:
        source = self.data_dir / "production_article_drafts" / slug / "index.html"
        if not source.exists():
            raise FileNotFoundError(f"Draft preview missing for {slug}: {source}")
        target = self.review_root / batch_date / slug / "index.html"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        return target

    def _update_batch_status(self, *, batch_date: str, slug: str, status: str, extra: dict[str, Any] | None = None) -> None:
        payload = self._load_queue(batch_date)
        for item in payload.get("topics", []):
            if str(item.get("slug") or "") != slug:
                continue
            item["status"] = status
            if extra:
                item.update(extra)
            break
        self._save_queue(batch_date, payload)

    def _update_batch_status_if_present(self, *, batch_date: str, slug: str, status: str | None = None, extra: dict[str, Any] | None = None) -> None:
        try:
            payload = self._load_queue(batch_date)
        except FileNotFoundError:
            return
        for item in payload.get("topics", []):
            if str(item.get("slug") or "") != slug:
                continue
            if status is not None:
                item["status"] = status
            if extra:
                item.update(extra)
            self._save_queue(batch_date, payload)
            return

    def _upsert_topics_into_batch(self, *, batch_date: str, topics: list[dict[str, Any]], mode: str) -> dict[str, Any]:
        try:
            payload = self._load_queue(batch_date)
        except FileNotFoundError:
            payload = {
                "generated_at": datetime.now(UTC).isoformat(),
                "date": batch_date,
                "week_start": self._week_start(batch_date),
                "week_end": (date.fromisoformat(self._week_start(batch_date)) + timedelta(days=6)).isoformat(),
                "mode": mode,
                "count": 0,
                "topics": [],
            }
        existing = {str(item.get("slug") or ""): item for item in payload.get("topics", [])}
        for topic in topics:
            existing[str(topic.get("slug") or "")] = topic
        merged = list(existing.values())
        payload["generated_at"] = datetime.now(UTC).isoformat()
        payload["mode"] = mode
        payload["count"] = len(merged)
        payload["topics"] = merged
        self._save_queue(batch_date, payload)
        return payload

    def _queue_entry_from_request_result(
        self,
        *,
        keyword: str,
        slug: str,
        result: dict[str, Any],
        batch_date: str,
        category: str,
        intent: str,
        content_type: str,
        source_type: str,
        partner_name: str,
        official_url: str,
        affiliate_url: str,
        pricing_url: str,
        cluster_article_number: int,
        cluster_article_total: int,
        suggested_article_angle: str,
    ) -> dict[str, Any]:
        drafted = bool(result.get("draft"))
        entry = {
            "keyword": keyword,
            "slug": slug,
            "title": keyword,
            "content_type": content_type,
            "search_intent": intent.strip() or "commercial research",
            "search_intent_score": _score_search_intent(intent.strip() or "commercial research"),
            "category": category.strip(),
            "source_type": source_type,
            "partner_name": partner_name.strip(),
            "official_url": official_url.strip(),
            "affiliate_url": affiliate_url.strip(),
            "pricing_url": pricing_url.strip(),
            "cluster_article_number": int(cluster_article_number or 1),
            "cluster_article_total": int(cluster_article_total or 1),
            "suggested_article_angle": suggested_article_angle,
            "status": "drafted" if drafted else "needs_enrichment",
            "batch_date": batch_date,
            "week_start": self._week_start(batch_date),
            "mode": source_type,
            "source_urls": [url for url in [official_url.strip(), affiliate_url.strip(), pricing_url.strip()] if url],
            "draft_dir": str(self.data_dir / "production_article_drafts" / slug) if drafted else "",
            "review_preview": "",
            "research_quality_gate": dict(result.get("quality_gate") or {}),
            "error": "" if drafted else "Research/source quality gate blocked draft generation.",
        }
        if drafted:
            try:
                preview_path = self._copy_review_preview(slug=slug, batch_date=batch_date)
                entry["review_preview"] = str(preview_path)
                entry["draft_file"] = str((self.data_dir / "production_article_drafts" / slug / "index.html"))
                entry["metadata_file"] = str((self.data_dir / "production_article_drafts" / slug / "metadata.json"))
            except FileNotFoundError:
                pass
        return entry

    def _build_custom_topic_requests(self, *, topic_name: str, category: str, intent: str, count: int) -> list[dict[str, str]]:
        normalized = topic_name.strip()
        if not normalized:
            return []
        if int(count or 1) <= 1:
            return [
                {
                    "topic": normalized,
                    "content_type": classify_content_type(normalized),
                    "suggested_article_angle": f"Custom topic request for {normalized}",
                    "category": category.strip(),
                    "intent": intent.strip(),
                }
            ]
        templates = [
            ("review", f"{normalized} review 2026"),
            ("pricing", f"{normalized} pricing"),
            ("alternatives", f"{normalized} alternatives"),
            ("pros_cons", f"{normalized} pros and cons"),
            ("tutorial", f"how to use {normalized}"),
            ("comparison", f"{normalized} vs competitors"),
            ("affiliate_program", f"{normalized} affiliate program"),
            ("faq", f"{normalized} faq"),
        ]
        requests: list[dict[str, str]] = []
        for content_type, topic in templates[: max(1, int(count or 1))]:
            requests.append(
                {
                    "topic": topic,
                    "content_type": content_type,
                    "suggested_article_angle": f"Custom cluster article for {normalized}: {content_type}",
                    "category": category.strip(),
                    "intent": intent.strip(),
                }
            )
        return requests

    def _build_partner_cluster_topics(self, *, partner_name: str, count: int) -> list[dict[str, str]]:
        templates = [
            ("review", f"{partner_name} Review 2026"),
            ("pricing", f"{partner_name} Pricing"),
            ("alternatives", f"{partner_name} Alternatives"),
            ("pros_cons", f"{partner_name} Pros and Cons"),
            ("tutorial", f"How to Use {partner_name}"),
            ("affiliate_program", f"{partner_name} Affiliate Program"),
            ("comparison", f"{partner_name} vs top competitor"),
            ("faq", f"{partner_name} FAQ"),
        ]
        return [
            {
                "topic": topic,
                "content_type": content_type,
                "suggested_article_angle": f"Affiliate partner cluster for {partner_name}: {content_type}",
                "category": "Affiliate Partner",
            }
            for content_type, topic in templates[: max(1, int(count or 8))]
        ]

    def _carry_forward_publish_candidates(self, *, batch_date: str, topics: list[dict[str, Any]], publish_rows: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
        known_slugs = {str(item.get("slug") or "") for item in topics}
        carry_forward: list[dict[str, Any]] = []
        for row in publish_rows.values():
            slug = str(row.get("slug") or "")
            if not slug or slug in known_slugs:
                continue
            status = str(row.get("status") or "")
            if status not in {"approved_for_publish", "published_local"}:
                continue
            metadata = self.console._load_metadata(slug)
            carry_forward.append(
                {
                    "keyword": str(metadata.get("title") or row.get("title") or slug.replace("-", " ")),
                    "slug": slug,
                    "status": "approved" if status == "approved_for_publish" else "published",
                    "carry_forward": True,
                    "batch_date": batch_date,
                }
            )
        return carry_forward

    def _upsert_affiliate_partner_record(self, partner_profile: dict[str, Any]) -> None:
        try:
            from modules.affiliate_links import upsert_affiliate_link
        except Exception:
            return
        upsert_affiliate_link(
            {
                "brand": str(partner_profile.get("name") or ""),
                "slug": str(partner_profile.get("slug") or ""),
                "official_url": str(partner_profile.get("official_url") or ""),
                "affiliate_url": str(partner_profile.get("affiliate_url") or ""),
                "status": "approved" if str(partner_profile.get("affiliate_url") or "").strip() else "official_only",
                "affiliate_status": "approved" if str(partner_profile.get("affiliate_url") or "").strip() else "official_only",
                "notes": str(partner_profile.get("contact_note") or ""),
                "commission_note": str(partner_profile.get("commission_note") or ""),
                "network": str(partner_profile.get("payout_note") or "Direct"),
                "approved": bool(str(partner_profile.get("affiliate_url") or "").strip()),
            }
        )

    def _topic_files_exist(self, item: dict[str, Any]) -> bool:
        draft_file = str(item.get("draft_file") or "")
        preview = str(item.get("review_preview") or "")
        if not draft_file or not preview:
            return False
        return Path(draft_file).exists() and Path(preview).exists()

    def _recommended_command(self, summary: dict[str, Any], *, batch_date: str) -> str:
        if summary["total_topics"] == 0:
            return f"python editorial_console.py trend --count 10 --date {batch_date}"
        if summary["drafted"] + summary["approved"] + summary["rejected"] + summary["published"] == 0:
            return f"python editorial_console.py draft --date {batch_date}"
        if summary.get("ready_for_publish", 0) > 0:
            return f"python editorial_console.py publish-ready --date {batch_date}"
        if summary["approved"] == summary["total_topics"]:
            return f"python editorial_console.py publish --date {batch_date}"
        if summary["published"] == summary["total_topics"]:
            return "Batch already published."
        return f"python editorial_console.py approve --slug <slug> --date {batch_date}"

    def _row_block_reason(self, item: dict[str, Any], publish_row: dict[str, Any]) -> str:
        failures = [str(reason).strip() for reason in list(publish_row.get("failures") or []) if str(reason).strip()]
        if failures:
            return "; ".join(self._operator_block_summary(reason) for reason in failures)
        error = str(item.get("error") or "").strip()
        if error:
            return self._operator_block_summary(error)
        status = str(publish_row.get("status") or item.get("status") or "").strip()
        return self._operator_status_label(status) or "Waiting for review"

    def _next_action_for_item(self, item: dict[str, Any], publish_row: dict[str, Any], *, batch_date: str) -> str:
        slug = str(item.get("slug") or "")
        status = str(item.get("status") or "")
        publish_status = str(publish_row.get("status") or "")
        if publish_status == "approved_for_publish":
            return f"python editorial_console.py publish-ready --date {batch_date}"
        if publish_status == "published_local" or status == "published":
            return "Already published"
        if self._has_reviewable_preview(item) and status in {"drafted", "selected"}:
            return f"python editorial_console.py approve --slug {slug} --date {batch_date}"
        if publish_status == "blocked":
            return self._recommended_action_for_failures(list(publish_row.get("failures") or []))
        if status == "rejected":
            return f"python editorial_console.py reject --slug {slug} --date {batch_date} --reason \"Need revision\""
        return f"python editorial_console.py draft --date {batch_date}"

    def _top_block_reasons(self, publish_rows: list[dict[str, Any]]) -> list[str]:
        counts: dict[str, int] = {}
        for row in publish_rows:
            if str(row.get("status") or "") != "blocked":
                continue
            failures = [str(reason).strip() for reason in list(row.get("failures") or []) if str(reason).strip()]
            if not failures:
                failures = ["blocked"]
            for reason in failures:
                friendly = self._operator_block_title(reason)
                counts[friendly] = counts.get(friendly, 0) + 1
        ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        return [f"{reason} ({count})" for reason, count in ranked[:5]]

    def _status_class(self, status: str) -> str:
        normalized = status.strip().lower()
        if normalized in {"approved", "published", "selected", "drafted", "rejected", "needs_enrichment", "draft_failed"}:
            return normalized
        return "selected"

    def _operator_status_label(self, status: str) -> str:
        normalized = status.strip().lower()
        labels = {
            "approved": "Human Approved",
            "human_approved": "Human Approved",
            "blocked": "Publish Blocked",
            "approved_for_publish": "Ready for Publish",
            "ready_to_publish": "Ready for Publish",
            "ready for publish": "Ready for Publish",
            "published_local": "Published",
            "published": "Published",
            "needs_human_review": "Waiting for editor approval",
            "needs_revision": "Needs revision",
            "drafted": "Drafted",
            "selected": "Selected",
            "missing": "Missing",
        }
        return labels.get(normalized, status.strip())

    def _operator_block_title(self, reason: str) -> str:
        normalized = reason.strip().lower()
        mapping = {
            "verified source score failed": "Need better verified sources",
            "verified source score too low": "Need better verified sources",
            "knowledge freshness failed": "Knowledge needs refresh",
            "ai review failed": "AI quality review required",
            "human approval missing": "Waiting for editor approval",
            "research quality failed": "Research package needs improvement",
            "broken links failed": "Broken links need repair",
            "affiliate disclosure failed": "Affiliate disclosure needs review",
            "duplicate title failed": "Duplicate title needs rewrite",
            "duplicate meta failed": "Duplicate meta description needs rewrite",
            "business score failed": "Business value needs improvement",
            "readability failed": "Readability needs editing",
        }
        for key, label in mapping.items():
            if key in normalized:
                return label
        if "source" in normalized:
            return "Need better verified sources"
        if "freshness" in normalized or "knowledge" in normalized:
            return "Knowledge needs refresh"
        if "review" in normalized and "ai" in normalized:
            return "AI quality review required"
        if "human" in normalized or "approval" in normalized:
            return "Waiting for editor approval"
        return reason.strip() or "Publish gate needs attention"

    def _recommended_action_for_reason(self, reason: str) -> str:
        normalized = reason.strip().lower()
        if "source" in normalized or "verified" in normalized:
            return "Open Source Review"
        if "freshness" in normalized or "knowledge" in normalized:
            return "Refresh Knowledge"
        if "human" in normalized or "approval" in normalized:
            return "Approve Article"
        if "review" in normalized or "quality" in normalized:
            return "Open Review"
        return "Open Review"

    def _operator_block_summary(self, reason: str) -> str:
        title = self._operator_block_title(reason)
        action = self._recommended_action_for_reason(reason)
        return f"{title}. Recommended Action: {action}"

    def _recommended_action_for_failures(self, failures: list[Any]) -> str:
        first = next((str(reason).strip() for reason in failures if str(reason).strip()), "")
        action = self._recommended_action_for_reason(first)
        if action == "Open Source Review":
            return "Open Source Review, add/verify sources, then rerun review"
        if action == "Refresh Knowledge":
            return "Refresh Knowledge, then rerun review"
        if action == "Approve Article":
            return "Approve Article after editor review"
        return "Open Review, fix blockers, then rerun publish validation"

    def _has_reviewable_preview(self, item: dict[str, Any]) -> bool:
        review_preview = str(item.get("review_preview") or "").strip()
        if review_preview:
            return Path(review_preview).exists()
        slug = str(item.get("slug") or "").strip()
        if not slug:
            return False
        batch_date = str(item.get("batch_date") or "").strip()
        review_preview_path = self.review_root / batch_date / slug / "index.html" if batch_date else None
        draft_preview = self.data_dir / "production_article_drafts" / slug / "index.html"
        return draft_preview.exists() or (review_preview_path is not None and review_preview_path.exists())

    def _build_advanced_keyword(self, base_keyword: str, *, content_type: str, template: str) -> str:
        keyword = _normalize_space(base_keyword)
        lower = keyword.lower()
        if content_type == "review":
            if "review" in lower:
                if any(char.isdigit() for char in keyword):
                    return keyword
                return _normalize_space(f"{keyword} 2026")
            return _normalize_space(f"{keyword} review 2026")
        guards = {
            "comparison": "comparison",
            "pricing": "pricing",
            "alternatives": "alternatives",
            "tutorial": "how to use",
            "best_for_use_case": "for small business",
        }
        guard = guards.get(content_type, "")
        if guard and guard in lower:
            return keyword
        return _normalize_space(template.format(topic=keyword).strip())

    def _relative_review_link(self, batch_date: str, path: Path) -> str:
        dashboard_dir = self.review_root / batch_date
        return path.relative_to(dashboard_dir).as_posix()

    def _review_file_link(self, batch_date: str, path: Path) -> str:
        if not path.exists():
            return ""
        dashboard_dir = self.review_root / batch_date
        return Path(os.path.relpath(path, dashboard_dir)).as_posix()

    def _button_link(self, href: str, label: str, tone: str = "") -> str:
        class_name = "button" + (f" {tone}" if tone else "")
        if not href:
            return f'<span class="{class_name} disabled">{html.escape(label)}</span>'
        return f'<a class="{class_name}" href="{html.escape(href, quote=True)}">{html.escape(label)}</a>'

    def _build_batch_launcher(self, *, batch_date: str, file_name: str, command: str, shell_only: bool = False) -> Path:
        actions_dir = self.review_root / batch_date / "actions"
        actions_dir.mkdir(parents=True, exist_ok=True)
        path = actions_dir / file_name
        if shell_only:
            lines = ["@echo off", command, "pause", ""]
        else:
            lines = ["@echo off", 'cd /d "%~dp0\\..\\..\\..\\.."', command, "pause", ""]
        path.write_text("\n".join(lines), encoding="utf-8")
        return path

    def _sync_upload_batch(self, *, batch_date: str) -> dict[str, Any]:
        batch_dir = self.upload_root / batch_date
        batch_dir.mkdir(parents=True, exist_ok=True)
        self.console.build_console()
        payload = self._load_queue(batch_date)
        topics = payload.get("topics", [])
        copied: list[str] = []

        review_dashboard = self.review_root / batch_date / "index.html"
        if review_dashboard.exists():
            copied.append(str(self._copy_file(review_dashboard, batch_dir / "review_dashboard.html")))

        queue_json = self._queue_dir(batch_date) / "topics.json"
        if queue_json.exists():
            copied.append(str(self._copy_file(queue_json, batch_dir / "topics.json")))

        dashboard_json = self._queue_dir(batch_date) / "dashboard.json"
        if dashboard_json.exists():
            copied.append(str(self._copy_file(dashboard_json, batch_dir / "dashboard.json")))

        for item in topics:
            slug = str(item.get("slug") or "")
            if not slug:
                continue
            draft_dir = self.data_dir / "production_article_drafts" / slug
            review_preview = self.review_root / batch_date / slug / "index.html"
            upload_review_dir = batch_dir / "review" / slug
            upload_draft_dir = batch_dir / "drafts" / slug
            if review_preview.exists():
                copied.append(str(self._copy_file(review_preview, upload_review_dir / "index.html")))
            for name in ("index.html", "article.md", "metadata.json", "review_summary.md", "publish_readiness_report.md"):
                source = draft_dir / name
                if source.exists():
                    copied.append(str(self._copy_file(source, upload_draft_dir / name)))

        self._write_upload_batch_helpers(batch_date=batch_date)
        self._validate_html_tree(self.review_root / batch_date, scope=f"review/{batch_date}")
        self._validate_html_tree(batch_dir, scope=f"upload/{batch_date}")
        return {"batch_dir": str(batch_dir), "copied_files": copied, "count": len(copied)}

    def _write_upload_batch_helpers(self, *, batch_date: str) -> None:
        batch_dir = self.upload_root / batch_date
        review_dashboard = self.review_root / batch_date / "index.html"
        helpers = {
            "open_dashboard.cmd": f'explorer "{review_dashboard}"',
            "publish_approved.cmd": f"python editorial_console.py publish-ready --date {batch_date}",
            "status.cmd": f"python editorial_console.py status --date {batch_date}",
        }
        for file_name, command in helpers.items():
            path = batch_dir / file_name
            lines = ["@echo off"]
            if command.startswith("python "):
                lines.append('cd /d "%~dp0\\.."')
            lines.extend([command, "pause", ""])
            path.write_text("\n".join(lines), encoding="utf-8")

    def _build_upload_master_dashboard(self) -> Path:
        self.upload_root.mkdir(parents=True, exist_ok=True)
        batches = sorted([path for path in self.upload_root.iterdir() if path.is_dir()], reverse=True)
        items: list[str] = []
        for batch_dir in batches:
            batch_date = batch_dir.name
            payload = _read_json(self._queue_dir(batch_date) / "topics.json", {})
            topics = payload.get("topics", [])
            operator_console_href = os.path.relpath(self.console.console_html, self.upload_root).replace("\\", "/")
            publish_status_href = os.path.relpath(self.data_dir / "publish_gate_report.md", self.upload_root).replace("\\", "/")
            queue_report_href = os.path.relpath(self.data_dir / "content_review_report.md", self.upload_root).replace("\\", "/")
            article_links = []
            for item in topics:
                slug = str(item.get("slug") or "")
                preview = batch_dir / "review" / slug / "index.html"
                if preview.exists():
                    article_links.append(f'<li><a href="{html.escape(preview.relative_to(self.upload_root).as_posix(), quote=True)}">{html.escape(slug)}</a></li>')
            items.append(
                "<section class='card'>"
                f"<h2>{html.escape(batch_date)}</h2>"
                f"<p><a href='{html.escape((batch_dir / 'review_dashboard.html').relative_to(self.upload_root).as_posix(), quote=True)}'>Today's review dashboard</a></p>"
                f"<p><a href='{html.escape(operator_console_href, quote=True)}'>Operator console</a></p>"
                f"<p><a href='{html.escape(batch_dir.relative_to(self.upload_root).as_posix(), quote=True)}'>Upload folder</a></p>"
                f"<p><a href='{html.escape(publish_status_href, quote=True)}'>Publish status</a></p>"
                f"<p><a href='{html.escape(queue_report_href, quote=True)}'>Queue reports</a></p>"
                f"<ul>{''.join(article_links) or '<li>No previews copied yet.</li>'}</ul>"
                "</section>"
            )
        html_text = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Upload Dashboard</title>
  <style>
    body{{font-family:Arial,sans-serif;background:#f4f6fb;color:#18212f;margin:0;padding:24px}}
    .wrap{{max-width:1100px;margin:0 auto}}
    .card{{background:#fff;border:1px solid #dbe4f0;border-radius:14px;padding:18px;margin:16px 0}}
    a{{color:#0f766e;text-decoration:none}}
  </style>
</head>
<body>
  <main class="wrap">
    <section class="card">
      <h1>Upload Dashboard</h1>
      <p>Open today's review dashboard, preview copied article files, check publish status, and access queue reports from one place.</p>
    </section>
    {''.join(items) or "<section class='card'><p>No upload batches yet.</p></section>"}
  </main>
</body>
</html>
"""
        path = self.upload_root / "dashboard.html"
        path.write_text(html_text, encoding="utf-8")
        return path

    def _check_live_items(self, *, batch_date: str, include_all: bool = False) -> list[dict[str, Any]]:
        payload = _read_json(self._queue_dir(batch_date) / "topics.json", {})
        queue_topics = list(payload.get("topics") or [])
        publish_rows = {
            str(row.get("slug") or ""): row
            for row in _read_json(self.data_dir / "publish_queue.json", [])
        }
        if include_all:
            candidate_slugs = [slug for slug in publish_rows.keys() if slug]
        elif queue_topics:
            candidate_slugs = [str(item.get("slug") or "") for item in queue_topics if str(item.get("slug") or "")]
        else:
            candidate_slugs = [slug for slug in publish_rows.keys() if slug]

        items: list[dict[str, Any]] = []
        for slug in candidate_slugs:
            publish_row = publish_rows.get(slug) or {}
            metadata = self.console._load_metadata(slug)
            site_file = self.site_output_dir / slug / "index.html"
            docs_file = self.root / "docs" / slug / "index.html"
            local_article_file = self.data_dir / "published_static_pages" / slug / "index.html"
            url = str(metadata.get("url") or publish_row.get("url") or "")
            local_exists = site_file.exists() or local_article_file.exists()
            docs_exists = docs_file.exists()
            git_status = self._git_file_publish_status(docs_file if docs_exists else site_file)
            live_probe = self._probe_live_url(url) if url else {"status": "unknown", "http_status": None, "reason": "missing url"}
            local_status = "local_only" if local_exists and not docs_exists else ("docs_synced" if docs_exists else "missing_local")
            diagnosis = self._diagnose_live_item(
                slug=slug,
                batch_date=batch_date,
                publish_row=publish_row,
                local_status=local_status,
                git_status=git_status,
                live_probe=live_probe,
                url=url,
            )
            display_status = self._live_display_status(
                publish_row=publish_row,
                local_status=local_status,
                docs_exists=docs_exists,
                git_status=git_status,
                live_probe=live_probe,
            )
            items.append(
                {
                    "slug": slug,
                    "title": str(metadata.get("title") or publish_row.get("title") or slug),
                    "publish_queue_status": str(publish_row.get("status") or "missing"),
                    "publish_queue_label": self._operator_status_label(str(publish_row.get("status") or "missing")),
                    "local_status": local_status,
                    "site_output_exists": site_file.exists(),
                    "published_static_exists": local_article_file.exists(),
                    "docs_synced": docs_exists,
                    "git_status": git_status["status"],
                    "git_reason": git_status["reason"],
                    "url": url,
                    "live_status": live_probe["status"],
                    "display_status": display_status,
                    "live_http_status": live_probe.get("http_status"),
                    "live_reason": live_probe.get("reason", ""),
                    "block_reason": diagnosis["block_reason"],
                    "resolution": diagnosis["resolution"],
                    "next_action_command": diagnosis["next_action_command"],
                    "site_output_file": str(site_file),
                    "docs_file": str(docs_file),
                    "published_static_file": str(local_article_file),
                }
            )
        return items

    def _live_display_status(
        self,
        *,
        publish_row: dict[str, Any],
        local_status: str,
        docs_exists: bool,
        git_status: dict[str, str],
        live_probe: dict[str, Any],
    ) -> str:
        queue_status = str(publish_row.get("status") or "missing")
        git_state = str(git_status.get("status") or "")
        live_state = str(live_probe.get("status") or "")
        published_states = {"published_local", "published"}
        awaiting_states = {"missing", "selected", "drafted", "needs_human_review", "needs_revision"}
        if queue_status == "blocked":
            return "Blocked"
        if local_status == "missing_local":
            return "Missing Local Output"
        if queue_status in awaiting_states:
            return "Awaiting Publish"
        if not docs_exists or local_status == "local_only":
            return "Docs Pending"
        if git_state in {"not_synced", "not_committed", "not_pushed"}:
            return "Awaiting Push"
        if queue_status in published_states and live_state == "404":
            return "Live 404"
        if live_state == "live":
            return "Published"
        if queue_status == "approved_for_publish":
            return "Ready"
        return "Unknown"

    def _diagnose_live_item(
        self,
        *,
        slug: str,
        batch_date: str,
        publish_row: dict[str, Any],
        local_status: str,
        git_status: dict[str, str],
        live_probe: dict[str, Any],
        url: str,
    ) -> dict[str, str]:
        queue_status = str(publish_row.get("status") or "missing")
        failures = [str(item).strip() for item in list(publish_row.get("failures") or []) if str(item).strip()]
        git_state = str(git_status.get("status") or "")
        live_state = str(live_probe.get("status") or "")

        if queue_status == "blocked":
            failure_text = "; ".join(self._operator_block_summary(reason) for reason in failures) if failures else "Publish gate is still blocking this article."
            return {
                "block_reason": f"Publish Blocked: {failure_text}",
                "resolution": "Recommended Action: Open Review or Open Source Review, fix the failing gate, then rerun publish validation.",
                "next_action_command": f"python editorial_console.py serve --date {batch_date} --open",
            }
        if queue_status in {"needs_human_review", "needs_revision"}:
            return {
                "block_reason": self._operator_status_label(queue_status),
                "resolution": "Recommended Action: Open Review, then approve or send back for revision before publish.",
                "next_action_command": f"python editorial_console.py serve --date {batch_date} --open",
            }
        if queue_status in {"missing", "selected", "drafted"} or local_status == "missing_local":
            return {
                "block_reason": "Awaiting Publish",
                "resolution": "Recommended Action: create or refresh the draft. If the research/source gate blocks it, add sources and rerun review.",
                "next_action_command": f"python editorial_console.py draft --date {batch_date}",
            }
        if local_status == "local_only":
            return {
                "block_reason": "Docs Pending",
                "resolution": "Recommended Action: run publish-ready so the local output is copied into docs for GitHub Pages.",
                "next_action_command": f"python editorial_console.py publish-ready --date {batch_date}",
            }
        if git_state in {"not_synced", "not_committed", "not_pushed"}:
            return {
                "block_reason": f"Awaiting Push: {git_status.get('reason', '')}",
                "resolution": "Recommended Action: rerun publish-ready so docs/site files are added, committed, and pushed.",
                "next_action_command": f"python editorial_console.py publish-ready --date {batch_date}",
            }
        if not url.strip():
            return {
                "block_reason": "Missing public URL",
                "resolution": "Recommended Action: rebuild metadata or the publish queue, then run publish-ready again.",
                "next_action_command": f"python editorial_console.py publish-ready --date {batch_date}",
            }
        if live_state == "404":
            return {
                "block_reason": "Live 404",
                "resolution": "Recommended Action: if git was just pushed, wait and rerun check-live. If it remains 404, inspect docs sync and GitHub Pages deployment.",
                "next_action_command": f"python editorial_console.py check-live --date {batch_date} --open",
            }
        if live_state == "unknown":
            return {
                "block_reason": f"Unknown live status: {live_probe.get('reason', '')}",
                "resolution": "Recommended Action: rerun check-live. If it still fails, inspect network, domain, or GitHub Pages configuration.",
                "next_action_command": f"python editorial_console.py check-live --date {batch_date} --open",
            }
        return {
            "block_reason": "No blocking issue detected",
            "resolution": "Article appears ready or already published.",
            "next_action_command": "",
        }

        if queue_status == "blocked":
            failure_text = "; ".join(failures) if failures else "publish gate vẫn đang chặn bài này"
            return {
                "block_reason": f"Publish gate đang chặn: {failure_text}",
                "resolution": "Mở báo cáo review/publish, sửa đúng điều kiện đang fail, rồi duyệt lại bài trước khi publish.",
                "next_action_command": f"python editorial_console.py serve --date {batch_date} --open",
            }
        if queue_status in {"needs_human_review", "needs_revision"}:
            return {
                "block_reason": f"Trạng thái hàng đợi hiện tại là {queue_status}",
                "resolution": "Mở dashboard, xem lại bài, rồi approve hoặc sửa/reject trước khi publish.",
                "next_action_command": f"python editorial_console.py serve --date {batch_date} --open",
            }
        if queue_status in {"missing", "selected", "drafted"} or local_status == "missing_local":
            return {
                "block_reason": "Chưa có bài local đủ điều kiện để publish",
                "resolution": "Hãy tạo draft hoặc tạo lại draft trước. Nếu bị research/source gate chặn thì cần bổ sung nguồn rồi chạy lại.",
                "next_action_command": f"python editorial_console.py draft --date {batch_date}",
            }
        if local_status == "local_only":
            return {
                "block_reason": "Đã có bài local nhưng chưa copy sang docs",
                "resolution": "Chạy publish-ready/publish để copy bài sang docs và chuẩn bị cho GitHub Pages.",
                "next_action_command": f"python editorial_console.py publish-ready --date {batch_date}",
            }
        if git_state in {"not_synced", "not_committed", "not_pushed"}:
            return {
                "block_reason": f"File docs chưa lên origin/main: {git_status.get('reason', '')}",
                "resolution": "Chạy lại bước publish để bot git add, commit và push các file docs/site cần thiết.",
                "next_action_command": f"python editorial_console.py publish-ready --date {batch_date}",
            }
        if not url.strip():
            return {
                "block_reason": "Bài chưa có URL public trong metadata",
                "resolution": "Hãy rebuild metadata/publish queue cho bài này rồi chạy publish lại.",
                "next_action_command": f"python editorial_console.py publish-ready --date {batch_date}",
            }
        if live_state == "404":
            return {
                "block_reason": "Domain/GitHub Pages vẫn đang trả về 404",
                "resolution": "Nếu đã push git thì chờ vài phút rồi check-live lại. Nếu vẫn 404, kiểm tra docs sync và cấu hình deploy GitHub Pages.",
                "next_action_command": f"python editorial_console.py check-live --date {batch_date} --open",
            }
        if live_state == "unknown":
            return {
                "block_reason": f"Chưa xác định được trạng thái live: {live_probe.get('reason', '')}",
                "resolution": "Chạy lại check-live. Nếu vẫn lỗi, kiểm tra mạng, domain hoặc cấu hình GitHub Pages.",
                "next_action_command": f"python editorial_console.py check-live --date {batch_date} --open",
            }
        return {
            "block_reason": "Không phát hiện lỗi chặn",
            "resolution": "Bài có vẻ đã sẵn sàng hoặc đã live.",
            "next_action_command": "",
        }

    def _git_branch_sync_status(self) -> dict[str, Any]:
        result = self._run_command(["git", "rev-list", "--left-right", "--count", "origin/main...HEAD"], cwd=self.root)
        if result["returncode"] != 0:
            return {"status": "unknown", "ahead": None, "behind": None, "reason": (result["stderr"] or result["stdout"]).strip()}
        parts = (result["stdout"] or "").strip().split()
        if len(parts) != 2:
            return {"status": "unknown", "ahead": None, "behind": None, "reason": "unexpected git rev-list output"}
        behind = int(parts[0])
        ahead = int(parts[1])
        status = "in_sync"
        if ahead > 0:
            status = "ahead_of_origin"
        elif behind > 0:
            status = "behind_origin"
        return {"status": status, "ahead": ahead, "behind": behind, "reason": ""}

    def _git_file_publish_status(self, path: Path) -> dict[str, str]:
        if not path.exists():
            return {"status": "not_synced", "reason": "file missing from docs/site_output"}
        try:
            rel = str(path.relative_to(self.root)).replace("\\", "/")
        except ValueError:
            rel = str(path).replace("\\", "/")
        tracked = self._run_command(["git", "ls-files", "--error-unmatch", rel], cwd=self.root)
        if tracked["returncode"] != 0:
            return {"status": "not_committed", "reason": "file not tracked by git"}
        commit = self._run_command(["git", "log", "-1", "--format=%H", "--", rel], cwd=self.root)
        commit_hash = (commit["stdout"] or "").strip()
        if not commit_hash:
            return {"status": "not_committed", "reason": "no git commit found for file"}
        ancestor = self._run_command(["git", "merge-base", "--is-ancestor", commit_hash, "origin/main"], cwd=self.root)
        if ancestor["returncode"] == 0:
            return {"status": "pushed", "reason": "file commit is contained in origin/main"}
        return {"status": "not_pushed", "reason": "file commit is not yet contained in origin/main"}

    def _probe_live_url(self, url: str) -> dict[str, Any]:
        request = urllib.request.Request(url, headers={"User-Agent": "SmileAIReviewHub/1.0"})
        try:
            with urllib.request.urlopen(request, timeout=6) as response:
                http_status = int(getattr(response, "status", 200))
                return {
                    "status": "live" if 200 <= http_status < 400 else str(http_status),
                    "http_status": http_status,
                    "reason": "reachable",
                }
        except urllib.error.HTTPError as exc:
            return {"status": "404" if exc.code == 404 else str(exc.code), "http_status": exc.code, "reason": str(exc)}
        except Exception as exc:
            return {"status": "unknown", "http_status": None, "reason": str(exc)}

    def _render_live_status_markdown(self, report: dict[str, Any]) -> str:
        summary = report["summary"]
        lines = [
            f"# Live Status Report {report['date']}",
            "",
            f"- Total items: {summary['total_items']}",
            f"- Published: {summary['published']}",
            f"- Awaiting Publish: {summary['awaiting_publish']}",
            f"- Awaiting Push: {summary['awaiting_push']}",
            f"- Missing Docs: {summary['missing_docs']}",
            f"- Blocked: {summary['blocked']}",
            f"- Ready: {summary['ready']}",
            f"- Unknown: {summary['unknown']}",
            "",
            "| Slug | Queue | Local | Docs | Git | Status | Block reason | How to fix | URL |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
        for item in report["items"]:
            lines.append(
                f"| {item['slug']} | {item['publish_queue_label']} | {item['local_status']} | {'yes' if item['docs_synced'] else 'no'} | {item['git_status']} | {item['display_status']} | {item['block_reason'] or '-'} | {item['resolution'] or '-'} | {item['url'] or '-'} |"
            )
        return "\n".join(lines) + "\n"

    def _render_live_status_html(self, report: dict[str, Any]) -> str:
        summary = report["summary"]
        rows = []
        for item in report["items"]:
            rows.append(
                "<tr>"
                f"<td><strong>{html.escape(item['title'])}</strong><br><code>{html.escape(item['slug'])}</code></td>"
                f"<td>{html.escape(item['publish_queue_label'])}</td>"
                f"<td>{html.escape(item['local_status'])}</td>"
                f"<td>{'yes' if item['docs_synced'] else 'no'}</td>"
                f"<td>{html.escape(item['git_status'])}<br><small>{html.escape(item['git_reason'])}</small></td>"
                f"<td>{html.escape(item['display_status'])}<br><small>{html.escape(str(item['live_http_status'] or item['live_reason']))}</small></td>"
                f"<td>{html.escape(item['block_reason'])}</td>"
                f"<td>{html.escape(item['resolution'])}{('<br><code>' + html.escape(item['next_action_command']) + '</code>') if item['next_action_command'] else ''}</td>"
                f"<td><a href='{html.escape(item['url'], quote=True)}'>{html.escape(item['url'])}</a></td>"
                f"<td><code>{html.escape(item['docs_file'])}</code></td>"
                "</tr>"
            )
        return f"""<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Live Status Report</title>
  <style>
    body{{font-family:Arial,sans-serif;background:#f6f8fb;color:#152033;margin:0;padding:24px}}
    .wrap{{max-width:1400px;margin:0 auto}}
    .card{{background:#fff;border:1px solid #d8e1ec;border-radius:14px;padding:20px;margin:16px 0}}
    .kpis{{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px}}
    .kpi{{background:#f8fafc;border:1px solid #d8e1ec;border-radius:10px;padding:12px}}
    .kpi strong{{display:block;font-size:1.4rem;margin-top:6px}}
    table{{width:100%;border-collapse:collapse}}
    th,td{{border-bottom:1px solid #e5edf6;padding:12px;text-align:left;vertical-align:top}}
    th{{background:#f1f5f9}}
    code{{white-space:pre-wrap;word-break:break-word}}
  </style>
</head>
<body>
  <main class="wrap">
    <section class="card">
      <h1>Live Status Report - {html.escape(report['date'])}</h1>
      <p>Use this report to see whether each article is published, waiting for approval, pending docs sync, waiting for push, or unexpectedly failing on the live domain.</p>
      <div class="kpis">
        <div class="kpi">Published<strong>{summary['published']}</strong></div>
        <div class="kpi">Awaiting Publish<strong>{summary['awaiting_publish']}</strong></div>
        <div class="kpi">Awaiting Push<strong>{summary['awaiting_push']}</strong></div>
        <div class="kpi">Missing Docs<strong>{summary['missing_docs']}</strong></div>
        <div class="kpi">Blocked<strong>{summary['blocked']}</strong></div>
        <div class="kpi">Ready<strong>{summary['ready']}</strong></div>
        <div class="kpi">Unknown<strong>{summary['unknown']}</strong></div>
      </div>
    </section>
    <section class="card">
      <table>
        <thead>
          <tr>
            <th>Article</th>
            <th>Queue</th>
            <th>Local</th>
            <th>Docs</th>
            <th>Git</th>
            <th>Status</th>
            <th>Block reason</th>
            <th>How to fix</th>
            <th>URL</th>
            <th>Docs path</th>
          </tr>
        </thead>
        <tbody>{''.join(rows)}</tbody>
      </table>
    </section>
  </main>
</body>
</html>
"""

    def _finalize_production_publish(self, *, batch_date: str, published: list[dict[str, Any]], commit_message: str, validation_mode: str = "smart") -> dict[str, Any]:
        self._report_progress(f"[1/6] Building site_output for {batch_date}")
        build_result = incremental_build()
        self._report_progress(f"[1/6] Build completed for {batch_date}")
        sync_result = self._run_command(
            [sys.executable, "scripts/sync_site_output_to_docs.py"],
            cwd=self.root,
            check=True,
            label="[2/6] Sync site_output -> docs",
        )
        self._sync_docs_for_published(published)
        self._report_progress(f"[3/6] Running {validation_mode} publish validation")
        validation_report = self._run_publish_validation(batch_date=batch_date, published=published, mode=validation_mode)
        valid_published = list(validation_report.get("published") or [])
        skipped = list(validation_report.get("skipped") or [])
        for item in list(validation_report.get("items") or []):
            slug = str(item.get("slug") or "")
            if not slug:
                continue
            if str(item.get("validation_status") or "") == "passed":
                self._update_batch_status_if_present(
                    batch_date=batch_date,
                    slug=slug,
                    status="published",
                    extra={"published_at": datetime.now(UTC).isoformat(), **self._validation_dashboard_fields(item, mode=validation_mode)},
                )
            else:
                self._update_batch_status_if_present(
                    batch_date=batch_date,
                    slug=slug,
                    extra=self._validation_dashboard_fields(item, mode=validation_mode),
                )
        if validation_mode == "strict":
            self._validate_html_tree(self.site_output_dir, scope="site_output")
            self._validate_html_tree(self.root / "docs", scope="docs")
        if not valid_published:
            dashboard = self.build_review_dashboard(batch_date=batch_date)
            upload_summary = self._sync_upload_batch(batch_date=batch_date)
            publish_report = self._write_publish_report(
                batch_date=batch_date,
                published=[],
                skipped=skipped,
                validation=validation_report,
                build_result=build_result,
                post_push_live_check={"status": "not_run", "message": "No publishable articles passed validation.", "attempts": [], "items": []},
            )
            master_dashboard = self._build_upload_master_dashboard()
            return {
                "date": batch_date,
                "published": [],
                "published_count": 0,
                "skipped": skipped,
                "skipped_count": len(skipped),
                "build": build_result,
                "sync_docs": sync_result,
                "validation": validation_report,
                "git_push": {"status": "skipped", "reason": "No publishable articles passed validation."},
                "post_push_live_check": {"status": "not_run", "message": "No publishable articles passed validation.", "attempts": [], "items": []},
                "live_url_history": {},
                "dashboard": dashboard,
                "upload_dir": str(self.upload_root / batch_date),
                "publish_report": str(publish_report),
                "master_dashboard": str(master_dashboard),
                "upload_summary": upload_summary,
            }
        stage_paths = self._publish_stage_paths(batch_date=batch_date, published=valid_published)
        self._run_command(["git", "add", "--", *stage_paths], cwd=self.root, check=True, label="[4/6] Git add published docs/site_output/data/upload")
        self._run_command(["git", "commit", "-m", commit_message], cwd=self.root, check=True, label="[5/6] Git commit")
        push_result = self._run_command(["git", "push", "origin", "main"], cwd=self.root, check=True, label="[6/6] Git push origin main")
        post_push_live_check = self._verify_live_after_push(valid_published)
        live_url_history = self._write_live_url_history(batch_date=batch_date, live_check=post_push_live_check, published=valid_published)
        self._report_progress("[done] Publish workflow completed")
        dashboard = self.build_review_dashboard(batch_date=batch_date)
        upload_summary = self._sync_upload_batch(batch_date=batch_date)
        publish_report = self._write_publish_report(
            batch_date=batch_date,
            published=valid_published,
            skipped=skipped,
            validation=validation_report,
            build_result=build_result,
            post_push_live_check=post_push_live_check,
        )
        master_dashboard = self._build_upload_master_dashboard()
        return {
            "date": batch_date,
            "published": valid_published,
            "published_count": len(valid_published),
            "skipped": skipped,
            "skipped_count": len(skipped),
            "build": build_result,
            "sync_docs": sync_result,
            "validation": validation_report,
            "git_push": push_result,
            "post_push_live_check": post_push_live_check,
            "live_url_history": live_url_history,
            "dashboard": dashboard,
            "upload_dir": str(self.upload_root / batch_date),
            "publish_report": str(publish_report),
            "master_dashboard": str(master_dashboard),
            "upload_summary": upload_summary,
        }

    def _write_publish_report(
        self,
        *,
        batch_date: str,
        published: list[dict[str, Any]],
        skipped: list[dict[str, Any]],
        validation: dict[str, Any],
        build_result: Any,
        post_push_live_check: dict[str, Any],
    ) -> Path:
        report = self.upload_root / batch_date / "publish_report.md"
        lines = [
            f"# Publish Report {batch_date}",
            "",
            f"- Published count: {len(published)}",
            f"- Skipped count: {len(skipped)}",
            f"- Validation mode: {validation.get('mode', '')}",
            f"- Validation status: published={validation.get('total_published', len(published))}, skipped={validation.get('total_skipped', len(skipped))}",
            f"- Build result: `{build_result}`",
            f"- Post-push live status: `{post_push_live_check.get('status', 'unknown')}`",
            f"- Post-push live message: {post_push_live_check.get('message', '')}",
            "",
            "## Published files",
        ]
        for item in published:
            lines.append(f"- `{item['slug']}`")
            lines.append(f"  site_output: `{item['site_file']}`")
            lines.append(f"  article_file: `{item['article_file']}`")
        if skipped:
            lines.extend(["", "## Skipped articles"])
            for item in skipped:
                lines.append(f"- `{item.get('slug', '')}`: {item.get('reason', item.get('status', 'skipped'))}")
        if post_push_live_check.get("attempts"):
            lines.extend(["", "## Post-push live verification"])
            for attempt in post_push_live_check["attempts"]:
                lines.append(
                    f"- attempt {attempt.get('attempt')} after {attempt.get('wait_seconds')}s: "
                    f"{attempt.get('live_count')}/{attempt.get('total_count')} live"
                )
        report.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return report

    def _verify_live_after_push(self, published: list[dict[str, Any]]) -> dict[str, Any]:
        urls = [(str(item.get("slug") or ""), str(item.get("url") or "")) for item in published if str(item.get("url") or "").strip()]
        if not urls:
            return {"status": "unknown", "message": "No published URLs available for live verification.", "attempts": [], "items": []}
        attempts: list[dict[str, Any]] = []
        last_items: list[dict[str, Any]] = []
        for attempt_number, wait_seconds in enumerate(self.post_push_live_waits, start=1):
            if wait_seconds > 0:
                self._report_progress(f"[post-push] Waiting {wait_seconds}s before live domain check attempt {attempt_number}")
                self.sleep_fn(wait_seconds)
            probe_items = []
            live_count = 0
            for slug, url in urls:
                probe = self._probe_live_url(url)
                if probe.get("status") == "live":
                    live_count += 1
                probe_items.append({"slug": slug, "url": url, **probe})
            attempts.append(
                {
                    "attempt": attempt_number,
                    "wait_seconds": wait_seconds,
                    "live_count": live_count,
                    "total_count": len(urls),
                    "items": probe_items,
                }
            )
            last_items = probe_items
            if live_count == len(urls):
                message = f"Website live OK: {live_count}/{len(urls)} URLs returned 200/3xx after push."
                self._report_progress(f"[post-push] {message}")
                return {"status": "live_ok", "message": message, "attempts": attempts, "items": probe_items}
            self._report_progress(
                f"[post-push] Attempt {attempt_number}: {live_count}/{len(urls)} URLs live. GitHub push OK but Pages may still be updating."
            )
        message = f"GitHub push OK but Pages chua cap nhat xong: 0/{len(urls)} or not all URLs are live yet."
        if last_items:
            live_count = sum(1 for item in last_items if item.get("status") == "live")
            message = f"GitHub push OK nhung Pages chua cap nhat hoan tat: {live_count}/{len(urls)} URLs live."
        self._report_progress(f"[post-push] {message}")
        return {"status": "pages_pending", "message": message, "attempts": attempts, "items": last_items}

    def _write_live_url_history(self, *, batch_date: str, live_check: dict[str, Any], published: list[dict[str, Any]]) -> dict[str, str]:
        history_jsonl = self.data_dir / "published_live_urls.jsonl"
        latest_json = self.data_dir / "published_live_urls_latest.json"
        rows: list[dict[str, Any]] = []
        published_by_slug = {str(item.get("slug") or ""): item for item in published}
        for item in list(live_check.get("items") or []):
            slug = str(item.get("slug") or "")
            url = str(item.get("url") or "")
            if not slug or not url:
                continue
            row = {
                "checked_at": datetime.now(UTC).isoformat(),
                "batch_date": batch_date,
                "slug": slug,
                "url": url,
                "live_status": str(item.get("status") or ""),
                "live_http_status": item.get("http_status"),
                "live_reason": str(item.get("reason") or ""),
                "post_push_status": str(live_check.get("status") or ""),
                "post_push_message": str(live_check.get("message") or ""),
                "site_file": str((published_by_slug.get(slug) or {}).get("site_file") or ""),
                "article_file": str((published_by_slug.get(slug) or {}).get("article_file") or ""),
            }
            rows.append(row)
        if rows:
            history_jsonl.parent.mkdir(parents=True, exist_ok=True)
            with history_jsonl.open("a", encoding="utf-8") as handle:
                for row in rows:
                    handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            _write_json(latest_json, {"generated_at": datetime.now(UTC).isoformat(), "batch_date": batch_date, "items": rows})
        return {"history_jsonl": str(history_jsonl), "latest_json": str(latest_json)}

    def _copy_file(self, source: Path, target: Path) -> Path:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        return target

    def _copy_tree_contents(self, source_root: Path, target_root: Path) -> None:
        if not source_root.exists():
            return
        for item in source_root.rglob("*"):
            if item.is_dir():
                continue
            target = target_root / item.relative_to(source_root)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target)

    def _publish_stage_paths(self, *, batch_date: str, published: list[dict[str, Any]]) -> list[str]:
        paths: list[Path] = []
        slugs = [str(item.get("slug") or "") for item in published if str(item.get("slug") or "").strip()]
        for slug in slugs:
            paths.extend(
                [
                    self.root / "docs" / slug,
                    self.site_output_dir / slug,
                    self.data_dir / "published_static_pages" / slug,
                    self.data_dir / "production_article_drafts" / slug,
                    self.review_root / batch_date / slug,
                    self.upload_root / batch_date / "published" / slug,
                    self.upload_root / batch_date / "drafts" / slug,
                    self.upload_root / batch_date / "review" / slug,
                ]
            )
        common_paths = [
            self.root / "docs" / "index.html",
            self.root / "docs" / "404.html",
            self.root / "docs" / "sitemap.xml",
            self.root / "docs" / "robots.txt",
            self.root / "docs" / "search.json",
            self.root / "docs" / "feed.xml",
            self.root / "docs" / "rss.xml",
            self.site_output_dir / "index.html",
            self.site_output_dir / "404.html",
            self.site_output_dir / "sitemap.xml",
            self.site_output_dir / "robots.txt",
            self.site_output_dir / "search.json",
            self.site_output_dir / "feed.xml",
            self.site_output_dir / "rss.xml",
            self.data_dir / "publish_queue.json",
            self.data_dir / "content_review_queue.json",
            self.data_dir / "human_approval_queue.json",
            self.data_dir / "content_review_report.json",
            self.data_dir / "content_review_report.csv",
            self.data_dir / "content_review_report.md",
            self.data_dir / "publish_gate_report.json",
            self.data_dir / "publish_gate_report.csv",
            self.data_dir / "publish_gate_report.md",
            self.data_dir / "daily_ceo_dashboard.html",
            self.data_dir / "editorial_operations_console.json",
            self.data_dir / "editorial_operations_console.csv",
            self.data_dir / "editorial_operations_console.html",
            self.data_dir / "live_status_report.json",
            self.data_dir / "live_status_report.md",
            self.data_dir / "live_status_report.html",
            self.data_dir / "published_live_urls.jsonl",
            self.data_dir / "published_live_urls_latest.json",
            self.data_dir / "master_dashboard.xlsx",
            self._queue_dir(batch_date) / "topics.json",
            self.review_root / batch_date / "index.html",
            self.upload_root / batch_date,
            self.upload_root / "dashboard.html",
        ]
        paths.extend(common_paths)
        unique: list[str] = []
        seen: set[str] = set()
        for path in paths:
            if not path.exists():
                continue
            try:
                rel = str(path.relative_to(self.root)).replace("\\", "/")
            except ValueError:
                rel = str(path).replace("\\", "/")
            if rel in seen:
                continue
            seen.add(rel)
            unique.append(rel)
        return unique

    def _validate_html_tree(self, root: Path, *, scope: str) -> None:
        if not root.exists():
            return
        forbidden_markers = (
            "Research package snapshot",
            "Content planning snapshot",
            "Affiliate placeholder fields",
            "{{",
            "internal debug",
            "planning block",
            "debug block",
        )
        for file in root.rglob("*.html"):
            text = file.read_text(encoding="utf-8", errors="ignore")
            for marker in forbidden_markers:
                if marker in text:
                    raise ValueError(f"{scope}: forbidden marker {marker!r} found in {file}")

    def _run_command(self, command: list[str], *, cwd: Path, check: bool = False, label: str = "", timeout: int | None = None) -> dict[str, Any]:
        effective_timeout = timeout or self.command_timeout_seconds
        if label:
            self._report_progress(f"{label}... running")
        try:
            completed = subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=False, timeout=effective_timeout)
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"Command timeout after {effective_timeout}s: {' '.join(command)}") from exc
        result = {
            "command": command,
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }
        if label:
            outcome = "OK" if completed.returncode == 0 else f"FAILED ({completed.returncode})"
            self._report_progress(f"{label}... {outcome}")
        if check and completed.returncode != 0:
            raise RuntimeError(f"Command failed: {' '.join(command)}\n{completed.stdout}\n{completed.stderr}".strip())
        return result
