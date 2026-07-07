from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Protocol

from config import settings
from modules.ai_trend_discovery import TopicCandidate, TrendDiscoveryEngine, classify_content_type, slugify
from modules.editorial_business_intelligence import ContentLifecycleManager, EditorialBusinessIntelligence
from modules.content_growth_pipeline import generate_topic_package, normalize_topic_record, page_to_dict
from modules.content_planning_engine import ContentPlanningEngine
from modules.research_intelligence import ResearchIntelligencePlatform


UTC = timezone.utc
WEEKDAY_LABELS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
EXPANSION_TEMPLATES: tuple[tuple[str, str], ...] = (
    ("pillar", "Overview"),
    ("deep_dive", "API"),
    ("deep_dive", "Pricing"),
    ("deep_dive", "Prompt Guide"),
    ("deep_dive", "Comparison"),
    ("deep_dive", "Tutorial"),
    ("deep_dive", "FAQ"),
)


class TrendProvider(Protocol):
    name: str

    def fetch(self, engine: TrendDiscoveryEngine) -> list[Any]:
        ...


@dataclass(frozen=True)
class EngineConnectorProvider:
    name: str
    method_name: str

    def fetch(self, engine: TrendDiscoveryEngine) -> list[Any]:
        return list(getattr(engine, self.method_name)())


@dataclass(frozen=True)
class CandidateTopicRecord:
    generated_at: str
    keyword: str
    title: str
    slug: str
    intent: str
    category: str
    cluster: str
    score: float
    popularity: int
    freshness: int
    seo_opportunity: int
    affiliate_opportunity: int
    commercial_intent: int
    competition: int
    existing_website_coverage: int
    source_count: int
    source_list: list[str]
    priority: str
    article_type: str
    affiliate_score: str
    estimated_article_count: int
    related_keywords: list[str] = field(default_factory=list)
    planning_reasoning: list[str] = field(default_factory=list)
    already_published: bool = False


@dataclass(frozen=True)
class WeeklyTopicRecord:
    rank: int
    keyword: str
    title: str
    slug: str
    intent: str
    category: str
    cluster: str
    score: float
    affiliate_score: str
    estimated_article_count: int
    priority: str
    article_type: str
    related_keywords: list[str] = field(default_factory=list)
    planning_reasoning: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class EditorialCalendarEntry:
    publish_date: str
    day_of_week: str
    parent_keyword: str
    parent_slug: str
    keyword: str
    title: str
    slug: str
    stage: str
    article_type: str
    cluster: str
    priority: str
    intent: str
    related_keywords: list[str] = field(default_factory=list)
    reasoning: list[str] = field(default_factory=list)


def _output_path(name: str) -> Path:
    return settings.data_dir / name


def _write_json(path: Path, payload: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return path
    fieldnames = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: _serialize_csv_value(value) for key, value in row.items()})
    return path


def _append_jsonl(path: Path, rows: list[dict[str, Any]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    return path


def _serialize_csv_value(value: Any) -> Any:
    if isinstance(value, list):
        return "; ".join(str(item) for item in value)
    return value


def _default_providers() -> list[TrendProvider]:
    return [
        EngineConnectorProvider("google_trends", "google_trends"),
        EngineConnectorProvider("bing_trending", "bing_trending"),
        EngineConnectorProvider("reddit", "reddit"),
        EngineConnectorProvider("hacker_news", "hacker_news"),
        EngineConnectorProvider("product_hunt", "product_hunt"),
        EngineConnectorProvider("github_trending", "github_trending"),
        EngineConnectorProvider("x_twitter", "x_twitter"),
        EngineConnectorProvider("linkedin", "linkedin"),
        EngineConnectorProvider("youtube_trending", "youtube_trending"),
        EngineConnectorProvider("ai_newsletters", "ai_newsletters"),
        EngineConnectorProvider("local_keyword_intelligence", "local_keyword_intelligence"),
    ]


def _next_monday(start: date | None = None) -> date:
    current = start or date.today()
    return current - timedelta(days=current.weekday())


def _category_for_candidate(candidate: TopicCandidate) -> str:
    labels = {label.lower() for label in candidate.classifications}
    if "ai coding" in labels:
        return "AI Coding"
    if "seo" in labels:
        return "SEO"
    if "ai agents" in labels:
        return "AI Agents"
    lower = candidate.topic.lower()
    if "website" in lower or "builder" in lower:
        return "Website Builder"
    if "crm" in lower or "salesforce" in lower or "hubspot" in lower:
        return "CRM"
    if "video" in lower:
        return "AI Video"
    return "AI Software"


def _seed_related_keywords(candidate: TopicCandidate) -> list[str]:
    base = candidate.topic.replace("  ", " ").strip()
    seeds = [
        base,
        f"{base} pricing",
        f"{base} alternatives",
        f"{base} comparison",
        f"how to use {base}",
        f"{base} faq",
    ]
    seen: set[str] = set()
    result: list[str] = []
    for item in seeds:
        normalized = item.lower().strip()
        if normalized in seen:
            continue
        seen.add(normalized)
        result.append(item)
    return result[:6]


class WeeklyTrendIntelligenceEngine:
    """Weekly trend collection, ranking, and calendar generation layer."""

    def __init__(
        self,
        *,
        providers: list[TrendProvider] | None = None,
        timeout: int | None = None,
        max_per_source: int | None = None,
        candidate_limit: int | None = None,
        top_topics: int | None = None,
    ) -> None:
        self.providers = providers or _default_providers()
        self.timeout = timeout
        self.max_per_source = max_per_source or settings.editorial_max_per_source
        self.candidate_limit = candidate_limit or settings.editorial_candidate_limit
        self.top_topics = top_topics or settings.editorial_top_topics
        self.planner = ContentPlanningEngine()
        self.lifecycle = ContentLifecycleManager(settings.data_dir)
        self.research = ResearchIntelligencePlatform(
            data_dir=settings.data_dir,
            site_output_dir=getattr(settings, "site_output_dir", None),
            offers_file=getattr(settings, "offers_file", None),
            affiliate_links_file=getattr(settings, "affiliate_links_file", None),
            config=getattr(settings, "editorial_config", None),
        )

    def collect_candidates(self) -> list[CandidateTopicRecord]:
        engine = TrendDiscoveryEngine(timeout=self.timeout, max_per_source=self.max_per_source)
        signals: list[Any] = []
        source_status: dict[str, dict[str, Any]] = {}
        for provider in self.providers:
            try:
                found = provider.fetch(engine)[: self.max_per_source]
                signals.extend(found)
                source_status[provider.name] = {"status": "ok" if found else "empty", "signals": len(found)}
            except Exception as exc:
                source_status[provider.name] = {"status": "error", "signals": 0, "detail": f"{type(exc).__name__}: {exc}"}
        candidates = engine.aggregate(signals)[: self.candidate_limit]
        generated_at = datetime.now(UTC).isoformat()
        records = [self._candidate_record(candidate, generated_at) for candidate in candidates]
        self._write_candidate_outputs(records, source_status)
        return records

    def rank_topics(self, candidates: list[CandidateTopicRecord], top_n: int | None = None) -> list[WeeklyTopicRecord]:
        chosen = sorted(
            [item for item in candidates if not item.already_published],
            key=lambda item: (-item.score, item.competition, item.keyword),
        )[: (top_n or self.top_topics)]
        ranked = [
            WeeklyTopicRecord(
                rank=index,
                keyword=item.keyword,
                title=item.title,
                slug=item.slug,
                intent=item.intent,
                category=item.category,
                cluster=item.cluster,
                score=item.score,
                affiliate_score=item.affiliate_score,
                estimated_article_count=item.estimated_article_count,
                priority=item.priority,
                article_type=item.article_type,
                related_keywords=item.related_keywords,
                planning_reasoning=item.planning_reasoning,
            )
            for index, item in enumerate(chosen, 1)
        ]
        self._write_weekly_topics(ranked)
        return ranked

    def generate_editorial_calendar(self, topics: list[WeeklyTopicRecord], week_start: date | None = None) -> list[EditorialCalendarEntry]:
        monday = _next_monday(week_start)
        entries: list[EditorialCalendarEntry] = []
        for topic in topics:
            for offset, (stage, label) in enumerate(EXPANSION_TEMPLATES[: settings.editorial_calendar_days]):
                publish_date = monday + timedelta(days=offset)
                keyword = topic.keyword if offset == 0 else f"{topic.keyword} {label}".strip()
                title = f"{topic.title} {label}" if offset > 0 else topic.title
                slug = topic.slug if offset == 0 else slugify(f"{topic.slug} {label}")
                article_type = classify_content_type(keyword)
                reasoning = [f"{WEEKDAY_LABELS[offset]} editorial expansion for {topic.keyword}.", *topic.planning_reasoning[:3]]
                entries.append(
                    EditorialCalendarEntry(
                        publish_date=publish_date.isoformat(),
                        day_of_week=WEEKDAY_LABELS[offset],
                        parent_keyword=topic.keyword,
                        parent_slug=topic.slug,
                        keyword=keyword,
                        title=title,
                        slug=slug,
                        stage=stage,
                        article_type=article_type,
                        cluster=topic.cluster,
                        priority=topic.priority,
                        intent=topic.intent,
                        related_keywords=topic.related_keywords,
                        reasoning=reasoning,
                    )
                )
                self.lifecycle.record_transition(
                    slug=slug,
                    keyword=keyword,
                    to_stage="planned",
                    publish_date=publish_date.isoformat(),
                    article_type=article_type,
                    priority=topic.priority,
                )
        self._write_editorial_calendar(entries)
        return entries

    def run_weekly_cycle(self) -> dict[str, Any]:
        candidates = self.collect_candidates()
        weekly_topics = self.rank_topics(candidates)
        approved_topics: list[WeeklyTopicRecord] = []
        blocked_topics: list[dict[str, Any]] = []
        for topic in weekly_topics:
            package = self.research.build_research_package(
                {"topic": topic.keyword, "slug": topic.slug, "related_keywords": topic.related_keywords}
            )
            gate = self.research.evaluate_quality_gate(package, topic={"topic": topic.keyword, "slug": topic.slug})
            if gate.passed:
                approved_topics.append(topic)
            else:
                blocked_topics.append(
                    {
                        "topic": topic.keyword,
                        "slug": topic.slug,
                        "score": gate.score,
                        "threshold": gate.threshold,
                        "status": gate.status,
                    }
                )
        calendar = self.generate_editorial_calendar(approved_topics)
        intelligence = EditorialBusinessIntelligence(
            base_dir=getattr(settings, "base_dir", None),
            data_dir=settings.data_dir,
            site_output_dir=getattr(settings, "site_output_dir", None),
            offers_file=getattr(settings, "offers_file", None),
            affiliate_links_file=getattr(settings, "affiliate_links_file", None),
            config=getattr(settings, "editorial_config", None),
        ).run_weekly_intelligence(
            weekly_topics=[asdict(item) for item in weekly_topics],
            candidate_topics=[asdict(item) for item in candidates],
            editorial_calendar=[asdict(item) for item in calendar],
        )
        return {
            "candidates": len(candidates),
            "weekly_topics": len(weekly_topics),
            "approved_topics": len(approved_topics),
            "blocked_topics": blocked_topics,
            "calendar_entries": len(calendar),
            "weekly_topics_json": str(_output_path("weekly_topics.json")),
            "editorial_calendar_json": str(_output_path("editorial_calendar.json")),
            "knowledge_dashboard_json": str(settings.data_dir / "knowledge_dashboard.json"),
            "source_review_report_json": str(settings.data_dir / "source_review_report.json"),
            **intelligence,
        }

    def _candidate_record(self, candidate: TopicCandidate, generated_at: str) -> CandidateTopicRecord:
        related_keywords = _seed_related_keywords(candidate)
        plan = self.planner.create_plan(candidate.topic, related_keywords=related_keywords[1:])
        seo_opportunity = max(0, 100 - candidate.competition)
        commercial_intent = min(100, int(round(candidate.affiliate_opportunity * 0.6 + candidate.cpc_potential * 0.4)))
        existing_coverage = 100 if candidate.already_published else 0
        return CandidateTopicRecord(
            generated_at=generated_at,
            keyword=candidate.topic,
            title=candidate.topic,
            slug=candidate.slug,
            intent=candidate.search_intent,
            category=_category_for_candidate(candidate),
            cluster=str(plan.cluster.get("name") or candidate.topic),
            score=candidate.total_score,
            popularity=candidate.search_volume_potential,
            freshness=candidate.news_freshness,
            seo_opportunity=seo_opportunity,
            affiliate_opportunity=candidate.affiliate_opportunity,
            commercial_intent=commercial_intent,
            competition=candidate.competition,
            existing_website_coverage=existing_coverage,
            source_count=len(candidate.sources),
            source_list=candidate.sources,
            priority=candidate.recommended_priority,
            article_type=candidate.content_type,
            affiliate_score=candidate.affiliate_potential,
            estimated_article_count=settings.editorial_calendar_days,
            related_keywords=plan.cluster.get("keywords") if isinstance(plan.cluster.get("keywords"), list) else related_keywords,
            planning_reasoning=plan.reasoning[:6],
            already_published=candidate.already_published,
        )

    def _write_candidate_outputs(self, records: list[CandidateTopicRecord], source_status: dict[str, dict[str, Any]]) -> None:
        rows = [asdict(item) for item in records]
        _write_json(_output_path("weekly_topic_candidates.json"), rows)
        _write_csv(_output_path("weekly_topic_candidates.csv"), rows)
        _append_jsonl(_output_path("weekly_topic_history.jsonl"), rows)
        _write_json(_output_path("weekly_topic_provider_status.json"), source_status)

    def _write_weekly_topics(self, topics: list[WeeklyTopicRecord]) -> None:
        rows = [asdict(item) for item in topics]
        _write_json(_output_path("weekly_topics.json"), rows)
        _write_csv(_output_path("weekly_topics.csv"), rows)

    def _write_editorial_calendar(self, entries: list[EditorialCalendarEntry]) -> None:
        rows = [asdict(item) for item in entries]
        _write_json(_output_path("editorial_calendar.json"), rows)
        _write_csv(_output_path("editorial_calendar.csv"), rows)


def load_editorial_calendar(target_date: date | None = None) -> list[dict[str, Any]]:
    path = _output_path("editorial_calendar.json")
    if not path.exists():
        return []
    rows = json.loads(path.read_text(encoding="utf-8"))
    if target_date is None:
        return rows
    stamp = target_date.isoformat()
    return [row for row in rows if str(row.get("publish_date")) == stamp]


def run_daily_editorial_content(
    *,
    target_date: date | None = None,
    build: bool = False,
) -> dict[str, Any]:
    run_date = target_date or date.today()
    weekly_refresh: dict[str, Any] | None = None
    research_config = getattr(settings, "editorial_research_config", getattr(settings, "editorial_config", {}).get("research_intelligence", {}))
    if run_date.weekday() == 0 and bool(research_config.get("auto_refresh_weekly_on_monday", True)):
        weekly_refresh = WeeklyTrendIntelligenceEngine().run_weekly_cycle()
    rows = load_editorial_calendar(run_date)
    generated: list[dict[str, Any]] = []
    blocked_topics: list[dict[str, Any]] = []
    lifecycle = ContentLifecycleManager(settings.data_dir)
    for row in rows:
        topic = normalize_topic_record(
            {
                "topic": row.get("keyword", ""),
                "slug": row.get("slug", ""),
                "content_type": row.get("article_type", ""),
                "search_intent": row.get("intent", ""),
                "related_keywords": row.get("related_keywords", []),
                "suggested_internal_links": [],
            }
        )
        lifecycle.record_transition(
            slug=str(topic.get("slug", "")),
            keyword=str(topic.get("topic", "")),
            to_stage="research",
            scheduled_date=str(row.get("publish_date", "")),
        )
        try:
            page = generate_topic_package(topic)
        except RuntimeError as exc:
            blocked_topics.append({"topic": str(topic.get("topic", "")), "slug": str(topic.get("slug", "")), "reason": str(exc)})
            continue
        lifecycle.record_transition(slug=page.slug, keyword=page.topic, to_stage="generated", url=page.url)
        lifecycle.record_transition(slug=page.slug, keyword=page.topic, to_stage="reviewed", url=page.url)
        lifecycle.record_transition(slug=page.slug, keyword=page.topic, to_stage="published", url=page.url)
        generated.append(page_to_dict(page))

    build_result: dict[str, Any] = {"skipped": not build}
    if build and generated:
        import build_site

        build_result = build_site.incremental_build()

    stamp = (target_date or date.today()).isoformat()
    report = {
        "date": stamp,
        "weekly_refresh": weekly_refresh,
        "calendar_rows": len(rows),
        "generated_pages": generated,
        "blocked_topics": blocked_topics,
        "build": build_result,
    }
    _write_json(_output_path(f"daily_editorial_report_{stamp}.json"), report)
    return report
