from __future__ import annotations

import json
import hashlib
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from modules.entity_knowledge_base import entity_id
from modules.affiliate_opportunity_discovery import (
    AffiliateOpportunityDiscovery,
    research_affiliate_program,
)
from modules.research_artifacts import ResearchArtifactResolution, resolve_research_artifacts
from modules.research_enrichment import ResearchEnrichmentPipeline, SourceRetriever
from modules.source_classification import (
    OFFICIAL_SOURCE_TYPES,
    canonical_source_type,
    classify_source,
    source_content_is_soft_404,
    source_content_matches_type,
    source_directly_relevant,
)


APPROVED = {"verified", "approved"}
MANUAL_SOURCE_FAMILIES = {
    "product_page",
    "official_docs",
    "pricing_page",
    "affiliate_program_page",
    "security_page",
    "integration_page",
    "independent_evidence",
}


def _read(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return default


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


class SourceReviewOperator:
    """Operator-facing source review over canonical per-task research artifacts."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.data = self.root / "data"

    def _current_batch_date(self) -> str:
        """Latest dated daily batch directory, without scanning or resolving history."""
        candidates: list[str] = []
        for path in (self.data / "editorial_queue").glob("*/topics.json"):
            name = path.parent.name
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", name):
                candidates.append(name)
        return max(candidates) if candidates else ""

    def _daily_topic_rows(self, *, include_ready: bool) -> list[dict[str, Any]]:
        """Current actionable targets that exist only in the daily queue, not in write_queue."""
        current_date = self._current_batch_date()
        if not current_date:
            return []
        topics_path = self.data / "editorial_queue" / current_date / "topics.json"
        payload = _read(topics_path, {})
        rows: list[dict[str, Any]] = []
        for topic in (payload.get("topics") or []) if isinstance(payload, dict) else []:
            if not isinstance(topic, dict):
                continue
            slug = str(topic.get("slug") or "").strip()
            if not slug:
                continue
            readiness = topic.get("article_readiness") if isinstance(topic.get("article_readiness"), dict) else {}
            if bool(readiness.get("draft_exportable")) and not include_ready:
                continue
            task = {
                "task_id": str(readiness.get("task_id") or topic.get("task_id") or ""),
                "task_type": str(topic.get("task_type") or "WEBSITE_ADVANCED"),
                "article_slug": slug,
                "slug": slug,
                "title": str(topic.get("title") or slug),
                "batch_date": str(topic.get("batch_date") or current_date),
                "root_topic_id": str(topic.get("root_topic_id") or ""),
                "parent_slug": str(topic.get("parent_slug") or ""),
                "source_article_slug": str(topic.get("source_article_slug") or ""),
                "daily_angle": str(topic.get("daily_angle") or ""),
                "task_path": str(topics_path.resolve()),
            }
            try:
                resolution = self.resolve(task)
            except Exception:
                continue
            rows.append(self._task_view(task, resolution, task_path=topics_path))
        return rows

    def tasks(self, *, include_ready: bool = False, scope: str = "current") -> list[dict[str, Any]]:
        rows: dict[str, dict[str, Any]] = {}
        for path in (self.data / "write_queue").glob("*.json"):
            if path.name == "index.json":
                continue
            task = _read(path, {})
            if not isinstance(task, dict) or not str(task.get("task_type") or "").startswith("WEBSITE_"):
                continue
            slug = str(task.get("article_slug") or task.get("slug") or "").strip()
            if not slug:
                continue
            current = rows.get(slug)
            if current and str(current.get("batch_date") or "") > str(task.get("batch_date") or ""):
                continue
            resolution = self.resolve(task)
            if include_ready or not resolution.draft_exportable:
                rows[slug] = self._task_view(task, resolution, task_path=path)
        current_date = self._current_batch_date()
        for row in self._daily_topic_rows(include_ready=include_ready):
            existing = rows.get(row["slug"])
            if existing and str(existing.get("batch_date") or "") > str(row.get("batch_date") or ""):
                continue
            rows[row["slug"]] = row
        if scope == "all":
            return sorted(rows.values(), key=lambda row: (row["batch_date"], row["slug"]), reverse=True)
        if not current_date:
            return sorted(rows.values(), key=lambda row: (row["batch_date"], row["slug"]), reverse=True)
        filtered = [
            row for row in rows.values() if str(row.get("batch_date") or "") == current_date
        ]
        return sorted(filtered, key=lambda row: (row["batch_date"], row["slug"]), reverse=True)

    def resolve(self, task: dict[str, Any]) -> ResearchArtifactResolution:
        return resolve_research_artifacts(
            self.root,
            task_id=str(task.get("task_id") or ""),
            slug=str(task.get("article_slug") or task.get("slug") or ""),
            batch_date=str(task.get("batch_date") or ""),
        )

    def candidates(self, slug: str) -> list[dict[str, Any]]:
        payload = _read(self.data / "research" / slug / "sources.json", {})
        plan = _read(self.data / "research" / slug / "ANGLE_RESEARCH_PLAN.json", {})
        entity_names = [
            str(row.get("canonical_name") or "").strip()
            for row in [
                plan.get("root_entity") or {},
                *(plan.get("required_evidence_entities") or []),
                *(plan.get("required_comparator_entities") or []),
            ]
            if isinstance(row, dict) and str(row.get("canonical_name") or "").strip()
        ] if isinstance(plan, dict) else []
        entity_names = list(dict.fromkeys(entity_names))
        if not entity_names:
            package = _read(self.data / "research" / slug / "package.json", {})
            entities = package.get("entities", {}) if isinstance(package, dict) else {}
            entity_names = list(entities.get("products") or entities.get("ai_tools") or []) if isinstance(entities, dict) else []
        trusted = payload.get("trusted_sources", {}) if isinstance(payload, dict) else {}
        result: list[dict[str, Any]] = []
        if isinstance(trusted, dict):
            for family, rows in trusted.items():
                for row in rows if isinstance(rows, list) else []:
                    if not isinstance(row, dict) or not str(row.get("url") or "").strip():
                        continue
                    result.append(classify_source({**row, "declared_family": family, "family": family}, entity_names))
        return result

    def add_manual_source(
        self,
        task_view: dict[str, Any],
        *,
        url: str,
        entity_name: str,
        source_family: str,
        reviewer: str = "operator",
        retriever: Any | None = None,
    ) -> dict[str, Any]:
        """Validate, persist and recalculate a manually supplied source.

        A successful HTTP response is only retrieval evidence.  It is never
        enough to mark a URL verified or official without ownership,
        relevance, soft-404 and family/content validation.
        """
        slug = str(task_view.get("slug") or "").strip()
        entity_name = re.sub(r"\s+", " ", str(entity_name or "")).strip()
        family = canonical_source_type(source_family, url)
        normalized_url = self._normalize_url(url)
        requested_family = re.sub(r"[\s-]+", "_", str(source_family or "").strip().casefold())
        validation = {
            "schema_version": "manual_source_verification_v1",
            "passes": False,
            "url": normalized_url,
            "entity_name": entity_name,
            "requested_source_family": requested_family,
            "classified_source_family": family,
            "checked_at": datetime.now(UTC).isoformat(),
            "checks": {},
            "failure_reasons": [],
        }
        if not slug:
            return self._manual_failure("", validation, "TASK_SLUG_MISSING")
        if requested_family not in MANUAL_SOURCE_FAMILIES:
            return self._manual_failure(slug, validation, "UNSUPPORTED_SOURCE_FAMILY")
        if family != requested_family:
            return self._manual_failure(
                slug,
                validation,
                f"SOURCE_TYPE_MISMATCH: requested {requested_family}, URL classifies as {family}",
            )
        if not normalized_url:
            return self._manual_failure(slug, validation, "INVALID_PUBLIC_HTTP_URL")
        if not entity_name:
            return self._manual_failure(slug, validation, "ENTITY_REQUIRED")

        source_path = self.data / "research" / slug / "sources.json"
        payload = _read(source_path, {})
        if not isinstance(payload, dict):
            payload = {}
        existing_urls = {
            self._normalize_url(str(row.get("url") or row.get("source_url") or row.get("canonical_url") or ""))
            for row in self._all_source_rows(payload)
        }
        if normalized_url in existing_urls:
            return {
                "status": "DUPLICATE",
                "added": False,
                "recalculated": False,
                "reason": "DUPLICATE_URL: source already exists in canonical inventory",
                "validation": validation,
            }

        source = {
            "url": normalized_url,
            "source_url": normalized_url,
            "canonical_url": normalized_url,
            "source_type": family,
            "source_family": family,
            "canonical_entity_id": entity_id(entity_name),
            "canonical_entity_name": entity_name,
            "brand": entity_name,
        }
        active_retriever = retriever or SourceRetriever(
            cache_dir=self.data / "research_cache" / "source_content"
        )
        retrieved = active_retriever.retrieve(source, refresh=True, reuse_cache=False)
        retrieval_status = str(retrieved.get("retrieval_status") or "")
        content = str(retrieved.get("content") or "")
        validation["checks"]["retrieval"] = {
            "passes": retrieval_status in {"retrieved", "not_modified_cache"},
            "status": retrieval_status,
            "http_status": int(retrieved.get("http_status") or 0),
            "final_url": str(retrieved.get("final_url") or normalized_url),
            "error": str(retrieved.get("error") or ""),
        }
        if not validation["checks"]["retrieval"]["passes"]:
            return self._manual_failure(
                slug,
                validation,
                f"RETRIEVAL_FAILED: {retrieved.get('error') or retrieval_status or 'unknown error'}",
            )

        final_url = self._normalize_url(str(retrieved.get("final_url") or normalized_url))
        source.update({"url": final_url, "source_url": final_url, "canonical_url": final_url})
        final_family = canonical_source_type(requested_family, final_url)
        validation["checks"]["final_url_family"] = {
            "passes": final_family == requested_family,
            "final_url": final_url,
            "classified_source_family": final_family,
        }
        if final_family != requested_family:
            return self._manual_failure(
                slug,
                validation,
                f"SOURCE_TYPE_MISMATCH_AFTER_REDIRECT: requested {requested_family}, final URL classifies as {final_family}",
            )
        if final_url != normalized_url and final_url in existing_urls:
            return {
                "status": "DUPLICATE",
                "added": False,
                "recalculated": False,
                "reason": "DUPLICATE_URL: redirected source already exists in canonical inventory",
                "validation": validation,
            }
        soft_404 = source_content_is_soft_404(content)
        validation["checks"]["soft_404"] = {"passes": not soft_404}
        if soft_404:
            return self._manual_failure(slug, validation, "SOFT_404_OR_FALLBACK_PAGE")

        classified = classify_source(source, [entity_name])
        official_family = family in OFFICIAL_SOURCE_TYPES
        domain_match = bool(classified.get("official_ownership_verified"))
        direct_relevance = source_directly_relevant(classified, [entity_name], content=content)
        validation["checks"]["entity_domain"] = {
            "passes": domain_match if official_family else direct_relevance,
            "official_family": official_family,
            "domain_match": domain_match,
            "direct_relevance": direct_relevance,
        }
        if official_family and not domain_match:
            return self._manual_failure(slug, validation, "WRONG_ENTITY_DOMAIN")
        if not official_family and not direct_relevance:
            return self._manual_failure(slug, validation, "ENTITY_NOT_FOUND_IN_INDEPENDENT_EVIDENCE")

        content_match = source_content_matches_type(classified, content)
        validation["checks"]["source_family_content"] = {
            "passes": content_match,
            "source_family": family,
        }
        if not content_match:
            return self._manual_failure(slug, validation, "SOURCE_TYPE_CONTENT_MISMATCH")

        now = datetime.now(UTC).isoformat()
        validation["passes"] = True
        entry = {
            **classified,
            "source_id": "manual-" + hashlib.sha256(final_url.casefold().encode("utf-8")).hexdigest()[:16],
            "title": f"{entity_name} {family.replace('_', ' ')}",
            "label": f"{entity_name} {family.replace('_', ' ')} (manual)",
            "status": "verified",
            "verification_status": "verified",
            "provenance": "MANUAL_OPERATOR",
            "discovery_method": "manual_operator",
            "added_at": now,
            "added_by": reviewer,
            "verified_by": reviewer,
            "verification_date": now,
            "verification_result": validation,
        }
        trusted = payload.setdefault("trusted_sources", {})
        if not isinstance(trusted, dict):
            trusted = {}
            payload["trusted_sources"] = trusted
        family_rows = trusted.setdefault(family, [])
        if not isinstance(family_rows, list):
            family_rows = []
            trusted[family] = family_rows
        family_rows.append(entry)
        verified = payload.setdefault("verified_sources", [])
        if not isinstance(verified, list):
            verified = []
            payload["verified_sources"] = verified
        verified.append(entry)
        payload["manual_source_schema_version"] = "manual_operator_source_v1"
        _write(source_path, payload)
        self._audit(
            slug,
            "MANUAL_SOURCE_ADDED",
            {
                "url": final_url,
                "entity_name": entity_name,
                "source_family": family,
                "provenance": "MANUAL_OPERATOR",
                "verification_result": validation,
            },
        )
        try:
            resolution = self.refresh(task_view)
        except Exception as exc:
            self._audit(
                slug,
                "MANUAL_SOURCE_RECALCULATION_FAILED",
                {"url": final_url, "error": f"{type(exc).__name__}: {exc}"},
            )
            return {
                "status": "ADDED_RECALCULATION_FAILED",
                "added": True,
                "recalculated": False,
                "reason": f"Source stored, but canonical recalculation failed: {type(exc).__name__}: {exc}",
                "source": entry,
                "validation": validation,
            }
        affiliate_discovery: dict[str, Any] | None = None
        if family == "affiliate_program_page":
            try:
                discovery = AffiliateOpportunityDiscovery(self.root)
                program = research_affiliate_program(self.root, slug)
                signal = discovery.extract_signal(
                    f"{entity_name} affiliate program",
                    source_url_value=final_url,
                    source_platform="MANUAL_OPERATOR",
                    entity=entity_name,
                    product=entity_name,
                )
                if signal:
                    opportunity_score = discovery.score(signal, program)
                    strategy = discovery.recommend_strategy(signal, program, opportunity_score)
                    affiliate_discovery = discovery.save_analysis(
                        {
                            "signal_detected": True,
                            "signal": signal,
                            "program": program,
                            "score": opportunity_score,
                            "strategy": strategy,
                        }
                    )
            except (OSError, ValueError, TypeError) as exc:
                affiliate_discovery = {
                    "saved": False,
                    "reason": f"AFFILIATE_DISCOVERY_FAIL_OPEN: {type(exc).__name__}: {exc}",
                }
        return {
            "status": "ADDED",
            "added": True,
            "recalculated": True,
            "reason": "Manual source validated and canonical research eligibility recalculated.",
            "source": entry,
            "validation": validation,
            "research_state": resolution.research_level,
            "draft_exportable": resolution.draft_exportable,
            "failing_gates": list(resolution.failing_gates),
            "affiliate_discovery": affiliate_discovery,
        }

    @staticmethod
    def _normalize_url(value: str) -> str:
        try:
            parsed = urlsplit(str(value or "").strip())
        except ValueError:
            return ""
        if parsed.scheme.casefold() not in {"http", "https"} or not parsed.hostname:
            return ""
        host = parsed.hostname.casefold().encode("idna").decode("ascii")
        port = f":{parsed.port}" if parsed.port else ""
        path = re.sub(r"/{2,}", "/", parsed.path or "").rstrip("/")
        return urlunsplit((parsed.scheme.casefold(), host + port, path, parsed.query, ""))

    @staticmethod
    def _all_source_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
        rows = [row for row in payload.get("verified_sources", []) if isinstance(row, dict)]
        trusted = payload.get("trusted_sources", {})
        if isinstance(trusted, dict):
            for family_rows in trusted.values():
                rows.extend(row for row in family_rows if isinstance(row, dict))
        return rows

    def _manual_failure(self, slug: str, validation: dict[str, Any], reason: str) -> dict[str, Any]:
        validation["failure_reasons"].append(reason)
        if slug:
            self._audit(
                slug,
                "MANUAL_SOURCE_REJECTED",
                {
                    "url": validation.get("url", ""),
                    "entity_name": validation.get("entity_name", ""),
                    "source_family": validation.get("requested_source_family", ""),
                    "reason": reason,
                    "verification_result": validation,
                },
            )
        return {
            "status": "VALIDATION_FAILED",
            "added": False,
            "recalculated": False,
            "reason": reason,
            "validation": validation,
        }

    def review_source(self, slug: str, url: str, *, approve: bool, reviewer: str = "operator") -> bool:
        path = self.data / "research" / slug / "sources.json"
        payload = _read(path, {})
        if not isinstance(payload, dict):
            return False
        changed = False
        candidate_by_url = {
            str(row.get("url") or row.get("source_url") or ""): row
            for row in self.candidates(slug)
        }
        trusted = payload.get("trusted_sources", {})
        for family, rows in trusted.items() if isinstance(trusted, dict) else []:
            for row in rows if isinstance(rows, list) else []:
                if not isinstance(row, dict) or str(row.get("url") or "").strip() != url:
                    continue
                row["status"] = "verified" if approve else "rejected"
                row["verification_status"] = row["status"]
                row["verified_by"] = reviewer
                row["verification_date"] = datetime.now(UTC).isoformat()
                changed = True
                if approve:
                    verified = payload.setdefault("verified_sources", [])
                    if isinstance(verified, list) and not any(
                        isinstance(item, dict) and str(item.get("url") or item.get("source_url") or "") == url
                        for item in verified
                    ):
                        verified.append({**row, **candidate_by_url.get(url, {}), "url": url})
                else:
                    verified = payload.get("verified_sources", [])
                    if isinstance(verified, list):
                        payload["verified_sources"] = [
                            item
                            for item in verified
                            if not (
                                isinstance(item, dict)
                                and str(item.get("url") or item.get("source_url") or "") == url
                            )
                        ]
        if changed:
            _write(path, payload)
            self._audit(slug, "SOURCE_APPROVED" if approve else "SOURCE_REJECTED", {"url": url, "reviewer": reviewer})
        return changed

    def refresh(self, task_view: dict[str, Any]) -> ResearchArtifactResolution:
        task_path = Path(task_view["task_path"])
        task = _read(task_path, {})
        approved = [row for row in self.candidates(task_view["slug"]) if str(row.get("status") or "").casefold() in APPROVED]
        urls = [str(row.get("url") or "") for row in approved if str(row.get("url") or "").startswith(("http://", "https://"))]
        if urls:
            task["primary_source_url"] = urls[0]
            task["supporting_source_urls"] = urls[1:]
        config = _read(self.root / "config" / "editorial_system.json", {})
        pipeline = ResearchEnrichmentPipeline(
            root=self.root,
            config=config,
            retriever=SourceRetriever(cache_dir=self.data / "research_cache" / "source_content"),
        )
        enrichment = pipeline.enrich_slug(
            task_view["slug"], task=task, refresh_sources=True, reuse_cache=True, dry_run=False
        )
        resolution = self.resolve(task)
        self.sync_task(
            task_view["slug"],
            resolution,
            unique_thesis=str(getattr(enrichment, "unique_thesis", "") or ""),
            unique_thesis_status=str(
                getattr(enrichment, "unique_thesis_status", "") or ""
            ),
        )
        self._audit(task_view["slug"], "RESEARCH_REFRESHED", {"draft_exportable": resolution.draft_exportable, "failing_gates": list(resolution.failing_gates)})
        return resolution

    def sync_task(
        self,
        slug: str,
        resolution: ResearchArtifactResolution,
        *,
        unique_thesis: str = "",
        unique_thesis_status: str = "",
    ) -> None:
        """Propagate only research readiness; editorial/approval/publish fields are untouched."""
        synced_at = datetime.now(UTC).isoformat()
        readiness_snapshot = {
            "status": resolution.status,
            "article_ready": resolution.article_ready,
            "draft_exportable": resolution.draft_exportable,
            "publishable_claims": resolution.claim_count,
            "usable_paragraphs": resolution.paragraph_count,
            "evidence_coverage_score": resolution.coverage_score,
            "entity_coverage_score": resolution.entity_coverage_score,
            "blockers": list(resolution.failing_gates),
            "research_level": resolution.research_level,
            "source_families": list(resolution.source_families),
            "total_source_count": resolution.total_source_count,
            "official_source_count": resolution.official_source_count,
            "verified_source_count": resolution.verified_source_count,
            "artifact_dir": str(resolution.canonical_dir),
            "readiness_scope": "ROOT_FOUNDATION",
            "evaluated_at": synced_at,
        }
        updates = {
            "research_artifact_status": resolution.status,
            "research_state": resolution.status,
            "research_level": resolution.research_level,
            "draft_exportable": resolution.draft_exportable,
            "research_paragraph_count": resolution.paragraph_count,
            "research_claim_count": resolution.claim_count,
            "research_coverage_score": resolution.coverage_score,
            "entity_coverage_score": resolution.entity_coverage_score,
            "source_review_failing_gates": list(resolution.failing_gates),
            "source_review_source_families": list(resolution.source_families),
            "source_review_total_sources": resolution.total_source_count,
            "source_review_official_sources": resolution.official_source_count,
            "source_review_verified_sources": resolution.verified_source_count,
            "source_review_scope": "ROOT_FOUNDATION",
            "source_review_synced_at": synced_at,
        }
        if unique_thesis:
            updates["unique_thesis"] = unique_thesis
            updates["unique_thesis_status"] = unique_thesis_status or "EVIDENCE_DERIVED"
        for path in (self.data / "write_queue").glob("*.json"):
            if path.name == "index.json":
                continue
            payload = _read(path, {})
            if isinstance(payload, dict) and str(payload.get("article_slug") or payload.get("slug") or "") == slug:
                existing_readiness = (
                    dict(payload.get("article_readiness") or {})
                    if isinstance(payload.get("article_readiness"), dict)
                    else {}
                )
                payload.update(updates)
                payload["article_readiness"] = {**existing_readiness, **readiness_snapshot}
                _write(path, payload)
        for path in (self.data / "editorial_queue").glob("*/topics.json"):
            payload = _read(path, {})
            changed = False
            for row in payload.get("topics", []) if isinstance(payload, dict) else []:
                if isinstance(row, dict) and str(row.get("slug") or "") == slug:
                    existing_readiness = (
                        dict(row.get("article_readiness") or {})
                        if isinstance(row.get("article_readiness"), dict)
                        else {}
                    )
                    row.update(updates)
                    row["article_readiness"] = {**existing_readiness, **readiness_snapshot}
                    changed = True
            if changed:
                _write(path, payload)

    def _task_view(
        self,
        task: dict[str, Any],
        resolution: ResearchArtifactResolution,
        *,
        task_path: Path,
    ) -> dict[str, Any]:
        quality = _read(resolution.canonical_dir / "research_quality.json", {})
        report = _read(resolution.canonical_dir / "enrichment_report.json", {})
        excerpts = _read(resolution.canonical_dir / "SOURCE_EXCERPTS.json", {})
        evidence_rows = excerpts.get("sources", []) if isinstance(excerpts, dict) else []
        entity_rows = report.get("entity_coverage", []) if isinstance(report, dict) else []
        per_entity = {
            str(row.get("canonical_entity_name") or row.get("canonical_name") or row.get("entity_name") or row.get("entity_id") or "").strip(): {
                "coverage": float(row.get("coverage_score") or 0),
                "sources": int(row.get("source_count") or 0),
                "claims": int(row.get("claim_count") or 0),
                "status": str(row.get("status") or ""),
            }
            for row in entity_rows if isinstance(row, dict)
            if str(row.get("canonical_entity_name") or row.get("canonical_name") or row.get("entity_name") or row.get("entity_id") or "").strip()
        }
        for name, metrics in per_entity.items():
            matched = [
                row for row in evidence_rows
                if isinstance(row, dict)
                and str(row.get("canonical_entity_name") or "").strip() == name
                and bool(row.get("official_ownership_verified"))
            ]
            metrics["source_families"] = sorted({
                str(row.get("source_type") or row.get("source_family") or "").strip()
                for row in matched
                if str(row.get("source_type") or row.get("source_family") or "").strip()
            })
            metrics["official_sources"] = [
                str(row.get("canonical_url") or row.get("url") or "").strip()
                for row in matched
                if str(row.get("canonical_url") or row.get("url") or "").strip()
            ]
        score_keys = (
            "total_verified_source_score",
            "official_docs_score",
            "pricing_source_score",
            "affiliate_source_score",
        )
        affiliate_program = research_affiliate_program(self.root, resolution.slug)
        report_blockers = [
            str(row).strip()
            for row in (report.get("blockers") or [])
            if str(row).strip()
        ] if isinstance(report, dict) else []
        research_tasks = [
            {
                "section": str(row.get("section") or "general"),
                "reason": str(row.get("reason") or ""),
                "recommended_source_families": list(row.get("recommended_source_families") or []),
            }
            for row in (report.get("research_tasks") or [])
            if isinstance(row, dict) and str(row.get("status") or "PENDING").upper() == "PENDING"
        ] if isinstance(report, dict) else []
        return {
            "task_id": str(task.get("task_id") or ""),
            "task_path": str(task_path.resolve()),
            "batch_date": str(task.get("batch_date") or ""),
            "slug": resolution.slug,
            "title": str(task.get("title") or task.get("article_title") or resolution.slug),
            "research_state": resolution.research_level,
            "total_sources": resolution.total_source_count,
            "official_sources": resolution.official_source_count,
            "verified_sources": int(quality.get("verified_source_count") or resolution.verified_source_count) if isinstance(quality, dict) else resolution.verified_source_count,
            "source_families": list(resolution.source_families),
            "evidence_coverage": resolution.coverage_score,
            "entity_coverage": resolution.entity_coverage_score,
            "entity_coverage_by_product": per_entity,
            "source_scores": {
                key: float(quality.get(key) or 0) for key in score_keys
            } if isinstance(quality, dict) else {},
            "unique_thesis": str(
                (report.get("angle_contract") or {}).get("unique_thesis")
                or report.get("unique_thesis")
                or ""
            ) if isinstance(report, dict) else "",
            "unique_thesis_status": str(report.get("unique_thesis_status") or "MISSING")
            if isinstance(report, dict) else "MISSING",
            "failing_gates": list(resolution.failing_gates) or list(resolution.critical_safety_violations),
            "canonical_blockers": report_blockers,
            "research_tasks": research_tasks,
            "draft_exportable": resolution.draft_exportable,
            "readiness_scope": "ROOT_FOUNDATION",
            "scheduled_angle_readiness": "NOT_EVALUATED_BY_SOURCE_REVIEW",
            "affiliate_program": affiliate_program,
        }

    def _audit(self, slug: str, action: str, details: dict[str, Any]) -> None:
        path = self.data / "reports" / "source_review" / "operator_audit.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"at": datetime.now(UTC).isoformat(), "slug": slug, "action": action, **details}, ensure_ascii=False) + "\n")
