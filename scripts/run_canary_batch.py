from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import time
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import settings
from modules.content_review import ContentReviewEngine
from modules.editorial_quality import EditorialBrain
from modules.llm_provider import LLMSectionRewriteProvider, build_llm_service, render_writer_output
from modules.research_intelligence import ResearchIntelligencePlatform, ResearchPackage


CANARY_TOPICS: list[dict[str, Any]] = [
    {
        "topic": "Microsoft AutoGen Review 2026",
        "slug": "microsoft-autogen-review-2026",
        "primary_keyword": "microsoft autogen review",
        "search_intent": "commercial investigation",
        "content_type": "review",
        "business_value": 78,
        "source_readiness_score": 92,
        "review_risk": 24,
        "validated_source_urls": [
            "https://microsoft.github.io/autogen/",
            "https://github.com/microsoft/autogen",
        ],
        "related_keywords": ["multi agent framework", "autogen alternatives", "python agent orchestration"],
    },
    {
        "topic": "Mastra AI Review 2026",
        "slug": "mastra-ai-review-2026",
        "primary_keyword": "mastra ai review",
        "search_intent": "commercial investigation",
        "content_type": "review",
        "business_value": 76,
        "source_readiness_score": 90,
        "review_risk": 25,
        "validated_source_urls": [
            "https://mastra.ai/",
            "https://github.com/mastra-ai/mastra",
        ],
        "related_keywords": ["typescript ai agents", "agent workflow framework", "mastra alternatives"],
    },
    {
        "topic": "n8n AI Agents Review 2026",
        "slug": "n8n-ai-agents-review-2026",
        "primary_keyword": "n8n ai agents review",
        "search_intent": "commercial investigation",
        "content_type": "review",
        "business_value": 82,
        "source_readiness_score": 91,
        "review_risk": 28,
        "validated_source_urls": [
            "https://docs.n8n.io/integrations/builtin/cluster-nodes/root-nodes/n8n-nodes-langchain.agent/",
            "https://github.com/n8n-io/n8n",
        ],
        "related_keywords": ["workflow automation agents", "n8n langchain agent", "n8n ai workflow"],
    },
    {
        "topic": "OpenAI Agents SDK Review 2026",
        "slug": "openai-agents-sdk-review-2026",
        "primary_keyword": "openai agents sdk review",
        "search_intent": "commercial investigation",
        "content_type": "review",
        "business_value": 80,
        "source_readiness_score": 93,
        "review_risk": 27,
        "validated_source_urls": [
            "https://openai.github.io/openai-agents-python/",
            "https://github.com/openai/openai-agents-python",
        ],
        "related_keywords": ["python agents sdk", "agent orchestration sdk", "openai agent framework"],
    },
    {
        "topic": "LangGraph Review 2026",
        "slug": "langgraph-review-2026",
        "primary_keyword": "langgraph review",
        "search_intent": "commercial investigation",
        "content_type": "review",
        "business_value": 79,
        "source_readiness_score": 89,
        "review_risk": 26,
        "validated_source_urls": [
            "https://langchain-ai.github.io/langgraph/",
            "https://github.com/langchain-ai/langgraph",
        ],
        "related_keywords": ["agent graph framework", "langgraph alternatives", "stateful ai agents"],
    },
]

SAFETY = {
    "publish": False,
    "deploy": False,
    "index": False,
    "auto_approve": False,
    "human_approval_required": True,
    "draft_only": True,
    "dry_run": False,
}

HIGH_RISK_TERMS = (
    "medical",
    "health",
    "healthcare",
    "legal",
    "law",
    "financial",
    "finance",
    "stock",
    "crypto",
    "tax",
    "insurance",
)


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(value or "").lower()).strip("-") or "topic"


def _write_json(path: Path, payload: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def _write_text(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _domain(url: str) -> str:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    return host[4:] if host.startswith("www.") else host


def _provider_status(config: dict[str, Any], provider_info: dict[str, Any] | None = None) -> dict[str, Any]:
    provider_info = provider_info or {}
    provider = provider_info.get("provider") or "none"
    model = provider_info.get("model") or ""
    available = bool(provider_info.get("provider_available", False))
    fallback_allowed = bool(provider_info.get("allow_heuristic_fallback", False))
    heuristic = not available
    return {
        "research_provider": "ResearchIntelligencePlatform(local)",
        "provider": provider,
        "model": model,
        "writer_provider": provider if available else "heuristic_fallback",
        "reviewer_provider": "ContentReviewEngine(local_ai_review_v2)",
        "rewrite_provider": provider if available else "heuristic_fallback",
        "judge_provider": "EditorialJudge(local)",
        "credentials_detected": bool(provider_info.get("credentials_detected", False)),
        "missing_environment": provider_info.get("missing_environment", []),
        "provider_available": available,
        "allow_heuristic_fallback": fallback_allowed,
        "heuristic_fallback_used": heuristic,
        "provider_mode": provider if available else "heuristic_fallback",
        "telemetry": provider_info.get("telemetry", {}),
    }


def _existing_slug_paths(slug: str) -> list[str]:
    paths = [
        settings.base_dir / "docs" / slug / "index.html",
        settings.base_dir / "site_output" / slug / "index.html",
        settings.base_dir / "data" / "published_static_pages" / slug / "index.html",
        settings.base_dir / "data" / "production_article_drafts" / f"{slug}.md",
        settings.base_dir / "data" / "production_article_drafts" / slug / "index.html",
    ]
    return [str(path) for path in paths if path.exists()]


def _select_topics(count: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    candidates: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for topic in CANARY_TOPICS:
        slug = str(topic.get("slug") or _slug(str(topic.get("topic") or "")))
        urls = [str(url) for url in topic.get("validated_source_urls", []) if str(url).startswith(("http://", "https://"))]
        domains = {_domain(url) for url in urls}
        reasons: list[str] = []
        if slug in seen:
            reasons.append("duplicate in canary list")
        if _existing_slug_paths(slug):
            reasons.append("existing production/draft slug collision")
        if any(term in str(topic.get("topic") or "").lower() for term in HIGH_RISK_TERMS):
            reasons.append("high-risk topic excluded from first canary")
        if len(urls) < 2 or len(domains) < 2:
            reasons.append("source readiness below two independent domains")
        seen.add(slug)
        if reasons:
            rejected.append({**topic, "slug": slug, "rejection_reasons": reasons})
            continue
        candidates.append(
            {
                **topic,
                "slug": slug,
                "source_urls": urls,
                "source_count": len(urls),
                "duplicate_collision": False,
                "cannibalization_risk": False,
            }
        )
    portfolio = EditorialBrain(settings.editorial_config.get("editorial_brain", {})).select_portfolio(candidates, target=count, minimum_review_ready=count)
    selected = [row for row in portfolio["selected"] if row.get("classification") in {"FAST_TRACK", "STANDARD"}][:count]
    selected_ids = {row["slug"] for row in selected}
    for row in candidates:
        if row["slug"] not in selected_ids:
            rejected.append({**row, "rejection_reasons": ["not selected for first canary portfolio"]})
    return selected, rejected


def _package_to_dict(package: ResearchPackage) -> dict[str, Any]:
    return asdict(package)


def _outline(package: ResearchPackage) -> list[str]:
    headings = package.outline.get("heading_hierarchy") if isinstance(package.outline, dict) else []
    result = [str(row.get("heading") or "") for row in headings if isinstance(row, dict) and str(row.get("heading") or "").strip()]
    return result[:6] or ["Overview", "Best-fit use cases", "Implementation notes", "Risks to verify", "Verdict"]


def _faq_pairs(topic: dict[str, Any]) -> list[tuple[str, str]]:
    title = str(topic.get("topic") or "")
    return [
        (f"What is {title} best for?", f"{title} is best treated as a candidate for teams that need to compare agent workflow fit, implementation effort, and source-backed product evidence before adoption."),
        (f"Should small teams test {title} before buying?", f"Yes. A small team should run one representative workflow, verify current documentation, and compare the operational effort against at least one alternative."),
        (f"What should editors verify before approving this {title} draft?", "Editors should verify pricing, feature limits, integration claims, and whether the cited official sources still match the article angle."),
    ]


def _render_article(topic: dict[str, Any], package: ResearchPackage) -> tuple[str, str, list[dict[str, Any]]]:
    title = str(topic.get("topic") or package.keyword)
    slug = str(topic.get("slug") or package.slug)
    sources = [str(url) for url in topic.get("validated_source_urls") or topic.get("source_urls") or []]
    source_links = "\n".join(f'<li><a href="{html.escape(url)}">{html.escape(_domain(url))}</a></li>' for url in sources)
    outline_items = "\n".join(f"<li>{html.escape(item)}</li>" for item in _outline(package))
    faq = _faq_pairs(topic)
    faq_html = "\n".join(f"<details><summary>{html.escape(q)}</summary><p>{html.escape(a)}</p></details>" for q, a in faq)
    faq_schema = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}}
            for q, a in faq
        ],
    }
    article_schema = {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": title,
        "author": {"@type": "Person", "name": "Smile AI Review Hub Editorial Team"},
        "mainEntityOfPage": f"https://smileaireviewhub.com/{slug}/",
    }
    claim_mapping = [
        {
            "claim": f"{title} should be evaluated against official documentation and repository evidence before editorial approval.",
            "source_url": sources[0],
            "importance": "critical",
        },
        {
            "claim": f"{title} has implementation considerations that editors should verify against independent source domains.",
            "source_url": sources[1],
            "importance": "important",
        },
    ]
    sections = [
        f"<section id='overview'><h2>Overview</h2><p>{html.escape(title)} is included in this canary because it has independent official source coverage, low compliance risk, and clear buyer-research intent. This draft is for controlled editorial review only and is not approved for publishing.</p></section>",
        f"<section id='fit'><h2>Best-fit workflow</h2><p>Teams should compare {html.escape(title)} by running one representative workflow, checking integration effort, and documenting the review time required before adoption.</p></section>",
        f"<section id='sources'><h2>Source-backed checks</h2><p>The canary draft uses at least two independent source domains. Editors still need to verify pricing, release notes, feature limits, and support policies before manual approval.</p><ul>{source_links}</ul></section>",
        f"<section id='outline'><h2>Editorial outline</h2><ul>{outline_items}</ul></section>",
        f"<section id='faq'><h2>FAQ</h2>{faq_html}</section>",
        "<section id='verdict'><h2>Canary verdict</h2><p>This item may enter canary human review when no hard blockers remain, but heuristic fallback output must not be treated as production-ready content.</p></section>",
    ]
    body = "\n".join(sections)
    html_doc = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{html.escape(title)}</title>
  <meta name="description" content="{html.escape(title)} canary review draft with source-backed editorial checks.">
  <link rel="canonical" href="https://smileaireviewhub.com/{html.escape(slug)}/">
  <script type="application/ld+json">{json.dumps(article_schema, ensure_ascii=False)}</script>
  <script type="application/ld+json">{json.dumps(faq_schema, ensure_ascii=False)}</script>
</head>
<body>
<article>
<h1>{html.escape(title)}</h1>
<section id="affiliate-disclosure"><h2>Affiliate disclosure</h2><p>Some links may become affiliate links after manual approval. We may earn a commission at no extra cost to readers.</p></section>
{body}
</article>
</body>
</html>
"""
    md = f"# {title}\n\n" + "\n\n".join(re.sub(r"<[^>]+>", "", section).strip() for section in sections) + "\n"
    return html_doc, md, claim_mapping


def _validate_article(article: dict[str, Any], html_doc: str) -> dict[str, Any]:
    source_urls = article.get("source_urls", [])
    headings = re.findall(r"<h[1-6]\b[^>]*>(.*?)</h[1-6]>", html_doc, flags=re.I | re.S)
    normalized_headings = [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", heading)).strip().lower() for heading in headings]
    unsupported = [
        claim for claim in article.get("fact_verification_summary", {}).get("claims", [])
        if claim.get("importance") == "critical" and claim.get("support_status") == "unsupported"
    ]
    empty_sections = [
        match.group(1)
        for match in re.finditer(r"<section\b[^>]*id=['\"]([^'\"]+)['\"][^>]*>(.*?)</section>", html_doc, re.I | re.S)
        if not re.sub(r"<[^>]+>", "", match.group(2)).strip()
    ]
    checks = {
        "source_validation": bool(source_urls) and all(url in html_doc for url in source_urls),
        "fact_validation": not unsupported,
        "schema_validation": '"@type": "FAQPage"' in html_doc and '"@type": "Article"' in html_doc,
        "render_validation": "<html" in html_doc.lower() and "</html>" in html_doc.lower() and "<h1" in html_doc.lower(),
        "duplicate_validation": not article.get("duplicate_collision"),
        "no_empty_sections": not empty_sections,
        "no_duplicate_headings": len(normalized_headings) == len(set(normalized_headings)),
        "unsupported_critical_claims": len(unsupported),
    }
    checks["passed"] = all(value is True for key, value in checks.items() if key != "unsupported_critical_claims") and checks["unsupported_critical_claims"] == 0
    return checks


def run_canary_batch(*, count: int = 5, output_root: Path | None = None, batch_id: str | None = None, allow_heuristic_fallback: bool = True) -> dict[str, Any]:
    started = time.monotonic()
    batch_id = batch_id or datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    output_root = output_root or settings.base_dir / "artifacts" / "canary"
    batch_root = output_root / batch_id
    data_dir = batch_root / "data"
    site_output_dir = batch_root / "site_output"
    drafts_dir = batch_root / "drafts"
    llm_service, provider_info = build_llm_service(settings.editorial_config, allow_heuristic_fallback=allow_heuristic_fallback)
    provider_status = _provider_status(settings.editorial_config, provider_info)
    if llm_service is None and not allow_heuristic_fallback:
        report = {
            "canary_mode": True,
            "canary_batch_size": count,
            "batch_id": batch_id,
            "output_root": str(batch_root),
            "provider_status": provider_status,
            "safety": SAFETY,
            "selected": 0,
            "rejected": [],
            "research_completed": 0,
            "drafts_generated": 0,
            "rewrite_attempts": 0,
            "review_ready": 0,
            "canary_queue_items": 0,
            "production_review_ready": 0,
            "warning_only": 0,
            "blocked": 0,
            "held": 0,
            "failed": 0,
            "average_confidence": 0.0,
            "average_pipeline_seconds": 0.0,
            "estimated_total_cost": 0.0,
            "per_article": [],
            "failed_items": [],
            "quality_check": {
                "source_validation": False,
                "fact_validation": False,
                "schema_validation": False,
                "render_validation": False,
                "duplicate_validation": False,
            },
            "production_recommendation": {
                "ready_for_5_per_day": False,
                "ready_for_10_per_day": False,
                "reasons": ["production LLM provider is unavailable and heuristic fallback is disabled"],
                "required_fixes": ["configure OPENAI_API_KEY or another supported provider credential"],
            },
        }
        _write_json(batch_root / "canary_report.json", report)
        _write_text(batch_root / "canary_report.md", _format_markdown(report))
        return report
    selected, rejected = _select_topics(count)
    results: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    research_platform = ResearchIntelligencePlatform(data_dir=data_dir, site_output_dir=site_output_dir, config=settings.editorial_config)
    review_config = dict(settings.editorial_config.get("content_review", {}))
    review_config["require_human_approval"] = True
    rewrite_provider = LLMSectionRewriteProvider(llm_service) if llm_service is not None else None
    review_engine = ContentReviewEngine(data_dir=data_dir, config=review_config, rewrite_provider=rewrite_provider)

    for topic in selected:
        article_started = time.monotonic()
        slug = str(topic.get("slug") or "")
        try:
            package = research_platform.build_research_package(topic, force_refresh=True)
            gate = research_platform.evaluate_quality_gate(package, topic=topic, allow_override=False)
            if llm_service is not None:
                writer_payload = llm_service.write_article(topic=topic, research_package=_package_to_dict(package))
                html_doc, markdown, claim_mapping = render_writer_output(writer_payload, canonical_url=f"https://smileaireviewhub.com/{slug}/")
            else:
                html_doc, markdown, claim_mapping = _render_article(topic, package)
            review = review_engine.review_content(
                topic=topic,
                html=html_doc,
                title=str(topic.get("topic") or package.keyword),
                description=f"{topic.get('topic')} canary review draft.",
                url=f"https://smileaireviewhub.com/{slug}/",
                internal_links=[("/ai-tools/", "AI tools"), ("/ai-agent-tools/", "AI agent tools")],
                warnings=list(gate.warnings),
                research={**_package_to_dict(package), "quality_gate": asdict(gate)},
                planning={"keyword": topic.get("primary_keyword"), "coverage_score": package.quality.get("coverage", 0)},
            )
            final_html = str(review.get("rewritten_html") or html_doc)
            validation = _validate_article(
                {
                    "source_urls": topic.get("validated_source_urls", []),
                    "fact_verification_summary": review.get("fact_verification", {}),
                    "duplicate_collision": topic.get("duplicate_collision", False),
                },
                final_html,
            )
            article_dir = drafts_dir / slug
            html_path = _write_text(article_dir / "index.html", final_html)
            md_path = _write_text(article_dir / "draft.md", markdown)
            research_path = _write_json(article_dir / "research_package.json", _package_to_dict(package))
            review_path = _write_json(article_dir / "review.json", review)
            source_urls = [str(url) for url in topic.get("validated_source_urls", [])]
            status = "held"
            if review.get("hard_blockers"):
                status = "blocked"
            elif provider_status["heuristic_fallback_used"]:
                status = "held"
            else:
                status = "canary_review_ready"
            results.append(
                {
                    "article_id": slug,
                    "topic": topic.get("topic"),
                    "status": status,
                    "provider_mode": provider_status["provider_mode"],
                    "production_review_ready": False if provider_status["heuristic_fallback_used"] else status == "canary_review_ready",
                    "confidence": review.get("publishing_confidence", {}).get("score", 0),
                    "sources": len(source_urls),
                    "source_urls": source_urls,
                    "source_domains": sorted({_domain(url) for url in source_urls}),
                    "verified_claims": sum(1 for claim in review.get("fact_verification", {}).get("claims", []) if claim.get("support_status") == "supported"),
                    "unsupported_critical_claims": sum(1 for claim in review.get("fact_verification", {}).get("claims", []) if claim.get("importance") == "critical" and claim.get("support_status") == "unsupported"),
                    "warnings": list(review.get("warnings", [])),
                    "hard_blockers": list(review.get("hard_blockers", [])),
                    "publishing_confidence": review.get("publishing_confidence", {}),
                    "judge_decision": review.get("ai_judge", {}).get("decision"),
                    "rewrite_history": review.get("rewrite_history", []),
                    "internal_link_suggestions": review.get("internal_link_suggestions", []),
                    "entity_coverage": review.get("entity_coverage", {}),
                    "claim_source_mapping": claim_mapping,
                    "fact_verification_summary": review.get("fact_verification", {}),
                    "validation": validation,
                    "output_path": str(article_dir),
                    "html_path": str(html_path),
                    "markdown_path": str(md_path),
                    "research_path": str(research_path),
                    "review_path": str(review_path),
                    "pipeline_seconds": round(time.monotonic() - article_started, 4),
                }
            )
        except Exception as exc:
            failed.append({"article_id": slug, "topic": topic.get("topic"), "status": "failed", "error": f"{type(exc).__name__}: {exc}"})
            continue

    if llm_service is not None:
        provider_status["telemetry"] = llm_service.telemetry.as_dict()
        provider_status["heuristic_fallback_used"] = bool(llm_service.telemetry.fallback_used)

    review_queue = [
        row for row in results
        if row["status"] in {"canary_review_ready", "held"} and not row["hard_blockers"]
    ]
    _write_json(batch_root / "canary_human_review_queue.json", review_queue)
    elapsed = time.monotonic() - started
    confidence_scores = [float(row.get("confidence") or 0) for row in results]
    quality = {
        "source_validation": all(row["validation"]["source_validation"] for row in results) if results else False,
        "fact_validation": all(row["validation"]["fact_validation"] for row in results) if results else False,
        "schema_validation": all(row["validation"]["schema_validation"] for row in results) if results else False,
        "render_validation": all(row["validation"]["render_validation"] for row in results) if results else False,
        "duplicate_validation": all(row["validation"]["duplicate_validation"] for row in results) if results else False,
    }
    provider_failed = bool(failed) and llm_service is not None
    report = {
        "canary_mode": True,
        "canary_batch_size": count,
        "batch_id": batch_id,
        "output_root": str(batch_root),
        "provider_status": provider_status,
        "safety": SAFETY,
        "selected": len(selected),
        "rejected": rejected,
        "research_completed": len(results),
        "drafts_generated": len([row for row in results if Path(row["html_path"]).exists()]),
        "rewrite_attempts": sum(len(row["rewrite_history"]) for row in results),
        "review_ready": sum(1 for row in results if row["status"] == "canary_review_ready"),
        "canary_queue_items": len(review_queue),
        "production_review_ready": sum(1 for row in results if row["production_review_ready"]),
        "warning_only": sum(1 for row in results if row["warnings"] and not row["hard_blockers"]),
        "blocked": sum(1 for row in results if row["status"] == "blocked"),
        "held": sum(1 for row in results if row["status"] == "held"),
        "failed": len(failed),
        "average_confidence": round(sum(confidence_scores) / max(1, len(confidence_scores)), 2),
        "average_pipeline_seconds": round(elapsed / max(1, len(results)), 4),
        "estimated_total_cost": float(provider_status.get("telemetry", {}).get("estimated_cost", 0.0) or 0.0),
        "per_article": results,
        "failed_items": failed,
        "quality_check": quality,
        "production_recommendation": {
            "ready_for_5_per_day": False if provider_status["heuristic_fallback_used"] or provider_failed else len(results) == count and not failed,
            "ready_for_10_per_day": False,
            "reasons": [
                "writer provider is heuristic_fallback; canary verifies orchestration only",
                "manual editorial review is still required before any publish action",
            ] if provider_status["heuristic_fallback_used"] else (
                ["production LLM provider returned errors during writer generation", "no article was routed to production review-ready"]
                if provider_failed
                else ["complete a larger canary before moving to 10 per day"]
            ),
            "required_fixes": [
                "configure and test a production writer provider",
                "run another canary with production writer output before enabling production review-ready routing",
            ] if provider_status["heuristic_fallback_used"] else (
                ["fix provider credential/model/API access error and rerun canary with fallback disabled"]
                if provider_failed
                else ["review 5-per-day operating metrics before increasing volume"]
            ),
        },
    }
    _write_json(batch_root / "canary_report.json", report)
    _write_text(batch_root / "canary_report.md", _format_markdown(report))
    return report


def _format_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Canary Batch Report",
        "",
        f"- CANARY_MODE: {'YES' if report['canary_mode'] else 'NO'}",
        f"- CANARY_BATCH_SIZE: {report['canary_batch_size']}",
        f"- Output: {report['output_root']}",
        "",
        "## Results",
        f"- Selected: {report['selected']}",
        f"- Drafts generated: {report['drafts_generated']}",
        f"- Held: {report['held']}",
        f"- Blocked: {report['blocked']}",
        f"- Failed: {report['failed']}",
        f"- Average confidence: {report['average_confidence']}",
        "",
        "## Per Article",
    ]
    for row in report["per_article"]:
        lines.extend(
            [
                f"- {row['article_id']}: {row['status']} confidence={row['confidence']} sources={row['sources']} judge={row['judge_decision']}",
                f"  - Output: {row['output_path']}",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a controlled draft-only canary batch.")
    parser.add_argument("--count", type=int, default=5)
    parser.add_argument("--output-root", type=Path, default=None)
    parser.add_argument("--batch-id", default=None)
    parser.add_argument(
        "--allow-heuristic-fallback",
        action="store_true",
        default=str(os.getenv("ALLOW_HEURISTIC_FALLBACK", "")).strip().lower() in {"1", "true", "yes", "on"},
        help="Allow local heuristic writer/rewrite fallback. Keep disabled for production-like canaries.",
    )
    args = parser.parse_args()
    report = run_canary_batch(count=args.count, output_root=args.output_root, batch_id=args.batch_id, allow_heuristic_fallback=args.allow_heuristic_fallback)
    print(json.dumps({k: report[k] for k in ("canary_mode", "canary_batch_size", "output_root", "selected", "drafts_generated", "held", "blocked", "failed", "average_confidence")}, indent=2))
    return 0 if report["selected"] == args.count and report["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
