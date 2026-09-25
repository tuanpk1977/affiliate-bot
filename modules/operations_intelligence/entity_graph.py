from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse

from .models import (
    SCHEMA_VERSION,
    Evidence,
    Entity,
    MergeSuggestion,
    Relation,
    domain_of,
    normalize_name,
    normalize_url,
    stable_id,
)
from .report_builder import build_entity_graph_report
from .storage import atomic_write_json, atomic_write_text


SHARED_REPOSITORY_HOSTS = {"github.com", "gitlab.com", "bitbucket.org"}


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None


def _strip_html(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", unescape(value))).strip()


def _values(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


class EntityGraphBuilder:
    """Build a source-evidenced entity graph without mutating workflow state."""

    def __init__(
        self,
        *,
        root: Path,
        now: datetime | None = None,
        draft_roots: Iterable[Path] | None = None,
        published_roots: Iterable[Path] | None = None,
        docs_root: Path | None = None,
        research_root: Path | None = None,
        source_registry: Path | None = None,
        weekly_root: Path | None = None,
        affiliate_files: Iterable[Path] | None = None,
    ) -> None:
        self.root = root.resolve()
        self.now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        self.draft_roots = list(draft_roots or [self.root / "data" / "production_article_drafts"])
        self.published_roots = list(published_roots or [self.root / "data" / "published_static_pages"])
        self.docs_root = docs_root or self.root / "docs"
        self.research_root = research_root or self.root / "data" / "research"
        self.source_registry = source_registry or self.root / "data" / "source_registry.json"
        self.weekly_root = weekly_root or self.root / "data" / "editorial_queue" / "weeks"
        self.affiliate_files = list(
            affiliate_files
            or [
                self.root / "data" / "affiliate_opportunities.json",
                self.root / "data" / "affiliate_coverage_report.json",
            ]
        )
        self.entities: dict[str, Entity] = {}
        self.relations: dict[tuple[str, str, str], Relation] = {}
        self.merge_suggestions: dict[tuple[str, str], MergeSuggestion] = {}
        self._domain_index: dict[tuple[str, str], str] = {}
        self._url_index: dict[tuple[str, str], str] = {}
        self._name_index: dict[tuple[str, str], list[str]] = {}
        self._article_slug_index: dict[str, str] = {}

    def _local_evidence(self, path: Path, confidence: float = 0.8) -> Evidence:
        try:
            source = path.resolve().relative_to(self.root).as_posix()
        except ValueError:
            source = str(path.resolve())
        return Evidence(
            source=source,
            source_kind="local_file",
            observed_at=self.now.isoformat(),
            confidence=confidence,
        )

    def _url_evidence(self, url: str, confidence: float, note: str = "") -> Evidence:
        return Evidence(
            source=normalize_url(url),
            source_kind="public_url",
            observed_at=self.now.isoformat(),
            confidence=confidence,
            note=note,
        )

    def _upsert(
        self,
        *,
        name: str,
        entity_type: str,
        evidence: Evidence,
        official_url: str = "",
        confidence: float = 0.6,
        verification_status: str = "unverified",
    ) -> Entity:
        official_url = normalize_url(official_url)
        domain = domain_of(official_url)
        domain_key = (entity_type, domain)
        url_key = (entity_type, official_url)
        name_key = (entity_type, normalize_name(name))
        domain_identity_types = {"company", "product", "model", "developer_tool", "competitor"}
        use_domain_identity = (
            entity_type in domain_identity_types and domain not in SHARED_REPOSITORY_HOSTS
        )
        existing_id = self._url_index.get(url_key) if official_url else None
        if not existing_id and domain and use_domain_identity:
            existing_id = self._domain_index.get(domain_key)
        candidates = self._name_index.get(name_key, [])
        if not existing_id and len(candidates) == 1:
            candidate = self.entities[candidates[0]]
            if not domain or not candidate.official_domain or candidate.official_domain == domain:
                existing_id = candidate.entity_id
        if not existing_id and candidates and domain and use_domain_identity:
            for candidate_id in candidates:
                candidate = self.entities[candidate_id]
                if candidate.official_domain and candidate.official_domain != domain:
                    pair = tuple(sorted((candidate_id, stable_id(entity_type, name, domain))))
                    self.merge_suggestions[pair] = MergeSuggestion(
                        left_entity_id=pair[0],
                        right_entity_id=pair[1],
                        reason="Same normalized name but conflicting official domains.",
                        confidence=0.35,
                    )
        discriminator = domain if use_domain_identity else official_url
        entity_id = existing_id or stable_id(entity_type, name, discriminator)
        entity = self.entities.get(entity_id)
        if entity is None:
            entity = Entity(entity_id=entity_id, canonical_name=name.strip(), entity_type=entity_type)
            entity.first_seen_at = evidence.observed_at
            self.entities[entity_id] = entity
            self._name_index.setdefault(name_key, []).append(entity_id)
        elif normalize_name(entity.canonical_name) != normalize_name(name):
            entity.aliases.add(name.strip())
        if domain:
            entity.official_domain = domain
            entity.official_urls.add(official_url)
            self._url_index[url_key] = entity.entity_id
            if use_domain_identity:
                self._domain_index[domain_key] = entity.entity_id
        entity.source_evidence.append(evidence)
        entity.confidence = max(entity.confidence, confidence)
        if verification_status == "verified" or entity.verification_status == "unknown":
            entity.verification_status = verification_status
        if verification_status == "verified":
            entity.last_verified_at = evidence.observed_at
        return entity

    def _add_relation(
        self,
        source: Entity,
        relation_type: str,
        target: Entity,
        evidence: Evidence,
        confidence: float,
        status: str = "candidate",
    ) -> None:
        key = (source.entity_id, relation_type, target.entity_id)
        relation = Relation(
            source.entity_id,
            relation_type,
            target.entity_id,
            evidence,
            confidence,
            status,
        )
        existing = self.relations.get(key)
        if existing is None or relation.confidence > existing.confidence:
            self.relations[key] = relation

    def _scan_article_metadata(self) -> None:
        seen: set[Path] = set()
        for base in [*self.draft_roots, *self.published_roots]:
            if not base.exists():
                continue
            for path in sorted(base.rglob("metadata.json")):
                if path in seen:
                    continue
                seen.add(path)
                payload = _read_json(path)
                if not isinstance(payload, dict):
                    continue
                slug = str(payload.get("slug") or path.parent.name).strip()
                title = str(payload.get("title") or slug).strip()
                evidence = self._local_evidence(path)
                article = self._upsert(
                    name=title,
                    entity_type="article",
                    evidence=evidence,
                    official_url=str(payload.get("url") or ""),
                    confidence=0.85,
                    verification_status="local_evidence",
                )
                article.add_fact("slug", slug, evidence)
                article.add_fact("title", title, evidence)
                article.related_articles.add(slug)
                self._article_slug_index[slug] = article.entity_id
                for category in _values(payload.get("categories") or payload.get("category")):
                    article.categories.add(category)
                candidate_name = str(
                    payload.get("product_name")
                    or payload.get("entity_name")
                    or payload.get("brand")
                    or ""
                ).strip()
                if candidate_name:
                    product = self._upsert(
                        name=candidate_name,
                        entity_type="product",
                        evidence=evidence,
                        official_url=str(payload.get("official_url") or ""),
                        confidence=0.7,
                        verification_status="local_evidence",
                    )
                    self._add_relation(article, "ARTICLE_REVIEWS_ENTITY", product, evidence, 0.7)

    def _scan_docs(self) -> None:
        if not self.docs_root.exists():
            return
        by_route: dict[str, Entity] = {}
        page_links: list[tuple[Entity, list[str], Evidence]] = []
        for path in sorted(self.docs_root.rglob("index.html")):
            rel = path.relative_to(self.docs_root).as_posix()
            if rel.startswith(("review/", "draft/", "reports/", "admin/")):
                continue
            try:
                html = path.read_text(encoding="utf-8")
            except (OSError, UnicodeError):
                continue
            title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
            canonical_match = re.search(
                r'<link[^>]+rel=["\']canonical["\'][^>]+href=["\']([^"\']+)', html, re.I
            )
            title = _strip_html(title_match.group(1)) if title_match else path.parent.name
            canonical = canonical_match.group(1) if canonical_match else ""
            evidence = self._local_evidence(path, 0.9)
            article = self._upsert(
                name=title,
                entity_type="article",
                evidence=evidence,
                official_url=canonical,
                confidence=0.9,
                verification_status="published_local",
            )
            route = urlparse(canonical).path if canonical else "/" + rel.removesuffix("index.html")
            by_route[route.rstrip("/") + "/"] = article
            page_links.append((article, re.findall(r'href=["\']([^"\']+)', html, re.I), evidence))
        for article, hrefs, evidence in page_links:
            for href in hrefs:
                path = urlparse(href).path if "://" in href else href.split("#", 1)[0]
                target = by_route.get(path.rstrip("/") + "/")
                if target and target.entity_id != article.entity_id:
                    self._add_relation(article, "ARTICLE_LINKS_TO_ARTICLE", target, evidence, 0.95)

    def _scan_weekly_manifests(self) -> None:
        if not self.weekly_root.exists():
            return
        for path in sorted(self.weekly_root.glob("*/week.json")):
            payload = _read_json(path)
            topics = payload.get("topics", []) if isinstance(payload, dict) else []
            if not isinstance(topics, list):
                continue
            evidence = self._local_evidence(path, 0.95)
            for row in topics:
                if not isinstance(row, dict):
                    continue
                title = str(row.get("title") or row.get("keyword") or row.get("slug") or "").strip()
                root_name = str(row.get("root_topic_id") or row.get("parent_slug") or title).strip()
                if not title or not root_name:
                    continue
                root_topic = self._upsert(
                    name=root_name,
                    entity_type="root_topic",
                    evidence=evidence,
                    confidence=0.95,
                    verification_status="workflow_manifest",
                )
                topic = self._upsert(
                    name=title,
                    entity_type="topic",
                    evidence=evidence,
                    confidence=0.9,
                    verification_status="workflow_manifest",
                )
                topic.add_fact("slug", str(row.get("slug") or ""), evidence)
                topic.add_fact("search_intent", str(row.get("search_intent") or ""), evidence)
                self._add_relation(topic, "TOPIC_BELONGS_TO_ROOT", root_topic, evidence, 0.98)
                article_id = self._article_slug_index.get(str(row.get("slug") or "").strip())
                if article_id:
                    self._add_relation(
                        self.entities[article_id],
                        "ARTICLE_BELONGS_TO_TOPIC",
                        topic,
                        evidence,
                        0.95,
                    )

    def _scan_source_registry(self) -> None:
        payload = _read_json(self.source_registry)
        if not isinstance(payload, list):
            return
        local = self._local_evidence(self.source_registry, 0.9)
        for row in payload:
            if not isinstance(row, dict):
                continue
            url = str(row.get("source_url") or "").strip()
            name = str(row.get("source_name") or url or row.get("id") or "").strip()
            brand = str(row.get("brand") or row.get("slug") or "").strip()
            if not url or not name:
                continue
            status = str(row.get("verification_status") or "unverified").lower()
            confidence = min(1.0, float(row.get("confidence") or 0) / 100.0)
            evidence = self._url_evidence(
                url,
                confidence or 0.5,
                note=f"Registry evidence: {self.source_registry.name}",
            )
            source = self._upsert(
                name=name,
                entity_type="source",
                evidence=local,
                official_url=url,
                confidence=confidence,
                verification_status=status,
            )
            source.add_fact("source_type", str(row.get("source_type") or ""), local)
            if not brand:
                continue
            product = self._upsert(
                name=brand,
                entity_type="product",
                evidence=evidence,
                official_url=url,
                confidence=confidence,
                verification_status=status,
            )
            source_type = str(row.get("source_type") or "")
            if domain_of(url) in SHARED_REPOSITORY_HOSTS:
                product.repository_urls.add(normalize_url(url))
            if "docs" in source_type:
                product.documentation_urls.add(normalize_url(url))
            if "pricing" in source_type:
                product.pricing_urls.add(normalize_url(url))
            if "affiliate" in source_type:
                product.affiliate_urls.add(normalize_url(url))
                program = self._upsert(
                    name=f"{brand} affiliate program",
                    entity_type="affiliate_program",
                    evidence=evidence,
                    official_url=url,
                    confidence=confidence,
                    verification_status=status,
                )
                self._add_relation(product, "ENTITY_HAS_AFFILIATE_PROGRAM", program, evidence, confidence)
            self._add_relation(product, "ENTITY_HAS_OFFICIAL_SOURCE", source, evidence, confidence)

    def _scan_affiliate_files(self) -> None:
        for path in sorted(self.affiliate_files):
            payload = _read_json(path)
            if isinstance(payload, list):
                rows = payload
            elif isinstance(payload, dict):
                rows = next(
                    (
                        payload[key]
                        for key in ("programs", "opportunities", "items", "rows")
                        if isinstance(payload.get(key), list)
                    ),
                    [],
                )
            else:
                rows = []
            evidence = self._local_evidence(path, 0.65)
            for row in rows:
                if not isinstance(row, dict):
                    continue
                brand = str(
                    row.get("brand")
                    or row.get("product")
                    or row.get("company")
                    or row.get("name")
                    or ""
                ).strip()
                url = str(
                    row.get("affiliate_url")
                    or row.get("program_url")
                    or row.get("official_url")
                    or row.get("url")
                    or ""
                ).strip()
                if not brand:
                    continue
                product = self._upsert(
                    name=brand,
                    entity_type="product",
                    evidence=evidence,
                    official_url=str(row.get("official_url") or ""),
                    confidence=0.65,
                    verification_status="local_evidence",
                )
                program = self._upsert(
                    name=f"{brand} affiliate program",
                    entity_type="affiliate_program",
                    evidence=evidence,
                    official_url=url,
                    confidence=0.6 if url else 0.4,
                    verification_status="local_evidence" if url else "unverified",
                )
                if url:
                    product.affiliate_urls.add(normalize_url(url))
                else:
                    program.add_fact("program_url", "", None)
                self._add_relation(
                    product,
                    "ENTITY_HAS_AFFILIATE_PROGRAM",
                    program,
                    evidence,
                    0.65 if url else 0.4,
                )
                offer = self._upsert(
                    name=f"{brand} affiliate offer",
                    entity_type="affiliate_offer",
                    evidence=evidence,
                    official_url=url,
                    confidence=0.6 if url else 0.35,
                    verification_status="local_evidence" if url else "unverified",
                )
                self._add_relation(
                    offer,
                    "OFFER_REFERENCES_PRODUCT",
                    product,
                    evidence,
                    0.65 if url else 0.35,
                    "candidate" if url else "needs_review",
                )

    def _scan_research_entities(self) -> None:
        if not self.research_root.exists():
            return
        for path in sorted(self.research_root.glob("*/entities.json")):
            payload = _read_json(path)
            collection_types = {
                "companies": "company",
                "products": "product",
                "ai_tools": "product",
                "ai_models": "ai_model",
                "models": "ai_model",
                "features": "feature",
                "integrations": "integration",
                "pricing_plans": "pricing_plan",
                "use_cases": "use_case",
                "competitors": "competitor",
                "alternatives": "competitor",
                "product_categories": "category",
                "categories": "category",
            }
            if isinstance(payload, list):
                rows = payload
            elif isinstance(payload, dict) and isinstance(payload.get("entities"), list):
                rows = payload["entities"]
            elif isinstance(payload, dict):
                rows = [
                    {"name": value, "entity_type": entity_type}
                    for key, entity_type in collection_types.items()
                    for value in _values(payload.get(key))
                ]
            else:
                rows = []
            if not isinstance(rows, list):
                continue
            evidence = self._local_evidence(path, 0.65)
            research_article = self._upsert(
                name=path.parent.name,
                entity_type="article",
                evidence=evidence,
                confidence=0.55,
                verification_status="research_candidate",
            )
            research_article.add_fact("slug", path.parent.name, evidence)
            typed: dict[str, list[Entity]] = {}
            for row in rows:
                if isinstance(row, str):
                    name, kind, official = row, "product", ""
                elif isinstance(row, dict):
                    name = str(row.get("name") or row.get("canonical_name") or "").strip()
                    kind = str(row.get("entity_type") or row.get("type") or "product").lower()
                    official = str(row.get("official_url") or row.get("url") or "")
                else:
                    continue
                if not name:
                    continue
                if kind == "model":
                    kind = "ai_model"
                if kind not in {
                    "company", "product", "ai_model", "developer_tool", "competitor",
                    "category", "feature", "integration", "pricing_plan", "use_case",
                }:
                    kind = "product"
                entity = self._upsert(
                    name=name,
                    entity_type=kind,
                    evidence=evidence,
                    official_url=official,
                    confidence=0.65 if official else 0.45,
                    verification_status="research_candidate",
                )
                if not official:
                    entity.add_fact("official_url", "", None)
                typed.setdefault(kind, []).append(entity)
                if kind in {"product", "competitor", "ai_model", "developer_tool"}:
                    self._add_relation(
                        research_article,
                        "ARTICLE_DISCUSS_PRODUCT",
                        entity,
                        evidence,
                        0.6,
                    )
            products = typed.get("product", [])
            companies = typed.get("company", [])
            for company in companies:
                for product in products:
                    if (
                        len(companies) != 1
                        or len(products) != 1
                    ) and normalize_name(company.canonical_name) != normalize_name(
                        product.canonical_name
                    ):
                        continue
                    self._add_relation(
                        company,
                        "COMPANY_OFFERS_PRODUCT",
                        product,
                        evidence,
                        0.55,
                        "candidate",
                    )
            relation_map = {
                "feature": "PRODUCT_HAS_FEATURE",
                "integration": "PRODUCT_SUPPORTS_INTEGRATION",
                "pricing_plan": "PRODUCT_HAS_PRICING_PLAN",
                "use_case": "PRODUCT_SERVES_USE_CASE",
            }
            # A shared research inventory proves that components co-occur in the
            # package, not which of several products owns each component. Avoid
            # a Cartesian product; only infer ownership for a single-product
            # package and keep the edge as a candidate.
            for product in products if len(products) == 1 else []:
                for entity_type, relation_type in relation_map.items():
                    for target in typed.get(entity_type, []):
                        self._add_relation(
                            product,
                            relation_type,
                            target,
                            evidence,
                            0.5,
                            "candidate",
                        )

    def _scan_research_claims_and_sources(self) -> None:
        if not self.research_root.exists():
            return
        for directory in sorted(path for path in self.research_root.iterdir() if path.is_dir()):
            article_evidence_path = directory / "FACT_LEDGER.json"
            if not article_evidence_path.is_file():
                continue
            ledger = _read_json(article_evidence_path)
            facts = ledger.get("facts", []) if isinstance(ledger, dict) else []
            if not isinstance(facts, list):
                facts = []
            article_evidence = self._local_evidence(article_evidence_path, 0.75)
            article = self._upsert(
                name=directory.name,
                entity_type="article",
                evidence=article_evidence,
                confidence=0.65,
                verification_status="research_candidate",
            )
            article.add_fact("slug", directory.name, article_evidence)
            for row in facts:
                if not isinstance(row, dict):
                    continue
                statement = str(
                    row.get("normalized_factual_statement")
                    or row.get("factual_statement")
                    or row.get("claim")
                    or ""
                ).strip()
                source_url = str(row.get("source_url") or "").strip()
                if not statement or not source_url:
                    continue
                confidence_map = {"high": 0.9, "medium": 0.7, "low": 0.4}
                confidence = confidence_map.get(str(row.get("confidence") or "").casefold(), 0.55)
                evidence = self._url_evidence(
                    source_url,
                    confidence,
                    note=f"Claim ledger: {article_evidence_path.relative_to(self.root).as_posix()}",
                )
                claim = self._upsert(
                    name=statement,
                    entity_type="claim",
                    evidence=article_evidence,
                    confidence=confidence,
                    verification_status=(
                        "verified_source_candidate"
                        if row.get("public_safe") and row.get("evidence_strength")
                        else "research_candidate"
                    ),
                )
                claim.add_fact("claim_id", str(row.get("claim_id") or ""), article_evidence)
                claim.add_fact("claim_type", str(row.get("claim_category") or ""), article_evidence)
                source = self._upsert(
                    name=str(row.get("source_id") or source_url),
                    entity_type="source",
                    evidence=evidence,
                    official_url=source_url,
                    confidence=confidence,
                    verification_status="research_source",
                )
                self._add_relation(article, "ARTICLE_CITES_SOURCE", source, evidence, confidence)
                self._add_relation(
                    claim,
                    "CLAIM_SUPPORTED_BY_SOURCE",
                    source,
                    evidence,
                    confidence,
                    "candidate" if confidence >= 0.6 else "needs_review",
                )

    def build(self, *, mode: str = "dry-run") -> dict[str, Any]:
        if mode not in {"dry-run", "write"}:
            raise ValueError("mode must be dry-run or write")
        self._scan_article_metadata()
        self._scan_docs()
        self._scan_weekly_manifests()
        self._scan_source_registry()
        self._scan_affiliate_files()
        self._scan_research_entities()
        self._scan_research_claims_and_sources()
        relation_entity_ids = {
            item.source_entity_id for item in self.relations.values()
        } | {item.target_entity_id for item in self.relations.values()}
        entities = [item.to_dict() for item in sorted(self.entities.values(), key=lambda row: row.entity_id)]
        relations = [
            item.to_dict()
            for item in sorted(
                self.relations.values(),
                key=lambda row: (row.source_entity_id, row.relation_type, row.target_entity_id),
            )
        ]
        suggestions = [
            item.to_dict()
            for item in sorted(
                self.merge_suggestions.values(),
                key=lambda row: (row.left_entity_id, row.right_entity_id),
            )
        ]
        unresolved = [
            item["entity_id"]
            for item in entities
            if item["verification_status"] in {"unknown", "unverified", "research_candidate"}
            or item["unknown_or_unverified"]
        ]
        missing_official = [
            item["entity_id"]
            for item in entities
            if item["entity_type"] in {"company", "product", "model", "developer_tool"}
            and not item["official_urls"]
        ]
        orphans = [
            item["entity_id"]
            for item in entities
            if item["entity_id"] not in relation_entity_ids
            and item["entity_type"] not in {"article", "source"}
        ]
        return {
            "schema_version": SCHEMA_VERSION,
            "generated_at": self.now.isoformat(),
            "source": "repository_local_evidence",
            "confidence": 0.75,
            "limitations": [
                "No network verification was performed.",
                "Name-only matches with conflicting domains are suggestions, never automatic merges.",
                "Missing evidence remains unknown_or_unverified and is not writer-authorized fact.",
                "This artifact is recommendation-only and is not workflow approval state.",
            ],
            "mode": mode,
            "entities": entities,
            "relations": relations,
            "merge_suggestions": suggestions,
            "unresolved_entities": sorted(unresolved),
            "missing_official_source": sorted(missing_official),
            "orphan_entities": sorted(orphans),
            "summary": {
                "entity_count": len(entities),
                "relation_count": len(relations),
                "suggested_merge_count": len(suggestions),
                "unresolved_count": len(unresolved),
                "missing_official_source_count": len(missing_official),
                "orphan_count": len(orphans),
            },
            "safety": {
                "recommendation_only": True,
                "approval_changed": False,
                "published": False,
                "production_content_changed": False,
            },
        }

    def write(self, payload: dict[str, Any], *, output_dir: Path) -> dict[str, str]:
        intelligence_root = self.root / "data" / "intelligence"
        output_dir = output_dir.resolve()
        graph_path = output_dir / "entity_graph.json"
        report_path = output_dir / "report.md"
        merge_path = output_dir / "merge_suggestions.json"
        atomic_write_json(graph_path, payload, intelligence_root=intelligence_root)
        atomic_write_json(
            merge_path,
            {
                "schema_version": SCHEMA_VERSION,
                "generated_at": payload["generated_at"],
                "source": payload["source"],
                "confidence": payload["confidence"],
                "limitations": payload["limitations"],
                "suggestions": payload["merge_suggestions"],
            },
            intelligence_root=intelligence_root,
        )
        atomic_write_text(
            report_path,
            build_entity_graph_report(payload),
            intelligence_root=intelligence_root,
        )
        return {
            "entity_graph": str(graph_path),
            "merge_suggestions": str(merge_path),
            "report": str(report_path),
        }
