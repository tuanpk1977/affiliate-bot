from __future__ import annotations

import csv
import json
import re
from datetime import UTC, datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from config import settings
from modules.editorial_quality import (
    EditorialJudge,
    FactVerificationEngine,
    KnowledgeGraphRuntime,
    PublishingConfidenceEngine,
    SourceQualityRanker,
    StructuredReviewBuilder,
    TargetedRewriteExecutor,
    TargetedRewriteLoop,
)
from modules.editorial_quality import SectionRewriteProvider


REVIEW_STATUSES = {
    "draft",
    "needs_ai_review",
    "ai_review_passed",
    "needs_human_review",
    "human_approved",
    "rejected",
    "needs_revision",
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


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return path
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: json.dumps(value, ensure_ascii=False) if isinstance(value, (list, dict)) else value for key, value in row.items()})
    return path


def _write_md(path: Path, lines: list[str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return path


def _clamp(value: float, minimum: float = 0, maximum: float = 100) -> float:
    return max(minimum, min(maximum, value))


def _strip_html(value: str) -> str:
    return re.sub(r"<[^>]+>", " ", value or "")


class ContentReviewEngine:
    def __init__(self, data_dir: Path | None = None, config: dict[str, Any] | None = None, rewrite_provider: SectionRewriteProvider | None = None) -> None:
        self.data_dir = data_dir or settings.data_dir
        self.config = config or {}
        self.queue_path = self.data_dir / "content_review_queue.json"
        self.report_json = self.data_dir / "content_review_report.json"
        self.report_csv = self.data_dir / "content_review_report.csv"
        self.report_md = self.data_dir / "content_review_report.md"
        self.source_ranker = SourceQualityRanker(self.config.get("source_ranking", {}) if isinstance(self.config.get("source_ranking"), dict) else {})
        self.fact_verifier = FactVerificationEngine(self.config.get("fact_verification", {}) if isinstance(self.config.get("fact_verification"), dict) else {})
        self.knowledge_graph = KnowledgeGraphRuntime(self.data_dir, self.config.get("knowledge_graph", {}) if isinstance(self.config.get("knowledge_graph"), dict) else {})
        self.structured_review_builder = StructuredReviewBuilder()
        self.rewrite_loop = TargetedRewriteLoop(self.config.get("rewrite_loop", {}) if isinstance(self.config.get("rewrite_loop"), dict) else {})
        self.rewrite_executor = TargetedRewriteExecutor(self.config.get("rewrite_loop", {}) if isinstance(self.config.get("rewrite_loop"), dict) else {}, provider=rewrite_provider)
        self.confidence_engine = PublishingConfidenceEngine(self.config.get("publishing_confidence", {}) if isinstance(self.config.get("publishing_confidence"), dict) else {})
        self.judge = EditorialJudge()

    def load_queue(self) -> list[dict[str, Any]]:
        return _read_json(self.queue_path, [])

    def save_queue(self, rows: list[dict[str, Any]]) -> None:
        _write_json(self.queue_path, rows)

    def refresh_reports(self) -> None:
        self._write_report(self.load_queue())

    def review_content(
        self,
        *,
        topic: dict[str, Any],
        html: str,
        title: str,
        description: str,
        url: str,
        internal_links: list[tuple[str, str]],
        warnings: list[str],
        research: dict[str, Any],
        planning: dict[str, Any],
    ) -> dict[str, Any]:
        queue = self.load_queue()
        text = _strip_html(html)
        words = [word for word in re.findall(r"[A-Za-z0-9']+", text)]
        word_count = len(words)
        sentences = [segment.strip() for segment in re.split(r"[.!?]+", text) if segment.strip()]
        average_sentence_length = word_count / max(1, len(sentences))
        average_word_length = sum(len(word) for word in words) / max(1, word_count)
        readability = round(_clamp(100 - average_sentence_length * 1.1 - average_word_length * 4), 2)

        research_quality = research.get("quality") if isinstance(research.get("quality"), dict) else {}
        source_quality = float(research_quality.get("source_quality", 0))
        verified_source_score = float(research_quality.get("total_verified_source_score", 0))
        factual_quality = round(_clamp((float(research_quality.get("overall_score", 0)) * 0.55) + (source_quality * 0.30) + (verified_source_score * 0.15) - len(warnings) * 3), 2)

        title_len = len(title.strip())
        desc_len = len(description.strip())
        keyword = str(topic.get("topic") or planning.get("keyword") or "").strip().lower()
        title_contains_keyword = keyword[:40] in title.lower() if keyword else False
        seo_title_meta_quality = round(
            _clamp(
                30
                + (25 if 35 <= title_len <= 65 else 8)
                + (25 if 110 <= desc_len <= 170 else 10)
                + (20 if title_contains_keyword else 0)
            ),
            2,
        )

        affiliate_disclosure_present = "affiliate disclosure" in html.lower() and "commission" in html.lower()
        internal_link_count = len(internal_links)
        internal_links_score = round(_clamp(30 + internal_link_count * 18), 2)
        duplicate_content_risk = round(self._duplicate_risk(title, url, queue, current_slug=str(topic.get("slug") or "")), 2)
        business_value = round(self._business_value(topic, planning, research_quality), 2)

        checks = {
            "factual_quality": factual_quality,
            "source_quality": source_quality,
            "seo_title_meta_quality": seo_title_meta_quality,
            "affiliate_disclosure": 100 if affiliate_disclosure_present else 0,
            "internal_links": internal_links_score,
            "duplicate_content_risk": duplicate_content_risk,
            "readability": readability,
            "word_count": word_count,
            "business_value": business_value,
        }
        publish_readiness = round(
            _clamp(
                (
                    factual_quality
                    + source_quality
                    + seo_title_meta_quality
                    + checks["affiliate_disclosure"]
                    + internal_links_score
                    + readability
                    + business_value
                    + max(0, 100 - duplicate_content_risk)
                )
                / 8
            ),
            2,
        )
        checks["publish_readiness"] = publish_readiness

        minimum_word_count = int(float(self.config.get("minimum_word_count", 900)))
        minimum_publish_readiness = float(self.config.get("minimum_publish_readiness", 65))
        minimum_readability = float(self.config.get("minimum_readability_score", 35))
        maximum_duplicate_risk = float(self.config.get("maximum_duplicate_risk", 65))
        minimum_factual_quality = float(self.config.get("minimum_factual_quality", 35))
        minimum_source_quality = float(self.config.get("minimum_source_quality", 20))
        minimum_seo_quality = float(self.config.get("minimum_seo_quality", 40))
        minimum_business_value = float(self.config.get("minimum_business_value", 35))

        failures: list[str] = []
        hard_blockers: list[str] = []
        review_warnings: list[str] = list(dict.fromkeys(str(item) for item in warnings if str(item).strip()))
        if factual_quality < minimum_factual_quality:
            failures.append("factual quality below threshold")
        if source_quality < minimum_source_quality:
            failures.append("source quality below threshold")
        if seo_title_meta_quality < minimum_seo_quality:
            failures.append("SEO title/meta quality below threshold")
        if not affiliate_disclosure_present:
            failures.append("affiliate disclosure missing")
        if internal_link_count < 1:
            failures.append("internal links missing")
        if duplicate_content_risk > maximum_duplicate_risk:
            failures.append("duplicate content risk too high")
        if readability < minimum_readability:
            failures.append("readability below threshold")
        if word_count < minimum_word_count:
            failures.append("word count below threshold")
        if business_value < minimum_business_value:
            failures.append("business value below threshold")
        if publish_readiness < minimum_publish_readiness:
            failures.append("publish readiness below threshold")

        source_candidates = self._source_candidates(research)
        source_quality_review = self.source_ranker.rank(source_candidates)
        legacy_source_score_present = bool(source_quality > 0 or verified_source_score > 0 or (research.get("quality_gate") or {}).get("passed"))
        if source_candidates or not legacy_source_score_present:
            fact_verification = self.fact_verifier.verify(html=html, sources=source_candidates)
        else:
            fact_verification = {
                "schema_version": 2,
                "claim_count": 0,
                "claims": [],
                "hard_blockers": [],
                "warnings": ["fact verification skipped: legacy source URLs unavailable"],
                "cache_size": 0,
            }
            review_warnings.extend(fact_verification["warnings"])

        if not html.strip() or word_count <= 0:
            hard_blockers.append("empty or missing draft")
        if source_quality <= 0 and verified_source_score <= 0 and not legacy_source_score_present:
            hard_blockers.append("zero usable sources")
        if duplicate_content_risk >= float(self.config.get("critical_duplicate_risk", 92)):
            hard_blockers.append("duplicate collision")
        hard_blockers.extend(str(item) for item in fact_verification.get("hard_blockers", []) if str(item).strip())

        soft_failure_markers = (
            "SEO title/meta quality below threshold",
            "readability below threshold",
            "word count below threshold",
            "business value below threshold",
            "publish readiness below threshold",
            "source quality below threshold",
            "factual quality below threshold",
            "internal links missing",
        )
        for failure in failures:
            if failure in hard_blockers:
                continue
            if failure == "affiliate disclosure missing":
                review_warnings.append("affiliate verification warning: affiliate disclosure missing")
            elif failure == "duplicate content risk too high":
                review_warnings.append(failure)
            elif failure in soft_failure_markers:
                review_warnings.append(failure)
            else:
                hard_blockers.append(failure)
        review_warnings.extend(str(item) for item in fact_verification.get("warnings", []) if str(item).strip())
        hard_blockers = list(dict.fromkeys(hard_blockers))
        review_warnings = [item for item in dict.fromkeys(review_warnings) if item not in hard_blockers]

        human_required = self._requires_human_approval(topic)
        if hard_blockers:
            status = "needs_revision"
        elif human_required:
            status = "needs_human_review"
        else:
            status = "ai_review_passed"

        reviewed_at = datetime.now(UTC).isoformat()
        result = {
            "slug": str(topic.get("slug") or ""),
            "topic": str(topic.get("topic") or ""),
            "url": url,
            "status": status,
            "reviewed_at": reviewed_at,
            "word_count": word_count,
            "factual_quality": factual_quality,
            "source_quality": source_quality,
            "seo_title_meta_quality": seo_title_meta_quality,
            "affiliate_disclosure_present": affiliate_disclosure_present,
            "internal_link_count": internal_link_count,
            "duplicate_content_risk": duplicate_content_risk,
            "readability": readability,
            "business_value": business_value,
            "publish_readiness": publish_readiness,
            "publishable": status in {"ai_review_passed", "needs_human_review", "human_approved"},
            "requires_human_approval": human_required,
            "failures": failures,
            "hard_blockers": hard_blockers,
            "warnings": review_warnings,
        }
        structured_review = self.structured_review_builder.build(
            legacy_review=result,
            failures=failures,
            warnings=review_warnings,
            hard_blockers=hard_blockers,
            fact_verification=fact_verification,
            source_quality=source_quality_review,
        )
        rewrite_execution = self.rewrite_executor.execute(
            article_id=str(topic.get("slug") or ""),
            html=html,
            structured_review=structured_review,
            context={"topic": topic.get("topic"), "primary_keyword": planning.get("keyword")},
        )
        rewrite_plan = self.rewrite_loop.plan(structured_review=structured_review)
        rewrite_summary = {
            key: value
            for key, value in rewrite_execution.items()
            if key != "html"
        }
        publishing_confidence = self.confidence_engine.calculate(
            review=result,
            research=research,
            fact_verification=fact_verification,
            source_quality=source_quality_review,
            hard_blockers=hard_blockers,
            warnings=review_warnings,
        )
        ai_judge = self.judge.evaluate(
            structured_review=structured_review,
            fact_verification=fact_verification,
            publishing_confidence=publishing_confidence,
        )
        graph_result = self.knowledge_graph.update_article(
            article_id=str(topic.get("slug") or ""),
            research_package=research,
            draft_html=str(rewrite_execution.get("html") or html),
            source_urls=[row["url"] for row in source_quality_review if row.get("url")],
        )
        review_state = "BLOCKED" if hard_blockers else ("WARNING" if review_warnings or failures else "PASS")
        result.update(
            {
                "schema_version": 2,
                "article_id": str(topic.get("slug") or ""),
                "review_state": review_state,
                "structured_review": structured_review,
                "source_quality_review": source_quality_review,
                "fact_verification": fact_verification,
                "targeted_rewrite": {**rewrite_plan, **rewrite_summary},
                "rewrite_history": rewrite_execution.get("rewrite_history", []),
                "publishing_confidence": publishing_confidence,
                "ai_judge": ai_judge,
                "recommended_reviewer_focus": ai_judge.get("recommended_human_focus", []),
                "entity_coverage": graph_result.get("entity_coverage", {}),
                "internal_link_suggestions": graph_result.get("internal_link_suggestions", []),
                "cannibalization": graph_result.get("cannibalization", {}),
                "estimated_review_minutes": 12 if hard_blockers else 8 if review_warnings else 5,
            }
        )
        if rewrite_execution.get("html") != html:
            result["rewritten_html"] = rewrite_execution.get("html")
        self._upsert_queue(result)
        return result

    def _upsert_queue(self, result: dict[str, Any]) -> None:
        rows = self.load_queue()
        stored_result = {key: value for key, value in result.items() if key != "rewritten_html"}
        replaced = False
        for index, row in enumerate(rows):
            if str(row.get("slug", "")) == str(result.get("slug", "")):
                rows[index] = stored_result
                replaced = True
                break
        if not replaced:
            rows.append(stored_result)
        self.save_queue(rows)
        self._write_report(rows)

    def _write_report(self, rows: list[dict[str, Any]]) -> None:
        summary = {
            "items": len(rows),
            "needs_revision": sum(1 for row in rows if str(row.get("status", "")) == "needs_revision"),
            "ai_review_passed": sum(1 for row in rows if str(row.get("status", "")) == "ai_review_passed"),
            "needs_human_review": sum(1 for row in rows if str(row.get("status", "")) == "needs_human_review"),
            "human_approved": sum(1 for row in rows if str(row.get("status", "")) == "human_approved"),
            "rejected": sum(1 for row in rows if str(row.get("status", "")) == "rejected"),
        }
        _write_json(self.report_json, {"summary": summary, "items": rows})
        _write_csv(self.report_csv, rows)
        _write_md(
            self.report_md,
            [
                "# Content Review Report",
                "",
                f"- Items: {summary['items']}",
                f"- AI Review Passed: {summary['ai_review_passed']}",
                f"- Needs Human Review: {summary['needs_human_review']}",
                f"- Needs Revision: {summary['needs_revision']}",
                f"- Human Approved: {summary['human_approved']}",
                f"- Rejected: {summary['rejected']}",
            ],
        )

    def _duplicate_risk(self, title: str, url: str, queue: list[dict[str, Any]], *, current_slug: str = "") -> float:
        if not queue:
            return 10.0
        scores = []
        for row in queue:
            if current_slug and str(row.get("slug", "")) == current_slug:
                continue
            similarity = SequenceMatcher(None, title.lower(), str(row.get("topic", "")).lower()).ratio()
            same_url = 1.0 if str(row.get("url", "")) == url else 0.0
            scores.append(max(similarity * 100, same_url * 100))
        risk = max(scores, default=0.0)
        return 10.0 if risk < 35 else risk

    def _business_value(self, topic: dict[str, Any], planning: dict[str, Any], research_quality: dict[str, Any]) -> float:
        estimated = str(topic.get("estimated_business_value") or "").strip().lower()
        estimated_score = {"low": 35, "medium": 60, "high": 82}.get(estimated, 55)
        coverage = float(planning.get("coverage_score", 0))
        affiliate_readiness = float(research_quality.get("affiliate_readiness", 0))
        return _clamp(estimated_score * 0.45 + coverage * 0.20 + affiliate_readiness * 0.35)

    def _requires_human_approval(self, topic: dict[str, Any]) -> bool:
        if bool(self.config.get("require_human_approval", False)):
            return True
        if bool((settings.editorial_config or {}).get("human_approval", {}).get("required", False)):
            return True
        if bool(self.config.get("require_human_approval", False)):
            return True
        manual_types = {str(item).strip().lower() for item in self.config.get("manual_approval_article_types", ["affiliate", "review", "pricing", "comparison", "product_recommendation"])}
        article_type = str(topic.get("content_type") or topic.get("article_type") or "").strip().lower()
        if article_type in manual_types:
            return True
        title = str(topic.get("topic") or topic.get("title") or "").lower()
        markers = tuple(str(item).strip().lower() for item in self.config.get("manual_approval_title_markers", [" pricing", " review", " comparison", " vs ", " best ", " alternative", " alternatives", "recommend"]))
        return any(marker in title for marker in markers)

    def _source_candidates(self, research: dict[str, Any]) -> list[dict[str, Any]]:
        sources = research.get("sources") if isinstance(research.get("sources"), dict) else {}
        candidates: list[dict[str, Any]] = []
        for row in sources.get("verified_sources", []) if isinstance(sources.get("verified_sources"), list) else []:
            if isinstance(row, dict) and str(row.get("url") or "").strip():
                candidates.append(row)
        trusted = sources.get("trusted_sources") if isinstance(sources.get("trusted_sources"), dict) else {}
        for rows in trusted.values():
            if not isinstance(rows, list):
                continue
            for row in rows:
                if isinstance(row, dict) and str(row.get("url") or "").strip():
                    candidates.append(row)
        seen: set[str] = set()
        unique: list[dict[str, Any]] = []
        for row in candidates:
            url = str(row.get("url") or "").strip()
            if not url or url in seen:
                continue
            seen.add(url)
            unique.append(row)
        return unique
