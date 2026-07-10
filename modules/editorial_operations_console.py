from __future__ import annotations

import csv
import html
import json
import math
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from config import settings
from modules.content_review import ContentReviewEngine
from modules.human_approval import HumanApprovalWorkflow
from modules.publish_gate import PublishGate


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
            writer.writerow(
                {
                    key: json.dumps(value, ensure_ascii=False) if isinstance(value, (list, dict)) else value
                    for key, value in row.items()
                }
            )
    return path


def _write_md(path: Path, lines: list[str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return path


class EditorialOperationsConsole:
    def __init__(
        self,
        *,
        data_dir: Path | None = None,
        site_output_dir: Path | None = None,
        published_dir: Path | None = None,
    ) -> None:
        self.data_dir = data_dir or settings.data_dir
        self.site_output_dir = site_output_dir or settings.site_output_dir
        self.published_dir = published_dir or (self.data_dir / "published_static_pages")
        self.drafts_dir = self.data_dir / "production_article_drafts"
        self.social_root = settings.base_dir / "social_drafts"
        self.console_json = self.data_dir / "editorial_operations_console.json"
        self.console_html = self.data_dir / "editorial_operations_console.html"
        self.console_csv = self.data_dir / "editorial_operations_console.csv"
        self.actions_dir = self.data_dir / "editorial_console_actions"
        self.review_queue_path = self.data_dir / "content_review_queue.json"
        self.human_queue_path = self.data_dir / "human_approval_queue.json"
        self.publish_queue_path = self.data_dir / "publish_queue.json"
        self.review_engine = ContentReviewEngine(data_dir=self.data_dir)
        self.human_workflow = HumanApprovalWorkflow(data_dir=self.data_dir)
        self.publish_gate = PublishGate(data_dir=self.data_dir, site_output_dir=self.site_output_dir, config=getattr(settings, "editorial_config", {}).get("publish_gate", {}))

    def list_pending_approvals(self) -> list[dict[str, Any]]:
        rows = self.collect_rows()
        return [row for row in rows if str(row.get("human_approval_status", "")) == "needs_human_review"]

    def approve_slug(self, slug: str, *, approver: str = "editor") -> dict[str, Any]:
        approval = self.human_workflow.approve(slug, approver=approver)
        if not approval:
            raise ValueError(f"Unknown approval slug: {slug}")
        review = self._update_review_status(slug, status="human_approved", reason="")
        publish = self._update_publish_status_after_approval(slug)
        self._update_draft_artifacts(slug, review=review, human_approval=approval, publish_gate=publish)
        self.rebuild_outputs()
        return {"slug": slug, "review": review, "human_approval": approval, "publish_gate": publish}

    def reject_slug(self, slug: str, *, reason: str, approver: str = "editor") -> dict[str, Any]:
        approval = self.human_workflow.reject(slug, approver=approver, reason=reason)
        if not approval:
            raise ValueError(f"Unknown approval slug: {slug}")
        review = self._update_review_status(slug, status="rejected", reason=reason)
        publish = self._block_publish_status(slug, f"human approval rejected: {reason}")
        self._update_draft_artifacts(slug, review=review, human_approval=approval, publish_gate=publish)
        self.rebuild_outputs()
        return {"slug": slug, "review": review, "human_approval": approval, "publish_gate": publish}

    def publish_slug(self, slug: str) -> dict[str, Any]:
        return self._publish_slug(slug, rebuild=True)

    def publish_all_approved(self) -> dict[str, Any]:
        rows = _read_json(self.publish_queue_path, [])
        approved = [str(row.get("slug", "")) for row in rows if str(row.get("status", "")) == "approved_for_publish"]
        published: list[dict[str, Any]] = []
        for slug in approved:
            published.append(self._publish_slug(slug, rebuild=False))
        self.rebuild_outputs()
        return {"approved_count": len(approved), "published": published}

    def request_custom_topic(
        self,
        topic_name: str,
        *,
        category: str = "",
        intent: str = "",
        source_url: str = "",
        official_url: str = "",
        affiliate_url: str = "",
        pricing_url: str = "",
        source_type: str = "custom_topic",
        partner_name: str = "",
        cluster_article_number: int = 1,
        cluster_article_total: int = 1,
        extra_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        from modules.content_growth_pipeline import generate_production_article_draft_from_package, get_research_platform

        keyword = topic_name.strip()
        if not keyword:
            raise ValueError("Topic name is required.")
        normalized_source_url = source_url.strip()
        normalized_official_url = official_url.strip() or normalized_source_url
        normalized_affiliate_url = affiliate_url.strip()
        normalized_pricing_url = pricing_url.strip()
        slug = self._slugify(keyword)
        source_urls = [url for url in [normalized_official_url, normalized_affiliate_url, normalized_pricing_url, normalized_source_url] if url]
        topic = {
            "topic": keyword,
            "slug": slug,
            "title": keyword,
            "category": category.strip(),
            "search_intent": intent.strip(),
            "requested_intent": intent.strip(),
            "source_urls": source_urls,
            "requested_source_url": normalized_source_url,
        }
        platform = get_research_platform()
        package = platform.build_research_package(topic, force_refresh=True)
        package_path = Path(package.package_dir) / "package.json"
        payload = _read_json(package_path, {})
        request_context = {
            "requested_topic": keyword,
            "category": category.strip(),
            "intent": intent.strip(),
            "source_url": normalized_source_url,
            "official_url": normalized_official_url,
            "affiliate_url": normalized_affiliate_url,
            "pricing_url": normalized_pricing_url,
            "source_type": source_type.strip() or "custom_topic",
            "partner_name": partner_name.strip(),
            "cluster_article_number": int(cluster_article_number or 1),
            "cluster_article_total": int(cluster_article_total or 1),
            "created_via": "editorial_console",
        }
        if extra_context:
            request_context.update(extra_context)
        payload["request_context"] = request_context
        _write_json(package_path, payload)
        gate = platform.evaluate_quality_gate(package, topic=topic, allow_override=False)
        result: dict[str, Any] = {
            "slug": slug,
            "topic": keyword,
            "category": category.strip(),
            "intent": intent.strip(),
            "source_url": normalized_source_url,
            "official_url": normalized_official_url,
            "affiliate_url": normalized_affiliate_url,
            "pricing_url": normalized_pricing_url,
            "source_type": request_context["source_type"],
            "partner_name": request_context["partner_name"],
            "cluster_article_number": request_context["cluster_article_number"],
            "cluster_article_total": request_context["cluster_article_total"],
            "quality_gate": {
                "passed": gate.passed,
                "score": gate.score,
                "threshold": gate.threshold,
                "status": gate.status,
            },
        }
        if gate.passed:
            result["draft"] = generate_production_article_draft_from_package(slug)
            metadata_path = self.drafts_dir / slug / "metadata.json"
            metadata = _read_json(metadata_path, {})
            metadata["request_context"] = request_context
            _write_json(metadata_path, metadata)
        else:
            result["queue"] = str(self.data_dir / "research_enrichment_queue.json")
        self.rebuild_outputs()
        return result

    def _publish_slug(self, slug: str, *, rebuild: bool) -> dict[str, Any]:
        publish_rows = _read_json(self.publish_queue_path, [])
        publish_row = next((row for row in publish_rows if str(row.get("slug", "")) == slug), None)
        if not publish_row:
            raise ValueError(f"Unknown publish slug: {slug}")
        normalized = PublishGate.normalize_existing_row(publish_row)
        if str(normalized.get("normalized_status") or publish_row.get("status", "")) != "approved_for_publish":
            raise ValueError(f"Slug is not approved for publish: {slug}")
        if normalized.get("hard_blockers"):
            raise ValueError(f"Slug has hard publish blockers: {slug}")
        draft_dir = self.drafts_dir / slug
        draft_html = draft_dir / "index.html"
        if not draft_html.exists():
            raise FileNotFoundError(f"Missing draft HTML: {draft_html}")
        metadata = self._load_metadata(slug)
        url = str(metadata.get("url") or publish_row.get("url") or "")
        html_text = draft_html.read_text(encoding="utf-8")
        article_file = self._write_local_publish(slug, html_text, root=self.published_dir)
        site_file = self._write_local_publish(slug, html_text, root=self.site_output_dir)
        updated = self.publish_gate.mark_published_local(slug, url=url, article_file=article_file, site_file=site_file)
        if updated is None:
            raise ValueError(f"Unable to mark published slug: {slug}")
        review = self._update_review_status(slug, status="human_approved", reason="")
        human = next((row for row in _read_json(self.human_queue_path, []) if str(row.get("slug", "")) == slug), {})
        self._update_draft_artifacts(slug, review=review, human_approval=human, publish_gate=updated)
        if rebuild:
            self.rebuild_outputs()
        return {"slug": slug, "publish_gate": updated, "article_file": str(article_file), "site_file": str(site_file)}

    def collect_rows(self) -> list[dict[str, Any]]:
        review_rows = {str(row.get("slug", "")): row for row in _read_json(self.review_queue_path, [])}
        human_rows = {str(row.get("slug", "")): row for row in _read_json(self.human_queue_path, [])}
        publish_rows = {str(row.get("slug", "")): row for row in _read_json(self.publish_queue_path, [])}
        draft_slugs = [folder.name for folder in self.drafts_dir.iterdir() if folder.is_dir()] if self.drafts_dir.exists() else []
        slugs = sorted({*review_rows.keys(), *human_rows.keys(), *publish_rows.keys(), *draft_slugs})
        rows: list[dict[str, Any]] = []
        for slug in slugs:
            self._ensure_operator_assets(slug)
            metadata = self._load_metadata(slug)
            request_context = metadata.get("request_context") if isinstance(metadata.get("request_context"), dict) else {}
            review = review_rows.get(slug) or metadata.get("review") or {}
            human = human_rows.get(slug) or metadata.get("human_approval") or {}
            publish = publish_rows.get(slug) or metadata.get("publish_gate") or {}
            quality_gate = metadata.get("research_quality_gate") if isinstance(metadata.get("research_quality_gate"), dict) else {}
            title = str(metadata.get("title") or publish.get("title") or slug.replace("-", " "))
            status = self._overall_status(review, human, publish)
            draft_dir = self.drafts_dir / slug
            html_stats = self._extract_html_stats(draft_dir / "index.html", metadata=metadata, review=review)
            command_paths = self._build_action_launchers(slug)
            social = self._collect_social_drafts(slug)
            social_actions = self._build_social_actions(slug, social)
            publish_enabled = self._publish_enabled(review, quality_gate, human, publish)
            rows.append(
                {
                    "title": title,
                    "slug": slug,
                    "status": status,
                    "research_quality_status": self._quality_status(quality_gate),
                    "ai_review_status": str(review.get("status") or "missing"),
                    "human_approval_status": str(human.get("status") or "missing"),
                    "publish_gate_status": str(publish.get("status") or "missing"),
                    "word_count": int(review.get("word_count") or 0),
                    "last_updated": self._last_updated(slug, review, human, publish),
                    "article_markdown": self._relative_link(draft_dir / "article.md"),
                    "article_html": self._relative_link(draft_dir / "index.html"),
                    "metadata_json": self._relative_link(draft_dir / "metadata.json"),
                    "review_summary": self._relative_link(draft_dir / "review_summary.md"),
                    "publish_readiness_report": self._relative_link(draft_dir / "publish_readiness_report.md"),
                    "source_review": self._relative_link(self.data_dir / "research" / slug / "sources.json")
                    or self._relative_link(self.data_dir / "source_review_report.md"),
                    "folder": self._relative_link(self._build_open_folder_launcher(slug, draft_dir)),
                    "copy_url": self._relative_link(self._build_copy_url_launcher(slug, str(metadata.get("url") or publish.get("url") or ""))),
                    "next_command": self._next_command(slug, human, publish),
                    "website_preview": self._website_preview_link(slug, publish),
                    "stats": html_stats,
                    "review_score": round(float(review.get("publish_readiness") or 0), 2),
                    "business_score": round(float(review.get("business_value") or 0), 2),
                    "source_type": str(request_context.get("source_type") or ""),
                    "partner_name": str(request_context.get("partner_name") or ""),
                    "official_url": str(request_context.get("official_url") or request_context.get("source_url") or ""),
                    "affiliate_url": str(request_context.get("affiliate_url") or ""),
                    "pricing_url": str(request_context.get("pricing_url") or ""),
                    "cluster_article_number": int(request_context.get("cluster_article_number") or 0),
                    "cluster_article_total": int(request_context.get("cluster_article_total") or 0),
                    "block_reason": ", ".join(str(item).strip() for item in list(publish.get("failures") or []) if str(item).strip()),
                    "author": metadata.get("editorial") if isinstance(metadata.get("editorial"), dict) else {},
                    "social_drafts": social,
                    "social_actions": social_actions,
                    "actions": {
                        "approve": self._relative_link(command_paths["approve"]),
                        "reject": self._relative_link(command_paths["reject"]),
                        "publish": self._relative_link(command_paths["publish"]),
                    },
                    "publish_enabled": publish_enabled,
                }
            )
        return rows

    def build_console(self) -> dict[str, Any]:
        rows = self.collect_rows()
        summary = {
            "generated_at": datetime.now(UTC).isoformat(),
            "drafts": len(rows),
            "pending_human_review": sum(1 for row in rows if row["human_approval_status"] == "needs_human_review"),
            "approved_for_publish": sum(1 for row in rows if row["publish_gate_status"] == "approved_for_publish"),
            "published_local": sum(1 for row in rows if row["publish_gate_status"] == "published_local"),
            "blocked": sum(1 for row in rows if row["publish_gate_status"] == "blocked"),
        }
        payload = {
            "summary": summary,
            "items": rows,
            "global_actions": {
                "publish_all_approved": self._relative_link(self._build_global_launcher("publish-all-approved", "python scripts/editorial_console.py --publish-all")),
                "rebuild_console": self._relative_link(self._build_global_launcher("rebuild-console", "python scripts/editorial_console.py --build")),
                "preview_website": self._preview_website_link(),
            },
        }
        _write_json(self.console_json, payload)
        _write_csv(self.console_csv, rows)
        self._write_console_html(payload)
        return payload

    def rebuild_outputs(self) -> dict[str, Any]:
        self.review_engine.refresh_reports()
        self.publish_gate.refresh_reports()
        if self.data_dir.resolve() == settings.data_dir.resolve():
            try:
                from scripts.build_ceo_dashboard import main as build_dashboard_main
            except Exception:
                build_dashboard_main = None
            if build_dashboard_main is not None:
                build_dashboard_main()
        return self.build_console()

    def _load_metadata(self, slug: str) -> dict[str, Any]:
        return _read_json(self.drafts_dir / slug / "metadata.json", {})

    def _update_review_status(self, slug: str, *, status: str, reason: str) -> dict[str, Any]:
        rows = _read_json(self.review_queue_path, [])
        updated: dict[str, Any] | None = None
        for row in rows:
            if str(row.get("slug", "")) != slug:
                continue
            row["status"] = status
            row["publishable"] = status in {"ai_review_passed", "needs_human_review", "human_approved"}
            if reason:
                row["failures"] = [reason]
            elif status == "human_approved":
                row["failures"] = []
            updated = row
            break
        if updated is None:
            raise ValueError(f"Unknown review slug: {slug}")
        _write_json(self.review_queue_path, rows)
        return updated

    def _update_publish_status_after_approval(self, slug: str) -> dict[str, Any]:
        rows = _read_json(self.publish_queue_path, [])
        updated: dict[str, Any] | None = None
        for row in rows:
            if str(row.get("slug", "")) != slug:
                continue
            normalized = PublishGate.normalize_existing_row(row)
            hard_blockers = list(normalized.get("hard_blockers") or [])
            warnings = list(normalized.get("warnings") or [])
            pending_reviews = [
                item
                for item in list(normalized.get("pending_reviews") or [])
                if str(item).strip().lower() != "human approval missing"
            ]
            row["human_approval_passed"] = True
            row["hard_blockers"] = hard_blockers
            row["warnings"] = warnings
            row["pending_reviews"] = pending_reviews
            row["failures"] = hard_blockers
            row["publish_ready"] = not hard_blockers
            row["status"] = "approved_for_publish" if not hard_blockers else "blocked"
            row["final_gate"] = "Ready for Publish" if not hard_blockers else "Publish Blocked"
            row["severity_counts"] = {
                "BLOCK": len(hard_blockers),
                "WARNING": len(warnings),
                "HUMAN_REVIEW_REQUIRED": len(pending_reviews),
            }
            row["checked_at"] = datetime.now(UTC).isoformat()
            updated = row
            break
        if updated is None:
            raise ValueError(f"Unknown publish slug: {slug}")
        _write_json(self.publish_queue_path, rows)
        return updated

    def _block_publish_status(self, slug: str, reason: str) -> dict[str, Any]:
        rows = _read_json(self.publish_queue_path, [])
        updated: dict[str, Any] | None = None
        for row in rows:
            if str(row.get("slug", "")) != slug:
                continue
            normalized = PublishGate.normalize_existing_row(row)
            failures = list(normalized.get("hard_blockers") or [])
            failures = [item for item in failures if not str(item).strip().lower().startswith("human approval rejected:")]
            if reason not in failures:
                failures.append(reason)
            row["human_approval_passed"] = False
            row["hard_blockers"] = failures
            row["warnings"] = list(normalized.get("warnings") or [])
            row["pending_reviews"] = ["human approval rejected"]
            row["failures"] = failures
            row["publish_ready"] = False
            row["status"] = "blocked"
            row["final_gate"] = "Publish Blocked"
            row["severity_counts"] = {
                "BLOCK": len(failures),
                "WARNING": len(row["warnings"]),
                "HUMAN_REVIEW_REQUIRED": len(row["pending_reviews"]),
            }
            row["checked_at"] = datetime.now(UTC).isoformat()
            updated = row
            break
        if updated is None:
            raise ValueError(f"Unknown publish slug: {slug}")
        _write_json(self.publish_queue_path, rows)
        return updated

    def _update_draft_artifacts(
        self,
        slug: str,
        *,
        review: dict[str, Any],
        human_approval: dict[str, Any],
        publish_gate: dict[str, Any],
    ) -> None:
        draft_dir = self.drafts_dir / slug
        if not draft_dir.exists():
            return
        metadata_path = draft_dir / "metadata.json"
        metadata = _read_json(metadata_path, {})
        metadata["review"] = review
        metadata["human_approval"] = human_approval
        metadata["publish_gate"] = publish_gate
        _write_json(metadata_path, metadata)
        publish_readiness = {
            "slug": slug,
            "title": metadata.get("title", ""),
            "description": metadata.get("description", ""),
            "url": metadata.get("url", ""),
            "review_status": review.get("status", ""),
            "human_approval_status": human_approval.get("status", ""),
            "publish_gate_status": publish_gate.get("status", ""),
            "publish_failures": publish_gate.get("failures", []),
            "research_quality_score": metadata.get("research_quality_gate", {}).get("score", 0),
            "verified_source_score": publish_gate.get("verified_source_score", metadata.get("publish_gate", {}).get("verified_source_score", 0)),
            "word_count": review.get("word_count", 0),
            "article_markdown": str(draft_dir / "article.md"),
            "article_html": str(draft_dir / "index.html"),
        }
        _write_json(draft_dir / "publish_readiness_report.json", publish_readiness)
        _write_md(
            draft_dir / "publish_readiness_report.md",
            [
                "# Publish Readiness Report",
                "",
                f"- Slug: `{slug}`",
                f"- Review status: `{review.get('status', '')}`",
                f"- Human approval: `{human_approval.get('status', '')}`",
                f"- Publish gate: `{publish_gate.get('status', '')}`",
                f"- Failures: {', '.join(publish_gate.get('failures', [])) or 'none'}",
                f"- Word count: {review.get('word_count', 0)}",
            ],
        )
        _write_md(
            draft_dir / "review_summary.md",
            [
                "# Review Summary",
                "",
                f"- AI review status: `{review.get('status', '')}`",
                f"- Human approval status: `{human_approval.get('status', '')}`",
                f"- Publish gate status: `{publish_gate.get('status', '')}`",
                f"- Publish failures: {', '.join(publish_gate.get('failures', [])) or 'none'}",
                f"- Publish readiness score: {review.get('publish_readiness', 0)}",
            ],
        )

    def _write_local_publish(self, slug: str, html_text: str, *, root: Path) -> Path:
        folder = root / slug
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / "index.html"
        target.write_text(html_text, encoding="utf-8")
        return target

    def _relative_link(self, path: Path) -> str:
        if not path.exists():
            return ""
        return path.relative_to(self.data_dir).as_posix()

    def _href_for_path(self, path: Path, *, from_dir: Path | None = None) -> str:
        base = from_dir or self.data_dir
        try:
            return os.path.relpath(path, base).replace("\\", "/")
        except Exception:
            return path.as_posix()

    def _slugify(self, value: str) -> str:
        cleaned = re.sub(r"[^a-z0-9]+", "-", value.strip().lower())
        return cleaned.strip("-")

    def _ensure_operator_assets(self, slug: str) -> None:
        draft_dir = self.drafts_dir / slug
        metadata = self._load_metadata(slug)
        needs_sync = (
            draft_dir.exists()
            and (
                not isinstance(metadata.get("editorial"), dict)
                or not str(metadata.get("social_folder") or "").strip()
                or not (draft_dir / "social_drafts_index.html").exists()
            )
        )
        if needs_sync:
            try:
                from modules.content_growth_pipeline import sync_production_draft_assets

                sync_production_draft_assets(slug)
                metadata = self._load_metadata(slug)
            except Exception:
                metadata = self._load_metadata(slug)
        social = self._collect_social_drafts(slug)
        self._write_social_index(slug, social)

    def _preview_website_link(self) -> str:
        target = self.site_output_dir / "index.html"
        if not target.exists():
            return ""
        return "../site_output/index.html"

    def _social_folder_for_slug(self, slug: str) -> Path | None:
        metadata = self._load_metadata(slug)
        metadata_folder = str(metadata.get("social_folder") or "").strip()
        if metadata_folder:
            path = Path(metadata_folder)
            if path.exists():
                return path
        if not self.social_root.exists():
            return None
        candidates = sorted(self.social_root.glob(f"*/{slug}"), key=lambda path: path.stat().st_mtime, reverse=True)
        return candidates[0] if candidates else None

    def _collect_social_drafts(self, slug: str) -> dict[str, str]:
        folder = self._social_folder_for_slug(slug)
        if folder is None or not folder.exists():
            return {}
        result: dict[str, str] = {}
        label_map = {
            "facebook.md": "facebook",
            "quora.md": "quora",
            "linkedin.md": "linkedin",
            "x-twitter.md": "x",
            "reddit.md": "reddit",
            "devto.md": "devto",
            "product-hunt.md": "product_hunt",
            "qiita.md": "qiita",
            "medium.md": "medium",
            "threads.md": "threads",
            "pinterest.md": "pinterest",
        }
        for file_name, label in label_map.items():
            path = folder / file_name
            if path.exists():
                result[label] = self._href_for_path(path)
        return result

    def _write_social_index(self, slug: str, social: dict[str, str]) -> Path:
        draft_dir = self.drafts_dir / slug
        draft_dir.mkdir(parents=True, exist_ok=True)
        target = draft_dir / "social_drafts_index.html"
        folder = self._social_folder_for_slug(slug)
        lines = [
            "<!doctype html>",
            "<html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">",
            f"<title>Social Drafts - {html.escape(slug)}</title>",
            "<style>body{font-family:Georgia,'Segoe UI',serif;background:#faf6ef;color:#201a14;margin:0;padding:24px}.card{max-width:860px;margin:0 auto;background:#fff;border:1px solid #e7dac6;border-radius:16px;padding:20px}a{display:inline-block;margin:6px 10px 6px 0;color:#0f5f63;text-decoration:none}.platform{padding:12px 0;border-top:1px solid #eee4d3}</style></head><body>",
            "<main class='card'><h1>Social Drafts</h1>",
        ]
        if not social:
            lines.append("<p>No social drafts found.</p>")
        else:
            for label, rel_path in social.items():
                href = rel_path
                if folder is not None:
                    file_name = f"{label.replace('_', '-')}.md" if label not in {"x"} else "x-twitter.md"
                    if label == "product_hunt":
                        file_name = "product-hunt.md"
                    elif label == "devto":
                        file_name = "devto.md"
                    elif label == "facebook":
                        file_name = "facebook.md"
                    elif label == "linkedin":
                        file_name = "linkedin.md"
                    elif label == "quora":
                        file_name = "quora.md"
                    elif label == "reddit":
                        file_name = "reddit.md"
                    elif label == "qiita":
                        file_name = "qiita.md"
                    elif label == "medium":
                        file_name = "medium.md"
                    elif label == "threads":
                        file_name = "threads.md"
                    elif label == "pinterest":
                        file_name = "pinterest.md"
                    href = self._href_for_path(folder / file_name, from_dir=draft_dir)
                lines.append(
                    f"<div class='platform'><strong>{html.escape(label.replace('_', ' ').title())}</strong><br><a href='{html.escape(href, quote=True)}'>Open Draft</a></div>"
                )
        lines.append("</main></body></html>")
        target.write_text("".join(lines), encoding="utf-8")
        return target

    def _last_updated(self, slug: str, review: dict[str, Any], human: dict[str, Any], publish: dict[str, Any]) -> str:
        candidates = [
            str(review.get("reviewed_at", "")),
            str(human.get("approved_at", "")),
            str(human.get("reviewed_at", "")),
            str(publish.get("checked_at", "")),
            str(publish.get("published_at", "")),
        ]
        draft_dir = self.drafts_dir / slug
        if draft_dir.exists():
            newest = max((item.stat().st_mtime for item in draft_dir.iterdir() if item.is_file()), default=0)
            if newest:
                candidates.append(datetime.fromtimestamp(newest, UTC).isoformat())
        return max((value for value in candidates if value), default="")

    def _quality_status(self, quality_gate: dict[str, Any]) -> str:
        if not quality_gate:
            return "missing"
        if bool(quality_gate.get("passed", False)):
            return "passed"
        return str(quality_gate.get("status") or "blocked")

    def _overall_status(self, review: dict[str, Any], human: dict[str, Any], publish: dict[str, Any]) -> str:
        if str(publish.get("status", "")):
            return str(publish.get("status", ""))
        if str(human.get("status", "")):
            return str(human.get("status", ""))
        return str(review.get("status", "") or "draft")

    def _next_command(self, slug: str, human: dict[str, Any], publish: dict[str, Any]) -> str:
        human_status = str(human.get("status", ""))
        publish_status = str(publish.get("status", ""))
        if human_status == "needs_human_review":
            return f"python scripts/editorial_console.py --approve {slug}"
        if publish_status == "approved_for_publish":
            return f"python scripts/editorial_console.py --publish {slug}"
        if publish_status == "published_local":
            return "No further action required."
        if human_status == "rejected":
            return f"python scripts/editorial_console.py --build"
        return f"python scripts/editorial_console.py --build"

    def _publish_enabled(
        self,
        review: dict[str, Any],
        quality_gate: dict[str, Any],
        human: dict[str, Any],
        publish: dict[str, Any],
    ) -> bool:
        review_status = str(review.get("status", ""))
        human_status = str(human.get("status", ""))
        publish_status = str(publish.get("status", ""))
        return (
            bool(quality_gate.get("passed", False))
            and review_status in {"ai_review_passed", "human_approved"}
            and human_status == "human_approved"
            and publish_status == "approved_for_publish"
        )

    def _build_action_launchers(self, slug: str) -> dict[str, Path]:
        return {
            "approve": self._build_slug_launcher(f"approve-{slug}", f"python scripts/editorial_console.py --approve {slug}"),
            "reject": self._build_slug_reject_launcher(slug),
            "publish": self._build_slug_launcher(f"publish-{slug}", f"python scripts/editorial_console.py --publish {slug}"),
        }

    def _build_social_actions(self, slug: str, social: dict[str, str]) -> dict[str, str]:
        folder = self._social_folder_for_slug(slug)
        actions: dict[str, str] = {
            "open_social_drafts": self._relative_link(self.drafts_dir / slug / "social_drafts_index.html"),
            "open_all_social_drafts": self._relative_link(self._build_open_folder_launcher(slug, folder)) if folder else "",
        }
        copy_platforms = {
            "facebook": "Copy Facebook Draft",
            "quora": "Copy Quora Draft",
            "linkedin": "Copy LinkedIn Draft",
            "x": "Copy X Draft",
        }
        for platform in copy_platforms:
            rel_path = social.get(platform, "")
            if rel_path:
                actions[f"copy_{platform}"] = self._relative_link(
                    self._build_copy_draft_launcher(slug, platform, (self.data_dir / rel_path).resolve())
                )
        for platform, rel_path in social.items():
            actions[f"open_{platform}"] = rel_path
        return actions

    def _build_slug_launcher(self, name: str, command: str) -> Path:
        self.actions_dir.mkdir(parents=True, exist_ok=True)
        path = self.actions_dir / f"{name}.cmd"
        path.write_text(
            "\n".join(
                [
                    "@echo off",
                    "cd /d \"%~dp0\\..\\..\"",
                    command,
                    "pause",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        return path

    def _build_global_launcher(self, name: str, command: str) -> Path:
        return self._build_slug_launcher(name, command)

    def _build_open_folder_launcher(self, slug: str, folder: Path) -> Path:
        self.actions_dir.mkdir(parents=True, exist_ok=True)
        path = self.actions_dir / f"open-social-{slug}.cmd"
        path.write_text(
            "\n".join(
                [
                    "@echo off",
                    f'explorer "{folder}"',
                    "",
                ]
            ),
            encoding="utf-8",
        )
        return path

    def _build_copy_url_launcher(self, slug: str, url: str) -> Path:
        self.actions_dir.mkdir(parents=True, exist_ok=True)
        path = self.actions_dir / f"copy-url-{slug}.cmd"
        path.write_text(
            "\n".join(
                [
                    "@echo off",
                    f'powershell -NoProfile -Command "Set-Clipboard -Value \\"{url}\\""',
                    "echo URL copied to clipboard.",
                    "pause",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        return path

    def _build_copy_draft_launcher(self, slug: str, platform: str, source_file: Path) -> Path:
        self.actions_dir.mkdir(parents=True, exist_ok=True)
        path = self.actions_dir / f"copy-{platform}-{slug}.cmd"
        path.write_text(
            "\n".join(
                [
                    "@echo off",
                    f'powershell -NoProfile -Command "Get-Content -LiteralPath \\"{source_file}\\" -Raw | Set-Clipboard"',
                    "echo Draft copied to clipboard.",
                    "pause",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        return path

    def _build_slug_reject_launcher(self, slug: str) -> Path:
        self.actions_dir.mkdir(parents=True, exist_ok=True)
        path = self.actions_dir / f"reject-{slug}.cmd"
        path.write_text(
            "\n".join(
                [
                    "@echo off",
                    "set /p reason=Reject reason: ",
                    "if \"%reason%\"==\"\" set reason=Rejected in editorial console",
                    "cd /d \"%~dp0\\..\\..\"",
                    f"python scripts/editorial_console.py --reject {slug} --reason \"%reason%\"",
                    "pause",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        return path

    def _website_preview_link(self, slug: str, publish: dict[str, Any]) -> str:
        if str(publish.get("status", "")) == "published_local":
            return f"../site_output/{slug}/index.html"
        return self._relative_link(self.drafts_dir / slug / "index.html")

    def _extract_html_stats(self, html_path: Path, *, metadata: dict[str, Any], review: dict[str, Any]) -> dict[str, Any]:
        html_text = html_path.read_text(encoding="utf-8") if html_path.exists() else ""
        links = re.findall(r"""<a\b[^>]*href=["']([^"']+)["']""", html_text, flags=re.IGNORECASE)
        internal_links, external_links, affiliate_links = self._classify_links(links, metadata)
        canonical_url = self._extract_meta_attr(html_text, "link", "rel", "canonical", "href")
        og_image = self._extract_meta_attr(html_text, "meta", "property", "og:image", "content")
        meta_description = self._extract_meta_attr(html_text, "meta", "name", "description", "content")
        schema_status = "present" if re.search(r"<script[^>]*application/ld\+json", html_text, flags=re.IGNORECASE) else "missing"
        featured_status = "prompt_ready" if (html_path.parent / "featured_image_prompt.txt").exists() else "missing"
        reading_time = max(1, int(math.ceil(int(review.get("word_count") or 0) / 225))) if int(review.get("word_count") or 0) else 0
        return {
            "seo_score": round(float(review.get("seo_title_meta_quality") or 0), 2),
            "reading_time_minutes": reading_time,
            "internal_links": internal_links,
            "external_links": external_links,
            "affiliate_links": affiliate_links,
            "featured_image": featured_status,
            "schema_status": schema_status,
            "meta_description": meta_description,
            "og_image": og_image or "missing",
            "canonical_url": canonical_url or str(metadata.get("url") or ""),
        }

    def _classify_links(self, links: list[str], metadata: dict[str, Any]) -> tuple[int, int, int]:
        base_url = str(metadata.get("url") or "")
        base_host = urlparse(base_url).netloc.lower()
        internal_links = 0
        external_links = 0
        affiliate_links = 0
        for href in links:
            text = href.strip()
            if not text or text.startswith("#") or text.startswith("mailto:") or text.startswith("tel:"):
                continue
            if text.startswith("/"):
                internal_links += 1
                continue
            parsed = urlparse(text)
            host = parsed.netloc.lower()
            if parsed.scheme in {"http", "https"} and host and host == base_host:
                internal_links += 1
                continue
            if parsed.scheme in {"http", "https"}:
                external_links += 1
                if any(marker in text.lower() for marker in ("aff", "ref=", "partner", "utm_", "affiliate", "tag=")):
                    affiliate_links += 1
        return internal_links, external_links, affiliate_links

    def _extract_meta_attr(self, html_text: str, tag: str, match_attr: str, match_value: str, return_attr: str) -> str:
        if not html_text:
            return ""
        pattern = rf"<{tag}\b[^>]*{match_attr}=[\"']{re.escape(match_value)}[\"'][^>]*{return_attr}=[\"']([^\"']+)[\"'][^>]*>"
        match = re.search(pattern, html_text, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip()
        reverse_pattern = rf"<{tag}\b[^>]*{return_attr}=[\"']([^\"']+)[\"'][^>]*{match_attr}=[\"']{re.escape(match_value)}[\"'][^>]*>"
        match = re.search(reverse_pattern, html_text, flags=re.IGNORECASE)
        return match.group(1).strip() if match else ""

    def _status_tone(self, value: str) -> str:
        normalized = value.strip().lower()
        if normalized in {"published_local", "published"}:
            return "published"
        if normalized in {"approved_for_publish", "human_approved", "ai_review_passed", "passed"}:
            return "approved"
        if normalized in {"needs_human_review", "pending", "waiting", "needs_revision"}:
            return "waiting"
        return "blocked"

    def _write_console_html(self, payload: dict[str, Any]) -> None:
        summary = payload["summary"]
        global_actions = payload["global_actions"]
        cards = "\n".join(
            f'<div class="card"><h2>{summary[key]}</h2><p>{label}</p></div>'
            for key, label in (
                ("drafts", "Drafts"),
                ("pending_human_review", "Pending Human Review"),
                ("approved_for_publish", "Ready for Publish"),
                ("published_local", "Published"),
                ("blocked", "Publish Blocked"),
            )
        )
        list_rows = "".join(
            f"""
            <tr class="row-link" data-slug="{html.escape(str(row['slug']), quote=True)}">
              <td><strong>{html.escape(str(row['title']))}</strong><br><code>{html.escape(str(row['slug']))}</code></td>
              <td>{self._badge_html(self._display_status_label(str(row['status'])), self._status_tone(row['status']))}</td>
              <td>{html.escape(str(row['word_count']))}</td>
              <td>{html.escape(str(row['review_score']))}</td>
              <td>{html.escape(str(row['last_updated']))}</td>
            </tr>
            """
            for row in payload["items"]
        )
        payload_json = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
        html_text = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Editorial Operations Console</title>
  <style>
    body {{ margin: 0; font-family: Georgia, 'Segoe UI', serif; background: linear-gradient(180deg, #f4efe6, #fffdfa); color: #201a14; }}
    .wrap {{ max-width: 1380px; margin: 0 auto; padding: 28px 20px 48px; }}
    .hero {{ background: #17324d; color: #fef8ee; border-radius: 18px; padding: 24px; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 14px; margin: 18px 0 26px; }}
    .card {{ background: #fff; border: 1px solid #e7dac6; border-radius: 16px; padding: 18px; box-shadow: 0 8px 28px rgba(23, 50, 77, 0.08); }}
    .layout {{ display: grid; grid-template-columns: minmax(340px, 460px) minmax(0, 1fr); gap: 18px; align-items: start; }}
    .detail-card {{ background: #fff; border: 1px solid #e7dac6; border-radius: 18px; padding: 20px; box-shadow: 0 8px 28px rgba(23, 50, 77, 0.08); position: sticky; top: 18px; }}
    .status-row {{ display: flex; flex-wrap: wrap; gap: 8px; margin: 10px 0 14px; }}
    .badge {{ display: inline-block; padding: 6px 10px; border-radius: 999px; font-size: 13px; font-weight: 700; }}
    .badge.blocked {{ background: #fee2e2; color: #991b1b; }}
    .badge.waiting {{ background: #fef3c7; color: #92400e; }}
    .badge.approved {{ background: #dcfce7; color: #166534; }}
    .badge.published {{ background: #dbeafe; color: #1d4ed8; }}
    .button-row {{ display: flex; flex-wrap: wrap; gap: 10px; margin: 14px 0 16px; }}
    .button {{ display: inline-block; padding: 10px 14px; border-radius: 10px; text-decoration: none; font-weight: 700; border: 1px solid #d9c9b2; background: #fcfaf6; color: #17324d; }}
    .button.primary {{ background: #17324d; color: #fff; border-color: #17324d; }}
    .button.success {{ background: #dff7e6; color: #166534; border-color: #b6e6c3; }}
    .button.warn {{ background: #fff1c2; color: #92400e; border-color: #f1da89; }}
    .button.danger {{ background: #fee2e2; color: #991b1b; border-color: #f5b6b6; }}
    .button.disabled {{ pointer-events: none; opacity: 0.45; }}
    .stats {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px 14px; }}
    .stat {{ background: #faf6ef; border: 1px solid #eee4d3; border-radius: 12px; padding: 10px; }}
    .stat strong {{ display: block; margin-bottom: 4px; }}
    .author-box {{ background: #faf6ef; border: 1px solid #eee4d3; border-radius: 12px; padding: 12px; margin: 12px 0 16px; }}
    .social-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 10px; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ text-align: left; padding: 12px; border-bottom: 1px solid #eee4d3; vertical-align: top; }}
    th {{ background: #f8f2e8; }}
    .row-link {{ cursor: pointer; }}
    .row-link.active {{ background: #f5eee1; }}
    code {{ background: #f3ebde; padding: 2px 6px; border-radius: 6px; }}
    a {{ color: #0f5f63; text-decoration: none; }}
    .panel {{ margin-top: 20px; }}
    .small {{ color: #6b5d4a; font-size: 14px; }}
    @media (max-width: 980px) {{ .layout {{ grid-template-columns: 1fr; }} .detail-card {{ position: static; }} .stats {{ grid-template-columns: 1fr; }} }}
  </style>
</head>
<body>
  <main class="wrap">
    <section class="hero">
      <p>Local-only operator console</p>
      <h1>Editorial Operations Console</h1>
      <p>Review drafts, approve or reject safely, inspect social drafts, and publish locally only after the existing gates pass.</p>
    </section>
    <section class="grid">{cards}</section>
    <section class="card panel">
      <h2>Core Commands</h2>
      <p><code>python scripts/editorial_console.py --build</code></p>
      <p><code>python scripts/editorial_console.py --request-topic "best AI tools for small business" --category "AI Tools" --intent "commercial"</code></p>
      <p><code>python scripts/editorial_console.py --approve best-ai-productivity-software</code></p>
      <p><code>python scripts/editorial_console.py --publish best-ai-productivity-software</code></p>
    </section>
    <section class="card panel">
      <h2>Console Actions</h2>
      <div class="button-row">
        {self._button_html(global_actions.get('preview_website', ''), 'Preview Website', 'primary', disabled=not bool(global_actions.get('preview_website', '')))}
        {self._button_html(global_actions.get('publish_all_approved', ''), 'Publish All Approved', 'success')}
        {self._button_html(global_actions.get('rebuild_console', ''), 'Rebuild Console', 'warn')}
      </div>
      <p class="small">Publish All Approved only runs for rows already in <code>approved_for_publish</code>. It never auto-approves drafts or posts to social platforms.</p>
    </section>
    <section class="panel">
      <div class="layout">
        <section class="card">
          <h2>All Articles</h2>
          <table>
            <thead>
              <tr><th>Article</th><th>Status</th><th>Words</th><th>Review</th><th>Updated</th></tr>
            </thead>
            <tbody>{list_rows or '<tr><td colspan="5">No article rows found.</td></tr>'}</tbody>
          </table>
        </section>
        <section class="detail-card">
          <div id="detail-panel"><p>Select an article from the list.</p></div>
        </section>
      </div>
    </section>
  </main>
  <script>
    const consoleData = {payload_json};
    const items = consoleData.items || [];
    const panel = document.getElementById('detail-panel');
    const rows = Array.from(document.querySelectorAll('.row-link'));

    function esc(value) {{
      return String(value ?? '').replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;');
    }}

    function button(href, label, tone, disabled) {{
      const cls = `button ${{tone || ''}} ${{disabled || !href ? 'disabled' : ''}}`.trim();
      if (disabled || !href) return `<span class="${{cls}}">${{esc(label)}}</span>`;
      return `<a class="${{cls}}" href="${{esc(href)}}">${{esc(label)}}</a>`;
    }}

    function badge(label, tone) {{
      return `<span class="badge ${{esc(tone)}}">${{esc(label)}}</span>`;
    }}

    function stat(label, value) {{
      return `<div class="stat"><strong>${{esc(label)}}</strong><span>${{esc(value)}}</span></div>`;
    }}

    function statusTone(value) {{
      const normalized = String(value || '').toLowerCase();
      if (normalized === 'published_local' || normalized === 'published') return 'published';
      if (['approved_for_publish', 'human_approved', 'ai_review_passed', 'passed'].includes(normalized)) return 'approved';
      if (['needs_human_review', 'pending', 'waiting', 'needs_revision'].includes(normalized)) return 'waiting';
      return 'blocked';
    }}

    function statusLabel(value) {{
      const normalized = String(value || '').toLowerCase();
      const labels = {{
        approved: 'Human Approved',
        human_approved: 'Human Approved',
        blocked: 'Publish Blocked',
        approved_for_publish: 'Ready for Publish',
        published_local: 'Published',
        published: 'Published',
        needs_human_review: 'Waiting for editor approval',
        needs_revision: 'Needs revision',
        ai_review_passed: 'AI Review Passed',
        passed: 'Passed',
        missing: 'Missing'
      }};
      return labels[normalized] || String(value || '');
    }}

    function renderDetail(item) {{
      const author = item.author || {{}};
      const stats = item.stats || {{}};
      const social = item.social_actions || {{}};
      const socialDrafts = item.social_drafts || {{}};
      panel.innerHTML = `
        <p class="small">Selected article</p>
        <h2>${{esc(item.title)}}</h2>
        <p><code>${{esc(item.slug)}}</code></p>
        <div class="status-row">
          ${{badge('Overall: ' + statusLabel(item.status), statusTone(item.status))}}
          ${{badge('Research: ' + statusLabel(item.research_quality_status), statusTone(item.research_quality_status))}}
          ${{badge('AI Review: ' + statusLabel(item.ai_review_status), statusTone(item.ai_review_status))}}
          ${{badge('Human: ' + statusLabel(item.human_approval_status), statusTone(item.human_approval_status))}}
          ${{badge('Publish: ' + statusLabel(item.publish_gate_status), statusTone(item.publish_gate_status))}}
        </div>
        <div class="button-row">
          ${{button(item.article_markdown, 'Open Draft', '', false)}}
          ${{button(item.article_html, 'Open HTML', '', false)}}
          ${{button(item.review_summary, 'Open Review', '', false)}}
          ${{button(item.publish_readiness_report, 'Open AI Report', '', false)}}
          ${{button(item.source_review, 'Open Source Review', '', false)}}
          ${{button(item.metadata_json, 'Open Metadata', '', false)}}
          ${{button(item.folder, 'Open Folder', '', false)}}
          ${{button(social.open_social_drafts, 'Open Social Drafts', 'warn', false)}}
          ${{button(item.actions.approve, 'Approve', 'success', item.human_approval_status !== 'needs_human_review')}}
          ${{button(item.actions.reject, 'Reject', 'danger', item.publish_gate_status === 'published_local')}}
          ${{button(item.actions.publish, 'Publish', 'primary', !item.publish_enabled)}}
        </div>
        <div class="button-row">
          ${{button(item.website_preview, 'Preview Website', 'warn', !item.website_preview)}}
          ${{button(item.website_preview, 'Preview Live', 'warn', !item.website_preview)}}
          ${{button(item.copy_url, 'Copy URL', '', !item.copy_url)}}
          ${{button(social.open_all_social_drafts, 'Open All Social Drafts', '', !social.open_all_social_drafts)}}
          ${{button(social.copy_facebook, 'Copy Facebook Draft', '', !social.copy_facebook)}}
          ${{button(social.copy_quora, 'Copy Quora Draft', '', !social.copy_quora)}}
          ${{button(social.copy_linkedin, 'Copy LinkedIn Draft', '', !social.copy_linkedin)}}
          ${{button(social.copy_x, 'Copy X Draft', '', !social.copy_x)}}
        </div>
        <div class="author-box">
          <p><strong>Source type:</strong> ${{esc(item.source_type || 'standard')}}</p>
          <p><strong>Partner name:</strong> ${{esc(item.partner_name || 'N/A')}}</p>
          <p><strong>Official URL:</strong> ${{item.official_url ? `<a href="${{esc(item.official_url)}}">${{esc(item.official_url)}}</a>` : 'Not set'}}</p>
          <p><strong>Affiliate URL:</strong> ${{item.affiliate_url ? `<a href="${{esc(item.affiliate_url)}}">${{esc(item.affiliate_url)}}</a>` : 'Not set'}}</p>
          <p><strong>Pricing URL:</strong> ${{item.pricing_url ? `<a href="${{esc(item.pricing_url)}}">${{esc(item.pricing_url)}}</a>` : 'Not set'}}</p>
          <p><strong>Cluster article:</strong> ${{item.cluster_article_number ? `${{esc(item.cluster_article_number)}} / ${{esc(item.cluster_article_total || 0)}}` : 'N/A'}}</p>
          <p><strong>Block reason:</strong> ${{esc(item.block_reason || 'None')}}</p>
          <p><strong>Author:</strong> ${{esc(author.author_name || '')}}</p>
          <p><strong>Author profile:</strong> ${{author.author_profile_url ? `<a href="${{esc(author.author_profile_url)}}">${{esc(author.author_profile_url)}}</a>` : 'Not set'}}</p>
          <p><strong>Author bio:</strong> ${{esc(author.author_bio || '')}}</p>
          <p><strong>Reviewed by:</strong> ${{esc(author.reviewed_by || '')}}</p>
          <p><strong>Last updated:</strong> ${{esc(author.last_updated || item.last_updated || '')}}</p>
          <p><strong>Editorial policy:</strong> ${{author.editorial_policy_url ? `<a href="${{esc(author.editorial_policy_url)}}">${{esc(author.editorial_policy_url)}}</a>` : 'Not set'}}</p>
          <p><strong>Affiliate disclosure:</strong> ${{author.affiliate_disclosure_url ? `<a href="${{esc(author.affiliate_disclosure_url)}}">${{esc(author.affiliate_disclosure_url)}}</a>` : 'Not set'}}</p>
        </div>
        <div class="stats">
          ${{stat('Word Count', item.word_count)}}
          ${{stat('SEO Score', stats.seo_score || 0)}}
          ${{stat('Review Score', item.review_score || 0)}}
          ${{stat('Business Score', item.business_score || 0)}}
          ${{stat('Reading Time', (stats.reading_time_minutes || 0) + ' min')}}
          ${{stat('Internal Links', stats.internal_links || 0)}}
          ${{stat('External Links', stats.external_links || 0)}}
          ${{stat('Affiliate Links', stats.affiliate_links || 0)}}
          ${{stat('Featured Image', stats.featured_image || 'missing')}}
          ${{stat('Schema Status', stats.schema_status || 'missing')}}
          ${{stat('Meta Description', stats.meta_description || 'missing')}}
          ${{stat('OG Image', stats.og_image || 'missing')}}
          ${{stat('Canonical URL', stats.canonical_url || 'missing')}}
        </div>
        <h3>Social Drafts</h3>
        <div class="social-grid">
          ${{Object.entries(socialDrafts).map(([platform, href]) => button(href, platform.replaceAll('_', ' ').toUpperCase(), '', false)).join('') || '<p class="small">No social drafts found.</p>'}}
        </div>
        <p class="small">Next command: <code>${{esc(item.next_command)}}</code></p>
      `;
    }}

    function selectSlug(slug) {{
      const item = items.find((row) => row.slug === slug);
      rows.forEach((row) => row.classList.toggle('active', row.dataset.slug === slug));
      if (item) renderDetail(item);
    }}

    rows.forEach((row) => row.addEventListener('click', () => selectSlug(row.dataset.slug)));
    if (items.length) selectSlug(items[0].slug);
  </script>
</body>
</html>
"""
        html_text = "\n".join(line.rstrip() for line in html_text.splitlines()) + "\n"
        self.console_html.write_text(html_text, encoding="utf-8")

    def _button_html(self, href: str, label: str, tone: str = "", *, disabled: bool = False) -> str:
        safe_label = html.escape(label)
        class_name = "button" + (f" {tone}" if tone else "") + (" disabled" if disabled or not href else "")
        if disabled or not href:
            return f'<span class="{class_name}">{safe_label}</span>'
        safe_href = html.escape(href, quote=True)
        return f'<a class="{class_name}" href="{safe_href}">{safe_label}</a>'

    def _display_status_label(self, status: str) -> str:
        labels = {
            "approved": "Human Approved",
            "human_approved": "Human Approved",
            "blocked": "Publish Blocked",
            "approved_for_publish": "Ready for Publish",
            "published_local": "Published",
            "published": "Published",
            "needs_human_review": "Waiting for editor approval",
            "needs_revision": "Needs revision",
            "ai_review_passed": "AI Review Passed",
            "passed": "Passed",
            "missing": "Missing",
        }
        return labels.get(status.strip().lower(), status)

    def _badge_html(self, label: str, tone: str) -> str:
        return f'<span class="badge {html.escape(tone)}">{html.escape(label)}</span>'

    def _stat_html(self, label: str, value: Any) -> str:
        return f'<div class="stat"><strong>{html.escape(str(label))}</strong><span>{html.escape(str(value))}</span></div>'
