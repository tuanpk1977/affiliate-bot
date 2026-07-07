from __future__ import annotations

import csv
import html
import json
import math
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
        self.console_json = self.data_dir / "editorial_operations_console.json"
        self.console_html = self.data_dir / "editorial_operations_console.html"
        self.console_csv = self.data_dir / "editorial_operations_console.csv"
        self.actions_dir = self.data_dir / "editorial_console_actions"
        self.review_queue_path = self.data_dir / "content_review_queue.json"
        self.human_queue_path = self.data_dir / "human_approval_queue.json"
        self.publish_queue_path = self.data_dir / "publish_queue.json"
        self.review_engine = ContentReviewEngine(data_dir=self.data_dir)
        self.human_workflow = HumanApprovalWorkflow(data_dir=self.data_dir)
        self.publish_gate = PublishGate(data_dir=self.data_dir, site_output_dir=self.site_output_dir)

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

    def _publish_slug(self, slug: str, *, rebuild: bool) -> dict[str, Any]:
        publish_rows = _read_json(self.publish_queue_path, [])
        publish_row = next((row for row in publish_rows if str(row.get("slug", "")) == slug), None)
        if not publish_row:
            raise ValueError(f"Unknown publish slug: {slug}")
        if str(publish_row.get("status", "")) != "approved_for_publish":
            raise ValueError(f"Slug is not approved for publish: {slug}")
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
            metadata = self._load_metadata(slug)
            review = review_rows.get(slug) or metadata.get("review") or {}
            human = human_rows.get(slug) or metadata.get("human_approval") or {}
            publish = publish_rows.get(slug) or metadata.get("publish_gate") or {}
            quality_gate = metadata.get("research_quality_gate") if isinstance(metadata.get("research_quality_gate"), dict) else {}
            title = str(metadata.get("title") or publish.get("title") or slug.replace("-", " "))
            status = self._overall_status(review, human, publish)
            draft_dir = self.drafts_dir / slug
            html_stats = self._extract_html_stats(draft_dir / "index.html", metadata=metadata, review=review)
            command_paths = self._build_action_launchers(slug)
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
                    "next_command": self._next_command(slug, human, publish),
                    "website_preview": self._website_preview_link(slug, publish),
                    "stats": html_stats,
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
            failures = [item for item in row.get("failures", []) if str(item).strip().lower() != "human approval missing"]
            row["human_approval_passed"] = True
            row["failures"] = failures
            row["publish_ready"] = not failures
            row["status"] = "approved_for_publish" if not failures else "blocked"
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
            failures = [item for item in row.get("failures", []) if str(item).strip().lower() != "human approval missing"]
            failures = [item for item in failures if not str(item).strip().lower().startswith("human approval rejected:")]
            failures.append(reason)
            row["human_approval_passed"] = False
            row["failures"] = failures
            row["publish_ready"] = False
            row["status"] = "blocked"
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

    def _preview_website_link(self) -> str:
        target = self.site_output_dir / "index.html"
        if not target.exists():
            return ""
        return "../site_output/index.html"

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
                ("approved_for_publish", "Approved For Publish"),
                ("published_local", "Published Local"),
                ("blocked", "Blocked"),
            )
        )
        rows_html = "".join(self._draft_card_html(row) for row in payload["items"])
        html_text = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Editorial Operations Console</title>
  <style>
    body {{ margin: 0; font-family: Georgia, 'Segoe UI', serif; background: linear-gradient(180deg, #f4efe6, #fffdfa); color: #201a14; }}
    .wrap {{ max-width: 1320px; margin: 0 auto; padding: 28px 20px 48px; }}
    .hero {{ background: #17324d; color: #fef8ee; border-radius: 18px; padding: 24px; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 14px; margin: 18px 0 26px; }}
    .card {{ background: #fff; border: 1px solid #e7dac6; border-radius: 16px; padding: 18px; box-shadow: 0 8px 28px rgba(23, 50, 77, 0.08); }}
    .draft-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(360px, 1fr)); gap: 18px; }}
    .draft-card {{ background: #fff; border: 1px solid #e7dac6; border-radius: 18px; padding: 20px; box-shadow: 0 8px 28px rgba(23, 50, 77, 0.08); }}
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
    code {{ background: #f3ebde; padding: 2px 6px; border-radius: 6px; }}
    a {{ color: #0f5f63; text-decoration: none; }}
    .panel {{ margin-top: 20px; }}
    .small {{ color: #6b5d4a; font-size: 14px; }}
    @media (max-width: 900px) {{ .stats {{ grid-template-columns: 1fr; }} .draft-grid {{ grid-template-columns: 1fr; }} }}
  </style>
</head>
<body>
  <main class="wrap">
    <section class="hero">
      <p>Local-only operator console</p>
      <h1>Editorial Operations Console</h1>
      <p>Open draft files directly from disk, review state across queues, and move approved content forward without deploy, push, or IndexNow.</p>
    </section>
    <section class="grid">{cards}</section>
    <section class="card panel">
      <h2>Next Command</h2>
      <p>If pending human review: <code>python scripts/editorial_console.py --approve best-ai-productivity-software</code></p>
      <p>If approved but not published: <code>python scripts/editorial_console.py --publish best-ai-productivity-software</code></p>
      <p>To refresh the console only: <code>python scripts/editorial_console.py --build</code></p>
    </section>
    <section class="card panel">
      <h2>Console Actions</h2>
      <div class="button-row">
        {self._button_html(global_actions.get('preview_website', ''), 'Preview Website', 'primary', disabled=not bool(global_actions.get('preview_website', '')))}
        {self._button_html(global_actions.get('publish_all_approved', ''), 'Publish All Approved', 'success')}
        {self._button_html(global_actions.get('rebuild_console', ''), 'Rebuild Console', 'warn')}
      </div>
      <p class="small">Publish All Approved only runs for rows already in <code>approved_for_publish</code>. It never auto-approves drafts.</p>
    </section>
    <section class="panel">
      <div class="draft-grid">{rows_html or '<div class="draft-card"><p>No draft rows found.</p></div>'}</div>
    </section>
  </main>
</body>
</html>
"""
        self.console_html.write_text(html_text, encoding="utf-8")

    def _draft_card_html(self, row: dict[str, Any]) -> str:
        stats = row["stats"]
        action_buttons = "".join(
            [
                self._button_html(row["article_markdown"], "Open Draft"),
                self._button_html(row["article_html"], "Open HTML Preview"),
                self._button_html(row["review_summary"], "Open Review Summary"),
                self._button_html(row["actions"]["approve"], "Approve", "success", disabled=row["human_approval_status"] != "needs_human_review"),
                self._button_html(row["actions"]["reject"], "Reject", "danger", disabled=row["publish_gate_status"] == "published_local"),
                self._button_html(row["actions"]["publish"], "Publish", "primary", disabled=not bool(row["publish_enabled"])),
            ]
        )
        status_chips = "".join(
            [
                self._badge_html(f"Overall: {row['status']}", self._status_tone(row["status"])),
                self._badge_html(f"Research: {row['research_quality_status']}", self._status_tone(row["research_quality_status"])),
                self._badge_html(f"AI Review: {row['ai_review_status']}", self._status_tone(row["ai_review_status"])),
                self._badge_html(f"Human: {row['human_approval_status']}", self._status_tone(row["human_approval_status"])),
                self._badge_html(f"Publish Gate: {row['publish_gate_status']}", self._status_tone(row["publish_gate_status"])),
            ]
        )
        stats_html = "".join(
            [
                self._stat_html("Word Count", row["word_count"]),
                self._stat_html("SEO Score", stats["seo_score"]),
                self._stat_html("Reading Time", f"{stats['reading_time_minutes']} min"),
                self._stat_html("Internal Links", stats["internal_links"]),
                self._stat_html("External Links", stats["external_links"]),
                self._stat_html("Affiliate Links", stats["affiliate_links"]),
                self._stat_html("Featured Image", stats["featured_image"]),
                self._stat_html("Schema Status", stats["schema_status"]),
                self._stat_html("Meta Description", stats["meta_description"] or "missing"),
                self._stat_html("OG Image", stats["og_image"]),
                self._stat_html("Canonical URL", stats["canonical_url"] or "missing"),
                self._stat_html("Last Updated", row["last_updated"]),
            ]
        )
        return f"""
        <article class="draft-card">
          <p class="small">Slug</p>
          <h2>{html.escape(str(row['title']))}</h2>
          <p><code>{html.escape(str(row['slug']))}</code></p>
          <div class="status-row">{status_chips}</div>
          <div class="button-row">{action_buttons}</div>
          <div class="button-row">
            {self._button_html(row["website_preview"], "Preview Website", "warn", disabled=not bool(row["website_preview"]))}
            {self._button_html(row["metadata_json"], "Open Metadata")}
            {self._button_html(row["publish_readiness_report"], "Open Publish Report")}
          </div>
          <div class="stats">{stats_html}</div>
          <p class="small">Next command: <code>{html.escape(str(row['next_command']))}</code></p>
        </article>
        """

    def _button_html(self, href: str, label: str, tone: str = "", *, disabled: bool = False) -> str:
        safe_label = html.escape(label)
        class_name = "button" + (f" {tone}" if tone else "") + (" disabled" if disabled or not href else "")
        if disabled or not href:
            return f'<span class="{class_name}">{safe_label}</span>'
        safe_href = html.escape(href, quote=True)
        return f'<a class="{class_name}" href="{safe_href}">{safe_label}</a>'

    def _badge_html(self, label: str, tone: str) -> str:
        return f'<span class="badge {html.escape(tone)}">{html.escape(label)}</span>'

    def _stat_html(self, label: str, value: Any) -> str:
        return f'<div class="stat"><strong>{html.escape(str(label))}</strong><span>{html.escape(str(value))}</span></div>'
