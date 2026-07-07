from __future__ import annotations

import csv
import html
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from config import settings
from modules.ai_trend_discovery import (
    TrendDiscoveryEngine,
    classify_content_type,
    classify_search_intent,
    save_discovery_result,
    slugify,
)
from modules.content_review import ContentReviewEngine
from modules.content_planning_engine import ContentPlanningEngine
from modules.publish_gate import PublishGate
from modules.human_approval import HumanApprovalWorkflow
from modules.indexing_policy import INDEXABLE_ROBOTS_META
from modules.research_intelligence import ResearchIntelligencePlatform, ResearchPackage
from modules.site_stats import load_site_stats


BASE_URL = (settings.base_site_url or settings.site_domain or "https://smileaireviewhub.com").rstrip("/")
ROOT = settings.base_dir
DATA_DIR = settings.data_dir
SITE_OUTPUT = settings.site_output_dir
PUBLISHED_DIR = DATA_DIR / "published_static_pages"
PRODUCTION_DRAFTS = DATA_DIR / "production_article_drafts"
VIDEO_OUTPUT = ROOT / "video_output"
SOCIAL_DRAFTS = ROOT / "social_drafts"
REPORT_DIR = DATA_DIR / "content_growth_reports"
TRACKING_CSV = DATA_DIR / "content_growth_performance_log.csv"
TRENDING_JSON = DATA_DIR / "trending_topics.json"
_CONTENT_PLANNER: ContentPlanningEngine | None = None
_RESEARCH_PLATFORM: ResearchIntelligencePlatform | None = None
_CONTENT_REVIEW_ENGINE: ContentReviewEngine | None = None
_HUMAN_APPROVAL_WORKFLOW: HumanApprovalWorkflow | None = None
_PUBLISH_GATE: PublishGate | None = None


@dataclass(frozen=True)
class GeneratedPage:
    topic: str
    slug: str
    url: str
    article_file: Path
    video_folder: Path
    social_folder: Path
    content_type: str
    focus_keyword: str
    title: str
    description: str
    research: dict[str, Any]
    planning: dict[str, Any]
    review: dict[str, Any]
    human_approval: dict[str, Any]
    publish_gate: dict[str, Any]
    warnings: list[str]


def load_research_package(slug: str) -> dict[str, Any]:
    package_path = DATA_DIR / "research" / slug / "package.json"
    if not package_path.exists():
        raise FileNotFoundError(f"Research package not found for slug '{slug}': {package_path}")
    return json.loads(package_path.read_text(encoding="utf-8"))


def run_daily_content_growth(
    limit: int = 10,
    discover: bool = False,
    build: bool = True,
    submit_indexnow_enabled: bool = True,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Create website articles and manual-publishing assets from trend data.

    This intentionally publishes only to the website output. YouTube and social
    assets are draft files for manual use.
    """

    assert_external_publishing_disabled()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    PUBLISHED_DIR.mkdir(parents=True, exist_ok=True)
    VIDEO_OUTPUT.mkdir(parents=True, exist_ok=True)
    SOCIAL_DRAFTS.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    topics = load_or_discover_topics(limit=max(limit * 3, 20), discover=discover)
    selected = select_daily_topics(topics, limit=limit)
    generated: list[GeneratedPage] = []
    blocked_topics: list[dict[str, Any]] = []
    warnings: list[str] = []

    for topic in selected:
        if dry_run:
            continue
        try:
            page = generate_topic_package(topic)
        except RuntimeError as exc:
            blocked_topics.append({"topic": str(topic.get("topic", "")), "slug": str(topic.get("slug", "")), "reason": str(exc)})
            warnings.append(str(exc))
            continue
        generated.append(page)
        warnings.extend(page.warnings)
        append_tracking_row(page)

    build_result: dict[str, Any] = {"skipped": not build or dry_run}
    if build and not dry_run and generated:
        build_result = run_build_and_sync()

    indexnow_result: dict[str, Any] = {"skipped": not submit_indexnow_enabled or dry_run or not generated}
    if submit_indexnow_enabled and not dry_run and generated:
        indexnow_result = submit_generated_urls([page.url for page in generated])

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "limit": limit,
        "dry_run": dry_run,
        "selected_topics": selected,
        "generated_pages": [page_to_dict(page) for page in generated],
        "blocked_topics": blocked_topics,
        "build": build_result,
        "indexnow": indexnow_result,
        "warnings": warnings,
        "manual_posting_order": manual_posting_order(generated),
        "next_actions": [
            "Review each generated article for product facts marked needs manual verification.",
            "Upload review_video.mp4 manually only if you render a final video file later.",
            "Copy social draft files manually to social platforms.",
            "Paste YouTube URLs into video_output/upload_links.csv after upload, then run python scripts/update_youtube_links.py.",
        ],
        "safety": {
            "auto_website_publish": True,
            "auto_youtube_upload": False,
            "auto_social_post": False,
        },
    }
    write_daily_report(report)
    return report


def assert_external_publishing_disabled() -> None:
    if truthy(os.getenv("AUTO_YOUTUBE_UPLOAD")):
        raise RuntimeError("AUTO_YOUTUBE_UPLOAD must remain false for this workflow.")
    if truthy(os.getenv("AUTO_SOCIAL_POST")):
        raise RuntimeError("AUTO_SOCIAL_POST must remain false for this workflow.")


def load_or_discover_topics(limit: int, discover: bool) -> list[dict[str, Any]]:
    if discover or not TRENDING_JSON.exists():
        result = TrendDiscoveryEngine().run(limit=limit)
        save_discovery_result(result)
    payload = json.loads(TRENDING_JSON.read_text(encoding="utf-8"))
    selected = payload.get("selected_topics", payload if isinstance(payload, list) else [])
    return [normalize_topic_record(row) for row in selected if isinstance(row, dict)]


def normalize_topic_record(row: dict[str, Any]) -> dict[str, Any]:
    topic = str(row.get("topic") or row.get("title") or "").strip()
    content_type = str(row.get("content_type") or classify_content_type(topic))
    total_score = float(row.get("total_score") or row.get("score") or 0)
    affiliate_score = int(row.get("affiliate_opportunity") or 0)
    cpc_score = int(row.get("cpc_potential") or 0)
    evergreen_score = int(row.get("evergreen_value") or 0)
    return {
        **row,
        "topic": topic,
        "slug": str(row.get("slug") or slugify(topic)),
        "content_type": content_type,
        "search_intent": str(row.get("search_intent") or classify_search_intent(topic)),
        "recommended_priority": str(row.get("recommended_priority") or priority_from_score(total_score)),
        "estimated_business_value": str(row.get("estimated_business_value") or business_value(affiliate_score, cpc_score, evergreen_score)),
        "suggested_article_angle": str(row.get("suggested_article_angle") or default_article_angle(topic, content_type)),
        "suggested_video_angle": str(row.get("suggested_video_angle") or default_video_angle(topic, content_type)),
        "suggested_internal_links": list(row.get("suggested_internal_links") or default_internal_links(topic, content_type)),
        "total_score": total_score,
    }


def select_daily_topics(topics: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    published = existing_slugs()
    selected: list[dict[str, Any]] = []
    content_counts: dict[str, int] = {}
    for topic in sorted(topics, key=lambda row: (-float(row.get("total_score", 0)), str(row.get("topic", "")))):
        slug = str(topic.get("slug", ""))
        if not slug or slug in published:
            continue
        if any(is_near_duplicate(slug, str(existing.get("slug", ""))) for existing in selected):
            continue
        content_type = str(topic.get("content_type") or "article")
        if content_counts.get(content_type, 0) >= 3 and len(selected) < max(4, limit // 2):
            continue
        selected.append(topic)
        content_counts[content_type] = content_counts.get(content_type, 0) + 1
        if len(selected) >= limit:
            break
    return selected


def existing_slugs() -> set[str]:
    slugs: set[str] = set()
    for root in (PUBLISHED_DIR, SITE_OUTPUT, ROOT / "docs", ROOT / "content" / "posts", ROOT / "public" / "posts", VIDEO_OUTPUT):
        if not root.exists():
            continue
        for child in root.iterdir():
            if child.is_dir():
                slugs.add(child.name)
    return slugs


def get_content_planner() -> ContentPlanningEngine:
    global _CONTENT_PLANNER
    if _CONTENT_PLANNER is None:
        _CONTENT_PLANNER = ContentPlanningEngine()
    return _CONTENT_PLANNER


def get_research_platform() -> ResearchIntelligencePlatform:
    global _RESEARCH_PLATFORM
    if _RESEARCH_PLATFORM is None:
        _RESEARCH_PLATFORM = ResearchIntelligencePlatform(
            data_dir=DATA_DIR,
            site_output_dir=SITE_OUTPUT,
            offers_file=settings.offers_file,
            affiliate_links_file=settings.affiliate_links_file,
            config=settings.editorial_config,
        )
    return _RESEARCH_PLATFORM


def get_content_review_engine() -> ContentReviewEngine:
    global _CONTENT_REVIEW_ENGINE
    if _CONTENT_REVIEW_ENGINE is None:
        _CONTENT_REVIEW_ENGINE = ContentReviewEngine(
            data_dir=DATA_DIR,
            config=getattr(settings, "editorial_config", {}).get("content_review", {}),
        )
    return _CONTENT_REVIEW_ENGINE


def get_human_approval_workflow() -> HumanApprovalWorkflow:
    global _HUMAN_APPROVAL_WORKFLOW
    if _HUMAN_APPROVAL_WORKFLOW is None:
        _HUMAN_APPROVAL_WORKFLOW = HumanApprovalWorkflow(
            data_dir=DATA_DIR,
            config=getattr(settings, "editorial_config", {}).get("human_approval", {}),
        )
    return _HUMAN_APPROVAL_WORKFLOW


def get_publish_gate() -> PublishGate:
    global _PUBLISH_GATE
    if _PUBLISH_GATE is None:
        _PUBLISH_GATE = PublishGate(
            data_dir=DATA_DIR,
            site_output_dir=SITE_OUTPUT,
            config=getattr(settings, "editorial_config", {}).get("publish_gate", {}),
        )
    return _PUBLISH_GATE


def build_topic_from_research_package(slug: str) -> tuple[dict[str, Any], Any]:
    payload = load_research_package(slug)
    research_package = ResearchPackage(
        keyword=str(payload.get("keyword") or slug.replace("-", " ")),
        slug=str(payload.get("slug") or slug),
        generated_at=str(payload.get("generated_at") or datetime.now(timezone.utc).isoformat()),
        package_dir=str(payload.get("package_dir") or (DATA_DIR / "research" / slug)),
        keyword_intelligence=payload.get("keyword_intelligence") if isinstance(payload.get("keyword_intelligence"), dict) else {},
        keyword_summary=payload.get("keyword_summary") if isinstance(payload.get("keyword_summary"), dict) else {},
        outline=payload.get("outline") if isinstance(payload.get("outline"), dict) else {},
        faq=payload.get("faq") if isinstance(payload.get("faq"), dict) else {},
        entities=payload.get("entities") if isinstance(payload.get("entities"), dict) else {},
        competitors=payload.get("competitors") if isinstance(payload.get("competitors"), dict) else {},
        sources=payload.get("sources") if isinstance(payload.get("sources"), dict) else {},
        writing_plan=payload.get("writing_plan") if isinstance(payload.get("writing_plan"), dict) else {},
        quality=payload.get("quality") if isinstance(payload.get("quality"), dict) else {},
        cache_hits=payload.get("cache_hits") if isinstance(payload.get("cache_hits"), list) else [],
    )
    package_dir = Path(research_package.package_dir)
    quality_gate = get_research_platform().evaluate_quality_gate(research_package, topic={"topic": research_package.keyword, "slug": slug})
    research = {
        "keyword": research_package.keyword,
        "slug": research_package.slug,
        "package_dir": str(package_dir),
        "generated_at": research_package.generated_at,
        "keyword_intelligence": research_package.keyword_intelligence,
        "outline": research_package.outline,
        "faq": research_package.faq,
        "entities": research_package.entities,
        "competitors": research_package.competitors,
        "sources": research_package.sources,
        "writing_plan": research_package.writing_plan,
        "quality": research_package.quality,
        "cache_hits": research_package.cache_hits,
        "quality_gate": {
            "passed": quality_gate.passed,
            "score": quality_gate.score,
            "threshold": quality_gate.threshold,
            "override_used": quality_gate.override_used,
            "status": quality_gate.status,
        },
    }
    keyword_summary = payload.get("keyword_summary") if isinstance(payload.get("keyword_summary"), dict) else {}
    keyword_intelligence = payload.get("keyword_intelligence") if isinstance(payload.get("keyword_intelligence"), dict) else {}
    outline = payload.get("outline") if isinstance(payload.get("outline"), dict) else {}
    quality = payload.get("quality") if isinstance(payload.get("quality"), dict) else {}
    cluster = keyword_intelligence.get("cluster") if isinstance(keyword_intelligence.get("cluster"), dict) else {}
    topic = {
        "topic": str(payload.get("keyword") or slug.replace("-", " ")),
        "slug": str(payload.get("slug") or slug),
        "title": str(payload.get("keyword") or slug.replace("-", " ")),
        "content_type": "listicle" if str(keyword_summary.get("article_type") or "").lower() == "best list" else str(keyword_summary.get("article_type") or "article"),
        "article_type": str(keyword_summary.get("article_type") or "article"),
        "search_intent": str(keyword_summary.get("intent") or keyword_intelligence.get("search_intent") or "commercial"),
        "estimated_business_value": "medium",
        "suggested_internal_links": default_internal_links(str(payload.get("keyword") or slug), "listicle"),
        "related_keywords": coerce_text_list(keyword_intelligence.get("semantic_keywords"))[:8],
        "research": research,
        "planning": {
            "keyword": str(payload.get("keyword") or slug.replace("-", " ")),
            "intent": str(keyword_summary.get("intent") or keyword_intelligence.get("search_intent") or "commercial"),
            "article_type": str(keyword_summary.get("article_type") or "article"),
            "topic_cluster": {
                "name": str(cluster.get("seed_topic") or payload.get("keyword") or slug.replace("-", " ")),
                "keywords": coerce_text_list(cluster.get("supporting_topics")) or coerce_text_list(keyword_intelligence.get("semantic_keywords"))[:5],
            },
            "coverage_score": float(quality.get("coverage", 0)),
            "outline_sections": coerce_text_list(outline.get("seo_outline")),
            "reasoning": [*coerce_text_list(outline.get("reasoning")), *coerce_text_list(cluster.get("supporting_article_ideas"))],
            "related_keywords": coerce_text_list(keyword_intelligence.get("semantic_keywords"))[:8],
            "recommended_cta": str(outline.get("recommended_cta") or "Compare the shortlist and verify pricing on official sites."),
            "confidence": float(outline.get("confidence", 0.75)),
            "research_quality_score": float(quality.get("overall_score", 0)),
        },
    }
    return topic, research_package


def coerce_text_list(value: Any) -> list[str]:
    if isinstance(value, str):
        items = re.split(r"[,;\n]", value)
    elif isinstance(value, (list, tuple, set)):
        items = list(value)
    else:
        items = []
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        text = str(item).strip()
        normalized = text.lower()
        if not text or normalized in seen:
            continue
        seen.add(normalized)
        result.append(text)
    return result


def extract_related_keywords(topic: dict[str, Any]) -> list[str]:
    for key in ("related_keywords", "secondary_keywords", "keywords"):
        values = coerce_text_list(topic.get(key))
        if values:
            return values
    return []


def extract_entities(topic: dict[str, Any]) -> list[str]:
    values = coerce_text_list(topic.get("entities"))
    if values:
        return values
    research_entities = topic.get("research", {}).get("entities") if isinstance(topic.get("research"), dict) else {}
    if isinstance(research_entities, dict):
        products = coerce_text_list(research_entities.get("products"))
        companies = coerce_text_list(research_entities.get("companies"))
        merged = products + [item for item in companies if item not in products]
        if merged:
            return merged[:8]
    links = coerce_text_list(topic.get("suggested_internal_links"))
    derived = [segment for link in links for segment in link.strip("/").split("/") if segment]
    return derived[:5]

def research_payload(topic: dict[str, Any]) -> dict[str, Any]:
    value = topic.get("research")
    return value if isinstance(value, dict) else {}


def enrich_topic_with_research_and_planning(topic: dict[str, Any], planner: ContentPlanningEngine | None = None) -> dict[str, Any]:
    planner = planner or get_content_planner()
    research_platform = get_research_platform()
    keyword = str(topic.get("topic") or "").strip()
    research_package = research_platform.build_research_package(topic)
    research = {
        "keyword": research_package.keyword,
        "slug": research_package.slug,
        "package_dir": research_package.package_dir,
        "generated_at": research_package.generated_at,
        "keyword_intelligence": research_package.keyword_intelligence,
        "outline": research_package.outline,
        "faq": research_package.faq,
        "entities": research_package.entities,
        "competitors": research_package.competitors,
        "sources": research_package.sources,
        "writing_plan": research_package.writing_plan,
        "quality": research_package.quality,
        "cache_hits": research_package.cache_hits,
    }
    gate = research_platform.evaluate_quality_gate(research_package, topic=topic)
    research["quality_gate"] = {
        "passed": gate.passed,
        "score": gate.score,
        "threshold": gate.threshold,
        "override_used": gate.override_used,
        "status": gate.status,
    }
    if not gate.passed:
        raise RuntimeError(
            f"Research quality gate blocked generation for {keyword}: score {gate.score} below threshold {gate.threshold}. Topic added to enrichment queue."
        )
    research_keywords = []
    for key in (
        "secondary_keywords",
        "semantic_keywords",
        "long_tail_keywords",
        "question_keywords",
        "buyer_keywords",
        "comparison_keywords",
        "transactional_keywords",
        "informational_keywords",
    ):
        research_keywords.extend(coerce_text_list(research_package.keyword_intelligence.get(key)))
    plan = planner.create_plan(
        keyword=keyword,
        related_keywords=extract_related_keywords(topic) or research_keywords,
        entities=extract_entities({**topic, "research": research}),
    )
    planning = {
        "keyword": plan.keyword,
        "intent": plan.search_intent,
        "article_type": plan.article_type,
        "topic_cluster": plan.cluster,
        "coverage_score": plan.coverage_score,
        "outline_sections": coerce_text_list(research_package.outline.get("seo_outline")) or plan.outline_sections,
        "reasoning": [*coerce_text_list(research_package.outline.get("reasoning")), *plan.reasoning],
        "related_keywords": extract_related_keywords(topic) or coerce_text_list(research_package.keyword_intelligence.get("secondary_keywords")) or coerce_text_list(plan.cluster.get("keywords")),
        "recommended_cta": plan.recommended_cta,
        "confidence": plan.confidence,
        "research_quality_score": research_package.quality.get("overall_score", 0),
    }
    return {
        **topic,
        "search_intent": plan.search_intent or str(topic.get("search_intent") or ""),
        "research": research,
        "planning": planning,
    }


def planning_payload(topic: dict[str, Any]) -> dict[str, Any]:
    value = topic.get("planning")
    return value if isinstance(value, dict) else {}


def generate_topic_package(topic: dict[str, Any]) -> GeneratedPage:
    enriched_topic = enrich_topic_with_research_and_planning(topic)
    topic_name = str(enriched_topic["topic"])
    slug = str(enriched_topic["slug"])
    path = f"/{slug}/"
    url = BASE_URL + path
    title = seo_title(topic_name)
    description = meta_description(topic_name)
    links = resolve_internal_links(enriched_topic)
    warnings = fact_warnings(topic_name)

    article_html = render_article(enriched_topic, title, description, path, links, warnings)
    review = get_content_review_engine().review_content(
        topic=enriched_topic,
        html=article_html,
        title=title,
        description=description,
        url=url,
        internal_links=links or [(href, href) for href in coerce_text_list(enriched_topic.get("suggested_internal_links"))],
        warnings=warnings,
        research=research_payload(enriched_topic),
        planning=planning_payload(enriched_topic),
    )
    human_approval = get_human_approval_workflow().sync_review(review)
    publish_gate = get_publish_gate().evaluate(
        topic=enriched_topic,
        title=title,
        description=description,
        url=url,
        html=article_html,
        research=research_payload(enriched_topic),
        review=review,
        human_approval=human_approval,
        internal_links=links,
    )
    if str(publish_gate.get("status", "")) == "blocked":
        raise RuntimeError(
            f"Publish gate blocked generation for {topic_name}: {'; '.join(publish_gate.get('failures', [])) or 'publish checks failed'}."
        )
    article_file = write_article(path, article_html)
    site_file = write_article(path, article_html, output=SITE_OUTPUT)
    video_folder = write_video_drafts(enriched_topic, url, title)
    social_folder = write_social_drafts(enriched_topic, url, title)
    publish_gate = get_publish_gate().mark_published_local(slug, url=url, article_file=article_file, site_file=site_file) or publish_gate
    return GeneratedPage(
        topic=topic_name,
        slug=slug,
        url=url,
        article_file=article_file,
        video_folder=video_folder,
        social_folder=social_folder,
        content_type=str(enriched_topic.get("content_type") or "article"),
        focus_keyword=focus_keyword(topic_name),
        title=title,
        description=description,
        research=research_payload(enriched_topic),
        planning=planning_payload(enriched_topic),
        review=review,
        human_approval=human_approval,
        publish_gate=publish_gate,
        warnings=warnings,
    )


def generate_production_article_draft_from_package(slug: str) -> dict[str, Any]:
    topic, research_package = build_topic_from_research_package(slug)
    research = research_payload(topic)
    quality_gate = research.get("quality_gate") if isinstance(research.get("quality_gate"), dict) else {}
    if not bool(quality_gate.get("passed", False)):
        raise RuntimeError(
            f"Research quality gate blocked draft generation for {slug}: score {quality_gate.get('score', 0)} below threshold {quality_gate.get('threshold', 0)}."
        )
    title = seo_title(str(topic.get("topic") or slug.replace("-", " ")))
    description = meta_description(str(topic.get("topic") or slug.replace("-", " ")))
    path = f"/{slug}/"
    url = BASE_URL + path
    warnings = fact_warnings(str(topic.get("topic") or slug))
    links = resolve_internal_links(topic)
    topic = {**topic, "editorial": build_editorial_metadata(reviewed_by="Human review pending")}
    article_html = render_article(topic, title, description, path, links, warnings)
    article_markdown = render_article_markdown(topic, title, description, url, links, warnings)

    review = get_content_review_engine().review_content(
        topic=topic,
        html=article_html,
        title=title,
        description=description,
        url=url,
        internal_links=links or [(href, href) for href in coerce_text_list(topic.get("suggested_internal_links"))],
        warnings=warnings,
        research=research,
        planning=planning_payload(topic),
    )
    human_approval = get_human_approval_workflow().sync_review(review)
    publish_gate = get_publish_gate().evaluate(
        topic=topic,
        title=title,
        description=description,
        url=url,
        html=article_html,
        research=research,
        review=review,
        human_approval=human_approval,
        internal_links=links,
    )
    editorial = build_editorial_metadata(
        reviewed_by=str(human_approval.get("approved_by") or human_approval.get("status") or "Human review pending"),
        last_updated=str(human_approval.get("approved_at") or review.get("reviewed_at") or datetime.now(timezone.utc).isoformat()),
    )
    topic = {**topic, "editorial": editorial}
    article_html = render_article(topic, title, description, path, links, warnings)
    article_markdown = render_article_markdown(topic, title, description, url, links, warnings)

    draft_dir = PRODUCTION_DRAFTS / slug
    draft_dir.mkdir(parents=True, exist_ok=True)
    article_file = draft_dir / "index.html"
    article_file.write_text(article_html, encoding="utf-8")
    markdown_file = draft_dir / "article.md"
    markdown_file.write_text(article_markdown, encoding="utf-8")
    social_folder = write_social_drafts(topic, url, title)
    video_folder = write_video_drafts(topic, url, title)
    featured_prompt = featured_image_prompt(topic, research, planning_payload(topic))
    (draft_dir / "featured_image_prompt.txt").write_text(featured_prompt + "\n", encoding="utf-8")

    review_summary = build_review_summary(review, human_approval, publish_gate, research_package)
    (draft_dir / "review_summary.md").write_text(review_summary, encoding="utf-8")
    publish_readiness = {
        "slug": slug,
        "title": title,
        "description": description,
        "url": url,
        "review_status": review.get("status", ""),
        "human_approval_status": human_approval.get("status", ""),
        "publish_gate_status": publish_gate.get("status", ""),
        "publish_failures": publish_gate.get("failures", []),
        "research_quality_score": research.get("quality", {}).get("overall_score", 0),
        "verified_source_score": research.get("quality", {}).get("total_verified_source_score", 0),
        "word_count": review.get("word_count", 0),
        "featured_image_prompt_file": str(draft_dir / "featured_image_prompt.txt"),
        "social_folder": str(social_folder),
        "video_folder": str(video_folder),
        "article_markdown": str(markdown_file),
        "article_html": str(article_file),
    }
    (draft_dir / "publish_readiness_report.json").write_text(json.dumps(publish_readiness, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (draft_dir / "publish_readiness_report.md").write_text(build_publish_readiness_md(publish_readiness), encoding="utf-8")
    (draft_dir / "social_post_draft.md").write_text(build_primary_social_draft(topic, url, title), encoding="utf-8")
    (draft_dir / "metadata.json").write_text(
        json.dumps(
            {
                "slug": slug,
                "title": title,
                "description": description,
                "url": url,
                "featured_image_prompt": featured_prompt,
                "editorial": editorial,
                "social_folder": str(social_folder),
                "review": review,
                "human_approval": human_approval,
                "publish_gate": publish_gate,
                "research_quality_gate": quality_gate,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    page = GeneratedPage(
        topic=str(topic.get("topic") or slug.replace("-", " ")),
        slug=slug,
        url=url,
        article_file=article_file,
        video_folder=video_folder,
        social_folder=social_folder,
        content_type=str(topic.get("content_type") or "article"),
        focus_keyword=focus_keyword(str(topic.get("topic") or slug.replace("-", " "))),
        title=title,
        description=description,
        research=research,
        planning=planning_payload(topic),
        review=review,
        human_approval=human_approval,
        publish_gate=publish_gate,
        warnings=warnings,
    )
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generated_pages": [page_to_dict(page)],
        "blocked_topics": [],
        "build": {"skipped": True},
        "indexnow": {"skipped": True},
        "warnings": warnings,
        "manual_posting_order": [f"{page.topic}: wait for human approval before any publish action."],
    }
    write_daily_report(report)
    return {
        "page": page_to_dict(page),
        "draft_dir": str(draft_dir),
        "markdown_file": str(markdown_file),
        "review_summary_file": str(draft_dir / "review_summary.md"),
        "publish_readiness_report": str(draft_dir / "publish_readiness_report.json"),
        "metadata_file": str(draft_dir / "metadata.json"),
        "featured_image_prompt_file": str(draft_dir / "featured_image_prompt.txt"),
        "social_post_draft_file": str(draft_dir / "social_post_draft.md"),
    }


def sync_production_draft_assets(slug: str) -> dict[str, Any]:
    topic, _research_package = build_topic_from_research_package(slug)
    draft_dir = PRODUCTION_DRAFTS / slug
    metadata_path = draft_dir / "metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path.exists() else {}
    review = metadata.get("review") if isinstance(metadata.get("review"), dict) else {}
    human_approval = metadata.get("human_approval") if isinstance(metadata.get("human_approval"), dict) else {}
    publish_gate = metadata.get("publish_gate") if isinstance(metadata.get("publish_gate"), dict) else {}
    title = str(metadata.get("title") or seo_title(str(topic.get("topic") or slug.replace("-", " "))))
    description = str(metadata.get("description") or meta_description(str(topic.get("topic") or slug.replace("-", " "))))
    path = f"/{slug}/"
    url = str(metadata.get("url") or (BASE_URL + path))
    warnings = fact_warnings(str(topic.get("topic") or slug))
    links = resolve_internal_links(topic)
    editorial = build_editorial_metadata(
        reviewed_by=str(human_approval.get("approved_by") or human_approval.get("status") or "Human review pending"),
        last_updated=str(
            publish_gate.get("published_at")
            or human_approval.get("approved_at")
            or review.get("reviewed_at")
            or metadata.get("editorial", {}).get("last_updated")
            or datetime.now(timezone.utc).isoformat()
        ),
    )
    topic = {**topic, "editorial": editorial}
    article_html = render_article(topic, title, description, path, links, warnings)
    article_markdown = render_article_markdown(topic, title, description, url, links, warnings)
    draft_dir.mkdir(parents=True, exist_ok=True)
    article_file = draft_dir / "index.html"
    article_file.write_text(article_html, encoding="utf-8")
    markdown_file = draft_dir / "article.md"
    markdown_file.write_text(article_markdown, encoding="utf-8")
    social_folder = write_social_drafts(topic, url, title)
    (draft_dir / "featured_image_prompt.txt").write_text(featured_image_prompt(topic, research_payload(topic), planning_payload(topic)) + "\n", encoding="utf-8")
    metadata.update(
        {
            "slug": slug,
            "title": title,
            "description": description,
            "url": url,
            "editorial": editorial,
            "social_folder": str(social_folder),
        }
    )
    metadata_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if str(publish_gate.get("status", "")) == "published_local":
        write_article(path, article_html)
        write_article(path, article_html, output=SITE_OUTPUT)
    return {"slug": slug, "draft_dir": str(draft_dir), "social_folder": str(social_folder), "metadata_file": str(metadata_path)}


def render_article(
    topic: dict[str, Any],
    title: str,
    description: str,
    path: str,
    links: list[tuple[str, str]],
    warnings: list[str],
) -> str:
    topic_name = str(topic["topic"])
    content_type = str(topic.get("content_type") or "article")
    intent = str(topic.get("search_intent") or "commercial investigation")
    planning = planning_payload(topic)
    planning_cluster = planning.get("topic_cluster") if isinstance(planning.get("topic_cluster"), dict) else {}
    planning_outline = coerce_text_list(planning.get("outline_sections"))
    planning_reasoning = coerce_text_list(planning.get("reasoning"))
    related_keywords = coerce_text_list(planning.get("related_keywords"))
    recommended_cta = str(planning.get("recommended_cta") or "Check pricing notes")
    research = research_payload(topic)
    research_quality = research.get("quality") if isinstance(research.get("quality"), dict) else {}
    research_entities = research.get("entities") if isinstance(research.get("entities"), dict) else {}
    research_outline = research.get("outline") if isinstance(research.get("outline"), dict) else {}
    tool_profiles = article_tool_profiles(research)
    article_angle = str(topic.get("suggested_article_angle") or default_article_angle(topic_name, content_type))
    video_angle = str(topic.get("suggested_video_angle") or default_video_angle(topic_name, content_type))
    canonical = BASE_URL + path
    editorial = topic.get("editorial") if isinstance(topic.get("editorial"), dict) else build_editorial_metadata()
    faq_groups = research.get("faq") if isinstance(research.get("faq"), dict) else {}
    faq_items = []
    for key in ("beginner", "intermediate", "advanced", "comparison", "pricing", "troubleshooting"):
        faq_items.extend(coerce_text_list(faq_groups.get(key)))
    if not faq_items:
        faq_items = faq_questions(topic_name)
    schemas = [
        article_schema(title, description, canonical, topic_name, editorial),
        faq_schema(faq_items),
        breadcrumb_schema(title, canonical),
    ]
    body = f"""
  <main class="wrap">
    <section class="hero">
      <p class="eyebrow">{html.escape(content_type.title())} · Updated June 2026</p>
      <h1>{html.escape(title)}</h1>
      <p class="lede">{html.escape(description)}</p>
      <div class="cta-row">
        <a class="btn" href="#pricing">{html.escape(recommended_cta)}</a>
        <a class="btn secondary" href="#alternatives">Compare alternatives</a>
      </div>
    </section>
    <section class="card trust">
      <h2>Affiliate disclosure</h2>
      <p>Some links may be affiliate links. We may earn a commission at no extra cost to you. This article is independent research and does not claim an official partnership.</p>
    </section>
    {render_editorial_byline(editorial)}
    <section class="card">
      <h2>Table of contents</h2>
      <ol class="toc">
        <li><a href="#overview">Overview</a></li>
        <li><a href="#quick-verdict">Quick verdict</a></li>
        <li><a href="#methodology">How we evaluated</a></li>
        <li><a href="#shortlist">Shortlist</a></li>
        <li><a href="#comparison-table">Comparison table</a></li>
        <li><a href="#pros-cons">Pros and cons</a></li>
        <li><a href="#pricing">Pricing notes</a></li>
        <li><a href="#best-for">Best use cases</a></li>
        <li><a href="#alternatives">Alternatives</a></li>
        <li><a href="#official-sources">Official sources</a></li>
        <li><a href="#affiliate-placeholders">Affiliate placeholders</a></li>
        <li><a href="#research-package">Research package</a></li>
        <li><a href="#content-planning">Content planning</a></li>
        <li><a href="#faq">FAQ</a></li>
      </ol>
    </section>
    <section class="card" id="overview">
      <h2>Overview</h2>
      <p>{html.escape(article_angle)} The goal is to help buyers understand where this topic fits, what to verify, and how it compares with related software before spending money.</p>
      <p>Search intent: {html.escape(intent)}. This page is written for practical evaluation: workflow fit, pricing risk, feature tradeoffs, support expectations, and alternatives. Any product-specific pricing or plan limit should be treated as <strong>needs manual verification</strong> on the official vendor website.</p>
      <p>Video angle: {html.escape(video_angle)} The matching YouTube assets are saved as manual upload drafts in the video folder for this page.</p>
    </section>
    <section class="card" id="quick-verdict">
      <h2>Quick verdict</h2>
      <p>{html.escape(topic_name)} is worth covering because the topic combines current search interest with buyer intent. It should be useful for readers comparing tools, checking pricing, or deciding whether a software category belongs in their workflow.</p>
      <p>The research package currently supports a high-confidence shortlist led by {html.escape(tool_profiles[0]["name"] if tool_profiles else "the best-verified option")} because it has the strongest verified-source coverage in the approved package. Other tools remain useful comparison points, but any unverified pricing or feature claim should stay marked <strong>needs review</strong> until a matching official source record is added.</p>
      <ul>
        <li><strong>Best for:</strong> teams that need a clear shortlist before testing software.</li>
        <li><strong>Not best for:</strong> buyers expecting guaranteed pricing, official endorsement, or one-size-fits-all advice.</li>
        <li><strong>Verification required:</strong> pricing, free-trial terms, refund rules, usage limits, integrations, and affiliate terms.</li>
      </ul>
    </section>
    <section class="card" id="methodology">
      <h2>How we evaluated the shortlist</h2>
      <p>This article uses the approved research package only. That means the shortlist is based on verified official pages already stored in the local registry, entity extraction from the approved package, and the current quality-gate output for this topic. It does not pull in a fresh weekly trend list or ad hoc live browsing during drafting.</p>
      <p>For each tool, the evaluation looks at three layers: workflow fit, pricing verification confidence, and editorial risk. Workflow fit asks whether a tool can realistically reduce planning, writing, coordination, or knowledge-management friction for a small team. Pricing verification confidence checks whether the current package contains an official pricing page, release notes, or partner-page context. Editorial risk asks whether a recommendation would still hold after a buyer verifies the official site.</p>
      <p>That process matters because “best” articles often fail when they mix solid recommendations with weak sourcing. A productivity tool may look compelling in a generic roundup, but if the pricing page is unclear, the AI add-on terms change frequently, or the positioning is too broad, the article can become misleading. This draft keeps those uncertainties visible instead of smoothing them over.</p>
      <ul>
        <li><strong>Workflow fit:</strong> planning, drafting, note capture, async collaboration, and output quality.</li>
        <li><strong>Commercial fit:</strong> whether a buyer could compare plans, limitations, and alternatives responsibly.</li>
        <li><strong>Source discipline:</strong> official docs, pricing pages, partner pages, and release notes get priority over generic summaries.</li>
        <li><strong>Human review rule:</strong> because this is a “best” commercial article, it must stop at human approval even if AI review passes.</li>
      </ul>
    </section>
    <section class="card" id="shortlist">
      <h2>Shortlist and editor notes</h2>
      {render_tool_profile_cards(tool_profiles)}
    </section>
    <section class="card" id="comparison-table">
      <h2>Comparison table</h2>
      {render_tool_comparison_table(tool_profiles)}
      <p>The table is intentionally conservative. If the package cannot verify a claim with an official source record, the article treats that row as a buying question, not a fact. That keeps the page useful for selection while respecting the current source-governance rules.</p>
    </section>
    <section class="card" id="pros-cons">
      <h2>Pros and cons</h2>
      <div class="grid">
        <div>
          <h3>Pros</h3>
          <ul>
            <li>Useful for buyers already researching a real software decision.</li>
            <li>Can support comparison, pricing, review, and alternative search intent.</li>
            <li>Works well with internal links to related review and comparison pages.</li>
            <li>Current verified-source coverage is strong enough to frame a responsible shortlist instead of a shallow roundup.</li>
          </ul>
        </div>
        <div>
          <h3>Cons</h3>
          <ul>
            <li>Pricing and feature claims require manual verification.</li>
            <li>Competitive topics may need stronger examples and screenshots over time.</li>
            <li>Some vendor claims may be marketing language rather than proven outcomes.</li>
            <li>The current approved package still has limited competitor evidence, so the recommendations must remain cautious.</li>
          </ul>
        </div>
      </div>
      <p>A buyer should treat this page as a decision-support layer, not a final procurement document. The safest workflow is to use the shortlist here, then confirm plan limits, AI usage caps, admin controls, export rules, and contract details directly on each vendor’s official site before purchase.</p>
    </section>
    <section class="card" id="pricing">
      <h2>Pricing notes</h2>
      <p>Do not rely on copied pricing snippets. Pricing can change by region, billing period, usage tier, seat count, and promotion. Verify current pricing on the official website before buying or recommending any tool related to {html.escape(topic_name)}.</p>
      <p>When comparing costs, check total monthly cost, annual discounts, free-trial restrictions, cancellation terms, and whether essential features sit behind higher-tier plans.</p>
      <p>In the current approved package, {html.escape(tool_profiles[0]["name"] if tool_profiles else "the lead tool")} has the strongest verified pricing support. Other shortlisted tools can still appear in the article, but any plan-specific number, seat rule, or AI credit detail should remain marked <strong>needs review</strong> until the registry contains a matching verified pricing source.</p>
      <div class="table-scroll">
        <table>
          <thead><tr><th>Tool</th><th>Pricing confidence</th><th>What to verify manually</th></tr></thead>
          <tbody>{''.join(f'<tr><td>{html.escape(profile["name"])}</td><td>{html.escape(profile["pricing_confidence"])}</td><td>{html.escape(profile["pricing_note"])}</td></tr>' for profile in tool_profiles)}</tbody>
        </table>
      </div>
    </section>
    <section class="card" id="best-for">
      <h2>Best use cases</h2>
      {render_best_for_cards(tool_profiles)}
      <p>These use cases are meant to reduce buyer regret. Instead of asking which tool has the loudest marketing or the largest AI feature list, ask which product removes the most friction from a real weekly workflow: planning, capture, drafting, collaboration, or review.</p>
    </section>
    <section class="card" id="alternatives">
      <h2>Alternatives and related reading</h2>
      <p>Use these related pages to compare adjacent software categories and avoid evaluating this topic in isolation.</p>
      <ul>{''.join(f'<li><a href="{html.escape(href)}">{html.escape(label)}</a></li>' for href, label in links)}</ul>
      <p>If you already know your workflow is meeting-heavy, voice-heavy, or coding-heavy, move to a category-specific comparison page instead of forcing a broad productivity shortlist to answer a narrow problem.</p>
    </section>
    <section class="card" id="official-sources">
      <h2>Official source references</h2>
      <p>These are the strongest current source references attached to the approved package. They should be the first pages a human reviewer checks before approving any product recommendation copy.</p>
      {render_official_source_refs(research)}
    </section>
    <section class="card" id="affiliate-placeholders">
      <h2>Affiliate placeholder fields</h2>
      <p>This draft keeps monetization placeholders explicit so a reviewer can approve or replace them without altering the editorial body.</p>
      {render_affiliate_placeholders(tool_profiles)}
    </section>
    <section class="card" id="research-package">
      <h2>Research package snapshot</h2>
      <p>Research is mandatory before planning and drafting. The package is stored at <code>{html.escape(str(research.get("package_dir") or ""))}</code>.</p>
      <ul>
        <li><strong>Research quality score:</strong> {html.escape(str(research_quality.get("overall_score") or 0))}</li>
        <li><strong>Quality gate:</strong> {html.escape(str(research.get("quality_gate", {}).get("status") or "unknown"))}</li>
        <li><strong>Source quality:</strong> {html.escape(str(research_quality.get("source_quality") or 0))}</li>
        <li><strong>Verified source score:</strong> {html.escape(str(research_quality.get("total_verified_source_score") or 0))}</li>
        <li><strong>Verified source status:</strong> {html.escape(str(research_quality.get("source_status") or "missing"))}</li>
        <li><strong>Entity coverage:</strong> {html.escape(str(research_quality.get("entity_coverage") or 0))}</li>
        <li><strong>Outline quality:</strong> {html.escape(str(research_quality.get("outline_quality") or 0))}</li>
        <li><strong>Products detected:</strong> {html.escape(', '.join(coerce_text_list(research_entities.get("products"))) or topic_name)}</li>
      </ul>
      <h3>Research outline assets</h3>
      <ul>
        <li><strong>FAQ placement:</strong> {html.escape(str(research_outline.get("faq_placement") or "Before final CTA"))}</li>
        <li><strong>CTA placement:</strong> {html.escape(str(research_outline.get("cta_placement") or "Hero and final verdict"))}</li>
        <li><strong>Internal link opportunities:</strong> {html.escape(', '.join(coerce_text_list(research_outline.get("internal_link_opportunities"))) or 'None')}</li>
      </ul>
    </section>
    <section class="card" id="content-planning">
      <h2>Content planning snapshot</h2>
      <p>This page keeps the planning stage attached to the generated article so review, SEO checks, and publishing can use the same context.</p>
      <ul>
        <li><strong>Keyword:</strong> {html.escape(str(planning.get("keyword") or topic_name))}</li>
        <li><strong>Intent:</strong> {html.escape(str(planning.get("intent") or intent))}</li>
        <li><strong>Topic cluster:</strong> {html.escape(str(planning_cluster.get("name") or topic_name))}</li>
        <li><strong>Coverage score:</strong> {html.escape(str(planning.get("coverage_score") or 0))}</li>
        <li><strong>Research quality score:</strong> {html.escape(str(planning.get("research_quality_score") or 0))}</li>
        <li><strong>Related keywords:</strong> {html.escape(', '.join(related_keywords) if related_keywords else topic_name)}</li>
      </ul>
      <h3>Planned outline sections</h3>
      <ol>{''.join(f'<li>{html.escape(section)}</li>' for section in planning_outline)}</ol>
      <h3>Planning reasoning</h3>
      <ul>{''.join(f'<li>{html.escape(reason)}</li>' for reason in planning_reasoning[:6])}</ul>
    </section>
    <section class="card">
      <h2>Research methodology</h2>
      <p>This page uses trend discovery signals, commercial-intent scoring, competition estimates, and existing Smile AI Review Hub topic coverage. It favors useful comparison-focused content over thin news summaries.</p>
      <p>Warnings: {html.escape('; '.join(warnings) if warnings else 'No critical warnings. Verify vendor facts before final promotion.')}</p>
      <p>EEAT note: recommendations in this draft are limited to what the current approved package can support. Where the package is thin, the article says so directly instead of claiming precision it does not have.</p>
    </section>
    <section class="card" id="faq">
      <h2>FAQ</h2>
      {faq_html(faq_items)}
    </section>
    <section class="card">
      <h2>Final verdict</h2>
      <p>{render_buying_guidance(tool_profiles)}</p>
      <p>{html.escape(topic_name)} is a good candidate for Smile AI Review Hub because it can serve readers who want practical, buyer-focused guidance. The strongest next step is human approval on the shortlist language, followed by verified screenshots and any additional competitor snapshots that tighten the comparison.</p>
      <a class="btn" href="/">Visit Smile AI Review Hub</a>
    </section>
  </main>
"""
    return html_shell(title, description, canonical, body, schemas)


def article_tool_profiles(research: dict[str, Any]) -> list[dict[str, str]]:
    entities = research.get("entities") if isinstance(research.get("entities"), dict) else {}
    source_rows = research.get("sources", {}).get("verified_sources", []) if isinstance(research.get("sources"), dict) else []
    verified_brands = {str(row.get("brand", "")).strip().lower(): row for row in source_rows if isinstance(row, dict)}
    names = coerce_text_list(entities.get("products")) or [str(research.get("keyword") or "Approved tool shortlist")]
    profiles: list[dict[str, str]] = []
    for index, name in enumerate(names[:4]):
        lower = name.lower()
        is_verified = lower in verified_brands
        best_for = {
            "notion": "teams that want one workspace for notes, docs, wikis, and lightweight AI support",
            "notion ai": "writers and operators who already use Notion and want AI inside an existing workspace",
            "gamma": "fast visual-first drafting, internal presentations, and turning raw notes into clean decks",
        }.get(lower, "buyers who need broad productivity support and can verify fit in a real workflow")
        use_case = {
            "notion": "knowledge management, async collaboration, meeting notes, and structured project planning",
            "notion ai": "summaries, first-pass drafting, and turning existing notes into cleaner working documents",
            "gamma": "presentation creation, quick concept packaging, and stakeholder-ready visual communication",
        }.get(lower, "workflow cleanup, planning, and content organization")
        pros = {
            "notion": "strong verified source coverage, broad workspace flexibility, and clear planning value",
            "notion ai": "fits naturally into existing Notion workflows and reduces context switching for drafting",
            "gamma": "useful when teams need speed from blank page to presentation-ready output",
        }.get(lower, "useful shortlist candidate with commercial-intent relevance")
        cons = {
            "notion": "buyers still need to verify workspace complexity and AI add-on fit against their exact team size",
            "notion ai": "package-level pricing precision still needs human review before recommendation copy is finalized",
            "gamma": "current package lacks verified pricing and release-note depth, so exact claims must stay conservative",
        }.get(lower, "source depth is thinner than the lead verified option")
        pricing_confidence = "verified official pricing" if is_verified and lower == "notion" else "needs review"
        pricing_note = "Use the official pricing page in the source registry before naming plan details." if pricing_confidence == "verified official pricing" else "Do not state live plan prices until the registry has a verified pricing page for this tool."
        source_status = "verified" if is_verified else "needs_review"
        profiles.append(
            {
                "name": name,
                "best_for": best_for,
                "use_case": use_case,
                "pros": pros,
                "cons": cons,
                "pricing_confidence": pricing_confidence,
                "pricing_note": pricing_note,
                "source_status": source_status,
                "summary": f"{name} stays on the shortlist because it addresses {use_case}, but the recommendation strength depends on verified-source depth.",
                "badge": "Best verified option" if index == 0 else "Shortlist candidate",
            }
        )
    return profiles


def render_tool_profile_cards(tool_profiles: list[dict[str, str]]) -> str:
    cards: list[str] = []
    for profile in tool_profiles:
        cards.append(
            f"""
      <section class="card">
        <h3>{html.escape(profile['name'])} <small>· {html.escape(profile['badge'])}</small></h3>
        <p><strong>Best for:</strong> {html.escape(profile['best_for'])}.</p>
        <p>{html.escape(profile['summary'])}</p>
        <p><strong>Strength:</strong> {html.escape(profile['pros'])}.</p>
        <p><strong>Risk:</strong> {html.escape(profile['cons'])}.</p>
        <p><strong>Pricing confidence:</strong> {html.escape(profile['pricing_confidence'])}. {html.escape(profile['pricing_note'])}</p>
      </section>
"""
        )
    return "".join(cards)


def render_tool_comparison_table(tool_profiles: list[dict[str, str]]) -> str:
    rows = "".join(
        f"<tr><td>{html.escape(profile['name'])}</td><td>{html.escape(profile['best_for'])}</td><td>{html.escape(profile['pricing_confidence'])}</td><td>{html.escape(profile['source_status'])}</td><td>{html.escape(profile['use_case'])}</td></tr>"
        for profile in tool_profiles
    )
    return f"""
      <div class="table-scroll">
        <table>
          <thead><tr><th>Tool</th><th>Best for</th><th>Pricing confidence</th><th>Source status</th><th>Use-case anchor</th></tr></thead>
          <tbody>{rows}</tbody>
        </table>
      </div>
"""


def render_best_for_cards(tool_profiles: list[dict[str, str]]) -> str:
    blocks = "".join(
        f"<div><h3>{html.escape(profile['name'])}</h3><p>{html.escape(profile['best_for']).capitalize()}.</p><p>{html.escape(profile['use_case']).capitalize()}.</p></div>"
        for profile in tool_profiles
    )
    return f'<div class="grid">{blocks}</div>'


def render_official_source_refs(research: dict[str, Any]) -> str:
    verified = research.get("sources", {}).get("verified_sources", []) if isinstance(research.get("sources"), dict) else []
    rows = []
    for row in verified:
        if not isinstance(row, dict):
            continue
        rows.append(
            f"<li><strong>{html.escape(str(row.get('brand') or 'Source'))}:</strong> "
            f"{html.escape(str(row.get('source_name') or row.get('source_type') or 'official source'))} "
            f"(<code>{html.escape(str(row.get('source_type') or 'source'))}</code>) - "
            f"<a href=\"{html.escape(str(row.get('source_url') or ''), quote=True)}\">{html.escape(str(row.get('source_url') or 'source link'))}</a></li>"
        )
    if not rows:
        rows.append("<li>No verified source references are attached to this package.</li>")
    return f"<ul>{''.join(rows)}</ul>"


def render_affiliate_placeholders(tool_profiles: list[dict[str, str]]) -> str:
    items = []
    for profile in tool_profiles:
        slug = slugify(profile["name"])
        items.append(
            f"<li><strong>{html.escape(profile['name'])}</strong>: <code>{{{{AFFILIATE_LINK_{html.escape(slug.upper()).replace('-', '_')}}}}}</code> "
            f"and <code>{{{{CTA_LABEL_{html.escape(slug.upper()).replace('-', '_')}}}}}</code></li>"
        )
    return f"<ul>{''.join(items)}</ul>"


def render_buying_guidance(tool_profiles: list[dict[str, str]]) -> str:
    if not tool_profiles:
        return "Use the approved package as a shortlist, verify the official pricing page, and choose the option that reduces your real weekly workflow friction instead of the one with the broadest marketing claim."
    lead = tool_profiles[0]["name"]
    return (
        f"Start with {lead} if you want the strongest current source confidence in this draft, then challenge it against your real workflow. "
        "If your team is more presentation-heavy than documentation-heavy, or if you only need lightweight AI drafting inside an existing stack, test the narrower alternatives before committing. "
        "The right buyer move is to shortlist two options, verify the official pricing and limits, run one real task in each tool, and approve only the recommendation language that still looks honest after that test."
    )


def render_article_markdown(
    topic: dict[str, Any],
    title: str,
    description: str,
    url: str,
    links: list[tuple[str, str]],
    warnings: list[str],
) -> str:
    research = research_payload(topic)
    planning = planning_payload(topic)
    editorial = topic.get("editorial") if isinstance(topic.get("editorial"), dict) else build_editorial_metadata()
    tool_profiles = article_tool_profiles(research)
    faq_groups = research.get("faq") if isinstance(research.get("faq"), dict) else {}
    faq_items: list[str] = []
    for key in ("beginner", "intermediate", "advanced", "comparison", "pricing", "troubleshooting"):
        faq_items.extend(coerce_text_list(faq_groups.get(key)))
    related_links = "\n".join(f"- [{label}]({href})" for href, label in links) or "- No safe internal links found."
    verified_sources = research.get("sources", {}).get("verified_sources", []) if isinstance(research.get("sources"), dict) else []
    source_lines = "\n".join(
        f"- **{row.get('brand', 'Source')}**: {row.get('source_name', row.get('source_type', 'source'))} - {row.get('source_url', '')}"
        for row in verified_sources
        if isinstance(row, dict)
    ) or "- No verified official sources are attached to this package."
    shortlist = "\n".join(
        f"### {profile['name']}\n\n"
        f"Best for: {profile['best_for']}.\n\n"
        f"Why it made the shortlist: {profile['summary']}\n\n"
        f"Strength: {profile['pros']}.\n\n"
        f"Risk: {profile['cons']}.\n\n"
        f"Pricing confidence: {profile['pricing_confidence']}. {profile['pricing_note']}\n"
        for profile in tool_profiles
    )
    faq_md = "\n".join(
        f"### {question}\n\nVerify current pricing, plan limits, integrations, AI usage caps, and policy terms on the official vendor site before you buy or recommend the tool.\n"
        for question in faq_items
    )
    comparison_rows = "\n".join(
        f"| {profile['name']} | {profile['best_for']} | {profile['pricing_confidence']} | {profile['source_status']} | {profile['use_case']} |"
        for profile in tool_profiles
    )
    return f"""# {title}

{description}

- Canonical URL: {url}
- Author: {editorial.get('author_name', '')}
- Author profile: {editorial.get('author_profile_url', '')}
- Reviewed by: {editorial.get('reviewed_by', '')}
- Last updated: {editorial.get('last_updated', '')}
- Editorial policy: {editorial.get('editorial_policy_url', '')}
- Affiliate disclosure: {editorial.get('affiliate_disclosure_url', '')}
- Review status target: human approval before publish
- Research quality score: {research.get('quality', {}).get('overall_score', 0)}
- Verified source score: {research.get('quality', {}).get('total_verified_source_score', 0)}

## Intro

This production draft is based only on the approved research package for **{topic.get('topic', '')}**. It is written for buyers who need a practical shortlist, not for readers who want hype, copied pricing snippets, or blanket recommendations without source discipline.

The core question is simple: which AI productivity tools are most likely to reduce planning, writing, knowledge-management, or collaboration friction for a real team? The article keeps that question tied to verified official sources and marks uncertain pricing or feature claims as **needs review**.

## How We Evaluated the Shortlist

We used the approved package's keyword intent, outline, entity extraction, official-source registry coverage, and research quality scoring. We did not pull a new weekly trend list or bypass any gate.

The shortlist focuses on:

- Workflow fit for planning, drafting, organizing, and sharing work
- Pricing verification confidence
- Official documentation quality
- Editorial and affiliate safety
- Whether the recommendation still looks honest after human review

## Quick Verdict

{render_buying_guidance(tool_profiles)}

## Tool Shortlist

{shortlist}

## Comparison Table

| Tool | Best for | Pricing confidence | Source status | Use-case anchor |
| --- | --- | --- | --- | --- |
{comparison_rows}

## Best-For Use Cases

{"".join(f"- **{profile['name']}**: {profile['best_for']}. Primary use case: {profile['use_case']}.\n" for profile in tool_profiles)}

## Pros and Cons

### Pros

- Stronger buyer guidance than a shallow roundup because the article stays tied to the approved package.
- Clear pricing-confidence labels reduce the risk of publishing unsupported claims.
- Internal-link support lets this article connect to deeper reviews, comparisons, and category pages.
- Human approval remains mandatory for the final recommendation layer.

### Cons

- Competitor coverage in the current package is still limited.
- Exact pricing for every shortlisted tool is not fully verified yet.
- Visual proof such as screenshots and product walkthroughs still needs manual editorial work.
- Any recommendation can age quickly if vendor plans or AI limits change.

## Pricing Section

Do not rely on copied pricing snippets. Verify current pricing on the official vendor site before naming plan details, limits, AI credits, or seat rules.

{"".join(f"- **{profile['name']}**: {profile['pricing_confidence']} - {profile['pricing_note']}\n" for profile in tool_profiles)}

## Official Source References

{source_lines}

## Affiliate Placeholder Fields

{"".join(f"- **{profile['name']}**: `{{{{AFFILIATE_LINK_{slugify(profile['name']).upper().replace('-', '_')}}}}}` and `{{{{CTA_LABEL_{slugify(profile['name']).upper().replace('-', '_')}}}}}`\n" for profile in tool_profiles)}

## Internal Links

{related_links}

## Planning Context

- Intent: {planning.get('intent', '')}
- Coverage score: {planning.get('coverage_score', 0)}
- Related keywords: {", ".join(coerce_text_list(planning.get('related_keywords')))}
- Recommended CTA: {planning.get('recommended_cta', '')}

## FAQ

{faq_md}

## Conclusion

Use this draft as a buyer guidance page, not as a final approved recommendation. Start with the best-verified option, compare it against one narrower alternative, verify the official pricing page yourself, and only then decide whether the tool deserves a stronger recommendation. This article should remain blocked until human approval confirms that the shortlist language is fair, source-backed, and commercially safe.

## Warnings

{chr(10).join(f"- {warning}" for warning in warnings) if warnings else "- No critical warnings beyond standard manual verification."}
"""


def featured_image_prompt(topic: dict[str, Any], research: dict[str, Any], planning: dict[str, Any]) -> str:
    tool_names = ", ".join(profile["name"] for profile in article_tool_profiles(research)[:3]) or str(topic.get("topic") or "")
    return (
        f"Create a clean editorial hero image for '{topic.get('topic', '')}'. "
        f"Show a modern workspace comparison scene with subtle cards for {tool_names}, a productivity dashboard feel, teal and slate accents, "
        "and a buyer-guide tone. Include no brand logos, no pricing numbers, and no crowded UI. Leave space for a headline overlay and keep it professional, trustworthy, and EEAT-oriented."
    )


def build_review_summary(review: dict[str, Any], human_approval: dict[str, Any], publish_gate: dict[str, Any], research_package: ResearchPackage) -> str:
    return f"""# Review Summary

- Slug: `{review.get('slug', '')}`
- Review status: `{review.get('status', '')}`
- Human approval status: `{human_approval.get('status', '')}`
- Publish gate status: `{publish_gate.get('status', '')}`
- Word count: `{review.get('word_count', 0)}`
- Publish readiness: `{review.get('publish_readiness', 0)}`
- Research quality score: `{research_package.quality.get('overall_score', 0)}`
- Verified source score: `{research_package.quality.get('total_verified_source_score', 0)}`

## Gate Notes

- AI review failures: {', '.join(review.get('failures', [])) or 'none'}
- Publish gate failures: {', '.join(publish_gate.get('failures', [])) or 'none'}
- Missing research information: {', '.join(research_package.quality.get('missing_information', [])) or 'none'}
"""


def build_publish_readiness_md(payload: dict[str, Any]) -> str:
    failures = payload.get("publish_failures", [])
    return f"""# Publish Readiness Report

- Slug: `{payload.get('slug', '')}`
- Title: `{payload.get('title', '')}`
- Review status: `{payload.get('review_status', '')}`
- Human approval status: `{payload.get('human_approval_status', '')}`
- Publish gate status: `{payload.get('publish_gate_status', '')}`
- Research quality score: `{payload.get('research_quality_score', 0)}`
- Verified source score: `{payload.get('verified_source_score', 0)}`
- Word count: `{payload.get('word_count', 0)}`

## Blocking Issues

{chr(10).join(f"- {item}" for item in failures) if failures else "- None"}
"""


def build_primary_social_draft(topic: dict[str, Any], url: str, title: str) -> str:
    return f"""# Social Post Draft

## LinkedIn

I just finished a buyer-focused draft on **{title}**.

The goal was not to hype every AI productivity tool. It was to build a shortlist that stays honest about source confidence, pricing verification, and workflow fit.

Key takeaway: the best tool is usually the one that reduces planning and coordination friction in a real weekly workflow, not the one with the loudest feature list.

Read the article draft:
{url}

#AIProductivity #SaaS #BuyerGuide #ContentOps
"""


def build_editorial_metadata(*, reviewed_by: str = "", last_updated: str = "") -> dict[str, str]:
    stats = load_site_stats()
    author = stats.get("author", {}) if isinstance(stats.get("author"), dict) else {}
    author_name = str(author.get("name") or "Nguyen Quoc Tuan")
    author_profile_url = str(author.get("profileUrl") or f"{BASE_URL}/about-author/")
    author_bio = str(author.get("bio") or "Independent AI & SaaS researcher covering software, automation, and practical buyer workflows.")
    updated = last_updated or datetime.now(timezone.utc).isoformat()
    return {
        "author_name": author_name,
        "author_profile_url": author_profile_url,
        "author_bio": author_bio,
        "reviewed_by": reviewed_by,
        "last_updated": updated,
        "editorial_policy_url": f"{BASE_URL}/editorial-policy/",
        "affiliate_disclosure_url": f"{BASE_URL}/affiliate-disclosure/",
    }


def render_editorial_byline(editorial: dict[str, Any]) -> str:
    author_name = str(editorial.get("author_name") or "Nguyen Quoc Tuan")
    profile = str(editorial.get("author_profile_url") or "").strip()
    author_bio = str(editorial.get("author_bio") or "").strip()
    reviewed_by = str(editorial.get("reviewed_by") or "Human review pending").strip()
    last_updated = str(editorial.get("last_updated") or "").strip()
    editorial_policy_url = str(editorial.get("editorial_policy_url") or "/editorial-policy/").strip()
    affiliate_disclosure_url = str(editorial.get("affiliate_disclosure_url") or "/affiliate-disclosure/").strip()
    author_html = html.escape(author_name)
    if profile:
        author_html = f'<a href="{html.escape(profile, quote=True)}">{author_html}</a>'
    return f"""
    <section class="card trust">
      <h2>Author and editorial review</h2>
      <p><strong>Author:</strong> {author_html}</p>
      <p><strong>Reviewed by:</strong> {html.escape(reviewed_by)}</p>
      <p><strong>Last updated:</strong> {html.escape(last_updated)}</p>
      <p>{html.escape(author_bio)}</p>
      <p><a href="{html.escape(editorial_policy_url, quote=True)}">Editorial policy</a> · <a href="{html.escape(affiliate_disclosure_url, quote=True)}">Affiliate disclosure</a></p>
    </section>
    """


def qiita_relevant(topic: dict[str, Any]) -> bool:
    haystack = " ".join(
        [
            str(topic.get("topic") or ""),
            str(topic.get("article_type") or ""),
            str(topic.get("content_type") or ""),
            str(topic.get("search_intent") or ""),
        ]
    ).lower()
    markers = ("developer", "coding", "code", "api", "sdk", "cli", "automation", "technical", "programming")
    return any(marker in haystack for marker in markers)


def html_shell(title: str, description: str, canonical: str, body: str, schemas: list[dict[str, Any]]) -> str:
    schema_tags = "\n".join(
        f'<script type="application/ld+json">{json.dumps(schema, ensure_ascii=False)}</script>' for schema in schemas
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <meta name="description" content="{html.escape(description)}">
  <meta name="robots" content="{INDEXABLE_ROBOTS_META}">
  <link rel="canonical" href="{html.escape(canonical, quote=True)}">
  <meta property="og:title" content="{html.escape(title)}">
  <meta property="og:description" content="{html.escape(description)}">
  <meta property="og:type" content="article">
  <meta property="og:url" content="{html.escape(canonical, quote=True)}">
  <meta property="og:image" content="{html.escape(BASE_URL + '/assets/og/site.svg', quote=True)}">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="{html.escape(title)}">
  <meta name="twitter:description" content="{html.escape(description)}">
  <meta name="twitter:image" content="{html.escape(BASE_URL + '/assets/og/site.svg', quote=True)}">
  {schema_tags}
  <style>{page_css()}</style>
</head>
<body>
  <nav class="nav"><div class="wrap nav-inner"><a class="logo" href="/">MS Smile AI Review Hub</a><div><a href="/reviews/">Reviews</a><a href="/comparisons/">Comparisons</a><a href="/contact/">Contact</a></div></div></nav>
  {body}
  <footer><div class="wrap"><p><strong>MS Smile AI Review Hub</strong></p><p>Contact: <a href="mailto:contact@smileaireviewhub.com">contact@smileaireviewhub.com</a></p><p><a href="/affiliate-disclosure/">Affiliate Disclosure</a> <a href="/privacy/">Privacy Policy</a> <a href="/about/">About</a></p></div></footer>
</body>
</html>
"""


def page_css() -> str:
    return """:root{--bg:#f7f9fc;--text:#17202a;--muted:#596579;--line:#dbe3ef;--card:#fff;--accent:#0f766e;--warn:#9a3412}*{box-sizing:border-box}body{margin:0;font-family:Arial,Helvetica,sans-serif;background:var(--bg);color:var(--text);line-height:1.7}.wrap{max-width:1120px;margin:0 auto;padding:0 20px}.nav{background:#fff;border-bottom:1px solid var(--line)}.nav-inner{min-height:64px;display:flex;justify-content:space-between;align-items:center;gap:16px}.nav a{color:#0f172a;font-weight:700;text-decoration:none;margin-right:16px}.logo{font-size:20px}.hero{padding:54px 0 22px}.eyebrow{font-weight:800;color:#0f766e;text-transform:uppercase;letter-spacing:.02em}.lede{font-size:19px;max-width:920px}.card{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:22px;margin:18px 0;box-shadow:0 1px 2px rgba(15,23,42,.04)}.trust{border-left:4px solid var(--warn)}h1{font-size:44px;line-height:1.08;margin:12px 0;color:#111827}h2{font-size:27px;margin:0 0 12px;color:#111827}h3{font-size:19px;margin:0 0 8px}p,li{color:var(--muted)}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:16px}.btn{display:inline-block;background:var(--accent);color:#fff;text-decoration:none;padding:11px 15px;border-radius:6px;font-weight:800;margin:5px 8px 5px 0}.btn.secondary{background:#e2e8f0;color:#0f172a}.table-scroll{overflow-x:auto}table{width:100%;border-collapse:collapse}th,td{text-align:left;border-bottom:1px solid #e6edf5;padding:12px;vertical-align:top}th{background:#f1f5f9;color:#334155}.toc a{color:#0f766e;text-decoration:none}details{border-top:1px solid #e6edf5;padding:12px 0}summary{cursor:pointer;font-weight:800;color:#334155}footer{margin-top:36px;background:#0f172a;color:#cbd5e1;padding:28px 0}footer p,footer a{color:#cbd5e1}@media(max-width:760px){h1{font-size:32px}.nav-inner{align-items:flex-start;flex-direction:column;padding:14px 0}}"""


def write_article(path: str, text: str, output: Path | None = None) -> Path:
    output = output or PUBLISHED_DIR
    folder = output / path.strip("/")
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / "index.html"
    target.write_text(text, encoding="utf-8")
    return target


def write_video_drafts(topic: dict[str, Any], url: str, title: str) -> Path:
    slug = str(topic["slug"])
    folder = VIDEO_OUTPUT / slug
    folder.mkdir(parents=True, exist_ok=True)
    script = video_script(topic, url, title)
    files = {
        "youtube_title.txt": f"{title} | Smile AI Review Hub",
        "youtube_description.txt": youtube_description(topic, url),
        "youtube_tags.txt": ", ".join(video_tags(topic)),
        "pinned_comment.txt": f"Read the full guide: {url}\nWhich tool should we compare next?",
        "shorts_script.txt": shorts_script(topic, url),
        "video_script.txt": script,
        "transcript.txt": script,
        "thumbnail_text.txt": thumbnail_text(topic),
        "scenes.json": json.dumps(video_scenes(topic), indent=2, ensure_ascii=False),
        "metadata.json": json.dumps(video_metadata(topic, url, title), indent=2, ensure_ascii=False),
    }
    for name, content in files.items():
        (folder / name).write_text(content, encoding="utf-8")
    return folder


def write_social_drafts(topic: dict[str, Any], url: str, title: str) -> Path:
    folder = SOCIAL_DRAFTS / date.today().isoformat() / str(topic["slug"])
    folder.mkdir(parents=True, exist_ok=True)
    platforms = {
        "facebook.md": facebook_draft(title, url),
        "linkedin.md": linkedin_draft(title, url),
        "quora.md": quora_draft(title, url),
        "reddit.md": reddit_draft(title, url),
        "x-twitter.md": x_draft(title, url),
        "threads.md": threads_draft(title, url),
        "medium.md": medium_draft(title, url),
        "devto.md": devto_draft(title, url),
        "product-hunt.md": product_hunt_draft(title, url),
        "pinterest.md": pinterest_draft(title, url),
    }
    if qiita_relevant(topic):
        platforms["qiita.md"] = qiita_draft(title, url)
    for name, content in platforms.items():
        (folder / name).write_text(content, encoding="utf-8")
    return folder


def run_build_and_sync() -> dict[str, Any]:
    result: dict[str, Any] = {}
    build = subprocess.run([sys.executable, "build_site.py"], cwd=ROOT, text=True, capture_output=True)
    result["build_returncode"] = build.returncode
    result["build_stdout_tail"] = build.stdout[-2000:]
    result["build_stderr_tail"] = build.stderr[-2000:]
    if build.returncode != 0:
        return result
    sync = subprocess.run([sys.executable, "scripts/sync_site_output_to_docs.py"], cwd=ROOT, text=True, capture_output=True)
    result["sync_returncode"] = sync.returncode
    result["sync_stdout_tail"] = sync.stdout[-1000:]
    result["sync_stderr_tail"] = sync.stderr[-1000:]
    return result


def submit_generated_urls(urls: list[str]) -> dict[str, Any]:
    try:
        from scripts.submit_indexnow import submit_indexnow

        result = submit_indexnow(urls, max_urls=len(urls))
        return {"submitted": len(urls), "result": result}
    except Exception as exc:
        return {"warning": f"IndexNow submission failed without stopping workflow: {type(exc).__name__}: {exc}"}


def write_daily_report(report: dict[str, Any]) -> None:
    stamp = date.today().isoformat()
    json_path = REPORT_DIR / f"{stamp}.json"
    md_path = REPORT_DIR / f"{stamp}.md"
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    lines = [
        f"# Daily AI Content Growth Report - {stamp}",
        "",
        "## Generated URLs",
    ]
    for page in report["generated_pages"]:
        lines.append(f"- {page['topic']}: {page['url']}")
    lines.extend(["", "## Manual Posting Order"])
    for item in report["manual_posting_order"]:
        lines.append(f"- {item}")
    lines.extend(["", "## Warnings"])
    lines.extend([f"- {item}" for item in report["warnings"]] or ["- None"])
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def append_tracking_row(page: GeneratedPage) -> None:
    TRACKING_CSV.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "publish_date",
        "url",
        "topic",
        "article_type",
        "source_keyword",
        "google_indexed_status",
        "bing_discovered_status",
        "bing_indexed_status",
        "yandex_index_status",
        "impressions",
        "clicks",
        "ctr",
        "average_position",
        "social_views",
        "youtube_views",
        "affiliate_clicks",
        "revenue",
        "notes",
    ]
    exists = TRACKING_CSV.exists()
    with TRACKING_CSV.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        if not exists:
            writer.writeheader()
        writer.writerow(
            {
                "publish_date": date.today().isoformat(),
                "url": page.url,
                "topic": page.topic,
                "article_type": page.content_type,
                "source_keyword": page.focus_keyword,
                "google_indexed_status": "pending",
                "bing_discovered_status": "pending",
                "bing_indexed_status": "pending",
                "yandex_index_status": "pending",
                "impressions": 0,
                "clicks": 0,
                "ctr": 0,
                "average_position": "",
                "social_views": 0,
                "youtube_views": 0,
                "affiliate_clicks": 0,
                "revenue": 0,
                "notes": "Generated by daily content growth pipeline; external posting is manual.",
            }
        )


def resolve_internal_links(topic: dict[str, Any]) -> list[tuple[str, str]]:
    suggestions = [str(item) for item in topic.get("suggested_internal_links", [])]
    defaults = ["/reviews/", "/comparisons/", "/categories/", "/best-website-builder-2026/", "/review/surfer-seo/"]
    candidates = suggestions + defaults
    result: list[tuple[str, str]] = []
    seen: set[str] = set()
    for href in candidates:
        clean = "/" + href.strip("/")
        if clean == "/":
            clean = "/"
        else:
            clean += "/"
        if clean in seen:
            continue
        target = SITE_OUTPUT / clean.strip("/") / "index.html" if clean != "/" else SITE_OUTPUT / "index.html"
        if target.exists():
            result.append((clean, label_from_path(clean)))
            seen.add(clean)
        if len(result) >= 8:
            break
    return result


def article_schema(title: str, description: str, url: str, topic: str, editorial: dict[str, Any] | None = None) -> dict[str, Any]:
    editorial = editorial or {}
    author_name = str(editorial.get("author_name") or "Nguyen Quoc Tuan")
    author_url = str(editorial.get("author_profile_url") or f"{BASE_URL}/about-author/")
    return {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": title,
        "description": description,
        "url": url,
        "datePublished": date.today().isoformat(),
        "dateModified": str(editorial.get("last_updated") or date.today().isoformat()),
        "author": {"@type": "Person", "name": author_name, "url": author_url},
        "publisher": {"@type": "Organization", "name": "MS Smile AI Review Hub", "url": BASE_URL},
        "about": topic,
    }


def faq_schema(items: list[str]) -> dict[str, Any]:
    return {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name": item,
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": "Use this article as a research starting point and verify pricing, terms, integrations, and limits on the official website before buying.",
                },
            }
            for item in items
        ],
    }


def breadcrumb_schema(title: str, url: str) -> dict[str, Any]:
    return {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Home", "item": BASE_URL + "/"},
            {"@type": "ListItem", "position": 2, "name": title, "item": url},
        ],
    }


def faq_html(items: list[str]) -> str:
    return "".join(
        f"<details><summary>{html.escape(item)}</summary><p>Verify current pricing, terms, limits, integrations, and official policies before buying or promoting this tool.</p></details>"
        for item in items
    )


def video_script(topic: dict[str, Any], url: str, title: str) -> str:
    topic_name = str(topic["topic"])
    return (
        f"Intro: In this Smile AI Review Hub video, we look at {topic_name}.\n\n"
        "Section one: what the topic means for buyers and creators.\n"
        "Section two: key features or comparison points to verify.\n"
        "Section three: pricing checks. Always verify current pricing on the official website.\n"
        "Section four: pros, cons, and alternatives.\n"
        f"Verdict: {title} is worth reviewing if it matches your workflow and budget.\n\n"
        f"Read the full guide on Smile AI Review Hub: {url}\n"
    )


def shorts_script(topic: dict[str, Any], url: str) -> str:
    return (
        f"Hook: Should you care about {topic['topic']} in 2026?\n"
        "Point one: check workflow fit before pricing.\n"
        "Point two: compare alternatives before buying.\n"
        "Point three: verify current terms on the official site.\n"
        f"CTA: Read the full guide at {url}\n"
    )


def youtube_description(topic: dict[str, Any], url: str) -> str:
    return (
        f"In this video, Smile AI Review Hub covers {topic['topic']} with buyer-focused notes on features, pricing checks, alternatives, and practical fit.\n\n"
        f"Read the full article:\n{url}\n\n"
        "Website:\nhttps://smileaireviewhub.com\n\n"
        "Note: pricing and product details can change. Verify current details on the official website."
    )


def video_tags(topic: dict[str, Any]) -> list[str]:
    words = [word for word in re.split(r"[^a-zA-Z0-9]+", str(topic["topic"]).lower()) if len(word) > 2]
    return list(dict.fromkeys(words + ["ai tools", "saas", "software review", "smile ai review hub"]))[:15]


def video_scenes(topic: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {"section": "Hook", "visual": "Title card with software category", "voiceover": f"Why {topic['topic']} matters in 2026."},
        {"section": "Overview", "visual": "Article-style dashboard slide", "voiceover": "Explain the buyer problem and workflow context."},
        {"section": "Pricing", "visual": "Pricing checklist slide", "voiceover": "Verify current pricing and plan limits."},
        {"section": "Pros and Cons", "visual": "Two-column pros and cons slide", "voiceover": "Summarize strengths and risks."},
        {"section": "Verdict", "visual": "CTA slide with website", "voiceover": "Read the full guide on Smile AI Review Hub."},
    ]


def video_metadata(topic: dict[str, Any], url: str, title: str) -> dict[str, Any]:
    return {
        "title": f"{title} | Smile AI Review Hub",
        "description": youtube_description(topic, url),
        "tags": video_tags(topic),
        "article_url": url,
        "manual_upload_only": True,
        "auto_youtube_upload": False,
    }


def page_to_dict(page: GeneratedPage) -> dict[str, Any]:
    return {
        "topic": page.topic,
        "slug": page.slug,
        "url": page.url,
        "article_file": str(page.article_file),
        "video_folder": str(page.video_folder),
        "social_folder": str(page.social_folder),
        "content_type": page.content_type,
        "focus_keyword": page.focus_keyword,
        "title": page.title,
        "description": page.description,
        "research": page.research,
        "planning": page.planning,
        "review": page.review,
        "human_approval": page.human_approval,
        "publish_gate": page.publish_gate,
        "warnings": page.warnings,
    }


def manual_posting_order(pages: list[GeneratedPage]) -> list[str]:
    order: list[str] = []
    for page in pages:
        order.append(f"{page.topic}: publish article first, upload YouTube manually, then post LinkedIn/Facebook/X drafts.")
    return order


def seo_title(topic: str) -> str:
    base = topic.strip()
    if "2026" not in base:
        base = f"{base} 2026"
    suffix = ": Pricing, Pros, Cons"
    title = base if len(base) <= 56 else base[:56].rstrip()
    if len(title + suffix) <= 60:
        return title + suffix
    return title


def meta_description(topic: str) -> str:
    text = f"Independent {topic} guide with pricing checks, pros, cons, alternatives, FAQs, and buyer-focused workflow advice."
    return text[:154].rstrip(". ,") + "."


def focus_keyword(topic: str) -> str:
    return re.sub(r"\s+", " ", topic.lower().replace("2026", "")).strip()


def faq_questions(topic: str) -> list[str]:
    return [
        f"What is {topic} best for?",
        f"How should I verify {topic} pricing?",
        f"What are the main alternatives to {topic}?",
        f"Is {topic} suitable for small teams?",
        f"What should I check before buying {topic}?",
        f"Can creators use {topic} for affiliate content?",
    ]


def fact_warnings(topic: str) -> list[str]:
    return [
        f"{topic}: pricing, trial terms, plan limits, and affiliate terms need manual verification before promotion.",
    ]


def thumbnail_text(topic: dict[str, Any]) -> str:
    words = str(topic["topic"]).replace("Review 2026", "").replace("2026", "").strip()
    return f"{words}\nWorth It?"


def facebook_draft(title: str, url: str) -> str:
    return f"{title}\n\nI published a buyer-focused breakdown with pricing checks, pros, cons, and alternatives.\n\nRead it here: {url}\n\n#AITools #SaaS #SoftwareReview\n"


def linkedin_draft(title: str, url: str) -> str:
    return f"New research note: {title}\n\nThe article focuses on workflow fit, pricing verification, alternatives, and buyer risk rather than vendor claims.\n\nFull guide: {url}\n"


def quora_draft(title: str, url: str) -> str:
    return f"Question angle: Is {title} worth considering?\n\nShort answer: it depends on workflow fit, pricing limits, and alternatives. I wrote a full research-style guide here: {url}\n"


def reddit_draft(title: str, url: str) -> str:
    return f"Manual draft only. Suggested post title: {title}\n\nI compared the practical buyer checks: pricing, pros, cons, alternatives, and when the topic is not a fit.\n\nLink: {url}\n"


def x_draft(title: str, url: str) -> str:
    return f"{title}\n\nPricing checks, pros/cons, alternatives, and buyer-fit notes.\n\n{url}\n\n#AI #SaaS #Software"


def threads_draft(title: str, url: str) -> str:
    return f"New guide: {title}\n\nUseful if you are comparing tools and want a practical checklist before buying.\n\n{url}"


def medium_draft(title: str, url: str) -> str:
    return f"# {title}\n\nThis is a manual repost draft. Summarize the buyer checklist, pricing verification steps, alternatives, and link back to the canonical article:\n\n{url}\n"


def devto_draft(title: str, url: str) -> str:
    return f"# {title}\n\nManual DEV.to draft. Keep the technical or workflow angle practical, explain what to verify before buying, and link back to the canonical article:\n\n{url}\n"


def product_hunt_draft(title: str, url: str) -> str:
    return f"Product Hunt discussion draft for {title}\n\nFocus on the buyer problem, what makes the shortlist useful, and where readers should verify pricing or limits before choosing a tool.\n\nCanonical article: {url}\n"


def qiita_draft(title: str, url: str) -> str:
    return f"# {title}\n\nQiita note draft. Explain the workflow, setup questions, and official verification steps for technical readers, then point back to the canonical article.\n\n{url}\n"


def pinterest_draft(title: str, url: str) -> str:
    return f"Pin title: {title}\n\nPin description: Compare pricing, pros, cons, alternatives, and buyer fit. Read the full guide: {url}\n"


def label_from_path(path: str) -> str:
    if path == "/":
        return "Smile AI Review Hub"
    return path.strip("/").replace("-", " ").replace("/", " / ").title()


def priority_from_score(score: float) -> str:
    if score >= 70:
        return "high"
    if score >= 55:
        return "medium"
    return "low"


def business_value(affiliate: int, cpc: int, evergreen: int) -> str:
    score = affiliate * 0.45 + cpc * 0.35 + evergreen * 0.2
    if score >= 70:
        return "high"
    if score >= 45:
        return "medium"
    return "low"


def default_article_angle(topic: str, content_type: str) -> str:
    return f"This {content_type} explains {topic} from a practical buyer perspective."


def default_video_angle(topic: str, content_type: str) -> str:
    return f"Use a clear {content_type} video structure: hook, overview, pricing checks, alternatives, and verdict."


def default_internal_links(topic: str, content_type: str) -> list[str]:
    lower = topic.lower()
    links = ["/reviews/", "/comparisons/", "/categories/"]
    if "seo" in lower:
        links.extend(["/review/surfer-seo/", "/category/seo-tools/"])
    if "website" in lower or "builder" in lower:
        links.extend(["/best-website-builder-2026/", "/category/website-builder-tools/"])
    if "automation" in lower or "zapier" in lower:
        links.extend(["/zapier-pricing/", "/category/automation-tools/"])
    if content_type == "comparison":
        links.append("/comparisons/")
    return links


def is_near_duplicate(left: str, right: str) -> bool:
    a = set(left.split("-"))
    b = set(right.split("-"))
    if not a or not b:
        return False
    return len(a & b) / len(a | b) >= 0.78


def truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}
