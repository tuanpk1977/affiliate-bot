from __future__ import annotations

import html
import io
import json
import secrets
import threading
import traceback
import urllib.parse
import webbrowser
from datetime import date
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from modules.daily_editorial_workflow import DailyEditorialWorkflow, REVIEWABLE_BATCH_STATES


class ReviewDashboardServer:
    def __init__(self, workflow: DailyEditorialWorkflow | None = None) -> None:
        self.workflow = workflow or DailyEditorialWorkflow()

    def serve(self, *, batch_date: str, host: str = "127.0.0.1", port: int = 8765, open_browser: bool = False) -> ThreadingHTTPServer:
        workflow = self.workflow
        csrf_token = secrets.token_urlsafe(24)
        server_ref: dict[str, ThreadingHTTPServer] = {}

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                parsed = urllib.parse.urlparse(self.path)
                params = urllib.parse.parse_qs(parsed.query)
                if parsed.path == "/health":
                    self._send_html("<html><body>ok</body></html>")
                    return
                if parsed.path == "/preview":
                    slug = (params.get("slug") or [""])[0]
                    if not slug:
                        self.send_error(HTTPStatus.BAD_REQUEST, "Missing slug")
                        return
                    preview = workflow.data_dir / "production_article_drafts" / slug / "index.html"
                    if not preview.exists():
                        self.send_error(HTTPStatus.NOT_FOUND, "Preview not found")
                        return
                    self._send_html(preview.read_text(encoding="utf-8", errors="ignore"))
                    return
                if parsed.path == "/artifact":
                    slug = (params.get("slug") or [""])[0]
                    artifact_type = (params.get("type") or [""])[0]
                    artifact = self._artifact_path(slug, artifact_type)
                    if artifact is None:
                        self.send_error(HTTPStatus.BAD_REQUEST, "Unsupported artifact")
                        return
                    if not artifact.exists():
                        self.send_error(HTTPStatus.NOT_FOUND, "Artifact not found")
                        return
                    if artifact.suffix.lower() in {".html", ".htm"}:
                        self._send_html(artifact.read_text(encoding="utf-8", errors="ignore"))
                    else:
                        self._send_text(artifact.read_text(encoding="utf-8", errors="ignore"))
                    return
                if parsed.path == "/shutdown":
                    self._send_html("<html><body>Shutting down...</body></html>")
                    threading.Thread(target=server_ref["server"].shutdown, daemon=True).start()
                    return
                requested_date = (params.get("date") or [batch_date])[0]
                resolved = self._resolve_batch_date(requested_date)
                selected_slug = (params.get("slug") or [""])[0]
                message = (params.get("message") or [""])[0]
                active_filter = (params.get("filter") or ["all"])[0]
                date_message = (
                    f"Requested date: {resolved['requested_date']} | "
                    f"Resolved batch date: {resolved['resolved_date']} | "
                    f"Draft count: {resolved['draft_count']}"
                )
                display_message = f"{date_message} | {message}" if message else date_message
                try:
                    self._send_html(
                        workflow.render_interactive_dashboard(
                            batch_date=resolved["resolved_date"],
                            selected_slug=selected_slug,
                            message=display_message,
                            active_filter=active_filter,
                            csrf_token=csrf_token,
                        )
                    )
                except Exception:
                    traceback.print_exc()
                    self._send_error_response(
                        HTTPStatus.INTERNAL_SERVER_ERROR,
                        "Dashboard render failed. Check the server console for the traceback.",
                    )

            def do_POST(self) -> None:  # noqa: N802
                parsed = urllib.parse.urlparse(self.path)
                length = int(self.headers.get("Content-Length", "0"))
                payload = urllib.parse.parse_qs(self.rfile.read(length).decode("utf-8"))
                target_date = (payload.get("date") or [batch_date])[0]
                slug = (payload.get("slug") or [""])[0]
                active_filter = (payload.get("filter") or ["all"])[0]
                anchor = (payload.get("anchor") or ([f"row-{slug}"] if slug else [""]))[0]
                submitted_token = (payload.get("csrf_token") or [""])[0]
                if submitted_token != csrf_token:
                    self._redirect(target_date, slug, "Security token expired. Refresh the dashboard and try again.", active_filter, anchor)
                    return
                try:
                    if parsed.path == "/approve":
                        workflow.approve(slug=slug, batch_date=target_date)
                        self._redirect(target_date, slug, "Article approved successfully", active_filter, anchor)
                        return
                    if parsed.path == "/reject":
                        reason = (payload.get("reason") or ["Need revision"])[0]
                        workflow.reject(slug=slug, batch_date=target_date, reason=reason)
                        self._redirect(target_date, slug, "Article rejected successfully", active_filter, anchor)
                        return
                    if parsed.path == "/publish":
                        workflow.publish_ready(batch_date=target_date)
                        self._redirect(target_date, slug, "Publish-ready workflow completed", active_filter, anchor)
                        return
                except Exception as exc:
                    self._redirect(target_date, slug, f"Error: {exc}", active_filter, anchor)
                    return
                self.send_error(HTTPStatus.NOT_FOUND, "Unsupported action")

            def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
                return

            def _send_html(self, content: str) -> None:
                encoded = content.encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)

            def _send_text(self, content: str) -> None:
                encoded = content.encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)

            def _send_error_response(self, status: HTTPStatus, message: str) -> None:
                safe_message = html.escape(message)
                content = f"<!doctype html><html><body><h1>{status.value} {html.escape(status.phrase)}</h1><p>{safe_message}</p></body></html>"
                encoded = content.encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)

            def _resolve_batch_date(self, requested_date: str) -> dict[str, Any]:
                return ReviewDashboardServer._resolve_batch_date_for_workflow(workflow, requested_date, default_date=batch_date)

            def _artifact_path(self, slug: str, artifact_type: str) -> Path | None:
                if not slug:
                    return None
                draft_dir = workflow.data_dir / "production_article_drafts" / slug
                paths = {
                    "draft": draft_dir / "article.md",
                    "html": draft_dir / "index.html",
                    "review": draft_dir / "review_summary.md",
                    "ai-report": draft_dir / "publish_readiness_report.md",
                    "metadata": draft_dir / "metadata.json",
                    "source-review": workflow.data_dir / "research" / slug / "sources.json",
                }
                return paths.get(artifact_type)

            def _redirect(self, batch_date_value: str, slug_value: str, message: str, active_filter: str = "all", anchor: str = "") -> None:
                query = urllib.parse.urlencode({"date": batch_date_value, "slug": slug_value, "filter": active_filter, "message": message})
                location = f"/?{query}"
                if anchor:
                    location = f"{location}#{urllib.parse.quote(anchor)}"
                self.send_response(HTTPStatus.SEE_OTHER)
                self.send_header("Location", location)
                self.end_headers()

        httpd = ThreadingHTTPServer((host, port), Handler)
        server_ref["server"] = httpd
        if open_browser:
            webbrowser.open(f"http://{host}:{port}/?date={urllib.parse.quote(batch_date)}")
        return httpd

    @staticmethod
    def _resolve_batch_date_for_workflow(workflow: DailyEditorialWorkflow, requested_date: str, *, default_date: str = "") -> dict[str, Any]:
        requested = (requested_date or default_date or "latest").strip() or "latest"
        queue_root = workflow.data_dir / "editorial_queue"

        def batch_info(batch: str) -> dict[str, Any] | None:
            path = queue_root / batch / "topics.json"
            if not path.exists():
                return None
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                return None
            topics = payload.get("topics", []) if isinstance(payload, dict) else []
            if not isinstance(topics, list):
                topics = []
            draft_count = 0
            for item in topics:
                if not isinstance(item, dict):
                    continue
                slug = str(item.get("slug") or "")
                draft_file = Path(str(item.get("draft_file") or "")) if str(item.get("draft_file") or "") else workflow.data_dir / "production_article_drafts" / slug / "index.html"
                review_preview = Path(str(item.get("review_preview") or "")) if str(item.get("review_preview") or "") else workflow.site_output_dir / "review" / batch / slug / "index.html"
                if draft_file.exists() or review_preview.exists():
                    draft_count += 1
            batch_state = workflow.batch_state(batch) if hasattr(workflow, "batch_state") else ""
            return {
                "date": batch,
                "topics": len(topics),
                "draft_count": draft_count,
                "batch_state": batch_state,
                "valid": bool(path.exists() and batch_state in REVIEWABLE_BATCH_STATES and draft_count > 0),
            }

        requested_info = None if requested.lower() == "latest" else batch_info(requested)
        if requested_info and requested_info["valid"]:
            return {
                "requested_date": requested,
                "resolved_date": requested,
                "draft_count": requested_info["draft_count"],
                "latest_batch_detection": "requested date has reviewable drafts",
            }

        candidates: list[dict[str, Any]] = []
        if queue_root.exists():
            for child in queue_root.iterdir():
                if not child.is_dir():
                    continue
                try:
                    date.fromisoformat(child.name)
                except ValueError:
                    continue
                info = batch_info(child.name)
                if info and info["valid"]:
                    candidates.append(info)
        if not candidates:
            fallback = requested if requested.lower() != "latest" else default_date
            fallback_info = batch_info(fallback) or {"draft_count": 0}
            return {
                "requested_date": requested,
                "resolved_date": fallback,
                "draft_count": int(fallback_info.get("draft_count", 0) or 0),
                "latest_batch_detection": "no draft-ready batch found",
            }
        latest = sorted(candidates, key=lambda row: str(row["date"]))[-1]
        return {
            "requested_date": requested,
            "resolved_date": str(latest["date"]),
            "draft_count": int(latest["draft_count"]),
            "latest_batch_detection": "latest draft-ready batch",
        }


def render_interactive_dashboard_html(*, workflow: DailyEditorialWorkflow, batch_date: str, selected_slug: str = "", message: str = "") -> str:
    return workflow.render_interactive_dashboard(batch_date=batch_date, selected_slug=selected_slug, message=message)
