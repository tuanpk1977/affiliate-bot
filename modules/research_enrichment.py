from __future__ import annotations

import hashlib
import ipaddress
import json
import re
import shutil
import time
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from modules.angle_research_planner import AngleResearchPlanner
from modules.entity_knowledge_base import EntityKnowledgeBase, EntityResolver, normalized_domain
from modules.official_source_registry import OfficialSourceRegistry, SOURCE_FAMILIES, normalize_family
from modules.research_artifacts import resolve_research_artifacts
from modules.research_readiness import (
    applicable_source_score_thresholds,
    classify_research_readiness,
    effective_entity_status,
)
from modules.source_classification import (
    OFFICIAL_SOURCE_TYPES,
    canonical_source_type,
    classify_source,
    official_seed_sources,
    source_content_matches_type,
    source_directly_relevant,
)
from modules.verified_source_acquisition import VerifiedSourceAcquisition


PLACEHOLDER_MARKERS = (
    "validated by weekly topic source-readiness preflight",
    "research package snapshot",
    "content planning snapshot",
    "affiliate placeholder",
    "{{",
    "}}",
)
TRANSIENT_STATUSES = {408, 425, 429, 500, 502, 503, 504}
ALLOWED_CONTENT_TYPES = (
    "text/html",
    "application/xhtml+xml",
    "text/plain",
    "text/markdown",
    "application/json",
    "application/rss+xml",
    "application/atom+xml",
    "application/xml",
    "text/xml",
)
CONFIDENCE_ENUMS = {"low", "medium", "high"}


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _write_json(path: Path, payload: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)
    return path


def _text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _norm(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def _unique(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = _text(value)
        key = _norm(cleaned)
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(cleaned)
    return result


@dataclass(frozen=True)
class ResearchValidationError:
    task_id: str
    slug: str
    source_id: str
    paragraph_id: str
    claim_id: str
    rule_id: str
    severity: str
    actual_value: Any
    expected_condition: str
    actionable_fix: str


@dataclass
class EnrichmentResult:
    task_id: str
    slug: str
    status: str
    article_ready: bool
    sources_attempted: int = 0
    sources_retrieved: int = 0
    sources_blocked: int = 0
    usable_paragraphs: int = 0
    candidate_claims: int = 0
    publishable_claims: int = 0
    rejected_claims: int = 0
    mandatory_sections_covered: int = 0
    mandatory_sections_total: int = 0
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    validation_errors: list[dict[str, Any]] = field(default_factory=list)
    artifact_dir: str = ""
    research_level: str = "BLOCKED_RESEARCH"
    draft_exportable: bool = False
    critical_safety_violations: list[str] = field(default_factory=list)
    research_tasks: list[dict[str, Any]] = field(default_factory=list)
    known_uncertainties: list[str] = field(default_factory=list)
    weak_sections: list[str] = field(default_factory=list)
    comparison_status: str = "NOT_APPLICABLE"
    identified_comparison_entities: list[str] = field(default_factory=list)
    official_sources_per_entity: dict[str, list[dict[str, str]]] = field(default_factory=dict)
    entity_coverage: list[dict[str, Any]] = field(default_factory=list)
    source_family_counts: dict[str, int] = field(default_factory=dict)
    evidence_coverage_score: float = 0.0
    estimated_publish_readiness: float = 0.0
    revision_count: int = 0
    unique_thesis: str = ""
    unique_thesis_status: str = "MISSING"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class SourceRetriever:
    def __init__(
        self,
        *,
        cache_dir: Path,
        timeout_seconds: float = 12,
        retries: int = 2,
        max_response_bytes: int = 2_000_000,
        stale_after_days: int = 14,
        user_agent: str = "SmileAIReviewHub-ResearchBot/1.0 (local editorial research)",
        session: Any | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.cache_dir = cache_dir
        self.timeout_seconds = timeout_seconds
        self.retries = max(0, retries)
        self.max_response_bytes = max_response_bytes
        self.stale_after_days = stale_after_days
        self.user_agent = user_agent
        self.session = session or requests.Session()
        self.sleep = sleep

    @staticmethod
    def cache_key(url: str) -> str:
        return hashlib.sha256(url.strip().encode("utf-8")).hexdigest()

    def retrieve(
        self,
        source: dict[str, Any],
        *,
        refresh: bool = False,
        reuse_cache: bool = True,
    ) -> dict[str, Any]:
        url = _text(source.get("canonical_url") or source.get("source_url") or source.get("url"))
        cache_path = self.cache_dir / f"{self.cache_key(url)}.json"
        cached = _read_json(cache_path, {})
        if reuse_cache and not refresh and self._cache_usable(cached, url):
            return {**cached, "retrieval_status": "cache_hit", "cache_path": str(cache_path)}
        if not self._is_public_http_url(url):
            return self._failure(url, "invalid_url", "Only public HTTP/HTTPS approved sources are supported.")

        headers = {"User-Agent": self.user_agent, "Accept": ", ".join(ALLOWED_CONTENT_TYPES)}
        if self._cache_matches(cached, url):
            if cached.get("etag"):
                headers["If-None-Match"] = str(cached["etag"])
            if cached.get("last_modified"):
                headers["If-Modified-Since"] = str(cached["last_modified"])
        last_error = ""
        for attempt in range(self.retries + 1):
            try:
                response = self.session.get(
                    url,
                    headers=headers,
                    timeout=self.timeout_seconds,
                    allow_redirects=True,
                    stream=True,
                )
                status = int(response.status_code)
                if status == 304 and self._cache_matches(cached, url):
                    payload = {
                        **cached,
                        "retrieval_status": "not_modified_cache",
                        "retrieved_at": _now(),
                        "http_status": 304,
                    }
                    _write_json(cache_path, payload)
                    return {**payload, "cache_path": str(cache_path)}
                if status in TRANSIENT_STATUSES and attempt < self.retries:
                    self.sleep(min(2**attempt, 4))
                    continue
                if status < 200 or status >= 300:
                    return self._failure(url, "http_error", f"HTTP {status}", status=status)
                final_url = _text(getattr(response, "url", url))
                if not self._is_public_http_url(final_url):
                    return self._failure(url, "unsafe_redirect", "Redirected outside public HTTP/HTTPS.")
                content_type = _text(response.headers.get("Content-Type")).split(";", 1)[0].casefold()
                if content_type and not any(content_type.startswith(item) for item in ALLOWED_CONTENT_TYPES):
                    return self._failure(
                        url,
                        "unsupported_content_type",
                        f"Unsupported content type: {content_type}",
                        status=status,
                    )
                body = bytearray()
                for chunk in response.iter_content(chunk_size=65536):
                    if not chunk:
                        continue
                    body.extend(chunk)
                    if len(body) > self.max_response_bytes:
                        return self._failure(
                            url,
                            "response_too_large",
                            f"Response exceeds {self.max_response_bytes} bytes.",
                            status=status,
                        )
                encoding = getattr(response, "encoding", None) or "utf-8"
                text = bytes(body).decode(encoding, errors="replace")
                payload = {
                    "url": url,
                    "final_url": final_url,
                    "retrieval_status": "retrieved",
                    "retrieved_at": _now(),
                    "http_status": status,
                    "content_type": content_type or "unknown",
                    "content_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                    "content": text,
                    "etag": _text(response.headers.get("ETag")),
                    "last_modified": _text(response.headers.get("Last-Modified")),
                    "warnings": [],
                }
                _write_json(cache_path, payload)
                return {**payload, "cache_path": str(cache_path)}
            except (requests.Timeout, requests.ConnectionError) as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                if attempt < self.retries:
                    self.sleep(min(2**attempt, 4))
                    continue
            except requests.RequestException as exc:
                return self._failure(url, "request_error", f"{type(exc).__name__}: {exc}")
        if reuse_cache and self._cache_matches(cached, url):
            return {
                **cached,
                "retrieval_status": "stale_cache_fallback",
                "warnings": [f"Network unavailable; stale cache reused: {last_error}"],
                "cache_path": str(cache_path),
            }
        return self._failure(url, "network_unavailable", last_error or "Network unavailable.")

    def _cache_matches(self, cached: dict[str, Any], url: str) -> bool:
        return bool(cached and _text(cached.get("url")) == url and _text(cached.get("content")))

    def _cache_usable(self, cached: dict[str, Any], url: str) -> bool:
        if not self._cache_matches(cached, url):
            return False
        try:
            retrieved = datetime.fromisoformat(str(cached["retrieved_at"]).replace("Z", "+00:00"))
        except (KeyError, TypeError, ValueError):
            return False
        return datetime.now(UTC) - retrieved <= timedelta(days=self.stale_after_days)

    @staticmethod
    def _failure(url: str, code: str, reason: str, *, status: int = 0) -> dict[str, Any]:
        return {
            "url": url,
            "final_url": url,
            "retrieval_status": "blocked",
            "retrieved_at": _now(),
            "http_status": status,
            "content_type": "",
            "content_hash": "",
            "content": "",
            "error_code": code,
            "error": reason,
            "warnings": [],
        }

    @staticmethod
    def _is_public_http_url(url: str) -> bool:
        parsed = urlparse(url)
        host = (parsed.hostname or "").casefold()
        if parsed.scheme not in {"http", "https"} or not host:
            return False
        if host in {"localhost", "localhost.localdomain"} or host.endswith((".local", ".internal")):
            return False
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            return True
        return not (
            address.is_private
            or address.is_loopback
            or address.is_link_local
            or address.is_reserved
            or address.is_multicast
        )


class ResearchEnrichmentPipeline:
    def __init__(
        self,
        *,
        root: Path,
        data_dir: Path | None = None,
        config: dict[str, Any] | None = None,
        retriever: SourceRetriever | None = None,
    ) -> None:
        self.root = root
        self.data_dir = data_dir or root / "data"
        self.config = config or {}
        cfg = self.config.get("research_enrichment", self.config)
        self.minimum_claims = int(cfg.get("minimum_publishable_claims", 20))
        self.maximum_claims = min(100, int(cfg.get("maximum_publishable_claims", 100)))
        self.maximum_expanded_sources = int(cfg.get("maximum_expanded_sources", 12))
        self.minimum_coverage_score = float(cfg.get("minimum_coverage_score", 0.65))
        self.maximum_research_passes = int(cfg.get("maximum_research_passes", 3))
        self.maximum_zero_gain_passes = int(cfg.get("maximum_zero_gain_passes", 2))
        self.kb = EntityKnowledgeBase(
            self.data_dir / "entity_knowledge_base",
            freshness_days=int(cfg.get("knowledge_freshness_days", 90)),
        )
        self.registry = OfficialSourceRegistry(
            self.data_dir / "official_source_registry.json"
        )
        self.angle_planner = AngleResearchPlanner(root=root, data_dir=self.data_dir)
        self.retriever = retriever or SourceRetriever(
            cache_dir=self.data_dir / "research_cache" / "source_content",
            timeout_seconds=float(cfg.get("timeout_seconds", 12)),
            retries=int(cfg.get("retries", 2)),
            max_response_bytes=int(cfg.get("max_response_bytes", 2_000_000)),
            stale_after_days=int(cfg.get("stale_after_days", 14)),
            user_agent=str(cfg.get("user_agent") or "SmileAIReviewHub-ResearchBot/1.0"),
        )

    def enrich_slug(
        self,
        slug: str,
        *,
        task: dict[str, Any] | None = None,
        refresh_sources: bool = False,
        reuse_cache: bool = True,
        dry_run: bool = False,
    ) -> EnrichmentResult:
        task = dict(task or {})
        task_id = _text(task.get("task_id") or slug)
        artifact_resolution = resolve_research_artifacts(
            self.root,
            task_id=task_id,
            slug=slug,
            batch_date=_text(task.get("batch_date")),
        )
        package_dir = artifact_resolution.canonical_dir
        migration_source = ""
        if not artifact_resolution.package_file.is_file():
            for legacy_dir in artifact_resolution.duplicate_dirs:
                legacy_package = legacy_dir / "package.json"
                if not legacy_package.is_file():
                    continue
                package_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(legacy_package, artifact_resolution.package_file)
                migration_source = str(legacy_dir)
                break
        package = _read_json(package_dir / "package.json", {})
        if not isinstance(package, dict) or not package:
            return EnrichmentResult(
                task_id=task_id,
                slug=slug,
                status="BLOCKED_RESEARCH",
                article_ready=False,
                blockers=[f"Research package not found: {package_dir / 'package.json'}"],
                artifact_dir=str(package_dir),
            )
        # sources.json is the canonical, operator-reviewable source inventory.
        # package.json may contain an older generation-time snapshot, so always
        # overlay the canonical inventory before classification and scoring.
        canonical_sources = _read_json(package_dir / "sources.json", {})
        if isinstance(canonical_sources, dict) and canonical_sources:
            package = {**package, "sources": canonical_sources}
        angle_plan = self.angle_planner.build(
            package, task, persist_report=not dry_run
        )
        task["_angle_research_plan"] = angle_plan
        if not dry_run:
            _write_json(package_dir / "ANGLE_RESEARCH_PLAN.json", angle_plan)
        evidence_entities = list(angle_plan.get("required_evidence_entities") or [])
        entity = _text(
            (evidence_entities[0] if evidence_entities else angle_plan.get("root_entity", {})).get(
                "canonical_name"
            )
        ) or self._primary_entity(package, task)
        inventory = self._source_inventory(package, task)
        root_record = angle_plan.get("root_entity") or {}
        planned_entity_rows = evidence_entities or [
            root_record,
            *(angle_plan.get("required_comparator_entities") or []),
        ]
        evidence_root_record = planned_entity_rows[0] if planned_entity_rows else root_record
        planned_entity_names = [
            _text(row.get("canonical_name"))
            for row in planned_entity_rows
            if _text(row.get("canonical_name"))
        ]
        planned_roles = {
            _text(row.get("entity_id")): _text(row.get("entity_role"))
            for row in planned_entity_rows
        }
        result_official_sources = {
            _text(row.get("canonical_name")): [
                {
                    "source_url": _text(source.get("source_url")),
                    "source_type": _text(source.get("source_type")),
                }
                for source in row.get("official_sources") or []
                if _text(source.get("source_url"))
            ]
            for row in planned_entity_rows
            if _text(row.get("canonical_name"))
        }
        # Reclassify ownership from the actual compared products.  Legacy
        # inventories often stamped every URL with the broad topic root.
        # BUT: Preserve verified vendor ownership. Sources with
        # official_ownership_verified=True already have correct entity binding.
        normalized_inventory: list[dict[str, Any]] = []
        for row in inventory:
            # Skip reclassification for sources that already have verified vendor ownership
            if row.get("official_ownership_verified") and _text(row.get("canonical_entity_name")):
                # Keep the verified entity binding, just ensure entity_role is set
                entity_key = _text(row.get("canonical_entity_id"))
                normalized_inventory.append(
                    {
                        **row,
                        "entity_role": planned_roles.get(entity_key, "independent"),
                    }
                )
            else:
                classified = classify_source(row, planned_entity_names)
                entity_key = _text(classified.get("canonical_entity_id"))
                normalized_inventory.append(
                    {
                        **classified,
                        "entity_role": planned_roles.get(entity_key, "independent"),
                    }
                )
        inventory = normalized_inventory
        inventory = self._merge_inventory(
            inventory, self.angle_planner.inventory_sources(angle_plan)
        )
        explicit_domains_for_plan = {
            _text(row.get("entity_id")): list(row.get("official_domains") or [])
            for row in planned_entity_rows
        }
        classified_inventory: list[dict[str, Any]] = []
        for row in inventory:
            # Preserve verified vendor ownership during reclassification
            if row.get("official_ownership_verified") and _text(row.get("canonical_entity_name")):
                entity_key = _text(row.get("canonical_entity_id"))
                classified_inventory.append(
                    {
                        **row,
                        "entity_role": planned_roles.get(entity_key, "independent"),
                    }
                )
            else:
                classified = classify_source(
                    row,
                    planned_entity_names,
                    explicit_domains=explicit_domains_for_plan,
                )
                classified_inventory.append(
                    {
                        **classified,
                        "entity_role": planned_roles.get(
                            _text(classified.get("canonical_entity_id")),
                            "independent",
                        ),
                    }
                )
        seeded: list[dict[str, Any]] = []
        owned_entity_ids = {
            _text(row.get("canonical_entity_id"))
            for row in classified_inventory
            if row.get("official_ownership_verified")
        }
        for entity_row in planned_entity_rows:
            entity_key = _text(entity_row.get("entity_id"))
            if entity_key in owned_entity_ids:
                continue
            seeded.extend(
                official_seed_sources(
                    _text(entity_row.get("canonical_name")),
                    entity_row.get("official_domains") or [],
                )
            )
        # Seed only when an entity has no first-party candidate at all. This
        # restores root coverage without multiplying requests for inventories
        # that already contain validated official evidence.
        if seeded:
            inventory = self._merge_inventory(classified_inventory, seeded)
            classified_inventory = []
            for row in inventory:
                # Preserve verified vendor ownership during reclassification after seeding
                if row.get("official_ownership_verified") and _text(row.get("canonical_entity_name")):
                    entity_key = _text(row.get("canonical_entity_id"))
                    classified_inventory.append(
                        {
                            **row,
                            "entity_role": planned_roles.get(entity_key, "independent"),
                        }
                    )
                else:
                    classified = classify_source(
                        row,
                        planned_entity_names,
                        explicit_domains=explicit_domains_for_plan,
                    )
                    classified_inventory.append(
                        {
                            **classified,
                            "entity_role": planned_roles.get(
                                _text(classified.get("canonical_entity_id")),
                                "independent",
                            ),
                        }
                    )
        inventory = classified_inventory
        if comparison_plan := bool(
            angle_plan.get("required_comparator_entities")
            or angle_plan.get("required_evidence_entities")
        ):
            classified_inventory = [
                row
                for row in inventory
                if source_directly_relevant(row, planned_entity_names)
            ]
            owned = [
                row for row in classified_inventory
                if row.get("official_ownership_verified")
            ]
            independent = [
                row for row in classified_inventory
                if not row.get("official_ownership_verified")
            ]
            # Keep enough bounded capacity to try each official family for
            # every compared entity, including common localized/partner URL
            # variants.  A root-first truncation previously starved later
            # comparators before their pricing/affiliate candidates ran.
            source_limit = max(
                self.maximum_expanded_sources,
                len(planned_entity_names) * 10 + 6,
            )
            entity_order = {
                _text(row.get("entity_id")): index
                for index, row in enumerate(planned_entity_rows)
            }
            official_family_order = {
                "product_page": 0,
                "official_docs": 1,
                "pricing_page": 2,
                "affiliate_program_page": 3,
                "api_docs": 4,
                "release_notes": 5,
            }
            owned.sort(
                key=lambda row: (
                    official_family_order.get(_text(row.get("source_type")), 9),
                    entity_order.get(_text(row.get("canonical_entity_id")), 99),
                    _text(row.get("source_url")),
                )
            )
            inventory = self._merge_inventory(owned, independent[:3])[:source_limit]
        else:
            source_limit = self.maximum_expanded_sources
        initial_urls = [
            _text(row.get("source_url") or row.get("canonical_url"))
            for row in inventory
            if _text(row.get("source_url") or row.get("canonical_url"))
        ]
        resolution = self.kb.resolver.resolve(
            entity,
            # Resolve ownership from the canonical root only. Full article-title aliases
            # can be shared by stale legacy profiles such as "<entity>-and".
            aliases=[entity],
            source_urls=[
                _text(row.get("source_url") or row.get("canonical_url"))
                for row in inventory
                if _text(row.get("canonical_entity_id")) == _text(evidence_root_record.get("entity_id"))
                and normalized_domain(_text(row.get("source_url") or row.get("canonical_url"))) != "github.com"
            ],
        )
        concrete_entity = bool(entity and entity != "unknown")
        if concrete_entity:
            inventory = self._merge_inventory(inventory, self.registry.sources_for(entity))
        family_priority = {
            normalize_family(family): index
            for index, family in enumerate(angle_plan.get("required_source_families") or [])
        }
        inventory.sort(
            key=lambda row: (
                family_priority.get(
                    normalize_family(
                        _text(row.get("source_family") or row.get("source_type"))
                    ),
                    len(family_priority) + 1,
                ),
                0 if _text(row.get("entity_role")) == "root" else 1,
                _text(row.get("source_url")),
            )
        )
        result = EnrichmentResult(
            task_id=task_id,
            slug=slug,
            status="SOURCES_DISCOVERED",
            article_ready=False,
            sources_attempted=len(inventory),
            artifact_dir=str(package_dir),
            official_sources_per_entity=result_official_sources,
        )
        retrieval_rows: list[dict[str, Any]] = []
        excerpts: list[dict[str, Any]] = []
        seen_hashes: set[str] = set()
        expansion_rows: list[dict[str, Any]] = []
        pages_reused = 0
        pages_refreshed = 0
        source_index = 0
        while source_index < len(inventory):
            source = inventory[source_index]
            source_index += 1
            retrieved = self.retriever.retrieve(
                source,
                refresh=refresh_sources,
                reuse_cache=reuse_cache,
            )
            retrieval_rows.append({key: value for key, value in retrieved.items() if key != "content"})
            if retrieved.get("retrieval_status") in {"cache_hit", "not_modified_cache"}:
                pages_reused += 1
            elif retrieved.get("retrieval_status") == "retrieved":
                pages_refreshed += 1
            if retrieved.get("retrieval_status") == "blocked":
                result.sources_blocked += 1
                continue
            if (
                comparison_plan
                and not source.get("official_ownership_verified")
                and not source_directly_relevant(
                    source,
                    planned_entity_names,
                    content=_text(retrieved.get("content")),
                )
            ):
                retrieval_rows[-1]["retrieval_status"] = "irrelevant_to_comparison_entities"
                retrieval_rows[-1]["warnings"] = [
                    "Independent source does not directly name a compared product."
                ]
                result.sources_blocked += 1
                continue
            content_hash = _text(retrieved.get("content_hash"))
            if content_hash in seen_hashes:
                retrieval_rows[-1]["retrieval_status"] = "duplicate_content"
                retrieval_rows[-1]["warnings"] = ["Duplicate of another approved source response."]
                continue
            seen_hashes.add(content_hash)
            expansion_source_types = {
                "official_docs",
                "pricing_page",
                "product_page",
                "release_notes",
                "affiliate_program_page",
                "api_docs",
                "official_website",
                "docs",
                "pricing",
                "github",
                "readme",
                "tutorial",
                "examples",
                "faq",
                "support",
            }
            if (
                len(inventory) < source_limit
                and _text(source.get("source_type")) in expansion_source_types
            ):
                discovered = self._merge_inventory(
                    self.discover_official_sources(
                        _text(retrieved.get("content")),
                        base_url=_text(retrieved.get("final_url")),
                        approved_inventory=inventory,
                    ),
                    self.discover_index_sources(
                        _text(retrieved.get("content")),
                        base_url=_text(retrieved.get("final_url")),
                        content_type=_text(retrieved.get("content_type")),
                    ),
                )
                for candidate in discovered:
                    classified_candidate = classify_source(
                        candidate,
                        planned_entity_names,
                        explicit_domains=explicit_domains_for_plan if comparison_plan else None,
                    )
                    classified_candidate.update(
                        {
                            "canonical_entity_id": source.get("canonical_entity_id"),
                            "canonical_entity_name": source.get("canonical_entity_name"),
                            "entity_role": source.get("entity_role") or "root",
                        }
                    )
                    before = len(inventory)
                    inventory = self._merge_inventory(inventory, [classified_candidate])
                    if len(inventory) > before:
                        expansion_rows.append(
                            {
                                "discovered_from": source.get("source_url"),
                                "source_url": classified_candidate["source_url"],
                                "source_family": classified_candidate["source_type"],
                                "discovery_method": classified_candidate.get("discovery_method", "approved_official_link"),
                                "official_domain_status": "approved",
                                "intended_missing_section": self._section_for_family(
                                    classified_candidate["source_type"]
                                ),
                                "reason": "Official-family link discovered from an approved official source.",
                                "rejection_reason": "",
                            }
                        )
                    if len(inventory) >= source_limit:
                        break
            paragraphs, metadata = self.extract_paragraphs(
                _text(retrieved.get("content")),
                content_type=_text(retrieved.get("content_type")),
                task=task,
                package=package,
            )
            if not paragraphs:
                retrieval_rows[-1]["retrieval_status"] = "no_usable_paragraphs"
                result.sources_blocked += 1
                continue
            paragraph_text = " ".join(_text(row.get("text")) for row in paragraphs)
            if (
                source.get("official_ownership_verified")
                and _text(source.get("source_type")) in OFFICIAL_SOURCE_TYPES
                and not source_content_matches_type(source, paragraph_text)
            ):
                retrieval_rows[-1]["retrieval_status"] = "source_type_content_mismatch"
                retrieval_rows[-1]["warnings"] = [
                    "Retrieved page does not contain evidence for its claimed official source family."
                ]
                result.sources_blocked += 1
                continue
            result.sources_retrieved += 1
            # Ensure unique source_id: prefer existing, but avoid collisions
            base_id = _text(source.get("source_id")) or f"source-{len(excerpts) + 1:03d}"
            used_ids = {_text(e.get("source_id")) for e in excerpts}
            source_id = base_id
            suffix = 1
            while source_id in used_ids:
                suffix += 1
                source_id = f"{base_id}-{suffix}"
            excerpt_rows = [
                {
                    "paragraph_id": f"{source_id}-p{index:03d}",
                    "paragraph_order": index,
                    "text": paragraph["text"],
                    "heading_context": paragraph.get("heading_context", ""),
                    "relevance_tags": paragraph.get("relevance_tags", []),
                    "extraction_confidence": paragraph.get("extraction_confidence", "medium"),
                }
                for index, paragraph in enumerate(paragraphs, start=1)
            ]
            excerpts.append(
                {
                    "source_id": source_id,
                    "title": _text(source.get("title") or metadata.get("title") or retrieved.get("final_url")),
                    "canonical_url": _text(retrieved.get("final_url")),
                    "url": _text(retrieved.get("final_url")),
                    "source_type": _text(source.get("source_type") or "approved_web_source"),
                    "source_family": normalize_family(
                        _text(source.get("source_family") or source.get("source_type"))
                    ),
                    # A row reaches SOURCE_EXCERPTS only after successful
                    # retrieval, ownership matching (for official families),
                    # usable paragraph extraction, and content/type checks.
                    "verification_status": "verified",
                    "canonical_entity_id": _text(source.get("canonical_entity_id")),
                    "canonical_entity_name": _text(source.get("canonical_entity_name")),
                    "entity_role": _text(source.get("entity_role") or "root"),
                    "author": _text(metadata.get("author") or source.get("author")),
                    "publication_date": _text(metadata.get("publication_date") or source.get("publication_date")),
                    "retrieved_at": retrieved.get("retrieved_at"),
                    "http_status": retrieved.get("http_status"),
                    "content_hash": content_hash,
                    "paragraphs": excerpt_rows,
                    "extracted_relevant_paragraphs": [row["text"] for row in excerpt_rows],
                    "allowed_usage": "Paraphrase only the directly supported statement and attribute it to this URL.",
                    "limitations": (
                        "Company-authored material is evidence of the company's public description, "
                        "not independent proof of performance or comparative superiority."
                    ),
                    "freshness": _text(metadata.get("publication_date") or retrieved.get("retrieved_at")),
                    "confidence": "high" if source.get("verification_status") == "verified" else "medium",
                    "warnings": list(retrieved.get("warnings") or []),
                }
            )
        official_domains = list(evidence_root_record.get("official_domains") or [])
        if not official_domains:
            official_domains = list(resolution.get("official_domains") or [])
        entity_mismatches: list[str] = []
        planned_entities = {
            row["entity_id"]: row
            for row in planned_entity_rows
            if row.get("entity_id")
        }
        comparison_plan = bool(
            angle_plan.get("required_comparator_entities")
            or angle_plan.get("required_evidence_entities")
        )
        explicit_domains = {
            _text(row.get("entity_id")): list(row.get("official_domains") or [])
            for row in planned_entities.values()
        }
        for source in excerpts:
            claimed_entity_id = _text(source.get("canonical_entity_id"))
            owned = classify_source(
                source,
                planned_entity_names,
                explicit_domains=explicit_domains,
            )
            source.update(owned)
            source_entity_id = _text(source.get("canonical_entity_id"))
            planned_entity = planned_entities.get(source_entity_id, {})
            if source.get("official_ownership_verified"):
                classification = EntityResolver.classify_source(
                    _text(source.get("canonical_url")),
                    official_domains=list(planned_entity.get("official_domains") or []),
                    verified_github=[
                        urlparse(_text(row.get("source_url"))).path.strip("/")
                        for row in inventory
                        if normalized_domain(_text(row.get("source_url"))) == "github.com"
                    ],
                )
                source.update(classification)
            else:
                source.update(
                    {
                        "canonical_entity_id": "",
                        "canonical_entity_name": "",
                        "entity_role": "independent",
                        "entity_match_status": "INDEPENDENT",
                        "official_classification": "independent",
                        "domain_ownership_confidence": "not_applicable",
                        "contamination_warning": "",
                    }
                )
                # An official-family row explicitly attributed to a product
                # but hosted outside that product's owned domains is a real
                # contamination error. Independent reporting is not.
                if (
                    claimed_entity_id
                    and _text(owned.get("source_type")) in OFFICIAL_SOURCE_TYPES
                ):
                    entity_mismatches.append(_text(source.get("canonical_url")))
            source["canonical_entity_id"] = (
                source_entity_id
                or _text(planned_entity.get("entity_id"))
                or ("" if comparison_plan else resolution["canonical_entity_id"])
            )
            source["canonical_entity_name"] = (
                _text(source.get("canonical_entity_name"))
                or _text(planned_entity.get("canonical_name"))
                or ("" if comparison_plan else entity)
            )
            source["entity_role"] = (
                _text(source.get("entity_role"))
                or _text(planned_entity.get("entity_role"))
                or ("independent" if comparison_plan else "root")
            )
            source["source_family"] = normalize_family(_text(source.get("source_type")))
            if source["entity_match_status"] == "ENTITY_MISMATCH":
                entity_mismatches.append(_text(source.get("canonical_url")))
        # Report only official pages that were actually retrieved and
        # ownership/type matched.  Seed URLs are discovery candidates and must
        # never appear as acquired evidence merely because they were planned.
        acquired_official: dict[str, list[dict[str, str]]] = {
            name: [] for name in planned_entity_names
        }
        for source in excerpts:
            entity_name = _text(source.get("canonical_entity_name"))
            if not entity_name or not source.get("official_ownership_verified"):
                continue
            acquired_official.setdefault(entity_name, []).append(
                {
                    "url": _text(source.get("canonical_url") or source.get("url")),
                    "source_type": _text(source.get("source_type")),
                }
            )
        result.official_sources_per_entity = acquired_official
        result.usable_paragraphs = sum(len(row["paragraphs"]) for row in excerpts)
        result.sources_attempted = len(inventory)
        article_type = self._article_type(package, task)
        evidence_profile = self.evidence_profile(article_type)
        evidence_hash = hashlib.sha256(
            (
                "claim-extractor-v4|"
                + article_type
                + "|"
                + "|".join(
                    sorted(
                        "::".join(
                            (
                                _text(row.get("source_id")),
                                _text(row.get("canonical_url") or row.get("url")),
                                _text(row.get("content_hash")),
                            )
                        )
                        for row in excerpts
                    )
                )
            ).encode("utf-8")
        ).hexdigest()
        previous_report = _read_json(package_dir / "enrichment_report.json", {})
        previous_ledger = _read_json(package_dir / "FACT_LEDGER.json", {})
        cached_claims = previous_ledger.get("facts", []) if isinstance(previous_ledger, dict) else []
        claim_cache_reused = bool(
            not refresh_sources
            and previous_report.get("claim_cache_key") == evidence_hash
            and isinstance(cached_claims, list)
        )
        extraction_diagnostics: dict[str, Any] = {}
        new_claims = (
            cached_claims
            if claim_cache_reused
            else self.extract_claims(
                excerpts,
                package=package,
                task=task,
                maximum=self.maximum_claims,
                diagnostics=extraction_diagnostics,
            )
        )
        if claim_cache_reused:
            extraction_diagnostics = _read_json(
                package_dir / "claim_extraction_diagnostics.json", {}
            )
        required_categories = set(self._required_claim_categories(article_type))
        canonical_reuse = self._canonical_artifact_evidence(
            package_dir,
            entity_ids={
                _text(row.get("entity_id"))
                for row in planned_entity_rows
                if _text(row.get("entity_id"))
            },
            # Entity claim completeness is independent from angle coverage.
            # Preserve every valid bound claim here; angle-specific categories
            # are enforced separately below.
            required_categories=set(),
        )
        reusable = (
            self.kb.reusable_evidence(
                entity,
                article_intent=article_type,
                required_categories=required_categories,
                same_root_slug=_text(task.get("root_topic_id")),
            )
            if concrete_entity
            else {"sources": [], "claims": []}
        )
        if comparison_plan:
            reusable_sources = [
                row
                for row in reusable.get("sources", [])
                if source_directly_relevant(
                    row,
                    planned_entity_names,
                    content=" ".join(
                        _text(paragraph.get("text"))
                        for paragraph in row.get("paragraphs", [])
                        if isinstance(paragraph, dict)
                    ),
                )
            ]
            allowed_reused_source_ids = {
                _text(row.get("source_id")) for row in reusable_sources
            }
            reusable = {
                "sources": reusable_sources,
                "claims": [
                    row
                    for row in reusable.get("claims", [])
                    if _text(row.get("source_id") or row.get("original_source_id"))
                    in allowed_reused_source_ids
                ],
            }
        excerpts, canonical_reused_claims = self._merge_reused_evidence(
            excerpts,
            canonical_reuse["sources"],
            canonical_reuse["claims"],
        )
        excerpts, reused_claims = self._merge_reused_evidence(
            excerpts,
            reusable.get("sources", []),
            reusable.get("claims", []),
        )
        claims = self._deduplicate_claims(
            [*canonical_reused_claims, *new_claims, *reused_claims]
        )[: self.maximum_claims]
        newly_extracted_claim_count = 0 if claim_cache_reused else len(new_claims)
        blueprint = self.build_blueprint(package, task, claims, article_type=article_type)
        coverage = self.analyze_coverage(blueprint, claims, article_type=article_type)
        coverage_score = self.coverage_score(coverage)
        result.evidence_coverage_score = coverage_score
        entity_coverage = self.analyze_entity_coverage(
            angle_plan,
            claims=claims,
            sources=excerpts,
            blueprint=blueprint,
        )
        result.identified_comparison_entities = list(planned_entity_names)
        result.entity_coverage = list(entity_coverage["entities"])
        result.unique_thesis = _text(task.get("unique_thesis"))
        stored_thesis_status = _text(task.get("unique_thesis_status")).upper()
        result.unique_thesis_status = (
            stored_thesis_status
            if result.unique_thesis and stored_thesis_status in {"PROVIDED", "EVIDENCE_DERIVED"}
            else "PROVIDED" if result.unique_thesis else "MISSING"
        )
        if comparison_plan and not result.unique_thesis:
            result.unique_thesis = self.derive_comparison_thesis(entity_coverage)
            if result.unique_thesis:
                result.unique_thesis_status = "EVIDENCE_DERIVED"
                angle_plan["unique_thesis"] = result.unique_thesis
                angle_plan["unique_thesis_status"] = result.unique_thesis_status
        gaps = self.detect_gaps(
            coverage,
            inventory=inventory,
            retrieval_rows=retrieval_rows,
            sources=excerpts,
        )
        errors = self.validate_claims(
            task_id=task_id,
            slug=slug,
            claims=claims,
            sources=excerpts,
            blueprint=blueprint,
            package=package,
            task=task,
        )
        result.publishable_claims = len(claims)
        result.candidate_claims = int(
            extraction_diagnostics.get("candidate_claims_generated") or len(new_claims)
        )
        result.rejected_claims = int(
            extraction_diagnostics.get("candidate_claims_rejected") or 0
        )
        result.validation_errors = [asdict(error) for error in errors]
        sections = blueprint["sections"]
        result.mandatory_sections_total = sum(1 for row in sections if row["mandatory"])
        result.mandatory_sections_covered = sum(
            1 for row in coverage if row["strength"] in {"Weak", "Strong"} or row["safely_caveatable"]
        )
        if not inventory:
            result.blockers.append("No approved source inventory exists.")
        if not excerpts:
            result.blockers.append("No real readable source paragraphs were retrieved.")
        # An explicit comparison plan is canonical for its product set.  Old
        # aliases in the long-lived entity registry may make the generic root
        # resolver ambiguous, but that is not an ownership failure when every
        # acquired source independently matches one of the planned entities.
        resolution_failed = resolution.get("status") in {"AMBIGUOUS", "ENTITY_MISMATCH"}
        if (resolution_failed and not comparison_plan) or entity_mismatches:
            result.blockers.append(
                "Entity resolution failed or a source is outside verified entity ownership."
            )
        expected_claims = max(
            self.expected_claim_target(article_type),
            int(evidence_profile["minimum_direct_support_claims"]),
        )
        effective_claim_target = max(self.minimum_claims, expected_claims)
        if len(claims) < effective_claim_target:
            result.blockers.append(
                f"Only {len(claims)} directly supported claims; "
                f"{article_type} evidence target is {effective_claim_target}."
            )
        if errors:
            result.blockers.append(f"{len(errors)} deterministic claim validation error(s).")
        uncovered = [
            row["section_id"]
            for row in sections
            if row["mandatory"] and row["evidence_coverage_status"] == "blocked"
        ]
        if uncovered:
            result.blockers.append("Mandatory evidence sections blocked: " + ", ".join(uncovered))
        required_coverage_score = max(
            self.minimum_coverage_score,
            float(evidence_profile["minimum_coverage_score"]),
        )
        if coverage_score < required_coverage_score:
            result.blockers.append(
                f"Evidence coverage score {coverage_score:.2f} is below "
                f"the required {required_coverage_score:.2f}."
            )
        distinct_families = {
            normalize_family(_text(row.get("source_type")))
            for row in excerpts
            if _text(row.get("source_type"))
        }
        result.source_family_counts = dict(
            sorted(
                Counter(
                    canonical_source_type(
                        row.get("source_type"),
                        _text(row.get("canonical_url") or row.get("source_url")),
                    )
                    for row in excerpts
                    if _text(row.get("source_type"))
                ).items()
            )
        )
        if len(distinct_families) < int(evidence_profile["minimum_distinct_source_families"]):
            result.blockers.append(
                f"Only {len(distinct_families)} distinct source families; "
                f"{article_type} requires {evidence_profile['minimum_distinct_source_families']}."
            )
        if _text(task.get("daily_angle")):
            missing_angle_fields = [
                field
                for field in ("root_topic_id", "reader_question", "unique_thesis")
                if not _text(task.get(field))
                and not (field == "unique_thesis" and result.unique_thesis)
            ]
            if missing_angle_fields:
                result.blockers.append(
                    "Advanced article contract is incomplete: " + ", ".join(missing_angle_fields)
                )
        for blocker in angle_plan.get("planning_blockers") or []:
            result.blockers.append(f"Angle research plan blocked: {blocker}")
        for row in entity_coverage["entities"]:
            target = (angle_plan.get("entity_evidence_targets") or {}).get(
                row["canonical_entity_id"], {}
            )
            minimum_sources = int(target.get("minimum_official_sources") or 1)
            minimum_entity_claims = int(target.get("minimum_claims") or 1)
            minimum_entity_coverage = float(target.get("minimum_coverage_score") or 0)
            if row["source_count"] < minimum_sources:
                result.blockers.append(
                    f"Entity {row['canonical_entity_name']} has {row['source_count']} approved "
                    f"source(s); requires {minimum_sources}."
                )
            if row["claim_count"] < minimum_entity_claims:
                result.blockers.append(
                    f"Entity {row['canonical_entity_name']} has {row['claim_count']} accepted "
                    f"claim(s); requires {minimum_entity_claims}."
                )
            if (
                angle_plan.get("angle_profile") == "pricing_and_value"
                and "pricing" not in set(row.get("claim_categories") or [])
            ):
                result.blockers.append(
                    f"Entity {row['canonical_entity_name']} has no accepted pricing/cost/ROI claim."
                )
            if row["coverage_score"] < minimum_entity_coverage:
                result.blockers.append(
                    f"Entity {row['canonical_entity_name']} coverage {row['coverage_score']:.2f} "
                    f"is below {minimum_entity_coverage:.2f}."
                )
        prohibited_overlap = task.get("prohibited_overlap")
        prohibited_phrases = (
            [_text(row) for row in prohibited_overlap]
            if isinstance(prohibited_overlap, list)
            else [_text(prohibited_overlap)]
        )
        prohibited_phrases = [row for row in prohibited_phrases if len(_norm(row)) >= 20]
        overlapping_claims = [
            claim.get("claim_id")
            for claim in claims
            if any(
                _norm(phrase) in _norm(_text(claim.get("exact_statement")))
                for phrase in prohibited_phrases
            )
        ]
        if overlapping_claims:
            result.blockers.append(
                "Same-root prohibited overlap appears in claims: "
                + ", ".join(str(row) for row in overlapping_claims)
            )
        # Apply the same verified-source score gates during enrichment/dry-run
        # that ResearchArtifactResolution and Menu X use after artifacts are
        # written.  This prevents a refresh from reporting exportable while
        # the canonical quality report would immediately block it.
        source_scores_now = VerifiedSourceAcquisition().score_verified_rows(
            [
                {
                    **row,
                    "verification_status": "verified",
                    "source_url": _text(row.get("canonical_url") or row.get("source_url")),
                }
                for row in excerpts
            ]
        )
        source_gate = self.config.get("research_intelligence", {}).get(
            "verified_source_gate", {}
        )
        if source_gate:
            score_requirements = applicable_source_score_thresholds(
                source_gate,
                article_type=article_type,
                task=task,
                claim_categories={
                    _text(row.get("claim_category"))
                    for row in claims
                    if _text(row.get("claim_category"))
                },
            )
            for score_name, minimum in score_requirements.items():
                actual = float(source_scores_now.get(score_name) or 0)
                if actual < minimum:
                    result.blockers.append(
                        f"{score_name} {actual:g} is below required {minimum:g}."
                    )
        result.article_ready = not result.blockers
        weak_sections = [
            str(row.get("section_id") or "")
            for row in coverage
            if str(row.get("strength") or "") in {"Weak", "Missing"}
        ]
        comparison_required = (
            str(angle_plan.get("angle_profile") or "")
            == "comparison_and_alternatives"
        )
        verified_comparator_count = len(
            list(angle_plan.get("required_comparator_entities") or [])
        )
        readiness = classify_research_readiness(
            approved_source_count=len(excerpts),
            paragraph_count=result.usable_paragraphs,
            claim_count=len(claims),
            expected_claim_count=effective_claim_target,
            coverage_score=coverage_score,
            article_complete=result.article_ready,
            blockers=result.blockers,
            gaps=gaps,
            weak_sections=weak_sections,
            entity_status=effective_entity_status(
                resolver_status=str(resolution.get("status") or ""),
                comparison_plan=comparison_plan,
                entity_mismatches=entity_mismatches,
            ),
            comparison_required=comparison_required,
            verified_comparator_count=verified_comparator_count,
            validation_error_count=len(errors),
        )
        result.research_level = readiness.level
        result.draft_exportable = readiness.draft_exportable
        # Research levels describe how much material was recovered; they must
        # not override canonical ownership/source-quality gates.  Keep a
        # constrained first draft exportable for ordinary editorial gaps, but
        # never advertise export eligibility while a hard source/entity gate
        # is failing.
        hard_source_gate_markers = (
            "entity resolution failed",
            "angle research plan blocked",
            "approved source(s); requires",
            "total_verified_source_score",
            "official_docs_score",
            "pricing_source_score",
            "affiliate_source_score",
        )
        if any(
            marker in blocker.casefold()
            for blocker in result.blockers
            for marker in hard_source_gate_markers
        ):
            result.draft_exportable = False
        result.critical_safety_violations = list(
            readiness.critical_safety_violations
        )
        result.research_tasks = list(readiness.research_tasks)
        result.known_uncertainties = list(readiness.known_uncertainties)
        result.weak_sections = list(readiness.weak_sections)
        result.comparison_status = readiness.comparison_status
        result.estimated_publish_readiness = (
            readiness.estimated_publish_readiness
        )
        result.status = (
            "ARTICLE_READY"
            if result.article_ready
            else readiness.level
        )

        artifacts = {
            "source_inventory.json": {"schema_version": 2, "slug": slug, "sources": inventory},
            "source_retrieval_report.json": {
                "schema_version": 2,
                "slug": slug,
                "generated_at": _now(),
                "sources": retrieval_rows,
            },
            "SOURCE_EXCERPTS.json": {"schema_version": 2, "slug": slug, "sources": excerpts},
            "FACT_LEDGER.json": {"schema_version": 2, "slug": slug, "facts": claims},
            "ANGLE_RESEARCH_PLAN.json": angle_plan,
            "claim_extraction_diagnostics.json": extraction_diagnostics,
            "ARTICLE_BLUEPRINT.json": blueprint,
            "evidence_coverage.json": {
                "schema_version": 2,
                "slug": slug,
                "article_type": article_type,
                "expected_claim_target": effective_claim_target,
                "coverage_score": coverage_score,
                "minimum_coverage_score": required_coverage_score,
                "evidence_profile": evidence_profile,
                "sections": coverage,
                "entity_coverage_summary": {
                    key: value
                    for key, value in entity_coverage.items()
                    if key not in {"entities", "section_entity_matrix"}
                },
                "entity_coverage": entity_coverage["entities"],
                "section_entity_matrix": entity_coverage["section_entity_matrix"],
                "covered": result.mandatory_sections_covered,
                "total": result.mandatory_sections_total,
            },
            "evidence_gap_report.json": {
                "schema_version": 2,
                "slug": slug,
                "article_type": article_type,
                "gaps": gaps,
                "missing_sections": [row["section_id"] for row in coverage if row["strength"] == "Missing"],
                "missing_source_families": sorted(
                    {family for row in gaps for family in row.get("recommended_source_families", [])}
                ),
            },
            "research_tasks.json": {
                "schema_version": 1,
                "slug": slug,
                "research_level": result.research_level,
                "draft_exportable": result.draft_exportable,
                "comparison_status": result.comparison_status,
                "estimated_publish_readiness": result.estimated_publish_readiness,
                "tasks": result.research_tasks,
                "known_uncertainties": result.known_uncertainties,
                "weak_sections": result.weak_sections,
                "recommended_writer_policy": (
                    "Write only from verified facts. Omit or qualify every "
                    "uncertain item according to each task's recommended wording."
                ),
            },
            "source_expansion_report.json": {
                "schema_version": 2,
                "slug": slug,
                "initial_source_count": result.sources_attempted - len(expansion_rows),
                "expanded_source_count": len(expansion_rows),
                "source_families_attempted": sorted(
                    {normalize_family(_text(row.get("source_type"))) for row in inventory if _text(row.get("source_type"))}
                ),
                "source_expansion_ceiling_reached": len(inventory) >= source_limit,
                "discoveries": expansion_rows,
                "pages_reused": pages_reused,
                "pages_refreshed": pages_refreshed,
                "claims_reused": len(reused_claims),
                "new_claims": newly_extracted_claim_count,
                "research_passes": [
                    {
                        "pass": 1,
                        "urls_attempted": result.sources_attempted,
                        "successful_retrievals": result.sources_retrieved,
                        "claims_gained": len(new_claims),
                        "sections_improved": sum(1 for row in coverage if row["strength"] != "Missing"),
                        "zero_gain": not new_claims,
                    }
                ],
                "maximum_safe_passes": self.maximum_research_passes,
                "evidence_ceiling_reason": self._evidence_ceiling_reason(
                    result=result,
                    inventory=inventory,
                    expansion_rows=expansion_rows,
                    gaps=gaps,
                ),
            },
            "entity_profile.json": {
                "schema_version": 1,
                "entity_id": resolution["canonical_entity_id"],
                "canonical_name": resolution.get("canonical_name") or entity,
                "aliases": resolution.get("aliases", []),
                "official_domains": official_domains,
            },
            "entity_resolution_report.json": {
                "schema_version": 1,
                **resolution,
                "source_classifications": [
                    {
                        key: source.get(key)
                        for key in (
                            "source_id",
                            "canonical_url",
                            "entity_match_status",
                            "official_classification",
                            "domain_ownership_confidence",
                            "source_family",
                            "canonical_entity_id",
                            "contamination_warning",
                        )
                    }
                    for source in excerpts
                ],
            },
            "freshness_report.json": self.kb.freshness_report(entity),
            "conflicts_and_caveats.json": {
                "schema_version": 1,
                "conflicts": self.kb.load(entity).get("conflicts", []),
                "caveats": [row for row in gaps if row.get("safely_caveatable")],
            },
            "enrichment_report.json": {
                **result.as_dict(),
                "generated_at": _now(),
                "article_type": article_type,
                "claim_cache_key": evidence_hash,
                "claim_cache_reused": claim_cache_reused,
                "coverage_score": coverage_score,
                "registry_sources_reused": sum(1 for row in inventory if row.get("registry_reused")),
                "new_official_sources_discovered": len(expansion_rows),
                "cached_pages_reused": pages_reused,
                "pages_refreshed": pages_refreshed,
                "claims_reused": len(reused_claims),
                "new_claims": newly_extracted_claim_count,
                "claim_diagnostics": self.claim_diagnostics(claims),
                "claim_extraction_diagnostics": extraction_diagnostics,
                "angle_profile": angle_plan.get("angle_profile"),
                "required_entities": len(entity_coverage["entities"]),
                "entity_coverage": entity_coverage["entities"],
                "migration": {
                    "status": (
                        "MIGRATED"
                        if result.article_ready and (artifact_resolution.is_legacy or migration_source)
                        else (
                            "MIGRATION_BLOCKED"
                            if artifact_resolution.is_legacy or migration_source
                            else "CURRENT_SCHEMA"
                        )
                    ),
                    "source_path": migration_source,
                    "canonical_path": str(package_dir),
                    "legacy_reasons": list(artifact_resolution.legacy_reasons),
                    "source_preserved": True,
                },
                "angle_contract": {
                    key: (
                        result.unique_thesis
                        if key == "unique_thesis" and result.unique_thesis
                        else task.get(key)
                    )
                    for key in (
                        "root_topic_id",
                        "daily_angle",
                        "sequence_number",
                        "reader_question",
                        "unique_thesis",
                        "required_evidence",
                        "prohibited_overlap",
                        "next_article_bridge",
                    )
                },
                "angle_validation": {
                    "relevance_terms": self._relevance_terms(package, task),
                    "prohibited_overlap_claim_ids": overlapping_claims,
                    "passed": not overlapping_claims
                    and not any(
                        blocker.startswith("Advanced article contract is incomplete")
                        for blocker in result.blockers
                    ),
                },
            },
        }
        if not dry_run:
            for filename, payload in artifacts.items():
                _write_json(package_dir / filename, payload)
            quality = _read_json(package_dir / "research_quality.json", {})
            # Every excerpt here came from the pre-approved inventory and was
            # successfully retrieved (blocked/no-content rows never enter the
            # excerpt list). Re-score only those concrete, readable artifacts.
            verified_rows = list(excerpts)
            canonical_rows = [
                {
                    **row,
                    "verification_status": "verified",
                    "source_url": _text(
                        row.get("canonical_url") or row.get("source_url") or row.get("url")
                    ),
                }
                for row in verified_rows
            ]
            source_scores = VerifiedSourceAcquisition().score_verified_rows(canonical_rows)
            quality.update(
                {
                    "article_readiness_status": result.status,
                    "article_ready": result.article_ready,
                    "publishable_claim_count": len(claims),
                    "usable_paragraph_count": result.usable_paragraphs,
                    "evidence_validation_errors": len(errors),
                    "evidence_checked_at": _now(),
                    "verified_source_count": len(canonical_rows),
                    "official_source_count": len(
                        {
                            _text(row.get("source_url")).casefold().rstrip("/")
                            for row in canonical_rows
                            if row.get("official_classification") == "official"
                            and _text(row.get("source_url"))
                        }
                    ),
                    "verified_source_family_count": len(
                        {_text(row.get("source_type")) for row in canonical_rows if _text(row.get("source_type"))}
                    ),
                    "source_recovery_status": "verified_rebuilt" if canonical_rows else "no_verified_sources",
                    **source_scores,
                }
            )
            _write_json(package_dir / "research_quality.json", quality)
            if concrete_entity:
                self.registry.remember(
                    entity,
                    [
                        {
                            **source,
                            "source_family": source.get("source_type"),
                            "verification_status": source.get("verification_status") or "approved",
                        }
                        for source in excerpts
                        if _text(source.get("canonical_entity_id")) == _text(root_record.get("entity_id"))
                    ],
                )
            profile = self.kb.persist(
                entity,
                aliases=self._entity_terms(package, task),
                official_domains=official_domains,
                sources=[
                    row for row in excerpts
                    if not comparison_plan
                    or _text(row.get("canonical_entity_id")) == _text(root_record.get("entity_id"))
                ],
                claims=[
                    row for row in claims
                    if not comparison_plan
                    or _text(row.get("canonical_entity_id")) == _text(root_record.get("entity_id"))
                ],
                article_slug=slug,
                article_intent=article_type,
                product_category=_text(
                    next(
                        iter(
                            (
                                package.get("entities", {}).get("product_categories", [])
                                if isinstance(package.get("entities"), dict)
                                else []
                            )
                        ),
                        "",
                    )
                ),
            )
            artifacts["freshness_report.json"] = self.kb.freshness_report(entity)
            artifacts["conflicts_and_caveats.json"]["conflicts"] = profile.get("conflicts", [])
            _write_json(package_dir / "freshness_report.json", artifacts["freshness_report.json"])
            _write_json(
                package_dir / "conflicts_and_caveats.json",
                artifacts["conflicts_and_caveats.json"],
            )
        return result

    def enrich_batch(
        self,
        slugs: list[str],
        *,
        tasks: dict[str, dict[str, Any]] | None = None,
        refresh_sources: bool = False,
        reuse_cache: bool = True,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        rows: list[dict[str, Any]] = []
        for slug in slugs:
            try:
                result = self.enrich_slug(
                    slug,
                    task=(tasks or {}).get(slug),
                    refresh_sources=refresh_sources,
                    reuse_cache=reuse_cache,
                    dry_run=dry_run,
                )
            except Exception as exc:
                result = EnrichmentResult(
                    task_id=slug,
                    slug=slug,
                    status="BLOCKED_RESEARCH",
                    article_ready=False,
                    blockers=[f"Unexpected enrichment failure: {type(exc).__name__}: {exc}"],
                    artifact_dir=str(self.data_dir / "research" / slug),
                )
            rows.append(result.as_dict())
        return {
            "generated_at": _now(),
            "tasks_processed": len(rows),
            "article_ready": sum(1 for row in rows if row["article_ready"]),
            "blocked_research": sum(1 for row in rows if not row["article_ready"]),
            "items": rows,
        }

    def _source_inventory(self, package: dict[str, Any], task: dict[str, Any]) -> list[dict[str, Any]]:
        sources = package.get("sources") if isinstance(package.get("sources"), dict) else {}
        candidates: list[dict[str, Any]] = []
        for key in ("verified_sources", "verified_registry_records"):
            rows = sources.get(key)
            if isinstance(rows, list):
                candidates.extend(row for row in rows if isinstance(row, dict))
        trusted = sources.get("trusted_sources")
        if isinstance(trusted, dict):
            for source_type, rows in trusted.items():
                for row in rows if isinstance(rows, list) else []:
                    if isinstance(row, dict):
                        candidates.append({**row, "source_type": row.get("source_type") or source_type})
        approved_urls = [
            task.get("primary_source_url"),
            *(task.get("supporting_source_urls") or []),
        ]
        for url in approved_urls:
            if _text(url):
                candidates.append(
                    {
                        "source_url": url,
                        "title": _text(task.get("title")) or url,
                        "source_type": "editorially_approved",
                        "verification_status": "supplied",
                    }
                )
        result: list[dict[str, Any]] = []
        seen: set[str] = set()
        for row in candidates:
            url = _text(row.get("canonical_url") or row.get("source_url") or row.get("url"))
            status = _text(row.get("verification_status") or row.get("source_status") or row.get("status"))
            if not url or status.casefold() not in {"verified", "approved", "supplied"}:
                continue
            key = url.casefold().rstrip("/")
            if key in seen:
                continue
            seen.add(key)
            result.append(
                {
                    **row,
                    "source_id": _text(row.get("source_id") or row.get("id")) or f"source-{len(result) + 1:03d}",
                    "title": _text(row.get("title") or row.get("source_name") or row.get("label")) or url,
                    "canonical_url": url,
                    "source_url": url,
                    "verification_status": status or "supplied",
                }
            )
        return result

    def extract_paragraphs(
        self,
        content: str,
        *,
        content_type: str,
        task: dict[str, Any],
        package: dict[str, Any],
    ) -> tuple[list[dict[str, Any]], dict[str, str]]:
        metadata = {"title": "", "author": "", "publication_date": ""}
        if "html" in content_type or "<html" in content[:500].casefold():
            soup = BeautifulSoup(content, "html.parser")
            title = soup.find("title")
            metadata["title"] = _text(title.get_text(" ", strip=True) if title else "")
            for tag in soup.select(
                "script,style,noscript,nav,footer,aside,form,button,svg,canvas,"
                "[role=navigation],[role=banner],[role=contentinfo],"
                ".cookie,.cookies,.cookie-banner,.modal,.popup,.advertisement,.ads"
            ):
                tag.decompose()
            root = soup.find("article") or soup.find("main") or soup.body or soup
            raw: list[tuple[str, str]] = []
            heading = ""
            for node in root.find_all(["h1", "h2", "h3", "p", "li"]):
                text = _text(node.get_text(" ", strip=True))
                if node.name in {"h1", "h2", "h3"}:
                    heading = text
                    continue
                raw.append((text, heading))
        elif any(item in content_type for item in ("xml", "rss", "atom")):
            soup = BeautifulSoup(content, "xml")
            raw = []
            for entry in soup.find_all(["item", "entry"]):
                heading = _text((entry.find("title") or "").get_text(" ", strip=True) if entry.find("title") else "")
                for node in entry.find_all(["description", "summary", "content"]):
                    nested = BeautifulSoup(node.get_text(" ", strip=True), "html.parser")
                    for paragraph in nested.find_all(["p", "li"]) or [nested]:
                        raw.append((_text(paragraph.get_text(" ", strip=True)), heading))
        else:
            raw = [(block, "") for block in re.split(r"\n\s*\n+", content)]
        terms = self._relevance_terms(package, task)
        paragraphs: list[dict[str, Any]] = []
        seen: set[str] = set()
        for value, heading in raw:
            key = _norm(value)
            lowered = value.casefold()
            if (
                len(value) < 45
                or len(value.split()) < 8
                or key in seen
                or any(marker in lowered for marker in PLACEHOLDER_MARKERS)
                or self._looks_like_boilerplate(value)
            ):
                continue
            seen.add(key)
            tags = sorted({term for term in terms if term in lowered})[:8]
            paragraphs.append(
                {
                    "text": value[:4000],
                    "heading_context": heading,
                    "relevance_tags": tags,
                    "extraction_confidence": "high" if tags else "medium",
                }
            )
        relevant = [row for row in paragraphs if row["relevance_tags"]]
        return (relevant or paragraphs)[:120], metadata

    def extract_claims(
        self,
        sources: list[dict[str, Any]],
        *,
        package: dict[str, Any],
        task: dict[str, Any],
        maximum: int,
        diagnostics: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        claims: list[dict[str, Any]] = []
        seen: list[tuple[set[str], set[str]]] = []
        entities = self._entity_terms(package, task)
        counters = {
            "paragraphs_evaluated": 0,
            "sentences_evaluated": 0,
            "candidate_claims_generated": 0,
            "candidate_claims_accepted": 0,
            "candidate_claims_rejected": 0,
        }
        rejection_counts: dict[str, int] = {}
        rejection_samples: list[dict[str, Any]] = []

        def reject(
            rule_id: str,
            *,
            source: dict[str, Any],
            paragraph: dict[str, Any],
            statement: str,
            fix: str,
        ) -> None:
            counters["candidate_claims_rejected"] += 1
            rejection_counts[rule_id] = rejection_counts.get(rule_id, 0) + 1
            if len(rejection_samples) < 30:
                rejection_samples.append(
                    {
                        "rule_id": rule_id,
                        "source_id": _text(source.get("source_id")),
                        "paragraph_id": _text(paragraph.get("paragraph_id")),
                        "statement": statement[:500],
                        "actionable_fix": fix,
                    }
                )

        for source in sources:
            company_authored = source.get("source_type") not in {"competitor_article", "research_paper"}
            source_entity_id = _text(source.get("canonical_entity_id"))
            source_entity_name = _text(source.get("canonical_entity_name"))
            source_entity_role = _text(source.get("entity_role") or "root")
            source_entity_norm = _norm(source_entity_name)
            source_has_entity_anchor = bool(
                source_entity_norm
                and any(
                    source_entity_norm in _norm(
                        f"{paragraph.get('heading_context', '')} {paragraph.get('text', '')}"
                    )
                    for paragraph in source.get("paragraphs") or []
                )
            )
            for paragraph in source.get("paragraphs") or []:
                counters["paragraphs_evaluated"] += 1
                for sentence in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", paragraph["text"]):
                    statement = _text(sentence)
                    if not statement:
                        continue
                    counters["sentences_evaluated"] += 1
                    counters["candidate_claims_generated"] += 1
                    candidate_rejection = self._claim_candidate_rejection(statement)
                    if candidate_rejection:
                        fixes = {
                            "too_short": "Retrieve a complete explanatory sentence with at least eight words.",
                            "url_only": "Extract the factual sentence from the page body instead of the URL.",
                            "placeholder_marker": "Replace workflow or placeholder text with actual source prose.",
                            "no_alpha": "Use a sentence containing a factual natural-language statement.",
                        }
                        reject(
                            candidate_rejection,
                            source=source,
                            paragraph=paragraph,
                            statement=statement,
                            fix=fixes[candidate_rejection],
                        )
                        continue
                    tokens = set(_norm(statement).split())
                    numbers = set(re.findall(r"\d+(?:\.\d+)?", statement))
                    if any(
                        len(tokens & prior_tokens) / max(1, len(tokens | prior_tokens)) >= 0.82
                        and numbers == prior_numbers
                        for prior_tokens, prior_numbers in seen
                    ):
                        reject(
                            "semantic_duplicate",
                            source=source,
                            paragraph=paragraph,
                            statement=statement,
                            fix="Keep the stronger or fresher supporting sentence and remove the duplicate.",
                        )
                        continue
                    match_terms = _unique([source_entity_name, *entities])
                    matched, matched_id = self._claim_entity_binding(
                        source,
                        statement,
                        match_terms,
                        source_has_entity_anchor=source_has_entity_anchor,
                    )
                    if not matched:
                        heading_context = _norm(str(paragraph.get("heading_context") or ""))
                        matched, matched_id = self._claim_entity_binding(
                            source,
                            str(paragraph.get("heading_context") or ""),
                            match_terms,
                            source_has_entity_anchor=source_has_entity_anchor,
                        )
                    if not matched and source_has_entity_anchor and source_entity_name:
                        matched = source_entity_name
                        matched_id = source_entity_id
                    if not matched and entities:
                        reject(
                            "entity_not_resolved",
                            source=source,
                            paragraph=paragraph,
                            statement=statement,
                            fix=(
                                "Tag the approved source with canonical_entity_id and "
                                "canonical_entity_name, or retrieve a sentence that names the entity."
                            ),
                        )
                        continue
                    seen.append((tokens, numbers))
                    category = self._claim_category(statement)
                    claim_id = f"claim-{len(claims) + 1:03d}"
                    limitations = (
                        "Treat as the company's own public description; do not present it as an "
                        "independently verified performance, superiority, or outcome claim."
                        if company_authored
                        else "Use only within the scope and date stated in the supporting excerpt."
                    )
                    claims.append(
                        {
                            "claim_id": claim_id,
                            "canonical_entity_id": matched_id or "unresolved",
                            "canonical_entity_name": matched or source_entity_name,
                            "entity_role": source_entity_role,
                            "factual_statement": statement,
                            "normalized_factual_statement": statement,
                            "exact_statement": statement,
                            "source_id": source["source_id"],
                            "source_url": source["url"],
                            "paragraph_id": paragraph["paragraph_id"],
                            "paragraph_ids": [paragraph["paragraph_id"]],
                            "supporting_excerpt": statement,
                            "entity": (
                                matched
                                or _text(source.get("title"))
                                or _text(task.get("title") or package.get("keyword"))
                            ),
                            "claim_category": category,
                            "allowed_usage": "Paraphrase narrowly with attribution to the cited source URL.",
                            "limitations": limitations,
                            "prohibited_extrapolations": [
                                "Do not add unstated pricing, availability, performance, eligibility, or comparisons.",
                                "Do not convert marketing language into an independently verified benchmark.",
                            ],
                            "freshness": source.get("freshness") or "date_not_available",
                            "confidence": "medium" if company_authored else "high",
                            "evidence_strength": "direct_excerpt",
                            "conflict_status": "none_detected",
                            "article_section_ids": [],
                            "public_safe": True,
                            "verification_notes": "Supporting excerpt is an exact sentence from the cited paragraph.",
                            "company_authored": company_authored,
                        }
                    )
                    counters["candidate_claims_accepted"] += 1
                    if len(claims) >= maximum:
                        if diagnostics is not None:
                            diagnostics.update(
                                {
                                    "schema_version": 1,
                                    **counters,
                                    "rejection_counts_by_rule": rejection_counts,
                                    "rejection_samples": rejection_samples,
                                    "limit_reached": True,
                                }
                            )
                        return claims
        if diagnostics is not None:
            diagnostics.update(
                {
                    "schema_version": 1,
                    **counters,
                    "rejection_counts_by_rule": rejection_counts,
                    "rejection_samples": rejection_samples,
                    "limit_reached": False,
                }
            )
        return claims

    @staticmethod
    def _claim_entity_binding(
        source: dict[str, Any],
        text: str,
        entity_names: list[str],
        *,
        source_has_entity_anchor: bool,
    ) -> tuple[str, str]:
        """Bind claims to explicit source ownership before textual mentions.

        Short/common vendor names are matched case-sensitively so an ordinary
        lowercase verb cannot override a verified source/entity binding.
        """
        source_name = _text(source.get("canonical_entity_name"))
        source_id = _text(source.get("canonical_entity_id"))
        explicit_source_binding = bool(
            source_name
            and source_id
            and (
                source.get("official_ownership_verified")
                or _text(source.get("entity_match_status")).upper() == "MATCHED"
            )
        )
        if explicit_source_binding and source_has_entity_anchor:
            return source_name, source_id
        for name in entity_names:
            phrase = re.sub(r"\s+", " ", _text(name)).strip()
            if not phrase:
                continue
            compact = re.sub(r"[^a-z0-9]", "", phrase.casefold())
            flags = 0 if len(compact) <= 5 and " " not in phrase else re.IGNORECASE
            if re.search(rf"(?<![A-Za-z0-9]){re.escape(phrase)}(?![A-Za-z0-9])", text, flags):
                return name, _norm(name).replace(" ", "-")
        return "", ""

    def build_blueprint(
        self,
        package: dict[str, Any],
        task: dict[str, Any],
        claims: list[dict[str, Any]],
        *,
        article_type: str = "software_review",
    ) -> dict[str, Any]:
        outline = package.get("outline") if isinstance(package.get("outline"), dict) else {}
        hierarchy = outline.get("heading_hierarchy") if isinstance(outline.get("heading_hierarchy"), list) else []
        headings = [_text(row.get("heading")) for row in hierarchy if isinstance(row, dict) and _text(row.get("heading"))]
        mandatory = [
            ("product-identity", "Product identity", "Explain what the product/topic is."),
            ("core-workflow", "Core workflow", "Explain how the documented workflow operates."),
            ("feature-scope", "Feature scope", "Describe only supported capabilities."),
            ("limitations", "Limitations", "State documented limits and evidence gaps."),
            ("pricing", "Pricing discussion", "Use sourced pricing or require current-price verification."),
            ("alternatives", "Alternatives", "Frame alternatives without unsupported rankings."),
            ("pros", "Pros", "Derive advantages only from supported evidence."),
            ("cons", "Cons", "Derive cautions only from supported limitations."),
            ("final-recommendation", "Final recommendation", "Give conditional buying guidance."),
            ("faq", "FAQ", "Answer only questions supported by the ledger."),
        ]
        sections: list[dict[str, Any]] = []
        section_targets = self.section_claim_targets(article_type)
        categories = {
            "product-identity": {"identity", "general"},
            "core-workflow": {"workflow", "feature"},
            "feature-scope": {"feature", "integration"},
            "limitations": {"limitation"},
            "pricing": {"pricing"},
            "alternatives": {"alternative", "comparison"},
            "pros": {"feature", "workflow"},
            "cons": {"limitation"},
            "final-recommendation": {"identity", "feature", "workflow", "limitation"},
            "faq": {"identity", "feature", "workflow", "pricing", "integration", "limitation", "general"},
        }
        for index, (section_id, heading, purpose) in enumerate(mandatory, start=1):
            assigned = [
                row["claim_id"]
                for row in claims
                if row["claim_category"] in categories[section_id]
            ]
            caveatable = section_id in {"pricing", "alternatives", "limitations", "cons"}
            status = "covered" if assigned else ("caveated" if caveatable else "blocked")
            if section_id == "pricing" and not assigned:
                purpose += " No price may be stated; tell readers to verify the current official pricing page."
            sections.append(
                {
                    "section_id": section_id,
                    "order": index,
                    "heading": heading,
                    "purpose": purpose,
                    "required_questions": [purpose],
                    "minimum_evidence_requirement": section_targets.get(section_id, 1),
                    "assigned_claim_ids": assigned,
                    "required_evidence_claim_ids": assigned,
                    "assigned_source_ids": sorted(
                        {row["source_id"] for row in claims if row["claim_id"] in assigned}
                    ),
                    "evidence_coverage_status": status,
                    "unresolved_gaps": [] if assigned else [f"No direct {section_id} evidence available."],
                    "prohibited_claims": [
                        "Any pricing, feature, performance, comparison, or availability claim absent from FACT_LEDGER.json."
                    ],
                    "target_word_range": {"minimum": 120, "maximum": 450},
                    "mandatory": True,
                    "safely_caveatable": caveatable,
                }
            )
        for claim in claims:
            claim["article_section_ids"] = [
                row["section_id"] for row in sections if claim["claim_id"] in row["assigned_claim_ids"]
            ]
        return {
            "schema_version": 2,
            "article_type": article_type,
            "slug": _text(task.get("article_slug") or task.get("slug") or package.get("slug")),
            "title": _text(task.get("title") or package.get("keyword")),
            "source_outline_headings": headings,
            "sections": sections,
        }

    @staticmethod
    def section_claim_targets(article_type: str) -> dict[str, int]:
        profiles = {
            "software_review": {
                "product-identity": 2,
                "core-workflow": 3,
                "feature-scope": 5,
                "limitations": 3,
                "pricing": 2,
                "alternatives": 3,
                "pros": 2,
                "cons": 2,
                "final-recommendation": 1,
                "faq": 2,
            },
            "comparison": {
                "product-identity": 4,
                "core-workflow": 4,
                "feature-scope": 7,
                "limitations": 4,
                "pricing": 3,
                "alternatives": 3,
                "pros": 2,
                "cons": 2,
                "final-recommendation": 2,
                "faq": 2,
            },
            "top_list": {
                "product-identity": 5,
                "core-workflow": 4,
                "feature-scope": 8,
                "limitations": 4,
                "pricing": 3,
                "alternatives": 4,
                "pros": 3,
                "cons": 3,
                "final-recommendation": 2,
                "faq": 2,
            },
            "news": {
                "product-identity": 2,
                "core-workflow": 3,
                "feature-scope": 4,
                "limitations": 2,
                "pricing": 1,
                "alternatives": 1,
                "pros": 1,
                "cons": 1,
                "final-recommendation": 1,
                "faq": 2,
            },
            "tutorial": {
                "product-identity": 2,
                "core-workflow": 7,
                "feature-scope": 4,
                "limitations": 3,
                "pricing": 1,
                "alternatives": 1,
                "pros": 1,
                "cons": 2,
                "final-recommendation": 1,
                "faq": 2,
            },
            "deep_dive": {
                "product-identity": 3,
                "core-workflow": 6,
                "feature-scope": 8,
                "limitations": 4,
                "pricing": 2,
                "alternatives": 3,
                "pros": 2,
                "cons": 3,
                "final-recommendation": 2,
                "faq": 3,
            },
        }
        return profiles.get(article_type, profiles["software_review"])

    def expected_claim_target(self, article_type: str) -> int:
        configured = self.config.get("research_enrichment", self.config).get("article_type_claim_targets", {})
        defaults = {
            "software_review": 25,
            "comparison": 30,
            "top_list": 34,
            "news": 20,
            "tutorial": 24,
            "deep_dive": 32,
        }
        return int(configured.get(article_type, defaults.get(article_type, self.minimum_claims)))

    @staticmethod
    def evidence_profile(article_type: str) -> dict[str, Any]:
        profiles = {
            "software_review": (1, 25, 0, 0.65, 90, ["product-identity", "core-workflow", "feature-scope", "limitations", "final-recommendation"]),
            "comparison": (2, 30, 0, 0.70, 60, ["product-identity", "feature-scope", "limitations", "alternatives", "final-recommendation"]),
            "top_list": (3, 34, 0, 0.70, 60, ["product-identity", "feature-scope", "alternatives", "final-recommendation"]),
            "tutorial": (1, 24, 0, 0.68, 90, ["product-identity", "core-workflow", "feature-scope", "limitations"]),
            "deep_dive": (3, 32, 0, 0.72, 90, ["product-identity", "core-workflow", "feature-scope", "limitations", "final-recommendation"]),
            "news": (1, 20, 0, 0.65, 30, ["product-identity", "feature-scope", "final-recommendation"]),
            "social_package": (1, 8, 0, 0.60, 30, ["product-identity", "final-recommendation"]),
        }
        families, direct, high, coverage, freshness, mandatory = profiles.get(
            article_type, profiles["software_review"]
        )
        return {
            "article_type": article_type,
            "mandatory_sections": mandatory,
            "optional_sections": ["pricing", "alternatives", "pros", "cons", "faq"],
            "minimum_distinct_source_families": families,
            "minimum_core_identity_evidence": 2,
            "minimum_direct_support_claims": direct,
            "minimum_high_confidence_claims": high,
            "minimum_coverage_score": coverage,
            "conflict_tolerance": "no unresolved material conflicts",
            "freshness_limit_days": freshness,
            "cautious_language_substitution": ["pricing", "alternatives"],
        }

    @staticmethod
    def _article_type(package: dict[str, Any], task: dict[str, Any]) -> str:
        keyword_summary = package.get("keyword_summary")
        if not isinstance(keyword_summary, dict):
            keyword_summary = {}
        raw = _text(
            task.get("article_type")
            or task.get("content_type")
            or keyword_summary.get("article_type")
        ).casefold()
        title = _text(task.get("title") or package.get("keyword")).casefold()
        workflow_lane = _text(task.get("workflow_lane") or task.get("content_lane")).upper()
        task_type = _text(task.get("task_type")).upper()
        daily_angle = _text(task.get("daily_angle")).casefold()
        if "comparison" in raw or " vs " in title or "alternative" in title:
            return "comparison"
        if "list" in raw or title.startswith(("best ", "top ")):
            return "top_list"
        if "news" in raw or "announcement" in raw:
            return "news"
        if "tutorial" in raw or title.startswith(("how to ", "guide to ")):
            return "tutorial"
        if (
            task_type == "WEBSITE_FOUNDATION"
            or workflow_lane == "FOUNDATION_MAIN"
            or daily_angle == "main_review"
        ):
            return "software_review"
        if "deep" in raw or daily_angle:
            return "deep_dive"
        return "software_review"

    def analyze_coverage(
        self,
        blueprint: dict[str, Any],
        claims: list[dict[str, Any]],
        *,
        article_type: str,
    ) -> list[dict[str, Any]]:
        claim_map = {row["claim_id"]: row for row in claims}
        categories_by_section = {
            "product-identity": ["identity"],
            "core-workflow": ["workflow"],
            "feature-scope": ["feature", "integration"],
            "limitations": ["limitation", "compatibility"],
            "pricing": ["pricing"],
            "alternatives": ["alternative", "identity"],
            "pros": ["feature", "workflow"],
            "cons": ["limitation"],
            "final-recommendation": ["identity", "workflow"],
            "faq": ["identity", "workflow", "feature"],
        }
        rows: list[dict[str, Any]] = []
        for section in blueprint.get("sections", []):
            assigned = [
                claim_map[claim_id]
                for claim_id in section.get("assigned_claim_ids", [])
                if claim_id in claim_map
            ]
            target = int(section.get("minimum_evidence_requirement") or 1)
            if not assigned:
                strength = "Missing"
            elif len(assigned) < target:
                strength = "Weak"
            else:
                strength = "Strong"
            rows.append(
                {
                    "section_id": section["section_id"],
                    "heading": section["heading"],
                    "article_type": article_type,
                    "claim_target": target,
                    "claim_count": len(assigned),
                    "source_count": len({row["source_id"] for row in assigned}),
                    "strength": strength,
                    "required_claim_categories": categories_by_section.get(section["section_id"], ["general"]),
                    "minimum_evidence_strength": "direct_excerpt",
                    "available_claim_ids": [row["claim_id"] for row in assigned],
                    "missing_claim_categories": [
                        category
                        for category in categories_by_section.get(section["section_id"], ["general"])
                        if category not in {row.get("claim_category") for row in assigned}
                    ],
                    "safely_caveatable": bool(section.get("safely_caveatable")),
                    "unresolved_gaps": list(section.get("unresolved_gaps") or []),
                }
            )
        return rows

    @staticmethod
    def analyze_entity_coverage(
        angle_plan: dict[str, Any],
        *,
        claims: list[dict[str, Any]],
        sources: list[dict[str, Any]],
        blueprint: dict[str, Any],
    ) -> dict[str, Any]:
        entities = list(angle_plan.get("required_evidence_entities") or []) or [
            angle_plan.get("root_entity") or {},
            *(angle_plan.get("required_comparator_entities") or []),
        ]
        mandatory_sections = list(angle_plan.get("mandatory_sections") or [])
        blueprint_sections = {
            _text(row.get("section_id"))
            for row in blueprint.get("sections") or []
            if isinstance(row, dict)
        }
        required_sections = [
            section for section in mandatory_sections if section in blueprint_sections
        ]
        rows: list[dict[str, Any]] = []
        matrix: list[dict[str, Any]] = []
        for entity in entities:
            entity_key = _text(entity.get("entity_id"))
            entity_claims = [
                row
                for row in claims
                if _text(row.get("canonical_entity_id")) == entity_key
            ]
            entity_sources = [
                row
                for row in sources
                if _text(row.get("canonical_entity_id")) == entity_key
            ]
            covered_sections = sorted(
                {
                    section
                    for claim in entity_claims
                    for section in claim.get("article_section_ids") or []
                    if section in required_sections
                }
            )
            coverage_score = (
                round(len(covered_sections) / len(required_sections), 4)
                if required_sections
                else 0.0
            )
            rows.append(
                {
                    "canonical_entity_id": entity_key,
                    "canonical_entity_name": _text(entity.get("canonical_name")),
                    "entity_role": _text(entity.get("entity_role")),
                    "source_count": len({_text(row.get("source_id")) for row in entity_sources}),
                    "claim_count": len(entity_claims),
                    "claim_categories": sorted(
                        {
                            _text(row.get("claim_category"))
                            for row in entity_claims
                            if _text(row.get("claim_category"))
                        }
                    ),
                    "sections_covered": covered_sections,
                    "sections_required": required_sections,
                    "coverage_score": coverage_score,
                    "status": (
                        "MISSING"
                        if not entity_sources or not entity_claims
                        else "STRONG"
                        if coverage_score >= 0.60
                        else "WEAK"
                    ),
                }
            )
        for section in required_sections:
            matrix.append(
                {
                    "section_id": section,
                    "entities": {
                        row["canonical_entity_id"]: {
                            "claim_count": sum(
                                1
                                for claim in claims
                                if _text(claim.get("canonical_entity_id"))
                                == row["canonical_entity_id"]
                                and section in (claim.get("article_section_ids") or [])
                            ),
                            "covered": section in row["sections_covered"],
                        }
                        for row in rows
                    },
                    "balanced": (
                        bool(rows)
                        and len(rows) >= int(
                            angle_plan.get("required_entity_count") or len(rows)
                        )
                        and all(section in row["sections_covered"] for row in rows)
                    ),
                }
            )
        required_entity_count = int(
            angle_plan.get("required_entity_count") or len(rows)
        )
        return {
            "required_entity_count": required_entity_count,
            "resolved_entity_count": len(rows),
            "missing_required_entity_count": max(0, required_entity_count - len(rows)),
            "entities": rows,
            "section_entity_matrix": matrix,
            "balanced_section_coverage_score": (
                round(sum(bool(row["balanced"]) for row in matrix) / len(matrix), 4)
                if matrix
                else 0.0
            ),
        }

    @staticmethod
    def derive_comparison_thesis(entity_coverage: dict[str, Any]) -> str:
        """Derive a neutral comparison frame only from evidenced entities.

        This does not select a winner or manufacture a product claim.  It only
        turns claim categories represented in the evidence ledger into a
        comparison-specific editorial thesis.
        """
        rows = [
            row
            for row in entity_coverage.get("entities", [])
            if isinstance(row, dict)
        ]
        if len(rows) < 2 or any(
            int(row.get("source_count") or 0) < 1
            or int(row.get("claim_count") or 0) < 1
            for row in rows
        ):
            return ""
        category_sets = [
            {
                _text(value)
                for value in row.get("claim_categories", [])
                if _text(value) not in {"general", "identity"}
            }
            for row in rows
        ]
        shared = set.intersection(*category_sets) if category_sets else set()
        preferred = [
            value
            for value in ("workflow", "feature", "integration", "pricing", "limitation")
            if value in shared
        ]
        if len(preferred) < 2:
            return ""
        names = [_text(row.get("canonical_entity_name")) for row in rows]
        dimensions = (
            f"{preferred[0]} and {preferred[1]}"
            if len(preferred) == 2
            else ", ".join(preferred[:-1]) + f", and {preferred[-1]}"
        )
        return (
            f"Compare {', '.join(names[:-1])}, and {names[-1]} by their evidenced "
            f"{dimensions} tradeoffs instead of treating them as interchangeable automation tools."
        )

    @staticmethod
    def coverage_score(coverage: list[dict[str, Any]]) -> float:
        if not coverage:
            return 0.0
        points = 0.0
        for row in coverage:
            if row["strength"] == "Strong":
                points += 1.0
            elif row["strength"] == "Weak":
                points += 0.6
            elif row.get("safely_caveatable"):
                points += 0.25
        return round(points / len(coverage), 4)

    def _required_claim_categories(self, article_type: str) -> list[str]:
        mapping = {
            "software_review": ["identity", "workflow", "feature", "limitation", "pricing", "general"],
            "comparison": ["identity", "feature", "workflow", "limitation", "pricing", "alternative"],
            "top_list": ["identity", "feature", "workflow", "limitation", "alternative"],
            "tutorial": ["identity", "workflow", "feature", "limitation", "compatibility"],
            "deep_dive": ["identity", "workflow", "feature", "limitation", "compatibility", "general"],
            "news": ["identity", "feature", "availability", "general"],
        }
        return mapping.get(article_type, mapping["software_review"])

    @staticmethod
    def _deduplicate_claims(claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        seen: set[str] = set()
        for claim in claims:
            fingerprint = _norm(
                _text(claim.get("exact_statement") or claim.get("normalized_factual_statement"))
            )
            if not fingerprint or fingerprint in seen:
                continue
            seen.add(fingerprint)
            rows.append(claim)
        for index, row in enumerate(rows, start=1):
            row["claim_id"] = f"claim-{index:03d}"
        return rows

    def _merge_reused_evidence(
        self,
        current_sources: list[dict[str, Any]],
        reused_sources: list[dict[str, Any]],
        reused_claims: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        sources = list(current_sources)
        url_to_source = {
            _text(row.get("canonical_url") or row.get("url")).casefold().rstrip("/"): row
            for row in sources
        }
        source_id_map: dict[str, str] = {}
        paragraph_id_map: dict[tuple[str, str], str] = {}
        for reused in reused_sources:
            url = _text(reused.get("canonical_url") or reused.get("url"))
            key = url.casefold().rstrip("/")
            existing = url_to_source.get(key)
            old_source_id = _text(reused.get("source_id"))
            if existing:
                source_id_map[old_source_id] = _text(existing.get("source_id"))
                existing_paragraphs = {
                    hashlib.sha256(_text(row.get("text")).encode("utf-8")).hexdigest(): row
                    for row in existing.get("paragraphs", [])
                }
                for paragraph in reused.get("paragraphs", []):
                    fingerprint = hashlib.sha256(_text(paragraph.get("text")).encode("utf-8")).hexdigest()
                    if fingerprint in existing_paragraphs:
                        paragraph_id_map[(old_source_id, _text(paragraph.get("paragraph_id")))] = _text(
                            existing_paragraphs[fingerprint].get("paragraph_id")
                        )
                continue
            new_source_id = f"source-{len(sources) + 1:03d}"
            source_id_map[old_source_id] = new_source_id
            paragraphs = []
            for index, paragraph in enumerate(reused.get("paragraphs", []), start=1):
                old_paragraph_id = _text(paragraph.get("paragraph_id"))
                new_paragraph_id = f"{new_source_id}-p{index:03d}"
                paragraph_id_map[(old_source_id, old_paragraph_id)] = new_paragraph_id
                paragraphs.append({**paragraph, "paragraph_id": new_paragraph_id})
            copied = {
                **reused,
                "source_id": new_source_id,
                "paragraphs": paragraphs,
                "reused_from_entity_knowledge_base": True,
            }
            sources.append(copied)
            url_to_source[key] = copied
        claims: list[dict[str, Any]] = []
        for claim in reused_claims:
            old_source_id = _text(claim.get("source_id") or claim.get("original_source_id"))
            old_paragraph_id = _text(claim.get("paragraph_id"))
            new_source_id = source_id_map.get(old_source_id)
            new_paragraph_id = paragraph_id_map.get((old_source_id, old_paragraph_id))
            if not new_source_id or not new_paragraph_id:
                continue
            source = next((row for row in sources if row.get("source_id") == new_source_id), None)
            claims.append(
                {
                    **claim,
                    "source_id": new_source_id,
                    "source_url": _text((source or {}).get("canonical_url") or (source or {}).get("url")),
                    "paragraph_id": new_paragraph_id,
                    "paragraph_ids": [new_paragraph_id],
                }
            )
        return sources, claims

    def _canonical_artifact_evidence(
        self,
        package_dir: Path,
        *,
        entity_ids: set[str],
        required_categories: set[str],
    ) -> dict[str, list[dict[str, Any]]]:
        """Recover still-valid, explicitly bound evidence from canonical artifacts."""
        source_payload = _read_json(package_dir / "SOURCE_EXCERPTS.json", {})
        ledger_payload = _read_json(package_dir / "FACT_LEDGER.json", {})
        sources: list[dict[str, Any]] = []
        for source in source_payload.get("sources", []) if isinstance(source_payload, dict) else []:
            entity_key = _text(source.get("canonical_entity_id"))
            if (
                entity_key not in entity_ids
                or not source.get("official_ownership_verified")
                or _text(source.get("verification_status")).casefold()
                not in {"verified", "approved"}
            ):
                continue
            try:
                retrieved_at = datetime.fromisoformat(
                    _text(source.get("retrieved_at")).replace("Z", "+00:00")
                )
            except ValueError:
                continue
            if datetime.now(UTC) - retrieved_at > timedelta(days=self.kb.freshness_days):
                continue
            sources.append(source)
        source_map = {_text(row.get("source_id")): row for row in sources}
        claims: list[dict[str, Any]] = []
        for claim in ledger_payload.get("facts", []) if isinstance(ledger_payload, dict) else []:
            source = source_map.get(_text(claim.get("source_id")))
            if (
                not source
                or _text(claim.get("canonical_entity_id"))
                != _text(source.get("canonical_entity_id"))
                or (
                    required_categories
                    and _text(claim.get("claim_category")) not in required_categories
                )
            ):
                continue
            paragraph = next(
                (
                    row
                    for row in source.get("paragraphs", [])
                    if _text(row.get("paragraph_id")) == _text(claim.get("paragraph_id"))
                ),
                None,
            )
            excerpt = _text(claim.get("supporting_excerpt") or claim.get("exact_statement"))
            if not paragraph or not excerpt or excerpt not in _text(paragraph.get("text")):
                continue
            claims.append(claim)
        return {"sources": sources, "claims": claims}

    @staticmethod
    def claim_diagnostics(claims: list[dict[str, Any]]) -> dict[str, Any]:
        statements = [
            _norm(_text(row.get("exact_statement") or row.get("normalized_factual_statement")))
            for row in claims
        ]
        unique = {row for row in statements if row}
        source_counts: dict[str, int] = {}
        category_counts: dict[str, int] = {}
        strength_counts: dict[str, int] = {}
        marketing = 0
        for claim in claims:
            source_id = _text(claim.get("source_id"))
            category = _text(claim.get("claim_category") or "general")
            strength = _text(claim.get("evidence_strength") or "unknown")
            source_counts[source_id] = source_counts.get(source_id, 0) + 1
            category_counts[category] = category_counts.get(category, 0) + 1
            strength_counts[strength] = strength_counts.get(strength, 0) + 1
            if claim.get("company_authored"):
                marketing += 1
        total = len(claims)
        return {
            "total_claims": total,
            "unique_semantic_claims": len(unique),
            "duplicate_ratio": round(1 - (len(unique) / total), 4) if total else 0.0,
            "source_concentration": (
                round(max(source_counts.values()) / total, 4) if source_counts and total else 0.0
            ),
            "claim_category_diversity": len(category_counts),
            "claim_categories": category_counts,
            "official_marketing_concentration": round(marketing / total, 4) if total else 0.0,
            "evidence_strength_distribution": strength_counts,
        }

    def _evidence_ceiling_reason(
        self,
        *,
        result: EnrichmentResult,
        inventory: list[dict[str, Any]],
        expansion_rows: list[dict[str, Any]],
        gaps: list[dict[str, Any]],
    ) -> str:
        if result.article_ready:
            return "ARTICLE_READY achieved."
        if len(inventory) >= self.maximum_expanded_sources:
            return "Maximum approved-source expansion ceiling reached."
        if not expansion_rows:
            return "No additional approved official URLs were discovered."
        if all(row.get("strength") != "Strong" for row in gaps):
            return "Approved evidence remains insufficient after bounded expansion."
        return "Remaining gaps require unavailable, ambiguous, or prohibited evidence."

    def detect_gaps(
        self,
        coverage: list[dict[str, Any]],
        *,
        inventory: list[dict[str, Any]],
        retrieval_rows: list[dict[str, Any]],
        sources: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        present_families = {normalize_family(_text(row.get("source_type"))) for row in inventory}
        failures = {
            _text(row.get("url")): _text(row.get("error_code") or row.get("retrieval_status"))
            for row in retrieval_rows
            if row.get("retrieval_status") in {"blocked", "no_usable_paragraphs", "duplicate_content"}
        }
        family_by_section = {
            "product-identity": ["official_website", "docs", "github", "readme"],
            "core-workflow": ["docs", "tutorial", "examples", "readme"],
            "feature-scope": ["docs", "api_docs", "release_notes", "changelog"],
            "pricing": ["pricing"],
            "limitations": ["docs", "faq", "support", "github"],
            "alternatives": ["blog", "marketplace", "community"],
            "pros": ["docs", "examples", "tutorial"],
            "cons": ["faq", "support", "github"],
            "faq": ["faq", "docs", "support"],
            "final-recommendation": ["official_website", "docs", "pricing"],
        }
        gaps: list[dict[str, Any]] = []
        for row in coverage:
            if row["strength"] == "Strong":
                continue
            recommended = [
                family
                for family in family_by_section.get(row["section_id"], ["docs"])
                if family in SOURCE_FAMILIES and family not in present_families
            ]
            reasons: list[str] = []
            if row["claim_count"] == 0:
                reasons.append("Insufficient factual statements for this section.")
            else:
                reasons.append(
                    f"Only {row['claim_count']} supported claims; target is {row['claim_target']}."
                )
            if failures:
                reasons.append("One or more approved sources timed out, were unavailable, duplicated, or had no usable body text.")
            if recommended:
                reasons.append("Relevant official source families have not yet been discovered.")
            gaps.append(
                {
                    **row,
                    "reasons": reasons,
                    "failed_sources": failures,
                    "recommended_source_families": recommended,
                    "suggested_official_source_families": recommended,
                    "exhausted_source_families": sorted(
                        family
                        for family in family_by_section.get(row["section_id"], ["docs"])
                        if family in present_families
                    ),
                    "cautious_limitation_allowed": bool(row.get("safely_caveatable")),
                }
            )
        return gaps

    def discover_official_sources(
        self,
        content: str,
        *,
        base_url: str,
        approved_inventory: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if "<" not in content:
            return []
        soup = BeautifulSoup(content, "html.parser")
        base_host = (urlparse(base_url).hostname or "").casefold().removeprefix("www.")
        base_root = ".".join(base_host.split(".")[-2:])
        priority = {
            "official_docs": 1,
            "pricing_page": 2,
            "affiliate_program_page": 3,
            "api_docs": 4,
            "release_notes": 5,
            "product_page": 6,
            "github": 7,
            "readme": 8,
            "blog": 9,
            "community": 10,
        }
        rows: list[dict[str, Any]] = []
        for anchor in soup.find_all("a", href=True):
            url = urljoin(base_url, str(anchor.get("href") or "")).split("#", 1)[0]
            parsed = urlparse(url)
            host = (parsed.hostname or "").casefold().removeprefix("www.")
            if parsed.scheme not in {"http", "https"}:
                continue
            same_official_root = ".".join(host.split(".")[-2:]) == base_root
            github_allowed = host == "github.com" and bool(base_root)
            if not same_official_root and not github_allowed:
                continue
            family = self._source_family(url, _text(anchor.get_text(" ", strip=True)))
            if family == "official_website" and url.rstrip("/") != base_url.rstrip("/"):
                continue
            rows.append(
                {
                    "title": _text(anchor.get_text(" ", strip=True)) or url,
                    "source_url": url,
                    "canonical_url": url,
                    "source_type": family,
                    "verification_status": "verified",
                    "discovery_status": "official_link_from_approved_source",
                    "discovery_method": "approved_official_link",
                }
            )
        rows.sort(key=lambda row: priority.get(str(row["source_type"]), 99))
        return self._merge_inventory([], rows)

    def discover_index_sources(
        self,
        content: str,
        *,
        base_url: str,
        content_type: str,
    ) -> list[dict[str, Any]]:
        """Extract same-domain URLs from sitemaps, XML indexes, RSS, Atom, and robots references."""
        base_host = normalized_domain(base_url)
        candidates: list[tuple[str, str]] = []
        if "xml" in content_type or "<urlset" in content.casefold() or "<sitemapindex" in content.casefold():
            soup = BeautifulSoup(content, "xml")
            candidates.extend((_text(node.get_text()), "sitemap") for node in soup.find_all("loc"))
            candidates.extend((_text(node.get("href")), "feed") for node in soup.find_all("link", href=True))
        if "robots" in urlparse(base_url).path.casefold() or content_type == "text/plain":
            for match in re.finditer(r"(?im)^\s*sitemap\s*:\s*(https?://\S+)", content):
                candidates.append((match.group(1), "robots_sitemap"))
        rows: list[dict[str, Any]] = []
        for url, method in candidates:
            if not url or normalized_domain(url) != base_host:
                continue
            family = self._source_family(url)
            if family == "official_website":
                path = urlparse(url).path.casefold()
                if "sitemap" in path:
                    family = "docs"
                elif path.endswith((".xml", ".rss", ".atom")):
                    family = "release_notes"
                else:
                    continue
            rows.append(
                {
                    "title": url,
                    "source_url": url,
                    "canonical_url": url,
                    "source_type": family,
                    "verification_status": "approved",
                    "discovery_status": f"{method}_from_approved_source",
                    "discovery_method": method,
                }
            )
        return self._merge_inventory([], rows)

    @staticmethod
    def _section_for_family(family: str) -> str:
        mapping = {
            "pricing": "pricing",
            "pricing_page": "pricing",
            "faq": "faq",
            "official_docs": "core-workflow",
            "product_page": "product-identity",
            "affiliate_program_page": "final-recommendation",
            "api_docs": "feature-scope",
            "release_notes": "feature-scope",
            "changelog": "feature-scope",
            "tutorial": "core-workflow",
            "examples": "core-workflow",
            "readme": "core-workflow",
            "github": "limitations",
            "support": "limitations",
            "marketplace": "alternatives",
            "blog": "alternatives",
        }
        return mapping.get(normalize_family(family), "product-identity")

    @staticmethod
    def _source_family(url: str, label: str = "") -> str:
        value = f"{url} {label}".casefold()
        rules = (
            ("pricing_page", ("pricing", "/plans", "subscription")),
            ("affiliate_program_page", ("affiliate", "partner-program", "/partners")),
            ("api_docs", ("/api", "api docs", "developer")),
            ("release_notes", ("release-notes", "releases")),
            ("official_docs", ("docs", "documentation", "guide", "support", "help-center", "help.", "faq", "getting-started", "quickstart", "how-to", "security")),
            ("product_page", ("integrations", "marketplace", "features")),
            ("independent_evidence", ("blog", "news", "community", "forum")),
        )
        for family, markers in rules:
            if any(marker in value for marker in markers):
                return family
        return "product_page"

    @staticmethod
    def _merge_inventory(
        current: list[dict[str, Any]],
        additions: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        used_ids: set[str] = set()
        seen = {
            _text(row.get("canonical_url") or row.get("source_url") or row.get("url")).casefold().rstrip("/")
            for row in current
        }
        for row in [*current, *additions]:
            url = _text(row.get("canonical_url") or row.get("source_url") or row.get("url"))
            key = url.casefold().rstrip("/")
            if not key:
                continue
            if any(
                _text(item.get("canonical_url") or item.get("source_url")).casefold().rstrip("/") == key
                for item in result
            ):
                continue
            seen.add(key)
            proposed_id = _text(row.get("source_id"))
            if not proposed_id or proposed_id in used_ids:
                proposed_id = f"source-{len(result) + 1:03d}"
                while proposed_id in used_ids:
                    proposed_id = f"source-{len(result) + len(used_ids) + 1:03d}"
            used_ids.add(proposed_id)
            result.append(
                {
                    **row,
                    "source_id": proposed_id,
                    "canonical_url": url,
                    "source_url": url,
                }
            )
        return result

    def validate_claims(
        self,
        *,
        task_id: str,
        slug: str,
        claims: list[dict[str, Any]],
        sources: list[dict[str, Any]],
        blueprint: dict[str, Any],
        package: dict[str, Any],
        task: dict[str, Any],
    ) -> list[ResearchValidationError]:
        source_map = {row["source_id"]: row for row in sources}
        paragraph_map = {
            paragraph["paragraph_id"]: paragraph
            for source in sources
            for paragraph in source.get("paragraphs", [])
        }
        section_ids = {row["section_id"] for row in blueprint.get("sections", [])}
        errors: list[ResearchValidationError] = []
        for claim in claims:
            source_id = _text(claim.get("source_id"))
            paragraph_id = _text(claim.get("paragraph_id"))
            claim_id = _text(claim.get("claim_id"))
            checks = [
                ("source_exists", source_id in source_map, source_id, "Referenced source must exist."),
                ("paragraph_exists", paragraph_id in paragraph_map, paragraph_id, "Referenced paragraph must exist."),
                (
                    "excerpt_in_paragraph",
                    paragraph_id in paragraph_map
                    and _text(claim.get("supporting_excerpt")) in paragraph_map[paragraph_id]["text"],
                    claim.get("supporting_excerpt"),
                    "Supporting excerpt must be present verbatim in the referenced paragraph.",
                ),
                (
                    "not_metadata",
                    self._claim_candidate(_text(claim.get("normalized_factual_statement"))),
                    claim.get("normalized_factual_statement"),
                    "Claim must be a publishable factual sentence, not metadata.",
                ),
                (
                    "confidence_enum",
                    claim.get("confidence") in CONFIDENCE_ENUMS,
                    claim.get("confidence"),
                    "Confidence must be low, medium, or high.",
                ),
                (
                    "allowed_usage",
                    bool(_text(claim.get("allowed_usage"))),
                    claim.get("allowed_usage"),
                    "Allowed usage must be populated.",
                ),
                (
                    "freshness",
                    bool(_text(claim.get("freshness"))),
                    claim.get("freshness"),
                    "Freshness must be recorded or explicitly unavailable.",
                ),
                (
                    "section_assignment",
                    bool(claim.get("article_section_ids"))
                    and set(claim.get("article_section_ids") or []).issubset(section_ids),
                    claim.get("article_section_ids"),
                    "Claim must map only to valid blueprint sections.",
                ),
            ]
            for rule, passed, actual, expected in checks:
                if passed:
                    continue
                errors.append(
                    ResearchValidationError(
                        task_id=task_id,
                        slug=slug,
                        source_id=source_id,
                        paragraph_id=paragraph_id,
                        claim_id=claim_id,
                        rule_id=rule,
                        severity="error",
                        actual_value=actual,
                        expected_condition=expected,
                        actionable_fix="Remove the claim or map it to a directly supporting approved paragraph.",
                    )
                )
        return errors

    @staticmethod
    def _looks_like_boilerplate(value: str) -> bool:
        lowered = value.casefold()
        markers = (
            "accept cookies",
            "privacy policy",
            "terms of service",
            "all rights reserved",
            "subscribe to our newsletter",
            "sign in",
            "log in",
            "skip to content",
            "table of contents",
        )
        return any(marker in lowered for marker in markers)

    @staticmethod
    def _claim_candidate(value: str) -> bool:
        return not ResearchEnrichmentPipeline._claim_candidate_rejection(value)

    @staticmethod
    def _claim_candidate_rejection(value: str) -> str:
        lowered = value.casefold()
        if len(value.split()) < 8 or len(value) < 45:
            return "too_short"
        if value.startswith(("http://", "https://")):
            return "url_only"
        if any(marker in lowered for marker in PLACEHOLDER_MARKERS):
            return "placeholder_marker"
        if not re.search(r"[A-Za-z]", value):
            return "no_alpha"
        return ""

    @staticmethod
    def _claim_category(value: str) -> str:
        lowered = value.casefold()
        mapping = (
            ("pricing", ("price", "pricing", "plan", "free tier", "subscription", "cost")),
            ("integration", ("integrat", "api", "plugin", "connector")),
            ("limitation", ("limit", "cannot", "does not", "only", "require", "restriction")),
            ("alternative", ("alternative", "competitor", "versus", " vs ")),
            ("workflow", ("workflow", "process", "step", "create", "run", "use")),
            ("feature", ("feature", "support", "provide", "include", "allow", "enable")),
            ("identity", ("is a", "platform", "software", "tool", "framework", "application")),
        )
        for category, markers in mapping:
            if any(marker in lowered for marker in markers):
                return category
        return "general"

    def _entity_terms(self, package: dict[str, Any], task: dict[str, Any]) -> list[str]:
        entities = package.get("entities") if isinstance(package.get("entities"), dict) else {}
        values: list[str] = []
        for key in ("products", "companies", "ai_tools", "competitors", "alternatives"):
            rows = entities.get(key)
            if isinstance(rows, list):
                values.extend(_text(row) for row in rows)
        title = _text(task.get("title") or package.get("keyword"))
        cleaned_title = re.sub(
            r"\b(review|pricing|alternatives?|comparison|pros|cons|202\d)\b",
            "",
            title,
            flags=re.I,
        )
        cleaned_title = re.sub(r"\b(and|versus|vs)\s*$", "", cleaned_title, flags=re.I)
        values.append(cleaned_title)
        return [row for row in _unique(values) if len(row) >= 3]

    @staticmethod
    def _has_concrete_entity(package: dict[str, Any]) -> bool:
        entities = package.get("entities") if isinstance(package.get("entities"), dict) else {}
        return any(
            _text(row)
            for key in ("products", "ai_tools", "companies")
            for row in (entities.get(key) or [])
        )

    @staticmethod
    def _primary_entity(package: dict[str, Any], task: dict[str, Any]) -> str:
        entities = package.get("entities") if isinstance(package.get("entities"), dict) else {}
        for key in ("products", "ai_tools", "companies"):
            rows = entities.get(key)
            if isinstance(rows, list):
                candidate = next((_text(row) for row in rows if len(_text(row)) >= 3), "")
                if candidate:
                    return candidate
        title = _text(task.get("title") or package.get("keyword") or package.get("slug"))
        cleaned = re.sub(
            r"\b(review|pricing|alternatives?|comparison|pros|cons|20\d{2})\b",
            "",
            title,
            flags=re.I,
        )
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" -:|")
        return cleaned or _text(package.get("slug")) or "unknown"

    def _relevance_terms(self, package: dict[str, Any], task: dict[str, Any]) -> list[str]:
        values = [*self._entity_terms(package, task)]
        keyword = _text(package.get("keyword"))
        values.extend(word for word in re.findall(r"[a-z0-9]{4,}", keyword.casefold()))
        for key in (
            "daily_angle",
            "reader_question",
            "search_intent",
            "unique_thesis",
            "required_evidence",
            "next_article_bridge",
        ):
            raw = task.get(key)
            text = " ".join(str(row) for row in raw) if isinstance(raw, list) else _text(raw)
            values.extend(word for word in re.findall(r"[a-z0-9]{4,}", text.casefold()))
        values.extend(("pricing", "feature", "integration", "workflow", "limit", "support"))
        return [value.casefold() for value in _unique(values)]
