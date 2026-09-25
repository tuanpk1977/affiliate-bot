from __future__ import annotations

import csv
import hashlib
import itertools
import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Iterable
from zoneinfo import ZoneInfo

from modules.operations_intelligence.calibration import Phase2Calibration
from modules.operations_intelligence.editorial_memory import EditorialMemoryStore
from modules.operations_intelligence.feature_flags import feature_enabled
from modules.operations_intelligence.weekly_preflight import WeeklyCalibrationPreflight
from modules.operations_intelligence.analytics_feedback import planning_feedback_advisory
from modules.editorial_topic_strategy import EditorialTopicStrategy
from modules.content_opportunity_fallback import ThreeLevelContentOpportunityFallback
from modules.affiliate_opportunity_discovery import apply_verified_affiliate_boost
from modules.official_source_registry import OfficialSourceRegistry, entity_key
from modules.seo_engine.content_gap import analyze_gaps
from modules.seo_engine.internal_link_planner import plan_internal_links
from modules.seo_engine.keyword_clustering import build_clusters
from modules.seo_engine.keyword_research import collect_candidates
from modules.seo_engine.opportunity_scoring import score_opportunities
from modules.seo_engine.weekly_preflight import WeeklySeoPreflight, configured_seed_keywords
from modules.weekly_root_guard import (
    FOUNDATION_MAIN,
    normalize_weekly_root_manifest,
    planned_weekly_series,
    stable_root_topic_id,
    validate_weekly_root_manifest,
    week_start_for,
)


OPERATING_TIMEZONE = ZoneInfo("Asia/Bangkok")


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")[:120]


def _tokens(value: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]+", value.casefold()) if len(token) > 2}


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _run_id(prefix: str, now: datetime) -> str:
    seed = f"{prefix}|{now.isoformat()}"
    return f"{prefix}-{now:%Y%m%dT%H%M%SZ}-{hashlib.sha256(seed.encode()).hexdigest()[:8]}"


def _weekly_plan_angles(topic: str) -> list[dict[str, str]]:
    return [
        {"angle": "pillar", "article_type": "foundation", "title": f"{topic}: Complete Review and Buyer Guide"},
        {"angle": "comparison", "article_type": "comparison", "title": f"{topic}: Comparison and Alternatives"},
        {"angle": "use_cases", "article_type": "use_case", "title": f"{topic}: Workflows and Use Cases"},
        {"angle": "pricing", "article_type": "pricing", "title": f"{topic}: Pricing, Cost, and ROI"},
        {"angle": "pros_cons", "article_type": "review", "title": f"{topic}: Pros, Cons, and Limitations"},
        {"angle": "tutorial", "article_type": "tutorial", "title": f"How to Implement {topic}"},
        {"angle": "security_privacy", "article_type": "security", "title": f"{topic}: Security and Privacy"},
        {"angle": "case_study", "article_type": "implementation_guide", "title": f"{topic}: Implementation Guide and Case Study"},
    ]


def _intent_family(keyword: str, fallback: str) -> str:
    value = keyword.casefold()
    if any(marker in value for marker in (" alternative", " alternatives", " vs ", "comparison", "compare")):
        return "comparison"
    if any(marker in value for marker in ("pricing", "price", "cost", "roi")):
        return "commercial investigation"
    if any(marker in value for marker in ("how to", "tutorial", "implementation", "workflow")):
        return "implementation guide"
    if any(marker in value for marker in ("best ", "review", "tools", "software")):
        return "commercial research"
    return fallback or "informational"


def _root_diversity(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    generic = {"the", "and", "for", "with", "2026", "best", "review", "tools", "software", "platform"}
    left_tokens = _tokens(str(left.get("topic") or left.get("root_title") or "")) - generic
    right_tokens = _tokens(str(right.get("topic") or right.get("root_title") or "")) - generic
    union = left_tokens | right_tokens
    overlap = len(left_tokens & right_tokens) / max(1, len(union))
    left_intent = str(left.get("search_intent") or left.get("primary_search_intent") or "").casefold().strip()
    right_intent = str(right.get("search_intent") or right.get("primary_search_intent") or "").casefold().strip()
    same_intent = bool(left_intent and left_intent == right_intent)
    dimensions = ("category", "subcategory", "buyer_type", "use_case", "monetization_model")
    same_dimensions = [
        key for key in dimensions
        if str(left.get(key) or "").strip()
        and str(left.get(key) or "").casefold().strip() == str(right.get(key) or "").casefold().strip()
    ]
    conflicts: list[str] = []
    unsafe_candidates = [
        str(row.get("topic") or row.get("root_title") or row.get("slug") or "candidate")
        for row in (left, right)
        if bool(row.get("cannibalization_risk"))
        or str(row.get("duplicate_risk") or "").casefold().startswith("high")
    ]
    if unsafe_candidates:
        conflicts.append(f"high cannibalization risk: {', '.join(unsafe_candidates)}")
    if same_intent:
        conflicts.append(f"same search intent: {left_intent}")
    if overlap >= 0.55:
        conflicts.append(f"topic token overlap is {overlap:.2f}")
    if str(left.get("root_topic_id") or "") == str(right.get("root_topic_id") or ""):
        conflicts.append("duplicate root_topic_id")
    dimension_penalty = min(25.0, len(same_dimensions) * 5.0)
    if len(same_dimensions) >= 2 and (same_intent or overlap >= 0.35):
        conflicts.append(f"same strategic dimensions: {', '.join(same_dimensions)}")
    score = round(max(0.0, 100.0 - (40.0 if same_intent else 0.0) - overlap * 45.0 - dimension_penalty - (60.0 if unsafe_candidates else 0.0)), 2)
    return {
        "root_diversity_score": score,
        "intent_conflict": same_intent,
        "topic_overlap": round(overlap, 4),
        "same_dimensions": same_dimensions,
        "cannibalization_risk": bool(conflicts),
        "conflict_warnings": conflicts,
        "requires_edit": bool(conflicts),
    }


def _recommended_pair(candidates: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    pairs = []
    for left, right in itertools.combinations(candidates, 2):
        diversity = _root_diversity(left, right)
        opportunity = float(left.get("opportunity_score") or 0) + float(right.get("opportunity_score") or 0)
        pairs.append((not diversity["requires_edit"], opportunity + diversity["root_diversity_score"], left, right, diversity))
    if not pairs:
        return [], {"root_diversity_score": 0, "requires_edit": True, "conflict_warnings": ["fewer than two candidates"]}
    _, _, left, right, diversity = max(pairs, key=lambda row: (row[0], row[1]))
    return [left, right], diversity


@dataclass
class WeeklyTopicSelection:
    root: Path
    now: datetime | None = None

    def __post_init__(self) -> None:
        self.root = self.root.resolve()
        self.now = (self.now or datetime.now(UTC)).astimezone(UTC)
        self.operating_date = self.now.astimezone(OPERATING_TIMEZONE).date().isoformat()
        self.week_start = week_start_for(self.operating_date)

    def detect(self, *, seeds: list[str] | None = None, imports: list[Path] | None = None) -> dict[str, Any]:
        run_id = _run_id("weekly-topic-selection", self.now)
        existing = self._current_manifest()
        if existing:
            root_count = len(existing.get("topics") or [])
            exact_contract = root_count in {1, 2}
            diversity = (
                _root_diversity(existing["topics"][0], existing["topics"][1])
                if root_count == 2
                else {"root_diversity_score": 100.0, "requires_edit": False, "conflict_warnings": ["Temporary partial week"]}
                if root_count == 1
                else {}
            )
            source_preflight = [self._candidate_source_readiness(row) for row in existing.get("topics") or []]
            source_warnings = [row["reason"] for row in source_preflight if not row["passes"]]
            return {
                "schema_version": "weekly_topic_selection_v1",
                "run_id": run_id,
                "timestamp": self.now.isoformat(),
                "week_start": self.week_start,
                "status": "SKIP" if exact_contract else "BLOCKED",
                "reason": (
                    f"This week already has {root_count} locked, operator-approved weekly root(s); they were not changed."
                    if exact_contract
                    else f"This week has a locked legacy manifest with {root_count} roots; it cannot be replaced automatically. Start the new two-root workflow in a new editorial week."
                ),
                "candidates": [],
                "recommended_weekly_roots": [self._root_summary(row) for row in existing["topics"][:2]],
                "existing_manifest": str(self._manifest_path()),
                "weekly_roots_changed": False,
                "root_diversity": diversity,
                "weekly_root_source_preflight": source_preflight,
                "source_preflight_warnings": source_warnings,
                "partial_week": root_count == 1,
                "blocked": not exact_contract,
                "analytics_feedback": planning_feedback_advisory(
                    self.root,
                    root_topics=[str(row.get("root_title") or row.get("title") or "") for row in existing.get("topics") or []],
                    now=self.now,
                ),
                **self._safety(),
            }

        preflight = WeeklySeoPreflight(root=self.root, now=self.now).detect(seeds=seeds, imports=imports)
        if preflight.get("blocked"):
            return {
                "schema_version": "weekly_topic_selection_v1",
                "run_id": run_id,
                "timestamp": self.now.isoformat(),
                "week_start": self.week_start,
                "status": "BLOCKED",
                "reason": "SEO preflight has missing or invalid input.",
                "seo_preflight": preflight,
                "candidates": [],
                "recommended_weekly_roots": [],
                "weekly_roots_changed": False,
                "blocked": True,
                "analytics_feedback": planning_feedback_advisory(self.root, now=self.now),
                **self._safety(),
            }
        pipeline = WeeklySeoPreflight(root=self.root, now=self.now).pipeline
        seed_values = list(seeds) if seeds else configured_seed_keywords(pipeline.config)
        import_values = list(imports or [])
        candidates = (
            collect_candidates(seed_values, import_values)
            if preflight["actions"]["import_keywords"]["status"] == "RUN"
            else pipeline._read(pipeline.data_dir / "keyword_candidates.json", [])
        )
        pages = pipeline.existing_pages()
        page_slugs = {row["slug"] for row in pages}
        clusters = (
            build_clusters(candidates, page_slugs)
            if preflight["actions"]["build_clusters"]["status"] == "RUN"
            else pipeline._read(pipeline.data_dir / "keyword_clusters.json", [])
        )
        gaps = (
            analyze_gaps(clusters, page_slugs)
            if preflight["actions"]["analyze_gaps"]["status"] == "RUN"
            else pipeline._read(pipeline.data_dir / "content_gaps.json", [])
        )
        opportunities = (
            score_opportunities(gaps, clusters, pipeline.config.get("scoring_weights"))
            if preflight["actions"]["rank_opportunities"]["status"] == "RUN"
            else pipeline._read(pipeline.data_dir / "opportunities.json", [])
        )
        links = (
            plan_internal_links(gaps, pages)
            if preflight["actions"]["plan_internal_links"]["status"] == "REVIEW"
            else pipeline._read(pipeline.data_dir / "internal_link_plan.json", [])
        )
        ranked_primary = self._rank_candidates(opportunities, pages, links)
        analytics_feedback = planning_feedback_advisory(self.root, now=self.now)
        ranked_all, recovery = self._expand_candidate_inventory(
            ranked_primary,
            pages=pages,
            links=links,
            reserve_keywords=list(pipeline.config.get("evergreen_root_reserve_keywords") or []),
            analytics_feedback=analytics_feedback,
        )
        strategy = EditorialTopicStrategy(self.root)
        ranked_all, taxonomy_fallback = strategy.fallback_inventory(ranked_all)
        recovery.update(taxonomy_fallback)
        ranked_all, affiliate_input = apply_verified_affiliate_boost(self.root, ranked_all)
        ranked_all.sort(
            key=lambda row: (-float(row.get("opportunity_score") or 0), str(row.get("slug") or ""))
        )
        recovery["affiliate_opportunity_input"] = affiliate_input
        source_ready: list[dict[str, Any]] = []
        source_held: list[dict[str, Any]] = []
        for candidate in ranked_all:
            readiness = self._candidate_source_readiness(candidate)
            candidate["source_readiness"] = readiness
            if readiness["passes"]:
                source_ready.append(candidate)
            else:
                source_held.append(
                    {
                        "topic": candidate.get("topic"),
                        "slug": candidate.get("slug"),
                        "reason": readiness["reason"],
                    }
                )
        ranked_all = source_ready
        recovery["candidates_rejected_source_unready"] = len(source_held)
        recovery["source_unready_candidates"] = source_held
        ranked_all, content_fallback = ThreeLevelContentOpportunityFallback(
            self.root,
            now=self.now,
        ).select(ranked_all, required_count=2, candidate_limit=10)
        fallback_rejections = list(content_fallback.get("rejected_candidates") or [])
        for row in source_held:
            fallback_rejections.append(
                {
                    "candidate": row.get("topic") or row.get("slug"),
                    "level": 1,
                    "root_topic": row.get("slug"),
                    "intent": "",
                    "novelty_score": None,
                    "overlap_score": None,
                    "research_status": "RESEARCH_REQUIRED",
                    "rejection_stage": "RESEARCH_READINESS",
                    "rejection_reason": row.get("reason"),
                    "required_operator_action": "Add and verify source evidence in Menu S, then rerun Menu 1.",
                }
            )
        content_fallback["NEW_ROOT_CANDIDATES"] = len(source_ready) + len(source_held)
        content_fallback["NEW_ROOT_PASSED"] = len(source_ready)
        content_fallback["SAFE_WEEKLY_ROOTS"] = len(ranked_all)
        content_fallback["rejected_candidates"] = fallback_rejections
        recovery["content_opportunity_fallback"] = content_fallback
        recovery["fallback_level_used"] = content_fallback.get("fallback_level_used", 1)
        recovery["candidates_accepted"] = len(ranked_all)
        recovery["partial_week"] = len(ranked_all) == 1
        recovery["all_levels_exhausted"] = len(ranked_all) == 0
        recovery["operator_selection_required"] = len(_recommended_pair(ranked_all)[0]) != 2
        ranked = ranked_all[:10]
        if feature_enabled(self.root, "editorial_memory.enabled"):
            try:
                memory = EditorialMemoryStore(root=self.root)
                for candidate in ranked:
                    candidate["editorial_memory"] = memory.detect_duplicates(
                        {
                            "slug": candidate.get("slug"),
                            "title": candidate.get("topic"),
                            "root_topic": candidate.get("root_topic_id"),
                            "angle": "weekly_root",
                            "keyword": candidate.get("primary_keyword"),
                        }
                    )
            except (OSError, ValueError, sqlite3.Error):
                pass
        recommended, diversity = _recommended_pair(ranked)
        recommended_indexes = [ranked.index(row) + 1 for row in recommended]
        if len(recommended) == 2 and not diversity.get("requires_edit"):
            status, reason, blocked = (
                "READY_FOR_ROOT_APPROVAL",
                "Candidate recovery found two diverse, unused weekly roots. Operator approval is required before saving.",
                False,
            )
        elif len(ranked) == 1:
            recommended = ranked[:1]
            recommended_indexes = [1]
            diversity = {
                "root_diversity_score": 100.0,
                "requires_edit": False,
                "conflict_warnings": ["Partial week: only one safe controlled-taxonomy root is available."],
            }
            status, reason, blocked = (
                "PARTIAL_WEEK_REVIEW",
                "Only one safe root remains after all three controlled fallback levels. Operator may approve a temporary one-root week, request a broader rescan, edit the selection, or cancel.",
                False,
            )
        elif content_fallback.get("status") == "INSUFFICIENT_QUALITY_OPPORTUNITIES" and not ranked:
            status, reason, blocked = (
                "INSUFFICIENT_QUALITY_OPPORTUNITIES",
                "All three content-opportunity levels were evaluated; no candidate passed the existing quality and source gates.",
                True,
            )
        else:
            status, reason, blocked = (
                "AWAITING_OPERATOR_SELECTION",
                "Automatic candidate recovery could not form a safe two-root pair. Add or edit an evergreen root; no weekly plan was changed.",
                False,
            )
        return {
            "schema_version": "weekly_topic_selection_v1",
            "run_id": run_id,
            "timestamp": self.now.isoformat(),
            "week_start": self.week_start,
            "status": status,
            "reason": reason,
            "seo_preflight": preflight,
            "candidates": ranked,
            "recommended_weekly_roots": recommended,
            "recommended_candidate_indexes": recommended_indexes,
            "candidate_inventory": {
                "configured": len(seed_values) + len(pipeline.config.get("evergreen_root_reserve_keywords") or []),
                "eligible": len(ranked_all),
                "displayed": len(ranked),
                "minimum_required": 2,
                "reserve_warning": len(ranked_all) < 4,
            },
            "root_diversity": diversity,
            "candidate_recovery": recovery,
            "WEEKLY_ROOT_RECOVERY_STATUS": recovery["status"],
            "CANDIDATES_BEFORE": len(ranked_primary),
            "CANDIDATES_AFTER": len(ranked_all),
            "DUPLICATES_REJECTED": recovery["candidates_rejected_duplicate"],
            "CANDIDATES_FOUND": recovery["candidates_found"],
            "CANDIDATES_REJECTED_DUPLICATE": recovery["candidates_rejected_duplicate"],
            "CANDIDATES_REJECTED_USED": recovery["candidates_rejected_used"],
            "CANDIDATES_REJECTED_LOW_CONFIDENCE": recovery["candidates_rejected_low_confidence"],
            "CANDIDATES_REJECTED_SOURCE_UNREADY": recovery["candidates_rejected_source_unready"],
            "CANDIDATES_ACCEPTED": recovery["candidates_accepted"],
            "ROOT_DIVERSITY_SCORE": diversity.get("root_diversity_score", 0),
            "FALLBACK_TIER_USED": recovery["fallback_tier_used"],
            "CONTROLLED_FALLBACK_LEVEL_USED": recovery.get("fallback_level_used", 0),
            "fallback_level": content_fallback.get("fallback_level_used", 1),
            "content_opportunity_fallback": content_fallback,
            "PARTIAL_WEEK": bool(recovery.get("partial_week")),
            "MENU1_FINAL_STATUS": status,
            "weekly_roots_changed": False,
            "blocked": blocked,
            "analytics_feedback": planning_feedback_advisory(
                self.root,
                root_topics=[str(row.get("topic") or "") for row in recommended],
                now=self.now,
            ),
            **self._safety(),
        }

    def persist(self, report: dict[str, Any], selected_indexes: list[int] | None = None) -> dict[str, Any]:
        if report.get("blocked") or report.get("status") == "SKIP":
            return {**report, "persistence_status": report.get("status"), "weekly_roots_changed": False}
        indexes = selected_indexes or list(report.get("recommended_candidate_indexes") or [1, 2])
        if len(indexes) not in {1, 2} or len(set(indexes)) != len(indexes):
            raise ValueError("Select one temporary partial-week root or two distinct weekly roots.")
        candidates = report["candidates"]
        try:
            chosen = [candidates[index - 1] for index in indexes]
        except IndexError as exc:
            raise ValueError("Candidate index is outside the displayed list.") from exc
        diversity = _root_diversity(chosen[0], chosen[1]) if len(chosen) == 2 else {
            "root_diversity_score": 100.0,
            "requires_edit": False,
            "conflict_warnings": ["Operator-approved temporary partial week with one root."],
        }
        if diversity["requires_edit"]:
            return {
                **report,
                "status": "EDIT_REQUIRED",
                "persistence_status": "EDIT_REQUIRED",
                "reason": "The selected roots have overlapping intent or topical scope. Choose a different pair with Edit.",
                "root_diversity": diversity,
                "weekly_roots_changed": False,
            }
        source_failures = []
        for item in chosen:
            readiness = item.get("source_readiness") or self._candidate_source_readiness(item)
            if not readiness.get("passes"):
                source_failures.append(f"{item.get('slug')}: {readiness.get('reason')}")
        if source_failures:
            return {
                **report,
                "status": "EDIT_REQUIRED",
                "persistence_status": "EDIT_REQUIRED",
                "reason": "Selected roots are not research-source ready. Choose source-ready roots with Edit.",
                "source_preflight_warnings": source_failures,
                "weekly_roots_changed": False,
            }
        topics = []
        for rank, item in enumerate(chosen, start=1):
            refresh = item.get("opportunity_type") == "content_refresh"
            series_plan = (
                [
                    {
                        "root_topic_id": item["root_topic_id"],
                        "root_title": item["topic"],
                        "content_lane": FOUNDATION_MAIN,
                        "article_id": f"{item['root_topic_id']}-content-refresh",
                        "sequence_number": 1,
                        "scheduled_date": self.week_start,
                        "planned_publishing_day": self.week_start,
                        "daily_angle": "content_refresh",
                        "primary_search_intent": item["search_intent"],
                        "search_intent": item["search_intent"],
                        "reader_question": f"What evidence and decision support should be refreshed in {item['topic']}?",
                        "refresh_thesis": item.get("refresh_thesis"),
                        "update_scope": item.get("update_scope"),
                        "required_evidence": ["prepared verified sources", "existing article snapshot"],
                        "next_scheduled_article": {"daily_angle": "", "bridge_state": "SERIES_COMPLETE"},
                        "series_status": "planned",
                        "article_state": "planned",
                    }
                ]
                if refresh
                else planned_weekly_series(
                    root_topic_id=item["root_topic_id"], root_title=item["topic"], week_start=self.week_start
                )
            )
            topic = {
                "root_topic_id": item["root_topic_id"],
                "root_title": item["topic"],
                "title": item["topic"],
                "keyword": item["primary_keyword"],
                "primary_keyword": item["primary_keyword"],
                "slug": item["slug"],
                "parent_slug": item["slug"],
                "search_intent": item["search_intent"],
                "primary_search_intent": item["search_intent"],
                "selection_score": item["opportunity_score"],
                "total_score": item["opportunity_score"],
                "reason_selected": item["why"],
                "content_lane": FOUNDATION_MAIN,
                "selected": True,
                "selected_status": "selected",
                "series_status": "active",
                "rank": rank,
                "topic_tier": item.get("topic_tier"),
                "topic_tier_id": item.get("topic_tier_id"),
                "category": item.get("category"),
                "subcategory": item.get("subcategory"),
                "content_plan": item["weekly_content_plan"],
                "series_plan": series_plan,
                "selection_source": item.get("selection_source", "weekly_content_planning"),
                "fallback_level": int(item.get("fallback_level") or 1),
                "opportunity_type": item.get("opportunity_type", "new_opportunity"),
                "parent_root_id": item.get("parent_root_id"),
                "source_article_slug": item.get("source_article_slug"),
                "proposed_new_intent": item.get("proposed_new_intent"),
                "upgrade_opportunity_score": item.get("upgrade_opportunity_score"),
                "score_breakdown": item.get("score_breakdown"),
                "unique_thesis": item.get("unique_thesis"),
                "refresh_thesis": item.get("refresh_thesis"),
                "update_scope": item.get("update_scope"),
                "existing_slug": item.get("existing_slug"),
                "refresh_reason": item.get("refresh_reason", []),
                "refresh_scope": item.get("refresh_scope", []),
                "preserve_slug": bool(item.get("preserve_slug")),
                "create_new_url": bool(item.get("create_new_url", True)),
                "deep_dive_eligible": bool(item.get("deep_dive_eligible", True)),
                "refresh_existing_article": bool(item.get("refresh_existing_article")),
                "human_approval_required": True,
                "duplicate_risk": item.get("duplicate_risk", "low"),
                "cannibalization_risk": bool(item.get("cannibalization_risk")),
                "source_readiness": item.get("source_readiness", {}),
            }
            topics.append(topic)
        manifest = normalize_weekly_root_manifest(
            {
                "schema_version": "weekly_root_manifest_v1",
                "generated_at": self.now.isoformat(),
                "selected_at": self.now.isoformat(),
                "week_start": self.week_start,
                "planning_week": self.week_start,
                "lock_status": "locked",
                "maximum_root_count": 2,
                "minimum_root_count": 1,
                "partial_week": len(topics) == 1,
                "partial_week_approved_by_operator": len(topics) == 1,
                "approved_by_operator": True,
                "operator_approved_at": self.now.isoformat(),
                "topics": topics,
                "selection_run_id": report["run_id"],
                "approval_scope": "weekly_content_plan_only",
                "root_diversity": diversity,
            },
            week_start=self.week_start,
            selection_source="weekly_topic_selection",
        )
        validation = validate_weekly_root_manifest(manifest, batch_date=self.week_start)
        if not validation.passed or len(manifest["topics"]) not in {1, 2}:
            raise ValueError("Weekly root manifest validation failed: " + "; ".join(validation.blockers))
        manifest_path = self._manifest_path()
        pointer_path = self.root / "data/editorial_queue/current_week.json"
        plan_path = self.root / "data/reports/weekly_plans" / f"{report['run_id']}.json"
        _write_json(manifest_path, manifest)
        _write_json(
            pointer_path,
            {"week_start": self.week_start, "selected_root_count": len(manifest["topics"]), "run_id": report["run_id"]},
        )
        plan = {
            **report,
            "status": "APPROVED_PLAN",
            "selected_weekly_roots": [self._root_summary(row) for row in manifest["topics"]],
            "weekly_root_manifest": str(manifest_path),
            "weekly_roots_changed": True,
            "approved_by_operator": True,
            "root_diversity": diversity,
        }
        _write_json(plan_path, plan)
        return {
            **plan,
            "persistence_status": "SAVED_FOR_WEEK",
            "MENU1_FINAL_STATUS": "SAVED_FOR_WEEK",
            "plan_path": str(plan_path),
            **self._safety(),
        }

    def run(
        self,
        *,
        seeds: list[str] | None = None,
        imports: list[Path] | None = None,
        dry_run: bool = False,
        yes: bool = False,
        selected_indexes: list[int] | None = None,
        confirm: Callable[[str], str] = input,
        edit: Callable[[str], str] = input,
        preview: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        report = self.detect(seeds=seeds, imports=imports)
        if dry_run or report.get("blocked") or report.get("status") == "SKIP":
            return report
        if report.get("status") == "AWAITING_OPERATOR_SELECTION" and len(report.get("candidates") or []) < 2:
            return {
                **report,
                "persistence_status": "AWAITING_OPERATOR_SELECTION",
                "reason": "Fewer than two safe candidates remain after recovery. Add one operator-approved evergreen candidate and rerun Menu 1.",
            }
        if preview is not None:
            preview(report)
        choice = (
            "y"
            if yes
            else confirm("Operator decision [Y] Approve [E] Edit [R] Rescan broader [N] Reject [C] Cancel: ")
            .strip()
            .casefold()
        )
        if choice in {"n", "no"}:
            return {**report, "persistence_status": "CANCELLED", "reason": "Operator selected N; weekly roots were not changed."}
        if choice in {"c", "cancel"}:
            return {**report, "persistence_status": "CANCELLED", "reason": "Operator cancelled; weekly roots were not changed."}
        if choice in {"r", "rescan"}:
            return {
                **report,
                "status": "BROADER_RESCAN_REQUESTED",
                "persistence_status": "BROADER_RESCAN_REQUESTED",
                "reason": "Operator requested a broader controlled-taxonomy rescan. No weekly roots were saved.",
                "weekly_roots_changed": False,
            }
        if choice in {"e", "edit"}:
            raw = edit("Enter one or two candidate indexes, for example 1 or 1,3: ")
            selected_indexes = [int(value.strip()) for value in raw.split(",") if value.strip()]
        elif choice not in {"y", "yes"}:
            return {**report, "persistence_status": "CANCELLED", "reason": "Unknown response; weekly roots were not changed."}
        elif report.get("status") == "AWAITING_OPERATOR_SELECTION" and not selected_indexes:
            return {
                **report,
                "persistence_status": "AWAITING_OPERATOR_SELECTION",
                "reason": "The automatic pair is unsafe. Choose Edit and enter two diverse candidate indexes; nothing was saved.",
            }
        return self.persist(report, selected_indexes)

    def _rank_candidates(self, opportunities: list[dict[str, Any]], pages: list[dict[str, str]], links: list[dict[str, Any]]) -> list[dict[str, Any]]:
        ranked: list[dict[str, Any]] = []
        used_roots = self._used_weekly_root_ids()
        for row in opportunities:
            candidate_root = stable_root_topic_id(str(row.get("slug") or row.get("keyword") or ""))
            if (
                str(row.get("decision") or "") != "create"
                or row.get("slug") in {page["slug"] for page in pages}
                or candidate_root in used_roots
            ):
                continue
            keyword = str(row.get("keyword") or "").strip()
            lowered = keyword.casefold()
            short_lived = any(marker in lowered for marker in ("breaking news", "today's news", "just announced"))
            if short_lived:
                continue
            related = [page for page in pages if _tokens(keyword) & _tokens(page.get("title") or page["slug"])]
            link_count = sum(1 for link in links if row.get("slug") in {link.get("source_slug"), link.get("target_slug"), link.get("target")})
            base = float(row.get("opportunity_score") or 0)
            score = round(max(0, min(100, base + min(8, len(related) * 2) + min(6, link_count) - (25 if short_lived else 0))), 2)
            topic = keyword[:1].upper() + keyword[1:]
            plan = _weekly_plan_angles(topic)
            ranked.append(
                {
                    "topic": topic,
                    "primary_keyword": keyword,
                    "slug": str(row.get("slug") or _slug(keyword)),
                    "root_topic_id": candidate_root,
                    "search_intent": _intent_family(keyword, str(row.get("search_intent") or "commercial research")),
                    "opportunity_score": score,
                    "why": [str(row.get("reason") or "Local content gap detected."), "Supports a multi-angle topical-authority series."],
                    "pillar_article": plan[0]["title"],
                    "supporting_article_ideas": [item["title"] for item in plan[1:]],
                    "weekly_content_plan": plan,
                    "existing_related_content": related[:5],
                    "internal_link_opportunities": max(link_count, len(related)),
                    "duplicate_risk": "low" if not related else "medium - related pages require intent separation",
                    "evergreen": not short_lived,
                }
            )
        return sorted(ranked, key=lambda row: (-row["opportunity_score"], row["slug"]))

    def _expand_candidate_inventory(
        self,
        primary: list[dict[str, Any]],
        *,
        pages: list[dict[str, str]],
        links: list[dict[str, Any]],
        reserve_keywords: list[str],
        analytics_feedback: dict[str, Any],
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """Expand exhausted Menu 1 inventory from existing, operator-controlled data.

        This is recommendation-only.  It never writes a weekly manifest and never
        relaxes duplicate/intent separation; persist() remains the final guard.
        """
        used = self._used_weekly_root_ids()
        page_slugs = {stable_root_topic_id(str(row.get("slug") or "")) for row in pages}
        accepted: list[dict[str, Any]] = []
        rejected_duplicate = 0
        rejected_used = 0
        rejected_low_confidence = 0
        found = len(primary)
        fallback_tier = 1 if primary else 0

        def add(row: dict[str, Any], tier: int) -> None:
            nonlocal rejected_duplicate, rejected_used, rejected_low_confidence, fallback_tier
            root_id = stable_root_topic_id(str(row.get("root_topic_id") or row.get("slug") or row.get("primary_keyword") or ""))
            if not root_id or root_id in used or root_id in page_slugs:
                rejected_used += 1
                return
            if not row.get("evergreen", True) or float(row.get("opportunity_score") or 0) < 40:
                rejected_low_confidence += 1
                return
            if any(
                root_id == str(current.get("root_topic_id") or "")
                or _root_diversity(row, current).get("topic_overlap", 0) >= 0.55
                for current in accepted
            ):
                rejected_duplicate += 1
                return
            row = {**row, "fallback_tier": tier}
            accepted.append(row)
            fallback_tier = max(fallback_tier, tier)

        for row in primary:
            add(row, 1)

        # Tier 2: explicit local reserve/backlog maintained in seo_engine.json.
        for offset, keyword in enumerate(reserve_keywords):
            keyword = str(keyword).strip()
            if not keyword:
                continue
            found += 1
            topic = keyword[:1].upper() + keyword[1:]
            slug = _slug(keyword)
            related = [page for page in pages if _tokens(keyword) & _tokens(page.get("title") or page.get("slug") or "")]
            plan = _weekly_plan_angles(topic)
            add(
                {
                    "topic": topic,
                    "primary_keyword": keyword,
                    "slug": slug,
                    "root_topic_id": stable_root_topic_id(slug),
                    "search_intent": _intent_family(keyword, "commercial research"),
                    "opportunity_score": max(55.0, 72.0 - offset * 0.5),
                    "why": ["Unused operator-configured evergreen backlog candidate.", "Supports a multi-angle topical-authority series."],
                    "pillar_article": plan[0]["title"],
                    "supporting_article_ideas": [item["title"] for item in plan[1:]],
                    "weekly_content_plan": plan,
                    "existing_related_content": related[:5],
                    "internal_link_opportunities": len(related) + sum(1 for link in links if slug in {link.get("source_slug"), link.get("target_slug"), link.get("target")}),
                    "duplicate_risk": "low" if not related else "medium - related pages require intent separation",
                    "evergreen": True,
                },
                2,
            )

        # Tier 3 is limited to analytics candidates explicitly approved by a human.
        for item in analytics_feedback.get("candidates") or []:
            keyword = str(item.get("topic") or item.get("root_topic") or item.get("article_slug") or "").strip()
            if not keyword or str(item.get("status") or "") != "APPROVED_FOR_BACKLOG":
                continue
            found += 1
            topic = keyword[:1].upper() + keyword[1:]
            slug = _slug(keyword)
            plan = _weekly_plan_angles(topic)
            add(
                {
                    "topic": topic,
                    "primary_keyword": keyword,
                    "slug": slug,
                    "root_topic_id": stable_root_topic_id(slug),
                    "search_intent": _intent_family(keyword, "commercial research"),
                    "opportunity_score": max(50.0, min(75.0, float(item.get("confidence") or 0.5) * 100)),
                    "why": ["Human-approved analytics feedback backlog candidate."],
                    "pillar_article": plan[0]["title"],
                    "supporting_article_ideas": [entry["title"] for entry in plan[1:]],
                    "weekly_content_plan": plan,
                    "existing_related_content": [],
                    "internal_link_opportunities": 0,
                    "duplicate_risk": "low",
                    "evergreen": True,
                },
                3,
            )

        accepted.sort(key=lambda row: (-float(row.get("opportunity_score") or 0), int(row.get("fallback_tier") or 9), str(row.get("slug") or "")))
        return accepted, {
            "status": "CANDIDATE_EXPANSION_REQUIRED" if len(primary) < 2 else "PRIMARY_INVENTORY_SUFFICIENT",
            "candidates_found": found,
            "candidates_rejected_duplicate": rejected_duplicate,
            "candidates_rejected_used": rejected_used,
            "candidates_rejected_low_confidence": rejected_low_confidence,
            "candidates_accepted": len(accepted),
            "fallback_tier_used": fallback_tier or 4,
            "operator_selection_required": len(_recommended_pair(accepted)[0]) != 2,
        }

    def _used_weekly_root_ids(self) -> set[str]:
        used: set[str] = set()
        weeks_root = self.root / "data/editorial_queue/weeks"
        if not weeks_root.exists():
            return used
        for path in weeks_root.glob("*/week.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            for row in payload.get("topics") or []:
                if not isinstance(row, dict):
                    continue
                root_id = stable_root_topic_id(
                    str(row.get("root_topic_id") or row.get("slug") or row.get("root_title") or "")
                )
                if root_id:
                    used.add(root_id)
        return used

    def _candidate_source_readiness(self, row: dict[str, Any]) -> dict[str, Any]:
        """Confirm that a weekly root has at least one reusable verified source.

        Menu 1 runs before daily research, so this is a feasibility preflight rather
        than the full research quality gate.  It only trusts local, previously
        verified evidence and never invents or fetches a URL.
        """
        slug = str(row.get("slug") or row.get("root_topic_id") or "").strip()
        topic = str(row.get("topic") or row.get("root_title") or row.get("primary_keyword") or "").strip()
        urls: set[str] = set()

        def collect(value: Any, *, trusted: bool = False) -> None:
            if isinstance(value, str):
                candidate = value.strip()
                if trusted and candidate.startswith(("http://", "https://")):
                    urls.add(candidate)
                return
            if isinstance(value, list):
                for item in value:
                    collect(item, trusted=trusted)
                return
            if not isinstance(value, dict):
                return
            status = str(
                value.get("verification_status") or value.get("source_status") or value.get("status") or ""
            ).casefold()
            approved = trusted or status in {"verified", "approved", "accepted", "pass", "passed"}
            if approved:
                for key in ("source_url", "canonical_url", "url"):
                    candidate = str(value.get(key) or "").strip()
                    if candidate.startswith(("http://", "https://")):
                        urls.add(candidate)
            for key, item in value.items():
                collect(
                    item,
                    trusted=approved or key in {"verified_sources", "approved_sources", "official_sources"},
                )

        collect(row)
        research_dir = self.root / "data/research" / slug
        for filename in ("source_inventory.json", "sources.json", "package.json", "research_quality.json"):
            path = research_dir / filename
            try:
                collect(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                continue

        official = OfficialSourceRegistry(self.root / "data/official_source_registry.json")
        registry_entities = official.load().get("entities") or {}
        exact_keys = {entity_key(slug), entity_key(topic), entity_key(str(row.get("primary_keyword") or ""))}
        for key in exact_keys:
            if key in registry_entities:
                for source in official.sources_for(key):
                    candidate = str(source.get("source_url") or "").strip()
                    if candidate.startswith(("http://", "https://")):
                        urls.add(candidate)

        try:
            registry_rows = json.loads((self.root / "data/source_registry.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            registry_rows = []
        for source in registry_rows if isinstance(registry_rows, list) else []:
            if not isinstance(source, dict):
                continue
            source_keys = {
                entity_key(str(source.get("slug") or "")),
                entity_key(str(source.get("brand") or "")),
            }
            if not exact_keys.intersection(source_keys):
                continue
            collect(source)

        domains = sorted(
            {
                re.sub(r"^www\.", "", re.split(r"/", url.split("://", 1)[-1], maxsplit=1)[0].casefold())
                for url in urls
            }
        )
        passes = bool(domains)
        reason = (
            "PASS"
            if passes
            else f"{slug or topic}: no reusable verified source is mapped locally; use Edit or verify a source before locking this root"
        )
        return {
            "root_topic_id": str(row.get("root_topic_id") or slug),
            "slug": slug,
            "passes": passes,
            "verified_source_count": len(urls),
            "source_family_count": len(domains),
            "source_urls": sorted(urls),
            "source_domains": domains,
            "reason": reason,
        }

    def _current_manifest(self) -> dict[str, Any]:
        path = self._manifest_path()
        if not path.is_file():
            return {}
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        validation = validate_weekly_root_manifest(value, batch_date=self.week_start)
        return value if validation.passed else {}

    def _manifest_path(self) -> Path:
        return self.root / "data/editorial_queue/weeks" / self.week_start / "week.json"

    @staticmethod
    def _root_summary(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "root_topic_id": row.get("root_topic_id"),
            "topic": row.get("root_title") or row.get("topic"),
            "primary_keyword": row.get("primary_keyword") or row.get("keyword"),
            "search_intent": row.get("primary_search_intent") or row.get("search_intent"),
            "opportunity_score": row.get("selection_score") or row.get("opportunity_score"),
            "fallback_level": row.get("fallback_level", 1),
            "opportunity_type": row.get("opportunity_type", "new_opportunity"),
            "source_article_slug": row.get("source_article_slug"),
            "existing_slug": row.get("existing_slug"),
        }

    @staticmethod
    def _safety() -> dict[str, bool]:
        return {"article_created": False, "queue_modified": False, "approval_changed": False, "published": False, "deployed": False, "social_hot_news_created": False}


@dataclass
class WeeklyDeepDiveSelection:
    root: Path
    now: datetime | None = None

    def __post_init__(self) -> None:
        self.root = self.root.resolve()
        self.now = (self.now or datetime.now(UTC)).astimezone(UTC)
        self.operating_date = self.now.astimezone(OPERATING_TIMEZONE).date().isoformat()
        self.week_start = week_start_for(self.operating_date)
        self.source_week = self.week_start
        self.target_week = (date.fromisoformat(self.source_week) + timedelta(days=7)).isoformat()

    def detect(self) -> dict[str, Any]:
        run_id = _run_id("weekly-deep-dive", self.now)
        manifest_path = self.root / "data/editorial_queue/weeks" / self.source_week / "week.json"
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return {"schema_version": "weekly_deep_dive_selection_v1", "run_id": run_id, "timestamp": self.now.isoformat(), "source_week": self.source_week, "target_week": self.target_week, "status": "BLOCKED", "reason": f"Weekly root manifest is missing or invalid: {exc}", "blocked": True, "roots": [], "analytics_feedback": planning_feedback_advisory(self.root, now=self.now), **WeeklyTopicSelection._safety()}
        validation = validate_weekly_root_manifest(manifest, batch_date=self.week_start)
        roots = list(manifest.get("topics") or [])
        if not validation.passed or len(roots) not in {1, 2}:
            return {"schema_version": "weekly_deep_dive_selection_v1", "run_id": run_id, "timestamp": self.now.isoformat(), "source_week": self.source_week, "target_week": self.target_week, "status": "BLOCKED", "reason": "One or two valid locked weekly roots are required.", "blocked": True, "roots": [], "analytics_feedback": planning_feedback_advisory(self.root, now=self.now), **WeeklyTopicSelection._safety()}
        refresh_roots = [row for row in roots if row.get("deep_dive_eligible") is False]
        roots = [row for row in roots if row.get("deep_dive_eligible") is not False]
        if not roots:
            return {
                "schema_version": "weekly_deep_dive_selection_v1",
                "run_id": run_id,
                "timestamp": self.now.isoformat(),
                "week_start": self.source_week,
                "source_week": self.source_week,
                "target_week": self.target_week,
                "plan_semantics": "backlog_for_target_week",
                "status": "NO_DEEP_DIVE_REQUIRED",
                "reason": "The approved weekly selection contains refresh-only work; no synthetic deep-dive tree was created.",
                "blocked": False,
                "roots": [],
                "refresh_roots": refresh_roots,
                "priority_recommendation": [],
                "weekly_roots_changed": False,
                **WeeklyTopicSelection._safety(),
            }
        calibration_preflight = WeeklyCalibrationPreflight(root=self.root, now=self.now).detect()
        if calibration_preflight.get("blocked"):
            return {
                "schema_version": "weekly_deep_dive_selection_v1",
                "run_id": run_id,
                "timestamp": self.now.isoformat(),
                "source_week": self.source_week,
                "target_week": self.target_week,
                "status": "BLOCKED",
                "reason": calibration_preflight.get("reason") or "Weekly calibration is blocked.",
                "blocked": True,
                "roots": [],
                "calibration_preflight": calibration_preflight,
                "analytics_feedback": planning_feedback_advisory(
                    self.root,
                    root_topics=[str(row.get("root_title") or row.get("title") or "") for row in roots],
                    now=self.now,
                ),
                **WeeklyTopicSelection._safety(),
            }
        calibration = calibration_preflight.get("calibration") or {}
        performance = self._performance_signals()
        existing = self._existing_slugs()
        root_groups = []
        for root in roots:
            root_id = str(root.get("root_topic_id") or "")
            root_title = str(root.get("root_title") or root.get("title") or "")
            gaps = [row for row in calibration.get("content_gaps", {}).get("items", []) if root_id and root_id in json.dumps(row, ensure_ascii=False)]
            suggestions = self._deep_dive_candidates(root_title, root_id, existing, gaps, performance)[:5]
            if feature_enabled(self.root, "editorial_memory.enabled"):
                try:
                    memory = EditorialMemoryStore(root=self.root)
                    for suggestion in suggestions:
                        suggestion["editorial_memory"] = memory.detect_duplicates(
                            {
                                "slug": suggestion.get("slug"),
                                "title": suggestion.get("title") or suggestion.get("topic"),
                                "root_topic": root_id,
                                "angle": suggestion.get("angle"),
                                "keyword": suggestion.get("primary_keyword") or suggestion.get("keyword"),
                            }
                        )
                except (OSError, ValueError, sqlite3.Error):
                    pass
            root_groups.append({"root_topic_id": root_id, "root_title": root_title, "topics": suggestions})
        priorities = sorted([topic for group in root_groups for topic in group["topics"]], key=lambda row: (-row["priority_score"], row["slug"]))[:2]
        return {
            "schema_version": "weekly_deep_dive_selection_v1",
            "run_id": run_id,
            "timestamp": self.now.isoformat(),
            "week_start": self.source_week,
            "source_week": self.source_week,
            "target_week": self.target_week,
            "plan_semantics": "backlog_for_target_week",
            "status": "REVIEW",
            "reason": f"Review deep-dive recommendations constrained to the {len(roots)} approved weekly root(s).",
            "blocked": False,
            "root_manifest": str(manifest_path),
            "root_count": len(roots),
            "partial_week": len(roots) == 1,
            "roots": root_groups,
            "refresh_roots": refresh_roots,
            "priority_recommendation": priorities,
            "review_steps": {
                **calibration_preflight.get("sections", {}),
                "performance": {
                    "status": "REVIEW" if performance else "SKIP",
                    "reason": "Offline performance signals were included in scoring." if performance else "No optional offline performance export was found; no paid API was called.",
                    "count": len(performance),
                },
                "recommendation": {
                    "status": "REVIEW",
                    "reason": "Operator confirmation is required before the deep-dive plan is saved.",
                    "count": sum(len(group["topics"]) for group in root_groups),
                },
            },
            "calibration_summary": {
                "alias_conflicts": calibration.get("alias_review_queue", {}).get("count", 0),
                "orphans": calibration.get("orphans", {}).get("production_true_orphan_unique_count", 0),
                "quality_high": calibration.get("quality", {}).get("after", {}).get("HIGH_PRIORITY", 0),
                "strong_gaps": calibration.get("content_gaps", {}).get("counts", {}).get("STRONG_GAP", 0),
            },
            "performance_signal_count": len(performance),
            "weekly_roots_changed": False,
            "analytics_feedback": planning_feedback_advisory(
                self.root,
                root_topics=[str(row.get("root_title") or row.get("title") or "") for row in roots],
                now=self.now,
            ),
            **WeeklyTopicSelection._safety(),
        }

    def persist(
        self,
        report: dict[str, Any],
        selected: dict[str, list[int]] | None = None,
        *,
        existing_action: str | None = None,
    ) -> dict[str, Any]:
        if report.get("source_week") != self.source_week or report.get("target_week") != self.target_week:
            raise ValueError("Deep-dive plan week assignment does not match the workflow source/target weeks.")
        selected = selected or self._recommended_selection(report)
        approved = []
        for group in report["roots"]:
            indexes = selected.get(group["root_topic_id"], [])
            if len(indexes) > 5:
                raise ValueError("At most five deep-dive topics may be selected per root.")
            for index in indexes:
                approved.append({**group["topics"][index - 1], "source_week": self.source_week, "target_week": self.target_week})
        approved_root_ids = {group["root_topic_id"] for group in report["roots"]}
        if len(approved_root_ids) not in {1, 2} or any(topic["root_topic_id"] not in approved_root_ids for topic in approved):
            raise ValueError("Deep-dive plan contains a topic outside the two approved weekly roots (or the one approved partial-week root).")
        canonical_path = self.root / "data/editorial_queue/weeks" / self.source_week / "deep_dive_plan.json"
        existing = self._read_existing_plan(canonical_path)
        same_plan = existing and self._topic_signature(existing.get("topics") or []) == self._topic_signature(approved)
        if existing and not same_plan:
            action = str(existing_action or "").strip().casefold()
            if action not in {"replace", "merge", "cancel"}:
                return {
                    **report,
                    "status": "AWAITING_PLAN_CONFLICT_DECISION",
                    "persistence_status": "AWAITING_PLAN_CONFLICT_DECISION",
                    "reason": "A different target-week backlog exists; choose Replace, Merge, or Cancel.",
                    "blocked": False,
                    "plan_changed": False,
                    "existing_plan_diff": self._plan_diff(existing.get("topics") or [], approved),
                }
            if action == "cancel":
                return {
                    **report,
                    "status": "CANCELLED_BY_OPERATOR",
                    "persistence_status": "CANCELLED_BY_OPERATOR",
                    "reason": "Operator kept the existing target-week backlog unchanged.",
                    "plan_changed": False,
                }
            if action == "merge":
                approved = self._merge_topics(existing.get("topics") or [], approved, approved_root_ids)
        plan = {
            **report,
            "status": "SAVED_FOR_TARGET_WEEK",
            "persistence_status": "SAVED_FOR_TARGET_WEEK",
            "approved_topics": approved,
            "approved_by_operator": True,
            "operator_actor": "operator",
            "operator_confirmed_at": self.now.isoformat(),
            "weekly_roots_changed": False,
        }
        report_path = self.root / "data/reports/weekly_plans" / f"{report['run_id']}.json"
        canonical = {
            "schema_version": "weekly_deep_dive_plan_v1",
            "run_id": report["run_id"],
            "timestamp": report["timestamp"],
            "status": "SAVED_FOR_TARGET_WEEK",
            "approved_at": self.now.isoformat(),
            "approved_by": "operator",
            "source_week": self.source_week,
            "target_week": self.target_week,
            "plan_semantics": "backlog_for_target_week",
            "approved_root_ids": sorted(approved_root_ids),
            "root_count": len(approved_root_ids),
            "partial_week": len(approved_root_ids) == 1,
            "topics": approved,
            **WeeklyTopicSelection._safety(),
        }
        if same_plan:
            return {
                **plan,
                "reason": "The same operator-approved backlog already exists; no duplicate was written.",
                "persistence_idempotent": True,
                "plan_path": str(report_path),
                "deep_dive_plan_path": str(canonical_path),
            }
        _write_json(report_path, plan)
        _write_json(canonical_path, canonical)
        self._append_audit_event(canonical_path, approved)
        return {**plan, "plan_path": str(report_path), "deep_dive_plan_path": str(canonical_path)}

    def run(
        self,
        *,
        dry_run: bool = False,
        yes: bool = False,
        confirm: Callable[[str], str] = input,
        edit: Callable[[str], str] = input,
        interactive: bool = True,
        max_attempts: int = 3,
    ) -> dict[str, Any]:
        report = self.detect()
        if dry_run or report.get("blocked"):
            return report
        return self.review(
            report,
            decision="Y" if yes else None,
            confirm=confirm,
            edit=edit,
            interactive=interactive or yes,
            max_attempts=max_attempts,
        )

    def review(
        self,
        report: dict[str, Any],
        *,
        decision: str | None = None,
        confirm: Callable[[str], str] = input,
        edit: Callable[[str], str] = input,
        interactive: bool = True,
        max_attempts: int = 3,
    ) -> dict[str, Any]:
        if report.get("blocked"):
            return report
        if not interactive and decision is None:
            return {
                **report,
                "status": "AWAITING_OPERATOR_REVIEW",
                "persistence_status": "AWAITING_OPERATOR_REVIEW",
                "reason": "A valid recommendation is waiting for an operator decision.",
                "blocked": False,
                "plan_changed": False,
                "rerun_command": f"python weekly_planning_console.py deep-dive-selection --date {self.source_week} --decision Y",
            }

        choice = self._prompt_choice(decision, confirm, max_attempts=max_attempts)
        if choice is None:
            return {
                **report,
                "status": "CANCELLED_INVALID_INPUT",
                "persistence_status": "CANCELLED_INVALID_INPUT",
                "reason": "Invalid input limit reached; deep-dive plan was not changed.",
                "blocked": False,
                "plan_changed": False,
            }
        if choice in {"n", "no"}:
            return {
                **report,
                "status": "DECLINED_BY_OPERATOR",
                "persistence_status": "DECLINED_BY_OPERATOR",
                "reason": "Operator declined the recommendation; deep-dive plan was not changed.",
                "plan_changed": False,
            }
        if choice in {"c", "q"}:
            return {
                **report,
                "status": "CANCELLED_BY_OPERATOR",
                "persistence_status": "CANCELLED_BY_OPERATOR",
                "reason": "Operator cancelled the review; deep-dive plan was not changed.",
                "plan_changed": False,
            }

        selected = None
        if choice in {"e", "edit"}:
            selected = self._edit_selection(report, edit)
            final_choice = self._prompt_choice(
                None,
                confirm,
                max_attempts=max_attempts,
                prompt="Confirm the final edited list? [Y/N]: ",
                allow_edit=False,
            )
            if final_choice not in {"y", "yes"}:
                status = "DECLINED_BY_OPERATOR" if final_choice in {"n", "no"} else "CANCELLED_INVALID_INPUT"
                return {
                    **report,
                    "status": status,
                    "persistence_status": status,
                    "reason": "The edited list was not confirmed; deep-dive plan was not changed.",
                    "selected_topics": self._selected_topics(report, selected),
                    "plan_changed": False,
                }
        result = self.persist(report, selected)
        if result.get("status") == "AWAITING_PLAN_CONFLICT_DECISION":
            action = str(confirm("A different plan exists. Choose Replace, Merge, or Cancel: ")).strip().casefold()
            if action not in {"replace", "merge", "cancel"}:
                return {
                    **result,
                    "status": "CANCELLED_INVALID_INPUT",
                    "persistence_status": "CANCELLED_INVALID_INPUT",
                    "reason": "Invalid conflict decision; existing plan was not changed.",
                }
            return self.persist(report, selected, existing_action=action)
        return result

    @staticmethod
    def _prompt_choice(
        initial: str | None,
        reader: Callable[[str], str],
        *,
        max_attempts: int,
        prompt: str = "Approve these deep-dive topics for the next week? [Y/N/Edit]: ",
        allow_edit: bool = True,
    ) -> str | None:
        allowed = {"y", "yes", "n", "no", "c", "q"} | ({"e", "edit"} if allow_edit else set())
        value = initial
        for _ in range(max(1, max_attempts)):
            normalized = str(value if value is not None else reader(prompt)).strip().casefold()
            if normalized in allowed:
                return normalized
            print("Invalid choice. Enter Y, N, or Edit.")
            value = None
        return None

    def _edit_selection(self, report: dict[str, Any], reader: Callable[[str], str]) -> dict[str, list[int]]:
        selected: dict[str, list[int]] = {}
        for group in report["roots"]:
            raw = reader(f"Select topic numbers for {group['root_title']} (comma-separated, blank for none): ")
            try:
                indexes = [int(value.strip()) for value in raw.split(",") if value.strip()]
            except ValueError as exc:
                raise ValueError("Edited topic indexes must be comma-separated integers.") from exc
            if len(indexes) > 5 or any(index < 1 or index > len(group["topics"]) for index in indexes):
                raise ValueError("Edited topic selection is outside the available candidate list.")
            selected[group["root_topic_id"]] = list(dict.fromkeys(indexes))
        return selected

    @staticmethod
    def _selected_topics(report: dict[str, Any], selected: dict[str, list[int]]) -> list[dict[str, Any]]:
        return [
            group["topics"][index - 1]
            for group in report["roots"]
            for index in selected.get(group["root_topic_id"], [])
        ]

    @staticmethod
    def _recommended_selection(report: dict[str, Any]) -> dict[str, list[int]]:
        recommended = {str(row.get("slug")) for row in report.get("priority_recommendation") or []}
        return {
            group["root_topic_id"]: [
                index for index, topic in enumerate(group["topics"], start=1) if str(topic.get("slug")) in recommended
            ]
            for group in report["roots"]
        }

    @staticmethod
    def _read_existing_plan(path: Path) -> dict[str, Any]:
        if not path.is_file():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    @staticmethod
    def _topic_signature(topics: Iterable[dict[str, Any]]) -> tuple[tuple[str, str], ...]:
        return tuple(sorted((str(row.get("root_topic_id")), str(row.get("slug"))) for row in topics))

    def _append_audit_event(self, plan_path: Path, topics: list[dict[str, Any]]) -> None:
        audit_path = self.root / "data/audit/weekly_deep_dive_events.jsonl"
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        event = {
            "event": "weekly_deep_dive_saved",
            "actor": "operator",
            "timestamp": self.now.isoformat(),
            "source_week": self.source_week,
            "target_week": self.target_week,
            "plan_path": str(plan_path),
            "topic_signature": self._topic_signature(topics),
        }
        with audit_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")

    @classmethod
    def _plan_diff(cls, existing: Iterable[dict[str, Any]], proposed: Iterable[dict[str, Any]]) -> dict[str, list[tuple[str, str]]]:
        old = set(cls._topic_signature(existing))
        new = set(cls._topic_signature(proposed))
        return {"added": sorted(new - old), "removed": sorted(old - new)}

    @classmethod
    def _merge_topics(
        cls,
        existing: Iterable[dict[str, Any]],
        proposed: Iterable[dict[str, Any]],
        approved_root_ids: set[str],
    ) -> list[dict[str, Any]]:
        merged: dict[tuple[str, str], dict[str, Any]] = {}
        for row in [*existing, *proposed]:
            root_id = str(row.get("root_topic_id"))
            if root_id not in approved_root_ids:
                raise ValueError("Existing deep-dive plan contains a topic outside the two approved weekly roots.")
            merged[(root_id, str(row.get("slug")))] = dict(row)
        return list(merged.values())

    def _deep_dive_candidates(self, root_title: str, root_id: str, existing: set[str], gaps: list[dict[str, Any]], performance: dict[str, float]) -> list[dict[str, Any]]:
        angles = [
            ("comparison", "Comparison and Alternatives", "comparison", "commercial investigation"),
            ("pricing", "Pricing, Cost, and ROI", "pricing", "commercial investigation"),
            ("security", "Security, Privacy, and Compliance", "security", "informational"),
            ("integrations", "Integrations and Implementation", "implementation_guide", "implementation guide"),
            ("case-study", "Small-Business Case Study", "case_study", "informational"),
            ("pros-cons", "Pros, Cons, and Limitations", "review", "commercial research"),
            ("faq", "Advanced FAQ and Decision Guide", "faq", "informational"),
        ]
        rows = []
        root_signal = max([score for slug, score in performance.items() if root_id in slug] or [0.0])
        for position, (angle, suffix, article_type, intent) in enumerate(angles):
            title = f"{root_title}: {suffix}"
            slug = _slug(f"{root_id}-{angle}")
            duplicate = slug in existing
            score = round(max(0, min(100, 86 - position * 3 + min(8, len(gaps) * 2) + min(6, root_signal) - (45 if duplicate else 0))), 2)
            rows.append({
                "root_topic_id": root_id,
                "root_title": root_title,
                "title": title,
                "slug": slug,
                "primary_keyword": f"{root_title} {suffix}".casefold(),
                "search_intent": intent,
                "why": "Fills a same-root depth gap and strengthens bidirectional internal linking.",
                "gap_filled": str(gaps[0].get("reason") or gaps[0].get("classification") or "same-root topical depth") if gaps else "same-root topical depth",
                "links_to": f"/{root_id}/",
                "receives_links_from": f"/{root_id}/ and same-root supporting articles",
                "priority": "HIGH" if score >= 80 else "MEDIUM",
                "priority_score": score,
                "confidence": "high" if not duplicate and score >= 75 else "medium",
                "duplicate_risk": "high - existing slug" if duplicate else "low",
                "suggested_article_type": article_type,
                "performance_signal": root_signal,
            })
        return sorted((row for row in rows if row["duplicate_risk"] != "high - existing slug"), key=lambda row: (-row["priority_score"], row["slug"]))

    def _existing_slugs(self) -> set[str]:
        return {path.parent.name for base in (self.root / "docs", self.root / "data/production_article_drafts") if base.exists() for path in base.glob("*/index.html")}

    def _performance_signals(self) -> dict[str, float]:
        scores: dict[str, float] = {}
        for base in (self.root / "data/performance", self.root / "data/performance_exports", self.root / "data/analytics"):
            if not base.exists():
                continue
            for path in base.glob("*.csv"):
                try:
                    with path.open("r", encoding="utf-8-sig", newline="") as handle:
                        for row in csv.DictReader(handle):
                            slug = str(row.get("slug") or row.get("page") or row.get("url") or "")
                            value = sum(float(row.get(key) or 0) for key in ("impressions", "clicks", "engagement", "quora_views"))
                            scores[_slug(slug)] = max(scores.get(_slug(slug), 0), value)
                except (OSError, ValueError):
                    continue
        return scores


def render_topic_selection(report: dict[str, Any]) -> str:
    lines = ["WEEKLY CONTENT OPPORTUNITIES", ""]
    for index, row in enumerate(report.get("candidates") or [], start=1):
        readiness = row.get("source_readiness") or {}
        opportunity_type = str(row.get("opportunity_type") or "new_opportunity")
        parent = row.get("source_article_slug") or row.get("parent_root_id") or "new root"
        why = list(row.get("why") or [])
        lines.extend(
            [
                f"{index}. {row['topic']}",
                f"   Type: {opportunity_type.upper()}",
                f"   Level: {row.get('fallback_level', 1)}",
                f"   Score: {row.get('upgrade_opportunity_score') or row.get('opportunity_score')}",
                f"   Root/source article: {parent}",
                f"   Main reason: {why[0] if why else 'quality opportunity'}",
                f"   Duplicate risk: {row.get('duplicate_risk', 'unknown')}",
                f"   Research: {'READY' if readiness.get('passes') else 'RESEARCH_REQUIRED'}",
                "   Recommendation: REVIEW WITH OPERATOR",
            ]
        )
        if opportunity_type == "content_refresh":
            lines.extend(
                [
                    "   THIS WILL UPDATE AN EXISTING ARTICLE",
                    "   NO NEW URL WILL BE CREATED",
                ]
            )
        lines.append("")
    lines.append("RECOMMENDED WEEKLY ROOTS:")
    recommended_indexes = report.get("recommended_candidate_indexes") or []
    for index, row in enumerate(report.get("recommended_weekly_roots") or [], start=1):
        candidate_number = recommended_indexes[index - 1] if index <= len(recommended_indexes) else None
        suffix = f" (Candidate {candidate_number})" if candidate_number else " (already locked)"
        lines.append(f"{index}. {row.get('topic')}{suffix}")
    diversity = report.get("root_diversity") or {}
    if diversity:
        lines.append(f"Root diversity score: {diversity.get('root_diversity_score')}")
        if diversity.get("conflict_warnings"):
            lines.append(f"Conflict warning: {'; '.join(diversity['conflict_warnings'])}")
    inventory = report.get("candidate_inventory") or {}
    if inventory:
        lines.append(
            "Candidate inventory: "
            f"configured={inventory.get('configured', 0)} | "
            f"eligible_unused={inventory.get('eligible', 0)} | "
            f"displayed={inventory.get('displayed', 0)} | "
            f"minimum_required={inventory.get('minimum_required', 2)}"
        )
        if inventory.get("reserve_warning"):
            lines.append(
                "Reserve warning: fewer than four unused eligible roots remain; replenish "
                "evergreen_root_reserve_keywords before the next weekly cycle."
            )
    recovery = report.get("candidate_recovery") or {}
    if recovery:
        lines.append(f"Fallback used: LEVEL {report.get('fallback_level') or recovery.get('fallback_level_used', 1)}")
        for row in recovery.get("source_unready_candidates") or []:
            lines.append(f"Source preflight hold: {row.get('topic')} - {row.get('reason')}")
    fallback = report.get("content_opportunity_fallback") or recovery.get("content_opportunity_fallback") or {}
    if fallback:
        lines.extend(
            [
                f"NEW_ROOT_CANDIDATES: {fallback.get('NEW_ROOT_CANDIDATES', 0)}",
                f"NEW_ROOT_PASSED: {fallback.get('NEW_ROOT_PASSED', 0)}",
                f"LEVEL2_CANDIDATES: {fallback.get('LEVEL2_CANDIDATES', 0)}",
                f"LEVEL2_PASSED: {fallback.get('LEVEL2_PASSED', 0)}",
                f"LEVEL3_CANDIDATES: {fallback.get('LEVEL3_CANDIDATES', 0)}",
                f"LEVEL3_PASSED: {fallback.get('LEVEL3_PASSED', 0)}",
                f"SAFE_WEEKLY_ROOTS: {fallback.get('SAFE_WEEKLY_ROOTS', len(report.get('candidates') or []))}",
            ]
        )
        rejected = list(fallback.get("rejected_candidates") or [])
        if rejected and int(fallback.get("SAFE_WEEKLY_ROOTS") or 0) == 0:
            lines.append("REJECTED FALLBACK CANDIDATES:")
            for row in rejected:
                lines.append(
                    "- "
                    f"candidate={row.get('candidate')} | level={row.get('level')} | "
                    f"root/topic={row.get('root_topic')} | intent={row.get('intent')} | "
                    f"novelty_score={row.get('novelty_score')} | overlap_score={row.get('overlap_score')} | "
                    f"research_status={row.get('research_status')} | rejection_stage={row.get('rejection_stage')} | "
                    f"rejection_reason={row.get('rejection_reason')} | "
                    f"required_operator_action={row.get('required_operator_action')}"
                )
        elif rejected:
            lines.append(
                f"Rejected fallback candidates: {len(rejected)} (safe candidates are available; use the full diagnostics command for the candidate-level audit)."
            )
    for warning in report.get("source_preflight_warnings") or []:
        lines.append(f"Source preflight warning: {warning}")
    feedback = report.get("analytics_feedback") or {}
    if feedback.get("enabled"):
        lines.append(
            f"Analytics advisory: {feedback.get('count', 0)} human-approved feedback candidate(s); "
            f"expired excluded={feedback.get('expired_count', 0)}. Weekly roots were not changed."
        )
    lines.append(f"Status: {report.get('status')} - {report.get('reason')}")
    if report.get("status") not in {"SKIP", "BLOCKED"}:
        lines.append("Operator decision: [Y] Approve  [E] Edit  [R] Rescan broader categories  [N] Reject  [C] Cancel")
    lines.append("Full diagnostics: python weekly_planning_console.py topic-selection --dry-run --json")
    return "\n".join(lines)


def render_deep_dive(report: dict[str, Any]) -> str:
    lines = [
        "WEEKLY DEEP-DIVE REVIEW",
        "",
        f"Source week: {report.get('source_week')}",
        f"Target week: {report.get('target_week')}",
        f"Plan semantics: {report.get('plan_semantics')}",
        "",
        "LOCKED WEEKLY ROOTS:",
    ]
    for index, group in enumerate(report.get("roots") or [], start=1):
        lines.append(f"{index}. {group['root_title']} ({group['root_topic_id']})")
    for row in report.get("refresh_roots") or []:
        lines.append(
            f"- Refresh-only: {row.get('root_title') or row.get('title')} "
            f"({row.get('existing_slug') or row.get('slug')}) - no deep-dive tree"
        )
    lines.extend(["", "PRIORITY RECOMMENDATION:"])
    for index, row in enumerate(report.get("priority_recommendation") or [], start=1):
        lines.extend(
            [
                f"{index}. {row['title']} ({row['root_title']})",
                f"   priority={row['priority']} | confidence={row['confidence']} | duplicate={row['duplicate_risk']}",
            ]
        )
    warnings = [
        str(row.get("reason"))
        for row in (report.get("analytics_feedback") or {}).get("candidates") or []
        if any(str(group.get("root_topic_id")) in json.dumps(row, ensure_ascii=False) for group in report.get("roots") or [])
    ]
    if warnings:
        lines.extend(["", "DIRECT WARNINGS:", *[f"- {warning}" for warning in warnings[:5]]])
    lines.extend(
        [
            "",
            "Candidate templates are a pool, not a required article list.",
            "View full read-only details: python weekly_planning_console.py deep-dive-selection --dry-run --json",
        ]
    )
    lines.append(f"Status: {report.get('status')} - {report.get('reason')}")
    return "\n".join(lines)
