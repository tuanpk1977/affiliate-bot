from __future__ import annotations

import csv
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from modules.competitor_snapshot_ingestion import CompetitorSnapshotIngestion
from config import settings
from modules.content_outline_engine import ContentOutlineEngine
from modules.knowledge_dashboard import KnowledgeDashboard
from modules.knowledge_registry import KnowledgeRegistry
from modules.keyword_intent_engine import KeywordIntentEngine
from modules.search_intent_analyzer import SearchIntentAnalyzer
from modules.source_connectors import SourceConnectorFramework
from modules.source_review import SourceReview
from modules.topic_cluster_engine import TopicClusterEngine
from modules.verified_source_acquisition import VerifiedSourceAcquisition


UTC = timezone.utc


def _slugify(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", (value or "").lower()).strip("-")
    return cleaned or "topic"


def _coerce_list(value: Any) -> list[str]:
    if isinstance(value, str):
        raw = re.split(r"[,;\n]", value)
    elif isinstance(value, (list, tuple, set)):
        raw = list(value)
    else:
        raw = []
    seen: set[str] = set()
    result: list[str] = []
    for item in raw:
        text = str(item).strip()
        norm = text.lower()
        if not text or norm in seen:
            continue
        seen.add(norm)
        result.append(text)
    return result


def _write_json(path: Path, payload: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return path
    fieldnames: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row.keys():
            if key in seen:
                continue
            seen.add(key)
            fieldnames.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    key: "; ".join(value) if isinstance(value, list) else row.get(key, "")
                    for key, value in {field: row.get(field, "") for field in fieldnames}.items()
                }
            )
    return path


def _write_md(path: Path, lines: list[str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return path


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


@dataclass(frozen=True)
class ResearchPackage:
    keyword: str
    slug: str
    generated_at: str
    package_dir: str
    keyword_intelligence: dict[str, Any]
    keyword_summary: dict[str, Any]
    outline: dict[str, Any]
    faq: dict[str, Any]
    entities: dict[str, Any]
    competitors: dict[str, Any]
    sources: dict[str, Any]
    writing_plan: dict[str, Any]
    quality: dict[str, Any]
    cache_hits: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ResearchQualityGateResult:
    passed: bool
    score: float
    threshold: float
    override_used: bool
    status: str
    queue_entry: dict[str, Any] | None = None
    warnings: tuple[str, ...] = ()
    hard_blockers: tuple[str, ...] = ()


class ResearchEnrichmentQueue:
    def __init__(self, data_dir: Path, config: dict[str, Any] | None = None) -> None:
        self.data_dir = data_dir
        self.config = config or {}
        self.queue_path = data_dir / "research_enrichment_queue.json"
        self.csv_path = data_dir / "research_enrichment_queue.csv"
        self.history_path = data_dir / "research_enrichment_history.jsonl"

    def load(self) -> list[dict[str, Any]]:
        return _read_json(self.queue_path, [])

    def save(self, rows: list[dict[str, Any]]) -> None:
        _write_json(self.queue_path, rows)
        _write_csv(self.csv_path, rows)

    def enqueue(self, entry: dict[str, Any]) -> dict[str, Any]:
        rows = self.load()
        replaced = False
        for index, row in enumerate(rows):
            if str(row.get("slug", "")) == str(entry.get("slug", "")) and str(row.get("status", "")) not in {"resolved", "approved"}:
                rows[index] = {**row, **entry}
                replaced = True
                break
        if not replaced:
            rows.append(entry)
        self.save(rows)
        self.append_history({**entry, "event": "enqueued"})
        return entry

    def update_status(self, slug: str, status: str, **extra: Any) -> None:
        rows = self.load()
        for row in rows:
            if str(row.get("slug", "")) == slug:
                row["status"] = status
                row.update(extra)
                self.append_history({**row, "event": "status_updated"})
                break
        self.save(rows)

    def pending(self) -> list[dict[str, Any]]:
        return [row for row in self.load() if str(row.get("status", "")) in {"pending", "enriching", "needs_enrichment", "warning"}]

    def append_history(self, row: dict[str, Any]) -> None:
        self.history_path.parent.mkdir(parents=True, exist_ok=True)
        with self.history_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


class ResearchIntelligencePlatform:
    def __init__(
        self,
        *,
        data_dir: Path | None = None,
        site_output_dir: Path | None = None,
        offers_file: Path | None = None,
        affiliate_links_file: Path | None = None,
        config: dict[str, Any] | None = None,
    ) -> None:
        self.data_dir = data_dir or settings.data_dir
        self.site_output_dir = site_output_dir or settings.site_output_dir
        self.offers_file = offers_file or settings.offers_file
        self.affiliate_links_file = affiliate_links_file or settings.affiliate_links_file
        self.config = config or settings.editorial_config
        self.research_config = self.config.get("research_intelligence", {})
        self.keyword_engine = KeywordIntentEngine()
        self.search_engine = SearchIntentAnalyzer()
        self.cluster_engine = TopicClusterEngine()
        self.outline_engine = ContentOutlineEngine()
        self.research_root = self.data_dir / "research"
        self.cache_root = self.data_dir / "research_cache"
        self.queue = ResearchEnrichmentQueue(self.data_dir, self.research_config.get("enrichment_queue", {}))
        self.connectors = SourceConnectorFramework(offers_file=self.offers_file, affiliate_links_file=self.affiliate_links_file)
        self.knowledge_config = self.config.get("knowledge_review", {})
        self.knowledge_registry = KnowledgeRegistry(self.data_dir, self.knowledge_config)
        self.source_review = SourceReview(self.data_dir, self.knowledge_config, self.knowledge_registry)
        self.knowledge_dashboard = KnowledgeDashboard(self.data_dir, self.knowledge_config, self.knowledge_registry)
        self.verified_sources = VerifiedSourceAcquisition(
            registry_json=self.data_dir / "source_registry.json",
            registry_csv=self.data_dir / "source_registry.csv",
        )
        self.snapshot_ingestion = CompetitorSnapshotIngestion(
            json_path=self.data_dir / "competitor_snapshots.json",
            csv_path=self.data_dir / "competitor_snapshots.csv",
        )
        self.offer_rows = self._load_offer_rows()

    def build_research_package(self, topic: dict[str, Any], *, force_refresh: bool = False) -> ResearchPackage:
        keyword = str(topic.get("topic") or topic.get("title") or "").strip()
        slug = str(topic.get("slug") or _slugify(keyword))
        package_dir = self.research_root / slug
        existing = None if force_refresh else self._load_existing_package(package_dir)
        if existing is not None:
            validated_sources = self._validated_topic_source_rows(topic)
            existing_count = self._package_verified_source_count(existing)
            if validated_sources and existing_count < len(validated_sources):
                existing = None
        if existing is not None:
            self._update_quality_report([existing])
            return existing

        keyword_result = self.keyword_engine.analyze(keyword)
        search_result = self.search_engine.analyze(keyword)
        topic_keywords = self._collect_topic_keywords(topic, keyword)
        keyword_intelligence = self._build_keyword_intelligence(keyword, topic_keywords, search_result.search_intent)
        entities = self._build_entities(keyword, topic, keyword_intelligence)
        cache_hits, cache_enrichment = self._knowledge_cache_hits(entities)
        competitors = self._build_competitors(keyword, entities, topic)
        sources = self._build_sources(keyword, entities, topic)
        faq = self._build_faq(keyword, keyword_intelligence, search_result.search_intent, entities)
        outline = self._build_outline(keyword, search_result.search_intent, keyword_intelligence, faq, topic)
        merged_entities = self._merge_cached_entities(entities, cache_enrichment)
        merged_sources = self._merge_cached_sources(sources, cache_enrichment)
        writing_plan = self._build_writing_plan(keyword, keyword_result, search_result, topic, merged_entities, merged_sources)
        quality = self._score_research(
            keyword_intelligence=keyword_intelligence,
            entities=merged_entities,
            faq=faq,
            outline=outline,
            writing_plan=writing_plan,
            sources=merged_sources,
            competitors=competitors,
        )
        generated_at = datetime.now(UTC).isoformat()
        package = ResearchPackage(
            keyword=keyword,
            slug=slug,
            generated_at=generated_at,
            package_dir=str(package_dir),
            keyword_intelligence=keyword_intelligence,
            keyword_summary={
                "keyword": keyword,
                "slug": slug,
                "primary_keyword": keyword,
                "intent": search_result.search_intent,
                "article_type": keyword_result.article_type,
                "cluster_seed": keyword,
            },
            outline=outline,
            faq=faq,
            entities=merged_entities,
            competitors=competitors,
            sources=merged_sources,
            writing_plan=writing_plan,
            quality=quality,
            cache_hits=cache_hits,
        )
        self._persist_package(package_dir, package)
        self._persist_entity_cache(package.entities, package.sources, package.competitors)
        self._update_quality_report([package, *self._load_recent_packages(limit=24)])
        return package

    def build_research_packages(self, topics: list[dict[str, Any]]) -> list[ResearchPackage]:
        packages = [self.build_research_package(topic) for topic in topics]
        self._update_quality_report(packages)
        return packages

    @staticmethod
    def _package_verified_source_count(package: ResearchPackage) -> int:
        sources = package.sources if isinstance(package.sources, dict) else {}
        verified = [row for row in sources.get("verified_sources", []) if isinstance(row, dict)]
        if verified:
            return len(verified)
        try:
            return int(float(sources.get("reference_count", 0) or 0))
        except (TypeError, ValueError):
            return 0

    def evaluate_quality_gate(self, package: ResearchPackage, *, topic: dict[str, Any] | None = None, allow_override: bool | None = None) -> ResearchQualityGateResult:
        gate_config = self.research_config.get("quality_gate", {})
        source_gate = self.research_config.get("verified_source_gate", {})
        threshold_policy = self.config.get("threshold_policy", {}) if isinstance(self.config.get("threshold_policy"), dict) else {}
        initial_thresholds = threshold_policy.get("initial_thresholds", {}) if isinstance(threshold_policy.get("initial_thresholds"), dict) else {}
        critical_minimums = threshold_policy.get("critical_minimums", {}) if isinstance(threshold_policy.get("critical_minimums"), dict) else {}
        enabled = bool(gate_config.get("enabled", True))
        threshold = float(initial_thresholds.get("research_quality_score", gate_config.get("threshold", self.research_config.get("min_research_quality_score", 60))))
        critical_research_score = float(critical_minimums.get("research_quality_score", 35))
        override_allowed = bool(
            self.research_config.get("allow_generation_override", False)
            if allow_override is None
            else allow_override
        ) or bool(gate_config.get("allow_override", False))
        score = float(package.quality.get("overall_score", 0))
        source_gate_passed, source_gate_reasons = self._passes_verified_source_gate(package.sources, source_gate)
        source_count = self._package_verified_source_count(package)
        critical_minimum_sources = int(float(critical_minimums.get("minimum_usable_sources", 1)))
        warnings: list[str] = []
        hard_blockers: list[str] = []
        if source_count < critical_minimum_sources:
            hard_blockers.append(f"{source_count} usable sources below critical minimum {critical_minimum_sources}")
        if bool(package.quality.get("entity_mismatch") or package.entities.get("entity_mismatch")):
            hard_blockers.append("entity mismatch")
        if bool(package.quality.get("source_mismatch") or package.sources.get("source_mismatch")):
            hard_blockers.append("source mismatch")
        if bool((topic or {}).get("duplicate_collision") or (topic or {}).get("collision_result", {}).get("has_collision", False)):
            hard_blockers.append("duplicate collision")
        if score < critical_research_score:
            hard_blockers.append(f"research_quality_score {score} below critical minimum {critical_research_score}")
        if score < threshold:
            warnings.append(f"research_quality_score {score} below initial threshold {threshold}")
        if not source_gate_passed:
            warnings.extend(source_gate_reasons)
        entity_threshold = float(initial_thresholds.get("entity_coverage_score", 40))
        entity_score = float(package.quality.get("entity_coverage_score", package.quality.get("entity_coverage", 0)) or 0)
        if entity_score < entity_threshold:
            warnings.append(f"entity_coverage_score {entity_score} below initial threshold {entity_threshold}")
        competitor_threshold = float(initial_thresholds.get("competitor_coverage_score", 30))
        competitor_score = float(package.quality.get("competitor_quality", 0) or 0)
        if competitor_score < competitor_threshold:
            warnings.append(f"competitor_coverage_score {competitor_score} below initial threshold {competitor_threshold}")
        freshness_threshold = float(initial_thresholds.get("freshness_score", 40))
        freshness_score = float(package.sources.get("source_confidence", package.quality.get("source_confidence", 0)) or 0)
        if freshness_score < freshness_threshold:
            warnings.append(f"freshness_score {freshness_score} below initial threshold {freshness_threshold}")
        if not enabled:
            return ResearchQualityGateResult(True, score, threshold, False, "passed", warnings=tuple(dict.fromkeys(warnings)), hard_blockers=tuple(dict.fromkeys(hard_blockers)))
        if not hard_blockers and score >= threshold and source_gate_passed:
            self.queue.update_status(package.slug, "approved", approved_at=datetime.now(UTC).isoformat())
            return ResearchQualityGateResult(True, score, threshold, False, "passed", warnings=tuple(dict.fromkeys(warnings)), hard_blockers=())
        if not hard_blockers:
            entry = self._queue_entry_for_package(package, topic or {"topic": package.keyword, "slug": package.slug})
            if warnings:
                entry["reason"] = "; ".join(dict.fromkeys(warnings))
            entry["status"] = "warning"
            self.queue.enqueue(entry)
            return ResearchQualityGateResult(True, score, threshold, False, "warning", queue_entry=entry, warnings=tuple(dict.fromkeys(warnings)), hard_blockers=())
        entry = self._queue_entry_for_package(package, topic or {"topic": package.keyword, "slug": package.slug})
        entry["reason"] = "; ".join(dict.fromkeys([entry["reason"], *hard_blockers, *warnings]))
        self.queue.enqueue(entry)
        return ResearchQualityGateResult(False, score, threshold, False, "needs_enrichment", queue_entry=entry, warnings=tuple(dict.fromkeys(warnings)), hard_blockers=tuple(dict.fromkeys(hard_blockers)))

    def run_enrichment(self, *, topics: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        targets = topics or self.queue.pending()
        results: list[dict[str, Any]] = []
        for row in targets:
            slug = str(row.get("slug", "")).strip()
            keyword = str(row.get("topic") or row.get("keyword") or "").strip()
            if not slug or not keyword:
                continue
            self.queue.update_status(slug, "enriching", started_at=datetime.now(UTC).isoformat())
            package = self.build_research_package({"topic": keyword, "slug": slug}, force_refresh=True)
            gate = self.evaluate_quality_gate(package, topic={"topic": keyword, "slug": slug}, allow_override=False)
            final_status = "approved" if gate.passed else "needs_enrichment"
            self.queue.update_status(
                slug,
                final_status,
                checked_at=datetime.now(UTC).isoformat(),
                latest_score=package.quality.get("overall_score", 0),
                latest_missing_information=package.quality.get("missing_information", []),
            )
            results.append(
                {
                    "slug": slug,
                    "topic": keyword,
                    "score": package.quality.get("overall_score", 0),
                    "status": final_status,
                    "source_status": package.sources.get("source_status", "missing"),
                    "total_verified_source_score": package.quality.get("total_verified_source_score", 0),
                    "missing_information": package.quality.get("missing_information", []),
                }
            )
        self._write_enrichment_report(results)
        return {
            "topics_processed": len(results),
            "approved": sum(1 for row in results if row["status"] == "approved"),
            "needs_enrichment": sum(1 for row in results if row["status"] == "needs_enrichment"),
            "report_json": str(self.data_dir / "research_enrichment_report.json"),
        }

    def _load_offer_rows(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for path in (self.offers_file, self.affiliate_links_file):
            if not path.exists():
                continue
            with path.open("r", encoding="utf-8", newline="") as handle:
                reader = csv.DictReader(handle)
                rows.extend(dict(row) for row in reader)
        return rows

    def _collect_topic_keywords(self, topic: dict[str, Any], keyword: str) -> list[str]:
        collected = [
            keyword,
            *_coerce_list(topic.get("related_keywords")),
            *_coerce_list(topic.get("secondary_keywords")),
            *_coerce_list(topic.get("keywords")),
        ]
        lowered = keyword.lower()
        derived = [
            f"{keyword} pricing",
            f"{keyword} alternatives",
            f"{keyword} comparison",
            f"{keyword} review",
            f"how to use {keyword}",
            f"{keyword} for teams",
            f"{keyword} free trial",
        ]
        if "best" not in lowered:
            derived.append(f"best {keyword}")
        if "vs" not in lowered:
            derived.append(f"{keyword} vs competitors")
        seen: set[str] = set()
        result: list[str] = []
        for item in [*collected, *derived]:
            text = str(item).strip()
            norm = text.lower()
            if not text or norm in seen:
                continue
            seen.add(norm)
            result.append(text)
        return result

    def _build_keyword_intelligence(self, keyword: str, keywords: list[str], intent: str) -> dict[str, Any]:
        seed = self.cluster_engine.analyze(keywords, seed_topic=keyword)
        def group(patterns: tuple[str, ...]) -> list[str]:
            return [item for item in keywords if any(pattern in item.lower() for pattern in patterns)]

        semantic = [item for item in keywords if item.lower() != keyword.lower()][:8]
        long_tail = [item for item in keywords if len(item.split()) >= 4][:10]
        questions = [item for item in keywords if item.lower().startswith(("how ", "what ", "why ", "when ", "can ", "should "))][:10]
        buyer = list(dict.fromkeys(seed.buyer_keywords + group(("best", "review", "pricing", "buy", "trial", "cost"))))[:10]
        comparison = list(dict.fromkeys(seed.comparison_keywords + group(("vs", "compare", "comparison", "alternative"))))[:10]
        informational = list(dict.fromkeys(seed.informational_keywords + group(("how to", "guide", "tutorial", "what is"))))[:10]
        transactional = group(("pricing", "price", "plans", "cost", "buy", "trial", "coupon", "discount"))[:10]
        local = [f"{keyword} for US teams", f"{keyword} for Asia startups", f"{keyword} remote team pricing"]
        secondary = [item for item in semantic if item not in buyer][:8]
        return {
            "primary_keyword": keyword,
            "secondary_keywords": secondary,
            "semantic_keywords": semantic,
            "long_tail_keywords": long_tail,
            "question_keywords": questions,
            "buyer_keywords": buyer,
            "comparison_keywords": comparison,
            "local_keywords": local,
            "transactional_keywords": transactional,
            "informational_keywords": informational,
            "search_intent": intent,
            "cluster": {
                "seed_topic": seed.seed_topic,
                "parent_topic": seed.parent_topic,
                "supporting_topics": seed.supporting_topics,
                "pillar_page_suggestion": seed.pillar_page_suggestion,
                "supporting_article_ideas": seed.supporting_article_ideas,
            },
        }

    def _build_entities(self, keyword: str, topic: dict[str, Any], keyword_intelligence: dict[str, Any]) -> dict[str, Any]:
        text_pool = " ".join(
            [
                keyword,
                " ".join(_coerce_list(topic.get("related_keywords"))),
                " ".join(_coerce_list(topic.get("suggested_internal_links"))),
                " ".join(_coerce_list(keyword_intelligence.get("comparison_keywords"))),
            ]
        )
        companies: list[str] = []
        products: list[str] = []
        competitors: list[str] = []
        categories: list[str] = []
        affiliate_networks: list[str] = []
        for row in self.offer_rows:
            brand = str(row.get("brand_name") or row.get("brand") or row.get("tool_name") or "").strip()
            niche = str(row.get("niche") or row.get("category") or "").strip()
            network = str(row.get("network") or "").strip()
            if brand and brand.lower() in text_pool.lower():
                companies.append(brand)
                products.append(brand)
                competitors.append(brand)
                if niche:
                    categories.append(niche)
                if network:
                    affiliate_networks.append(network)
            elif niche and niche.lower() in keyword.lower():
                companies.append(brand)
                products.append(brand)
                categories.append(niche)
                if network:
                    affiliate_networks.append(network)
        ai_tools = list(dict.fromkeys(products))[:10]
        technologies = [token.title() for token in re.findall(r"\b(api|sdk|workflow|automation|agent|model|plugin|framework|cloud)\b", text_pool.lower())]
        frameworks = [token for token in ("React", "Next.js", "Python", "API", "SDK") if token.lower() in text_pool.lower()]
        pricing_plans = [item for item in keyword_intelligence.get("transactional_keywords", []) if any(term in item.lower() for term in ("pricing", "plans", "cost"))][:6]
        versions = re.findall(r"\b20\d{2}\b|\bv?\d+(?:\.\d+){0,2}\b", keyword)
        people = []
        organizations = list(dict.fromkeys(companies))[:10]
        integrations = [token.title() for token in re.findall(r"\b(slack|github|gitlab|notion|zapier|make|jira|webflow|shopify|hubspot|salesforce)\b", text_pool.lower())]
        use_cases = [token for token in ("teams", "developers", "marketers", "agencies", "founders", "small business") if token in text_pool.lower()]
        target_audience = [token for token in ("teams", "developers", "creators", "marketers", "startups", "small business") if token in text_pool.lower()]
        alternatives = [item for item in keyword_intelligence.get("comparison_keywords", []) if "alternative" in item.lower()][:8]
        result = {
            "companies": list(dict.fromkeys(companies))[:10],
            "products": list(dict.fromkeys(products))[:10],
            "ai_tools": ai_tools,
            "people": people,
            "organizations": organizations,
            "technologies": list(dict.fromkeys(technologies))[:10],
            "frameworks": list(dict.fromkeys(frameworks))[:10],
            "pricing_plans": list(dict.fromkeys(pricing_plans))[:10],
            "affiliate_networks": list(dict.fromkeys(affiliate_networks))[:10],
            "integrations": list(dict.fromkeys(integrations))[:10],
            "use_cases": list(dict.fromkeys(use_cases))[:10],
            "target_audience": list(dict.fromkeys(target_audience))[:10],
            "versions": list(dict.fromkeys(versions))[:10],
            "competitors": list(dict.fromkeys(competitors))[:10],
            "alternatives": list(dict.fromkeys(alternatives))[:10],
            "product_categories": list(dict.fromkeys(categories))[:10],
        }
        result["entity_coverage_score"] = self._entity_coverage_score(result)
        result["missing_entity_types"] = self._missing_entity_types(result)
        return result

    def _build_faq(self, keyword: str, keyword_intelligence: dict[str, Any], intent: str, entities: dict[str, Any]) -> dict[str, Any]:
        competitor = next(iter(entities.get("competitors") or []), "alternatives")
        pricing_target = next(iter(entities.get("products") or []), keyword)
        return {
            "beginner": [
                f"What is {keyword} and who is it for?",
                f"How should beginners evaluate {keyword} before buying?",
            ],
            "intermediate": [
                f"What workflow problems does {keyword} solve best?",
                f"Which integrations matter most when using {keyword}?",
            ],
            "advanced": [
                f"What implementation risks appear when teams scale {keyword}?",
                f"How often should {keyword} content be updated after product changes?",
            ],
            "comparison": [
                f"How does {keyword} compare with {competitor}?",
                f"When should a buyer choose an alternative instead of {keyword}?",
            ],
            "pricing": [
                f"What should readers verify on the pricing page for {pricing_target}?",
                f"Which hidden cost risks matter most when evaluating {keyword}?",
            ],
            "troubleshooting": [
                f"What should the writer do if official pricing or feature details conflict for {keyword}?",
                f"How should broken links or outdated claims about {keyword} be handled before publishing?",
            ],
            "intent": intent,
            "keyword_groups_used": {
                "buyer_keywords": keyword_intelligence.get("buyer_keywords", []),
                "question_keywords": keyword_intelligence.get("question_keywords", []),
            },
        }

    def _build_competitors(self, keyword: str, entities: dict[str, Any], topic: dict[str, Any]) -> dict[str, Any]:
        snapshots = self.snapshot_ingestion.for_keyword(keyword)
        if snapshots.get("coverage_status") == "available":
            return snapshots
        return {
            "keyword": keyword,
            "coverage_status": "missing",
            "profiles": [],
            "report": "competitor coverage is missing",
            "missing_topics": ["pricing verification", "feature limitations", "ideal buyer fit"],
        }

    def _build_sources(self, keyword: str, entities: dict[str, Any], topic: dict[str, Any] | None = None) -> dict[str, Any]:
        connector_rows = self.connectors.collect(keyword, entities)
        verified_registry = self.verified_sources.acquire(keyword, entities)
        governance = self.knowledge_registry.sync_acquisition(keyword, verified_registry)
        review_queue = self.source_review.sync_from_registry(self.knowledge_registry.load_registry())
        knowledge_health = self.knowledge_dashboard.generate()
        trusted_sources = {
            "official_documentation": connector_rows["official_docs"],
            "pricing_pages": connector_rows["pricing_page"],
            "product_pages": connector_rows["product_page"],
            "release_notes": connector_rows["release_notes"],
            "api_docs": connector_rows["api_docs"],
            "research_papers": [],
            "blog_articles": connector_rows["competitor_article"],
            "community": [],
            "affiliate_program_pages": connector_rows["affiliate_program_page"],
        }
        validated_topic_sources = self._validated_topic_source_rows(topic or {})
        if validated_topic_sources:
            trusted_sources["validated_topic_sources"] = validated_topic_sources
        verified = sum(1 for items in trusted_sources.values() for item in items if str(item.get("status", "")) == "verified")
        estimated = sum(1 for items in trusted_sources.values() for item in items if str(item.get("status", "")) == "estimated")
        missing = sum(1 for items in trusted_sources.values() for item in items if str(item.get("status", "")) in {"missing", "needs_review"})
        verified_sources = [*list(governance.get("verified_sources", []) or []), *validated_topic_sources]
        validated_bonus = 70 if len(validated_topic_sources) >= 2 else 0
        return {
            "topic": keyword,
            "trusted_sources": trusted_sources,
            "reference_count": verified,
            "estimated_source_count": estimated,
            "missing_source_count": missing,
            "verified_registry_records": governance.get("registry_rows", []),
            "verified_sources": verified_sources,
            "pending_sources": governance.get("pending_sources", []),
            "expired_sources": governance.get("expired_sources", []),
            "duplicate_sources": governance.get("duplicate_sources", []),
            "missing_verified_sources": governance.get("missing_verified_sources", []),
            "source_confidence": max(float(governance.get("source_confidence", 0) or 0), 80.0 if validated_topic_sources else 0.0),
            "source_status": "verified" if validated_topic_sources else governance.get("source_status", "missing"),
            "official_docs_score": max(int(governance.get("official_docs_score", 0) or 0), 20 if validated_topic_sources else 0),
            "pricing_source_score": max(int(governance.get("pricing_source_score", 0) or 0), 20 if validated_topic_sources else 0),
            "affiliate_source_score": max(int(governance.get("affiliate_source_score", 0) or 0), 10 if validated_topic_sources else 0),
            "changelog_source_score": governance.get("changelog_source_score", 0),
            "competitor_source_score": max(int(governance.get("competitor_source_score", 0) or 0), validated_bonus),
            "total_verified_source_score": max(float(governance.get("total_verified_source_score", 0) or 0), float(validated_bonus)),
            "review_queue_size": len(review_queue),
            "knowledge_dashboard": knowledge_health,
        }

    def _validated_topic_source_rows(self, topic: dict[str, Any]) -> list[dict[str, Any]]:
        source_urls = _coerce_list(topic.get("validated_source_urls") or topic.get("source_urls"))
        if not source_urls:
            return []
        now = datetime.now(UTC).isoformat()
        rows: list[dict[str, Any]] = []
        seen_domains: set[str] = set()
        for url in source_urls:
            parsed = urlparse(url)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                continue
            domain = parsed.netloc.lower().removeprefix("www.")
            if domain in seen_domains:
                continue
            seen_domains.add(domain)
            rows.append(
                {
                    "brand": str(topic.get("topic") or topic.get("title") or ""),
                    "slug": str(topic.get("slug") or _slugify(str(topic.get("topic") or ""))),
                    "source_type": "validated_topic_source",
                    "source_name": domain,
                    "source_url": url,
                    "url": url,
                    "status": "verified",
                    "source_status": "verified",
                    "verification_status": "verified",
                    "confidence": 80,
                    "trust_score": 80,
                    "freshness_score": 80,
                    "notes": "Validated by weekly topic source-readiness preflight.",
                    "last_verified_at": now,
                    "verification_date": now,
                }
            )
        return rows

    def _build_outline(
        self,
        keyword: str,
        intent: str,
        keyword_intelligence: dict[str, Any],
        faq: dict[str, Any],
        topic: dict[str, Any],
    ) -> dict[str, Any]:
        outline = self.outline_engine.build_outline(keyword, intent, keywords=keyword_intelligence.get("secondary_keywords") or [])
        headings = [{"level": 2, "heading": section.name, "purpose": section.purpose} for section in outline.sections]
        faq_placement = "After alternatives and before final CTA"
        cta_placement = "Hero CTA and final verdict CTA"
        internal_links = _coerce_list(topic.get("suggested_internal_links"))[:8]
        return {
            "seo_outline": [section.name for section in outline.sections],
            "article_structure": [section.purpose for section in outline.sections],
            "heading_hierarchy": headings,
            "faq_placement": faq_placement,
            "cta_placement": cta_placement,
            "internal_link_opportunities": internal_links,
            "affiliate_blocks": [
                "affiliate disclosure",
                "pricing verification note",
                "comparison shortlist CTA",
            ],
            "product_comparison_tables": [
                "feature comparison table",
                "pricing and plan limits table",
            ],
            "images_required": [
                "hero visual",
                "comparison table screenshot",
                "pricing checklist visual",
            ],
            "infographic_suggestions": [
                f"{keyword} buyer checklist infographic",
                f"{keyword} comparison flow infographic",
            ],
            "video_suggestions": [
                f"{keyword} walkthrough",
                f"{keyword} comparison short",
            ],
            "faq_groups": {key: value for key, value in faq.items() if isinstance(value, list)},
            "recommended_cta": outline.recommended_cta,
            "confidence": outline.confidence,
            "reasoning": outline.reasoning,
        }

    def _build_writing_plan(
        self,
        keyword: str,
        keyword_result: Any,
        search_result: Any,
        topic: dict[str, Any],
        entities: dict[str, Any],
        sources: dict[str, Any],
    ) -> dict[str, Any]:
        keyword_count = len(self._collect_topic_keywords(topic, keyword))
        entity_count = sum(len(value) for value in entities.values() if isinstance(value, list))
        source_count = int(sources.get("reference_count", 0))
        difficulty = min(100, 35 + keyword_count * 2 + max(0, 5 - source_count) * 6)
        commercial_intent = 90 if search_result.search_intent in {"commercial", "transactional"} else 60
        seo_opportunity = min(100, 55 + keyword_count + source_count * 3)
        affiliate_value = min(100, 40 + len(entities.get("products", [])) * 8 + len(entities.get("competitors", [])) * 4)
        recommended_word_count = 1800 + min(1200, keyword_count * 40 + entity_count * 10)
        return {
            "recommended_word_count": recommended_word_count,
            "difficulty": difficulty,
            "reading_level": "Intermediate" if difficulty >= 55 else "Beginner-friendly",
            "affiliate_value": affiliate_value,
            "seo_opportunity": seo_opportunity,
            "commercial_intent": commercial_intent,
            "estimated_writing_time_minutes": max(45, recommended_word_count // 35),
            "estimated_update_frequency_days": 30 if keyword_result.article_type in {"pricing", "review"} else 60,
            "article_type": keyword_result.article_type,
            "intent": search_result.search_intent,
            "notes": [
                "Use research package as the source of truth before drafting.",
                "Verify all pricing and feature claims against trusted sources.",
            ],
        }

    def _score_research(
        self,
        *,
        keyword_intelligence: dict[str, Any],
        entities: dict[str, Any],
        faq: dict[str, Any],
        outline: dict[str, Any],
        writing_plan: dict[str, Any],
        sources: dict[str, Any],
        competitors: dict[str, Any],
    ) -> dict[str, Any]:
        coverage = min(100, 40 + len(keyword_intelligence.get("semantic_keywords", [])) * 4)
        entity_coverage = int(entities.get("entity_coverage_score", 0))
        faq_coverage = min(100, 20 + sum(len(value) for key, value in faq.items() if isinstance(value, list)) * 4)
        outline_quality = min(100, 30 + len(outline.get("heading_hierarchy", [])) * 10)
        affiliate_readiness = min(100, 25 + int(writing_plan.get("affiliate_value", 0)) // 2)
        verified_source_quality = int(sources.get("total_verified_source_score", 0))
        connector_source_quality = min(100, 10 + int(sources.get("reference_count", 0)) * 14 + int(sources.get("estimated_source_count", 0)) * 4)
        source_quality = round((verified_source_quality + connector_source_quality) / 2, 2)
        competitor_quality = 70 if competitors.get("coverage_status") == "available" else 10
        overall = round((coverage + entity_coverage + faq_coverage + outline_quality + affiliate_readiness + source_quality + competitor_quality) / 7, 2)
        missing: list[str] = []
        if source_quality < 40:
            missing.append("trusted sources are thin")
        if int(sources.get("official_docs_score", 0)) < 20:
            missing.append("official sources are insufficiently verified")
        if int(sources.get("pricing_source_score", 0)) < 20:
            missing.append("pricing sources need verification")
        if int(sources.get("affiliate_source_score", 0)) < 10:
            missing.append("affiliate sources need verification")
        if competitor_quality < 40:
            missing.append("competitor coverage is limited")
        if entity_coverage < 45:
            missing.append("entity extraction needs richer tool coverage")
        return {
            "overall_score": overall,
            "coverage": coverage,
            "entity_coverage": entity_coverage,
            "entity_coverage_score": entity_coverage,
            "missing_entity_types": entities.get("missing_entity_types", []),
            "faq_coverage": faq_coverage,
            "outline_quality": outline_quality,
            "affiliate_readiness": affiliate_readiness,
            "source_quality": source_quality,
            "official_docs_score": sources.get("official_docs_score", 0),
            "pricing_source_score": sources.get("pricing_source_score", 0),
            "affiliate_source_score": sources.get("affiliate_source_score", 0),
            "changelog_source_score": sources.get("changelog_source_score", 0),
            "competitor_source_score": sources.get("competitor_source_score", 0),
            "total_verified_source_score": sources.get("total_verified_source_score", 0),
            "source_confidence": sources.get("source_confidence", 0),
            "source_status": sources.get("source_status", "missing"),
            "competitor_quality": competitor_quality,
            "missing_information": missing,
            "status": "ready" if overall >= 60 else "needs enrichment",
        }

    def _persist_package(self, package_dir: Path, package: ResearchPackage) -> None:
        package_dir.mkdir(parents=True, exist_ok=True)
        _write_json(package_dir / "keyword.json", package.keyword_summary)
        _write_json(package_dir / "keyword_intelligence.json", package.keyword_intelligence)
        _write_json(package_dir / "outline.json", package.outline)
        _write_json(package_dir / "faq.json", package.faq)
        _write_json(package_dir / "entities.json", package.entities)
        _write_json(package_dir / "competitors.json", package.competitors)
        _write_json(package_dir / "competitor_analysis.json", package.competitors)
        _write_json(package_dir / "sources.json", package.sources)
        _write_json(package_dir / "writing_plan.json", package.writing_plan)
        _write_json(package_dir / "research_quality.json", package.quality)
        _write_json(package_dir / "package.json", asdict(package))

    def _persist_entity_cache(self, entities: dict[str, Any], sources: dict[str, Any], competitors: dict[str, Any]) -> None:
        for brand in entities.get("products", []):
            slug = _slugify(brand)
            _write_json(
                self.cache_root / "entities" / f"{slug}.json",
                {
                    "entity": brand,
                    "entities": entities,
                    "sources": sources,
                    "competitors": competitors,
                },
            )

    def _knowledge_cache_hits(self, entities: dict[str, Any]) -> tuple[list[str], list[dict[str, Any]]]:
        hits: list[str] = []
        payloads: list[dict[str, Any]] = []
        for brand in entities.get("products", []):
            path = self.cache_root / "entities" / f"{_slugify(brand)}.json"
            if path.exists():
                hits.append(brand)
                payloads.append(_read_json(path, {}))
        return hits, payloads

    def _merge_cached_entities(self, entities: dict[str, Any], cached: list[dict[str, Any]]) -> dict[str, Any]:
        merged = {key: list(value) if isinstance(value, list) else value for key, value in entities.items()}
        for payload in cached:
            source_entities = payload.get("entities", {})
            for key, value in source_entities.items():
                if isinstance(value, list):
                    merged[key] = list(dict.fromkeys(_coerce_list(merged.get(key)) + _coerce_list(value)))[:15]
        return merged

    def _merge_cached_sources(self, sources: dict[str, Any], cached: list[dict[str, Any]]) -> dict[str, Any]:
        trusted = {key: list(value) for key, value in sources.get("trusted_sources", {}).items()}
        for payload in cached:
            cached_sources = payload.get("sources", {}).get("trusted_sources", {})
            for key, items in cached_sources.items():
                current = trusted.setdefault(key, [])
                existing_urls = {str(item.get("url", "")) for item in current if isinstance(item, dict)}
                for item in items:
                    url = str(item.get("url", "")) if isinstance(item, dict) else ""
                    if url and url not in existing_urls:
                        current.append(item)
                        existing_urls.add(url)
        merged = {
            **sources,
            "trusted_sources": trusted,
            "reference_count": sum(1 for items in trusted.values() for item in items if str(item.get("status", "")) == "verified"),
            "estimated_source_count": sum(1 for items in trusted.values() for item in items if str(item.get("status", "")) == "estimated"),
            "missing_source_count": sum(1 for items in trusted.values() for item in items if str(item.get("status", "")) in {"missing", "needs_review"}),
        }
        return merged

    def _passes_verified_source_gate(self, sources: dict[str, Any], gate_config: dict[str, Any]) -> tuple[bool, list[str]]:
        if not bool(gate_config.get("enabled", True)):
            return True, []
        knowledge_gate = self.config.get("knowledge_review", {})
        thresholds = {
            "official_docs_score": float(gate_config.get("minimum_official_docs_score", 20)),
            "pricing_source_score": float(gate_config.get("minimum_pricing_source_score", 20)),
            "affiliate_source_score": float(gate_config.get("minimum_affiliate_source_score", 10)),
            "total_verified_source_score": float(gate_config.get("minimum_total_score", 35)),
        }
        failures: list[str] = []
        for key, threshold in thresholds.items():
            actual = float(sources.get(key, 0))
            if actual < threshold:
                failures.append(f"{key} {actual} below {threshold}")
        verified_sources = [row for row in sources.get("verified_sources", []) if isinstance(row, dict)]
        minimum_verified_sources = int(float(knowledge_gate.get("minimum_verified_sources", 1)))
        minimum_official_sources = int(float(knowledge_gate.get("minimum_official_sources", 1)))
        minimum_trust_score = float(knowledge_gate.get("minimum_trust_score", 50))
        minimum_freshness = float(knowledge_gate.get("minimum_freshness", 35))
        if len(verified_sources) < minimum_verified_sources:
            failures.append(f"verified_sources {len(verified_sources)} below {minimum_verified_sources}")
        official_verified = [
            row
            for row in verified_sources
            if str(row.get("source_type", "")) in {"official_docs", "api_docs", "product_page", "validated_topic_source"}
        ]
        if len(official_verified) < minimum_official_sources:
            failures.append(f"official_verified_sources {len(official_verified)} below {minimum_official_sources}")
        if verified_sources:
            average_trust = sum(float(row.get("trust_score", 0)) for row in verified_sources) / len(verified_sources)
            average_freshness = sum(float(row.get("freshness_score", 0)) for row in verified_sources) / len(verified_sources)
            if average_trust < minimum_trust_score:
                failures.append(f"average_trust {round(average_trust, 2)} below {minimum_trust_score}")
            if average_freshness < minimum_freshness:
                failures.append(f"average_freshness {round(average_freshness, 2)} below {minimum_freshness}")
        return not failures, failures

    def _entity_coverage_score(self, entities: dict[str, Any]) -> int:
        entity_types = (
            "ai_tools",
            "companies",
            "pricing_plans",
            "affiliate_networks",
            "integrations",
            "use_cases",
            "target_audience",
            "competitors",
            "alternatives",
            "product_categories",
        )
        present = sum(1 for key in entity_types if _coerce_list(entities.get(key)))
        return min(100, 20 + present * 8)

    def _missing_entity_types(self, entities: dict[str, Any]) -> list[str]:
        entity_types = (
            "ai_tools",
            "companies",
            "pricing_plans",
            "affiliate_networks",
            "integrations",
            "use_cases",
            "target_audience",
            "competitors",
            "alternatives",
            "product_categories",
        )
        return [key for key in entity_types if not _coerce_list(entities.get(key))]

    def _queue_entry_for_package(self, package: ResearchPackage, topic: dict[str, Any]) -> dict[str, Any]:
        missing_info = [str(item) for item in package.quality.get("missing_information", [])]
        score = float(package.quality.get("overall_score", 0))
        queue_config = self.research_config.get("enrichment_queue", {})
        high = float(queue_config.get("high_priority_below_score", 45))
        medium = float(queue_config.get("medium_priority_below_score", 60))
        if score < high:
            priority = "high"
        elif score < medium:
            priority = "medium"
        else:
            priority = "low"
        return {
            "topic": str(topic.get("topic") or package.keyword),
            "slug": str(topic.get("slug") or package.slug),
            "missing_sources": package.sources.get("missing_source_count", 0),
            "missing_verified_sources": package.sources.get("missing_verified_sources", []),
            "missing_competitors": 0 if package.competitors.get("coverage_status") == "available" else 1,
            "missing_entities": len(package.entities.get("missing_entity_types", [])),
            "missing_affiliate_data": 0 if _coerce_list(package.entities.get("affiliate_networks")) else 1,
            "priority": priority,
            "reason": "; ".join(missing_info) if missing_info else "research quality below threshold",
            "created_at": datetime.now(UTC).isoformat(),
            "status": str(queue_config.get("default_status", "pending")),
            "score": score,
            "source_status": package.sources.get("source_status", "missing"),
            "source_confidence": package.sources.get("source_confidence", 0),
        }

    def _write_enrichment_report(self, rows: list[dict[str, Any]]) -> None:
        _write_json(self.data_dir / "research_enrichment_report.json", rows)
        _write_csv(self.data_dir / "research_enrichment_report.csv", rows)
        lines = ["# Research Enrichment Report", "", f"- Topics processed: {len(rows)}", ""]
        for row in rows[:20]:
            lines.append(
                f"- `{row['slug']}`: score {row['score']} -> {row['status']} "
                f"(verified sources {row.get('total_verified_source_score', 0)}, {row.get('source_status', 'missing')})"
            )
        _write_md(self.data_dir / "research_enrichment_report.md", lines)

    def _find_offer_row(self, brand: str) -> dict[str, Any]:
        for row in self.offer_rows:
            candidate = str(row.get("brand_name") or row.get("brand") or row.get("tool_name") or "").strip()
            if candidate.lower() == brand.lower():
                return row
        return {}

    def _load_existing_package(self, package_dir: Path) -> ResearchPackage | None:
        payload = _read_json(package_dir / "package.json", None)
        if not isinstance(payload, dict):
            return None
        try:
            return ResearchPackage(**payload)
        except TypeError:
            return None

    def _load_recent_packages(self, limit: int) -> list[ResearchPackage]:
        packages: list[ResearchPackage] = []
        if not self.research_root.exists():
            return packages
        paths = sorted(self.research_root.glob("*/package.json"), key=lambda path: path.stat().st_mtime, reverse=True)
        for path in paths[:limit]:
            payload = _read_json(path, None)
            if not isinstance(payload, dict):
                continue
            try:
                packages.append(ResearchPackage(**payload))
            except TypeError:
                continue
        return packages

    def _update_quality_report(self, packages: list[ResearchPackage]) -> None:
        seen: set[str] = set()
        rows: list[dict[str, Any]] = []
        for package in packages:
            if package.slug in seen:
                continue
            seen.add(package.slug)
            rows.append(
                {
                    "slug": package.slug,
                    "keyword": package.keyword,
                    "overall_score": package.quality.get("overall_score", 0),
                    "coverage": package.quality.get("coverage", 0),
                    "entity_coverage": package.quality.get("entity_coverage", 0),
                    "entity_coverage_score": package.quality.get("entity_coverage_score", 0),
                    "missing_entity_types": package.quality.get("missing_entity_types", []),
                    "faq_coverage": package.quality.get("faq_coverage", 0),
                    "outline_quality": package.quality.get("outline_quality", 0),
                    "affiliate_readiness": package.quality.get("affiliate_readiness", 0),
                    "source_quality": package.quality.get("source_quality", 0),
                    "official_docs_score": package.quality.get("official_docs_score", 0),
                    "pricing_source_score": package.quality.get("pricing_source_score", 0),
                    "affiliate_source_score": package.quality.get("affiliate_source_score", 0),
                    "total_verified_source_score": package.quality.get("total_verified_source_score", 0),
                    "source_confidence": package.quality.get("source_confidence", 0),
                    "source_status": package.quality.get("source_status", ""),
                    "status": package.quality.get("status", ""),
                    "missing_information": package.quality.get("missing_information", []),
                    "cache_hits": package.cache_hits,
                    "package_dir": package.package_dir,
                }
            )
        _write_json(self.data_dir / "research_quality_report.json", rows)
        _write_csv(self.data_dir / "research_quality_report.csv", rows)
        lines = ["# Research Quality Report", "", f"- Packages scored: {len(rows)}", ""]
        for row in rows[:20]:
            missing = ", ".join(row["missing_information"]) if row["missing_information"] else "none"
            lines.append(f"- `{row['slug']}`: score {row['overall_score']} ({row['status']}); missing: {missing}")
        _write_md(self.data_dir / "research_quality_report.md", lines)
