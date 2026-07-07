from __future__ import annotations

import csv
import html
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

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
        payload = {"summary": summary, "items": rows}
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

    def _write_console_html(self, payload: dict[str, Any]) -> None:
        summary = payload["summary"]
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
        rows_html = "".join(
            f"""
            <tr>
              <td><strong>{html.escape(str(row['title']))}</strong><br><code>{html.escape(str(row['slug']))}</code></td>
              <td>{html.escape(str(row['status']))}</td>
              <td>{html.escape(str(row['research_quality_status']))}</td>
              <td>{html.escape(str(row['ai_review_status']))}</td>
              <td>{html.escape(str(row['human_approval_status']))}</td>
              <td>{html.escape(str(row['publish_gate_status']))}</td>
              <td>{html.escape(str(row['word_count']))}</td>
              <td>{html.escape(str(row['last_updated']))}</td>
              <td>
                {self._link_html(row['article_markdown'], 'article.md')}
                {self._link_html(row['article_html'], 'index.html')}
                {self._link_html(row['metadata_json'], 'metadata.json')}
                {self._link_html(row['review_summary'], 'review_summary.md')}
                {self._link_html(row['publish_readiness_report'], 'publish_readiness_report.md')}
              </td>
              <td><code>{html.escape(str(row['next_command']))}</code></td>
            </tr>
            """
            for row in payload["items"]
        )
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
    table {{ width: 100%; border-collapse: collapse; background: #fff; border-radius: 18px; overflow: hidden; }}
    th, td {{ border-bottom: 1px solid #eee4d3; padding: 14px 12px; vertical-align: top; text-align: left; }}
    th {{ background: #f5eee1; }}
    code {{ background: #f3ebde; padding: 2px 6px; border-radius: 6px; }}
    a {{ color: #0f5f63; text-decoration: none; margin-right: 8px; display: inline-block; margin-bottom: 6px; }}
    .panel {{ margin-top: 20px; }}
    @media (max-width: 900px) {{ table, thead, tbody, tr, td, th {{ font-size: 14px; }} }}
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
    <section class="panel">
      <table>
        <thead>
          <tr>
            <th>Draft</th>
            <th>Status</th>
            <th>Research</th>
            <th>AI Review</th>
            <th>Human Approval</th>
            <th>Publish Gate</th>
            <th>Words</th>
            <th>Last Updated</th>
            <th>Open Files</th>
            <th>Next Command</th>
          </tr>
        </thead>
        <tbody>{rows_html or '<tr><td colspan="10">No draft rows found.</td></tr>'}</tbody>
      </table>
    </section>
  </main>
</body>
</html>
"""
        self.console_html.write_text(html_text, encoding="utf-8")

    def _link_html(self, relative_path: str, label: str) -> str:
        if not relative_path:
            return ""
        safe_href = html.escape(relative_path, quote=True)
        safe_label = html.escape(label)
        return f'<a href="{safe_href}">{safe_label}</a>'
