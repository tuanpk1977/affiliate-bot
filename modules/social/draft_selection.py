from __future__ import annotations

from pathlib import Path
from typing import Any, Callable


class SocialDraftSelectionService:
    def __init__(
        self,
        *,
        data_dir: Path,
        draft_root: Path,
        read_json: Callable[[Path, Any], Any],
        slug_from_url: Callable[[str], str],
        looks_like_iso_date: Callable[[str], bool],
    ) -> None:
        self.data_dir = data_dir
        self.draft_root = draft_root
        self.read_json = read_json
        self.slug_from_url = slug_from_url
        self.looks_like_iso_date = looks_like_iso_date

    def _live_report_items(
        self,
        batch_date: str | None = None,
        *,
        is_live_200: Callable[[dict[str, Any]], bool] | None = None,
    ) -> tuple[str, list[dict[str, Any]]]:
        checker = is_live_200 or self._is_live_200
        report = self.read_json(self.data_dir / "live_status_report.json", {})
        receipts = self.read_json(self.data_dir / "published_live_urls_latest.json", {})
        requested = str(batch_date or "latest")

        sources: list[tuple[str, list[dict[str, Any]]]] = []
        report_date = str(report.get("date") or report.get("batch_date") or "")
        report_items = report.get("items") or []
        # A Menu 7 blocked-only view is not a website-live inventory.  Older
        # versions overwrote live_status_report.json with that filtered view;
        # ignore it here and recover from the post-push live receipt.
        if not bool(report.get("blocked_only")) and isinstance(report_items, list):
            sources.append((report_date, [item for item in report_items if isinstance(item, dict)]))

        receipt_date = str(receipts.get("batch_date") or receipts.get("date") or "")
        receipt_items = receipts.get("items") or []
        if isinstance(receipt_items, list):
            normalized_receipts: list[dict[str, Any]] = []
            for item in receipt_items:
                if not isinstance(item, dict):
                    continue
                normalized = dict(item)
                normalized.setdefault("batch_date", receipt_date)
                normalized.setdefault("title", str(item.get("slug") or "").replace("-", " ").title())
                normalized_receipts.append(normalized)
            sources.append((receipt_date, normalized_receipts))

        if requested != "latest":
            resolved = requested
        else:
            live_dates = [
                source_date
                for source_date, rows in sources
                if source_date and any(checker(row) for row in rows)
            ]
            resolved = max(live_dates) if live_dates else (report_date or receipt_date)

        merged: dict[str, dict[str, Any]] = {}
        for source_date, rows in sources:
            if source_date != resolved:
                continue
            for item in rows:
                slug = str(item.get("slug") or self.slug_from_url(str(item.get("url") or "")))
                if not slug:
                    continue
                existing = merged.get(slug)
                if existing is None or (checker(item) and not checker(existing)):
                    merged[slug] = dict(item)
        return resolved, list(merged.values())

    def _social_batch_dates(self) -> list[str]:
        if not self.draft_root.exists():
            return []
        return sorted(
            path.name
            for path in self.draft_root.iterdir()
            if path.is_dir() and self.looks_like_iso_date(path.name)
        )

    def resolve_latest_live_batch(
        self,
        requested_date: str = "latest",
        *,
        live_report_items: Callable[..., tuple[str, list[dict[str, Any]]]] | None = None,
        is_live_200: Callable[[dict[str, Any]], bool] | None = None,
        social_batch_dates: Callable[[], list[str]] | None = None,
    ) -> str:
        """Resolve the newest website-live batch used to create social queues."""
        if requested_date and requested_date != "latest":
            return requested_date
        report_reader = live_report_items or self._live_report_items
        checker = is_live_200 or self._is_live_200
        batch_dates = social_batch_dates or self._social_batch_dates
        report_date, items = report_reader()
        if report_date and any(checker(item) for item in items):
            return report_date
        latest = self.read_json(self.data_dir / "published_live_urls_latest.json", {})
        if isinstance(latest, dict) and latest.get("batch_date"):
            return str(latest["batch_date"])
        existing = batch_dates()
        if existing:
            return existing[-1]
        return report_date or "latest"

    def resolve_latest_social_batch(
        self,
        requested_date: str = "latest",
        *,
        social_batch_dates: Callable[[], list[str]] | None = None,
        resolve_latest_live_batch: Callable[[str], str] | None = None,
    ) -> str:
        """Resolve the newest existing social-review batch.

        Social review is intentionally independent from the latest website-live
        report. A newer hot-news or imported social batch may exist without a
        corresponding website article, so Menu G must prefer the canonical
        social manifests on disk.
        """
        if requested_date and requested_date != "latest":
            return requested_date
        batch_dates = social_batch_dates or self._social_batch_dates
        live_batch_resolver = resolve_latest_live_batch or self.resolve_latest_live_batch
        existing = batch_dates()
        manifest_dates = [
            date
            for date in existing
            if (self.draft_root / date / "manifest.json").is_file()
        ]
        if manifest_dates:
            return manifest_dates[-1]
        return live_batch_resolver(requested_date)

    def _is_live_200(self, row: dict[str, Any]) -> bool:
        values = [
            row.get("live_http_status"),
            row.get("http_status"),
            row.get("live_status"),
            row.get("display_status"),
            row.get("status"),
        ]
        normalized = [str(value).lower() for value in values if value not in (None, "")]
        return any(value == "200" or "live 200" in value or value == "live" for value in normalized)

    def live_articles(
        self,
        batch_date: str = "latest",
        *,
        resolve_latest_live_batch: Callable[[str], str] | None = None,
        live_report_items: Callable[..., tuple[str, list[dict[str, Any]]]] | None = None,
        is_live_200: Callable[[dict[str, Any]], bool] | None = None,
    ) -> list[dict[str, Any]]:
        live_batch_resolver = resolve_latest_live_batch or self.resolve_latest_live_batch
        report_reader = live_report_items or self._live_report_items
        checker = is_live_200 or self._is_live_200
        resolved = live_batch_resolver(batch_date)
        report_date, items = report_reader(resolved)
        if report_date != resolved and batch_date != "latest":
            return []
        live: list[dict[str, Any]] = []
        for item in items:
            url = str(item.get("url") or "")
            slug = str(item.get("slug") or self.slug_from_url(url))
            if not slug or not url.startswith("https://") or not checker(item):
                continue
            live.append(
                {
                    "slug": slug,
                    "title": str(item.get("title") or slug.replace("-", " ").title()),
                    "url": url,
                    "batch_date": resolved,
                    "source": "live_status_report",
                }
            )
        return live
