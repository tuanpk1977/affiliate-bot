from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


CLAIM_STATES = {
    "ACTIVE",
    "STALE",
    "SUPERSEDED",
    "CONFLICTED",
    "RETRACTED",
    "ENTITY_MISMATCH",
    "UNUSABLE",
}


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def entity_id(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(value or "").casefold()).strip("-") or "unknown"


def normalized_domain(url: str) -> str:
    host = (urlparse(str(url or "")).hostname or "").casefold().removeprefix("www.")
    return host


def atomic_json(path: Path, payload: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)
    return path


def read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


class EntityResolver:
    """Deterministic alias and official-domain resolver; ambiguous matches never merge."""

    def __init__(self, kb_root: Path) -> None:
        self.kb_root = kb_root

    def resolve(
        self,
        canonical_name: str,
        *,
        aliases: list[str] | None = None,
        source_urls: list[str] | None = None,
    ) -> dict[str, Any]:
        requested_id = entity_id(canonical_name)
        requested_names = {
            entity_id(canonical_name),
            *(entity_id(value) for value in (aliases or []) if value),
        }
        matches: list[dict[str, Any]] = []
        for profile_path in self.kb_root.glob("*/profile.json"):
            profile = read_json(profile_path, {})
            if not isinstance(profile, dict):
                continue
            known_names = {
                entity_id(profile.get("canonical_name", "")),
                *(entity_id(value) for value in profile.get("aliases", []) if value),
            }
            if requested_names & known_names:
                matches.append(profile)
        if len(matches) > 1:
            return {
                "status": "AMBIGUOUS",
                "canonical_entity_id": requested_id,
                "matches": [row.get("entity_id") for row in matches],
                "warnings": ["Multiple entity profiles share the requested alias."],
            }
        profile = matches[0] if matches else {}
        resolved_id = str(profile.get("entity_id") or requested_id)
        official_domains = set(profile.get("official_domains") or [])
        source_domains = {normalized_domain(url) for url in (source_urls or []) if normalized_domain(url)}
        conflicting_domains = sorted(
            domain
            for domain in source_domains
            if official_domains and not self._domain_allowed(domain, official_domains)
        )
        return {
            "status": "ENTITY_MISMATCH" if conflicting_domains else "MATCHED",
            "canonical_entity_id": resolved_id,
            "canonical_name": profile.get("canonical_name") or canonical_name,
            "aliases": sorted(set(profile.get("aliases") or []) | set(aliases or [])),
            "official_domains": sorted(official_domains | source_domains) if not official_domains else sorted(official_domains),
            "conflicting_domains": conflicting_domains,
            "warnings": (
                [f"Source domain is not owned by the resolved entity: {domain}" for domain in conflicting_domains]
                if conflicting_domains
                else []
            ),
        }

    @staticmethod
    def _domain_allowed(domain: str, official_domains: set[str]) -> bool:
        return any(domain == root or domain.endswith("." + root) for root in official_domains)

    @staticmethod
    def classify_source(
        url: str,
        *,
        official_domains: list[str],
        verified_github: list[str] | None = None,
    ) -> dict[str, Any]:
        domain = normalized_domain(url)
        official = EntityResolver._domain_allowed(domain, set(official_domains))
        github_path = urlparse(url).path.casefold().strip("/")
        github_match = domain == "github.com" and any(
            github_path == value.casefold().strip("/")
            or github_path.startswith(value.casefold().strip("/") + "/")
            for value in (verified_github or [])
        )
        classification = "official" if official or github_match else "unofficial"
        return {
            "entity_match_status": "MATCHED" if classification == "official" else "ENTITY_MISMATCH",
            "official_classification": classification,
            "domain_ownership_confidence": "high" if official else ("medium" if github_match else "low"),
            "contamination_warning": "" if classification == "official" else "Unverified domain, fork, or mirror.",
        }


class EntityKnowledgeBase:
    """Versioned, repository-first evidence memory with provenance-preserving reuse."""

    schema_version = 1
    extraction_version = 1

    def __init__(self, root: Path, *, freshness_days: int = 90) -> None:
        self.root = root
        self.freshness_days = freshness_days
        self.resolver = EntityResolver(root)

    def entity_dir(self, value: str) -> Path:
        return self.root / entity_id(value)

    def load(self, value: str) -> dict[str, Any]:
        target = self.entity_dir(value)
        profile = read_json(target / "profile.json", {})
        if not isinstance(profile, dict):
            profile = {}
        profile.setdefault("schema_version", self.schema_version)
        profile.setdefault("entity_id", entity_id(value))
        profile.setdefault("canonical_name", value)
        profile.setdefault("aliases", [])
        profile.setdefault("official_domains", [])
        profile.setdefault("verified_github", [])
        profile.setdefault("documentation_roots", [])
        profile.setdefault("product_category", "")
        profile.setdefault("related_entities", [])
        profile.setdefault("known_competitors", [])
        profile.setdefault("disambiguation_rules", [])
        profile.setdefault("first_seen", now_iso())
        profile.setdefault("last_checked", "")
        profile.setdefault("last_changed", "")
        profile["sources"] = read_json(target / "sources.json", {"records": []}).get("records", [])
        profile["paragraphs"] = read_json(target / "paragraphs.json", {"records": []}).get("records", [])
        profile["claims"] = read_json(target / "claims.json", {"records": []}).get("records", [])
        profile["usage_history"] = read_json(target / "usage_history.json", {"records": []}).get("records", [])
        profile["conflicts"] = read_json(target / "conflicts.json", {"records": []}).get("records", [])
        profile["competitor_relationships"] = self.load_competitor_relationships(value)
        return profile

    def load_competitor_relationships(self, value: str) -> list[dict[str, Any]]:
        payload = read_json(
            self.entity_dir(value) / "competitors.json",
            {"schema_version": 1, "records": []},
        )
        records = payload.get("records", []) if isinstance(payload, dict) else []
        return [row for row in records if isinstance(row, dict)]

    def upsert_competitor_relationship(
        self,
        root_entity: str,
        *,
        comparator_entity: str,
        relationship_type: str,
        comparable_use_cases: list[str],
        category_overlap: list[str],
        source_evidence: list[dict[str, Any]],
        confidence: float,
        operator_confirmation: dict[str, Any],
        article_slug: str,
        current_status: str,
    ) -> dict[str, Any]:
        path = self.entity_dir(root_entity) / "competitors.json"
        records = self.load_competitor_relationships(root_entity)
        root_id = entity_id(root_entity)
        comparator_id = entity_id(comparator_entity)
        existing = next(
            (
                row
                for row in records
                if str(row.get("comparator_entity_id") or "") == comparator_id
            ),
            None,
        )
        checked_at = now_iso()
        values = {
            "root_entity": root_entity,
            "root_entity_id": root_id,
            "comparator_entity": comparator_entity,
            "comparator_entity_id": comparator_id,
            "relationship_type": relationship_type,
            "comparable_use_cases": sorted(set(comparable_use_cases)),
            "category_overlap": sorted(set(category_overlap)),
            "source_evidence": source_evidence,
            "first_seen": (
                existing.get("first_seen") if existing else checked_at
            ),
            "last_verified": checked_at,
            "confidence": round(float(confidence), 4),
            "operator_confirmation": operator_confirmation,
            "articles_where_used": sorted(
                set((existing or {}).get("articles_where_used") or []) | {article_slug}
            ),
            "current_status": current_status,
        }
        if existing is None:
            records.append(values)
        else:
            existing.update(values)
        atomic_json(path, {"schema_version": 1, "records": records})
        return values

    def persist(
        self,
        value: str,
        *,
        aliases: list[str],
        official_domains: list[str],
        sources: list[dict[str, Any]],
        claims: list[dict[str, Any]],
        article_slug: str,
        article_intent: str,
        product_category: str = "",
    ) -> dict[str, Any]:
        target = self.entity_dir(value)
        existing = self.load(value)
        checked_at = now_iso()
        profile = {
            key: existing.get(key)
            for key in (
                "schema_version",
                "entity_id",
                "canonical_name",
                "verified_github",
                "documentation_roots",
                "related_entities",
                "known_competitors",
                "disambiguation_rules",
                "first_seen",
            )
        }
        profile.update(
            {
                "canonical_name": value,
                "aliases": sorted(set(existing.get("aliases", [])) | set(aliases)),
                "official_domains": sorted(set(existing.get("official_domains", [])) | set(official_domains)),
                "product_category": product_category or existing.get("product_category", ""),
                "last_checked": checked_at,
                "last_changed": existing.get("last_changed") or checked_at,
            }
        )
        source_records, changed_source_ids = self._merge_sources(existing["sources"], sources, checked_at)
        paragraph_records = self._merge_paragraphs(existing["paragraphs"], sources, checked_at)
        claim_records, conflicts = self._merge_claims(
            existing["claims"],
            claims,
            changed_source_ids=changed_source_ids,
            checked_at=checked_at,
        )
        if changed_source_ids or len(claim_records) != len(existing["claims"]):
            profile["last_changed"] = checked_at
        usage = list(existing["usage_history"])
        usage.append(
            {
                "article_slug": article_slug,
                "article_intent": article_intent,
                "used_at": checked_at,
                "claim_ids": [row.get("claim_id") for row in claims],
            }
        )
        atomic_json(target / "profile.json", profile)
        atomic_json(target / "sources.json", {"schema_version": 1, "records": source_records})
        atomic_json(target / "paragraphs.json", {"schema_version": 1, "records": paragraph_records})
        atomic_json(target / "claims.json", {"schema_version": 1, "records": claim_records})
        atomic_json(target / "conflicts.json", {"schema_version": 1, "records": [*existing["conflicts"], *conflicts]})
        atomic_json(target / "usage_history.json", {"schema_version": 1, "records": usage})
        return self.load(value)

    def reusable_evidence(
        self,
        value: str,
        *,
        article_intent: str,
        required_categories: set[str] | None = None,
        same_root_slug: str = "",
    ) -> dict[str, Any]:
        profile = self.load(value)
        source_map = {row.get("source_id"): row for row in profile["sources"]}
        paragraphs = {row.get("paragraph_id"): row for row in profile["paragraphs"]}
        claims: list[dict[str, Any]] = []
        source_ids: set[str] = set()
        now = datetime.now(UTC)
        for row in profile["claims"]:
            if row.get("state") != "ACTIVE":
                continue
            if required_categories and row.get("claim_category") not in required_categories:
                continue
            source = source_map.get(row.get("source_id"))
            paragraph = paragraphs.get(row.get("paragraph_id"))
            if not source or not paragraph or source.get("status") not in {"verified", "approved"}:
                continue
            checked = self._parse_date(source.get("last_checked") or row.get("original_retrieval_date"))
            stale = checked is None or now - checked > timedelta(days=self.freshness_days)
            if stale:
                continue
            source_ids.add(str(row.get("source_id")))
            claims.append(
                {
                    **row.get("claim", {}),
                    "reused_from_entity": profile["entity_id"],
                    "original_claim_id": row.get("claim_id"),
                    "original_source_id": row.get("source_id"),
                    "original_retrieval_date": row.get("original_retrieval_date"),
                    "current_freshness_status": "fresh",
                    "refresh_required": False,
                    "reuse_reason": (
                        f"Exact entity match; category supports {article_intent or 'the requested article'}."
                    ),
                    "same_root_history_checked": bool(same_root_slug),
                }
            )
        return {
            "entity_id": profile["entity_id"],
            "claims": claims,
            "sources": [source_map[source_id]["source"] for source_id in source_ids],
        }

    def freshness_report(self, value: str) -> dict[str, Any]:
        profile = self.load(value)
        now = datetime.now(UTC)
        rows = []
        for source in profile["sources"]:
            checked = self._parse_date(source.get("last_checked"))
            expired = checked is None or now - checked > timedelta(days=self.freshness_days)
            rows.append(
                {
                    "source_id": source.get("source_id"),
                    "url": source.get("url"),
                    "last_checked": source.get("last_checked"),
                    "status": "EXPIRED" if expired else "FRESH",
                    "refresh_required": expired,
                }
            )
        return {"entity_id": profile["entity_id"], "freshness_days": self.freshness_days, "sources": rows}

    def _merge_sources(
        self,
        existing: list[dict[str, Any]],
        sources: list[dict[str, Any]],
        checked_at: str,
    ) -> tuple[list[dict[str, Any]], set[str]]:
        records = list(existing)
        changed: set[str] = set()
        for source in sources:
            source_id = str(source.get("source_id") or "")
            url = str(source.get("canonical_url") or source.get("url") or "")
            content_hash = str(source.get("content_hash") or "")
            current = next((row for row in records if row.get("url") == url), None)
            version = {
                "content_hash": content_hash,
                "retrieved_at": source.get("retrieved_at"),
                "paragraph_ids": [row.get("paragraph_id") for row in source.get("paragraphs", [])],
            }
            if current is None:
                records.append(
                    {
                        "source_id": source_id,
                        "url": url,
                        "source_family": source.get("source_type"),
                        "status": source.get("verification_status") or "approved",
                        "first_seen": checked_at,
                        "last_checked": checked_at,
                        "last_changed": checked_at,
                        "content_hash": content_hash,
                        "versions": [version],
                        "source": source,
                    }
                )
                changed.add(source_id)
            else:
                current["last_checked"] = checked_at
                current["source"] = source
                if current.get("content_hash") != content_hash:
                    current["content_hash"] = content_hash
                    current["last_changed"] = checked_at
                    current.setdefault("versions", []).append(version)
                    changed.add(str(current.get("source_id")))
        return records, changed

    @staticmethod
    def _merge_paragraphs(
        existing: list[dict[str, Any]],
        sources: list[dict[str, Any]],
        checked_at: str,
    ) -> list[dict[str, Any]]:
        records = list(existing)
        for source in sources:
            for paragraph in source.get("paragraphs", []):
                fingerprint = hashlib.sha256(str(paragraph.get("text") or "").encode("utf-8")).hexdigest()
                if any(row.get("content_hash") == fingerprint for row in records):
                    continue
                records.append(
                    {
                        **paragraph,
                        "source_id": source.get("source_id"),
                        "source_url": source.get("canonical_url") or source.get("url"),
                        "content_hash": fingerprint,
                        "first_seen": checked_at,
                        "last_checked": checked_at,
                        "evidence_strength": "direct_excerpt",
                    }
                )
        return records

    @staticmethod
    def _merge_claims(
        existing: list[dict[str, Any]],
        claims: list[dict[str, Any]],
        *,
        changed_source_ids: set[str],
        checked_at: str,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        records = [dict(row) for row in existing]
        conflicts: list[dict[str, Any]] = []
        for row in records:
            if row.get("source_id") in changed_source_ids and row.get("state") == "ACTIVE":
                row["state"] = "STALE"
                row["state_changed_at"] = checked_at
        for claim in claims:
            fingerprint = hashlib.sha256(
                re.sub(r"\W+", " ", str(claim.get("exact_statement") or "").casefold()).strip().encode("utf-8")
            ).hexdigest()
            active_same = next(
                (row for row in records if row.get("fingerprint") == fingerprint and row.get("state") == "ACTIVE"),
                None,
            )
            if active_same:
                active_same["last_checked"] = checked_at
                continue
            category = claim.get("claim_category")
            possible_conflicts = [
                row
                for row in records
                if row.get("state") == "ACTIVE"
                and row.get("claim_category") == category
                and category in {"pricing", "availability", "compatibility"}
            ]
            state = "ACTIVE"
            if possible_conflicts:
                state = "CONFLICTED"
                for old in possible_conflicts:
                    old["state"] = "CONFLICTED"
                conflicts.append(
                    {
                        "conflict_id": f"conflict-{len(conflicts) + 1:04d}",
                        "claim_category": category,
                        "claim_ids": [old.get("claim_id") for old in possible_conflicts] + [claim.get("claim_id")],
                        "detected_at": checked_at,
                        "resolution": "Use cautious language and refresh the newest official source.",
                    }
                )
            records.append(
                {
                    "claim_id": claim.get("claim_id"),
                    "source_id": claim.get("source_id"),
                    "paragraph_id": claim.get("paragraph_id"),
                    "claim_category": category,
                    "fingerprint": fingerprint,
                    "state": state,
                    "first_seen": checked_at,
                    "last_checked": checked_at,
                    "original_retrieval_date": claim.get("freshness"),
                    "limitations": claim.get("limitations"),
                    "prohibited_extrapolations": claim.get("prohibited_extrapolations", []),
                    "confidence": claim.get("confidence"),
                    "entity_scope": claim.get("entity"),
                    "permitted_reuse": claim.get("allowed_usage"),
                    "claim": claim,
                }
            )
        return records, conflicts

    @staticmethod
    def _parse_date(value: Any) -> datetime | None:
        try:
            return datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
        except ValueError:
            return None
