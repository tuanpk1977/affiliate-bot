from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from config import settings
from modules.content_growth_pipeline import (
    BASE_URL,
    build_editorial_metadata,
    build_publish_readiness_md,
    build_review_summary,
    fact_warnings,
    featured_image_prompt,
    meta_description,
    render_article,
    render_article_markdown,
    resolve_internal_links,
    seo_title,
)
from modules.content_review import ContentReviewEngine
from modules.human_approval import HumanApprovalWorkflow
from modules.publish_gate import PublishGate
from modules.research_intelligence import ResearchPackage


WRITER_METADATA = {
    "provider": "codex",
    "mode": "interactive_repository_writer",
    "api_call_used": False,
    "openai_api_used": False,
    "heuristic_fallback_used": False,
}


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write_json(path: Path, payload: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def _unique_source_domains(rows: list[dict[str, Any]]) -> list[str]:
    domains: list[str] = []
    seen: set[str] = set()
    for row in rows:
        url = str(row.get("source_url") or row.get("url") or "").strip()
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            continue
        domain = parsed.netloc.lower().removeprefix("www.")
        if domain in seen:
            continue
        seen.add(domain)
        domains.append(domain)
    return domains


class CodexDailyArticleWriter:
    """Repository-local writer used by Codex, not by any external LLM API provider."""

    def __init__(
        self,
        *,
        root: Path | None = None,
        data_dir: Path | None = None,
        site_output_dir: Path | None = None,
        minimum_sources: int = 2,
    ) -> None:
        self.root = root or settings.base_dir
        self.data_dir = data_dir or settings.data_dir
        self.site_output_dir = site_output_dir or settings.site_output_dir
        self.queue_root = self.data_dir / "editorial_queue"
        self.review_root = self.site_output_dir / "review"
        self.upload_root = self.root / "upload"
        self.drafts_root = self.data_dir / "production_article_drafts"
        self.minimum_sources = max(1, int(minimum_sources))
        self.config = _read_json(self.root / "config" / "editorial_system.json", {}) or dict(getattr(settings, "editorial_config", {}) or {})

    def write_daily_articles(self, *, batch_date: str, count: int = 10, depth: str = "deep", dry_run: bool = False) -> dict[str, Any]:
        payload = self._load_queue(batch_date)
        topics = list(payload.get("topics") or [])
        selected, held = self._select_topics(topics, count=count)
        written: list[dict[str, Any]] = []
        if not dry_run:
            for item in selected:
                written.append(self._write_one(item, batch_date=batch_date, depth=depth))
            self._update_topic_payload(payload, written=written, held=held)
            _write_json(self.queue_root / batch_date / "topics.json", payload)
            self._refresh_dashboards(batch_date)
        return {
            "codex_writer_mode": True,
            "dry_run": dry_run,
            "date": batch_date,
            "requested_count": count,
            "topics_available": len(topics),
            "selected": len(selected),
            "articles_written": 0 if dry_run else len(written),
            "dashboard_items_created": 0 if dry_run else len(written),
            "approved": 0,
            "published": 0,
            "openai_writer_calls": 0,
            "github_pushes": 0,
            "deploy_runs": 0,
            "index_runs": 0,
            "writer": dict(WRITER_METADATA),
            "selected_topics": [self._topic_summary(item) for item in selected],
            "held_topics": held,
            "written": written,
            "would_create": self._would_create(batch_date, selected),
            "final_decision": "PASS" if len(selected) >= count else "FAIL",
        }

    def _load_queue(self, batch_date: str) -> dict[str, Any]:
        path = self.queue_root / batch_date / "topics.json"
        if not path.exists():
            raise FileNotFoundError(f"Topic queue not found: {path}")
        payload = _read_json(path, {})
        if not isinstance(payload, dict):
            raise ValueError(f"Invalid topic queue: {path}")
        return payload

    def _select_topics(self, topics: list[dict[str, Any]], *, count: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        selected: list[dict[str, Any]] = []
        held: list[dict[str, Any]] = []
        seen_slugs: set[str] = set()
        publish_queue = _read_json(self.data_dir / "publish_queue.json", [])
        published_slugs = {
            str(row.get("slug") or "")
            for row in publish_queue
            if str(row.get("status") or "") in {"published", "published_local"}
        }
        for item in topics:
            slug = str(item.get("slug") or "").strip()
            if not slug:
                held.append({"slug": "", "reason": "missing slug"})
                continue
            if slug in seen_slugs:
                held.append({"slug": slug, "reason": "duplicate in candidate set"})
                continue
            if slug in published_slugs:
                held.append({"slug": slug, "reason": "already published"})
                continue
            package = self._load_research_package(slug)
            if package is None:
                held.append({"slug": slug, "reason": "missing research package"})
                continue
            source_rows = self._source_rows(package)
            domains = _unique_source_domains(source_rows)
            if len(domains) < self.minimum_sources:
                held.append({"slug": slug, "reason": f"{len(domains)} independent usable sources below {self.minimum_sources}"})
                continue
            selected.append(item)
            seen_slugs.add(slug)
            if len(selected) >= count:
                break
        return selected, held

    def _write_one(self, item: dict[str, Any], *, batch_date: str, depth: str) -> dict[str, Any]:
        slug = str(item.get("slug") or "")
        package = self._load_research_package(slug)
        if package is None:
            raise FileNotFoundError(f"Research package not found for {slug}")
        topic = self._build_topic(item, package, depth=depth)
        title = seo_title(str(topic.get("topic") or slug.replace("-", " ")))
        description = meta_description(str(topic.get("topic") or slug.replace("-", " ")))
        path = f"/{slug}/"
        url = BASE_URL + path
        warnings = fact_warnings(str(topic.get("topic") or slug))
        links = resolve_internal_links(topic)
        article_html = render_article(topic, title, description, path, links, warnings)
        article_markdown = render_article_markdown(topic, title, description, url, links, warnings)

        review_engine = ContentReviewEngine(data_dir=self.data_dir, config=self.config.get("content_review", {}))
        review = review_engine.review_content(
            topic=topic,
            html=article_html,
            title=title,
            description=description,
            url=url,
            internal_links=links,
            warnings=warnings,
            research=topic["research"],
            planning=topic["planning"],
        )
        if str(review.get("rewritten_html") or "").strip():
            article_html = str(review["rewritten_html"])
        human_approval = HumanApprovalWorkflow(data_dir=self.data_dir, config=self.config.get("human_approval", {})).sync_review(review)
        publish_gate = PublishGate(data_dir=self.data_dir, site_output_dir=self.site_output_dir, config=self.config.get("publish_gate", {})).evaluate(
            topic=topic,
            title=title,
            description=description,
            url=url,
            html=article_html,
            research=topic["research"],
            review=review,
            human_approval=human_approval,
            internal_links=links,
        )
        draft_dir = self.drafts_root / slug
        draft_dir.mkdir(parents=True, exist_ok=True)
        article_file = draft_dir / "index.html"
        markdown_file = draft_dir / "article.md"
        article_file.write_text(article_html, encoding="utf-8")
        markdown_file.write_text(article_markdown, encoding="utf-8")
        featured_prompt = featured_image_prompt(topic, topic["research"], topic["planning"])
        (draft_dir / "featured_image_prompt.txt").write_text(featured_prompt + "\n", encoding="utf-8")
        (draft_dir / "review_summary.md").write_text(build_review_summary(review, human_approval, publish_gate, package), encoding="utf-8")
        publish_readiness = {
            "slug": slug,
            "title": title,
            "description": description,
            "url": url,
            "review_status": review.get("status", ""),
            "human_approval_status": human_approval.get("status", ""),
            "publish_gate_status": publish_gate.get("status", ""),
            "publish_failures": publish_gate.get("failures", []),
            "research_quality_score": package.quality.get("overall_score", 0),
            "verified_source_score": package.quality.get("total_verified_source_score", 0),
            "word_count": review.get("word_count", 0),
            "article_markdown": str(markdown_file),
            "article_html": str(article_file),
        }
        _write_json(draft_dir / "publish_readiness_report.json", publish_readiness)
        (draft_dir / "publish_readiness_report.md").write_text(build_publish_readiness_md(publish_readiness), encoding="utf-8")
        _write_json(
            draft_dir / "metadata.json",
            {
                "slug": slug,
                "title": title,
                "description": description,
                "url": url,
                "writer": dict(WRITER_METADATA),
                "root_topic_id": str(item.get("root_topic_id") or ""),
                "root_title": str(item.get("root_title") or item.get("parent_keyword") or ""),
                "daily_angle": str(item.get("daily_angle") or ""),
                "weekly_article_history": list(item.get("weekly_article_history") or []),
                "featured_image_prompt": featured_prompt,
                "editorial": topic["editorial"],
                "review": review,
                "human_approval": human_approval,
                "publish_gate": publish_gate,
                "research_quality_gate": topic["research"].get("quality_gate", {}),
            },
        )
        _write_json(
            draft_dir / "codex_writer_report.json",
            {
                "generated_at": datetime.now(UTC).isoformat(),
                "writer": dict(WRITER_METADATA),
                "source_count": len(_unique_source_domains(self._source_rows(package))),
                "source_urls": [str(row.get("source_url") or row.get("url") or "") for row in self._source_rows(package)],
                "human_approval_required": True,
                "published": False,
            },
        )
        return {
            "slug": slug,
            "status": "drafted",
            "draft_dir": str(draft_dir),
            "metadata_file": str(draft_dir / "metadata.json"),
            "review_status": str(review.get("status") or ""),
            "human_approval_status": str(human_approval.get("status") or ""),
            "publish_gate_status": str(publish_gate.get("status") or ""),
            "source_count": len(_unique_source_domains(self._source_rows(package))),
        }

    def _build_topic(self, item: dict[str, Any], package: ResearchPackage, *, depth: str) -> dict[str, Any]:
        research = {
            "keyword": package.keyword,
            "slug": package.slug,
            "package_dir": package.package_dir,
            "generated_at": package.generated_at,
            "keyword_intelligence": package.keyword_intelligence,
            "outline": package.outline,
            "faq": package.faq,
            "entities": package.entities,
            "competitors": package.competitors,
            "sources": package.sources,
            "writing_plan": package.writing_plan,
            "quality": package.quality,
            "cache_hits": package.cache_hits,
            "quality_gate": item.get("research_quality_gate") if isinstance(item.get("research_quality_gate"), dict) else {},
        }
        planning = {
            "keyword": package.keyword,
            "intent": str(item.get("search_intent") or package.keyword_summary.get("intent") or ""),
            "article_type": str(item.get("content_type") or package.keyword_summary.get("article_type") or "review"),
            "topic_cluster": package.keyword_intelligence.get("cluster", {}),
            "coverage_score": package.quality.get("coverage", 0),
            "outline_sections": package.outline.get("seo_outline", []),
            "reasoning": package.outline.get("article_structure", []) or package.outline.get("reasoning", []),
            "related_keywords": package.keyword_intelligence.get("secondary_keywords", []) or item.get("related_keywords", []),
            "recommended_cta": package.outline.get("recommended_cta", "Compare official pricing"),
            "confidence": package.writing_plan.get("confidence", 0),
            "research_quality_score": package.quality.get("overall_score", 0),
            "depth": depth,
        }
        return {
            "topic": str(item.get("keyword") or item.get("topic") or package.keyword),
            "slug": package.slug,
            "title": str(item.get("keyword") or package.keyword),
            "content_type": str(item.get("content_type") or planning["article_type"]),
            "search_intent": planning["intent"],
            "related_keywords": list(item.get("related_keywords") or []),
            "suggested_internal_links": list(item.get("suggested_internal_links") or []),
            "suggested_article_angle": str(item.get("suggested_article_angle") or ""),
            "root_topic_id": str(item.get("root_topic_id") or ""),
            "root_title": str(item.get("root_title") or item.get("parent_keyword") or ""),
            "daily_angle": str(item.get("daily_angle") or ""),
            "weekly_article_history": list(item.get("weekly_article_history") or []),
            "research": research,
            "planning": planning,
            "editorial": build_editorial_metadata(reviewed_by="Human review pending"),
            "writer": dict(WRITER_METADATA),
        }

    def _refresh_dashboards(self, batch_date: str) -> None:
        from modules.daily_editorial_workflow import DailyEditorialWorkflow

        workflow = DailyEditorialWorkflow(root=self.root, data_dir=self.data_dir, site_output_dir=self.site_output_dir)
        for path in (self.drafts_root).glob("*/index.html"):
            slug = path.parent.name
            queue = _read_json(self.queue_root / batch_date / "topics.json", {})
            if any(str(item.get("slug") or "") == slug for item in list(queue.get("topics") or [])):
                workflow._copy_review_preview(slug=slug, batch_date=batch_date)
        workflow.build_review_dashboard(batch_date=batch_date)
        workflow._sync_upload_batch(batch_date=batch_date)
        workflow._build_upload_master_dashboard()

    def _update_topic_payload(self, payload: dict[str, Any], *, written: list[dict[str, Any]], held: list[dict[str, Any]]) -> None:
        by_slug = {row["slug"]: row for row in written}
        held_by_slug = {row["slug"]: row for row in held}
        for item in payload.get("topics", []):
            slug = str(item.get("slug") or "")
            if slug in by_slug:
                result = by_slug[slug]
                item.update(
                    {
                        "status": "drafted",
                        "draft_dir": result["draft_dir"],
                        "draft_file": str(Path(result["draft_dir"]) / "index.html"),
                        "review_preview": str(self.review_root / str(payload.get("date") or "") / slug / "index.html"),
                        "metadata_file": result["metadata_file"],
                        "review_status": result["review_status"],
                        "human_approval_status": result["human_approval_status"],
                        "publish_gate_status": result["publish_gate_status"],
                        "writer": dict(WRITER_METADATA),
                        "error": "",
                    }
                )
            elif slug in held_by_slug:
                item.setdefault("status", "held_for_codex_writer")
                item["codex_writer_hold_reason"] = held_by_slug[slug]["reason"]
        payload["codex_writer"] = {
            "last_run_at": datetime.now(UTC).isoformat(),
            "writer": dict(WRITER_METADATA),
            "written": len(written),
            "held": len(held),
        }

    def _load_research_package(self, slug: str) -> ResearchPackage | None:
        payload = _read_json(self.data_dir / "research" / slug / "package.json", None)
        if not isinstance(payload, dict):
            return None
        try:
            return ResearchPackage(**payload)
        except TypeError:
            return None

    @staticmethod
    def _source_rows(package: ResearchPackage) -> list[dict[str, Any]]:
        sources = package.sources if isinstance(package.sources, dict) else {}
        return [row for row in list(sources.get("verified_sources") or []) if isinstance(row, dict)]

    @staticmethod
    def _topic_summary(item: dict[str, Any]) -> dict[str, Any]:
        return {
            "slug": str(item.get("slug") or ""),
            "topic": str(item.get("keyword") or item.get("topic") or ""),
            "search_intent": str(item.get("search_intent") or ""),
        }

    def _would_create(self, batch_date: str, selected: list[dict[str, Any]]) -> list[str]:
        paths: list[str] = []
        for item in selected:
            slug = str(item.get("slug") or "")
            paths.extend(
                [
                    f"data/production_article_drafts/{slug}/index.html",
                    f"data/production_article_drafts/{slug}/article.md",
                    f"data/production_article_drafts/{slug}/metadata.json",
                    f"site_output/review/{batch_date}/{slug}/index.html",
                    f"upload/{batch_date}/drafts/{slug}/index.html",
                    f"upload/{batch_date}/review/{slug}/index.html",
                ]
            )
        paths.extend(
            [
                "data/content_review_queue.json",
                "data/human_approval_queue.json",
                "data/publish_queue.json",
                f"data/editorial_queue/{batch_date}/topics.json",
                f"site_output/review/{batch_date}/index.html",
                f"upload/{batch_date}/review_dashboard.html",
            ]
        )
        return sorted(set(paths))


def run_codex_daily_writer(
    *,
    batch_date: str,
    count: int = 10,
    depth: str = "deep",
    dry_run: bool = False,
    root: Path | None = None,
    data_dir: Path | None = None,
    site_output_dir: Path | None = None,
) -> dict[str, Any]:
    writer = CodexDailyArticleWriter(root=root, data_dir=data_dir, site_output_dir=site_output_dir)
    return writer.write_daily_articles(batch_date=batch_date, count=count, depth=depth, dry_run=dry_run)
