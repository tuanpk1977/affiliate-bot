from __future__ import annotations

import csv
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import settings
from modules.content_outline_engine import ContentOutlineEngine
from modules.keyword_intent_engine import KeywordIntentEngine
from modules.search_intent_analyzer import SearchIntentAnalyzer
from modules.topic_cluster_engine import TopicClusterEngine


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
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        for row in rows:
            writer.writerow({key: "; ".join(value) if isinstance(value, list) else value for key, value in row.items()})
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
        self.offer_rows = self._load_offer_rows()

    def build_research_package(self, topic: dict[str, Any]) -> ResearchPackage:
        keyword = str(topic.get("topic") or topic.get("title") or "").strip()
        slug = str(topic.get("slug") or _slugify(keyword))
        package_dir = self.research_root / slug
        existing = self._load_existing_package(package_dir)
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
        sources = self._build_sources(keyword, entities)
        faq = self._build_faq(keyword, keyword_intelligence, search_result.search_intent, entities)
        outline = self._build_outline(keyword, search_result.search_intent, keyword_intelligence, faq, topic)
        writing_plan = self._build_writing_plan(keyword, keyword_result, search_result, topic, entities, sources)
        quality = self._score_research(
            keyword_intelligence=keyword_intelligence,
            entities=entities,
            faq=faq,
            outline=outline,
            writing_plan=writing_plan,
            sources=sources,
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
            entities=self._merge_cached_entities(entities, cache_enrichment),
            competitors=competitors,
            sources=self._merge_cached_sources(sources, cache_enrichment),
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
        for row in self.offer_rows:
            brand = str(row.get("brand_name") or row.get("brand") or row.get("tool_name") or "").strip()
            niche = str(row.get("niche") or row.get("category") or "").strip()
            if brand and brand.lower() in text_pool.lower():
                companies.append(brand)
                products.append(brand)
                competitors.append(brand)
            elif niche and niche.lower() in keyword.lower():
                companies.append(brand)
                products.append(brand)
        ai_tools = list(dict.fromkeys(products))[:10]
        technologies = [token.title() for token in re.findall(r"\b(api|sdk|workflow|automation|agent|model|plugin|framework|cloud)\b", text_pool.lower())]
        frameworks = [token for token in ("React", "Next.js", "Python", "API", "SDK") if token.lower() in text_pool.lower()]
        pricing_plans = [item for item in keyword_intelligence.get("transactional_keywords", []) if any(term in item.lower() for term in ("pricing", "plans", "cost"))][:6]
        versions = re.findall(r"\b20\d{2}\b|\bv?\d+(?:\.\d+){0,2}\b", keyword)
        people = []
        organizations = list(dict.fromkeys(companies))[:10]
        return {
            "companies": list(dict.fromkeys(companies))[:10],
            "products": list(dict.fromkeys(products))[:10],
            "ai_tools": ai_tools,
            "people": people,
            "organizations": organizations,
            "technologies": list(dict.fromkeys(technologies))[:10],
            "frameworks": list(dict.fromkeys(frameworks))[:10],
            "pricing_plans": list(dict.fromkeys(pricing_plans))[:10],
            "versions": list(dict.fromkeys(versions))[:10],
            "competitors": list(dict.fromkeys(competitors))[:10],
        }

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
        brands = entities.get("competitors") or entities.get("products") or []
        profiles: list[dict[str, Any]] = []
        for brand in list(dict.fromkeys(brands))[:5]:
            row = self._find_offer_row(brand)
            site = str(row.get("website") or row.get("official_url") or "").strip()
            niche = str(row.get("niche") or row.get("category") or "AI software").strip()
            profiles.append(
                {
                    "site": site,
                    "title": f"{brand} overview",
                    "description": f"{brand} in the {niche} category relevant to {keyword}.",
                    "estimated_angle": f"Commercial comparison against {keyword} with workflow and pricing focus.",
                    "estimated_word_count": 1600 if "pricing" in keyword.lower() else 2200,
                    "missing_topics": ["pricing verification", "feature limitations", "ideal buyer fit"],
                    "content_strengths": ["clear brand recognition", "high buyer intent", "commercial relevance"],
                    "content_weaknesses": ["pricing may change", "requires fact verification", "needs differentiated examples"],
                }
            )
        return {"profiles": profiles}

    def _build_sources(self, keyword: str, entities: dict[str, Any]) -> dict[str, Any]:
        buckets = {
            "official_documentation": [],
            "pricing_pages": [],
            "product_pages": [],
            "release_notes": [],
            "api_docs": [],
            "research_papers": [],
            "blog_articles": [],
            "community": [],
        }
        for brand in entities.get("products", []):
            row = self._find_offer_row(brand)
            official = str(row.get("website") or row.get("official_url") or "").strip()
            if official:
                buckets["product_pages"].append({"label": brand, "url": official})
                buckets["pricing_pages"].append({"label": f"{brand} pricing source", "url": official})
        for key, items in buckets.items():
            seen: set[str] = set()
            unique: list[dict[str, str]] = []
            for item in items:
                url = str(item.get("url", "")).strip()
                if not url or url in seen:
                    continue
                seen.add(url)
                unique.append(item)
            buckets[key] = unique
        return {
            "topic": keyword,
            "trusted_sources": buckets,
            "reference_count": sum(len(items) for items in buckets.values()),
        }

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
        entity_coverage = min(100, 20 + sum(len(value) for value in entities.values() if isinstance(value, list)) * 3)
        faq_coverage = min(100, 20 + sum(len(value) for key, value in faq.items() if isinstance(value, list)) * 4)
        outline_quality = min(100, 30 + len(outline.get("heading_hierarchy", [])) * 10)
        affiliate_readiness = min(100, 25 + int(writing_plan.get("affiliate_value", 0)) // 2)
        source_quality = min(100, 15 + int(sources.get("reference_count", 0)) * 12)
        competitor_quality = min(100, 20 + len(competitors.get("profiles", [])) * 12)
        overall = round((coverage + entity_coverage + faq_coverage + outline_quality + affiliate_readiness + source_quality + competitor_quality) / 7, 2)
        missing: list[str] = []
        if source_quality < 40:
            missing.append("trusted sources are thin")
        if competitor_quality < 40:
            missing.append("competitor coverage is limited")
        if entity_coverage < 45:
            missing.append("entity extraction needs richer tool coverage")
        return {
            "overall_score": overall,
            "coverage": coverage,
            "entity_coverage": entity_coverage,
            "faq_coverage": faq_coverage,
            "outline_quality": outline_quality,
            "affiliate_readiness": affiliate_readiness,
            "source_quality": source_quality,
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
            "reference_count": sum(len(items) for items in trusted.values()),
        }
        return merged

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
                    "faq_coverage": package.quality.get("faq_coverage", 0),
                    "outline_quality": package.quality.get("outline_quality", 0),
                    "affiliate_readiness": package.quality.get("affiliate_readiness", 0),
                    "source_quality": package.quality.get("source_quality", 0),
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

