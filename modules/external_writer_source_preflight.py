from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from modules.research_artifacts import resolve_research_artifacts
from modules.research_enrichment import SourceRetriever


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return default


def _text(value: Any) -> str:
    return str(value or "").strip()


def _http_url(value: Any) -> bool:
    parsed = urlparse(_text(value))
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _relative(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path)


def _website_source_preflight(root: Path, task: dict[str, Any]) -> dict[str, Any]:
    """Return the shared, read-only source readiness used before website export.

    A research run may contain downloaded paragraphs while its authoritative
    quality report has rejected every source.  Treat an explicit zero verified
    score as a blocker, and otherwise require at least one approved URL on the
    immutable writer task.  This keeps Menu X from producing a package that
    Menu W or the publish gate can only reject later.
    """
    slug = _text(task.get("article_slug"))
    resolution = resolve_research_artifacts(
        root,
        task_id=_text(task.get("task_id")),
        slug=slug,
        batch_date=_text(task.get("batch_date")),
    )
    quality_path = root / "data" / "research" / slug / "research_quality.json"
    score = resolution.source_quality_score
    approved_urls = {
        _text(url)
        for url in [task.get("primary_source_url"), *list(task.get("supporting_source_urls") or [])]
        if _http_url(url)
    }
    research_root = root / "data" / "research" / slug
    for name in ("source_inventory.json", "SOURCE_EXCERPTS.json", "package.json"):
        payload = _read_json(research_root / name, {})
        rows: list[Any] = []
        if isinstance(payload, dict):
            for key in ("sources", "verified_sources", "trusted_sources", "source_inventory"):
                value = payload.get(key)
                if isinstance(value, list):
                    rows.extend(value)
        elif isinstance(payload, list):
            rows.extend(payload)
        for row in rows:
            if not isinstance(row, dict):
                continue
            status = _text(
                row.get("verification_status")
                or row.get("source_status")
                or row.get("status")
                or row.get("retrieval_status")
            ).casefold()
            url = _text(row.get("canonical_url") or row.get("source_url") or row.get("url") or row.get("final_url"))
            if status in {"verified", "approved", "cache_hit", "retrieved", "not_modified_cache", "stale_cache_fallback"} and _http_url(url):
                approved_urls.add(url)
    blockers: list[str] = [
        str(row)
        for row in resolution.failing_gates
        if str(row).startswith(
            (
                "VERIFIED_SOURCE_SCORE",
                "OFFICIAL_DOCS_SCORE",
                "PRICING_SOURCE_SCORE",
                "AFFILIATE_SOURCE_SCORE",
                "NO_VERIFIED_",
            )
        )
    ]
    blockers = [
        (
            f"Research quality reports zero usable verified sources ({reason})."
            if reason.startswith("VERIFIED_SOURCE_SCORE 0 ")
            else reason
        )
        for reason in blockers
    ]
    # An explicit zero remains authoritative. Recovery must rebuild this score
    # from genuinely verified local artifacts before export can proceed.
    if not approved_urls:
        blockers.append("No approved source URL exists on the external-writer task.")
    return {
        "ready": not blockers,
        "approved_source_urls": sorted(approved_urls),
        "verified_source_score": score,
        "canonical_eligibility": resolution.draft_exportable,
        "quality_report": _relative(root, quality_path),
        "blockers": blockers,
    }


class _CachedOnlySourceRetriever(SourceRetriever):
    """Recovery retriever that never performs a network request."""

    def retrieve(self, source: dict[str, Any], *, refresh: bool = False, reuse_cache: bool = True) -> dict[str, Any]:
        url = _text(source.get("canonical_url") or source.get("source_url") or source.get("url"))
        cache_path = self.cache_dir / f"{self.cache_key(url)}.json"
        cached = _read_json(cache_path, {})
        if self._cache_matches(cached, url):
            return {**cached, "retrieval_status": "cache_hit", "cache_path": str(cache_path)}
        return self._failure(url, "local_cache_miss", "No verified local source-content cache exists; operator source review is required.")
