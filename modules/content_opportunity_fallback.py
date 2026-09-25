from __future__ import annotations

import json
import csv
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse

from modules.editorial_topic_strategy import EditorialTopicStrategy


SCHEMA_VERSION = "content_opportunity_fallback_v1"
INVENTORY_SCHEMA_VERSION = "existing_content_inventory_v1"
DEFAULT_MINIMUM_SCORE = 55.0

ANGLE_DEFINITIONS = (
    ("pricing", "Pricing, Cost, and ROI", "commercial investigation"),
    ("comparison", "Comparison and Alternatives", "comparison"),
    ("security", "Security and Privacy", "security research"),
    ("integrations", "Integrations Guide", "implementation guide"),
    ("workflows", "Automation Workflows", "implementation guide"),
    ("small-business", "for Small Business", "commercial research"),
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")[:120]


def _tokens(value: str) -> set[str]:
    ignored = {"the", "and", "for", "with", "best", "review", "guide", "2026"}
    return {
        token
        for token in re.findall(r"[a-z0-9]+", value.casefold())
        if len(token) > 2 and token not in ignored
    }


def _intent(value: str) -> str:
    lowered = value.casefold()
    if any(marker in f" {lowered} " for marker in (" vs ", " comparison ", " alternatives ")):
        return "comparison"
    if any(marker in lowered for marker in ("pricing", "price", "cost", "roi")):
        return "commercial investigation"
    if any(marker in lowered for marker in ("security", "privacy", "compliance")):
        return "security research"
    if any(marker in lowered for marker in ("how to", "workflow", "integration", "implementation")):
        return "implementation guide"
    return "commercial research"


def _overlap(left: str, right: str) -> float:
    left_tokens, right_tokens = _tokens(left), _tokens(right)
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / max(1, min(len(left_tokens), len(right_tokens)))


def _title_similarity(left: str, right: str) -> float:
    left_tokens, right_tokens = _tokens(left), _tokens(right)
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / max(1, len(left_tokens | right_tokens))


def _title_similarity_tokens(left_tokens: set[str], right_tokens: set[str]) -> float:
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / max(1, len(left_tokens | right_tokens))


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _rows(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [dict(row) for row in value if isinstance(row, dict)]
    if not isinstance(value, dict):
        return []
    for key in ("articles", "items", "pages", "content", "records", "opportunities", "claims"):
        if isinstance(value.get(key), list):
            return [dict(row) for row in value[key] if isinstance(row, dict)]
    return []


def _http_urls(value: Any, *, trusted: bool = False) -> set[str]:
    urls: set[str] = set()
    if isinstance(value, str):
        if trusted and value.startswith(("http://", "https://")):
            urls.add(value.strip())
        return urls
    if isinstance(value, list):
        for item in value:
            urls.update(_http_urls(item, trusted=trusted))
        return urls
    if not isinstance(value, dict):
        return urls
    status = _text(
        value.get("verification_status")
        or value.get("source_status")
        or value.get("status")
    ).casefold()
    approved = trusted or status in {
        "verified", "approved", "accepted", "pass", "passed",
        "verified_official", "verified_multisource", "verified_local_production",
    }
    for key, item in value.items():
        child_trusted = approved or key in {
            "verified_sources", "approved_sources", "official_sources",
        }
        if key in {"url", "source_url", "canonical_url"} and isinstance(item, str):
            if child_trusted and item.startswith(("http://", "https://")):
                urls.add(item.strip())
        else:
            urls.update(_http_urls(item, trusted=child_trusted))
    return urls


def _source_readiness(urls: Iterable[str]) -> dict[str, Any]:
    values = sorted({value for value in urls if value.startswith(("http://", "https://"))})
    domains = sorted({urlparse(value).netloc.casefold().removeprefix("www.") for value in values})
    return {
        "passes": bool(values),
        "verified_source_count": len(values),
        "source_family_count": len(domains),
        "source_urls": values,
        "source_domains": domains,
        "reason": "PASS" if values else "RESEARCH_REQUIRED: no reusable verified source is mapped locally",
    }


@dataclass
class ExistingContentInventory:
    root: Path
    now: datetime | None = None

    def __post_init__(self) -> None:
        self.root = self.root.resolve()
        self.now = (self.now or datetime.now(UTC)).astimezone(UTC)

    def scan(self) -> dict[str, Any]:
        """Read canonical local stores; never fetch or infer remote facts."""
        collected: dict[str, dict[str, Any]] = {}
        inputs: list[str] = []
        registries = (
            self.root / "data/published_articles.json",
            self.root / "data/published_article_registry.json",
            self.root / "data/article_registry.json",
            self.root / "data/content_registry.json",
        )
        for path in registries:
            if not path.is_file():
                continue
            inputs.append(path.relative_to(self.root).as_posix())
            for row in _rows(_read_json(path, [])):
                self._merge(collected, row, source=path)

        production = self.root / "data/production_article_drafts"
        if production.is_dir():
            inputs.append("data/production_article_drafts/*/metadata.json")
            for path in sorted(production.glob("*/metadata.json")):
                row = _read_json(path, {})
                if not isinstance(row, dict):
                    continue
                slug = path.parent.name
                status = _text(
                    row.get("status")
                    or row.get("editorial_status")
                    or (row.get("publish_gate") or {}).get("status")
                ).casefold()
                live_exists = any(
                    (base / slug / "index.html").is_file()
                    for base in (self.root / "docs", self.root / "site_output")
                )
                if status not in {"published", "published_local", "ready_for_publish"} and not live_exists:
                    continue
                self._merge(collected, {**row, "slug": slug}, source=path)

        for base in (self.root / "docs", self.root / "site_output"):
            if not base.is_dir():
                continue
            inputs.append(f"{base.name}/**/index.html")
            for path in sorted(base.glob("*/index.html")):
                if path.parent.name in {"review", "actions", "assets"}:
                    continue
                html = path.read_text(encoding="utf-8", errors="ignore")
                match = re.search(r"(?is)<title[^>]*>(.*?)</title>", html)
                self._merge(
                    collected,
                    {
                        "slug": path.parent.name,
                        "title": re.sub(r"<[^>]+>", " ", match.group(1)).strip() if match else path.parent.name,
                        "status": "published",
                    },
                    source=path,
                )

        partner_rows = self._partner_rows()
        performance = self._performance_rows()
        link_counts = self._internal_link_counts()
        planned = self._planned_identities()
        memory_slugs = self._editorial_memory_slugs()
        strategy = EditorialTopicStrategy(self.root)
        inventory: list[dict[str, Any]] = []
        for slug, row in sorted(collected.items()):
            verified = set(row.get("verified_source_urls") or [])
            verified.update(self._research_sources(slug))
            knowledge = self._knowledge_signals(slug)
            verified.update(knowledge["verified_source_urls"])
            partner_matches = self._partner_matches(row, partner_rows)
            performance_row = performance.get(slug, {})
            title = _text(row.get("title") or row.get("name") or slug.replace("-", " ").title())
            classification = strategy.classify(title)
            inventory.append(
                {
                    **row,
                    "slug": slug,
                    "root_topic_id": _text(row.get("root_topic_id") or slug),
                    "title": title,
                    "search_intent": _text(row.get("search_intent") or _intent(_text(row.get("title") or slug))),
                    "verified_source_urls": sorted(verified),
                    "source_readiness": _source_readiness(verified),
                    "partner_signal_matches": partner_matches,
                    "commercially_relevant": classification.allowed,
                    "topic_tier": classification.tier,
                    "topic_tier_id": classification.tier_id,
                    "category": classification.category,
                    "subcategory": classification.subcategory,
                    "performance": performance_row,
                    "internal_link_count": link_counts.get(slug, 0),
                    "entity_coverage_score": knowledge["entity_coverage_score"],
                    "knowledge_claim_count": knowledge["claim_count"],
                    "editorial_memory_match": slug in memory_slugs,
                    "already_planned": slug in planned,
                }
            )
        return {
            "schema_version": INVENTORY_SCHEMA_VERSION,
            "generated_at": self.now.isoformat(),
            "canonical_inputs": sorted(set(inputs)),
            "article_count": len(inventory),
            "articles": inventory,
            "partner_signal_count": len(partner_rows),
            "analytics_available": bool(performance),
            "network_used": False,
        }

    def _merge(self, target: dict[str, dict[str, Any]], row: dict[str, Any], *, source: Path) -> None:
        identity = _text(row.get("slug") or row.get("article_slug") or row.get("path") or row.get("url"))
        if identity.startswith(("http://", "https://")):
            identity = urlparse(identity).path.strip("/").rsplit("/", 1)[-1]
        slug = _slug(identity)
        if not slug:
            return
        current = target.setdefault(slug, {"inventory_sources": []})
        current.update({key: value for key, value in row.items() if value not in (None, "", [], {})})
        current["inventory_sources"] = sorted(
            set([*current.get("inventory_sources", []), source.relative_to(self.root).as_posix()])
        )
        verified = set(current.get("verified_source_urls") or [])
        verified.update(_http_urls(row))
        current["verified_source_urls"] = sorted(verified)

    def _research_sources(self, slug: str) -> set[str]:
        urls: set[str] = set()
        base = self.root / "data/research" / slug
        for name in ("source_inventory.json", "sources.json", "research_quality.json", "package.json"):
            value = _read_json(base / name, {})
            urls.update(_http_urls(value))
        return urls

    def _partner_rows(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for path in (
            self.root / "data/partner_opportunities.json",
            self.root / "data/partnerstack_opportunities.json",
            self.root / "data/partnerstack_registry.json",
            self.root / "config/partner_opportunities.json",
        ):
            rows.extend(_rows(_read_json(path, [])))
        csv_path = self.root / "data/imports/partner_opportunities.csv"
        try:
            with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
                rows.extend(dict(row) for row in csv.DictReader(handle))
        except OSError:
            pass
        return rows

    @staticmethod
    def _partner_matches(article: dict[str, Any], partners: list[dict[str, Any]]) -> list[str]:
        article_tokens = _tokens(" ".join((_text(article.get("title")), _text(article.get("slug")), _text(article.get("entity")))))
        matches = []
        for row in partners:
            name = _text(row.get("program_name") or row.get("brand") or row.get("name"))
            if name and article_tokens & _tokens(name):
                matches.append(name)
        return sorted(set(matches))[:5]

    def _performance_rows(self) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for path in (self.root / "data/content_performance.json", self.root / "data/analytics/content_performance.json"):
            for row in _rows(_read_json(path, [])):
                slug = _slug(_text(row.get("slug") or row.get("page") or row.get("url")))
                if slug:
                    result[slug] = row
        return result

    def _internal_link_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        path = self.root / "data/internal_link_action_plan.csv"
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                for row in csv.DictReader(handle):
                    for key in ("source_page", "target_page", "source_slug", "target_slug"):
                        slug = _slug(_text(row.get(key)).strip("/").rsplit("/", 1)[-1])
                        if slug:
                            counts[slug] = counts.get(slug, 0) + 1
        except OSError:
            pass
        return counts

    def _knowledge_signals(self, slug: str) -> dict[str, Any]:
        base = self.root / "data/entity_knowledge_base" / slug
        claims = _read_json(base / "claims.json", [])
        sources = _read_json(base / "sources.json", [])
        claim_rows = _rows(claims) or ([row for row in claims if isinstance(row, dict)] if isinstance(claims, list) else [])
        verified = _http_urls(sources)
        claim_count = len(claim_rows)
        return {
            "claim_count": claim_count,
            "entity_coverage_score": min(100.0, claim_count * 5.0),
            "verified_source_urls": sorted(verified),
        }

    def _editorial_memory_slugs(self) -> set[str]:
        matched: set[str] = set()
        for base in (self.root / "editorial_memory/approved", self.root / "editorial_memory/best"):
            if not base.is_dir():
                continue
            for path in base.glob("*.json"):
                value = _read_json(path, {})
                for row in _rows(value):
                    slug = _slug(_text(row.get("slug") or row.get("article_slug")))
                    if slug:
                        matched.add(slug)
                path_slug = _slug(path.stem)
                if path_slug:
                    matched.add(path_slug)
        return matched

    def _planned_identities(self) -> set[str]:
        identities: set[str] = set()
        weeks = self.root / "data/editorial_queue/weeks"
        for path in weeks.glob("*/week.json") if weeks.is_dir() else []:
            value = _read_json(path, {})
            for row in value.get("topics", []) if isinstance(value, dict) else []:
                if isinstance(row, dict):
                    identities.add(_slug(_text(row.get("existing_slug") or row.get("slug") or row.get("root_topic_id"))))
        return identities


@dataclass
class ThreeLevelContentOpportunityFallback:
    root: Path
    now: datetime | None = None
    minimum_score: float | None = None

    def __post_init__(self) -> None:
        self.root = self.root.resolve()
        self.now = (self.now or datetime.now(UTC)).astimezone(UTC)
        config = _read_json(self.root / "config/editorial_system.json", {})
        fallback = config.get("three_level_content_opportunity_fallback", {}) if isinstance(config, dict) else {}
        self.scoring_config = fallback
        if self.minimum_score is None:
            self.minimum_score = float(fallback.get("minimum_upgrade_opportunity_score") or DEFAULT_MINIMUM_SCORE)

    def select(
        self,
        level_1_candidates: list[dict[str, Any]],
        *,
        required_count: int = 2,
        candidate_limit: int | None = None,
        inventory: dict[str, Any] | None = None,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        inventory_limit = max(required_count, int(candidate_limit or required_count))
        level_1 = [self._level_one(row) for row in level_1_candidates]
        selected = list(level_1)
        diagnostics: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "required_count": required_count,
            "minimum_upgrade_opportunity_score": self.minimum_score,
            "levels_evaluated": [1],
            "level_counts": {"1": len(level_1), "2": 0, "3": 0},
            "routed_level_2_to_refresh": [],
            "quality_gates_lowered": False,
            "human_approval_required": True,
            "network_used": False,
            "NEW_ROOT_CANDIDATES": len(level_1),
            "NEW_ROOT_PASSED": len(level_1),
            "LEVEL2_CANDIDATES": 0,
            "LEVEL2_PASSED": 0,
            "LEVEL3_CANDIDATES": 0,
            "LEVEL3_PASSED": 0,
            "SAFE_WEEKLY_ROOTS": min(len(selected), required_count),
            "rejected_candidates": [],
        }
        if len(selected) >= required_count:
            diagnostics.update({"fallback_level_used": 1, "status": "LEVEL_1_SUFFICIENT"})
            return selected, diagnostics

        snapshot = inventory or ExistingContentInventory(self.root, self.now).scan()
        articles = [row for row in snapshot.get("articles", []) if isinstance(row, dict)]
        self._guard_index = self._build_guard_index(articles)
        expansions: list[dict[str, Any]] = []
        refresh_pool: list[dict[str, Any]] = []
        rejected: list[dict[str, Any]] = []
        diagnostics["levels_evaluated"].append(2)
        for article_index, article in enumerate(articles):
            expansion, refresh, evaluations = self._opportunities_for(
                article,
                articles,
                angle_offset=article_index % len(ANGLE_DEFINITIONS),
            )
            rejected.extend(row for row in evaluations if row.get("rejection_stage"))
            if expansion:
                expansions.append(expansion)
            if refresh:
                refresh_pool.append(refresh)
        expansions = self._dedupe(expansions, selected)
        expansions.sort(key=lambda row: (-float(row["opportunity_score"]), row["slug"]))
        selected.extend(expansions[: max(0, inventory_limit - len(selected))])
        diagnostics["level_counts"]["2"] = len(expansions)
        diagnostics["LEVEL2_CANDIDATES"] = len(articles)
        diagnostics["LEVEL2_PASSED"] = len(expansions)
        diagnostics["rejected_candidates"] = rejected
        diagnostics["SAFE_WEEKLY_ROOTS"] = min(len(selected), required_count)
        if len(selected) >= required_count:
            diagnostics.update({"fallback_level_used": 2, "status": "LEVEL_2_USED", "inventory": snapshot})
            return selected, diagnostics

        diagnostics["levels_evaluated"].append(3)
        expanded_source_slugs = {
            _text(row.get("source_article_slug"))
            for row in selected
            if row.get("opportunity_type") == "existing_root_expansion"
        }
        refreshes = [
            row
            for row in self._dedupe(refresh_pool, selected)
            if _text(row.get("existing_slug") or row.get("slug")) not in expanded_source_slugs
        ]
        refreshes.sort(key=lambda row: (-float(row["opportunity_score"]), row["slug"]))
        selected.extend(refreshes[: max(0, required_count - len(selected))])
        diagnostics["level_counts"]["3"] = len(refreshes)
        diagnostics["LEVEL3_CANDIDATES"] = len(refresh_pool)
        diagnostics["LEVEL3_PASSED"] = len(refreshes)
        diagnostics["SAFE_WEEKLY_ROOTS"] = min(len(selected), required_count)
        status = (
            "LEVEL_3_USED"
            if len(selected) >= required_count
            else "PARTIAL_WEEK_AVAILABLE"
            if selected
            else "INSUFFICIENT_QUALITY_OPPORTUNITIES"
        )
        diagnostics.update(
            {
                "fallback_level_used": max((int(row.get("fallback_level") or 0) for row in selected), default=0),
                "status": status,
                "inventory": snapshot,
            }
        )
        return selected, diagnostics

    @staticmethod
    def _level_one(row: dict[str, Any]) -> dict[str, Any]:
        return {
            **row,
            "selection_source": "weekly_content_planning",
            "fallback_level": 1,
            "opportunity_type": "new_opportunity",
            "human_approval_required": True,
            "create_new_url": True,
            "preserve_slug": False,
            "deep_dive_eligible": True,
        }

    def _opportunities_for(
        self,
        article: dict[str, Any],
        inventory: list[dict[str, Any]],
        *,
        angle_offset: int = 0,
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None, list[dict[str, Any]]]:
        score = self.score(article, opportunity_type="existing_root_expansion")
        refresh = self._refresh_candidate(article, score)
        evaluations: list[dict[str, Any]] = []
        source_ready = bool(article.get("source_readiness", {}).get("passes"))
        if not source_ready:
            evaluations.extend(
                [
                    self._rejection(article, level=2, stage="RESEARCH_READINESS", reason="Historical root has no reusable verified source evidence."),
                    self._rejection(article, level=3, stage="RESEARCH_READINESS", reason="Content refresh cannot bypass the existing research gate."),
                ]
            )
            return None, None, evaluations
        if article.get("already_planned"):
            evaluations.append(
                self._rejection(article, level=2, stage="PLANNING_STATE", reason="Existing root is already present in a weekly plan; only an in-place refresh may be reconsidered.")
            )
            if score["upgrade_opportunity_score"] < self.minimum_score:
                evaluations.append(
                    self._rejection(article, level=3, stage="QUALITY_SCORE", reason=f"Upgrade score {score['upgrade_opportunity_score']} is below {self.minimum_score}.")
                )
                return None, None, evaluations
            return None, refresh, evaluations
        if score["upgrade_opportunity_score"] < self.minimum_score:
            reason = f"Upgrade score {score['upgrade_opportunity_score']} is below {self.minimum_score}."
            evaluations.extend(
                [
                    self._rejection(article, level=2, stage="QUALITY_SCORE", reason=reason),
                    self._rejection(article, level=3, stage="QUALITY_SCORE", reason=reason),
                ]
            )
            return None, None, evaluations
        base_title = _text(article.get("entity") or article.get("root_title") or article.get("title"))
        base_title = re.sub(r"(?i)\s+(complete )?review(?: and buyer guide)?\s*$", "", base_title).strip()
        angles = [*ANGLE_DEFINITIONS[angle_offset:], *ANGLE_DEFINITIONS[:angle_offset]]
        for angle, suffix, proposed_intent in angles:
            proposed_title = f"{base_title}: {suffix}" if not suffix.startswith("for ") else f"{base_title} {suffix}"
            proposed_slug = _slug(f"{article['slug']}-{angle}")
            thesis = (
                f"Evaluate {base_title} through {suffix.casefold()}, a different decision question "
                f"from the existing {article.get('search_intent') or 'review'} article."
            )
            proposed = {
                "topic": proposed_title,
                "primary_keyword": proposed_title.casefold(),
                "slug": proposed_slug,
                "root_topic_id": proposed_slug,
                "search_intent": proposed_intent,
                "parent_root_id": _text(article.get("root_topic_id") or article["slug"]),
                "source_article_slug": article["slug"],
                "unique_thesis": thesis,
                "verified_source_urls": list(article.get("verified_source_urls") or []),
                **self._angle_dimensions(angle, suffix),
            }
            guard = self.cannibalization_guard(proposed, inventory)
            if guard["decision"] not in {"PASS_DEEP_DIVE", "PASS_NEW"}:
                evaluations.append(
                    self._rejection(
                        proposed,
                        level=2,
                        stage="NOVELTY_CANNIBALIZATION",
                        reason="; ".join(guard.get("decision_reasons") or [guard["decision"]]),
                        guard=guard,
                    )
                )
                continue
            plan = self._weekly_plan(proposed_title)
            candidate = {
                **proposed,
                **guard,
                "selection_source": "weekly_content_planning",
                "fallback_level": 2,
                "opportunity_type": "existing_root_expansion",
                "proposed_new_intent": proposed_intent,
                "topic_tier": article.get("topic_tier"),
                "topic_tier_id": article.get("topic_tier_id"),
                "category": article.get("category"),
                "subcategory": article.get("subcategory"),
                "upgrade_opportunity_score": score["upgrade_opportunity_score"],
                "opportunity_score": score["upgrade_opportunity_score"],
                "score_breakdown": score,
                "unique_thesis": thesis,
                "duplicate_risk": guard["duplicate_risk"],
                "cannibalization_risk": bool(guard.get("cannibalization_risk")),
                "research_ready": True,
                "source_readiness": article["source_readiness"],
                "verified_sources": [
                    {"source_url": url, "verification_status": "verified"}
                    for url in article.get("verified_source_urls", [])
                ],
                "human_approval_required": True,
                "preserve_slug": False,
                "create_new_url": True,
                "deep_dive_eligible": True,
                "why": self._reasons(score, "existing root expansion"),
                "weekly_content_plan": plan,
                "pillar_article": plan[0]["title"],
                "supporting_article_ideas": [row["title"] for row in plan[1:]],
                "existing_related_content": [{"slug": article["slug"], "title": article["title"]}],
                "internal_link_opportunities": int(score["internal_link_opportunity"]),
                "evergreen": True,
            }
            return candidate, refresh, evaluations
        return None, refresh, evaluations

    @staticmethod
    def _angle_dimensions(angle: str, suffix: str) -> dict[str, Any]:
        mapping = {
            "pricing": {"pricing_roi_angle": suffix},
            "comparison": {"comparison_set": suffix},
            "security": {"security_privacy_angle": suffix},
            "integrations": {"implementation_angle": suffix},
            "workflows": {"workflow": suffix},
            "small-business": {"target_audience": "small business"},
        }
        return mapping.get(angle, {"use_case": suffix})

    @staticmethod
    def _rejection(
        candidate: dict[str, Any],
        *,
        level: int,
        stage: str,
        reason: str,
        guard: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        guard = guard or {}
        research = candidate.get("source_readiness") or {}
        return {
            "candidate": _text(candidate.get("topic") or candidate.get("title") or candidate.get("slug")),
            "level": level,
            "root_topic": _text(candidate.get("parent_root_id") or candidate.get("root_topic_id") or candidate.get("slug")),
            "intent": _text(candidate.get("search_intent")),
            "novelty_score": guard.get("novelty_score"),
            "overlap_score": guard.get("overlap_score"),
            "research_status": "READY" if research.get("passes") else "RESEARCH_REQUIRED",
            "rejection_stage": stage,
            "rejection_reason": reason,
            "required_operator_action": (
                "Add and verify source evidence in Menu S, then rerun Menu 1."
                if stage == "RESEARCH_READINESS"
                else "Choose a substantively different intent/angle with evidence, or leave the candidate rejected."
            ),
        }

    def score(self, article: dict[str, Any], *, opportunity_type: str) -> dict[str, Any]:
        weights = {
            "freshness_gap": 18.0,
            "topical_depth_gap": 17.0,
            "commercial_value": 15.0,
            "affiliate_opportunity": 10.0,
            "internal_link_opportunity": 12.0,
            "source_availability": 12.0,
            "existing_authority_value": 8.0,
            "entity_coverage_gap": 8.0,
            **(
                self.scoring_config.get("component_weights", {})
                if isinstance(self.scoring_config.get("component_weights"), dict)
                else {}
            ),
        }
        penalties = {
            "duplicate_intent": 30.0,
            "source_unavailable": 25.0,
            "obsolete_or_dead_product": 30.0,
            "low_commercial_relevance": 20.0,
            **(
                self.scoring_config.get("penalties", {})
                if isinstance(self.scoring_config.get("penalties"), dict)
                else {}
            ),
        }
        title = f"{_text(article.get('title'))} {_text(article.get('slug'))}".casefold()
        updated = _text(article.get("updated_at") or article.get("published_at") or article.get("date"))
        age_days = 365
        try:
            parsed = datetime.fromisoformat(updated.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)
            age_days = max(0, (self.now - parsed.astimezone(UTC)).days)
        except ValueError:
            pass
        freshness = round(min(float(weights["freshness_gap"]), float(weights["freshness_gap"]) * (0.22 + min(1.0, age_days / 365.0) * 0.78)), 2)
        commercial = float(weights["commercial_value"]) if any(word in title for word in ("software", "tool", "pricing", "review", "crm", "automation")) else round(float(weights["commercial_value"]) * 0.53, 2)
        affiliate = min(float(weights["affiliate_opportunity"]), len(article.get("partner_signal_matches") or []) * float(weights["affiliate_opportunity"]) * 0.4)
        siblings = int(article.get("supporting_article_count") or 0)
        topical = max(float(weights["topical_depth_gap"]) * 0.3, float(weights["topical_depth_gap"]) - min(float(weights["topical_depth_gap"]) * 0.7, siblings * 2.0))
        internal = min(float(weights["internal_link_opportunity"]), float(weights["internal_link_opportunity"]) * 0.33 + float(article.get("internal_link_count") or 0) + siblings)
        sources = article.get("source_readiness") or {}
        source_score = min(float(weights["source_availability"]), float(sources.get("verified_source_count") or 0) * float(weights["source_availability"]) * 0.5)
        performance = article.get("performance") or {}
        authority = float(weights["existing_authority_value"]) * (1.0 if float(performance.get("impressions") or 0) > 0 else 0.625)
        entity_gap = float(weights["entity_coverage_gap"]) if not article.get("entity_coverage_score") else max(0.0, float(weights["entity_coverage_gap"]) * (1.0 - min(100.0, float(article["entity_coverage_score"])) / 100.0))
        duplicate_penalty = 0.0
        source_penalty = 0.0 if sources.get("passes") else float(penalties["source_unavailable"])
        obsolete_penalty = float(penalties["obsolete_or_dead_product"]) if article.get("obsolete") or article.get("dead_product") else 0.0
        relevance_penalty = float(penalties["low_commercial_relevance"]) if article.get("commercially_relevant") is False else 0.0
        total = max(
            0.0,
            min(100.0, freshness + commercial + affiliate + topical + internal + source_score + authority + entity_gap - duplicate_penalty - source_penalty - obsolete_penalty - relevance_penalty),
        )
        return {
            "schema_version": "upgrade_opportunity_score_v1",
            "config_schema_version": _text(self.scoring_config.get("schema_version") or "built_in_v1"),
            "opportunity_type": opportunity_type,
            "upgrade_opportunity_score": round(total, 2),
            "freshness_gap": freshness,
            "commercial_value": commercial,
            "affiliate_opportunity": affiliate,
            "partnerstack_opportunity": affiliate,
            "topical_depth_gap": topical,
            "internal_link_opportunity": internal,
            "source_availability": source_score,
            "existing_authority_value": authority,
            "entity_coverage_gap": round(entity_gap, 2),
            "duplication_penalty": duplicate_penalty,
            "source_penalty": source_penalty,
            "obsolete_product_penalty": obsolete_penalty,
            "low_relevance_penalty": relevance_penalty,
        }

    def cannibalization_guard(self, proposed: dict[str, Any], inventory: list[dict[str, Any]]) -> dict[str, Any]:
        exact_slug = False
        near_title = False
        same_primary_keyword = False
        same_intent = False
        topical_overlap = 0.0
        entity = _text(proposed.get("parent_root_id") or proposed.get("source_article_slug"))
        proposed_keyword = _slug(_text(proposed.get("primary_keyword") or proposed.get("topic") or proposed.get("title")))
        proposed_entity_tokens = _tokens(entity) - {"review", "pricing", "comparison", "software", "tools", "tool", "ai"}
        proposed_title_tokens = _tokens(_text(proposed.get("topic") or proposed.get("title")))
        index = getattr(self, "_guard_index", None)
        rows = index if isinstance(index, list) and len(index) == len(inventory) else self._build_guard_index(inventory)
        for existing in rows:
            exact_slug = exact_slug or existing["slug"] == _slug(_text(proposed.get("slug")))
            overlap = _title_similarity_tokens(proposed_title_tokens, existing["title_tokens"])
            topical_overlap = max(topical_overlap, overlap)
            near_title = near_title or (
                overlap >= 0.82
                and len(proposed_title_tokens) >= 2
                and len(existing["title_tokens"]) >= 2
            )
            existing_keyword = existing["primary_keyword"]
            same_primary_keyword = same_primary_keyword or bool(
                proposed_keyword and existing_keyword and proposed_keyword == existing_keyword
            )
            same_entity = entity in {
                existing["root_topic_id"], existing["raw_slug"], existing["parent_root_id"]
            }
            existing_entity_tokens = existing["entity_tokens"]
            same_entity = same_entity or bool(
                proposed_entity_tokens
                and existing_entity_tokens
                and proposed_entity_tokens & existing_entity_tokens
                and overlap >= 0.34
            )
            same_intent = same_intent or (
                same_entity
                and existing["search_intent"] == _text(proposed.get("search_intent")).casefold()
            )
        risk = "high" if exact_slug or near_title or same_primary_keyword or same_intent else "medium" if topical_overlap >= 0.55 else "low"

        dimension_fields = {
            "root_entity": ("root_topic_id", "parent_root_id", "source_article_slug"),
            "search_intent": ("search_intent",),
            "target_audience": ("target_audience", "audience"),
            "unique_thesis": ("unique_thesis", "thesis"),
            "workflow": ("workflow", "workflow_angle"),
            "implementation": ("implementation_angle", "implementation"),
            "troubleshooting": ("troubleshooting_angle", "troubleshooting"),
            "pricing_roi": ("pricing_roi_angle", "pricing", "roi"),
            "comparison_set": ("comparison_set", "competitors", "alternatives"),
            "use_case": ("use_case", "use_cases"),
            "risks_limitations": ("risks_limitations", "limitations"),
            "security_privacy": ("security_privacy_angle", "security", "privacy"),
            "verified_source_urls": ("verified_source_urls", "source_urls"),
            "heading_patterns": ("heading_patterns", "headings"),
            "faq_themes": ("faq_themes", "faq"),
        }

        def dimension_value(record: dict[str, Any], keys: tuple[str, ...]) -> str:
            for key in keys:
                value = record.get(key)
                if isinstance(value, (list, tuple, set)):
                    text = " ".join(sorted(str(item) for item in value if str(item).strip()))
                else:
                    text = _text(value)
                if text:
                    return text
            return ""

        def similarity(left: str, right: str) -> float:
            left_tokens = _tokens(left)
            right_tokens = _tokens(right)
            if not left_tokens or not right_tokens:
                return 0.0
            return len(left_tokens & right_tokens) / max(1, len(left_tokens | right_tokens))

        proposed_root = _text(
            proposed.get("parent_root_id")
            or proposed.get("source_article_slug")
            or proposed.get("root_topic_id")
        )
        best_row: dict[str, Any] = {}
        best_overlap = -1.0
        best_reused: list[str] = []
        best_new: list[str] = []
        for existing in inventory:
            reused_dimensions: list[str] = []
            new_dimensions: list[str] = []
            considered = 0
            overlap_points = 0.0
            for name, keys in dimension_fields.items():
                proposed_value = dimension_value(proposed, keys)
                if not proposed_value:
                    continue
                considered += 1
                existing_value = dimension_value(existing, keys)
                score = similarity(proposed_value, existing_value) if existing_value else 0.0
                if name == "root_entity" and proposed_value.casefold() == existing_value.casefold():
                    score = 1.0
                overlap_points += score
                if score >= 0.65:
                    reused_dimensions.append(name)
                elif score < 0.35:
                    new_dimensions.append(name)
            overlap_score = overlap_points / max(1, considered)
            if overlap_score > best_overlap:
                best_overlap = overlap_score
                best_row = existing
                best_reused = reused_dimensions
                best_new = new_dimensions

        novelty_score = round(max(0.0, 100.0 * (1.0 - max(0.0, best_overlap))), 2)
        overlap_score = round(max(0.0, best_overlap) * 100.0, 2)
        nearest_url = _text(best_row.get("canonical") or best_row.get("url"))
        if not nearest_url and best_row:
            nearest_slug = _text(best_row.get("slug"))
            nearest_url = nearest_slug
        nearest_urls = [nearest_url] if nearest_url else []
        nearest_root = dimension_value(best_row, dimension_fields["root_entity"])
        same_root = bool(proposed_root and nearest_root and proposed_root.casefold() == nearest_root.casefold())
        proposed_intent = dimension_value(proposed, dimension_fields["search_intent"])
        existing_intent = dimension_value(best_row, dimension_fields["search_intent"])
        intent_overlap = similarity(proposed_intent, existing_intent)
        if proposed_intent and existing_intent and proposed_intent.casefold() == existing_intent.casefold():
            intent_overlap = 1.0

        reasons: list[str] = []
        if exact_slug or (same_root and intent_overlap >= 0.65 and novelty_score < 40):
            decision = "REJECT_DUPLICATE"
            reasons.append("Same root and search intent do not add enough substantive new dimensions.")
        elif same_root and novelty_score >= 40 and len(best_new) >= 2:
            decision = "PASS_DEEP_DIVE"
            reasons.append("Same-root article adds multiple substantive editorial dimensions.")
        elif not same_root and not exact_slug and not same_primary_keyword:
            decision = "PASS_NEW"
            reasons.append("Candidate targets a distinct root/entity with no exact collision.")
        else:
            decision = "NEEDS_HUMAN_REVIEW"
            reasons.append("Novelty is borderline and requires editorial judgment.")

        return {
            "exact_slug": exact_slug,
            "near_duplicate_title": near_title,
            "same_primary_keyword": same_primary_keyword,
            "same_intent": same_intent,
            "same_entity_same_decision_question": same_intent,
            "topical_overlap": round(topical_overlap, 4),
            "novelty_score": novelty_score,
            "overlap_score": overlap_score,
            "intent_overlap": round(intent_overlap, 4),
            "nearest_existing_urls": nearest_urls,
            "new_dimensions": best_new,
            "reused_dimensions": best_reused,
            "cannibalization_risk": decision == "REJECT_DUPLICATE" or risk == "high",
            "duplicate_risk": "high" if decision == "REJECT_DUPLICATE" else risk,
            "decision": decision,
            "decision_reasons": reasons,
            "route": "content_refresh" if decision == "REJECT_DUPLICATE" else "new_article",
        }

    @staticmethod
    def _build_guard_index(inventory: list[dict[str, Any]]) -> list[dict[str, Any]]:
        ignored = {"review", "pricing", "comparison", "software", "tools", "tool", "ai"}
        return [
            {
                "slug": _slug(_text(row.get("slug"))),
                "raw_slug": _text(row.get("slug")),
                "root_topic_id": _text(row.get("root_topic_id")),
                "parent_root_id": _text(row.get("parent_root_id")),
                "title_tokens": _tokens(_text(row.get("title"))),
                "primary_keyword": _slug(_text(row.get("primary_keyword") or row.get("title"))),
                "search_intent": _text(row.get("search_intent")).casefold(),
                "entity_tokens": _tokens(
                    _text(row.get("parent_root_id") or row.get("root_topic_id") or row.get("slug"))
                ) - ignored,
            }
            for row in inventory
        ]

    def route_level_2_candidate(
        self,
        proposed: dict[str, Any],
        source_article: dict[str, Any],
        inventory: list[dict[str, Any]],
    ) -> dict[str, Any]:
        guard = self.cannibalization_guard(proposed, inventory)
        if guard["route"] == "content_refresh":
            score = self.score(source_article, opportunity_type="content_refresh")
            return self._refresh_candidate(source_article, score)
        return {**proposed, **guard, "fallback_level": 2, "opportunity_type": "existing_root_expansion"}

    def _refresh_candidate(self, article: dict[str, Any], score: dict[str, Any]) -> dict[str, Any]:
        reasons = ["content_freshness_review", "evidence_coverage_review", "internal_link_gap"]
        if article.get("performance"):
            reasons.append("analytics_opportunity")
        title = _text(article.get("title") or article["slug"].replace("-", " ").title())
        return {
            "topic": title,
            "primary_keyword": _text(article.get("primary_keyword") or title.casefold()),
            "slug": article["slug"],
            "root_topic_id": _text(article.get("root_topic_id") or article["slug"]),
            "search_intent": _text(article.get("search_intent") or _intent(title)),
            "selection_source": "weekly_content_planning",
            "fallback_level": 3,
            "opportunity_type": "content_refresh",
            "existing_slug": article["slug"],
            "source_article_slug": article["slug"],
            "parent_root_id": _text(article.get("root_topic_id") or article["slug"]),
            "refresh_reason": reasons,
            "refresh_scope": ["evidence", "pricing_and_features", "internal_links", "entity_coverage"],
            "refresh_thesis": f"Update {title} in place while preserving its canonical identity.",
            "update_scope": "advanced evidence-led refresh of the existing article",
            "preserve_slug": True,
            "create_new_url": False,
            "deep_dive_eligible": False,
            "refresh_existing_article": True,
            "task_type_hint": "WEBSITE_UPDATE",
            "upgrade_opportunity_score": score["upgrade_opportunity_score"],
            "opportunity_score": score["upgrade_opportunity_score"],
            "score_breakdown": score,
            "duplicate_risk": "refresh_existing_url",
            "cannibalization_risk": False,
            "research_ready": bool(article.get("source_readiness", {}).get("passes")),
            "source_readiness": article.get("source_readiness") or _source_readiness([]),
            "verified_sources": [
                {"source_url": url, "verification_status": "verified"}
                for url in article.get("verified_source_urls", [])
            ],
            "existing_article_reference": _text(article.get("metadata_path") or f"data/production_article_drafts/{article['slug']}"),
            "human_approval_required": True,
            "why": self._reasons(score, "content refresh"),
            "weekly_content_plan": [{"angle": "content_refresh", "title": title}],
            "pillar_article": title,
            "supporting_article_ideas": [],
            "existing_related_content": [{"slug": article["slug"], "title": title}],
            "internal_link_opportunities": int(score["internal_link_opportunity"]),
            "evergreen": True,
        }

    @staticmethod
    def _weekly_plan(topic: str) -> list[dict[str, str]]:
        return [
            {"angle": "pillar", "title": topic},
            {"angle": "implementation", "title": f"How to evaluate {topic}"},
            {"angle": "limitations", "title": f"{topic}: limitations and risks"},
        ]

    @staticmethod
    def _reasons(score: dict[str, Any], kind: str) -> list[str]:
        ranked = sorted(
            (
                (key, value)
                for key, value in score.items()
                if key not in {"schema_version", "opportunity_type", "upgrade_opportunity_score"}
                and isinstance(value, (int, float))
                and value > 0
                and not key.endswith("penalty")
            ),
            key=lambda row: (-float(row[1]), row[0]),
        )
        return [f"Selected as {kind}.", *[f"{key}={value}" for key, value in ranked[:3]]]

    @staticmethod
    def _dedupe(candidates: list[dict[str, Any]], selected: list[dict[str, Any]]) -> list[dict[str, Any]]:
        seen = {
            (_slug(_text(row.get("slug"))), _text(row.get("opportunity_type")))
            for row in selected
        }
        result = []
        for row in candidates:
            key = (_slug(_text(row.get("slug"))), _text(row.get("opportunity_type")))
            if key in seen:
                continue
            seen.add(key)
            result.append(row)
        return result
