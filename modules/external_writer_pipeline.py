from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sqlite3
import tempfile
import zipfile
from datetime import UTC, datetime
from html import unescape as _html_unescape
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlparse

from modules.external_writer_return_validator import (
    PublicOutputValidationError,
    assert_public_output_files,
    assert_website_advanced_html,
    public_output_validation_contract,
)
from modules.external_writer_source_preflight import (
    _CachedOnlySourceRetriever,
    _website_source_preflight,
)
from modules.external_writer_return_discovery import (
    ExternalWriterReturnDiscovery,
    ImportCandidate,
)
from modules.external_writer_package_materialization import ExternalWriterPackageMaterializer
from modules.research_artifacts import resolve_research_artifacts
from modules.affiliate_opportunity_discovery import build_affiliate_opportunity_brief
from modules.research_enrichment import ResearchEnrichmentPipeline, SourceRetriever
from modules.research_readiness import revision_tasks_from_validation
from modules.revision_binding import approval_binding_status, binding_for_file
from modules.official_source_registry import OfficialSourceRegistry
from modules.verified_source_acquisition import VerifiedSourceAcquisition
from modules.operations_intelligence.editorial_memory import EditorialMemoryStore
from modules.operations_intelligence.feature_flags import feature_enabled
from modules.social.content_quality import (
    SOCIAL_PLATFORM_WRITING_GUIDANCE,
    cross_platform_similarity,
    infer_story_audience,
    official_source_name,
    validate_social_value,
)
from modules.social.utils import configured_social_draft_platforms, configured_social_platform_playbooks
from modules.social.platform_native import (
    COMPONENT_ROLES,
    PlatformNativeSocialEngine,
    X_MAX_CHARACTERS,
    X_THREAD_ENABLED,
    validate_x_draft,
)
from modules.verified_writer_package import (
    CONTRACT_SCHEMA,
    build_verified_package,
    validate_verified_package,
)


QUEUE_SCHEMA = "universal_external_writer_task_v1"
PACKAGE_SCHEMA = "universal_external_writer_package_v1"
RETURN_SCHEMA = "universal_external_writer_return_v1"
TASK_TYPES = {
    "WEBSITE_FOUNDATION",
    "WEBSITE_ADVANCED",
    "WEBSITE_CUSTOM",
    "WEBSITE_UPDATE",
    "SOCIAL_WEBSITE_DISTRIBUTION",
    "SOCIAL_HOT_NEWS",
}
EXPORTABLE_RESEARCH_SUFFIXES = {
    ".csv",
    ".json",
    ".md",
    ".txt",
}
QUEUE_STATUSES = {
    "PENDING",
    "EXPORTED",
    "WRITING",
    "RETURNED",
    "VALIDATED",
    "IMPORTED",
    "NEEDS_REVIEW",
    "REVISION_REQUESTED",
    "APPROVED",
    "READY_FOR_PUBLISH",
    "PUBLISHED",
    "REJECTED",
    "FAILED_IMPORT",
}
SOCIAL_PLATFORMS = tuple(configured_social_draft_platforms())
SOCIAL_PLATFORM_PLAYBOOKS = configured_social_platform_playbooks()
SOCIAL_VARIANTS = ("A.md", "B.md", "C.md")
SOCIAL_SERIES_SCHEMA = "social_editorial_series_v1"
PROTECTED_WEBSITE_STATES = {
    "drafted",
    "reviewed",
    "under_review",
    "needs_review",
    "needs_human_review",
    "ai_review_passed",
    "approved",
    "human_approved",
    "approved_for_publish",
    "ready_for_publish",
    "published",
    "published_local",
    "rejected",
    "revision_requested",
}
IMMUTABLE_WEBSITE_STATES = {
    "approved",
    "human_approved",
    "approved_for_publish",
    "ready_for_publish",
    "published",
    "published_local",
}
PROTECTED_SOCIAL_STATES = {
    "approved_for_copy",
    "pending_manual_publish",
    "published_manual",
    "rejected",
    "revision_requested",
    "not_recommended",
}
EXECUTABLE_SUFFIXES = {
    ".bat",
    ".cmd",
    ".com",
    ".dll",
    ".exe",
    ".jar",
    ".js",
    ".msi",
    ".ps1",
    ".py",
    ".scr",
    ".vbs",
}
SECRET_NAME_RE = re.compile(
    r"(^|[._-])(credential|credentials|secret|secrets|token|tokens|api[_-]?key|id_rsa|private[_-]?key)([._-]|$)",
    re.I,
)
VIETNAMESE_DIACRITIC_RE = re.compile(r"[ÀÁÂÃÈÉÊÌÍÒÓÔÕÙÚĂĐĨŨƠƯẠ-ỹ]")
MOJIBAKE_RE = re.compile(
    r"(?:"
    r"Ãƒ|Ã‚|Ã„|Ã¡Â|Ã†|"
    r"Ã[¡¢£¨©ª¬­²³´µ¹º]|"
    r"Ä[ƒ‘©]|Å©|Æ[¡°]|"
    r"áº|á»"
    r")"
)
UTF8_DAMAGE_RE = re.compile(
    r"(?:\ufffd|\?\?|"
    r"\b(?:C\?ng|T\?nh|B\?i|kh\?ng|ti\?ng|Vi\?t)\b)",
    re.I,
)
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
STANDARD_VOCABULARY_URLS = {
    "https://schema.org",
    "http://schema.org",
}


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return default


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _text(value: Any) -> str:
    return str(value or "").strip()


def _normalized_social_title(value: Any) -> str:
    """Normalize a public social title for deterministic duplicate checks."""
    return re.sub(r"[^a-z0-9]+", " ", _text(value).casefold()).strip()


def _clean_public_title(value: Any) -> str:
    text = _html_unescape(re.sub(r"<[^>]+>", " ", str(value or "")))
    return re.sub(r"\s+", " ", text).strip()


def _normalized_website_title(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", _clean_public_title(value).casefold()).strip()


def _html_public_title(html: str, tag: str) -> str:
    match = re.search(rf"(?is)<{tag}\b[^>]*>(.*?)</{tag}>", html)
    return _clean_public_title(match.group(1)) if match else ""


def _markdown_public_title(markdown: str) -> str:
    match = re.search(r"(?m)^#\s+(.+?)\s*$", markdown)
    return _clean_public_title(match.group(1)) if match else ""


def _is_website_revision(task: dict[str, Any]) -> bool:
    return (
        _text(task.get("status")) == "REVISION_REQUESTED"
        or _text(task.get("exported_from_status")) == "REVISION_REQUESTED"
        or _text(task.get("task_type")) == "WEBSITE_UPDATE"
        or bool(task.get("refresh_existing_article"))
    )


def _http_url(value: Any) -> bool:
    parsed = urlparse(_text(value))
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _safe_task_id(task_type: str, batch_date: str, slug: str) -> str:
    digest = hashlib.sha256(f"{task_type}|{batch_date}|{slug}".encode("utf-8")).hexdigest()[:16]
    return f"{task_type.lower()}-{batch_date}-{digest}"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _relative(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path)


def _research_source_count(artifact: Any) -> int:
    payload = _read_json(artifact.source_excerpts_file, {})
    if isinstance(payload, dict):
        rows = payload.get("sources") or payload.get("verified_sources") or []
    else:
        rows = payload if isinstance(payload, list) else []
    return sum(1 for row in rows if isinstance(row, dict))


class _HTMLContractParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title = 0
        self.h1 = 0
        self.canonical = 0
        self.charset = 0
        self.html = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key.lower(): (value or "") for key, value in attrs}
        if tag.lower() == "html":
            self.html += 1
        elif tag.lower() == "title":
            self.title += 1
        elif tag.lower() == "h1":
            self.h1 += 1
        elif tag.lower() == "link" and values.get("rel", "").lower() == "canonical":
            self.canonical += 1
        elif tag.lower() == "meta" and values.get("charset", "").lower() == "utf-8":
            self.charset += 1


class UniversalWriteQueue:
    """Compatibility queue layered over the existing website and social stores."""

    def __init__(self, *, root: Path) -> None:
        self.root = root
        self.data_dir = root / "data"
        self.queue_dir = self.data_dir / "write_queue"

    def list_tasks(
        self,
        *,
        batch_date: str | None = None,
        task_type: str | None = None,
        statuses: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for path in sorted(self.queue_dir.glob("*.json")):
            if path.name == "index.json":
                continue
            row = _read_json(path, {})
            if not isinstance(row, dict) or row.get("schema_version") != QUEUE_SCHEMA:
                continue
            if batch_date and row.get("batch_date") != batch_date:
                continue
            if task_type and row.get("task_type") != task_type:
                continue
            if statuses and row.get("status") not in statuses:
                continue
            rows.append(row)
        return rows

    def get(self, task_id: str) -> dict[str, Any] | None:
        row = _read_json(self.queue_dir / f"{task_id}.json", None)
        return row if isinstance(row, dict) else None

    def save(self, task: dict[str, Any]) -> dict[str, Any]:
        task_id = _text(task.get("task_id"))
        if not task_id:
            raise ValueError("task_id is required")
        if task.get("task_type") not in TASK_TYPES:
            raise ValueError(f"Unsupported task_type: {task.get('task_type')}")
        if task.get("status") not in QUEUE_STATUSES:
            raise ValueError(f"Unsupported queue status: {task.get('status')}")
        task["schema_version"] = QUEUE_SCHEMA
        task["updated_at"] = _now()
        _write_json(self.queue_dir / f"{task_id}.json", task)
        self._write_index()
        return task

    def transition(self, task_id: str, status: str, **extra: Any) -> dict[str, Any]:
        if status not in QUEUE_STATUSES:
            raise ValueError(f"Unsupported queue status: {status}")
        task = self.get(task_id)
        if task is None:
            raise ValueError(f"Unknown task_id: {task_id}")
        task["status"] = status
        task.update(extra)
        return self.save(task)

    def request_website_revision(self, task_id: str, *, reason: str) -> dict[str, Any]:
        task = self.get(task_id)
        if task is None:
            raise ValueError(f"Unknown task_id: {task_id}")
        if not _text(task.get("task_type")).startswith("WEBSITE_"):
            raise ValueError("Website revision can only be requested for a website task.")
        invalidated_approval = self._invalidated_unpublished_approval(task)
        if (
            _text(task.get("status"))
            not in {"NEEDS_REVIEW", "REJECTED", "FAILED_IMPORT"}
            and not invalidated_approval
        ):
            raise ValueError(
                "Website revision requires NEEDS_REVIEW, REJECTED, or FAILED_IMPORT status."
            )
        immutable = self._website_states(task) & IMMUTABLE_WEBSITE_STATES
        if immutable and not invalidated_approval:
            raise ValueError(
                f"Refusing revision for approved/ready/published website state: {sorted(immutable)}"
            )
        revision_payload = _read_json(
            self.data_dir
            / "production_article_drafts"
            / _text(task.get("article_slug"))
            / "revision_tasks.json",
            {},
        )
        revision_tasks = (
            list(revision_payload.get("tasks") or [])
            if isinstance(revision_payload, dict)
            else []
        )
        affected_sections = list(
            dict.fromkeys(
                _text(row.get("section"))
                for row in revision_tasks
                if isinstance(row, dict) and _text(row.get("section"))
            )
        )
        return self.transition(
            task_id,
            "REVISION_REQUESTED",
            revision=int(task.get("revision") or 1) + 1,
            revision_reason=_text(reason) or "Editorial rewrite requested.",
            revision_requested_at=_now(),
            revision_tasks=revision_tasks,
            affected_sections=affected_sections,
            revision_scope=(
                "affected_sections_only"
                if affected_sections
                else "editorial_reason_only"
            ),
            invalidated_approval_recovery=invalidated_approval,
        )

    def _invalidated_unpublished_approval(self, task: dict[str, Any]) -> bool:
        """Allow a new revision only when approved bytes changed before publish.

        A revision-bound approval whose current draft hash no longer matches is
        not valid publish authorization.  Recovery may supersede it, but must
        never reopen a locally published or live article.
        """
        slug = _text(task.get("article_slug"))
        draft = self.data_dir / "production_article_drafts" / slug / "index.html"
        if not draft.is_file():
            return False
        states = self._website_states(task)
        if states & {"published", "published_local"}:
            return False
        approval = next(
            (
                row
                for row in _read_json(self.data_dir / "human_approval_queue.json", [])
                if isinstance(row, dict) and _text(row.get("slug")) == slug
            ),
            {},
        )
        binding = binding_for_file(draft)
        status = approval_binding_status(
            approval,
            current_content_hash=binding["content_hash"],
            current_revision_id=binding["revision_id"],
        )
        return status in {"CONTENT_HASH_MISMATCH", "REVISION_ID_MISMATCH"}

    def _website_states(self, task: dict[str, Any]) -> set[str]:
        slug = _text(task.get("article_slug"))
        states = {_text(task.get("status")).lower()}
        batch = _read_json(
            self.data_dir / "editorial_queue" / _text(task.get("batch_date")) / "topics.json",
            {},
        )
        for row in list(batch.get("topics") or []) if isinstance(batch, dict) else []:
            if not isinstance(row, dict) or _text(row.get("slug")) != slug:
                continue
            states.update(
                {
                    _text(row.get("status")).lower(),
                    _text(row.get("batch_state")).lower(),
                    _text(row.get("human_approval_status")).lower(),
                    _text(row.get("publish_gate_status")).lower(),
                }
            )
        for filename in (
            "content_review_queue.json",
            "human_approval_queue.json",
            "publish_queue.json",
        ):
            rows = _read_json(self.data_dir / filename, [])
            for row in rows if isinstance(rows, list) else []:
                if not isinstance(row, dict) or _text(row.get("slug")) != slug:
                    continue
                states.update(
                    {
                        _text(row.get("status")).lower(),
                        _text(row.get("normalized_status")).lower(),
                        _text(row.get("editorial_status")).lower(),
                    }
                )
        return {state for state in states if state}

    def sync_website(self, *, batch_date: str = "latest") -> list[dict[str, Any]]:
        resolved = self._resolve_website_date(batch_date)
        queue_path = self.data_dir / "editorial_queue" / resolved / "topics.json"
        payload = _read_json(queue_path, {})
        if not isinstance(payload, dict):
            raise RuntimeError(f"Invalid website queue: {queue_path}")
        mode = _text(payload.get("mode")).lower()
        task_type = {
            "advanced": "WEBSITE_ADVANCED",
            "custom": "WEBSITE_CUSTOM",
            "update": "WEBSITE_UPDATE",
        }.get(mode, "WEBSITE_FOUNDATION")
        tasks: list[dict[str, Any]] = []
        for item in list(payload.get("topics") or []):
            if not isinstance(item, dict):
                continue
            slug = _text(item.get("slug"))
            if not SLUG_RE.fullmatch(slug):
                continue
            row_task_type = (
                "WEBSITE_UPDATE"
                if item.get("refresh_existing_article") or item.get("opportunity_type") == "content_refresh"
                else task_type
            )
            item_state = _text(
                item.get("batch_state")
                or item.get("editorial_status")
                or item.get("status")
            ).lower()
            if item_state in PROTECTED_WEBSITE_STATES | {
                "research_blocked",
                "blocked_research",
                "blocked",
                "archived",
                "removed",
            }:
                continue
            if (
                (self.data_dir / "production_article_drafts" / slug / "index.html").exists()
                and row_task_type != "WEBSITE_UPDATE"
            ):
                continue
            resolution = resolve_research_artifacts(
                self.root,
                task_id=_safe_task_id(row_task_type, resolved, slug),
                slug=slug,
                batch_date=resolved,
            )
            research_path = resolution.package_file
            if not research_path.exists():
                continue
            existing = self.get(_safe_task_id(row_task_type, resolved, slug))
            if existing and existing.get("status") in {
                "IMPORTED",
                "NEEDS_REVIEW",
                "APPROVED",
                "READY_FOR_PUBLISH",
                "PUBLISHED",
                "REJECTED",
            }:
                tasks.append(existing)
                continue
            sources = self._website_source_urls(item, research_path)
            series = self._series_contract(item, resolved)
            prior_website_titles = self._prior_website_titles(exclude_slug=slug)
            task = {
                "schema_version": QUEUE_SCHEMA,
                "task_id": _safe_task_id(row_task_type, resolved, slug),
                "task_type": row_task_type,
                "workflow_lane": _text(item.get("content_lane") or row_task_type),
                "batch_date": resolved,
                "week_start": _text(payload.get("week_start") or item.get("week_start")),
                "root_topic_id": _text(item.get("root_topic_id")),
                "series_id": _text(item.get("root_topic_id")),
                "article_slug": slug,
                "title": _text(item.get("title") or item.get("keyword") or item.get("topic")),
                "normalized_title": _text(item.get("keyword") or item.get("title")).lower(),
                "primary_source_url": sources[0] if sources else "",
                "supporting_source_urls": sources[1:],
                "source_files": [],
                "research_files": [_relative(self.root, research_path)],
                "research_artifact_dir": _relative(self.root, resolution.canonical_dir),
                "research_artifact_status": resolution.status,
                "research_level": resolution.research_level,
                "draft_exportable": resolution.draft_exportable,
                "comparison_status": resolution.comparison_status,
                "outstanding_research_tasks": resolution.outstanding_research_tasks,
                "known_weak_sections": list(resolution.weak_sections),
                "estimated_publish_readiness": resolution.estimated_publish_readiness,
                "research_paragraph_count": resolution.paragraph_count,
                "research_claim_count": resolution.claim_count,
                "research_coverage_score": resolution.coverage_score,
                "target_output_type": "website",
                "target_output_paths": [
                    f"website/{slug}/article.html",
                    f"website/{slug}/article.md",
                    f"website/{slug}/metadata.json",
                    f"website/{slug}/validation_report.json",
                ],
                "article_type": _text(item.get("content_type") or ("content_refresh" if row_task_type == "WEBSITE_UPDATE" else mode) or "review"),
                "content_goal": _text(series.get("decision_objective") or item.get("suggested_article_angle")),
                "reader_intent": _text(series.get("reader_question")),
                "reader_question": _text(item.get("reader_question") or series.get("reader_question")),
                "search_intent": _text(item.get("search_intent")),
                "daily_angle": _text(item.get("daily_angle")),
                "sequence_number": item.get("sequence_number"),
                "unique_thesis": _text(item.get("unique_thesis")),
                "required_evidence": list(item.get("required_evidence") or []),
                "prohibited_overlap": list(item.get("prohibited_overlap") or []),
                "same_root_article_history": list(item.get("weekly_article_history") or []),
                "prior_website_titles": prior_website_titles,
                "audience": _text((item.get("content_strategy") or {}).get("audience") or "Small business operators"),
                "language": "en",
                "platform_targets": [],
                "language_targets": ["en"],
                "required_sections": list(series.get("unique_sections") or []),
                "required_tables": [series.get("table_purpose")] if series.get("table_purpose") else [],
                "required_faq": list(series.get("faq_set") or []),
                "required_cta": _text(series.get("cta_intent") or "Continue the editorial series"),
                "internal_link_requirements": list(item.get("suggested_internal_links") or []),
                "next_article_bridge": series.get("next_scheduled_article") or {},
                "tone": "independent, evidence-led, practical",
                "voice": "Smile AI Review Hub editorial voice",
                "style_contract": "AI_ONBOARDING.md and writing DNA files included in export",
                "source_rules": "Use only supplied source URLs and research. Never invent facts, prices, links, or experience.",
                "claim_safety_rules": "Omit or clearly qualify unsupported claims; entity/source mismatch is forbidden.",
                "forbidden_actions": self._forbidden_actions(),
                "validation_commands": [
                    "website HTML contract",
                    "UTF-8",
                    "source URL allowlist",
                    "human approval remains pending",
                ],
                "status": "PENDING",
                "created_at": existing.get("created_at") if existing else _now(),
                "updated_at": _now(),
                "writer": {},
                "revision": int((existing or {}).get("revision") or 1),
                "legacy_queue_file": _relative(self.root, queue_path),
                "legacy_task_files": self._legacy_task_files(resolved),
                "source_readiness": item.get("source_readiness") or {},
                "fallback_level": int(item.get("fallback_level") or 1),
                "opportunity_type": _text(item.get("opportunity_type") or "new_opportunity"),
                "refresh_existing_article": row_task_type == "WEBSITE_UPDATE",
                "existing_slug": _text(item.get("existing_slug") or (slug if row_task_type == "WEBSITE_UPDATE" else "")),
                "preserve_slug": bool(item.get("preserve_slug") or row_task_type == "WEBSITE_UPDATE"),
                "create_new_url": bool(item.get("create_new_url", row_task_type != "WEBSITE_UPDATE")),
                "refresh_reason": list(item.get("refresh_reason") or []),
                "refresh_scope": list(item.get("refresh_scope") or []),
                "refresh_thesis": _text(item.get("refresh_thesis")),
                "update_scope": _text(item.get("update_scope")),
                "existing_article_reference": _text(item.get("existing_article_reference") or f"data/production_article_drafts/{slug}"),
            }
            tasks.append(self.save(task))
        return tasks

    def is_exportable(self, task: dict[str, Any]) -> bool:
        status = _text(task.get("status"))
        if status not in {"PENDING", "EXPORTED", "REVISION_REQUESTED", "FAILED_IMPORT"}:
            return False
        slug = _text(task.get("article_slug"))
        if task.get("task_type", "").startswith("WEBSITE_"):
            revision_requested = _is_website_revision(task)
            if (
                (self.data_dir / "production_article_drafts" / slug / "index.html").exists()
                and not revision_requested
            ):
                return False
            states = self._website_states(task)
            protected = (
                set()
                if _text(task.get("task_type")) == "WEBSITE_UPDATE"
                else
                states & ({"published", "published_local"} if self._invalidated_unpublished_approval(task) else IMMUTABLE_WEBSITE_STATES)
                if revision_requested
                else states & PROTECTED_WEBSITE_STATES
            )
            if protected:
                return False
            return True
        social_root = self.data_dir / "social_drafts" / _text(task.get("batch_date")) / slug
        for platform in SOCIAL_PLATFORMS:
            if (social_root / platform / "A.md").exists():
                return False
            metadata = _read_json(social_root / platform / "metadata.json", {})
            if _text(metadata.get("status")).lower() in PROTECTED_SOCIAL_STATES:
                return False
        return True

    def _prior_social_series(self, *, slug: str, before_batch: str) -> dict[str, Any]:
        titles: set[str] = set()
        batch_dates: set[str] = set()
        if not self.data_dir.joinpath("social_drafts").exists():
            return {"batch_dates": [], "titles": []}
        try:
            before = datetime.fromisoformat(before_batch)
            cycle_start = before.replace(hour=0, minute=0, second=0, microsecond=0)
            cycle_start = cycle_start.fromordinal(cycle_start.toordinal() - cycle_start.weekday())
            cycle_start_text = cycle_start.date().isoformat()
        except ValueError:
            cycle_start_text = before_batch
        for batch_dir in sorted((self.data_dir / "social_drafts").glob("*")):
            if (
                not batch_dir.is_dir()
                or batch_dir.name >= before_batch
                or batch_dir.name < cycle_start_text
            ):
                continue
            article_dir = batch_dir / slug
            if not article_dir.is_dir():
                continue
            found = False
            for platform in SOCIAL_PLATFORMS:
                metadata = _read_json(article_dir / platform / "metadata.json", {})
                if not isinstance(metadata, dict):
                    continue
                candidates = [_text(metadata.get("title"))]
                variant_titles = metadata.get("variant_titles")
                if isinstance(variant_titles, dict):
                    candidates.extend(_text(value) for value in variant_titles.values())
                for title in candidates:
                    if title:
                        titles.add(title)
                        found = True
            if found:
                batch_dates.add(batch_dir.name)
        return {"batch_dates": sorted(batch_dates), "titles": sorted(titles)}

    def _prior_website_titles(self, *, exclude_slug: str) -> list[str]:
        titles: set[str] = set()
        root = self.data_dir / "production_article_drafts"
        if not root.exists():
            return []
        for metadata_path in root.glob("*/metadata.json"):
            if metadata_path.parent.name == exclude_slug:
                continue
            metadata = _read_json(metadata_path, {})
            title = _text(metadata.get("title")) if isinstance(metadata, dict) else ""
            if title:
                titles.add(title)
        return sorted(titles)

    def sync_social(self, *, batch_date: str = "latest") -> list[dict[str, Any]]:
        resolved = self._resolve_social_date(batch_date)
        manifest_path = self.data_dir / "social_drafts" / resolved / "manifest.json"
        manifest = _read_json(manifest_path, {})
        if not isinstance(manifest, dict):
            raise RuntimeError(f"Invalid social manifest: {manifest_path}")
        tasks: list[dict[str, Any]] = []
        for item in list(manifest.get("items") or []):
            if not isinstance(item, dict):
                continue
            slug = _text(item.get("slug"))
            source_package = Path(_text(item.get("source_package")))
            if not source_package.is_absolute():
                source_package = self.root / source_package
            if not SLUG_RE.fullmatch(slug) or not source_package.exists():
                continue
            content_lane = _text(item.get("content_lane"))
            task_type = (
                "SOCIAL_HOT_NEWS"
                if content_lane in {"SOCIAL_HOT_DRAFT", "SOCIAL_HOT_UNCONFIRMED"}
                or slug.startswith("hot-news-")
                else "SOCIAL_WEBSITE_DISTRIBUTION"
            )
            package = _read_json(source_package, {})
            provenance = package.get("provenance") if isinstance(package, dict) and isinstance(package.get("provenance"), dict) else {}
            package_evidence = package.get("evidence") if isinstance(package, dict) and isinstance(package.get("evidence"), dict) else {}
            allowed_social_claim_ids = [
                _text(row.get("claim_id") or row.get("id"))
                for row in list(package_evidence.get("fact_ledger") or [])
                if isinstance(row, dict) and _text(row.get("claim_id") or row.get("id"))
            ]
            editorial = item.get("editorial_selection") if isinstance(item.get("editorial_selection"), dict) else {}
            article = package.get("article") if isinstance(package, dict) and isinstance(package.get("article"), dict) else {}
            source_urls = list(editorial.get("source_urls") or package.get("source_urls") or [])
            website_url = _text(item.get("url") or article.get("url"))
            if website_url:
                source_urls.insert(0, website_url)
            source_urls = list(dict.fromkeys(_text(url) for url in source_urls if _http_url(url)))
            source_url = source_urls[0] if source_urls else ""
            source_name = official_source_name(
                source_url,
                _text(editorial.get("publisher") or editorial.get("source_name") or package.get("source_name")),
            )
            story_title = _text(item.get("title") or article.get("title") or slug)
            story_summary = _text(editorial.get("summary") or package.get("summary") or article.get("description"))
            inferred_audience = infer_story_audience(story_title, story_summary)
            followup = item.get("scheduled_followup") if isinstance(item.get("scheduled_followup"), dict) else {}
            followup_date = _text(followup.get("scheduled_date"))
            followup_task_id = _text(followup.get("task_id"))
            followup_record = self.get(followup_task_id) if followup_task_id else None
            scheduled_followup_exists = bool(
                followup_record
                and DATE_RE.fullmatch(followup_date)
                and followup_date > resolved
                and _text(followup_record.get("parent_task_id")) == _safe_task_id(task_type, resolved, slug)
            )
            task_id = _safe_task_id(task_type, resolved, slug)
            existing = self.get(task_id)
            prior_series = self._prior_social_series(slug=slug, before_batch=resolved)
            series_day = len(prior_series["batch_dates"]) + 1
            task = {
                "schema_version": QUEUE_SCHEMA,
                "task_id": task_id,
                "task_type": task_type,
                "workflow_lane": content_lane or task_type,
                "batch_date": resolved,
                "week_start": "",
                "root_topic_id": _text(provenance.get("root_topic_id")),
                "series_id": _text(provenance.get("root_topic_id")),
                "article_slug": slug,
                "content_origin": _text(
                    package.get("content_origin")
                    or provenance.get("content_origin")
                    or ("HOT_NEWS" if task_type == "SOCIAL_HOT_NEWS" else "WEBSITE_ROOT_BASED")
                ),
                "social_mode": _text(
                    package.get("social_mode")
                    or provenance.get("social_mode")
                    or ("STANDALONE_SOCIAL_RESEARCH" if task_type == "SOCIAL_HOT_NEWS" else "SOURCE_BASED_SOCIAL")
                ),
                "root_title": _text(provenance.get("root_title")),
                "source_article_slug": _text(provenance.get("source_article_slug") or slug),
                "source_revision_id": _text(provenance.get("source_revision_id")),
                "source_content_hash": _text(provenance.get("source_content_hash")),
                "source_evidence_reference": _text(provenance.get("source_evidence_reference")),
                "evidence_inheritance": _text(provenance.get("evidence_inheritance")),
                "allowed_social_claim_ids": allowed_social_claim_ids,
                "claim_verification_contract": "NEW_CLAIMS_REQUIRE_SUPPLIED_EVIDENCE",
                "social_angle": _text(provenance.get("social_angle") or "source_article_adaptation"),
                "content_relationship": _text(provenance.get("content_relationship") or "website_root_social_adaptation"),
                "title": story_title,
                "normalized_title": _text(item.get("title") or article.get("title")).lower(),
                "primary_source_url": source_url,
                "supporting_source_urls": source_urls[1:],
                "source_files": [_relative(self.root, source_package)],
                "research_files": [],
                "target_output_type": "social",
                "target_output_paths": [
                    f"social/{slug}/metadata.json",
                    *[
                        f"social/{slug}/{platform}/{variant}.md"
                        for platform in SOCIAL_PLATFORMS
                        for variant in ("A", "B", "C")
                    ],
                ],
                "article_type": "social_hot_news" if task_type == "SOCIAL_HOT_NEWS" else "social_distribution",
                "content_goal": "Create distinct platform-native drafts for human review.",
                "reader_intent": "",
                "search_intent": "",
                "audience": inferred_audience,
                "language": "multi",
                "platform_targets": list(SOCIAL_PLATFORMS),
                "language_targets": ["en", "vi"],
                "required_sections": [],
                "required_tables": [],
                "required_faq": [],
                "required_cta": (
                    "CTA is optional. Prefer a story-specific implication, decision question, observation, or source ending."
                    if task_type == "SOCIAL_HOT_NEWS"
                    else "Optional and platform-specific. For X, omit the link when one useful insight needs the full 280-character budget."
                ),
                "internal_link_requirements": [],
                "next_article_bridge": {
                    "required": scheduled_followup_exists,
                    "series_schema": SOCIAL_SERIES_SCHEMA,
                    "pillar_title": _text(item.get("title") or article.get("title") or slug),
                    "day_number": series_day,
                    "instruction": (
                        "A dated future CTA is allowed because the linked follow-up task exists."
                        if scheduled_followup_exists
                        else "Do not promise tomorrow or a future post. A CTA is optional; end naturally for the story."
                    ),
                },
                "prior_social_titles": prior_series["titles"],
                "prior_social_batch_dates": prior_series["batch_dates"],
                "tone": "platform-native, useful, concise, evidence-led",
                "voice": "Smile AI Review Hub editorial voice",
                "style_contract": (
                    "Distinct copy and distinct title per platform and A/B/C variant; include what happened, "
                    "why it matters, a practical takeaway, and visible source attribution. A CTA is optional."
                ),
                "source_rules": (
                    "Use only real source URLs. Never create a Smile AI Review Hub URL."
                    if task_type == "SOCIAL_HOT_NEWS"
                    else "Use the exact supplied Live 200 website URL."
                ),
                "claim_safety_rules": "Preserve official_confirmed, uncertainty, known facts, and safe wording.",
                "forbidden_actions": self._forbidden_actions(),
                "validation_commands": ["UTF-8", "platform limits", "source URL allowlist", "no duplicate URL"],
                "status": (
                    existing.get("status")
                    if existing and existing.get("status") in QUEUE_STATUSES
                    else "PENDING"
                ),
                "created_at": existing.get("created_at") if existing else _now(),
                "updated_at": _now(),
                "writer": (existing or {}).get("writer") or {},
                "revision": int((existing or {}).get("revision") or 1),
                "legacy_queue_file": _relative(self.root, manifest_path),
                "legacy_task_files": self._legacy_task_files(resolved),
                "website_url": website_url,
                "official_confirmed": bool(editorial.get("official_confirmed")),
                "what_is_known": _text(editorial.get("what_is_known") or package.get("what_is_known")),
                "what_is_not_confirmed": _text(editorial.get("what_is_not_confirmed") or package.get("what_is_not_confirmed")),
                "safe_wording_guidance": _text(editorial.get("safe_wording_guidance") or package.get("safe_wording_guidance")),
                "official_source_name": source_name,
                "official_source_url": source_url,
                "official_source_type": _text(editorial.get("source_type") or package.get("source_type") or "official_source"),
                "source_render_required": bool(source_url),
                "x_source_link_optional": task_type == "SOCIAL_WEBSITE_DISTRIBUTION",
                "x_max_characters": X_MAX_CHARACTERS,
                "x_thread_enabled": X_THREAD_ENABLED,
                "variant_strategies": {
                    "A.md": "ACTIONABLE",
                    "B.md": "INSIGHT_POINT_OF_VIEW",
                    "C.md": "PROBLEM_SOLUTION_CASE",
                },
                "platform_playbooks": {
                    platform: dict(SOCIAL_PLATFORM_PLAYBOOKS.get(platform) or {})
                    for platform in SOCIAL_PLATFORMS
                },
                "scheduled_followup_exists": scheduled_followup_exists,
                "scheduled_followup_date": followup_date if scheduled_followup_exists else "",
                "scheduled_followup_task_id": followup_task_id if scheduled_followup_exists else "",
                "social_value_requirements": {
                    # Both social lanes use the current value-first contract.  Leaving
                    # website distribution on the legacy path incorrectly requires a
                    # "tomorrow" teaser even when there is no scheduled follow-up.
                    "enabled": True,
                    "what_happened": True,
                    "why_it_matters": True,
                    "practical_takeaway": True,
                    "official_source": bool(source_url),
                    "no_unsupported_future_promise": True,
                    "no_generic_compliance_only": True,
                    "no_generic_cta": True,
                    "no_fake_urgency": True,
                    "no_stale_relative_date": True,
                    "verified_pricing": bool(editorial.get("pricing_verified") or package.get("pricing_verified")),
                    "affiliate_claims_supported": bool(
                        editorial.get("affiliate_claims_supported") or package.get("affiliate_claims_supported")
                    ),
                },
                "platform_writing_guidance": {
                    platform: SOCIAL_PLATFORM_WRITING_GUIDANCE[platform]
                    for platform in SOCIAL_PLATFORMS
                },
                "pinterest_visual_facts": [
                    f"Official update from {source_name}",
                    "Check scope and applicability for your workflow",
                    "Use the official source as the canonical reference",
                ] if source_name else [],
            }
            tasks.append(self.save(task))
        return tasks

    def sync_all(self, *, batch_date: str = "latest") -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for sync in (self.sync_website, self.sync_social):
            try:
                rows.extend(sync(batch_date=batch_date))
            except (RuntimeError, FileNotFoundError):
                continue
        return rows

    def _write_index(self) -> None:
        rows = self.list_tasks()
        _write_json(
            self.queue_dir / "index.json",
            {
                "schema_version": QUEUE_SCHEMA,
                "updated_at": _now(),
                "task_count": len(rows),
                "tasks": [
                    {
                        key: row.get(key)
                        for key in ("task_id", "task_type", "batch_date", "article_slug", "status", "revision")
                    }
                    for row in rows
                ],
            },
        )

    def _resolve_website_date(self, requested: str) -> str:
        if requested != "latest":
            return requested
        root = self.data_dir / "editorial_queue"
        dates = [
            path.name
            for path in root.iterdir()
            if path.is_dir() and DATE_RE.fullmatch(path.name) and (path / "topics.json").exists()
        ] if root.exists() else []
        if not dates:
            raise RuntimeError("No website editorial queue is available. Run Menu 1, 2, or 3 first.")
        return sorted(dates)[-1]

    def _resolve_social_date(self, requested: str) -> str:
        if requested != "latest":
            return requested
        root = self.data_dir / "social_drafts"
        dates = [
            path.name
            for path in root.iterdir()
            if path.is_dir() and DATE_RE.fullmatch(path.name) and (path / "manifest.json").exists()
        ] if root.exists() else []
        if not dates:
            raise RuntimeError("No social editorial queue is available. Run Menu F or H first.")
        return sorted(dates)[-1]

    @staticmethod
    def _website_source_urls(item: dict[str, Any], research_path: Path) -> list[str]:
        package = _read_json(research_path, {})
        sources = package.get("sources") if isinstance(package, dict) else {}
        verified = sources.get("verified_sources") if isinstance(sources, dict) else []
        urls = list(item.get("source_urls") or [])
        for row in verified if isinstance(verified, list) else []:
            if isinstance(row, dict):
                urls.append(row.get("source_url") or row.get("url"))
        return list(dict.fromkeys(_text(url) for url in urls if _http_url(url)))

    @staticmethod
    def _series_contract(item: dict[str, Any], batch_date: str) -> dict[str, Any]:
        for row in list(item.get("series_plan") or []):
            if isinstance(row, dict) and row.get("scheduled_date") == batch_date:
                return row
        return {}

    def _legacy_task_files(self, batch_date: str) -> list[str]:
        candidates = [
            self.data_dir / "ai_tasks" / "CURRENT_AI_TASK.md",
            self.data_dir / "codex_tasks" / "CURRENT_TASK.md",
            self.data_dir / "ai_tasks" / batch_date,
            self.data_dir / "codex_tasks" / batch_date,
        ]
        return [_relative(self.root, path) for path in candidates if path.exists()]

    @staticmethod
    def _forbidden_actions() -> list[str]:
        return [
            "approve",
            "publish",
            "commit",
            "push",
            "deploy",
            "index",
            "call any API",
            "invent facts or URLs",
        ]


class UniversalExternalWriterExporter:
    def __init__(self, *, root: Path) -> None:
        self.root = root
        self.queue = UniversalWriteQueue(root=root)
        self.export_root = root / "exports" / "external_writer"

    def _package_materializer(self) -> ExternalWriterPackageMaterializer:
        return ExternalWriterPackageMaterializer(
            root=self.root,
            affiliate_brief_builder=build_affiliate_opportunity_brief,
        )

    def export(
        self,
        *,
        batch_date: str = "latest",
        task_type: str | None = None,
    ) -> dict[str, Any]:
        self.queue.sync_all(batch_date=batch_date)
        active_batches = self.active_batches()
        candidates = self.queue.list_tasks(
            task_type=task_type,
            statuses={"PENDING", "EXPORTED", "REVISION_REQUESTED", "FAILED_IMPORT"},
        )
        candidates = [row for row in candidates if self.queue.is_exportable(row)]
        if batch_date != "latest":
            candidates = [row for row in candidates if row.get("batch_date") == batch_date]
        if not candidates:
            if task_type in {None, "WEBSITE_ADVANCED"}:
                editorial_batch = self._advanced_editorial_preflight(batch_date)
                if editorial_batch and editorial_batch["held"]:
                    reasons = "\n".join(
                        f"- {row['article_slug']}: {row['reason']}"
                        for row in editorial_batch["tasks"]
                        if not row["eligible"]
                    )
                    raise RuntimeError(f"NO_ELIGIBLE_TASKS\n{reasons}")
            choices = ", ".join(
                f"{row['task_type']}@{row['batch_date']} ({row['task_count']})"
                for row in active_batches
            )
            suffix = f" Active batches: {choices}." if choices else ""
            raise RuntimeError("No pending external-writer tasks are available." + suffix)
        latest_date = max(_text(row.get("batch_date")) for row in candidates)
        candidates = [row for row in candidates if row.get("batch_date") == latest_date]
        groups: dict[str, list[dict[str, Any]]] = {}
        for row in candidates:
            groups.setdefault(_text(row.get("task_type")), []).append(row)
        if task_type:
            selected_type = task_type
        elif len(groups) == 1:
            selected_type = next(iter(groups))
        else:
            choices = ", ".join(
                f"{row['task_type']}@{row['batch_date']} ({row['task_count']})"
                for row in active_batches
            )
            raise RuntimeError(f"Multiple active task types are available: {choices}. Choose one explicitly.")
        tasks = sorted(groups.get(selected_type, []), key=lambda row: _text(row.get("article_slug")))
        if not tasks:
            raise RuntimeError(f"No pending tasks found for {selected_type}.")
        tasks, held_tasks = self._partition_research_ready(tasks, selected_type)
        recovery_report = self._empty_recovery_report()
        if not tasks and held_tasks and selected_type.startswith("WEBSITE_"):
            original_tasks = [self.queue.get(row["task_id"]) for row in held_tasks]
            recovery_tasks = [row for row in original_tasks if isinstance(row, dict)]
            recovery_report = self._recover_research_once(recovery_tasks, selected_type)
            tasks, held_tasks = self._partition_research_ready(recovery_tasks, selected_type)
        if not tasks:
            reasons = "\n".join(
                f"- {row['article_slug']}: {row['reason']}" for row in held_tasks
            )
            recovery_lines = "\n".join(
                f"{key}: {value}" for key, value in recovery_report.items()
                if key.isupper()
            )
            raise RuntimeError(f"NO_ELIGIBLE_TASKS\n{recovery_lines}\n{reasons}")
        package_id = self._package_id(latest_date, selected_type, tasks)
        stage_parent = self.export_root / latest_date
        stage_parent.mkdir(parents=True, exist_ok=True)
        package_dir = stage_parent / f".{package_id}.building"
        if package_dir.exists():
            shutil.rmtree(package_dir)
        package_dir.mkdir(parents=True)
        try:
            self._build_package(
                package_dir,
                package_id,
                selected_type,
                latest_date,
                tasks,
                held_tasks=held_tasks,
            )
            verification = validate_verified_package(package_dir)
            if not verification.valid:
                raise RuntimeError(
                    "Verified package is incomplete: " + "; ".join(verification.errors)
                )
            zip_path = stage_parent / f"{selected_type.lower()}_{package_id}_verified_package.zip"
            temp_zip = stage_parent / f".{zip_path.name}.tmp"
            if temp_zip.exists():
                temp_zip.unlink()
            with zipfile.ZipFile(temp_zip, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for path in sorted(package_dir.rglob("*")):
                    if path.is_file():
                        archive.write(path, path.relative_to(package_dir).as_posix())
            os.replace(temp_zip, zip_path)
            legacy_zip = stage_parent / f"{selected_type.lower()}_{package_id}_ready_for_chatgpt.zip"
            shutil.copy2(zip_path, legacy_zip)
        finally:
            if package_dir.exists():
                shutil.rmtree(package_dir)
        for task in tasks:
            self.queue.transition(
                task["task_id"],
                "EXPORTED",
                exported_from_status=_text(task.get("status")),
                package_id=package_id,
                exported_zip=_relative(self.root, legacy_zip),
                verified_package_zip=_relative(self.root, zip_path),
                exported_at=_now(),
            )
        for held in held_tasks:
            task = self.queue.get(held["task_id"])
            if task is not None:
                task["research_hold"] = held
                self.queue.save(task)
        result = {
            "package_id": package_id,
            "package_type": selected_type,
            "batch_date": latest_date,
            "task_count": len(tasks),
            "exported_tasks": [row["task_id"] for row in tasks],
            "held_task_count": len(held_tasks),
            "held_tasks": held_tasks,
            "selection": {
                "task_type": selected_type,
                "batch_date": latest_date,
                "eligible": len(tasks),
                "held": len(held_tasks),
            },
            "article_count": len(tasks) if selected_type.startswith("WEBSITE_") else 0,
            "platform_count": len(SOCIAL_PLATFORMS) if selected_type.startswith("SOCIAL_") else 0,
            "language_count": 2 if selected_type.startswith("SOCIAL_") else 1,
            "zip_path": str(zip_path),
            "zip_size": zip_path.stat().st_size,
            "sha256": _sha256(zip_path),
            "validation": "PASS",
            "research_recovery": recovery_report,
        }
        return result

    @staticmethod
    def _empty_recovery_report() -> dict[str, Any]:
        return {
            "RECOVERY_ATTEMPTED": False,
            "RESEARCH_RECOVERY_ATTEMPTED": False,
            "SOURCES_BEFORE": 0,
            "SOURCES_AFTER": 0,
            "EVIDENCE_COVERAGE_BEFORE": 0.0,
            "EVIDENCE_COVERAGE_AFTER": 0.0,
            "TASKS_RECOVERED": 0,
            "TASKS_STILL_HELD": 0,
            "TASKS_HELD": 0,
            "SOURCES_FOUND": 0,
            "OFFICIAL_SOURCES_FOUND": 0,
            "SOURCE_FAMILIES": [],
            "VERIFIED_CLAIMS": 0,
            "ENTITY_COVERAGE": 0.0,
            "EVIDENCE_COVERAGE": 0.0,
            "RESEARCH_TASKS_REMAINING": 0,
            "FINAL_EXPORTABLE_COUNT": 0,
            "FINAL_HELD_COUNT": 0,
            "OPERATOR_ACTION_REQUIRED": [],
        }

    def _recover_research_once(self, tasks: list[dict[str, Any]], task_type: str) -> dict[str, Any]:
        report = self._empty_recovery_report()
        report["RECOVERY_ATTEMPTED"] = True
        report["RESEARCH_RECOVERY_ATTEMPTED"] = True
        config = _read_json(self.root / "config" / "editorial_system.json", {})
        retriever = _CachedOnlySourceRetriever(
            cache_dir=self.root / "data" / "research_cache" / "source_content",
            retries=0,
        )
        pipeline = ResearchEnrichmentPipeline(root=self.root, config=config, retriever=retriever)
        families: set[str] = set()
        actions: list[str] = []
        recovered = 0
        for task in tasks:
            before_artifact = resolve_research_artifacts(
                self.root,
                task_id=_text(task.get("task_id")),
                slug=_text(task.get("article_slug")),
                batch_date=_text(task.get("batch_date")),
            )
            report["SOURCES_BEFORE"] += _research_source_count(before_artifact)
            report["EVIDENCE_COVERAGE_BEFORE"] = max(
                report["EVIDENCE_COVERAGE_BEFORE"], float(before_artifact.coverage_score or 0)
            )
            sources = self._local_recovery_sources(task)
            report["SOURCES_FOUND"] += len(sources)
            report["OFFICIAL_SOURCES_FOUND"] += sum(
                1 for row in sources if _text(row.get("source_type")).casefold() not in {"competitor_article", "community"}
            )
            families.update(_text(row.get("source_type") or "official_website") for row in sources)
            cached_sources = [row for row in sources if self._source_is_cached(row)]
            if not cached_sources:
                actions.append(
                    f"{task.get('article_slug')}: add or verify at least one official source in Source Review, then rerun Menu X."
                )
                continue
            recovery_task = dict(task)
            recovery_task["primary_source_url"] = _text(cached_sources[0].get("source_url") or cached_sources[0].get("canonical_url"))
            recovery_task["supporting_source_urls"] = [
                _text(row.get("source_url") or row.get("canonical_url")) for row in cached_sources[1:]
            ]
            result = pipeline.enrich_slug(
                _text(task.get("article_slug")),
                task=recovery_task,
                refresh_sources=False,
                reuse_cache=True,
                dry_run=False,
            )
            artifact = resolve_research_artifacts(
                self.root,
                task_id=_text(task.get("task_id")),
                slug=_text(task.get("article_slug")),
                batch_date=_text(task.get("batch_date")),
            )
            report["SOURCES_AFTER"] += _research_source_count(artifact)
            report["EVIDENCE_COVERAGE_AFTER"] = max(
                report["EVIDENCE_COVERAGE_AFTER"], float(artifact.coverage_score or 0)
            )
            report["VERIFIED_CLAIMS"] += int(getattr(result, "publishable_claims", 0) or artifact.claim_count)
            report["ENTITY_COVERAGE"] = max(report["ENTITY_COVERAGE"], float(artifact.entity_coverage_score or 0))
            report["EVIDENCE_COVERAGE"] = max(report["EVIDENCE_COVERAGE"], float(artifact.coverage_score or 0))
            report["RESEARCH_TASKS_REMAINING"] += len(getattr(result, "research_tasks", []) or [])
            if bool(getattr(result, "draft_exportable", False)):
                # Keep the persisted queue state unchanged; the source fields on
                # this in-memory task are only packaged after every gate passes.
                task.update(
                    primary_source_url=recovery_task["primary_source_url"],
                    supporting_source_urls=recovery_task["supporting_source_urls"],
                )
                recovered += 1
            else:
                blockers = list(getattr(result, "blockers", []) or [])
                actions.append(
                    f"{task.get('article_slug')}: " + ("; ".join(blockers[:4]) or "complete the outstanding Source Review tasks")
                )
        ready, held = self._partition_research_ready(tasks, task_type)
        report.update(
            {
                "TASKS_RECOVERED": recovered,
                "TASKS_STILL_HELD": len(held),
                "TASKS_HELD": len(held),
                "SOURCE_FAMILIES": sorted(family for family in families if family),
                "FINAL_EXPORTABLE_COUNT": len(ready),
                "FINAL_HELD_COUNT": len(held),
                "OPERATOR_ACTION_REQUIRED": list(dict.fromkeys(actions)),
            }
        )
        return report

    def _source_is_cached(self, source: dict[str, Any]) -> bool:
        url = _text(source.get("source_url") or source.get("canonical_url") or source.get("url"))
        path = self.root / "data" / "research_cache" / "source_content" / f"{SourceRetriever.cache_key(url)}.json"
        payload = _read_json(path, {})
        return bool(isinstance(payload, dict) and _text(payload.get("content")) and _text(payload.get("url")) == url)

    def _local_recovery_sources(self, task: dict[str, Any]) -> list[dict[str, Any]]:
        """Discover approved sources from existing repository stores only."""
        slug = _text(task.get("article_slug"))
        research_root = self.root / "data" / "research" / slug
        rows: list[dict[str, Any]] = []
        for url in [task.get("primary_source_url"), *list(task.get("supporting_source_urls") or [])]:
            if _http_url(url):
                rows.append({"source_url": _text(url), "source_type": "task_approved", "verification_status": "approved"})
        for name in ("source_inventory.json", "SOURCE_EXCERPTS.json", "package.json"):
            payload = _read_json(research_root / name, {})
            values: list[Any] = []
            if isinstance(payload, dict):
                for key in ("sources", "verified_sources", "trusted_sources", "source_inventory"):
                    if isinstance(payload.get(key), list):
                        values.extend(payload[key])
            elif isinstance(payload, list):
                values.extend(payload)
            for row in values:
                if not isinstance(row, dict):
                    continue
                status = _text(row.get("verification_status") or row.get("source_status") or row.get("status") or row.get("retrieval_status")).casefold()
                if status in {"verified", "approved", "cache_hit", "retrieved", "not_modified_cache", "stale_cache_fallback"}:
                    rows.append(dict(row))
        raw_entities = task.get("entities") or []
        if isinstance(raw_entities, dict):
            raw_entities = list(raw_entities.values())
        elif isinstance(raw_entities, str):
            raw_entities = [raw_entities]
        entities: list[str] = []
        for value in (
            task.get("root_topic_id"), task.get("primary_keyword"), task.get("title"), slug,
            *list(raw_entities),
        ):
            if isinstance(value, dict):
                value = value.get("name") or value.get("canonical_name")
            if _text(value):
                entities.append(_text(value))
        registry = OfficialSourceRegistry(self.root / "data" / "official_source_registry.json")
        for entity in entities:
            rows.extend(registry.sources_for(entity))
        acquired = VerifiedSourceAcquisition(
            registry_json=self.root / "data" / "source_registry.json",
            registry_csv=self.root / "data" / "source_registry.csv",
        ).acquire(_text(task.get("primary_keyword") or slug), {"products": entities})
        rows.extend(acquired.get("verified_sources") or [])
        rows.extend(self._knowledge_graph_sources(entities))
        unique: dict[str, dict[str, Any]] = {}
        for row in rows:
            url = _text(row.get("canonical_url") or row.get("source_url") or row.get("url") or row.get("final_url"))
            if not _http_url(url):
                continue
            unique.setdefault(url.casefold().rstrip("/"), {**row, "source_url": url, "canonical_url": url})
        return list(unique.values())

    def _knowledge_graph_sources(self, entities: list[str]) -> list[dict[str, Any]]:
        db_path = self.root / "data" / "intelligence" / "knowledge_graph" / "knowledge_graph.sqlite3"
        if not db_path.is_file() or not entities:
            return []
        tokens = {token for value in entities for token in re.findall(r"[a-z0-9]+", value.casefold()) if len(token) > 3}
        if not tokens:
            return []
        try:
            with sqlite3.connect(db_path) as connection:
                rows = connection.execute(
                    "SELECT p.source_url, p.confidence, p.human_verified, e.canonical_name "
                    "FROM provenance p LEFT JOIN entities e ON p.subject_type='entity' AND p.subject_id=e.entity_id "
                    "WHERE p.source_url <> '' AND (p.human_verified=1 OR p.confidence>=0.8)"
                ).fetchall()
        except sqlite3.Error:
            return []
        return [
            {"source_url": url, "canonical_url": url, "source_type": "knowledge_graph_provenance", "verification_status": "verified"}
            for url, _confidence, _verified, name in rows
            if _http_url(url) and tokens & {token for token in re.findall(r"[a-z0-9]+", _text(name).casefold()) if len(token) > 3}
        ]

    def active_batches(self) -> list[dict[str, Any]]:
        """Return the newest active batch independently for each task type."""
        rows = self.queue.list_tasks(
            statuses={"PENDING", "EXPORTED", "REVISION_REQUESTED", "FAILED_IMPORT"}
        )
        grouped: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            grouped.setdefault(_text(row.get("task_type")), []).append(row)
        result: list[dict[str, Any]] = []
        for task_type, task_rows in sorted(grouped.items()):
            batch_date = max(_text(row.get("batch_date")) for row in task_rows)
            selected = [row for row in task_rows if _text(row.get("batch_date")) == batch_date]
            ready, held = self._partition_research_ready(selected, task_type)
            result.append(
                {
                    "task_type": task_type,
                    "batch_date": batch_date,
                    "task_count": len(selected),
                    "eligible": len(ready),
                    "held": len(held),
                    "tasks": self._preflight_task_rows(selected, ready, held),
                }
            )
        advanced = self._advanced_editorial_preflight("latest")
        if advanced and not any(
            row["task_type"] == "WEBSITE_ADVANCED"
            and row["batch_date"] == advanced["batch_date"]
            for row in result
        ):
            result.append(advanced)
        return result

    def _advanced_editorial_preflight(self, requested_date: str) -> dict[str, Any] | None:
        try:
            batch_date = self.queue._resolve_website_date(requested_date)
        except (RuntimeError, FileNotFoundError):
            return None
        queue_path = self.root / "data" / "editorial_queue" / batch_date / "topics.json"
        payload = _read_json(queue_path, {})
        if not isinstance(payload, dict) or _text(payload.get("mode")) != "advanced":
            return None
        tasks: list[dict[str, Any]] = []
        for index, item in enumerate(payload.get("topics") or [], start=1):
            if not isinstance(item, dict):
                continue
            slug = _text(item.get("slug"))
            if not slug:
                continue
            task_id = _text(item.get("task_id")) or f"website-advanced-{batch_date}-{slug}"
            resolution = resolve_research_artifacts(
                self.root,
                task_id=task_id,
                slug=slug,
                batch_date=batch_date,
            )
            report = _read_json(resolution.enrichment_report_file, {})
            blockers = [
                *resolution.missing_files,
                *resolution.legacy_reasons,
                *(report.get("blockers") or [] if isinstance(report, dict) else []),
            ]
            tasks.append(
                {
                    "task_id": task_id,
                    "article_slug": slug,
                    "batch_date": batch_date,
                    "root_topic_id": _text(item.get("root_topic_id")),
                    "sequence": item.get("sequence_number") or item.get("sequence") or index,
                    "daily_angle": _text(item.get("daily_angle")),
                    "research_artifact_dir": _relative(
                        self.root, resolution.canonical_dir
                    ),
                    "research_state": resolution.status or "BLOCKED_RESEARCH",
                    "article_ready": resolution.article_ready,
                    "research_level": resolution.research_level,
                    "draft_exportable": resolution.draft_exportable,
                    "comparison_status": resolution.comparison_status,
                    "outstanding_research_tasks": resolution.outstanding_research_tasks,
                    "known_weak_sections": list(resolution.weak_sections),
                    "estimated_publish_readiness": resolution.estimated_publish_readiness,
                    "paragraphs": resolution.paragraph_count,
                    "claims": resolution.claim_count,
                    "coverage_score": resolution.coverage_score,
                    "angle_profile": resolution.angle_profile,
                    "required_entities": resolution.required_entity_count,
                    "resolved_entities": resolution.resolved_entity_count,
                    "entity_coverage_score": resolution.entity_coverage_score,
                    "candidate_claims": resolution.candidate_claim_count,
                    "rejected_claims": resolution.rejected_claim_count,
                    "eligible": resolution.draft_exportable,
                    "reason": "; ".join(
                        dict.fromkeys(
                            str(reason) for reason in blockers if str(reason).strip()
                        )
                    )
                    or (
                        "Research evidence is ready."
                        if resolution.draft_exportable
                        else "Research evidence is not safe for a first draft."
                    ),
                }
            )
        if not tasks:
            return None
        result = {
            "task_type": "WEBSITE_ADVANCED",
            "batch_date": batch_date,
            "task_count": len(tasks),
            "eligible": sum(bool(row["eligible"]) for row in tasks),
            "held": sum(not bool(row["eligible"]) for row in tasks),
            "tasks": tasks,
            "source": _relative(self.root, queue_path),
        }
        return result

    def _preflight_task_rows(
        self,
        tasks: list[dict[str, Any]],
        ready: list[dict[str, Any]],
        held: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        ready_ids = {_text(row.get("task_id")) for row in ready}
        held_by_id = {_text(row.get("task_id")): row for row in held}
        result: list[dict[str, Any]] = []
        for index, task in enumerate(tasks, start=1):
            task_id = _text(task.get("task_id"))
            slug = _text(task.get("article_slug"))
            hold = held_by_id.get(task_id, {})
            if _text(task.get("social_mode")) == "SOURCE_BASED_SOCIAL":
                result.append(
                    {
                        "task_id": task_id,
                        "article_slug": slug,
                        "batch_date": _text(task.get("batch_date")),
                        "root_topic_id": _text(task.get("root_topic_id")),
                        "sequence": task.get("sequence_number") or task.get("sequence") or index,
                        "daily_angle": _text(task.get("social_angle") or task.get("daily_angle")),
                        "content_origin": "WEBSITE_ROOT_BASED",
                        "social_mode": "SOURCE_BASED_SOCIAL",
                        "source_article_slug": _text(task.get("source_article_slug") or slug),
                        "source_revision_id": _text(task.get("source_revision_id")),
                        "source_content_hash": _text(task.get("source_content_hash")),
                        "research_artifact_dir": _text(task.get("source_evidence_reference")),
                        "research_state": "EVIDENCE_INHERITED",
                        "article_ready": True,
                        "research_level": "SOURCE_BASED_SOCIAL",
                        "draft_exportable": True,
                        "comparison_status": "NOT_APPLICABLE",
                        "outstanding_research_tasks": [],
                        "known_weak_sections": [],
                        "estimated_publish_readiness": 1.0,
                        "paragraphs": 0,
                        "claims": 0,
                        "coverage_score": 1.0,
                        "angle_profile": "platform_adaptation",
                        "required_entities": 0,
                        "resolved_entities": 0,
                        "entity_coverage_score": 1.0,
                        "candidate_claims": 0,
                        "rejected_claims": 0,
                        "eligible": task_id in ready_ids,
                        "reason": _text(hold.get("reason")) or "Verified Website source evidence is inherited; unrelated Website research gates are not applicable.",
                    }
                )
                continue
            resolution = resolve_research_artifacts(
                self.root,
                task_id=task_id,
                slug=slug,
                batch_date=_text(task.get("batch_date")),
            )
            result.append(
                {
                    "task_id": task_id,
                    "article_slug": slug,
                    "batch_date": _text(task.get("batch_date")),
                    "root_topic_id": _text(task.get("root_topic_id")),
                    "sequence": task.get("sequence_number") or task.get("sequence") or index,
                    "daily_angle": _text(task.get("daily_angle")),
                    "research_artifact_dir": _relative(
                        self.root, resolution.canonical_dir
                    ),
                    "research_state": resolution.status,
                    "article_ready": resolution.article_ready,
                    "research_level": resolution.research_level,
                    "draft_exportable": resolution.draft_exportable,
                    "comparison_status": resolution.comparison_status,
                    "outstanding_research_tasks": resolution.outstanding_research_tasks,
                    "known_weak_sections": list(resolution.weak_sections),
                    "estimated_publish_readiness": resolution.estimated_publish_readiness,
                    "paragraphs": resolution.paragraph_count,
                    "claims": resolution.claim_count,
                    "coverage_score": resolution.coverage_score,
                    "angle_profile": resolution.angle_profile,
                    "required_entities": resolution.required_entity_count,
                    "resolved_entities": resolution.resolved_entity_count,
                    "entity_coverage_score": resolution.entity_coverage_score,
                    "candidate_claims": resolution.candidate_claim_count,
                    "rejected_claims": resolution.rejected_claim_count,
                    "eligible": task_id in ready_ids,
                    "reason": _text(hold.get("reason")) or "Research evidence is ready.",
                }
            )
        return result

    def _build_package(
        self,
        package_dir: Path,
        package_id: str,
        task_type: str,
        batch_date: str,
        tasks: list[dict[str, Any]],
        held_tasks: list[dict[str, Any]] | None = None,
    ) -> None:
        if task_type.startswith("WEBSITE_"):
            tasks = [
                {
                    **row,
                    "target_output_paths": [
                        f"website/{row['article_slug']}/article.html",
                        f"website/{row['article_slug']}/article.md",
                        f"website/{row['article_slug']}/metadata.json",
                        f"website/{row['article_slug']}/validation.json",
                    ],
                }
                for row in tasks
            ]
        manifest = {
            "schema_version": PACKAGE_SCHEMA,
            "package_id": package_id,
            "task_type": task_type,
            "batch_date": batch_date,
            "generated_at": _now(),
            "human_approval_required": True,
            "tasks": [
                {
                    "task_id": row["task_id"],
                    "article_slug": row["article_slug"],
                    "revision": row["revision"],
                    "target_output_paths": row["target_output_paths"],
                }
                for row in tasks
            ],
        }
        _write_json(package_dir / "manifest.json", manifest)
        _write_json(
            package_dir / "batch_selection.json",
            {
                "schema_version": "research_partial_batch_selection_v1",
                "package_id": package_id,
                "policy": "iterative_research_minimum",
                "exported": [
                    {"task_id": row["task_id"], "article_slug": row["article_slug"]}
                    for row in tasks
                ],
                "held": list(held_tasks or []),
                "replacement_topics_created": False,
                "weekly_root_lock_changed": False,
            },
        )
        _write_json(package_dir / "queue.json", {"schema_version": QUEUE_SCHEMA, "tasks": tasks})
        _write_json(package_dir / "OUTPUT_CONTRACT.json", self._output_contract(task_type, tasks))
        _write_json(package_dir / "source_manifest.json", self._source_manifest(tasks))
        for folder in (
            "official_sources",
            "supporting_sources",
            "research",
            "images",
            "templates",
            "examples",
            "editorial_brain",
            "editorial_memory",
            "gold_library",
        ):
            target = package_dir / folder
            target.mkdir(parents=True, exist_ok=True)
            (target / "README.txt").write_text(
                f"{folder} supplied for this package. This file may be ignored by the writer.\n",
                encoding="utf-8",
                newline="\n",
            )
        (package_dir / "START_HERE.txt").write_text(
            self._start_here_text(task_type), encoding="utf-8", newline="\n"
        )

        (package_dir / "ZIP_CREATION_GUIDE.md").write_text(
            self._zip_creation_guide(task_type), encoding="utf-8", newline="\n"
        )
        (package_dir / "CREATE_COMPLETED_DRAFTS.py").write_text(
            self._completed_zip_helper_script(), encoding="utf-8", newline="\n"
        )
        self._copy_inputs(package_dir, tasks)
        self._write_editorial_memory_brief(package_dir, tasks)
        self._copy_guidance(package_dir)
        layers = self._prompt_layers(package_id, task_type, tasks)
        for name, content in layers:
            (package_dir / name).write_text(content, encoding="utf-8", newline="\n")
        prompt = self._assembled_prompt(layers)
        (package_dir / "PROMPT.md").write_text(prompt, encoding="utf-8", newline="\n")
        (package_dir / "PROMPT.txt").write_text(prompt, encoding="utf-8", newline="\n")
        (package_dir / "TASK.md").write_text(self._task_summary(tasks), encoding="utf-8", newline="\n")
        (package_dir / "validation_rules.md").write_text(
            self._validation_rules(task_type), encoding="utf-8", newline="\n"
        )
        if task_type.startswith("WEBSITE_"):
            website_contract = self._website_writing_contract(task_type, tasks)
            _write_json(
                package_dir / "website_writing_contract.json",
                website_contract,
            )
        else:
            website_contract = None
        build_verified_package(
            package_dir=package_dir,
            root=self.root,
            package_id=package_id,
            task_type=task_type,
            batch_date=batch_date,
            tasks=tasks,
            output_contract=self._output_contract(task_type, tasks),
            website_contract=website_contract,
        )
        (package_dir / "START_HERE.txt").write_text(
            self._verified_start_here_text(task_type),
            encoding="utf-8",
            newline="\n",
        )

    def _write_editorial_memory_brief(self, package_dir: Path, tasks: list[dict[str, Any]]) -> None:
        if not feature_enabled(self.root, "editorial_memory.enabled"):
            return
        try:
            memory_tasks = [
                {
                    "task_id": row.get("task_id"),
                    "slug": row.get("article_slug"),
                    "title": row.get("title") or row.get("article_title"),
                    "root_topic": row.get("root_topic_id"),
                    "angle": row.get("daily_angle") or row.get("angle"),
                    "keyword": row.get("primary_keyword") or row.get("keyword"),
                    "entities": row.get("entities") or [],
                    "claims": row.get("claims") or [],
                    "cited_sources": row.get("verified_sources") or row.get("source_urls") or [],
                }
                for row in tasks
            ]
            _write_json(
                package_dir / "editorial_memory" / "MEMORY_BRIEF.json",
                EditorialMemoryStore(root=self.root).memory_brief(memory_tasks),
            )
        except (OSError, ValueError, sqlite3.Error):
            # Recommendation-only integration must never interrupt export.
            return

    def _partition_research_ready(
        self,
        tasks: list[dict[str, Any]],
        task_type: str,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        if not task_type.startswith("WEBSITE_"):
            return tasks, []
        config = _read_json(self.root / "config" / "editorial_system.json", {})
        policy = (
            config.get("research_enrichment", {}).get("partial_batch_export", True)
            if isinstance(config, dict)
            else True
        )
        enforce_advanced_evidence = bool(
            isinstance(config, dict)
            and isinstance(config.get("research_enrichment"), dict)
            and config["research_enrichment"].get("enabled", False)
        )
        ready: list[dict[str, Any]] = []
        held: list[dict[str, Any]] = []
        for task in tasks:
            slug = _text(task.get("article_slug"))
            source_preflight = _website_source_preflight(self.root, task)
            resolution = resolve_research_artifacts(
                self.root,
                task_id=_text(task.get("task_id")),
                slug=slug,
                batch_date=_text(task.get("batch_date")),
            )
            report_path = resolution.enrichment_report_file
            report = _read_json(report_path, {})
            if task_type != "WEBSITE_ADVANCED" or not enforce_advanced_evidence:
                # Missing enrichment artifacts retain legacy compatibility,
                # but once the canonical resolver has evidence its decision
                # is authoritative for every WEBSITE lane.
                if not report_path.is_file():
                    if source_preflight["ready"]:
                        ready.append(task)
                    else:
                        held.append(
                            {
                                "task_id": task["task_id"],
                                "article_slug": slug,
                                "status": "BLOCKED_RESEARCH",
                                "reason": "; ".join(source_preflight["blockers"]),
                                "enrichment_report": _relative(self.root, report_path),
                                "research_artifact_dir": _relative(self.root, resolution.canonical_dir),
                                "paragraphs": resolution.paragraph_count,
                                "claims": resolution.claim_count,
                                "coverage_score": resolution.coverage_score,
                                "source_preflight": source_preflight,
                                "held_at": _now(),
                            }
                        )
                    continue
                is_ready = resolution.draft_exportable
            else:
                is_ready = resolution.draft_exportable
            # Source safety is never bypassed by partial_batch_export.  That
            # policy controls evidence completeness, not zero-source drafts.
            if (is_ready or not policy) and source_preflight["ready"]:
                ready.append(task)
                continue
            reasons = (
                [
                    *resolution.missing_files,
                    *resolution.legacy_reasons,
                    *(report.get("blockers") or [] if isinstance(report, dict) else []),
                ]
                if task_type == "WEBSITE_ADVANCED" and enforce_advanced_evidence
                else list(report.get("blockers") or ["Research evidence is not ready."])
            )
            source_reasons = list(source_preflight.get("blockers") or [])
            reasons = [*source_reasons, *reasons]
            held.append(
                {
                    "task_id": task["task_id"],
                    "article_slug": slug,
                    "status": resolution.status or "BLOCKED_RESEARCH",
                    "reason": "; ".join(
                        dict.fromkeys(str(reason) for reason in reasons if str(reason).strip())
                    )
                    or "Research evidence is not ready.",
                    "enrichment_report": _relative(self.root, report_path),
                    "research_artifact_dir": _relative(self.root, resolution.canonical_dir),
                    "paragraphs": resolution.paragraph_count,
                    "claims": resolution.claim_count,
                    "coverage_score": resolution.coverage_score,
                    "source_preflight": source_preflight,
                    "held_at": _now(),
                }
            )
        return ready, held

    def _copy_inputs(self, package_dir: Path, tasks: list[dict[str, Any]]) -> None:
        self._package_materializer().copy_inputs(
            package_dir,
            tasks,
            copy_website_research_artifacts=self._copy_website_research_artifacts,
            copy_existing_article_snapshot=self._copy_existing_article_snapshot,
            copy_series_history=self._copy_series_history,
        )

    def _copy_existing_article_snapshot(self, package_dir: Path, task: dict[str, Any]) -> None:
        self._package_materializer().copy_existing_article_snapshot(package_dir, task)

    def _copy_website_research_artifacts(self, package_dir: Path, slug: str) -> None:
        self._package_materializer().copy_website_research_artifacts(package_dir, slug)

    def _copy_series_history(self, package_dir: Path, task: dict[str, Any]) -> None:
        self._package_materializer().copy_series_history(package_dir, task)

    def _copy_guidance(self, package_dir: Path) -> None:
        self._package_materializer().copy_guidance(package_dir)

    @staticmethod
    def _copy_guidance_tree(source_root: Path, target_root: Path) -> None:
        ExternalWriterPackageMaterializer.copy_guidance_tree(source_root, target_root)

    @staticmethod
    def _package_id(batch_date: str, task_type: str, tasks: list[dict[str, Any]]) -> str:
        identity = "|".join(
            f"{row['task_id']}:{row.get('revision', 1)}" for row in sorted(tasks, key=lambda x: x["task_id"])
        )
        return hashlib.sha256(f"{batch_date}|{task_type}|{identity}".encode("utf-8")).hexdigest()[:16]

    @staticmethod
    def _output_contract(task_type: str, tasks: list[dict[str, Any]]) -> dict[str, Any]:
        website_validation_file = (
            "validation.json"
            if any(
                str(path).endswith("/validation.json")
                for row in tasks
                for path in row.get("target_output_paths") or []
            )
            else "validation_report.json"
        )
        result = {
            "schema_version": RETURN_SCHEMA,
            "required_filename": "completed_drafts.zip",
            "task_type": task_type,
            "allowed_paths": [
                "completed_manifest.json",
                "verified_package_contract.json",
                *[path for row in tasks for path in row["target_output_paths"]],
                *[
                    f"{'website' if task_type.startswith('WEBSITE_') else 'social'}/{row['article_slug']}/assets/*"
                    for row in tasks
                ],
            ],
            "website_required": [
                "article.html",
                "article.md",
                "metadata.json",
                website_validation_file,
            ],
            "social_platforms": list(SOCIAL_PLATFORMS),
            "social_variants": ["A.md", "B.md", "C.md"],
            "social_editorial_contract": (
                {
                    "schema_version": SOCIAL_SERIES_SCHEMA,
                    "series_plan_required": True,
                    "series_plan_fields": [
                        "schema_version",
                        "pillar_title",
                        "day_number",
                        "today_angle",
                    ],
                    "platform_metadata_fields": [
                        "title",
                        "variant_titles",
                        "variant_strategies",
                        "social_angles",
                        "evidence_refs",
                        "new_claims",
                        "visual_recommended",
                        "visual_type",
                        "visual_concept",
                        "visual_source",
                        "visual_alt_text",
                        "hashtags",
                        *([] if task_type == "SOCIAL_HOT_NEWS" else ["cta"]),
                    ],
                    "cta_policy": (
                        "optional_story_specific_only"
                        if task_type == "SOCIAL_HOT_NEWS"
                        else "required_live_article_action"
                    ),
                    "variant_title_keys": list(SOCIAL_VARIANTS),
                    "titles_unique_within_task": True,
                    "titles_must_not_match_article_title": True,
                    "titles_must_not_reuse_prior_social_titles": True,
                    "future_promise_rule": (
                        "A dated future CTA is permitted only when task metadata links to a real queued "
                        "follow-up with a scheduled date. Otherwise avoid relative dates and future promises."
                    ),
                    "source_render_rule": "Never leave Source: blank; render the supplied source name and URL.",
                    "social_value_rule": "Explain what happened, why it matters, and one practical takeaway.",
                    "ending_rule": (
                        "CTA is optional. End with a story-specific implication, decision question, operational "
                        "takeaway, concise observation, or the official source. Generic CTA endings are rejected."
                    ),
                    "hashtag_rule": "Use only directly relevant hashtags; zero hashtags is valid.",
                    "platform_writing_guidance": dict(SOCIAL_PLATFORM_WRITING_GUIDANCE),
                    "platform_playbooks": {
                        platform: dict(SOCIAL_PLATFORM_PLAYBOOKS.get(platform) or {})
                        for platform in SOCIAL_PLATFORMS
                    },
                    "variant_strategy_rule": {
                        "A.md": "ACTIONABLE",
                        "B.md": "INSIGHT_POINT_OF_VIEW",
                        "C.md": "PROBLEM_SOLUTION_CASE",
                    },
                    "x_contract": {
                        "hard_max_characters": X_MAX_CHARACTERS,
                        "thread_enabled": X_THREAD_ENABLED,
                        "over_limit_action": "regenerate_or_compress_semantically_never_truncate",
                        "website_link_optional": True,
                        "local_validation_required": True,
                    },
                    "pinterest_visual_rule": (
                        "Declare pinterest_visual_points using only task.pinterest_visual_facts; include a readable "
                        "headline, useful subhead, 2-4 points, and a source indicator."
                    ),
                    "every_variant_must_end_with_closing_cta": False,
                    "legacy_tomorrow_bridge_examples_do_not_use_without_scheduled_followup": {
                        "en": "Tomorrow, we will compare the next practical angle in this series.",
                        "allowed_only_when_task_scheduled_followup_exists": True,
                        "vi": "Ngày mai, mời bạn đón đọc góc tiếp theo trong chuỗi này.",
                    },
                }
                if task_type.startswith("SOCIAL_")
                else {}
            ),
            "human_approval_required": True,
            "public_output_validation": public_output_validation_contract(),
        }
        return result

    @staticmethod
    def _start_here_text(task_type: str) -> str:
        target_kind = "website article" if task_type.startswith("WEBSITE_") else "social draft"
        return (
            "Do not analyze or summarize this package as your final answer.\n"
            "Do not return prose, a checklist, or a review instead of completed files.\n"
            "\n"
            "Your job is to create the requested draft files and package them into completed_drafts.zip.\n"
            "\n"
            "Required order:\n"
            "1. Read 01_SYSTEM.md through 09_SELF_REVIEW.md in numeric order.\n"
            "2. Read PROMPT.md, output_contract.json, queue.json, source_manifest.json, and TASK.md.\n"
            f"3. Write every required {target_kind} file listed in output_contract.json.\n"
            "4. Use only the supplied research, source, entity, keyword, history, and memory files.\n"
            "5. If research/<slug>/verified_facts exists, factual claims may use only records marked "
            "VERIFIED_OFFICIAL, VERIFIED_LOCAL_PRODUCTION, or VERIFIED_MULTISOURCE.\n"
            "6. Treat facts_to_verify and fact_conflicts as questions, never as publishable claims.\n"
            "7. Do not invent source URLs, public article URLs, image URLs, pricing claims, or product facts.\n"
            "8. If a returned draft references https://smileaireviewhub.com/<slug>/assets/<file>, "
            "also include the matching local file at website/<slug>/assets/<file> or social/<slug>/assets/<file>.\n"
            "9. Run this command from the package root after all files are written:\n"
            "   python CREATE_COMPLETED_DRAFTS.py\n"
            "10. Return only the generated completed_drafts.zip file.\n"
            "\n"
            "Safety rules:\n"
            "- Do not approve, publish, commit, push, deploy, index, or call any API.\n"
            "- Do not change task IDs, slugs, package_id, canonical URLs, or approval state.\n"
            "- Do not include executable files in completed_drafts.zip.\n"
        )

    @staticmethod
    def _verified_start_here_text(task_type: str) -> str:
        target_kind = "website article" if task_type.startswith("WEBSITE_") else "social draft"
        return (
            "Do not analyze or summarize this package as your final answer.\n"
            "This ZIP is the complete source of truth. Do not request repository access, chat "
            "history, private tools, or additional project context.\n\n"
            "Your role is writing only. Never search, browse, crawl, verify, or research. "
            "Never compare against information outside this ZIP.\n\n"
            "Read these files before writing:\n"
            "1. TASK.md, ARTICLE_SPEC.json, and OUTLINE.json\n"
            "2. FACT_LEDGER.json, VERIFIED_CLAIMS.json, and SOURCE_EXCERPTS.json\n"
            "3. SECTION_GUIDE.json, FAQ.json, TERMINOLOGY.json, and COMPETITOR_NOTES.json\n"
            "4. INTERNAL_LINKS.json, EXTERNAL_LINKS.json, IMAGE_GUIDE.json, and SCHEMA.json\n"
            "5. EDITORIAL_RULES.json, RESEARCH_GAPS.json, and WRITER_CHECKLIST.json\n"
            "6. VALIDATION_RULES.json and OUTPUT_CONTRACT.json\n"
            "7. GOLDEN_EXAMPLE/ for process demonstration only; never copy its facts.\n\n"
            "For WEBSITE_ADVANCED, also read each research/<slug>/research_inventory.json and "
            "consume FACT_LEDGER.json, SOURCE_EXCERPTS.json, sources.json, outline.json, "
            "writing_plan.json, faq.json, competitor_analysis.json, and entities.json. Writing "
            "an outline is not completion: verified evidence from these artifacts must appear "
            "in the finished article through supported entities, attributed claims, and citations.\n\n"
            f"Complete every required {target_kind} in the exact blueprint order. Each factual "
            "claim must trace to a claim_id in FACT_LEDGER.json. Never extract new facts from a "
            "URL and never guess missing details. SOURCE_EXCERPTS.json contains the relevant source "
            "paragraphs needed for writing; do not revisit any website. Every production article "
            "has the minimum verified claim count declared in its evidence_policy, with usage "
            "limits, freshness, and confidence. Omit a "
            "claim when the ledger does not support it. RESEARCH_TASKS.json lists known gaps, "
            "wording constraints, and held sections. Do not fill those gaps from memory. "
            "When comparison_status is HELD_WAITING_COMPARATORS, omit direct rankings and "
            "write only the root-product sections supported by the ledger.\n\n"
            "Legacy verified-fact files, when present, permit only VERIFIED_OFFICIAL, "
            "VERIFIED_LOCAL_PRODUCTION, or VERIFIED_MULTISOURCE records. Treat facts_to_verify "
            "and fact_conflicts as questions, never as publishable claims.\n\n"
            "If required information is absent, write a reader-facing Research Gap note instead "
            "of researching or guessing. Create every path listed in OUTPUT_CONTRACT.json. "
            "For website work, create article.md, article.html, metadata.json, and validation.json. "
            "Copy verified_package_contract.json "
            "unchanged into the returned ZIP root. Create completed_manifest.json according to "
            "OUTPUT_CONTRACT.json, including SHA-256 hashes for every returned file. Return one "
            "file named completed_drafts.zip.\n\n"
            "Before packaging WEBSITE_ADVANCED, run a private self-review covering ARTICLE_SPEC, "
            "word count, duplicate risk, pricing, security, integrations, comparison, FAQ, links, "
            "affiliate disclosure, entity coverage, citation coverage, CTA, and JSON-LD. Predict "
            "the Menu W AI Review score. If it is below 70 or any hard check fails, regenerate the "
            "article automatically and repeat, up to three total generation attempts. Never package "
            "a failed attempt, placeholder section, `coming soon` text, or empty comparison table.\n\n"
            "Do not approve, publish, commit, push, deploy, index, call an API, or alter task IDs, "
            "slugs, revisions, package_id, canonical URLs, or approval state.\n"
        )

    @staticmethod
    def _zip_creation_guide(task_type: str) -> str:
        output_root = "website/<slug>/" if task_type.startswith("WEBSITE_") else "social/<slug>/"
        return (
            "# How to return a Menu W compatible ZIP\n\n"
            "Menu W imports only a strict ZIP named `completed_drafts.zip`.\n\n"
            "## Required process\n\n"
            "1. Create all target files under the output folders listed in `OUTPUT_CONTRACT.json`.\n"
            f"2. Expected output root for this package: `{output_root}`.\n"
            "3. Run `python CREATE_COMPLETED_DRAFTS.py` from this package folder.\n"
            "4. Download or return the generated `completed_drafts.zip`.\n\n"
            "## Common rejection causes\n\n"
            "- `writer must be a JSON object`: the returned ZIP has no valid `completed_manifest.json` writer object.\n"
            "- `writer_name is required`: the writer object is missing `writer_name`.\n"
            "- `Returned content contains URLs outside task allowlist`: the draft contains a URL that was not supplied "
            "or a public asset URL without the matching local asset file.\n"
            "- `Missing required output`: a target file from `OUTPUT_CONTRACT.json` was not created.\n"
            "- `Executable files are not allowed`: the returned ZIP contains `.py`, `.js`, `.exe`, `.bat`, or similar files.\n\n"
            "The helper script creates the manifest, writer object, SHA-256 file hashes, and ZIP member list for you. "
            "Do not hand-write the manifest unless you exactly match the contract.\n"
        )

    @staticmethod
    def _completed_zip_helper_script() -> str:
        return r'''from __future__ import annotations

import hashlib
import json
import os
import posixpath
import re
import sys
import zipfile
from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse


EXECUTABLE_SUFFIXES = {
    ".bat",
    ".cmd",
    ".com",
    ".dll",
    ".exe",
    ".js",
    ".jse",
    ".msi",
    ".ps1",
    ".py",
    ".scr",
    ".sh",
    ".vbs",
    ".wsf",
}


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    return value


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_safe_relative(path: str) -> bool:
    pure = PurePosixPath(path)
    return (
        bool(path)
        and not pure.is_absolute()
        and "\\" not in path
        and all(part not in {"", ".", ".."} for part in pure.parts)
    )


def allowed(path: str, allowed_paths: list[str]) -> bool:
    if path == "completed_manifest.json":
        return True
    for pattern in allowed_paths:
        if pattern.endswith("/*"):
            prefix = pattern[:-1]
            if path.startswith(prefix):
                return True
        elif path == pattern:
            return True
    return False


def output_root_for(task_type: str, slug: str) -> str:
    lane = "website" if task_type.startswith("WEBSITE_") else "social"
    return f"{lane}/{slug}"


class EditorialParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.skip = 0
        self.heading = ""
        self.heading_parts: list[str] = []
        self.text: list[str] = []
        self.h2: list[str] = []
        self.h3: list[str] = []
        self.h3_parents: list[str] = []
        self.latest_h2 = ""
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.casefold()
        if tag in {"script", "style", "nav", "footer"}:
            self.skip += 1
            return
        if self.skip:
            return
        if tag in {"h2", "h3"}:
            self.heading = tag
            self.heading_parts = []
        if tag == "a":
            href = next((value or "" for key, value in attrs if key.casefold() == "href"), "")
            if href.strip():
                self.links.append(href.strip())

    def handle_endtag(self, tag: str) -> None:
        tag = tag.casefold()
        if tag in {"script", "style", "nav", "footer"}:
            self.skip = max(0, self.skip - 1)
            return
        if self.skip:
            return
        if tag == self.heading:
            value = " ".join(self.heading_parts).strip()
            if tag == "h2":
                self.h2.append(value)
                self.latest_h2 = value
            else:
                self.h3.append(value)
                self.h3_parents.append(self.latest_h2)
            self.heading = ""
            self.heading_parts = []

    def handle_data(self, data: str) -> None:
        if self.skip or not data.strip():
            return
        self.text.append(data.strip())
        if self.heading:
            self.heading_parts.append(data.strip())


def advanced_editorial_review(
    root: Path,
    slug: str,
    task_id: str,
    html: str,
    spec: dict,
    website_contract: dict,
) -> dict:
    parser = EditorialParser()
    parser.feed(html)
    text = " ".join(parser.text)
    headings = [value.casefold() for value in parser.h2]
    target = spec.get("target_length") if isinstance(spec.get("target_length"), dict) else {}
    word_contract = website_contract.get("editorial_word_count") or {}
    minimum_words = int(target.get("minimum_words") or word_contract.get("minimum") or 2200)
    maximum_words = int(target.get("maximum_words") or word_contract.get("maximum") or 2600)
    structure = website_contract.get("structure") or {}
    h2_range = structure.get("h2_range") or []
    section_order = spec.get("section_order") or []
    minimum_h2 = max(int(h2_range[0] if h2_range else 8), len(section_order))
    faq = spec.get("faq_requirements") if isinstance(spec.get("faq_requirements"), dict) else {}
    faq_range = structure.get("faq_questions") or []
    minimum_faq = int(
        faq.get("minimum_questions")
        or len(faq.get("questions") or [])
        or (faq_range[0] if faq_range else 1)
    )
    required_internal = spec.get("required_internal_links") or []
    minimum_internal = len(required_internal) if required_internal else 1
    canonical = re.search(
        r"<link\b[^>]*rel=['\"]canonical['\"][^>]*href=['\"]([^'\"]+)",
        html,
        flags=re.I,
    )
    canonical_host = urlparse(canonical.group(1)).netloc.casefold() if canonical else ""
    internal: set[str] = set()
    citations: set[str] = set()
    for href in parser.links:
        parsed = urlparse(href)
        if href.startswith("/") and not href.startswith("//"):
            internal.add(href)
        elif parsed.scheme in {"http", "https"}:
            if canonical_host and parsed.netloc.casefold() == canonical_host:
                internal.add(href)
            else:
                citations.add(href)
    checks = {
        "pricing section": ("pricing", "price", "cost"),
        "security section": ("security", "privacy", "compliance"),
        "integrations section": ("integration", "integrations", "connectors"),
        "comparison section": ("comparison", "compare", "alternatives", "versus", " vs "),
    }
    errors: list[str] = []
    words = re.findall(r"[A-Za-z0-9']+", text)
    if len(words) < minimum_words:
        errors.append(f"word count {len(words)} is below ARTICLE_SPEC minimum {minimum_words}")
    if len(words) > maximum_words:
        errors.append(f"word count {len(words)} exceeds ARTICLE_SPEC maximum {maximum_words}")
    if len(parser.h2) < minimum_h2:
        errors.append(f"H2 count {len(parser.h2)} is below minimum {minimum_h2}")
    if not any("faq" in value or "frequently asked" in value for value in headings):
        errors.append("FAQ section is missing")
    faq_questions = sum(
        1
        for parent in parser.h3_parents
        if "faq" in parent.casefold() or "frequently asked" in parent.casefold()
    )
    if faq_questions < minimum_faq:
        errors.append(f"FAQ question count {faq_questions} is below ARTICLE_SPEC minimum {minimum_faq}")
    for label, markers in checks.items():
        if not any(any(marker in f" {heading} " for marker in markers) for heading in headings):
            errors.append(f"{label} is missing")
    lowered = text.casefold()
    if "affiliate disclosure" not in lowered or "commission" not in lowered:
        errors.append("affiliate disclosure with commission language is missing")
    if len(internal) < minimum_internal:
        errors.append(f"internal link count {len(internal)} is below ARTICLE_SPEC minimum {minimum_internal}")
    if len(citations) < 2:
        errors.append(f"external citation count {len(citations)} is below minimum 2")

    placeholder_found = bool(
        re.search(
            r"\{\{[^{}]+\}\}|\[(?:placeholder|insert [^\]]+)\]|\b(?:coming soon|lorem ipsum|tbd|todo)\b",
            text,
            flags=re.I,
        )
    )
    if placeholder_found:
        errors.append("placeholder or coming-soon text is present")

    h2_blocks = re.split(r"(?i)<h2\b[^>]*>", html)
    empty_sections = 0
    for block in h2_blocks[1:]:
        body = re.split(r"(?i)</h2>", block, maxsplit=1)
        if len(body) != 2:
            empty_sections += 1
            continue
        section_body = re.split(r"(?i)<h2\b", body[1], maxsplit=1)[0]
        if len(re.findall(r"[A-Za-z0-9']+", re.sub(r"<[^>]+>", " ", section_body))) < 20:
            empty_sections += 1
    if empty_sections:
        errors.append(f"{empty_sections} H2 section(s) are empty or insubstantial")

    tables = re.findall(r"(?is)<table\b[^>]*>(.*?)</table>", html)
    nonempty_tables = [
        table
        for table in tables
        if len(re.findall(r"(?is)<t[dh]\b[^>]*>\s*(?!</t[dh]>).+?</t[dh]>", table)) >= 2
    ]
    if not nonempty_tables:
        errors.append("comparison table is missing or empty")

    cta_present = bool(
        re.search(
            r"(?is)<a\b[^>]*>[^<]*(?:try|visit|check|read|compare|explore|learn|get started|view)[^<]*</a>",
            html,
        )
    )
    if not cta_present:
        errors.append("reader-facing CTA link is missing")
    json_ld_present = bool(
        re.search(r"<script\b[^>]*type=['\"]application/ld\+json['\"]", html, flags=re.I)
    )
    if bool((website_contract.get("schema_policy") or {}).get("json_ld_required", True)) and not json_ld_present:
        errors.append("required JSON-LD is missing")

    required_artifacts = list(website_contract.get("required_research_artifacts") or [])
    research_root = root / "research" / slug
    available_names = {
        path.name.casefold()
        for path in research_root.rglob("*")
        if path.is_file()
    }
    missing_artifacts = [
        name for name in required_artifacts if name.casefold() not in available_names
    ]
    if missing_artifacts:
        errors.append("required research artifacts missing: " + ", ".join(missing_artifacts))

    validation_path = root / "website" / slug / "validation.json"
    validation = load_json(validation_path) if validation_path.is_file() else {}
    generation_attempt = int(validation.get("generation_attempt") or 0)
    if generation_attempt < 1 or generation_attempt > 3:
        errors.append("validation.json generation_attempt must be between 1 and 3")
    utilization = (
        validation.get("research_utilization")
        if isinstance(validation.get("research_utilization"), dict)
        else {}
    )
    consumed = {
        str(value).casefold()
        for value in utilization.get("artifacts", [])
        if str(value).strip()
    }
    unreported_artifacts = [
        name for name in required_artifacts if name.casefold() not in consumed
    ]
    if unreported_artifacts:
        errors.append(
            "research utilization not declared for: " + ", ".join(unreported_artifacts)
        )
    contract_payload = load_json(root / "verified_package_contract.json")
    contract_task = next(
        (
            row for row in contract_payload.get("tasks", [])
            if isinstance(row, dict) and str(row.get("task_id") or "") == task_id
        ),
        {},
    )
    minimum_claims = int(
        (contract_task.get("evidence_policy") or {}).get(
            "minimum_publishable_claims", 1
        )
    )
    fact_payload = load_json(root / "FACT_LEDGER.json")
    fact_row = next(
        (
            row for row in fact_payload.get("articles", [])
            if isinstance(row, dict) and str(row.get("task_id") or "") == task_id
        ),
        {},
    )
    valid_claim_ids = {
        str(row.get("claim_id") or "")
        for row in fact_row.get("facts", [])
        if isinstance(row, dict) and str(row.get("claim_id") or "")
    }
    used_claim_ids = {
        str(value) for value in utilization.get("used_claim_ids", []) if str(value)
    }
    invalid_claim_ids = sorted(used_claim_ids - valid_claim_ids)
    required_claim_count = min(minimum_claims, len(valid_claim_ids))
    if len(used_claim_ids & valid_claim_ids) < required_claim_count:
        errors.append(
            f"verified claim utilization {len(used_claim_ids & valid_claim_ids)} "
            f"is below required {required_claim_count}"
        )
    if invalid_claim_ids:
        errors.append("unknown used_claim_ids: " + ", ".join(invalid_claim_ids))
    declared_citations = {
        str(value) for value in utilization.get("citation_urls", []) if str(value)
    }
    if not citations.issubset(declared_citations):
        errors.append("research_utilization.citation_urls does not cover article citations")

    entity_profile = load_json(root / "ENTITY_PROFILE.json")
    entity_row = next(
        (
            row for row in entity_profile.get("articles", [])
            if isinstance(row, dict) and str(row.get("task_id") or "") == task_id
        ),
        {},
    )
    entity_names = [
        str(entity.get("official_name") or "").strip()
        for entity in entity_row.get("entities", [])
        if isinstance(entity, dict) and str(entity.get("official_name") or "").strip()
    ]
    covered_entities = [
        name for name in entity_names if name.casefold() in text.casefold()
    ]
    entity_coverage = round(
        len(covered_entities) / max(1, len(entity_names)) * 100,
        2,
    )
    if entity_names and entity_coverage < 100:
        errors.append(f"entity coverage {entity_coverage} is below 100")

    paragraphs = [
        re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", value)).strip().casefold()
        for value in re.findall(r"(?is)<p\b[^>]*>(.*?)</p>", html)
    ]
    comparable = [value for value in paragraphs if len(value.split()) >= 20]
    duplicated = len(comparable) - len(set(comparable))
    history_paragraphs: set[str] = set()
    history_root = research_root / "series_history"
    if history_root.is_dir():
        for path in history_root.rglob("article.md"):
            for paragraph in re.split(r"(?:\r?\n){2,}", path.read_text(encoding="utf-8")):
                normalized = re.sub(r"\s+", " ", paragraph).strip().casefold()
                if len(normalized.split()) >= 20:
                    history_paragraphs.add(normalized)
    website_root = root / "website"
    if website_root.is_dir():
        for path in website_root.glob("*/article.html"):
            if path.parent.name == slug:
                continue
            other_html = path.read_text(encoding="utf-8")
            for paragraph in re.findall(r"(?is)<p\b[^>]*>(.*?)</p>", other_html):
                normalized = re.sub(
                    r"\s+",
                    " ",
                    re.sub(r"<[^>]+>", " ", paragraph),
                ).strip().casefold()
                if len(normalized.split()) >= 20:
                    history_paragraphs.add(normalized)
    duplicated += sum(1 for value in set(comparable) if value in history_paragraphs)
    duplicate_risk = round(duplicated / max(1, len(comparable)) * 100, 2)
    maximum_duplicate = float(
        (website_contract.get("preflight_quality") or {}).get("maximum_duplicate_risk", 35)
    )
    if duplicate_risk > maximum_duplicate:
        errors.append(f"duplicate risk {duplicate_risk} exceeds maximum {maximum_duplicate}")

    required_checks = 17
    coverage = round(max(0, required_checks - len(errors)) / required_checks * 100, 2)
    citation_coverage = round(min(100, len(citations) / 2 * 100), 2)
    predicted_score = round(
        max(
            0,
            min(
                100,
                coverage * 0.55
                + (100 - duplicate_risk) * 0.15
                + entity_coverage * 0.15
                + citation_coverage * 0.15,
            ),
        ),
        2,
    )
    minimum_score = float(
        (website_contract.get("preflight_quality") or {}).get(
            "minimum_predicted_ai_score", 70
        )
    )
    if predicted_score < minimum_score:
        errors.append(f"predicted AI score {predicted_score} is below minimum {minimum_score}")
    return {
        "task_id": task_id,
        "slug": slug,
        "predicted_ai_score": predicted_score,
        "word_count": len(words),
        "duplicate_risk": duplicate_risk,
        "coverage": coverage,
        "entity_coverage": entity_coverage,
        "citation_coverage": citation_coverage,
        "missing_sections": errors,
        "expected_menu_w_result": "VALIDATION_PASS" if not errors else "BLOCKED",
        "generation_attempt": generation_attempt,
        "errors": errors,
    }


def normalized_social_title(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").casefold()).strip()


def clean_website_title(value: object) -> str:
    text = unescape(re.sub(r"<[^>]+>", " ", str(value or "")))
    return re.sub(r"\s+", " ", text).strip()


def normalized_website_title(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", " ", clean_website_title(value).casefold()).strip()


def website_title_review(root: Path, task: dict) -> tuple[str, list[str]]:
    errors: list[str] = []
    slug = str(task.get("article_slug") or task.get("slug") or "")
    article_root = root / "website" / slug
    try:
        metadata = load_json(article_root / "metadata.json")
        html = (article_root / "article.html").read_text(encoding="utf-8")
        markdown = (article_root / "article.md").read_text(encoding="utf-8")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return "", [f"website title files are missing or invalid: {exc}"]
    html_title_match = re.search(r"(?is)<title\b[^>]*>(.*?)</title>", html)
    html_h1_match = re.search(r"(?is)<h1\b[^>]*>(.*?)</h1>", html)
    markdown_h1_match = re.search(r"(?m)^#\s+(.+?)\s*$", markdown)
    values = [
        clean_website_title(metadata.get("title")),
        clean_website_title(html_title_match.group(1) if html_title_match else ""),
        clean_website_title(html_h1_match.group(1) if html_h1_match else ""),
        clean_website_title(markdown_h1_match.group(1) if markdown_h1_match else ""),
    ]
    normalized = [normalized_website_title(value) for value in values]
    if not all(normalized) or len(set(normalized)) != 1:
        errors.append(
            "public title must match in metadata.title, HTML title, HTML H1, and Markdown H1"
        )
    title = values[0]
    if len(title) >= 45 and re.search(r"\b[A-Za-z]$", title):
        errors.append("title appears truncated because it ends with a single-letter fragment")
    prior = {
        normalized_website_title(value)
        for value in task.get("prior_website_titles") or []
        if normalized_website_title(value)
    }
    if normalized[0] and normalized[0] in prior:
        errors.append(f"title reuses a prior website title: {title}")
    return normalized[0], errors


def social_series_review(root: Path, task: dict, contract: dict) -> list[str]:
    errors: list[str] = []
    slug = str(task.get("article_slug") or task.get("slug") or "")
    metadata_path = root / "social" / slug / "metadata.json"
    try:
        metadata = load_json(metadata_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return [f"social metadata is missing or invalid: {exc}"]
    series_plan = metadata.get("series_plan")
    if not isinstance(series_plan, dict):
        return ["social metadata must declare series_plan"]
    social_contract = contract.get("social_editorial_contract") or {}
    expected_schema = str(social_contract.get("schema_version") or "social_editorial_series_v1")
    if str(series_plan.get("schema_version") or "") != expected_schema:
        errors.append(f"series_plan schema_version must be {expected_schema}")
    strict_value = bool((task.get("social_value_requirements") or {}).get("enabled"))
    complementary_components = str(task.get("task_type") or "") == "SOCIAL_WEBSITE_DISTRIBUTION"
    fields = (
        ("pillar_title", "today_angle")
        if strict_value or complementary_components
        else ("pillar_title", "today_angle", "next_day_title")
    )
    for field in fields:
        if not str(series_plan.get(field) or "").strip():
            errors.append(f"series_plan.{field} is required")
    try:
        if int(series_plan.get("day_number") or 0) < 1:
            errors.append("series_plan.day_number must be a positive integer")
    except (TypeError, ValueError):
        errors.append("series_plan.day_number must be a positive integer")
    if str(series_plan.get("next_day_title") or "").strip() and normalized_social_title(series_plan.get("today_angle")) == normalized_social_title(
        series_plan.get("next_day_title")
    ):
        errors.append("series_plan.next_day_title must differ from today_angle")

    canonical = normalized_social_title(task.get("title"))
    prior = {
        normalized_social_title(value)
        for value in task.get("prior_social_titles") or []
        if normalized_social_title(value)
    }
    seen: set[str] = set()
    platforms = contract.get("social_platforms") or []
    variants = contract.get("social_variants") or ["A.md", "B.md", "C.md"]
    platform_metadata = metadata.get("platforms")
    if not isinstance(platform_metadata, dict):
        return [*errors, "social metadata.platforms must be an object"]
    for platform in platforms:
        details = platform_metadata.get(platform)
        if not isinstance(details, dict):
            errors.append(f"missing metadata for {platform}")
            continue
        variant_titles = details.get("variant_titles")
        if not isinstance(variant_titles, dict):
            errors.append(f"missing variant_titles for {platform}")
            continue
        for variant in variants:
            title = str(variant_titles.get(variant) or "").strip()
            normalized = normalized_social_title(title)
            if not normalized:
                errors.append(f"missing {platform} title for {variant}")
            elif normalized == canonical:
                errors.append(f"{platform} {variant} title repeats the canonical article title")
            elif normalized in prior:
                errors.append(f"{platform} {variant} title reuses a prior social title")
            elif normalized in seen:
                errors.append(f"duplicate social variant title: {title}")
            seen.add(normalized)
        if normalized_social_title(details.get("title")) != normalized_social_title(
            variant_titles.get("A.md")
        ):
            errors.append(f"{platform} title must match variant_titles.A.md")
        teaser = str(details.get("closing_cta") or details.get("next_day_teaser") or details.get("cta") or "").strip()
        if not teaser and not strict_value and not complementary_components:
            errors.append(f"missing closing CTA for {platform}")
            continue
        markers = (
            ("ngày mai", "đón đọc", "tiếp theo")
            if platform == "facebook_vi"
            else ("tomorrow", "next", "coming")
        )
        if not strict_value and not complementary_components and not any(marker in teaser.casefold() for marker in markers):
            errors.append(f"{platform} next_day_teaser does not lead into tomorrow's content")
        if strict_value and teaser and not task.get("scheduled_followup_exists") and re.search(
            r"\b(tomorrow|check back tomorrow|more tomorrow|stay tuned|i['\u2019]?ll (?:post|share))\b",
            teaser,
            flags=re.I,
        ):
            errors.append(f"{platform} contains an unsupported future promise")
        for variant in variants:
            draft = root / "social" / slug / platform / variant
            if draft.is_file():
                draft_text = draft.read_text(encoding="utf-8").rstrip()
                if teaser and not complementary_components and not draft_text.endswith(teaser):
                    errors.append(f"{platform} {variant} must end with the declared closing CTA")
                if strict_value:
                    public_lines = [line.strip() for line in draft_text.splitlines() if line.strip()]
                    ending = public_lines[-1] if public_lines else ""
                    if re.search(
                        r"^(?:use|check(?: out)?|learn more|try|start|read|visit|follow|click|open|save)\b",
                        ending,
                        flags=re.I,
                    ):
                        errors.append(
                            f"{platform} {variant} generic CTA ending; use an implication, decision question, observation, or source"
                        )
                    if not task.get("scheduled_followup_exists") and re.search(
                        r"\b(?:today|yesterday|tomorrow|this week|act now|breaking|game[ -]?changer)\b",
                        draft_text,
                        flags=re.I,
                    ):
                        errors.append(f"{platform} {variant} contains fake urgency or a stale relative date")
    return errors


def main() -> int:
    root = Path.cwd()
    manifest = load_json(root / "manifest.json")
    queue = load_json(root / "queue.json")
    contract_path = (
        root / "OUTPUT_CONTRACT.json"
        if (root / "OUTPUT_CONTRACT.json").is_file()
        else root / "output_contract.json"
    )
    contract = load_json(contract_path)
    tasks = queue.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        print("ERROR: queue.json must contain at least one task.", file=sys.stderr)
        return 2

    package_id = str(manifest.get("package_id") or "")
    task_type = str(manifest.get("task_type") or "")
    allowed_paths = contract.get("allowed_paths") or []
    if not isinstance(allowed_paths, list):
        print("ERROR: OUTPUT_CONTRACT.json allowed_paths must be a list.", file=sys.stderr)
        return 2

    writer_name = os.environ.get("EXTERNAL_WRITER_NAME", "ChatGPT").strip() or "ChatGPT"
    writer_type = os.environ.get("EXTERNAL_WRITER_TYPE", "external_ai").strip() or "external_ai"
    writer_version = os.environ.get("EXTERNAL_WRITER_VERSION", "web").strip() or "web"
    now = datetime.now(timezone.utc).isoformat()

    errors: list[str] = []
    item_rows: list[dict] = []
    zip_members: list[str] = []
    quality_reports: list[dict] = []
    returned_website_titles: set[str] = set()
    article_specs: dict[str, dict] = {}
    website_contract: dict = {}
    if task_type == "WEBSITE_ADVANCED":
        try:
            spec_payload = load_json(root / "ARTICLE_SPEC.json")
            website_contract = load_json(root / "website_writing_contract.json")
            article_specs = {
                str(row.get("task_id") or ""): row
                for row in spec_payload.get("articles", [])
                if isinstance(row, dict) and str(row.get("task_id") or "")
            }
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"WEBSITE_ADVANCED contract files are missing or invalid: {exc}")

    for task in tasks:
        if not isinstance(task, dict):
            errors.append("Every task must be a JSON object.")
            continue
        slug = str(task.get("article_slug") or task.get("slug") or "")
        row_task_type = str(task.get("task_type") or task_type)
        task_id = str(task.get("task_id") or "")
        revision = int(task.get("revision") or 1)
        targets = task.get("target_output_paths") or []
        if not slug or not task_id:
            errors.append("Task is missing article_slug or task_id.")
            continue
        if not isinstance(targets, list) or not targets:
            errors.append(f"{task_id}: no target_output_paths are declared.")
            continue

        files: dict[str, str] = {}
        for target in targets:
            target = str(target)
            if not is_safe_relative(target):
                errors.append(f"{task_id}: unsafe target path {target!r}.")
                continue
            if not allowed(target, allowed_paths):
                errors.append(f"{task_id}: target path is outside output_contract allowlist: {target}")
                continue
            source = root / Path(*PurePosixPath(target).parts)
            if not source.is_file():
                errors.append(f"{task_id}: missing required output {target}.")
                continue
            if source.suffix.lower() in EXECUTABLE_SUFFIXES:
                errors.append(f"{task_id}: executable output is not allowed: {target}.")
                continue
            files[target] = sha256(source)
            zip_members.append(target)

        asset_root = root / output_root_for(row_task_type, slug) / "assets"
        if asset_root.exists():
            for asset in sorted(path for path in asset_root.rglob("*") if path.is_file()):
                rel = asset.relative_to(root).as_posix()
                if not is_safe_relative(rel):
                    errors.append(f"{task_id}: unsafe asset path {rel!r}.")
                    continue
                if not allowed(rel, allowed_paths):
                    errors.append(f"{task_id}: asset path is outside output_contract allowlist: {rel}")
                    continue
                if asset.suffix.lower() in EXECUTABLE_SUFFIXES:
                    errors.append(f"{task_id}: executable asset is not allowed: {rel}.")
                    continue
                files[rel] = sha256(asset)
                zip_members.append(rel)

        if row_task_type.startswith("WEBSITE_"):
            returned_title, title_errors = website_title_review(root, task)
            for error in title_errors:
                errors.append(f"{task_id}: {error}.")
            if returned_title:
                if returned_title in returned_website_titles:
                    errors.append(f"{task_id}: duplicate website title within package.")
                returned_website_titles.add(returned_title)

        if row_task_type == "WEBSITE_ADVANCED":
            article_path = root / "website" / slug / "article.html"
            spec = article_specs.get(task_id)
            if spec is None:
                errors.append(f"{task_id}: ARTICLE_SPEC.json entry is missing.")
            elif article_path.is_file():
                quality_report = advanced_editorial_review(
                    root,
                    slug,
                    task_id,
                    article_path.read_text(encoding="utf-8"),
                    spec,
                    website_contract,
                )
                quality_reports.append(quality_report)
                for error in quality_report["errors"]:
                    errors.append(f"{task_id}: {error}.")
        elif row_task_type.startswith("SOCIAL_"):
            for error in social_series_review(root, task, contract):
                errors.append(f"{task_id}: {error}.")

        item_rows.append(
            {
                "task_id": task_id,
                "slug": slug,
                "article_slug": slug,
                "task_type": row_task_type,
                "revision": revision,
                "status": "completed_needs_review",
                "output_root": output_root_for(row_task_type, slug),
                "files": files,
            }
        )

    if errors:
        stale_zip = root / "completed_drafts.zip"
        if stale_zip.exists():
            stale_zip.unlink()
        for report in quality_reports:
            print(f"Predicted AI Score: {report['predicted_ai_score']}")
            print(f"Word count: {report['word_count']}")
            print(f"Duplicate score: {report['duplicate_risk']}")
            print(f"Coverage: {report['coverage']}")
            print(f"Missing sections: {report['missing_sections']}")
            print(f"Expected Menu W result: {report['expected_menu_w_result']}")
            if report["generation_attempt"] < 3:
                print(
                    f"Regeneration required: automatically rewrite and self-review attempt "
                    f"{report['generation_attempt'] + 1} of 3."
                )
            else:
                print("Regeneration limit reached: 3 of 3 attempts; ZIP remains blocked.")
        print("completed_drafts.zip was not created because the package is incomplete:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        retryable = bool(quality_reports) and all(
            report["generation_attempt"] < 3 for report in quality_reports
        )
        if retryable:
            (root / "generation_feedback.json").write_text(
                json.dumps(
                    {
                        "status": "REGENERATION_REQUIRED",
                        "next_attempt": max(
                            1,
                            max(report["generation_attempt"] for report in quality_reports) + 1,
                        ),
                        "maximum_attempts": 3,
                        "reports": quality_reports,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            return 3
        feedback_path = root / "generation_feedback.json"
        if feedback_path.exists():
            feedback_path.unlink()
        return 1

    completed_manifest = {
        "schema_version": "universal_external_writer_return_v1",
        "package_id": package_id,
        "task_type": task_type,
        "verified_package_contract": {
            "path": "verified_package_contract.json",
            "sha256": sha256(root / "verified_package_contract.json"),
        },
        "writer": {
            "writer_type": writer_type,
            "writer_name": writer_name,
            "writer_version": writer_version,
            "generated_at": now,
        },
        "writer_type": writer_type,
        "writer_name": writer_name,
        "writer_version": writer_version,
        "generated_at": now,
        "completed_at": now,
        "approval_changed": False,
        "published": False,
        "items": item_rows,
    }

    manifest_path = root / "completed_manifest.json"
    manifest_path.write_text(
        json.dumps(completed_manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    zip_path = root / "completed_drafts.zip"
    feedback_path = root / "generation_feedback.json"
    if feedback_path.exists():
        feedback_path.unlink()
    if zip_path.exists():
        zip_path.unlink()
    unique_members = [
        "completed_manifest.json",
        "verified_package_contract.json",
        *sorted(set(zip_members)),
    ]
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for member in unique_members:
            if not is_safe_relative(member):
                print(f"ERROR: unsafe ZIP member {member!r}.", file=sys.stderr)
                return 2
            if Path(member).suffix.lower() in EXECUTABLE_SUFFIXES:
                print(f"ERROR: executable ZIP member is not allowed: {member}", file=sys.stderr)
                return 2
            archive.write(root / Path(*PurePosixPath(member).parts), member)

    print(f"completed_drafts.zip created: {zip_path}")
    print(f"tasks: {len(item_rows)}")
    print(f"files: {len(unique_members)}")
    for report in quality_reports:
        print(f"Predicted AI Score: {report['predicted_ai_score']}")
        print(f"Word count: {report['word_count']}")
        print(f"Duplicate score: {report['duplicate_risk']}")
        print(f"Coverage: {report['coverage']}")
        print(f"Missing sections: {report['missing_sections']}")
        print(f"Expected Menu W result: {report['expected_menu_w_result']}")
    print("approval_changed: false")
    print("published: false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''

    @staticmethod
    def _source_manifest(tasks: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "tasks": [
                {
                    "task_id": row["task_id"],
                    "primary_source_url": row.get("primary_source_url", ""),
                    "supporting_source_urls": row.get("supporting_source_urls", []),
                    "source_files": row.get("source_files", []),
                    "research_files": row.get("research_files", []),
                    "verified_fact_policy": {
                        "allowed_statuses": [
                            "VERIFIED_OFFICIAL",
                            "VERIFIED_LOCAL_PRODUCTION",
                            "VERIFIED_MULTISOURCE",
                        ],
                        "facts_to_verify_are_claimable": False,
                        "fact_conflicts_are_claimable": False,
                    },
                }
                for row in tasks
            ]
        }

    @staticmethod
    def _task_summary(tasks: list[dict[str, Any]]) -> str:
        lines = ["# External Writer Tasks", ""]
        for index, row in enumerate(tasks, start=1):
            sources = [
                _text(row.get("primary_source_url")),
                *[_text(value) for value in row.get("supporting_source_urls") or []],
            ]
            sources = [value for value in sources if value]
            lines.extend(
                [
                    f"## {index}. {row['title']}",
                    f"- Task ID: `{row['task_id']}`",
                    f"- Type: `{row['task_type']}`",
                    f"- Slug: `{row['article_slug']}`",
                    f"- Root topic: `{row.get('root_topic_id', '')}`",
                    f"- Series: `{row.get('series_id', '')}`",
                    f"- Article type/angle: `{row.get('article_type', '')}`",
                    f"- Goal: {row.get('content_goal', '')}",
                    f"- Reader intent: {row.get('reader_intent', '')}",
                    f"- Search intent: {row.get('search_intent', '')}",
                    f"- Audience: {row.get('audience', '')}",
                    f"- Required sections: {json.dumps(row.get('required_sections') or [], ensure_ascii=False)}",
                    f"- Required tables: {json.dumps(row.get('required_tables') or [], ensure_ascii=False)}",
                    f"- Required FAQ: {json.dumps(row.get('required_faq') or [], ensure_ascii=False)}",
                    f"- Required CTA: {row.get('required_cta', '')}",
                    f"- Internal links: {json.dumps(row.get('internal_link_requirements') or [], ensure_ascii=False)}",
                    f"- Next-article bridge: {json.dumps(row.get('next_article_bridge') or {}, ensure_ascii=False)}",
                    f"- Prior website titles (must not be reused): {json.dumps(row.get('prior_website_titles') or [], ensure_ascii=False)}",
                    f"- Prior social titles (must not be reused): {json.dumps(row.get('prior_social_titles') or [], ensure_ascii=False)}",
                    f"- Prior social batch dates: {json.dumps(row.get('prior_social_batch_dates') or [], ensure_ascii=False)}",
                    f"- Sources ({len(sources)}):",
                    *[f"  - {source}" for source in sources],
                    f"- Research files: {json.dumps(row.get('research_files') or [], ensure_ascii=False)}",
                    *(
                        [
                            "- TASK TYPE: UPDATE EXISTING ARTICLE",
                            "- PRESERVE SLUG: TRUE",
                            "- DO NOT CREATE DUPLICATE ARTICLE",
                            f"- Existing article snapshot: `existing_article/{row['article_slug']}/`",
                            f"- Refresh reason: {json.dumps(row.get('refresh_reason') or [], ensure_ascii=False)}",
                            f"- Refresh scope: {json.dumps(row.get('refresh_scope') or [], ensure_ascii=False)}",
                        ]
                        if row.get("task_type") == "WEBSITE_UPDATE"
                        else []
                    ),
                    "",
                ]
            )
        return "\n".join(lines)

    @staticmethod
    def _website_writing_contract(
        task_type: str,
        tasks: list[dict[str, Any]],
    ) -> dict[str, Any]:
        advanced = task_type == "WEBSITE_ADVANCED"
        return {
            "schema_version": "website_writing_contract_v1",
            "task_type": task_type,
            "editorial_word_count": {
                "minimum": 2200 if advanced else 1900,
                "target": 2400 if advanced else 2250,
                "maximum": 2600,
                "exclude": ["navigation", "footer", "JSON-LD", "metadata"],
            },
            "structure": {
                "h1_exactly": 1,
                "h2_range": [10, 14] if advanced else [8, 14],
                "h3_range": [3, 12],
                "intro_paragraphs": [2, 3],
                "faq_questions": [4, 6],
                "tables": [1, 2],
                "entity_specific_h2_minimum": 4,
            },
            "title_policy": {
                "unique_within_package": True,
                "must_not_reuse_prior_website_title": True,
                "metadata_html_h1_markdown_must_match": True,
                "truncated_trailing_fragment_forbidden": True,
                "preferred_maximum_characters": 60,
                "collision_resolution": (
                    "Preserve the entity and add the assigned angle (review, comparison, pricing, security, "
                    "workflow, FAQ, or case study); never solve a collision by appending a number."
                ),
            },
            "required_advanced_sections": (
                ["pricing", "security", "integrations", "comparison", "faq", "cta"]
                if advanced
                else []
            ),
            "required_research_artifacts": (
                [
                    "FACT_LEDGER.json",
                    "SOURCE_EXCERPTS.json",
                    "sources.json",
                    "outline.json",
                    "writing_plan.json",
                    "faq.json",
                    "competitor_analysis.json",
                    "entities.json",
                    "research_inventory.json",
                ]
                if advanced
                else []
            ),
            "preflight_quality": {
                "required": advanced,
                "minimum_predicted_ai_score": 70,
                "maximum_regeneration_attempts": 3,
                "maximum_duplicate_risk": 35,
            },
            "schema_policy": {
                "json_ld_required": advanced,
            },
            "section_word_budgets": {
                "introduction": [120, 180],
                "quick_verdict": [100, 160],
                "entity_and_reader_fit": [180, 260],
                "method_and_evidence": [140, 220],
                "capabilities_or_angle_analysis": [280, 420],
                "workflow_examples": [250, 380],
                "comparison": [180, 280],
                "pricing_limits": [180, 280],
                "pros_cons": [180, 260],
                "alternatives": [180, 280],
                "risks": [180, 280],
                "buying_checklist": [140, 220],
                "faq_each": [60, 100],
                "final_recommendation": [100, 160],
                "next_article_bridge": [60, 100],
                "disclosure": [35, 70],
            },
            "source_policy": {
                "identity_features_integrations": "official project, product, or documentation source",
                "pricing_limits": "official pricing or official documentation only",
                "market_context_alternatives": "independent supporting source, clearly attributed",
                "unsupported_claim": "omit it or state that it could not be verified",
                "minimum_independent_domains": 2,
                "never_invent_urls": True,
            },
            "image_policy": {
                "allowed_source": "only files supplied under images/<slug>/",
                "preferred_dimensions": "1200x630",
                "preferred_formats": ["webp", "png", "jpg", "jpeg"],
                "filename": "<slug>-hero.<extension>",
                "alt_words": [8, 18],
                "required_attributes": ["src", "alt", "width", "height", "decoding"],
                "missing_behavior": "omit all image references and report required image missing",
                "hotlinking_allowed": False,
            },
            "advanced_differentiation": {
                "required": advanced,
                "read_series_history": advanced,
                "repeat_foundation_summary_words_max": 120,
                "normalized_paragraph_overlap_max_percent": 35,
                "batch_outline_reuse_forbidden": True,
                "unique_angle_table_required": advanced,
                "next_article_bridge_required": True,
            },
            "style_comparator": {
                "mandatory_at_import": False,
                "status": "DEPRECATED_FOR_DRAFT_IMPORT",
                "failure_action": "none",
                "note": (
                    "Menu W validates the output contract only; it does not compare "
                    "articles or revalidate research."
                ),
            },
            "gold_standard_library": {
                "catalog": "gold_library/website/catalog.json",
                "usage": "select the outline matching article_type or daily angle",
                "purpose": "structure, evidence placement, and section-budget reference",
                "copying_forbidden": True,
                "entity_swap_reuse_forbidden": True,
            },
            "tasks": [
                {
                    "task_id": row["task_id"],
                    "slug": row["article_slug"],
                    "root_topic_id": row.get("root_topic_id", ""),
                    "article_type": row.get("article_type", ""),
                    "required_sections": row.get("required_sections", []),
                    "required_tables": row.get("required_tables", []),
                    "next_article_bridge": row.get("next_article_bridge", {}),
                }
                for row in tasks
            ],
        }

    def _prompt_layers(
        self,
        package_id: str,
        task_type: str,
        tasks: list[dict[str, Any]],
    ) -> list[tuple[str, str]]:
        lane_rules = (
            "Write complete website article.html and article.md. The HTML must be a full UTF-8 document "
            "with title, one H1, canonical, valid heading hierarchy, schema, source-backed claims, FAQ, CTA, "
            "internal links, and the supplied next-article bridge. Treat `website_writing_contract.json` as "
            "a binding, machine-readable contract. Build a Private Article Plan before drafting and Enforce "
            "a unique angle-specific title that does not reuse any prior website title in TASK.md. The exact "
            "same public title must appear in metadata.title, HTML title, HTML H1, and Markdown H1. Never "
            "truncate a title mid-word; shorten it by rewriting while preserving the entity and daily angle. "
            "Batch Diversity before returning files. At least four main headings per article must be "
            "entity-specific. Read gold_library/website/catalog.json and the matching annotated outline as "
            "an evidence/structure example only; never copy its wording or reuse one outline across a batch. "
            "Do not reference any /assets/ image URL "
            "unless the exact image file is returned under the matching website/<slug>/assets/ directory. "
            "When no image is supplied, omit image references and report required image missing honestly."
            if task_type.startswith("WEBSITE_")
            else "Write three complementary internal components for every requested platform: A.md = ACTIONABLE, "
            "B.md = INSIGHT, and C.md = PROBLEM_SOLUTION. They must all develop the one shared today_angle; do not "
            "spend or preview a future series angle. Give every component a clear working title; never reuse the canonical article title or any title listed in "
            "TASK.md under prior social titles. Explain what happened, why it matters to the platform audience, and "
            "at least one practical takeaway. Add metadata.series_plan and platform variant_titles exactly as required "
            "by OUTPUT_CONTRACT.json. Render Source with the supplied official_source_name and official_source_url; "
            "never leave Source: blank. A CTA is optional: prefer a story-specific implication, decision question, "
            "operational takeaway, concise observation, or simply the source. Do not use generic Follow/Read/Visit/Try "
            "endings. Do not promise tomorrow or another future post unless TASK.md proves scheduled_followup_exists=true. Facebook "
            "Vietnamese must use natural Vietnamese with full diacritics. Each public draft contains only copy "
            "intended for the platform. These files are source material for the local Platform Composer, not competing "
            "publication choices. Do not concatenate them and do not write or approve FINAL.md externally."
        )
        hot_rule = (
            "\nFor SOCIAL_HOT_NEWS, use only supplied real source URLs, preserve uncertainty and "
            "official_confirmed, and never create a Smile AI Review Hub URL. Do not turn the post into a generic "
            "source-checking disclaimer: use verified material to deliver reader value without inventing pricing, "
            "rollout, performance, integration, availability, or affiliate claims. Clearly separate verified facts, "
            "interpretation, and unknowns. Infer the primary audience and adapt the implication to that audience. "
            "Use exact dates only when timing materially matters; avoid fake urgency and stale relative dates."
            if task_type == "SOCIAL_HOT_NEWS"
            else ""
        )
        system = f"""# System Contract

Package ID: `{package_id}`
Task type: `{task_type}`
Task count: `{len(tasks)}`

Follow `CHATGPT_EXECUTION_ORDER.md` and read numbered files in order.

Use only supplied facts, sources, URLs, task identities, slugs, series context, and
canonical rules. Never invent pricing, features, dates, quotes, tests, experience,
sources, links, or confirmation. Omit or qualify unsupported claims.

Read AFFILIATE_OPPORTUNITY_BRIEF.json when supplied. DO NOT INVENT commission,
cookie duration, pricing, features, affiliate terms, market size, earning potential,
conversion, or performance claims. Every commercial claim must map to supplied
verified evidence; UNKNOWN and unverified values must remain unknown.

All returned content must be UTF-8. Do not include local paths, prompts, notes,
labels, executable code, secrets, or extra files in public draft bodies.

Every returned item starts unapproved. Do not approve, publish, commit, push,
deploy, index, call an API, or claim that any of those actions occurred.
"""
        editorial_dna = self._read_editorial_text(
            "docs/editorial/editorial_brain/EDITORIAL_DNA.md",
            "# Editorial DNA\n\nUse the source-aware, buyer-first project voice.",
        )
        universal = self._read_editorial_text(
            "docs/editorial/UNIVERSAL_WRITING_STANDARD.md",
            "# Universal Writing Standard\n\nUse only supplied evidence.",
        )
        lane_standard = self._read_editorial_text(
            (
                "docs/editorial/WEBSITE_WRITING_STANDARD.md"
                if task_type.startswith("WEBSITE_")
                else "docs/editorial/SOCIAL_WRITING_STANDARD.md"
            ),
            "# Lane Writing Standard\n\nFollow the task output contract.",
        )
        website_playbook = (
            self._read_editorial_text(
                "docs/editorial/CHATGPT_WEBSITE_WRITING_PLAYBOOK.md",
                "# ChatGPT Website Writing Playbook\n\nWrite entity-specific, source-backed content.",
            )
            if task_type.startswith("WEBSITE_")
            else ""
        )
        social_playbook = (
            self._read_editorial_text(
                "docs/editorial/CHATGPT_SOCIAL_WRITING_PLAYBOOK.md",
                "# ChatGPT Social Writing Playbook\n\nWrite platform-native, paste-ready social copy.",
            )
            if not task_type.startswith("WEBSITE_")
            else ""
        )
        platform_rules = self._read_editorial_text(
            "docs/editorial/PLATFORM_STYLE_MATRIX.md",
            "# Platform Rules\n\nUse only platforms declared by the task.",
        )
        article_types = self._read_editorial_text(
            "docs/editorial/ARTICLE_TYPE_MATRIX.md",
            "# Article Type Rules\n\nUse the task-declared article type.",
        )
        memory_files = [
            path.relative_to(self.root / "editorial_memory").as_posix()
            for path in sorted((self.root / "editorial_memory").rglob("*"))
            if path.is_file()
        ] if (self.root / "editorial_memory").exists() else []
        memory = (
            "# Editorial Memory\n\n"
            "Read metadata records under `editorial_memory/`. They are pattern context only; "
            "they do not grant approval and contain no full articles.\n\n"
            + "\n".join(f"- `{name}`" for name in memory_files)
        )
        task_text = self._task_summary(tasks)
        output_contract = self._output_contract(task_type, tasks)
        output_spec = f"""# Output Specification

{lane_rules}{hot_rule}

Return exactly one ZIP named `completed_drafts.zip`. Its root must contain
`completed_manifest.json` and only files allowed by `output_contract.json`.
`completed_manifest.json` uses schema `{RETURN_SCHEMA}` and includes package ID
`{package_id}`, writer identity/version/time, and one item per task with task ID,
revision, output root, and file SHA-256 values. Use this exact writer structure:

```json
{{
  "writer": {{
    "writer_type": "external_ai",
    "writer_name": "ChatGPT",
    "writer_version": "the model or application version",
    "generated_at": "ISO-8601 timestamp"
  }}
}}
```

```json
{json.dumps(output_contract, indent=2, ensure_ascii=False)}
```
"""
        self_review = self._read_editorial_text(
            "docs/editorial/SELF_REVIEW_CHECKLIST.md",
            "# Self Review\n\nValidate output without rewriting or approving.",
        )
        if task_type == "WEBSITE_ADVANCED":
            self_review += """

## Mandatory WEBSITE_ADVANCED generation loop

1. Consume every artifact listed by `website_writing_contract.json.required_research_artifacts`;
   use the research inventory to confirm none were skipped.
2. Draft the complete 2,200-2,600-word article, not only an outline.
3. Check at least 10 H2 sections, pricing, security, integrations, comparison, FAQ,
   affiliate disclosure, internal links, external citations, CTA, entity coverage,
   citation coverage, and required JSON-LD.
4. Reject placeholders, `coming soon`, empty sections, and empty comparison tables.
5. Estimate Menu W AI Review score and duplicate risk.
6. If any check fails or predicted score is below 70, regenerate automatically and
   repeat this review. Stop after at most three total generation attempts.
7. Record the current `generation_attempt` (1-3) in validation.json and add
   `research_utilization.artifacts` listing every consumed filename from
   `website_writing_contract.json.required_research_artifacts`, plus
   `research_utilization.used_claim_ids` and `research_utilization.citation_urls`.
   Claim IDs must exist in FACT_LEDGER.json and every declared citation must appear
   in the article.
8. Run `python CREATE_COMPLETED_DRAFTS.py` only on a passing attempt. The helper is
   authoritative and will refuse to create the ZIP when the article is under spec.
   Exit code 3 plus generation_feedback.json means regenerate automatically using
   the reported failures, increment generation_attempt, and rerun the helper. Exit
   code 1 after attempt 3 is terminal and must not be bypassed.
"""
        elif task_type.startswith("SOCIAL_"):
            self_review += """

## Mandatory social-series self-review

1. Treat the source article as the pillar of a topical-authority series, not as a title to repost daily.
2. Declare `metadata.series_plan` with the pillar, current day number, and today's distinct angle.
3. For each platform, write A.md as ACTIONABLE, B.md as INSIGHT, and C.md as PROBLEM_SOLUTION.
   All three components must use the same `series_plan.today_angle`; they are not competing variants.
4. Include what happened, why it matters, a practical takeaway, and visible official-source attribution.
5. Never leave `Source:` blank and never promise future content without a linked scheduled follow-up task.
6. Do not reuse the canonical article title or any prior title listed in TASK.md.
7. A CTA is optional. If used, it must be story-specific and non-mechanical. Otherwise end with an implication,
   decision question, operational takeaway, concise observation, or the official source.
8. Confirm Dev.to, Blogger, Quora, and Pinterest components are platform-native. The local Platform Composer
   will synthesize the single final post; never concatenate A+B+C.
9. For Pinterest, use an angle-specific pin title plus a subhead, 2-4 verified points, and source indicator.
10. For SOCIAL_HOT_NEWS, reject fake urgency, stale relative dates, generic CTAs, unsupported commercial language,
    excessive hashtags, and copied cross-platform wording. Zero hashtags is acceptable.
11. Run CREATE_COMPLETED_DRAFTS.py. It must refuse duplicate titles, blank source rendering, low-value copy,
    unsupported visual claims, unsupported future promises, or generic CTA endings.
"""
        return [
            ("01_SYSTEM.md", system),
            ("02_EDITORIAL_DNA.md", editorial_dna),
            (
                "03_WRITING_STANDARD.md",
                f"{universal}\n\n---\n\n{lane_standard}"
                + (f"\n\n---\n\n{website_playbook}" if website_playbook else "")
                + (f"\n\n---\n\n{social_playbook}" if social_playbook else ""),
            ),
            ("04_PLATFORM_RULES.md", platform_rules),
            ("05_ARTICLE_TYPE.md", article_types),
            ("06_EDITORIAL_MEMORY.md", memory),
            ("07_TASK.md", task_text),
            ("08_OUTPUT_SPEC.md", output_spec),
            ("09_SELF_REVIEW.md", self_review),
        ]

    def _read_editorial_text(self, raw: str, fallback: str) -> str:
        path = self.root / raw
        if not path.is_file():
            return fallback
        return path.read_text(encoding="utf-8")

    @staticmethod
    def _assembled_prompt(layers: list[tuple[str, str]]) -> str:
        sections = ["# Universal External Writer Prompt", ""]
        for name, content in layers:
            sections.extend([f"<!-- BEGIN {name} -->", content.strip(), f"<!-- END {name} -->", ""])
        return "\n".join(sections).rstrip() + "\n"

    @staticmethod
    def _validation_rules(task_type: str) -> str:
        common = """# Validation Rules

- Match every task ID, slug, package ID, and revision exactly.
- UTF-8 only; no BOM requirement is imposed.
- Use only source URLs supplied for that task.
- No fake source, website, canonical, quote, pricing, feature, result, or experience.
- No executable, script, credential, token, secret, local path, or prompt artifact.
- Returned status is unapproved and requires human review.
"""
        if task_type.startswith("WEBSITE_"):
            return common + """
- article.html is a full document with `<meta charset="utf-8">`, title, exactly one H1, and canonical.
- article.md and article.html contain the same article, without workflow markers.
- Metadata records writer identity, package_id, task_id, revision, title, slug, and source URLs.
- The title is unique within the package and website history, and does not reuse a prior website title
  listed in TASK.md. metadata.title, HTML title, HTML H1, and Markdown H1 must match.
- Never truncate a title mid-word or leave a trailing fragment merely to meet a character limit; rewrite it
  to preserve both the entity and the article's distinct angle.
- Validation report must not claim approval or publication.
- Follow `website_writing_contract.json`; count editorial body words only.
- Foundation articles contain 1,900-2,600 editorial words; advanced articles contain 2,200-2,600.
- Advanced articles use at least 10 H2 headings. All website articles use 3-12 H3 headings,
  complete FAQ answers, and 1-2 responsive, non-empty tables.
- At least four H2 headings must be specific to the exact entity and assigned article angle.
- Map identity/features to official sources; map pricing to official pricing/docs only.
- Use an independent source only for attributed market context or alternatives.
- Every required section in TASK.md must contain substantive evidence-backed content.
- Advanced articles must read supplied series_history, use a new angle-specific outline and table,
  summarize prior coverage in no more than 120 words, and include the supplied next-article bridge.
- Normalized paragraph overlap with another returned article or prior same-root article must stay at
  or below 35 percent. Replacing only the entity name does not create a different article.
- Use only supplied image files. Never hotlink or invent an image. If none exists, omit image markup
  and report `required image missing` for the existing image pipeline.
- Self-score structure, heading specificity, tone, CTA, FAQ, SEO, source discipline,
  differentiation, series continuity, entity coverage, citation coverage, and output-contract
  compliance. Predict the Menu W AI Review score; it must be at least 70.
- WEBSITE_ADVANCED must consume FACT_LEDGER.json, SOURCE_EXCERPTS.json, sources.json,
  outline.json, writing_plan.json, faq.json, competitor_analysis.json, entities.json, and
  research_inventory.json. Do not stop after producing an outline.
- WEBSITE_ADVANCED must contain substantive pricing, security, integrations, comparison, FAQ,
  affiliate disclosure, internal links, external citations, CTA, and required JSON-LD sections.
- Never return placeholders, `coming soon`, empty sections, or an empty comparison table.
- Run the private self-review and regenerate automatically when it fails, for at most three
  generation attempts. CREATE_COMPLETED_DRAFTS.py is the final deterministic gate.
"""
        return common + """
- Every platform has non-empty A.md, B.md, and C.md complementary components.
- A.md is ACTIONABLE, B.md is INSIGHT, and C.md is PROBLEM_SOLUTION. They share one today angle and do not consume future angles.
- metadata.json declares `series_plan` using `social_editorial_series_v1`, including the pillar,
  current day number, and today's distinct angle.
- Every platform declares unique `variant_titles` for A.md, B.md, and C.md. No variant title may
  equal the canonical article title, duplicate another returned title, or reuse a prior title from TASK.md.
- CTA is optional. If metadata declares one, it must be story-specific and match the draft. A draft may instead
  end with an implication, decision question, operational takeaway, concise observation, or official source.
- Generic CTA, fake urgency, stale relative dates, unsupported promotional/affiliate/pricing language, and
  excessive hashtags are reported with actionable reasons. Zero hashtags is acceptable.
- Dev.to, Blogger, Quora, and Pinterest public titles follow the selected variant angle. Pinterest
  overlay/title copy must not repeat the pillar article H1.
- Facebook Vietnamese uses full Vietnamese diacritics.
- X components comply with the configured short-post limit; the local composer also enforces one final post at or below 280 characters with no thread.
- Hot news uses real discovery/official URLs and no fabricated Smile AI Review Hub URL.
- Hot news renders the official source name and URL (Pinterest keeps its destination URL separate),
  provides useful context and a practical takeaway, and is not merely a compliance reminder.
"""


class UniversalExternalWriterImporter:
    def __init__(self, *, root: Path) -> None:
        self.root = root
        self.data_dir = root / "data"
        self.queue = UniversalWriteQueue(root=root)
        self.history_root = self.data_dir / "import_history" / "external_writer"
        self.returned_root = root / "exports" / "external_writer" / "returned"
        self.archived_root = root / "exports" / "external_writer" / "Archived"
        self.rejected_root = root / "exports" / "external_writer" / "Rejected"
        self.duplicate_root = root / "exports" / "external_writer" / "Duplicate"
        self.lifecycle_root = self.history_root / "file_lifecycle"

    def _return_discovery(self) -> ExternalWriterReturnDiscovery:
        return ExternalWriterReturnDiscovery(
            root=self.root,
            queue=self.queue,
            validate_zip=self.validate_zip,
            validate_archive_members=self._validate_archive_members,
            read_zip_json=self._read_zip_json,
            normalize_completed_manifest=self._normalize_completed_manifest,
            immutable_website_states=IMMUTABLE_WEBSITE_STATES,
            protected_website_states=PROTECTED_WEBSITE_STATES,
            is_website_revision=_is_website_revision,
        )

    def discover(self, *, explicit: str = "") -> list[ImportCandidate]:
        return self._return_discovery().discover(
            explicit=explicit,
            inspect_candidate=self.inspect_candidate,
        )

    def audit_returned(self) -> list[ImportCandidate]:
        return self._return_discovery().audit_returned(inspect_candidate=self.inspect_candidate)

    def _successful_import_index(self) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
        return self._return_discovery().successful_import_index()

    def _manifest_identity(self, source: Path) -> tuple[str, str, str]:
        return self._return_discovery().manifest_identity(source)

    def _protected_manifest_states(self, source: Path) -> list[dict[str, Any]]:
        return self._return_discovery().protected_manifest_states(source)

    def inspect_candidate(self, source: Path) -> ImportCandidate:
        return self._return_discovery().inspect_candidate(
            source,
            manifest_identity=self._manifest_identity,
            successful_import_index=self._successful_import_index,
            protected_manifest_states=self._protected_manifest_states,
        )

    def _lifecycle_path(self, checksum: str) -> Path:
        return self.lifecycle_root / f"{checksum}.json"

    def _write_lifecycle(self, checksum: str, payload: dict[str, Any]) -> Path:
        path = self._lifecycle_path(checksum)
        existing = _read_json(path, {})
        sources = list(existing.get("source_filenames", [])) if isinstance(existing, dict) else []
        filename = _text(payload.get("source_filename"))
        if filename and filename not in sources:
            sources.append(filename)
        merged = {**existing, **payload, "source_filenames": sources, "updated_at": _now()}
        _write_json(path, merged)
        return path

    @staticmethod
    def _safe_move_destination(folder: Path, source: Path, checksum: str) -> Path:
        candidate = folder / source.name
        if not candidate.exists():
            return candidate
        stamp = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
        return folder / f"{source.stem}_{stamp}_{checksum[:8]}{source.suffix}"

    def _move_with_audit(
        self,
        candidate: ImportCandidate,
        folder: Path,
        payload: dict[str, Any],
        *,
        rejected_sidecar: bool = False,
    ) -> dict[str, Any]:
        folder.mkdir(parents=True, exist_ok=True)
        lifecycle_path = self._write_lifecycle(candidate.checksum, payload)
        destination = self._safe_move_destination(folder, candidate.path, candidate.checksum)
        try:
            candidate.path.replace(destination)
        except OSError as exc:
            self._write_lifecycle(candidate.checksum, {**payload, "move_error": str(exc)})
            return {
                **payload,
                "status": f"{payload['status']}_MOVE_FAILED",
                "source_preserved": candidate.path.exists(),
                "move_error": str(exc),
                "lifecycle_path": str(lifecycle_path),
            }
        completed = {
            **payload,
            "destination_path": str(destination),
            "moved_at": _now(),
            "move_error": "",
        }
        self._write_lifecycle(candidate.checksum, completed)
        if rejected_sidecar:
            _write_json(Path(str(destination) + ".audit.json"), completed)
        return {**completed, "lifecycle_path": str(lifecycle_path)}

    def process_returned_zip(self, source: Path) -> dict[str, Any]:
        """Preflight, import at most once, then move without deleting any ZIP."""
        candidate = self.inspect_candidate(source)
        base = {
            "schema_version": "external_writer_zip_lifecycle_v1",
            "source_filename": candidate.path.name,
            "source_path": str(candidate.path),
            "zip_sha256": candidate.checksum,
            "package_id": candidate.package_id,
            "lane": candidate.lane,
            "approval_changed": False,
            "published": False,
            "imported": [],
            "skipped": [],
            "rejected": [],
        }
        if candidate.status == "ARCHIVE_PENDING":
            return self._move_with_audit(
                candidate, self.archived_root, {**base, "status": "IMPORTED", "import_result": "IMPORTED"}
            )
        if candidate.status == "DUPLICATE":
            return self._move_with_audit(
                candidate,
                self.duplicate_root,
                {
                    **base,
                    "status": "DUPLICATE_SKIPPED",
                    "import_result": "SKIPPED",
                    "reason": candidate.reason,
                    "skipped": [candidate.reason],
                },
            )
        if candidate.status == "STALE_PROTECTED":
            return self._move_with_audit(
                candidate,
                self.duplicate_root,
                {
                    **base,
                    "status": "PROTECTED_STATE_SKIPPED",
                    "import_result": "SKIPPED",
                    "reason": candidate.reason,
                    "skipped": [candidate.reason],
                },
            )
        if candidate.status == "INVALID":
            return self._move_with_audit(
                candidate,
                self.rejected_root,
                {
                    **base,
                    "status": "FAILED_VALIDATION",
                    "import_result": "NOT_RUN",
                    "reason": candidate.reason,
                    "rejected": [{"task_id": "", "reason": candidate.reason}],
                },
                rejected_sidecar=True,
            )
        result = self.import_zip(candidate.path)
        if result.get("status") != "IMPORTED" or result.get("rejected"):
            reasons = [
                _text(row.get("reason")) for row in result.get("rejected", []) if isinstance(row, dict)
            ]
            return self._move_with_audit(
                candidate,
                self.rejected_root,
                {
                    **base,
                    "status": "FAILED_IMPORT",
                    "import_result": _text(result.get("status")) or "FAILED_IMPORT",
                    "reason": "; ".join(filter(None, reasons)) or "Import failed after validation.",
                    "import_history_path": _text(result.get("history_path")),
                },
                rejected_sidecar=True,
            )
        moved = self._move_with_audit(
            candidate,
            self.archived_root,
            {
                **base,
                "status": "IMPORTED",
                "import_result": "IMPORTED",
                "imported_at": _text(result.get("imported_at")) or _now(),
                "import_history_path": _text(result.get("history_path")),
                "imported": result.get("imported", []),
                "skipped": result.get("skipped", []),
                "rejected": result.get("rejected", []),
            },
        )
        return {**result, **moved}

    def reconcile_returned(self) -> list[dict[str, Any]]:
        """Move only precisely classified non-pending ZIPs out of Returned."""
        results: list[dict[str, Any]] = []
        for candidate in self.audit_returned():
            if candidate.status != "PENDING":
                results.append(self.process_returned_zip(candidate.path))
        return results

    def archive_report(self, *, older_than_days: int = 30) -> dict[str, Any]:
        cutoff = datetime.now(tz=UTC).timestamp() - max(0, older_than_days) * 86400
        files = [
            path for path in self.archived_root.glob("completed_drafts*.zip")
            if path.is_file() and path.stat().st_mtime < cutoff
        ] if self.archived_root.exists() else []
        return {
            "schema_version": "external_writer_archive_report_v1",
            "read_only": True,
            "older_than_days": older_than_days,
            "file_count": len(files),
            "total_bytes": sum(path.stat().st_size for path in files),
            "files": [str(path) for path in sorted(files)],
            "deleted": False,
        }

    def import_zip(self, zip_path: Path, *, dry_run: bool = False) -> dict[str, Any]:
        source = zip_path.resolve()
        if not source.is_file():
            raise FileNotFoundError(f"ZIP not found: {source}")
        checksum = _sha256(source)
        package_id = f"invalid-{checksum[:12]}"
        try:
            with zipfile.ZipFile(source) as archive:
                members = self._validate_archive_members(archive)
                manifest = self._read_zip_json(archive, "completed_manifest.json")
                manifest = self._normalize_completed_manifest(manifest, archive)
                self._validate_completed_manifest(manifest)
                package_id = _text(manifest.get("package_id"))
                history_dir = self.history_root / datetime.now().date().isoformat() / package_id
                history_path = history_dir / "import.json"
                previous = _read_json(history_path, {})
                if previous.get("zip_sha256") == checksum and previous.get("status") == "IMPORTED":
                    return {
                        "status": "UNCHANGED",
                        "package_id": package_id,
                        "zip_sha256": checksum,
                        "imported": [],
                        "skipped": ["same package checksum already imported"],
                        "rejected": [],
                        "history_path": str(history_path),
                    }
                staging_root = self.root / "artifacts" / "external_writer" / "staging"
                staging_root.mkdir(parents=True, exist_ok=True)
                with tempfile.TemporaryDirectory(prefix=f"{package_id}-", dir=staging_root) as temp:
                    extracted = Path(temp)
                    archive.extractall(extracted, members)
                    try:
                        result = self._import_extracted(
                            extracted,
                            manifest,
                            checksum,
                            dry_run=dry_run,
                        )
                    except (ValueError, OSError, UnicodeError, json.JSONDecodeError) as exc:
                        result = self._failed_result(package_id, checksum, str(exc))
        except (ValueError, zipfile.BadZipFile, UnicodeError, json.JSONDecodeError) as exc:
            result = self._failed_result(package_id, checksum, str(exc))
        if dry_run:
            result["status"] = (
                "VALIDATION_PASS" if not result["rejected"] else "FAILED_VALIDATION"
            )
            result["validation_only"] = True
            return result
        history_dir = self.history_root / datetime.now().date().isoformat() / package_id
        history_path = history_dir / "import.json"
        history_dir.mkdir(parents=True, exist_ok=True)
        _write_json(history_path, result)
        result["history_path"] = str(history_path)
        if result["rejected"]:
            quarantine = history_dir / "quarantine"
            quarantine.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, quarantine / source.name)
        return result

    def validate_zip(
        self,
        zip_path: Path,
        *,
        verified_package: Path | None = None,
    ) -> dict[str, Any]:
        result = self.import_zip(zip_path, dry_run=True)
        if verified_package is None:
            return result
        package_result = validate_verified_package(verified_package)
        if not package_result.valid:
            result["rejected"].append(
                {
                    "task_id": "",
                    "reason": "Verified package failed validation.",
                    "rule_id": "VERIFIED_PACKAGE_INVALID",
                    "severity": "BLOCKER",
                    "details": list(package_result.errors),
                }
            )
        else:
            try:
                with zipfile.ZipFile(verified_package) as archive:
                    package_manifest = self._read_zip_json(archive, "manifest.json")
                expected_package_id = _text(package_manifest.get("package_id"))
                if expected_package_id != _text(result.get("package_id")):
                    result["rejected"].append(
                        {
                            "task_id": "",
                            "reason": "Returned ZIP package_id does not match verified package.",
                            "rule_id": "IMMUTABLE_PACKAGE_ID_MISMATCH",
                            "severity": "BLOCKER",
                            "expected": expected_package_id,
                            "actual": _text(result.get("package_id")),
                        }
                    )
            except (OSError, ValueError, zipfile.BadZipFile) as exc:
                result["rejected"].append(
                    {
                        "task_id": "",
                        "reason": f"Unable to inspect verified package: {exc}",
                        "rule_id": "VERIFIED_PACKAGE_READ_ERROR",
                        "severity": "BLOCKER",
                    }
                )
        result["status"] = (
            "VALIDATION_PASS" if not result["rejected"] else "FAILED_VALIDATION"
        )
        result["verified_package"] = str(verified_package.resolve())
        return result

    def stage_completed_zip(
        self,
        zip_path: Path,
        *,
        verified_package: Path | None = None,
    ) -> dict[str, Any]:
        """Validate and atomically place one return ZIP in Menu W's inbox.

        This operation never imports drafts and never changes approval or publish
        state.  It exists to prevent valid writer returns from being saved in a
        folder that Menu W does not scan.
        """
        source = zip_path.resolve()
        if not source.is_file():
            raise FileNotFoundError(f"ZIP not found: {source}")
        validation = self.validate_zip(source, verified_package=verified_package)
        if validation.get("status") != "VALIDATION_PASS":
            return {
                **validation,
                "status": "FAILED_VALIDATION",
                "staged": False,
                "destination_path": "",
                "approval_changed": False,
                "published": False,
            }

        checksum = _sha256(source)
        package_id = _text(validation.get("package_id"))
        safe_package_id = re.sub(r"[^A-Za-z0-9._-]+", "-", package_id).strip(".-")
        if not safe_package_id:
            safe_package_id = checksum[:16]
        self.returned_root.mkdir(parents=True, exist_ok=True)
        destination = self.returned_root / f"completed_drafts-{safe_package_id}.zip"
        if destination.exists():
            existing_checksum = _sha256(destination)
            if existing_checksum == checksum:
                return {
                    **validation,
                    "status": "ALREADY_STAGED",
                    "staged": True,
                    "destination_path": str(destination),
                    "approval_changed": False,
                    "published": False,
                }
            return {
                **validation,
                "status": "STAGING_CONFLICT",
                "staged": False,
                "destination_path": str(destination),
                "reason": (
                    "A different pending ZIP for this package already exists in Returned. "
                    "Process or reconcile it with Menu W before staging a replacement."
                ),
                "approval_changed": False,
                "published": False,
            }

        temporary = destination.with_name(f".{destination.name}.{os.getpid()}.tmp")
        try:
            shutil.copy2(source, temporary)
            if _sha256(temporary) != checksum:
                raise OSError("Staged ZIP checksum does not match source ZIP.")
            os.replace(temporary, destination)
        finally:
            if temporary.exists():
                temporary.unlink()
        return {
            **validation,
            "status": "STAGED",
            "staged": True,
            "source_path": str(source),
            "destination_path": str(destination),
            "zip_sha256": checksum,
            "approval_changed": False,
            "published": False,
        }

    @staticmethod
    def _failed_result(package_id: str, checksum: str, reason: str) -> dict[str, Any]:
        return {
            "schema_version": RETURN_SCHEMA,
            "status": "FAILED_IMPORT",
            "package_id": package_id,
            "zip_sha256": checksum,
            "imported_at": _now(),
            "writer": {},
            "imported": [],
            "skipped": [],
            "rejected": [{"task_id": "", "reason": reason}],
            "approval_changed": False,
            "published": False,
        }

    def _validate_archive_members(self, archive: zipfile.ZipFile) -> list[zipfile.ZipInfo]:
        infos = archive.infolist()
        if len(infos) > 500:
            raise ValueError("ZIP contains too many files.")
        total = 0
        allowed: list[zipfile.ZipInfo] = []
        for info in infos:
            name = info.filename.replace("\\", "/")
            path = PurePosixPath(name)
            if path.is_absolute() or ".." in path.parts or not path.parts:
                raise ValueError(f"Unsafe ZIP path: {name}")
            suffix = Path(path.name).suffix.lower()
            if suffix in EXECUTABLE_SUFFIXES:
                raise ValueError(f"Executable/script file is not allowed: {name}")
            if path.name == ".env" or SECRET_NAME_RE.search(path.name):
                raise ValueError(f"Potential secret file is not allowed: {name}")
            total += info.file_size
            if info.file_size > 20 * 1024 * 1024 or total > 100 * 1024 * 1024:
                raise ValueError("ZIP exceeds safe extraction size.")
            allowed.append(info)
        names = {info.filename.replace("\\", "/") for info in infos if not info.is_dir()}
        if "completed_manifest.json" not in names:
            raise ValueError("completed_manifest.json is required at the ZIP root.")
        return allowed

    @staticmethod
    def _read_zip_json(archive: zipfile.ZipFile, name: str) -> dict[str, Any]:
        try:
            value = json.loads(archive.read(name).decode("utf-8"))
        except (KeyError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"Invalid {name}: {exc}") from exc
        if not isinstance(value, dict):
            raise ValueError(f"{name} must contain a JSON object.")
        return value

    def _normalize_completed_manifest(
        self,
        manifest: dict[str, Any],
        archive: zipfile.ZipFile,
    ) -> dict[str, Any]:
        normalized = dict(manifest)
        if normalized.get("schema_version") == "universal_external_writer_completed_manifest_v1":
            normalized["schema_version"] = RETURN_SCHEMA
            if not isinstance(normalized.get("items"), list) and isinstance(
                normalized.get("tasks"), list
            ):
                normalized["items"] = [
                    self._normalize_legacy_completed_task(item, archive)
                    for item in normalized["tasks"]
                    if isinstance(item, dict)
                ]
        return self._normalize_writer_fields(normalized)

    @staticmethod
    def _normalize_legacy_completed_task(
        item: dict[str, Any],
        archive: zipfile.ZipFile,
    ) -> dict[str, Any]:
        raw_files = item.get("files")
        files: dict[str, str] = {}
        if isinstance(raw_files, dict):
            files = {
                PurePosixPath(_text(path).replace("\\", "/")).as_posix(): _text(checksum)
                for path, checksum in raw_files.items()
            }
        elif isinstance(raw_files, list):
            for raw in raw_files:
                path = PurePosixPath(_text(raw).replace("\\", "/")).as_posix()
                if not path:
                    continue
                try:
                    payload = archive.read(path)
                except KeyError as exc:
                    raise ValueError(f"Declared file is missing from ZIP: {path}") from exc
                files[path] = hashlib.sha256(payload).hexdigest()

        slug = _text(item.get("slug") or item.get("article_slug"))
        output_root = _text(item.get("output_root")).strip("/")
        if not output_root and slug:
            first_file = next(iter(files), "")
            root_name = PurePosixPath(first_file).parts[0] if first_file else "website"
            if root_name not in {"website", "social"}:
                root_name = "website"
            output_root = f"{root_name}/{slug}"

        return {
            "task_id": _text(item.get("task_id")),
            "revision": int(item.get("revision") or 1),
            "output_root": output_root,
            "files": files,
        }

    @staticmethod
    def _normalize_writer_fields(manifest: dict[str, Any]) -> dict[str, Any]:
        writer = manifest.get("writer")
        if writer is None:
            return manifest
        normalized = dict(manifest)
        if isinstance(writer, str):
            writer_name = _text(writer)
            if not writer_name:
                raise ValueError("writer_name is required.")
            writer = {
                "writer_type": _text(manifest.get("writer_type") or "external_ai"),
                "writer_name": writer_name,
                "writer_version": _text(manifest.get("writer_version")),
                "generated_at": _text(
                    manifest.get("generated_at") or manifest.get("completed_at") or _now()
                ),
            }
            normalized["writer"] = writer
        if not isinstance(writer, dict):
            raise ValueError("writer must be a JSON object.")

        for field in ("writer_type", "writer_name", "writer_version", "generated_at"):
            flat_value = _text(manifest.get(field))
            nested_value = _text(writer.get(field))
            if flat_value and nested_value and flat_value != nested_value:
                raise ValueError(f"Conflicting writer identity field: {field}.")
            if not flat_value and nested_value:
                normalized[field] = nested_value
        return normalized

    def _validate_completed_manifest(self, manifest: dict[str, Any]) -> None:
        if manifest.get("schema_version") != RETURN_SCHEMA:
            raise ValueError(f"schema_version must be {RETURN_SCHEMA}.")
        if not _text(manifest.get("package_id")):
            raise ValueError("package_id is required.")
        if not isinstance(manifest.get("items"), list) or not manifest["items"]:
            raise ValueError("completed_manifest.items must be a non-empty list.")
        if not _text(manifest.get("writer_name")):
            raise ValueError("writer_name is required.")

    def _import_extracted(
        self,
        extracted: Path,
        manifest: dict[str, Any],
        checksum: str,
        *,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        imported: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []
        rejected: list[dict[str, Any]] = []
        package_id = _text(manifest["package_id"])
        declared_all = {"completed_manifest.json"}
        standalone_tasks: dict[str, dict[str, Any]] = {}
        website_contract: dict[str, Any] = {}
        article_specs: dict[str, dict[str, Any]] = {}
        contract_info = manifest.get("verified_package_contract")
        contract_path = extracted / "verified_package_contract.json"
        if contract_path.is_file():
            if not isinstance(contract_info, dict):
                raise ValueError(
                    "completed_manifest must declare verified_package_contract."
                )
            expected_hash = _text(contract_info.get("sha256")).lower()
            if not expected_hash or _sha256(contract_path) != expected_hash:
                raise ValueError("verified_package_contract checksum mismatch.")
            contract = _read_json(contract_path, {})
            if contract.get("schema_version") != CONTRACT_SCHEMA:
                raise ValueError(
                    f"verified_package_contract schema must be {CONTRACT_SCHEMA}."
                )
            if _text(contract.get("package_id")) != package_id:
                raise ValueError("verified_package_contract package_id mismatch.")
            standalone_tasks = {
                _text(row.get("task_id")): row
                for row in contract.get("tasks", [])
                if isinstance(row, dict) and _text(row.get("task_id"))
            }
            if not standalone_tasks:
                raise ValueError("verified_package_contract contains no tasks.")
            website_contract = (
                contract.get("website_writing_contract")
                if isinstance(contract.get("website_writing_contract"), dict)
                else {}
            )
            article_specs = {
                _text(row.get("task_id")): row
                for row in contract.get("article_specs", [])
                if isinstance(row, dict) and _text(row.get("task_id"))
            }
            declared_all.add("verified_package_contract.json")
        for item in manifest["items"]:
            if isinstance(item, dict) and isinstance(item.get("files"), dict):
                declared_all.update(
                    PurePosixPath(_text(path).replace("\\", "/")).as_posix()
                    for path in item["files"].keys()
                )
        actual_all = {
            path.relative_to(extracted).as_posix()
            for path in extracted.rglob("*")
            if path.is_file()
        }
        unexpected = sorted(actual_all - declared_all)
        if unexpected:
            raise ValueError(f"ZIP contains files outside completed_manifest: {unexpected}")

        prepared: list[tuple[dict[str, Any], dict[str, Any], str]] = []
        returned_website_titles: set[str] = set()
        for item in manifest["items"]:
            if not isinstance(item, dict):
                rejected.append({"task_id": "", "reason": "manifest item must be an object"})
                continue
            task_id = _text(item.get("task_id"))
            source_task = standalone_tasks.get(task_id) or self.queue.get(task_id)
            task = dict(source_task) if isinstance(source_task, dict) else None
            try:
                if task is None:
                    raise ValueError(f"Unknown task_id: {task_id}")
                if not standalone_tasks and _text(task.get("package_id")) != package_id:
                    raise ValueError(f"Task {task_id} was not exported in package {package_id}.")
                revision = int(item.get("revision") or 0)
                if revision != int(task.get("revision") or 1):
                    raise ValueError(f"Revision mismatch for {task_id}.")
                root_name = "website" if task["task_type"].startswith("WEBSITE_") else "social"
                expected_root = f"{root_name}/{task['article_slug']}"
                if _text(item.get("output_root")).strip("/") != expected_root:
                    raise ValueError(f"output_root must be {expected_root}.")
                self._validate_returned_paths(extracted, item, task, expected_root)
                self._verify_declared_checksums(extracted, item, expected_root)
                task["_article_spec"] = (
                    article_specs.get(task_id)
                    or (task.get("blueprint") if isinstance(task.get("blueprint"), dict) else {})
                )
                task["_website_writing_contract"] = website_contract
                if root_name == "website":
                    self._import_website(
                        extracted / expected_root,
                        task,
                        manifest,
                        dry_run=True,
                    )
                    returned_metadata = _read_json(
                        extracted / expected_root / "metadata.json", {}
                    )
                    returned_title = _normalized_website_title(
                        returned_metadata.get("title")
                    )
                    if returned_title in returned_website_titles:
                        raise ValueError(
                            "Duplicate website title within returned package: "
                            f"{_text(returned_metadata.get('title'))}"
                        )
                    returned_website_titles.add(returned_title)
                else:
                    self._import_social(
                        extracted / expected_root,
                        task,
                        manifest,
                        dry_run=True,
                    )
                prepared.append((item, task, expected_root))
            except (ValueError, OSError, UnicodeError, json.JSONDecodeError) as exc:
                validation_errors = getattr(exc, "errors", None)
                if isinstance(exc, PublicOutputValidationError) or (
                    isinstance(validation_errors, list) and validation_errors
                ):
                    first = dict(exc.errors[0])
                    rejected.append(
                        {
                            **first,
                            "reason": str(exc),
                            "validation_errors": exc.errors,
                        }
                    )
                else:
                    rejected.append({"task_id": task_id, "reason": str(exc)})

        if rejected:
            if not dry_run:
                for _item, task, _expected_root in prepared:
                    task_id = _text(task.get("task_id"))
                    if self.queue.get(task_id) is not None:
                        self.queue.transition(
                            task_id,
                            "FAILED_IMPORT",
                            last_import_error="Package preflight failed; no tasks were imported.",
                        )
            prepared = []
        else:
            for _item, task, expected_root in prepared:
                root_name = expected_root.split("/", 1)[0]
                if root_name == "website":
                    row = self._import_website(
                        extracted / expected_root,
                        task,
                        manifest,
                        dry_run=dry_run,
                    )
                else:
                    row = self._import_social(
                        extracted / expected_root,
                        task,
                        manifest,
                        dry_run=dry_run,
                    )
                imported.append(row)
        status = "IMPORTED" if imported and not rejected else ("PARTIAL" if imported else "FAILED_IMPORT")
        memory_advisories: list[dict[str, Any]] = []
        if feature_enabled(self.root, "editorial_memory.enabled"):
            try:
                memory = EditorialMemoryStore(root=self.root)
                for _item, task, expected_root in prepared:
                    metadata = _read_json(extracted / expected_root / "metadata.json", {})
                    candidate = {
                        "slug": task.get("article_slug"),
                        "title": metadata.get("title") or task.get("title"),
                        "root_topic": task.get("root_topic_id"),
                        "angle": task.get("daily_angle") or task.get("angle"),
                        "keyword": metadata.get("primary_keyword") or task.get("primary_keyword"),
                        "entities": metadata.get("entities") or [],
                        "claims": metadata.get("claims") or [],
                        "cited_sources": metadata.get("cited_sources") or metadata.get("verified_sources") or [],
                    }
                    memory_advisories.append({"task_id": task.get("task_id"), **memory.detect_duplicates(candidate)})
            except (OSError, ValueError, sqlite3.Error):
                memory_advisories = []
        result = {
            "schema_version": RETURN_SCHEMA,
            "status": status,
            "package_id": package_id,
            "zip_sha256": checksum,
            "imported_at": _now(),
            "writer": {
                "writer_type": _text(manifest.get("writer_type") or "external"),
                "writer_name": _text(manifest.get("writer_name")),
                "writer_version": _text(manifest.get("writer_version")),
            },
            "imported": imported,
            "skipped": skipped,
            "rejected": rejected,
            "approval_changed": False,
            "published": False,
        }
        if feature_enabled(self.root, "editorial_memory.enabled"):
            result["editorial_memory_advisories"] = memory_advisories
        return result

    @staticmethod
    def _validate_returned_paths(
        extracted: Path,
        item: dict[str, Any],
        task: dict[str, Any],
        expected_root: str,
    ) -> None:
        declared = {
            PurePosixPath(_text(path).replace("\\", "/")).as_posix()
            for path in (item.get("files") or {}).keys()
        }
        actual = {
            path.relative_to(extracted).as_posix()
            for path in (extracted / expected_root).rglob("*")
            if path.is_file()
        }
        if declared != actual:
            extras = sorted(actual - declared)
            missing = sorted(declared - actual)
            raise ValueError(f"Returned files do not match manifest; extra={extras}, missing={missing}")
        slug = task["article_slug"]
        if task["task_type"].startswith("WEBSITE_"):
            validation_name = (
                "validation.json"
                if any(
                    str(path).endswith("/validation.json")
                    for path in task.get("target_output_paths") or []
                )
                else "validation_report.json"
            )
            exact = {
                f"website/{slug}/article.html",
                f"website/{slug}/article.md",
                f"website/{slug}/metadata.json",
                f"website/{slug}/{validation_name}",
            }
            asset_prefix = f"website/{slug}/assets/"
        else:
            exact = {
                f"social/{slug}/metadata.json",
                *{
                    f"social/{slug}/{platform}/{variant}.md"
                    for platform in SOCIAL_PLATFORMS
                    for variant in ("A", "B", "C")
                },
            }
            asset_prefix = f"social/{slug}/assets/"
        for path in actual:
            if path in exact:
                continue
            if path.startswith(asset_prefix) and Path(path).suffix.lower() in {
                ".png",
                ".jpg",
                ".jpeg",
                ".webp",
                ".svg",
            }:
                continue
            raise ValueError(f"File is outside the declared output contract: {path}")

    @staticmethod
    def _verify_declared_checksums(extracted: Path, item: dict[str, Any], expected_root: str) -> None:
        files = item.get("files")
        if not isinstance(files, dict) or not files:
            raise ValueError("Each completed item must declare file SHA-256 values.")
        for raw, expected in files.items():
            normalized = PurePosixPath(_text(raw).replace("\\", "/"))
            if normalized.is_absolute() or ".." in normalized.parts:
                raise ValueError(f"Unsafe declared file path: {raw}")
            relative = normalized.as_posix()
            if not relative.startswith(expected_root + "/"):
                raise ValueError(f"Declared file is outside {expected_root}: {relative}")
            path = extracted / relative
            if not path.is_file():
                raise ValueError(f"Declared output file is missing: {relative}")
            if _sha256(path) != _text(expected).lower():
                raise ValueError(f"Checksum mismatch: {relative}")

    def _import_website(
        self,
        source_dir: Path,
        task: dict[str, Any],
        manifest: dict[str, Any],
        *,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        validation_file = (
            source_dir / "validation.json"
            if (source_dir / "validation.json").is_file()
            else source_dir / "validation_report.json"
        )
        required = ("article.html", "article.md", "metadata.json")
        for name in required:
            if not (source_dir / name).is_file():
                raise ValueError(f"Missing website output: {name}")
        if not validation_file.is_file():
            raise ValueError("Missing website output: validation.json")
        html = (source_dir / "article.html").read_text(encoding="utf-8")
        markdown = (source_dir / "article.md").read_text(encoding="utf-8")
        markdown = self._strip_internal_markdown_sections(markdown)
        metadata = json.loads((source_dir / "metadata.json").read_text(encoding="utf-8"))
        validation_report = json.loads(validation_file.read_text(encoding="utf-8"))
        if (
            not html.strip()
            or not markdown.strip()
            or not isinstance(metadata, dict)
            or not isinstance(validation_report, dict)
        ):
            raise ValueError("Website article output is empty or invalid.")
        self._validate_utf8_text(
            "website",
            "\n".join(
                (
                    html,
                    markdown,
                    json.dumps(metadata, ensure_ascii=False),
                    json.dumps(validation_report, ensure_ascii=False),
                )
            ),
        )
        parser = _HTMLContractParser()
        parser.feed(html)
        if not all((parser.html, parser.title, parser.h1, parser.canonical, parser.charset)):
            raise ValueError("Website HTML requires html, title, H1, canonical, and meta charset=utf-8.")
        if parser.h1 != 1:
            raise ValueError("Website HTML must contain exactly one H1.")
        metadata_title = _clean_public_title(metadata.get("title"))
        html_title = _html_public_title(html, "title")
        html_h1 = _html_public_title(html, "h1")
        markdown_h1 = _markdown_public_title(markdown)
        if not metadata_title:
            raise ValueError("Website metadata.title is required.")
        title_versions = {
            _normalized_website_title(value)
            for value in (metadata_title, html_title, html_h1, markdown_h1)
        }
        if "" in title_versions or len(title_versions) != 1:
            raise ValueError(
                "Website public title must match in metadata.title, HTML title, HTML H1, "
                "and Markdown H1."
            )
        if len(metadata_title) >= 45 and re.search(r"\b[A-Za-z]$", metadata_title):
            raise ValueError(
                "Website title appears truncated because it ends with a single-letter fragment."
            )
        historical_titles = {
            _normalized_website_title(value)
            for value in task.get("prior_website_titles") or []
            if _normalized_website_title(value)
        }
        production_root = self.data_dir / "production_article_drafts"
        if production_root.is_dir():
            for metadata_path in production_root.glob("*/metadata.json"):
                if metadata_path.parent.name == _text(task.get("article_slug")):
                    continue
                prior_metadata = _read_json(metadata_path, {})
                normalized = _normalized_website_title(prior_metadata.get("title"))
                if normalized:
                    historical_titles.add(normalized)
        if _normalized_website_title(metadata_title) in historical_titles:
            raise ValueError(
                f"Website title reuses a prior website title: {metadata_title}"
            )
        assert_public_output_files(
            task_id=_text(task.get("task_id")),
            slug=_text(task.get("article_slug")),
            files={
                f"website/{task['article_slug']}/article.html": (html, "html"),
                f"website/{task['article_slug']}/article.md": (markdown, "markdown"),
                f"website/{task['article_slug']}/metadata.json": (
                    json.dumps(metadata, ensure_ascii=False),
                    "metadata",
                ),
            },
        )
        if _text(task.get("task_type")) == "WEBSITE_ADVANCED":
            assert_website_advanced_html(
                task_id=_text(task.get("task_id")),
                slug=_text(task.get("article_slug")),
                html=html,
                article_spec=(
                    task.get("_article_spec")
                    if isinstance(task.get("_article_spec"), dict)
                    else {}
                ),
                website_contract=(
                    task.get("_website_writing_contract")
                    if isinstance(task.get("_website_writing_contract"), dict)
                    else {}
                ),
            )
        self._validate_task_sources(
            task,
            metadata,
            html + "\n" + markdown,
            extra_allowed_urls=self._website_asset_urls(
                html + "\n" + markdown,
                source_dir,
                task,
            ),
        )
        slug = task["article_slug"]
        if dry_run:
            return {
                "task_id": task["task_id"],
                "slug": slug,
                "type": "website",
                "path": str(source_dir),
                "validated": True,
            }
        # External-writer HTML is editorial input.  Convert it to the complete
        # production page before registration and human review so approval is
        # bound to the exact bytes that Menu 8 will later publish.  Publish-time
        # validation must never mutate an already approved revision.
        from modules.final_revision_staging import render_metadata_complete_revision

        html, render_metadata = render_metadata_complete_revision(
            html,
            title=metadata_title,
            description=_text(metadata.get("description")),
            canonical=_text(metadata.get("canonical_url") or metadata.get("url") or parser.canonical),
            topic=_text(task.get("topic") or task.get("keyword") or metadata_title),
            date_published=_text(metadata.get("datePublished") or task.get("batch_date")),
            date_modified=_text(metadata.get("dateModified") or manifest.get("generated_at") or _now()),
        )
        metadata["production_render"] = {
            "status": "COMPLETE_BEFORE_HUMAN_REVIEW",
            "article_schema": render_metadata["article_schema"],
        }
        destination = self.data_dir / "production_article_drafts" / slug
        advanced = _text(task.get("task_type")) == "WEBSITE_ADVANCED"
        update_existing = _text(task.get("task_type")) == "WEBSITE_UPDATE"
        self._protect_website_destination(task, destination)
        working_destination = (
            self.data_dir
            / "external_writer_revision_drafts"
            / _text(manifest.get("package_id"))
            / _text(task.get("task_id"))
            / f"revision-{int(task.get('revision') or 1)}"
            if advanced or update_existing
            else destination
        )
        if not advanced:
            self._archive_website_revision_source(task, destination)
        working_destination.mkdir(parents=True, exist_ok=True)
        (working_destination / "index.html").write_text(html, encoding="utf-8", newline="\n")
        (working_destination / "article.md").write_text(markdown, encoding="utf-8", newline="\n")
        _write_json(working_destination / "validation_report.json", validation_report)
        revision_tasks = revision_tasks_from_validation(
            validation_report,
            task_id=_text(task.get("task_id")),
            slug=slug,
            revision=int(task.get("revision") or 1),
        )
        _write_json(
            working_destination / "revision_tasks.json",
            {
                "schema_version": 1,
                "task_id": _text(task.get("task_id")),
                "slug": slug,
                "revision": int(task.get("revision") or 1),
                "status": "REVISION_REQUIRED" if revision_tasks else "PASS",
                "tasks": revision_tasks,
            },
        )
        _write_json(
            working_destination / "draft_validation_scope.json",
            {
                "schema_version": 1,
                "status": "VALIDATED",
                "checks": [
                    "required_files",
                    "utf8",
                    "json",
                    "markdown",
                    "html",
                    "schema",
                    "citation_urls_exist_in_package",
                ],
                "research_revalidated": False,
                "comparator_run": False,
            },
        )
        writer = {
            "writer_type": _text(manifest.get("writer_type") or "external_ai"),
            "writer_name": _text(manifest.get("writer_name")),
            "writer_version": _text(manifest.get("writer_version")),
            "generated_at": _text(manifest.get("generated_at") or _now()),
            "package_id": manifest["package_id"],
            "task_id": task["task_id"],
            "revision": task["revision"],
        }
        registration: dict[str, Any] | None = None
        try:
            if advanced:
                registration = self._register_website_draft(
                    task,
                    working_destination,
                    html,
                    markdown,
                    metadata,
                    writer,
                    synchronize=False,
                )
            else:
                registration = self._register_website_draft(
                    task,
                    working_destination,
                    html,
                    markdown,
                    metadata,
                    writer,
                )
        except ValueError as exc:
            if "no longer exists in editorial queue" not in str(exc):
                raise
        ai_review_passed = self._ai_review_passed(registration)
        if update_existing:
            self._copy_assets(source_dir, working_destination / "assets")
            self.queue.transition(
                task["task_id"],
                "NEEDS_REVIEW",
                writer=writer,
                imported_at=_now(),
                exported_from_status="",
                ai_review_passed=ai_review_passed,
                isolated_draft_dir=_relative(self.root, working_destination),
                canonical_slug_preserved=True,
                canonical_updated=False,
                human_approval_required=True,
                revision_task_count=len(revision_tasks),
                revision_tasks_file=_relative(self.root, working_destination / "revision_tasks.json"),
            )
            return {
                "task_id": task["task_id"],
                "slug": slug,
                "type": "website_update",
                "path": str(working_destination),
                "isolated": True,
                "canonical_updated": False,
                "preserve_slug": True,
                "create_new_url": False,
                "human_approval_required": True,
                "ai_review_passed": ai_review_passed,
                "revision_task_count": len(revision_tasks),
            }
        if advanced and not ai_review_passed:
            self._copy_assets(source_dir, working_destination / "assets")
            self.queue.transition(
                task["task_id"],
                "NEEDS_REVIEW",
                writer=writer,
                imported_at=_now(),
                exported_from_status="",
                ai_review_passed=False,
                isolated_draft_dir=_relative(self.root, working_destination),
                revision_task_count=len(revision_tasks),
                revision_tasks_file=_relative(
                    self.root,
                    working_destination / "revision_tasks.json",
                ),
            )
            return {
                "task_id": task["task_id"],
                "slug": slug,
                "type": "website",
                "path": str(working_destination),
                "isolated": True,
                "canonical_updated": False,
                "ai_review_passed": False,
                "revision_task_count": len(revision_tasks),
            }

        if advanced:
            self._archive_website_revision_source(task, destination)
            destination.mkdir(parents=True, exist_ok=True)
            for source in working_destination.iterdir():
                if source.is_file():
                    shutil.copy2(source, destination / source.name)
            self._copy_assets(source_dir, destination / "assets")
            self._point_editorial_queue_at_destination(task, destination, registration)
            self._synchronize_website_draft(task)
        else:
            self._copy_assets(source_dir, destination / "assets")
        self.queue.transition(
            task["task_id"],
            "NEEDS_REVIEW",
            writer=writer,
            imported_at=_now(),
            exported_from_status="",
            revision_task_count=len(revision_tasks),
            revision_tasks_file=_relative(
                self.root,
                destination / "revision_tasks.json",
            ),
        )
        return {
            "task_id": task["task_id"],
            "slug": slug,
            "type": "website",
            "path": str(destination),
            "isolated": False,
            "canonical_updated": True,
            # Record the synchronous content-review result for every website
            # lane.  Leaving WEBSITE_FOUNDATION as null made the later
            # provenance check reinterpret a completed review as not_run.
            "ai_review_passed": ai_review_passed,
            "revision_task_count": len(revision_tasks),
        }

    @staticmethod
    def _ai_review_passed(registration: dict[str, Any] | None) -> bool:
        if not isinstance(registration, dict):
            return False
        review = registration.get("review")
        if not isinstance(review, dict):
            return False
        return (
            _text(review.get("status"))
            in {"ai_review_passed", "needs_human_review", "human_approved"}
            and bool(review.get("publishable", True))
            and not list(review.get("hard_blockers") or [])
        )

    def _point_editorial_queue_at_destination(
        self,
        task: dict[str, Any],
        destination: Path,
        registration: dict[str, Any] | None,
    ) -> None:
        queue_path = self.data_dir / "editorial_queue" / task["batch_date"] / "topics.json"
        payload = _read_json(queue_path, {})
        for row in payload.get("topics", []) if isinstance(payload, dict) else []:
            if isinstance(row, dict) and row.get("slug") == task["article_slug"]:
                row["draft_dir"] = str(destination)
                row["draft_file"] = str(destination / "index.html")
                row["metadata_file"] = str(destination / "metadata.json")
                if isinstance(registration, dict):
                    row["review_status"] = _text(
                        (registration.get("review") or {}).get("status")
                    )
                break
        _write_json(queue_path, payload)

    def _synchronize_website_draft(self, task: dict[str, Any]) -> None:
        from modules.daily_editorial_workflow import DailyEditorialWorkflow

        workflow = DailyEditorialWorkflow(
            root=self.root,
            data_dir=self.data_dir,
            site_output_dir=self.root / "site_output",
        )
        workflow._copy_review_preview(
            slug=task["article_slug"],
            batch_date=task["batch_date"],
        )
        workflow.build_review_dashboard(batch_date=task["batch_date"])
        workflow._sync_upload_batch(batch_date=task["batch_date"])

    @staticmethod
    def _strip_internal_markdown_sections(markdown: str) -> str:
        section_names = (
            "Affiliate Placeholder Fields",
            "Research Package Snapshot",
            "Content Planning Snapshot",
        )
        updated = markdown
        for section_name in section_names:
            pattern = re.compile(
                rf"(?ims)^##+\s+{re.escape(section_name)}\s*$.*?(?=^##+\s+|\Z)"
            )
            updated = pattern.sub("", updated)
        return re.sub(r"\n{3,}", "\n\n", updated).strip() + "\n"

    def _register_website_draft(
        self,
        task: dict[str, Any],
        destination: Path,
        html: str,
        markdown: str,
        returned_metadata: dict[str, Any],
        writer_metadata: dict[str, Any],
        *,
        synchronize: bool = True,
    ) -> dict[str, Any]:
        from modules.codex_writer_workflow import CodexDailyArticleWriter
        from modules.content_review import ContentReviewEngine
        from modules.human_approval import HumanApprovalWorkflow
        from modules.publish_gate import PublishGate
        from modules.research_intelligence import ResearchPackage

        batch_date = task["batch_date"]
        queue_path = self.data_dir / "editorial_queue" / batch_date / "topics.json"
        queue_payload = _read_json(queue_path, {})
        topics = list(queue_payload.get("topics") or []) if isinstance(queue_payload, dict) else []
        queue_item = next((row for row in topics if isinstance(row, dict) and row.get("slug") == task["article_slug"]), None)
        if queue_item is None:
            raise ValueError(f"Website task no longer exists in editorial queue: {task['article_slug']}")
        package_payload = _read_json(self.data_dir / "research" / task["article_slug"] / "package.json", {})
        try:
            package = ResearchPackage(**package_payload)
        except TypeError as exc:
            raise ValueError(f"Invalid research package for {task['article_slug']}: {exc}") from exc
        writer = CodexDailyArticleWriter(root=self.root, data_dir=self.data_dir, site_output_dir=self.root / "site_output")
        topic = writer._build_topic(queue_item, package, depth="deep")
        title = _text(returned_metadata.get("title") or task.get("title"))
        description = _text(returned_metadata.get("description") or returned_metadata.get("meta_description"))
        url = _text(returned_metadata.get("canonical_url") or f"https://smileaireviewhub.com/{task['article_slug']}/")
        source_urls = [task.get("primary_source_url"), *list(task.get("supporting_source_urls") or [])]
        topic["writer"] = writer_metadata
        topic["external_source_urls"] = [url for url in source_urls if _http_url(url)]
        internal_links = [
            (href, href)
            for href in re.findall(
                r"<a\b[^>]*href=['\"]([^'\"]+)['\"]",
                html,
                flags=re.IGNORECASE,
            )
            if href.startswith("/") and not href.startswith("//")
        ]
        config = _read_json(self.root / "config" / "editorial_system.json", {})
        review = ContentReviewEngine(data_dir=self.data_dir, config=config.get("content_review", {})).review_content(
            topic=topic,
            html=html,
            title=title,
            description=description,
            url=url,
            internal_links=internal_links,
            warnings=[],
            research=topic["research"],
            planning=topic["planning"],
        )
        human = HumanApprovalWorkflow(data_dir=self.data_dir, config=config.get("human_approval", {})).sync_review(review)
        gate = PublishGate(
            data_dir=self.data_dir,
            site_output_dir=self.root / "site_output",
            config=config.get("publish_gate", {}),
        ).evaluate(
            topic=topic,
            title=title,
            description=description,
            url=url,
            html=html,
            research=topic["research"],
            review=review,
            human_approval=human,
            internal_links=internal_links,
        )
        if str(human.get("status") or "") == "human_approved":
            raise ValueError("External import cannot preserve or create human approval.")
        metadata = {
            **returned_metadata,
            "slug": task["article_slug"],
            "title": title,
            "description": description,
            "url": url,
            "writer": writer_metadata,
            "review": review,
            "human_approval": {**human, "status": "needs_human_review", "approved": False},
            "publish_gate": gate,
            "external_import": True,
        }
        _write_json(destination / "metadata.json", metadata)
        _write_json(
            destination / "external_writer_report.json",
            {
                "writer": writer_metadata,
                "source_urls": topic["external_source_urls"],
                "ai_review_passed": bool(
                    str(review.get("review_state") or "").upper() == "PASS"
                    and bool(review.get("publishable", True))
                    and not list(review.get("hard_blockers") or [])
                ),
                "ai_review_status": str(review.get("status") or ""),
                "human_approval_required": True,
                "approved": False,
                "published": False,
            },
        )
        queue_item.update(
            {
                "status": "drafted",
                "draft_dir": str(destination),
                "draft_file": str(destination / "index.html"),
                "metadata_file": str(destination / "metadata.json"),
                "review_status": str(review.get("status") or "needs_human_review"),
                "human_approval_status": "needs_human_review",
                "publish_gate_status": str(gate.get("status") or "needs_human_review"),
                "writer": writer_metadata,
                "error": "",
            }
        )
        queue_payload["batch_state"] = "UNDER_REVIEW"
        _write_json(queue_path, queue_payload)
        if synchronize:
            self._synchronize_website_draft(task)
        return {"review": review, "human_approval": human, "publish_gate": gate}

    def _import_social(
        self,
        source_dir: Path,
        task: dict[str, Any],
        manifest: dict[str, Any],
        *,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        metadata_path = source_dir / "metadata.json"
        if not metadata_path.is_file():
            raise ValueError("Missing social metadata.json.")
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if not isinstance(metadata, dict):
            raise ValueError("Social metadata.json must contain an object.")
        self._validate_utf8_text("social metadata", json.dumps(metadata, ensure_ascii=False))
        self._validate_task_sources(task, metadata, "")
        slug = task["article_slug"]
        destination = self.data_dir / "social_drafts" / task["batch_date"] / slug
        self._protect_social_destination(destination)
        series_plan = metadata.get("series_plan")
        if not isinstance(series_plan, dict):
            raise ValueError("Social metadata must declare series_plan.")
        if _text(series_plan.get("schema_version")) != SOCIAL_SERIES_SCHEMA:
            raise ValueError(f"series_plan schema_version must be {SOCIAL_SERIES_SCHEMA}.")
        strict_social_value = bool((task.get("social_value_requirements") or {}).get("enabled"))
        complementary_components = task.get("task_type") == "SOCIAL_WEBSITE_DISTRIBUTION"
        series_fields = (
            ("pillar_title", "today_angle")
            if strict_social_value or complementary_components
            else ("pillar_title", "today_angle", "next_day_title")
        )
        for field in series_fields:
            if not _text(series_plan.get(field)):
                raise ValueError(f"series_plan.{field} is required.")
        try:
            day_number = int(series_plan.get("day_number") or 0)
        except (TypeError, ValueError) as exc:
            raise ValueError("series_plan.day_number must be a positive integer.") from exc
        if day_number < 1:
            raise ValueError("series_plan.day_number must be a positive integer.")
        if _text(series_plan.get("next_day_title")) and _normalized_social_title(series_plan.get("today_angle")) == _normalized_social_title(
            series_plan.get("next_day_title")
        ):
            raise ValueError("series_plan.next_day_title must differ from today_angle.")
        canonical_title = _normalized_social_title(task.get("title"))
        historical_titles = self._historical_social_titles(task)
        returned_titles: set[str] = set()
        validated: dict[
            str,
            tuple[dict[str, str], dict[str, Any], dict[str, Any], dict[str, Any]],
        ] = {}
        for platform in SOCIAL_PLATFORMS:
            platform_source = source_dir / platform
            if not platform_source.is_dir():
                raise ValueError(f"Missing social platform directory: {platform}")
            variants: dict[str, str] = {}
            for variant in ("A.md", "B.md", "C.md"):
                text = (platform_source / variant).read_text(encoding="utf-8")
                self._validate_social_text(platform, text, task)
                variants[variant] = text
            if len(set(value.strip() for value in variants.values())) != 3:
                raise ValueError(f"{platform} variants must be meaningfully distinct files.")
            platform_meta = metadata.get("platforms", {}).get(platform, {})
            if not isinstance(platform_meta, dict):
                raise ValueError(f"Missing metadata object for social platform: {platform}")
            allowed_claim_ids = {
                _text(value) for value in list(task.get("allowed_social_claim_ids") or []) if _text(value)
            }
            declared_claim_ids = {
                _text(value) for value in list(platform_meta.get("claim_ids") or []) if _text(value)
            }
            unknown_claim_ids = sorted(declared_claim_ids - allowed_claim_ids)
            if unknown_claim_ids:
                raise ValueError(
                    f"{platform} contains unsupported claim IDs: {', '.join(unknown_claim_ids)}"
                )
            for new_claim in list(platform_meta.get("new_claims") or []):
                if not isinstance(new_claim, dict):
                    raise ValueError(f"{platform} NEW_UNSUPPORTED_FACTUAL_CLAIM: evidence binding is required.")
                claim_id = _text(new_claim.get("claim_id"))
                evidence_url = _text(new_claim.get("evidence_url"))
                allowed_urls = {
                    _text(task.get("primary_source_url")),
                    *[_text(value) for value in list(task.get("supporting_source_urls") or [])],
                }
                if claim_id not in allowed_claim_ids and evidence_url not in allowed_urls:
                    raise ValueError(f"{platform} NEW_UNSUPPORTED_FACTUAL_CLAIM: evidence binding is required.")
            variant_titles = platform_meta.get("variant_titles")
            if not isinstance(variant_titles, dict):
                raise ValueError(f"Missing social variant_titles metadata for: {platform}")
            normalized_platform_titles: list[str] = []
            for variant in SOCIAL_VARIANTS:
                variant_title = _text(variant_titles.get(variant))
                if not variant_title:
                    raise ValueError(f"Missing {platform} title for variant {variant}.")
                normalized = _normalized_social_title(variant_title)
                if not normalized:
                    raise ValueError(f"Invalid {platform} title for variant {variant}.")
                if normalized == canonical_title:
                    raise ValueError(
                        f"{platform} {variant} title must not repeat the canonical article title."
                    )
                if normalized in historical_titles:
                    raise ValueError(
                        f"{platform} {variant} title reuses a prior social title: {variant_title}"
                    )
                if normalized in returned_titles:
                    raise ValueError(
                        f"Social variant titles must be unique within the task: {variant_title}"
                    )
                normalized_platform_titles.append(normalized)
                returned_titles.add(normalized)
            if len(set(normalized_platform_titles)) != len(SOCIAL_VARIANTS):
                raise ValueError(f"{platform} variant titles must be distinct.")
            if _normalized_social_title(platform_meta.get("title")) != normalized_platform_titles[0]:
                raise ValueError(f"{platform} title must match variant_titles.A.md.")
            next_day_teaser = _text(platform_meta.get("next_day_teaser"))
            closing_cta = _text(platform_meta.get("closing_cta") or next_day_teaser or platform_meta.get("cta"))
            if not next_day_teaser:
                if not strict_social_value and not complementary_components:
                    raise ValueError(f"Missing next_day_teaser metadata for: {platform}")
                next_day_teaser = closing_cta
            teaser_markers = (
                ("ngày mai", "đón đọc", "tiếp theo")
                if platform == "facebook_vi"
                else ("tomorrow", "next", "coming")
            )
            if (
                not strict_social_value
                and not complementary_components
                and not any(marker in next_day_teaser.casefold() for marker in teaser_markers)
            ):
                raise ValueError(f"{platform} next_day_teaser must clearly lead into tomorrow's content.")
            for variant, text in variants.items():
                if next_day_teaser and not complementary_components and not text.rstrip().endswith(next_day_teaser):
                    raise ValueError(
                        f"{platform} {variant} must end with the declared next_day_teaser."
                    )
                if strict_social_value:
                    requirements = task.get("social_value_requirements") or {}
                    quality = validate_social_value(
                        text,
                        platform=platform,
                        official_source_name_value=_text(task.get("official_source_name")),
                        official_source_url=_text(task.get("official_source_url")),
                        source_render_required=bool(task.get("source_render_required")) and platform != "x",
                        scheduled_followup_exists=bool(task.get("scheduled_followup_exists")),
                        title=_text(variant_titles.get(variant)),
                        story_title=_text(task.get("title")),
                        hashtags=platform_meta.get("hashtags") or [],
                        verified_pricing=bool(requirements.get("verified_pricing")),
                        affiliate_claims_supported=bool(requirements.get("affiliate_claims_supported")),
                    )
                    if quality["status"] == "BLOCKED":
                        raise ValueError(f"{platform} {variant} social value gate blocked: {', '.join(quality['reasons'])}")
            final_result: dict[str, Any] = {}
            if complementary_components:
                final_result = PlatformNativeSocialEngine.compose_components(
                    platform=platform,
                    components=variants,
                    topic=_text(task.get("root_title") or task.get("title") or slug),
                    url=_text(task.get("website_url")),
                    evidence_refs=list(platform_meta.get("evidence_refs") or platform_meta.get("claim_ids") or []),
                )
                if platform == "x" and not validate_x_draft(_text(final_result.get("text")))["within_limit"]:
                    raise ValueError("x FINAL.md exceeds the configured short-post limit.")
            selected_text = _text(final_result.get("text")) if final_result else variants["A.md"]
            selected_title = _text(final_result.get("title")) if final_result else _text(variant_titles.get("A.md"))
            selected_quality = (
                validate_social_value(
                    selected_text,
                    platform=platform,
                    official_source_name_value=_text(task.get("official_source_name")),
                    official_source_url=_text(task.get("official_source_url")),
                    source_render_required=bool(task.get("source_render_required")) and platform != "x",
                    scheduled_followup_exists=bool(task.get("scheduled_followup_exists")),
                    title=selected_title,
                    story_title=_text(task.get("title")),
                    hashtags=platform_meta.get("hashtags") or [],
                    verified_pricing=bool((task.get("social_value_requirements") or {}).get("verified_pricing")),
                    affiliate_claims_supported=bool(
                        (task.get("social_value_requirements") or {}).get("affiliate_claims_supported")
                    ),
                )
                if strict_social_value
                else {}
            )
            if not strict_social_value and not _text(platform_meta.get("cta")):
                raise ValueError(f"Missing social CTA metadata for: {platform}")
            if not isinstance(platform_meta.get("hashtags"), list):
                raise ValueError(f"Social hashtags metadata must be a list for: {platform}")
            platform_meta["closing_cta"] = closing_cta
            validated[platform] = (variants, platform_meta, selected_quality, final_result)
        if strict_social_value:
            platforms = list(validated)
            for left_index, left_platform in enumerate(platforms):
                left_variants = validated[left_platform][0]
                for right_platform in platforms[left_index + 1:]:
                    right_variants = validated[right_platform][0]
                    for variant in SOCIAL_VARIANTS:
                        similarity = cross_platform_similarity(left_variants[variant], right_variants[variant])
                        if similarity >= 0.92:
                            raise ValueError(
                                "DUPLICATED_CROSS_PLATFORM_WORDING: "
                                f"{left_platform}/{variant} and {right_platform}/{variant} similarity={similarity:.3f}; "
                                "rewrite for each platform audience."
                            )
        if dry_run:
            return {
                "task_id": task["task_id"],
                "slug": slug,
                "type": "social",
                "path": str(source_dir),
                "validated": True,
            }
        for platform, (variants, platform_meta, selected_quality, final_result) in validated.items():
            platform_destination = destination / platform
            platform_destination.mkdir(parents=True, exist_ok=True)
            for variant, text in variants.items():
                (platform_destination / variant).write_text(text, encoding="utf-8", newline="\n")
            if final_result:
                (platform_destination / "FINAL.md").write_text(
                    _text(final_result.get("text")) + "\n",
                    encoding="utf-8",
                    newline="\n",
                )
            _write_json(
                platform_destination / "metadata.json",
                {
                    "schema_version": 1,
                    "status": "needs_social_review",
                    "status_label": "Needs Review",
                    "approved_for_copy": False,
                    "selected_variant": "FINAL.md" if final_result else "A.md",
                    "article_slug": slug,
                    "platform": platform,
                    "content_origin": _text(task.get("content_origin") or "WEBSITE_ROOT_BASED"),
                    "social_mode": _text(task.get("social_mode") or "SOURCE_BASED_SOCIAL"),
                    "root_topic_id": _text(task.get("root_topic_id")),
                    "root_title": _text(task.get("root_title")),
                    "source_article_slug": _text(task.get("source_article_slug") or slug),
                    "source_revision_id": _text(task.get("source_revision_id")),
                    "source_content_hash": _text(task.get("source_content_hash")),
                    "source_evidence_reference": _text(task.get("source_evidence_reference")),
                    "evidence_inheritance": _text(task.get("evidence_inheritance")),
                    "social_angle": _text(task.get("social_angle")),
                    "today_social_angle": _text(series_plan.get("today_angle") or task.get("social_angle")),
                    "content_model": (
                        "COMPLEMENTARY_COMPONENTS_V1" if final_result else "HOT_NEWS_VARIANTS_V1"
                    ),
                    "components_read_only": bool(final_result),
                    "legacy_variant_model": False,
                    "recompose_status": "COMPOSED" if final_result else "NOT_APPLICABLE",
                    "final_post_file": "FINAL.md" if final_result else "",
                    "final_title": _text(final_result.get("title")),
                    "final_metadata": {
                        **final_result,
                        "component_inputs": list(SOCIAL_VARIANTS),
                        "evidence_refs": list(
                            platform_meta.get("evidence_refs") or platform_meta.get("claim_ids") or []
                        ),
                        "new_claims": [],
                        "claim_guard": "SOURCE_AND_COMPONENT_KNOWLEDGE_ONLY",
                    } if final_result else {},
                    "content_relationship": _text(task.get("content_relationship")),
                    "claim_ids": list(platform_meta.get("claim_ids") or []),
                    "new_claims": list(platform_meta.get("new_claims") or []),
                    "evidence_refs": list(platform_meta.get("evidence_refs") or platform_meta.get("claim_ids") or []),
                    "claim_verification_contract": _text(task.get("claim_verification_contract")),
                    "language": "vi" if platform == "facebook_vi" else "en",
                    "title": _text(platform_meta["variant_titles"]["A.md"]),
                    "variant_titles": {
                        variant: _text(platform_meta["variant_titles"][variant])
                        for variant in SOCIAL_VARIANTS
                    },
                    "variant_metadata": {
                        variant: {
                            "component_role": COMPONENT_ROLES[variant],
                            "variant_strategy": _text(
                                COMPONENT_ROLES[variant]
                                if complementary_components
                                else (platform_meta.get("variant_strategies") or task.get("variant_strategies") or {}).get(variant)
                            ),
                            "social_angle": _text(
                                series_plan.get("today_angle")
                                if complementary_components
                                else (platform_meta.get("social_angles") or {}).get(variant)
                                or platform_meta.get("social_angle")
                                or task.get("social_angle")
                            ),
                            "character_count": len(variants[variant].strip()),
                            "platform_limit": X_MAX_CHARACTERS if platform == "x" else None,
                            "within_limit": len(variants[variant].strip()) <= X_MAX_CHARACTERS if platform == "x" else True,
                            "platform_validation_status": (
                                validate_x_draft(variants[variant].strip())["status"] if platform == "x" else "PASS"
                            ),
                            "evidence_refs": list(platform_meta.get("evidence_refs") or platform_meta.get("claim_ids") or []),
                        }
                        for variant in SOCIAL_VARIANTS
                    },
                    "visual_recommended": bool(platform_meta.get("visual_recommended")),
                    "visual_type": _text(platform_meta.get("visual_type") or "NO_VISUAL"),
                    "visual_concept": _text(platform_meta.get("visual_concept")),
                    "visual_source": _text(platform_meta.get("visual_source") or "CONCEPT_ONLY"),
                    "visual_alt_text": _text(platform_meta.get("visual_alt_text")),
                    "platform_playbook": dict(SOCIAL_PLATFORM_PLAYBOOKS.get(platform) or {}),
                    "platform_native_contract": True,
                    "x_max_characters": X_MAX_CHARACTERS if platform == "x" else None,
                    "x_thread_enabled": X_THREAD_ENABLED if platform == "x" else None,
                    "next_day_teaser": _text(platform_meta.get("next_day_teaser")),
                    "closing_cta": _text(platform_meta.get("closing_cta")),
                    "series_plan": dict(series_plan),
                    "cta": _text(platform_meta.get("cta")),
                    "CTA": _text(platform_meta.get("cta")),
                    "hashtags": list(platform_meta.get("hashtags") or []),
                    "website_url": _text(task.get("website_url")),
                    "source_url": _text(task.get("primary_source_url")),
                    "official_source_name": _text(task.get("official_source_name")),
                    "official_source_url": _text(task.get("official_source_url")),
                    "official_source_type": _text(task.get("official_source_type")),
                    "source_render_required": bool(task.get("source_render_required")) and platform != "x",
                    "scheduled_followup_exists": bool(task.get("scheduled_followup_exists")),
                    "scheduled_followup_date": _text(task.get("scheduled_followup_date")),
                    "social_value_requirements": dict(task.get("social_value_requirements") or {}),
                    "social_value_validation": selected_quality,
                    "pinterest_visual_facts": list(task.get("pinterest_visual_facts") or []),
                    "pinterest_visual_points": list(platform_meta.get("pinterest_visual_points") or []),
                    "pinterest_visual_subhead": _text(platform_meta.get("pinterest_visual_subhead")),
                    "source_urls": [
                        url
                        for url in [task.get("primary_source_url"), *list(task.get("supporting_source_urls") or [])]
                        if _http_url(url)
                    ],
                    "content_lane": task["workflow_lane"],
                    "writer_type": _text(manifest.get("writer_type") or "external_ai"),
                    "writer_name": _text(manifest.get("writer_name")),
                    "writer_version": _text(manifest.get("writer_version")),
                    "package_id": manifest["package_id"],
                    "task_id": task["task_id"],
                    "revision": task["revision"],
                    "validation_warnings": [],
                    "api_used": False,
                    "oauth_used": False,
                    "browser_automation_used": False,
                },
            )
        self._copy_assets(source_dir, destination / "assets")
        self._upsert_social_manifest(task)
        self.queue.transition(
            task["task_id"],
            "NEEDS_REVIEW",
            writer={
                "writer_type": _text(manifest.get("writer_type") or "external_ai"),
                "writer_name": _text(manifest.get("writer_name")),
                "writer_version": _text(manifest.get("writer_version")),
            },
            imported_at=_now(),
        )
        return {"task_id": task["task_id"], "slug": slug, "type": "social", "path": str(destination)}

    def _validate_task_sources(
        self,
        task: dict[str, Any],
        metadata: dict[str, Any],
        body: str,
        *,
        extra_allowed_urls: set[str] | None = None,
    ) -> None:
        approved_sources = {
            _text(url)
            for url in [task.get("primary_source_url"), *list(task.get("supporting_source_urls") or [])]
            if _http_url(url)
        }
        if _text(task.get("task_type")).startswith("WEBSITE_") and not approved_sources:
            raise ValueError(
                "Website source contract failed: no approved source URLs exist in the writer task."
            )
        allowed = set(approved_sources)
        allowed.update(extra_allowed_urls or set())
        website_url = _text(task.get("website_url"))
        if _http_url(website_url):
            allowed.add(website_url)
        canonical_url = _text(metadata.get("canonical_url"))
        expected_canonical = f"https://smileaireviewhub.com/{task['article_slug']}/"
        if canonical_url == expected_canonical:
            allowed.add(canonical_url)
        for requirement in list(task.get("internal_link_requirements") or []):
            if isinstance(requirement, dict):
                candidate = _text(requirement.get("url") or requirement.get("href"))
            else:
                candidate = _text(requirement)
            if candidate.startswith("/"):
                candidate = "https://smileaireviewhub.com" + candidate
            if _http_url(candidate):
                allowed.add(candidate)
        returned = {_text(url) for url in list(metadata.get("source_urls") or []) if _http_url(url)}
        if returned - allowed:
            raise ValueError(f"Returned metadata contains source URLs outside task allowlist: {sorted(returned - allowed)}")
        body_urls = self._extract_http_urls(body) - STANDARD_VOCABULARY_URLS
        if body_urls - allowed:
            raise ValueError(f"Returned content contains URLs outside task allowlist: {sorted(body_urls - allowed)}")
        if _text(task.get("task_type")).startswith("WEBSITE_"):
            cited_sources = (returned | body_urls) & approved_sources
            if not cited_sources:
                raise ValueError(
                    "Website source contract failed: returned draft cites none of its approved sources."
                )
        if task["task_type"] == "SOCIAL_HOT_NEWS":
            if "smileaireviewhub.com/" in body.lower() or "smileaireviewhub.com/" in json.dumps(metadata).lower():
                raise ValueError("Hot-news draft must not create a Smile AI Review Hub URL.")

    @staticmethod
    def _website_asset_urls(body: str, source_dir: Path, task: dict[str, Any]) -> set[str]:
        asset_root = source_dir / "assets"
        slug = _text(task.get("article_slug"))
        if not SLUG_RE.fullmatch(slug):
            return set()
        allowed_suffixes = {".png", ".jpg", ".jpeg", ".webp", ".svg"}
        public_prefix = f"https://smileaireviewhub.com/{slug}/assets/"
        referenced = {
            url
            for url in UniversalExternalWriterImporter._extract_http_urls(body)
            if url.startswith(public_prefix)
            and Path(urlparse(url).path).suffix.lower() in allowed_suffixes
            and not urlparse(url).query
            and not urlparse(url).fragment
        }
        returned = (
            {
                f"{public_prefix}{path.relative_to(asset_root).as_posix()}"
                for path in asset_root.rglob("*")
                if path.is_file() and path.suffix.lower() in allowed_suffixes
            }
            if asset_root.is_dir()
            else set()
        )
        # Source validation only establishes that these are same-article local
        # assets. The rendering/image gate separately verifies file existence.
        return referenced | returned

    @staticmethod
    def _extract_http_urls(text: str) -> set[str]:
        urls: set[str] = set()
        for match in re.findall(r"https?://[^\s<>\"')\]]+", text):
            normalized = match.rstrip(".,;:!?}")
            if _http_url(normalized):
                urls.add(normalized)
        return urls

    def _protect_website_destination(self, task: dict[str, Any], destination: Path) -> None:
        if _text(task.get("task_type")) == "WEBSITE_UPDATE":
            return
        revision_requested = _is_website_revision(task)
        states = self.queue._website_states(task)
        protected = (
            states
            & (
                {"published", "published_local"}
                if revision_requested and self.queue._invalidated_unpublished_approval(task)
                else IMMUTABLE_WEBSITE_STATES
            )
            if revision_requested
            else states & PROTECTED_WEBSITE_STATES
        )
        if protected:
            raise ValueError(f"Refusing to overwrite protected website state: {sorted(protected)}")
        if destination.exists() and (destination / "metadata.json").exists():
            current = _read_json(destination / "metadata.json", {})
            if (
                not revision_requested
                and (current.get("reviewer_notes") or current.get("audit_history"))
            ):
                raise ValueError("Refusing to overwrite website draft with review history.")

    def _archive_website_revision_source(
        self,
        task: dict[str, Any],
        destination: Path,
    ) -> None:
        if not _is_website_revision(task) or not destination.is_dir():
            return
        revision = max(1, int(task.get("revision") or 1) - 1)
        archive = (
            self.data_dir
            / "import_history"
            / "external_writer"
            / "revisions"
            / _text(task.get("task_id"))
            / f"revision-{revision}"
        )
        if archive.exists():
            return
        archive.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(destination, archive)

    def _protect_social_destination(self, destination: Path) -> None:
        for platform in SOCIAL_PLATFORMS:
            current = _read_json(destination / platform / "metadata.json", {})
            status = _text(current.get("status")).lower()
            if status in PROTECTED_SOCIAL_STATES or current.get("reviewer_notes") or current.get("history"):
                raise ValueError(f"Refusing to overwrite protected social state: {platform}/{status}")

    def _historical_social_titles(self, task: dict[str, Any]) -> set[str]:
        titles = {
            _normalized_social_title(value)
            for value in task.get("prior_social_titles") or []
            if _normalized_social_title(value)
        }
        social_root = self.data_dir / "social_drafts"
        slug = _text(task.get("article_slug"))
        current_batch = _text(task.get("batch_date"))
        if not social_root.exists():
            return titles
        for batch_dir in social_root.glob("*"):
            if not batch_dir.is_dir() or batch_dir.name >= current_batch:
                continue
            for platform in SOCIAL_PLATFORMS:
                metadata = _read_json(batch_dir / slug / platform / "metadata.json", {})
                if not isinstance(metadata, dict):
                    continue
                candidates = [_text(metadata.get("title"))]
                variant_titles = metadata.get("variant_titles")
                if isinstance(variant_titles, dict):
                    candidates.extend(_text(value) for value in variant_titles.values())
                titles.update(
                    normalized
                    for normalized in map(_normalized_social_title, candidates)
                    if normalized
                )
        return titles

    def _validate_social_text(self, platform: str, text: str, task: dict[str, Any]) -> None:
        if not text.strip():
            raise ValueError(f"{platform} draft is empty.")
        UniversalExternalWriterImporter._validate_utf8_text(platform, text)
        if platform == "facebook_vi":
            if not VIETNAMESE_DIACRITIC_RE.search(text):
                raise ValueError("facebook_vi draft must use Vietnamese with full diacritics.")
        lowered = text.lower()
        if any(marker in lowered for marker in ("suggested question:", "# quora answer draft", "local image file:")):
            raise ValueError(f"{platform} draft contains internal writer labels.")
        if platform == "x":
            validation = validate_x_draft(text.strip(), X_MAX_CHARACTERS)
            if not validation["within_limit"]:
                raise ValueError(
                    f"X draft exceeds the configured 280-character limit; status=INVALID_PLATFORM_LIMIT "
                    f"({validation['character_count']}/{X_MAX_CHARACTERS}); "
                    "regenerate/compress semantically and do not truncate the ending."
                )
        if task["task_type"] == "SOCIAL_HOT_NEWS" and "smileaireviewhub.com/" in lowered:
            raise ValueError("Hot-news social draft contains a fake website URL.")
        self._validate_task_sources(task, {"source_urls": []}, text)

    @staticmethod
    def _validate_utf8_text(label: str, text: str) -> None:
        if UTF8_DAMAGE_RE.search(text):
            raise ValueError(f"{label} draft appears to contain UTF-8 damage.")
        if MOJIBAKE_RE.search(text):
            raise ValueError(f"{label} draft contains mojibake.")

    @staticmethod
    def _copy_assets(source_dir: Path, destination: Path) -> None:
        source = source_dir / "assets"
        if not source.exists():
            return
        destination.mkdir(parents=True, exist_ok=True)
        for path in source.iterdir():
            if path.is_file() and path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".svg"}:
                shutil.copy2(path, destination / path.name)

    def _upsert_social_manifest(self, task: dict[str, Any]) -> None:
        path = self.data_dir / "social_drafts" / task["batch_date"] / "manifest.json"
        manifest = _read_json(path, {})
        if not isinstance(manifest, dict):
            manifest = {}
        items = manifest.get("items") if isinstance(manifest.get("items"), list) else []
        item = next((row for row in items if isinstance(row, dict) and row.get("slug") == task["article_slug"]), None)
        if item is None:
            item = {}
            items.append(item)
        item.update(
            {
                "slug": task["article_slug"],
                "title": task["title"],
                "url": _text(task.get("website_url")),
                "status": "needs_social_review",
                "platforms": list(SOCIAL_PLATFORMS),
                "content_lane": task["workflow_lane"],
                "task_id": task["task_id"],
            }
        )
        manifest.update(
            {
                "schema_version": manifest.get("schema_version", 1),
                "batch_date": task["batch_date"],
                "status": "social_review_ready",
                "items": items,
            }
        )
        _write_json(path, manifest)


def rebuild_completed_manifest(
    source_directory: Path,
    *,
    output: Path,
    project_root: Path,
) -> dict[str, Any]:
    source = source_directory.resolve()
    if not source.is_dir():
        raise FileNotFoundError(f"Completed drafts directory not found: {source}")
    manifest_path = source / "completed_manifest.json"
    contract_path = source / "verified_package_contract.json"
    manifest = _read_json(manifest_path, {})
    if not isinstance(manifest, dict) or manifest.get("schema_version") != RETURN_SCHEMA:
        raise ValueError(f"completed_manifest.json must use {RETURN_SCHEMA}.")
    if not contract_path.is_file():
        raise ValueError("verified_package_contract.json is required.")
    items = manifest.get("items")
    if not isinstance(items, list) or not items:
        raise ValueError("completed_manifest.items must be a non-empty list.")

    members = {"completed_manifest.json", "verified_package_contract.json"}
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Every completed manifest item must be an object.")
        output_root = PurePosixPath(_text(item.get("output_root")).strip("/"))
        if output_root.is_absolute() or ".." in output_root.parts or not output_root.parts:
            raise ValueError(f"Unsafe output_root: {output_root}")
        disk_root = source / Path(*output_root.parts)
        if not disk_root.is_dir():
            raise ValueError(f"Output directory is missing: {output_root.as_posix()}")
        files: dict[str, str] = {}
        for path in sorted(candidate for candidate in disk_root.rglob("*") if candidate.is_file()):
            if path.suffix.lower() in EXECUTABLE_SUFFIXES:
                raise ValueError(f"Executable output is not allowed: {path}")
            relative = path.relative_to(source).as_posix()
            files[relative] = _sha256(path)
            members.add(relative)
        if not files:
            raise ValueError(f"No returned files found under {output_root.as_posix()}.")
        item["files"] = files

    contract = _read_json(contract_path, {})
    package_id = _text(manifest.get("package_id"))
    if _text(contract.get("package_id")) != package_id:
        raise ValueError("Immutable package_id mismatch in verified_package_contract.json.")
    contract_tasks = {
        _text(row.get("task_id")): row
        for row in contract.get("tasks", [])
        if isinstance(row, dict)
    }
    for item in items:
        task_id = _text(item.get("task_id"))
        task = contract_tasks.get(task_id)
        if task is None:
            raise ValueError(f"Immutable task_id is not in verified contract: {task_id}")
        if int(item.get("revision") or 0) != int(task.get("revision") or 1):
            raise ValueError(f"Immutable revision mismatch for {task_id}.")

    manifest["verified_package_contract"] = {
        "path": "verified_package_contract.json",
        "sha256": _sha256(contract_path),
    }
    manifest["approval_changed"] = False
    manifest["published"] = False
    _write_json(manifest_path, manifest)

    target = output.resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="completed-drafts-", dir=target.parent) as temp:
        candidate = Path(temp) / "completed_drafts.zip"
        with zipfile.ZipFile(candidate, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for member in sorted(members):
                archive.write(source / Path(*PurePosixPath(member).parts), member)
        validation = UniversalExternalWriterImporter(root=project_root).validate_zip(candidate)
        if validation.get("status") != "VALIDATION_PASS":
            raise ValueError(
                "Rebuilt ZIP still contains blockers: "
                + json.dumps(validation.get("rejected", []), ensure_ascii=False)
            )
        shutil.copy2(candidate, target)
    return {
        "status": "PASS",
        "package_id": package_id,
        "task_count": len(items),
        "output": str(target),
        "sha256": _sha256(target),
        "validation": validation,
    }
