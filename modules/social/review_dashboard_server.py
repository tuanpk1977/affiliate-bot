from __future__ import annotations

import json
import socket
import subprocess
import sys
import threading
import time
import traceback
import urllib.error
import urllib.request
import webbrowser
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from os import getpid
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from .draft_workflow import SocialDraftWorkflow
from .utils import now_iso


def _safe_asset_part(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", value or ""):
        raise ValueError("invalid asset path")
    return value


def _state_path(root: Path) -> Path:
    return root / "artifacts" / "social_dashboard" / "server_state.json"


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _port_available(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.3)
        return sock.connect_ex((host, port)) != 0


def dashboard_health(host: str = "127.0.0.1", port: int = 8776) -> dict[str, Any]:
    url = f"http://{host}:{port}/health"
    try:
        with urllib.request.urlopen(url, timeout=1.0) as response:
            body = response.read().decode("utf-8")
            payload = json.loads(body or "{}")
            return {
                "healthy": response.status == 200 and bool(payload.get("ok")),
                "status": response.status,
                "url": url,
                "payload": payload,
            }
    except Exception as exc:
        return {"healthy": False, "status": None, "url": url, "error": str(exc)}


def _next_available_port(host: str, preferred: int) -> int:
    for port in range(preferred, preferred + 20):
        if _port_available(host, port):
            return port
    raise RuntimeError(f"No available social dashboard port found near {preferred}.")


class SocialReviewDashboardServer:
    def __init__(self, *, root: Path, date: str = "latest", host: str = "127.0.0.1", port: int = 8776) -> None:
        self.root = root
        self.date = date
        self.host = host
        self.port = port
        self.workflow = SocialDraftWorkflow(root=root)

    def url(self) -> str:
        return f"http://{self.host}:{self.port}/?date={self.date}"

    def serve(self, *, open_browser: bool = False) -> None:
        parent = self
        httpd: ThreadingHTTPServer | None = None

        class Handler(BaseHTTPRequestHandler):
            server_version = "SmileSocialReview/1.0"

            def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
                print(f"[social-dashboard] {self.address_string()} - {format % args}")

            def _send(self, status: int, body: str | bytes, content_type: str) -> None:
                if isinstance(body, str):
                    payload = body.encode("utf-8")
                else:
                    payload = body
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def _json(self, status: int, payload: dict[str, Any]) -> None:
                self._send(status, json.dumps(payload, ensure_ascii=False), "application/json; charset=utf-8")

            def _send_asset(self, parsed: Any) -> None:
                parts = [part for part in parsed.path.split("/") if part]
                if len(parts) != 4 or parts[0] != "assets":
                    self._send(404, "Not found", "text/plain; charset=utf-8")
                    return
                date = _safe_asset_part(parts[1])
                slug = _safe_asset_part(parts[2])
                filename = _safe_asset_part(parts[3])
                if not filename.endswith(".png"):
                    self._send(404, "Only PNG social assets are available.", "text/plain; charset=utf-8")
                    return
                root = (parent.workflow.draft_root / date / slug / "assets").resolve()
                path = (root / filename).resolve()
                if root not in path.parents or not path.exists():
                    self._send(404, "Asset not found", "text/plain; charset=utf-8")
                    return
                payload = path.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                if parse_qs(parsed.query).get("download"):
                    self.send_header("Content-Disposition", f'attachment; filename="{slug}-{filename}"')
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def do_GET(self) -> None:  # noqa: N802
                try:
                    parsed = urlparse(self.path)
                    if parsed.path == "/health":
                        self._json(
                            200,
                            {
                                "ok": True,
                                "service": "social_review_dashboard",
                                "pid": getpid(),
                                "port": parent.port,
                                "date": parent.date,
                            },
                        )
                        return
                    if parsed.path == "/favicon.ico":
                        self._send(204, b"", "image/x-icon")
                        return
                    if parsed.path.startswith("/assets/"):
                        self._send_asset(parsed)
                        return
                    if parsed.path not in {"", "/"}:
                        self._send(404, "Not found", "text/plain; charset=utf-8")
                        return
                    query = parse_qs(parsed.query)
                    date = query.get("date", [parent.date])[0] or parent.date
                    payload = parent.workflow.dashboard_payload(batch_date=date)
                    html = parent.workflow.render_review_dashboard_html(payload)
                    self._send(200, html, "text/html; charset=utf-8")
                except Exception:
                    traceback.print_exc()
                    self._send(500, "Social review dashboard render failed. See console for traceback.", "text/plain; charset=utf-8")

            def do_POST(self) -> None:  # noqa: N802
                try:
                    length = int(self.headers.get("Content-Length") or "0")
                    payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
                    parsed = urlparse(self.path)
                    parts = [part for part in parsed.path.split("/") if part]
                    if len(parts) != 3 or parts[:2] != ["api", "social"]:
                        self._json(404, {"error": "unknown endpoint"})
                        return
                    action = parts[2]
                    if action == "stop":
                        self._json(200, {"ok": True, "message": "Dashboard server stopped. You may close this browser tab and continue in Runbot Menu."})
                        if httpd is not None:
                            threading.Thread(target=httpd.shutdown, daemon=True).start()
                        return
                    batch_date = str(payload.get("date") or parent.date)
                    slug = str(payload.get("slug") or "")
                    platform = str(payload.get("platform") or "")
                    if not slug or not platform:
                        self._json(400, {"error": "slug and platform are required"})
                        return
                    if action == "save":
                        item = parent.workflow.save_platform_draft(
                            batch_date=batch_date,
                            slug=slug,
                            platform=platform,
                            title=str(payload.get("title") or ""),
                            body=str(payload.get("body") or ""),
                            cta=str(payload.get("cta") or ""),
                            hashtags=payload.get("hashtags") or "",
                            image_url=str(payload.get("image_url") or ""),
                            reviewer_notes=str(payload.get("reviewer_notes") or ""),
                        )
                        self._json(200, {"ok": True, "item": item})
                        return
                    if action == "status":
                        parent.workflow.set_platform_status(
                            batch_date=batch_date,
                            slug=slug,
                            platform=platform,
                            status=str(payload.get("status") or ""),
                            reviewer_notes=str(payload.get("reviewer_notes") or ""),
                        )
                        item = parent.workflow.platform_payload(batch_date=batch_date, slug=slug, platform=platform)
                        self._json(200, {"ok": True, "item": item})
                        return
                    if action == "select-variant":
                        item = parent.workflow.select_platform_variant(
                            batch_date=batch_date,
                            slug=slug,
                            platform=platform,
                            variant=str(payload.get("variant") or ""),
                            approve=bool(payload.get("approve")),
                            reviewer_notes=str(payload.get("reviewer_notes") or ""),
                        )
                        self._json(200, {"ok": True, "item": item})
                        return
                    if action == "regenerate-final":
                        item = parent.workflow.recompose_final_platform_post(
                            batch_date=batch_date,
                            slug=slug,
                            platform=platform,
                            reviewer_notes=str(payload.get("reviewer_notes") or ""),
                        )
                        self._json(200, {"ok": True, "item": item})
                        return
                    if action == "pinterest-pending":
                        parent.workflow.mark_pending_manual_publish(
                            batch_date=batch_date,
                            slug=slug,
                            platform=platform,
                        )
                        item = parent.workflow.platform_payload(batch_date=batch_date, slug=slug, platform=platform)
                        self._json(200, {"ok": True, "item": item})
                        return
                    if action == "pinterest-published-url":
                        parent.workflow.mark_published_manual(
                            batch_date=batch_date,
                            slug=slug,
                            platform=platform,
                            published_url=str(payload.get("final_published_url") or payload.get("published_url") or ""),
                            allow_duplicate_override=bool(payload.get("allow_duplicate_override")),
                        )
                        item = parent.workflow.platform_payload(batch_date=batch_date, slug=slug, platform=platform)
                        self._json(200, {"ok": True, "item": item})
                        return
                    if action == "pinterest-reset-published":
                        parent.workflow.reset_published_manual(
                            batch_date=batch_date,
                            slug=slug,
                            platform=platform,
                            confirmed=bool(payload.get("confirmed")),
                        )
                        item = parent.workflow.platform_payload(batch_date=batch_date, slug=slug, platform=platform)
                        self._json(200, {"ok": True, "item": item})
                        return
                    if action == "copy":
                        path = parent.workflow.write_copy_fallback(
                            batch_date=batch_date,
                            slug=slug,
                            platform=platform,
                            field=str(payload.get("field") or "all"),
                            text=str(payload.get("text") or ""),
                        )
                        self._json(200, {"ok": True, "file_path": str(path)})
                        return
                    self._json(404, {"error": "unknown action"})
                except Exception as exc:
                    traceback.print_exc()
                    self._json(500, {"error": str(exc)})

        httpd = ThreadingHTTPServer((self.host, self.port), Handler)
        _write_json(
            _state_path(self.root),
            {
                "pid": getpid(),
                "host": self.host,
                "port": self.port,
                "date": self.date,
                "url": self.url(),
                "started_at": now_iso(),
                "service": "social_review_dashboard",
            },
        )
        print(f"Social review dashboard server: {self.url()}")
        if open_browser:
            webbrowser.open(self.url())
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("Social review dashboard server stopped.")


class SocialReviewDashboardLauncher:
    def __init__(self, *, root: Path, date: str = "latest", host: str = "127.0.0.1", port: int = 8776) -> None:
        self.root = root
        self.date = date
        self.host = host
        self.port = port

    def _state(self) -> dict[str, Any]:
        return _read_json(_state_path(self.root))

    def _healthy_existing(self) -> dict[str, Any] | None:
        state = self._state()
        port = int(state.get("port") or self.port)
        host = str(state.get("host") or self.host)
        health = dashboard_health(host, port)
        if health.get("healthy"):
            return {**state, "host": host, "port": port, "url": f"http://{host}:{port}/?date={self.date}", "health": health}
        return None

    def launch(self, *, open_browser: bool = True) -> dict[str, Any]:
        existing = self._healthy_existing()
        if existing:
            if open_browser:
                webbrowser.open(str(existing["url"]))
            return {"status": "reused_existing", **existing}

        selected_port = self.port
        stale_or_busy = ""
        if not _port_available(self.host, self.port):
            health = dashboard_health(self.host, self.port)
            if health.get("healthy"):
                url = f"http://{self.host}:{self.port}/?date={self.date}"
                if open_browser:
                    webbrowser.open(url)
                return {"status": "reused_existing", "host": self.host, "port": self.port, "url": url, "health": health}
            stale_or_busy = f"Port {self.port} is busy but does not look like the Social Review Dashboard."
            selected_port = _next_available_port(self.host, self.port + 1)

        command = [
            sys.executable,
            str(self.root / "social_console.py"),
            "review-dashboard",
            "--date",
            self.date,
            "--serve",
            "--port",
            str(selected_port),
        ]
        creationflags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
        process = subprocess.Popen(command, cwd=str(self.root), creationflags=creationflags)
        url = f"http://{self.host}:{selected_port}/?date={self.date}"
        _write_json(
            _state_path(self.root),
            {
                "pid": process.pid,
                "host": self.host,
                "port": selected_port,
                "date": self.date,
                "url": url,
                "started_at": now_iso(),
                "service": "social_review_dashboard",
                "command": command,
            },
        )
        health = {"healthy": False}
        for _ in range(25):
            health = dashboard_health(self.host, selected_port)
            if health.get("healthy"):
                break
            time.sleep(0.2)
        if open_browser:
            webbrowser.open(url)
        return {
            "status": "started",
            "pid": process.pid,
            "host": self.host,
            "port": selected_port,
            "url": url,
            "health": health,
            "note": stale_or_busy,
        }
