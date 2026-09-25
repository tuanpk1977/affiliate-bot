from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from modules.entity_knowledge_base import EntityKnowledgeBase, entity_id
from modules.official_source_registry import OfficialSourceRegistry
from modules.source_classification import domain_looks_owned_by


VERIFICATION_STATES = {
    "CANDIDATE",
    "VERIFIED",
    "REJECTED",
    "AMBIGUOUS",
    "STALE",
    "INSUFFICIENT_EVIDENCE",
}


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _write_json(path: Path, payload: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)
    return path


def _text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _domain(url: str) -> str:
    return (urlparse(url).hostname or "").casefold().removeprefix("www.")


def _values(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return [value] if value not in (None, "") else []


class ComparatorDiscoveryEngine:
    """Deterministic comparator discovery using repository-owned evidence only."""

    schema_version = 1

    def __init__(
        self,
        *,
        root: Path,
        data_dir: Path | None = None,
        freshness_days: int = 180,
        auto_selection_margin: float = 0.10,
    ) -> None:
        self.root = root
        self.data_dir = data_dir or root / "data"
        self.kb = EntityKnowledgeBase(self.data_dir / "entity_knowledge_base")
        self.registry = OfficialSourceRegistry(
            self.data_dir / "official_source_registry.json"
        )
        self.freshness_days = freshness_days
        self.auto_selection_margin = auto_selection_margin
        self.taxonomy_path = self.data_dir / "category_taxonomy.json"
        self.manual_mappings_path = self.data_dir / "comparator_mappings.json"

    def discover(
        self,
        *,
        root_entity: str,
        article_slug: str,
        package: dict[str, Any],
        task: dict[str, Any],
        required_count: int = 2,
        persist_report: bool = True,
    ) -> dict[str, Any]:
        root_profile = self.kb.load(root_entity)
        raw = self._candidate_inputs(
            root_entity=root_entity,
            root_profile=root_profile,
            package=package,
            task=task,
        )
        raw_candidates = [
            self._verify_candidate(
                root_profile=root_profile,
                candidate_name=name,
                relationship_sources=sources,
            )
            for name, sources in raw.items()
        ]
        root_id = entity_id(root_profile.get("canonical_name") or root_entity)
        candidates_by_id: dict[str, dict[str, Any]] = {}
        for candidate in raw_candidates:
            candidate_id = str(candidate.get("candidate_entity_id") or "")
            if not candidate_id or candidate_id == root_id:
                continue
            previous = candidates_by_id.get(candidate_id)
            if previous is None or float(candidate.get("confidence") or 0) > float(previous.get("confidence") or 0):
                candidates_by_id[candidate_id] = candidate
        candidates = list(candidates_by_id.values())
        candidates.sort(key=lambda row: row["canonical_name"].casefold())
        candidates.sort(
            key=lambda row: (
                row["verification_status"] == "VERIFIED",
                float(row["confidence"]),
            ),
            reverse=True,
        )

        confirmed = self._confirmed_relationships(root_entity)
        confirmed_ids = {
            str(row.get("comparator_entity_id") or "")
            for row in confirmed
            if str(row.get("current_status") or "") == "VERIFIED"
        }
        for candidate in candidates:
            if candidate["candidate_entity_id"] in confirmed_ids:
                candidate["operator_confirmed"] = True
                if candidate["verification_status"] not in {
                    "REJECTED",
                    "AMBIGUOUS",
                    "STALE",
                }:
                    candidate["verification_status"] = "VERIFIED"
                    candidate["confidence"] = max(float(candidate["confidence"]), 0.95)

        verified = [
            row for row in candidates if row["verification_status"] == "VERIFIED"
        ]
        confirmed_verified = [
            row
            for row in verified
            if row.get("operator_confirmed")
        ]
        selected: list[dict[str, Any]] = []
        mode = "HUMAN_CONFIRM_REQUIRED"
        decision_reason = ""
        if len(confirmed_verified) == required_count:
            selected = confirmed_verified
            mode = "AUTO_VERIFIED"
            decision_reason = "Reused the exact operator-confirmed comparator mapping."
        elif len(verified) == required_count:
            selected = verified[:required_count]
            mode = "AUTO_VERIFIED"
            decision_reason = "Exactly the required number of candidates passed every verification rule."
        elif len(verified) > required_count:
            boundary = float(verified[required_count - 1]["confidence"])
            next_score = float(verified[required_count]["confidence"])
            if boundary - next_score >= self.auto_selection_margin:
                selected = verified[:required_count]
                mode = "AUTO_VERIFIED"
                decision_reason = "The selected candidates exceed the next candidate by the configured margin."
            else:
                decision_reason = "Several verified candidates are similarly plausible; operator confirmation is required."
        else:
            decision_reason = (
                f"Only {len(verified)} of {required_count} required comparators passed verification."
            )

        payload = {
            "schema_version": self.schema_version,
            "generated_at": _now(),
            "article_slug": article_slug,
            "root_entity_id": entity_id(root_profile.get("canonical_name") or root_entity),
            "root_entity_name": _text(root_profile.get("canonical_name") or root_entity),
            "root_category": _text(root_profile.get("product_category")),
            "required_comparator_count": required_count,
            "approval_mode": mode,
            "decision_reason": decision_reason,
            "candidate_count": len(candidates),
            "verified_count": len(verified),
            "selected_comparators": selected,
            "operator_candidates": candidates[:5],
            "candidates": candidates,
            "status": "READY" if len(selected) == required_count else "BLOCKED",
        }
        if persist_report:
            self._write_operator_report(article_slug, payload)
        return payload

    def confirm(
        self,
        *,
        root_entity: str,
        comparator_names: list[str],
        article_slug: str,
        operator: str = "editor",
    ) -> dict[str, Any]:
        if len(comparator_names) != 2:
            raise ValueError("Exactly two comparator names are required.")
        root_profile = self.kb.load(root_entity)
        verified: list[dict[str, Any]] = []
        for name in comparator_names:
            candidate = self._verify_candidate(
                root_profile=root_profile,
                candidate_name=name,
                relationship_sources=[
                    {
                        "type": "operator_confirmation",
                        "detail": f"Confirmed by {operator} for {article_slug}",
                    }
                ],
            )
            if candidate["verification_status"] != "VERIFIED":
                raise ValueError(
                    f"Comparator {name!r} cannot be confirmed: "
                    f"{candidate['verification_status']} - {candidate['rejection_reason']}"
                )
            self.kb.upsert_competitor_relationship(
                root_entity,
                comparator_entity=name,
                relationship_type="direct_comparator",
                comparable_use_cases=candidate["comparable_use_cases"],
                category_overlap=candidate["category_overlap"],
                source_evidence=candidate["relationship_sources"],
                confidence=float(candidate["confidence"]),
                operator_confirmation={
                    "confirmed": True,
                    "confirmed_by": operator,
                    "confirmed_at": _now(),
                },
                article_slug=article_slug,
                current_status="VERIFIED",
            )
            verified.append(candidate)
        return {
            "status": "CONFIRMED",
            "root_entity": root_entity,
            "article_slug": article_slug,
            "comparators": verified,
        }

    def _candidate_inputs(
        self,
        *,
        root_entity: str,
        root_profile: dict[str, Any],
        package: dict[str, Any],
        task: dict[str, Any],
    ) -> dict[str, list[dict[str, str]]]:
        candidates: dict[str, list[dict[str, str]]] = {}

        def add(name: Any, source_type: str, detail: str) -> None:
            cleaned = _text(name)
            key = entity_id(cleaned)
            root_key = entity_id(root_entity)
            if (
                not cleaned
                or key == root_key
                or root_key in key
                or key in root_key
            ):
                return
            candidates.setdefault(cleaned, []).append(
                {"type": source_type, "detail": detail}
            )

        for relationship in self.kb.load_competitor_relationships(root_entity):
            if str(relationship.get("current_status") or "") in {
                "VERIFIED",
                "CANDIDATE",
            }:
                add(
                    relationship.get("comparator_entity"),
                    "entity_knowledge_base",
                    "Persisted competitor relationship.",
                )
        for name in root_profile.get("known_competitors") or []:
            add(name, "entity_knowledge_base", "Root profile known_competitors.")
        for name in root_profile.get("related_entities") or []:
            add(name, "entity_knowledge_base", "Root profile related_entities.")
        for source in root_profile.get("sources") or []:
            if not isinstance(source, dict):
                continue
            source_type = _text(
                source.get("source_type") or source.get("source_family")
            ).casefold()
            source_url = _text(
                source.get("canonical_url") or source.get("source_url")
            )
            relationship_page = source_type in {
                "marketplace",
                "integration",
                "migration",
                "alternatives",
                "compare",
            } or any(
                marker in source_url.casefold()
                for marker in ("/compare", "/alternatives", "/integrations", "/migration")
            )
            if not relationship_page:
                continue
            for key in (
                "related_entities",
                "competitors",
                "alternatives",
                "integrations",
                "migration_targets",
            ):
                for name in _values(source.get(key)):
                    add(
                        name,
                        "official_relationship_page",
                        (
                            f"Product-authored relationship claim from "
                            f"{source_url or source_type}; not independent truth."
                        ),
                    )
        for name, excerpt in self._product_authored_claim_candidates(root_profile):
            add(
                name,
                "official_relationship_page",
                f"Product-authored comparison claim: {excerpt}",
            )

        for key in (
            "comparison_entities",
            "comparator_entities",
            "competitors",
            "alternatives",
        ):
            for name in _values(task.get(key)):
                add(name, "article_blueprint", f"Task field {key}.")
        entities = package.get("entities") if isinstance(package.get("entities"), dict) else {}
        for key in ("competitors", "alternatives"):
            for name in _values(entities.get(key)):
                add(name, "research_package", f"Research package field {key}.")

        mappings = _read_json(self.manual_mappings_path, {"mappings": []})
        for row in mappings.get("mappings", []) if isinstance(mappings, dict) else []:
            if not isinstance(row, dict):
                continue
            if entity_id(row.get("root_entity", "")) == entity_id(root_entity):
                add(
                    row.get("comparator_entity"),
                    "manual_mapping",
                    "Repository-owned manually approved mapping.",
                )

        for history_name in (
            "content_review_queue.json",
            "human_approval_queue.json",
            "publish_queue.json",
        ):
            history = _read_json(self.data_dir / history_name, [])
            rows = history if isinstance(history, list) else history.get("items", [])
            for row in rows if isinstance(rows, list) else []:
                if not isinstance(row, dict):
                    continue
                status = _text(row.get("status")).casefold()
                row_root = _text(
                    row.get("root_entity")
                    or row.get("primary_entity")
                    or row.get("root_title")
                )
                if (
                    entity_id(row_root) != entity_id(root_entity)
                    or status
                    not in {
                        "ai_review_passed",
                        "human_approved",
                        "approved_for_publish",
                        "published_local",
                    }
                ):
                    continue
                for key in (
                    "comparison_entities",
                    "comparator_entities",
                    "competitors",
                    "alternatives",
                ):
                    for name in _values(row.get(key)):
                        add(
                            name,
                            "prior_approved_comparison",
                            f"Approved relationship reused from {history_name}.",
                        )

        root_category = _text(root_profile.get("product_category")).casefold()
        if root_category:
            for profile_path in (self.data_dir / "entity_knowledge_base").glob(
                "*/profile.json"
            ):
                profile = _read_json(profile_path, {})
                if (
                    isinstance(profile, dict)
                    and _text(profile.get("product_category")).casefold() == root_category
                ):
                    add(
                        profile.get("canonical_name"),
                        "same_category_entity",
                        f"Entity KB category: {root_category}.",
                    )

        taxonomy = _read_json(self.taxonomy_path, {"categories": {}})
        categories = taxonomy.get("categories", {}) if isinstance(taxonomy, dict) else {}
        for row in _values(categories.get(root_category)):
            name = row.get("entity") if isinstance(row, dict) else row
            add(name, "category_taxonomy", f"Category taxonomy: {root_category}.")

        strategy = task.get("content_strategy") if isinstance(task.get("content_strategy"), dict) else {}
        for row in strategy.get("related_weekly_topics") or []:
            if isinstance(row, dict):
                add(
                    row.get("title"),
                    "editorial_memory",
                    _text(row.get("reason")) or "Related weekly topic.",
                )
        return candidates

    def _verify_candidate(
        self,
        *,
        root_profile: dict[str, Any],
        candidate_name: str,
        relationship_sources: list[dict[str, str]],
    ) -> dict[str, Any]:
        initial_resolution = self.kb.resolver.resolve(candidate_name)
        resolved_name = _text(initial_resolution.get("canonical_name"))
        profile = self.kb.load(resolved_name or candidate_name)
        canonical_name = _text(profile.get("canonical_name") or candidate_name)
        if canonical_name.casefold() == "unknown" and _text(candidate_name):
            canonical_name = _text(candidate_name)
        candidate_id = entity_id(canonical_name)
        resolution = self.kb.resolver.resolve(canonical_name)
        sources = self.registry.sources_for(canonical_name)
        known_urls = {
            _text(row.get("canonical_url") or row.get("source_url")).casefold().rstrip("/")
            for row in sources
        }
        for row in profile.get("sources") or []:
            if not isinstance(row, dict):
                continue
            url = _text(row.get("canonical_url") or row.get("source_url"))
            key = url.casefold().rstrip("/")
            if not url:
                continue
            if key in known_urls:
                existing = next(
                    source
                    for source in sources
                    if _text(
                        source.get("canonical_url") or source.get("source_url")
                    ).casefold().rstrip("/")
                    == key
                )
                existing.update(row)
            else:
                sources.append(
                    {
                        **row,
                        "source_url": url,
                        "canonical_url": url,
                    }
                )
                known_urls.add(key)
        sources = [
            row
            for row in sources
            if domain_looks_owned_by(
                canonical_name,
                _text(row.get("canonical_url") or row.get("source_url")),
            )
        ]
        domains = sorted(
            {
                *(_text(row) for row in profile.get("official_domains") or [] if _text(row)),
                *(
                    _domain(_text(row.get("canonical_url") or row.get("source_url")))
                    for row in sources
                    if _domain(_text(row.get("canonical_url") or row.get("source_url")))
                ),
            }
        )
        root_category = _text(root_profile.get("product_category"))
        category = _text(profile.get("product_category"))
        root_use_cases = {
            _text(row).casefold()
            for row in root_profile.get("use_cases") or []
            if _text(row)
        }
        candidate_use_cases = {
            _text(row).casefold()
            for row in profile.get("use_cases") or []
            if _text(row)
        }
        category_overlap = bool(
            root_category
            and category
            and root_category.casefold() == category.casefold()
        )
        use_case_overlap = sorted(root_use_cases & candidate_use_cases)
        relationship_supports_overlap = any(
            row.get("type")
            in {
                "entity_knowledge_base",
                "manual_mapping",
                "same_category_entity",
                "category_taxonomy",
                "operator_confirmation",
                "article_blueprint",
                "research_package",
                "official_relationship_page",
                "prior_approved_comparison",
            }
            for row in relationship_sources
        )
        last_checked = self._parse_date(profile.get("last_checked"))
        stale = bool(
            last_checked
            and datetime.now(UTC) - last_checked > timedelta(days=self.freshness_days)
        )
        urls = [
            _text(row.get("canonical_url") or row.get("source_url"))
            for row in sources
        ]
        github_urls = [url for url in urls if _domain(url) == "github.com"]
        contamination = any(
            bool(row.get("is_fork") or row.get("is_mirror") or row.get("entity_mismatch"))
            for row in sources
        )
        official_retrievable = any(
            str(row.get("verification_status") or row.get("status") or "").casefold()
            in {"verified", "approved", "supplied"}
            or int(row.get("http_status") or 0) in range(200, 400)
            for row in sources
        )

        status = "CANDIDATE"
        reasons: list[str] = []
        if resolution.get("status") == "AMBIGUOUS":
            status = "AMBIGUOUS"
            reasons.append("Entity identity matches multiple profiles.")
        elif resolution.get("status") == "ENTITY_MISMATCH" or contamination:
            status = "REJECTED"
            reasons.append("Entity mismatch, fork, or mirror evidence detected.")
        elif not domains:
            status = "INSUFFICIENT_EVIDENCE"
            reasons.append("Official domain is unknown.")
        elif not sources or not official_retrievable:
            status = "INSUFFICIENT_EVIDENCE"
            reasons.append("No retrievable approved official source is available.")
        elif stale:
            status = "STALE"
            reasons.append("Entity evidence is older than the freshness policy.")
        elif not (category_overlap or use_case_overlap or relationship_supports_overlap):
            status = "INSUFFICIENT_EVIDENCE"
            reasons.append("Category or workflow overlap is not supported.")
        else:
            status = "VERIFIED"

        confidence = 0.0
        confidence += 0.25 if domains else 0.0
        confidence += 0.25 if official_retrievable else 0.0
        confidence += 0.20 if category_overlap else 0.0
        confidence += 0.15 if use_case_overlap else 0.0
        confidence += 0.15 if relationship_supports_overlap else 0.0
        if any(
            row.get("type") == "official_relationship_page"
            for row in relationship_sources
        ):
            confidence += 0.05
        if stale or status in {"REJECTED", "AMBIGUOUS"}:
            confidence = min(confidence, 0.49)

        return {
            "candidate_entity_id": candidate_id,
            "canonical_name": canonical_name,
            "category": category,
            "why_comparable": (
                "Same verified product category."
                if category_overlap
                else "Overlapping verified use cases."
                if use_case_overlap
                else "Repository relationship evidence requires verification."
            ),
            "relationship_sources": relationship_sources,
            "official_domain": domains[0] if domains else "",
            "official_docs": [
                url
                for url in urls
                if any(marker in url.casefold() for marker in ("docs", "guide", "help"))
            ],
            "github_or_repository": github_urls[0] if github_urls else "",
            "official_sources": sources,
            "comparable_use_cases": use_case_overlap,
            "category_overlap": [root_category, category] if category_overlap else [],
            "confidence": round(confidence, 4),
            "verification_status": status,
            "rejection_reason": "; ".join(reasons),
            "freshness": profile.get("last_checked") or "",
            "operator_confirmed": False,
        }

    def _confirmed_relationships(self, root_entity: str) -> list[dict[str, Any]]:
        return self.kb.load_competitor_relationships(root_entity)

    def _write_operator_report(
        self, article_slug: str, payload: dict[str, Any]
    ) -> None:
        target = self.data_dir / "research" / article_slug
        _write_json(target / "comparator_candidate_report.json", payload)
        lines = [
            f"# Comparator candidates: {payload['root_entity_name']}",
            "",
            f"- Status: {payload['status']}",
            f"- Approval mode: {payload['approval_mode']}",
            f"- Reason: {payload['decision_reason']}",
            "",
        ]
        for index, row in enumerate(payload["operator_candidates"], start=1):
            lines.extend(
                [
                    f"{index}. **{row['canonical_name']}** - {row['verification_status']} "
                    f"- confidence {row['confidence']:.2f}",
                    f"   - Why: {row['why_comparable']}",
                    f"   - Official domain: {row['official_domain'] or 'missing'}",
                    f"   - Limitation: {row['rejection_reason'] or 'none'}",
                ]
            )
        (target / "comparator_candidate_report.md").write_text(
            "\n".join(lines) + "\n", encoding="utf-8"
        )

    @staticmethod
    def _product_authored_claim_candidates(
        root_profile: dict[str, Any],
    ) -> list[tuple[str, str]]:
        """Extract only explicit relationship names from approved root paragraphs."""
        results: list[tuple[str, str]] = []
        patterns = (
            re.compile(r"existing tools like (.+?) are ", re.I),
            re.compile(r"ai browsers like (.+?) ship ", re.I),
            re.compile(r"benchmarked .+? against (.+?) on ", re.I),
            re.compile(
                r"^(.+?) was the first widely-used .+? started from there",
                re.I,
            ),
        )
        for paragraph in root_profile.get("paragraphs") or []:
            if not isinstance(paragraph, dict):
                continue
            text = _text(paragraph.get("text"))
            for pattern in patterns:
                match = pattern.search(text)
                if not match:
                    continue
                captured = match.group(1)
                for name in re.split(r"\s+(?:and|or)\s+|,\s*", captured):
                    cleaned = _text(name).strip(" .:;")
                    if 2 <= len(cleaned) <= 80:
                        results.append((cleaned, text[:280]))
        unique: dict[str, tuple[str, str]] = {}
        for name, excerpt in results:
            unique.setdefault(entity_id(name), (name, excerpt))
        return list(unique.values())

    @staticmethod
    def _parse_date(value: Any) -> datetime | None:
        text = _text(value)
        if not text:
            return None
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
        except ValueError:
            return None
