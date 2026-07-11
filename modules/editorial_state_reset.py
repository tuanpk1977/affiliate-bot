from __future__ import annotations

import json
import shutil
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


PUBLISHED_STATES = {"published", "published_local", "live", "live 200"}
READY_STATES = {"approved_for_publish", "ready_for_publish", "ready for publish"}
APPROVED_STATES = {"approved", "human_approved", "human approved"}


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _slug_from_url(value: str) -> str:
    parts = [part for part in urlparse(value).path.split("/") if part]
    return parts[0] if len(parts) == 1 else ""


class EditorialStateReset:
    """Plan and archive stale unpublished editorial records without touching public output."""

    queue_names = ("content_review_queue.json", "human_approval_queue.json", "publish_queue.json")

    def __init__(self, *, root: Path, workflow: Any | None = None) -> None:
        self.root = root.resolve()
        self.data_dir = self.root / "data"
        self.workflow = workflow

    def _directory_slugs(self, root: Path) -> set[str]:
        if not root.exists():
            return set()
        return {path.name for path in root.iterdir() if path.is_dir() and (path / "index.html").exists()}

    def _sitemap_slugs(self) -> set[str]:
        slugs: set[str] = set()
        for path in (self.root / "docs" / "sitemap.xml", self.root / "site_output" / "sitemap.xml"):
            if not path.exists():
                continue
            try:
                root = ET.fromstring(path.read_text(encoding="utf-8"))
            except (ET.ParseError, UnicodeError):
                continue
            for node in root.iter():
                if node.tag.endswith("loc") and node.text:
                    slug = _slug_from_url(node.text.strip())
                    if slug:
                        slugs.add(slug)
        return slugs

    def _history_slugs(self) -> set[str]:
        slugs: set[str] = set()
        latest = _read_json(self.data_dir / "published_live_urls_latest.json", {})
        for row in latest.get("items", []) if isinstance(latest, dict) else []:
            slug = str(row.get("slug") or _slug_from_url(str(row.get("url") or "")))
            if slug:
                slugs.add(slug)
        history = self.data_dir / "published_live_urls.jsonl"
        if history.exists():
            for line in history.read_text(encoding="utf-8", errors="ignore").splitlines():
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                slug = str(row.get("slug") or _slug_from_url(str(row.get("url") or "")))
                if slug:
                    slugs.add(slug)
        return slugs

    def protected_slugs(self, active_date: str) -> tuple[set[str], dict[str, list[str]]]:
        reasons: dict[str, set[str]] = {}

        def protect(slug: str, reason: str) -> None:
            if slug:
                reasons.setdefault(slug, set()).add(reason)

        for base, reason in (
            (self.root / "docs", "docs output"),
            (self.root / "site_output", "site_output"),
            (self.data_dir / "published_static_pages", "published static output"),
        ):
            for slug in self._directory_slugs(base):
                protect(slug, reason)
        for slug in self._sitemap_slugs():
            protect(slug, "sitemap")
        for slug in self._history_slugs():
            protect(slug, "published live history")
        for row in _read_json(self.data_dir / "publish_queue.json", []):
            status = str(row.get("status") or "").lower()
            if status in PUBLISHED_STATES:
                protect(str(row.get("slug") or ""), "published queue status")
        live = _read_json(self.data_dir / "live_status_report.json", {})
        for row in live.get("items", []) if isinstance(live, dict) else []:
            status_text = " ".join(str(row.get(key) or "").lower() for key in ("display_status", "publish_gate_status", "live_status"))
            if "live 200" in status_text or "published" in status_text or int(row.get("live_http_status") or 0) == 200:
                protect(str(row.get("slug") or ""), "dashboard/live published status")
        active = _read_json(self.data_dir / "editorial_queue" / active_date / "topics.json", {})
        for row in active.get("topics", []) if isinstance(active, dict) else []:
            protect(str(row.get("slug") or ""), "current active batch")
        seo = _read_json(self.data_dir / "seo" / "opportunities.json", [])
        for row in seo if isinstance(seo, list) else []:
            if bool(row.get("selected")) or str(row.get("queue_status") or "").lower() == "selected":
                protect(str(row.get("slug") or ""), "SEO selected opportunity")
        for queue_dir in (self.data_dir / "editorial_queue").glob("*/topics.json"):
            payload = _read_json(queue_dir, {})
            for row in payload.get("topics", []) if isinstance(payload, dict) else []:
                if str(row.get("source") or "") == "seo_engine" and str(row.get("status") or "").lower() == "selected":
                    protect(str(row.get("slug") or ""), "SEO selected queue item")
        return set(reasons), {slug: sorted(values) for slug, values in sorted(reasons.items())}

    @staticmethod
    def _unsafe_status(row: dict[str, Any]) -> bool:
        values = {str(row.get(key) or "").strip().lower() for key in ("status", "editorial_status", "publish_gate_status", "display_status")}
        return bool(values & (PUBLISHED_STATES | READY_STATES | APPROVED_STATES)) or int(row.get("live_http_status") or 0) == 200

    def plan(self, *, before_date: str | None = None) -> dict[str, Any]:
        queue_root = self.data_dir / "editorial_queue"
        dates = sorted(path.parent.name for path in queue_root.glob("*/topics.json") if path.parent.name[:4].isdigit())
        active_date = max(dates) if dates else (before_date or datetime.now(UTC).date().isoformat())
        cutoff = before_date or active_date
        protected, protected_records = self.protected_slugs(active_date)
        candidates: dict[str, set[str]] = {}
        batch_rows: dict[str, list[str]] = {}
        row_by_slug: dict[str, list[dict[str, Any]]] = {}
        for name in self.queue_names:
            for row in _read_json(self.data_dir / name, []):
                row_by_slug.setdefault(str(row.get("slug") or ""), []).append(row)
        for path in queue_root.glob("*/topics.json"):
            batch_date = path.parent.name
            if batch_date >= cutoff or batch_date == active_date:
                continue
            payload = _read_json(path, {})
            for row in payload.get("topics", []) if isinstance(payload, dict) else []:
                slug = str(row.get("slug") or "")
                candidates.setdefault(slug, set()).add(f"editorial batch {batch_date}")
                batch_rows.setdefault(path.relative_to(self.root).as_posix(), []).append(slug)
                row_by_slug.setdefault(slug, []).append(row)
        stale: list[str] = []
        excluded: dict[str, str] = {}
        for slug in sorted(candidates):
            if not slug:
                continue
            if slug in protected:
                excluded[slug] = "protected"
            elif any(self._unsafe_status(row) for row in row_by_slug.get(slug, [])):
                excluded[slug] = "approved, ready, published, or live state"
            else:
                stale.append(slug)
        stale_set = set(stale)
        queue_rows = {}
        for name in self.queue_names:
            rows = _read_json(self.data_dir / name, [])
            selected = [str(row.get("slug") or "") for row in rows if str(row.get("slug") or "") in stale_set]
            if selected:
                queue_rows[(self.data_dir / name).relative_to(self.root).as_posix()] = selected
        for path_text, slugs in batch_rows.items():
            selected = [slug for slug in slugs if slug in stale_set]
            if selected:
                queue_rows[path_text] = selected
        file_paths: set[str] = set()
        for slug in stale:
            for path in (
                self.data_dir / "production_article_drafts" / slug,
                self.data_dir / "research" / slug,
            ):
                if path.exists():
                    file_paths.add(path.relative_to(self.root).as_posix())
            for date_dir in (self.root / "upload").glob("*"):
                if date_dir.name >= cutoff:
                    continue
                for section in ("drafts", "review"):
                    path = date_dir / section / slug
                    if path.exists():
                        file_paths.add(path.relative_to(self.root).as_posix())
            for date_dir in (self.root / "site_output" / "review").glob("*"):
                if date_dir.name >= cutoff:
                    continue
                path = date_dir / slug
                if path.exists():
                    file_paths.add(path.relative_to(self.root).as_posix())
        return {
            "dry_run": True, "active_date": active_date, "before_date": cutoff,
            "protected_count": len(protected), "protected_slugs": sorted(protected), "protected_records": protected_records,
            "stale_candidate_count": len(candidates), "stale_count": len(stale), "stale_slugs": stale,
            "excluded_candidates": excluded, "files_to_archive": sorted(file_paths), "queue_rows_to_remove": queue_rows,
            "queue_row_count": sum(len(rows) for rows in queue_rows.values()),
            "candidates_examined": len(candidates),
            "protected_candidates": len(excluded),
            "stale_items_to_archive": len(stale),
        }

    def apply(self, *, before_date: str | None = None) -> dict[str, Any]:
        plan = self.plan(before_date=before_date)
        previous_summary = _read_json(self.data_dir / "archive" / "unpublished_reset" / "latest_summary.json", {})
        live_before = _read_json(self.data_dir / "live_status_report.json", {})
        confirmed_live = {
            str(row.get("slug") or "")
            for row in live_before.get("items", []) if isinstance(live_before, dict)
            if int(row.get("live_http_status") or 0) == 200
        }
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        archive = self.data_dir / "archive" / "unpublished_reset" / stamp
        archive.mkdir(parents=True, exist_ok=False)
        _write_json(archive / "reset_manifest.json", plan)
        _write_json(archive / "protected_records.json", plan["protected_records"])
        removed_records: dict[str, list[dict[str, Any]]] = {}
        stale = set(plan["stale_slugs"])
        for path_text in plan["queue_rows_to_remove"]:
            source = self.root / path_text
            payload = _read_json(source, [] if source.name != "topics.json" else {})
            _write_json(archive / "backups" / path_text, payload)
            if isinstance(payload, list):
                removed = [row for row in payload if str(row.get("slug") or "") in stale]
                kept = [row for row in payload if str(row.get("slug") or "") not in stale]
                _write_json(source, kept)
            else:
                rows = list(payload.get("topics", []))
                removed = [row for row in rows if str(row.get("slug") or "") in stale]
                payload["topics"] = [row for row in rows if str(row.get("slug") or "") not in stale]
                payload["count"] = len(payload["topics"])
                _write_json(source, payload)
            removed_records[path_text] = removed
        archived_paths = []
        for path_text in plan["files_to_archive"]:
            source = self.root / path_text
            if not source.exists():
                continue
            target = archive / "files" / path_text
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(target))
            archived_paths.append(path_text)
        _write_json(archive / "removed_records.json", removed_records)
        restored_published = self._restore_confirmed_published(confirmed_live, active_date=plan["active_date"])
        summary = {**plan, "dry_run": False, "archive_dir": str(archive), "archived_paths": archived_paths, "applied_at": datetime.now(UTC).isoformat()}
        summary["restored_published_slugs"] = restored_published
        _write_json(archive / "apply_result.json", summary)
        _write_json(self.data_dir / "archive" / "unpublished_reset" / "latest_summary.json", {
            "archive_dir": str(archive),
            "archived_count": int(previous_summary.get("archived_count") or 0) + len(stale),
            "queue_rows_removed": int(previous_summary.get("queue_rows_removed") or 0) + plan["queue_row_count"],
            "applied_at": summary["applied_at"],
        })
        if self.workflow is not None:
            self.workflow.console.review_engine.refresh_reports()
            self.workflow.console.publish_gate.refresh_reports()
            self.workflow.console.build_console()
            self.workflow.build_review_dashboard(batch_date=plan["active_date"])
            self.workflow.check_live(batch_date=plan["active_date"], include_all=False)
        summary["final_plan"] = self.plan(before_date=before_date)
        return summary

    def _restore_confirmed_published(self, slugs: set[str], *, active_date: str) -> list[str]:
        valid = {
            slug for slug in slugs
            if slug
            and (self.root / "docs" / slug / "index.html").exists()
            and (self.root / "site_output" / slug / "index.html").exists()
            and (self.data_dir / "published_static_pages" / slug / "index.html").exists()
        }
        if not valid:
            return []
        publish_path = self.data_dir / "publish_queue.json"
        publish_rows = _read_json(publish_path, [])
        for row in publish_rows:
            if str(row.get("slug") or "") not in valid:
                continue
            row["status"] = "published_local"
            row["published_local"] = True
            row["failures"] = []
            row["hard_blockers"] = []
            row["warnings"] = []
            row["pending_reviews"] = []
        _write_json(publish_path, publish_rows)
        batch_path = self.data_dir / "editorial_queue" / active_date / "topics.json"
        batch = _read_json(batch_path, {})
        for row in batch.get("topics", []) if isinstance(batch, dict) else []:
            if str(row.get("slug") or "") in valid:
                row["status"] = "published"
        if batch:
            _write_json(batch_path, batch)
        return sorted(valid)
