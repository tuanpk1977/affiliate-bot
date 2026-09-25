from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .storage import atomic_write_json, atomic_write_text


SCHEMA_VERSION = "entity_graph_quality_gate_v1"
GENERIC_NAMES = {
    "ai",
    "company",
    "developer",
    "model",
    "platform",
    "product",
    "review",
    "software",
    "source",
    "tool",
}
OFFICIAL_SOURCE_TYPES = {"company", "product", "model", "developer_tool"}
SYMMETRIC_RELATIONS = {"PRODUCT_COMPETES_WITH_PRODUCT"}
LOCAL_ONLY_HOSTS = {"127.0.0.1", "localhost", "0.0.0.0"}


def _norm(value: Any) -> str:
    return " ".join(str(value or "").casefold().split())


def _evidence_exists(root: Path, evidence: dict[str, Any]) -> tuple[bool, str]:
    source = str(evidence.get("source") or "").strip()
    kind = str(evidence.get("source_kind") or "").strip()
    if not source:
        return False, "missing evidence source"
    if kind == "local_file":
        path = Path(source)
        if not path.is_absolute():
            path = root / path
        return path.is_file(), "" if path.is_file() else "local evidence path does not exist"
    parsed = urlparse(source)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return False, "malformed evidence URL"
    if parsed.hostname.casefold() in LOCAL_ONLY_HOSTS or parsed.hostname.casefold().endswith(
        (".local", ".test", ".invalid")
    ):
        return False, "local or staging URL used as public evidence"
    return True, ""


class EntityGraphQualityGate:
    """Audit a graph artifact without promoting, merging, or mutating graph data."""

    def __init__(
        self,
        *,
        root: Path,
        duplicate_rate_limit: float = 0.01,
        suspicious_hub_degree: int = 100,
        minimum_evidence_coverage: float = 0.98,
    ) -> None:
        self.root = root.resolve()
        self.duplicate_rate_limit = duplicate_rate_limit
        self.suspicious_hub_degree = suspicious_hub_degree
        self.minimum_evidence_coverage = minimum_evidence_coverage

    def validate(self, graph: dict[str, Any]) -> dict[str, Any]:
        entities = [row for row in graph.get("entities", []) if isinstance(row, dict)]
        relations = [row for row in graph.get("relations", []) if isinstance(row, dict)]
        entity_by_id = {str(row.get("entity_id") or ""): row for row in entities}
        entity_types = Counter(str(row.get("entity_type") or "unknown") for row in entities)
        relation_types = Counter(str(row.get("relation_type") or "unknown") for row in relations)

        exact_keys: Counter[tuple[str, str, str, str]] = Counter()
        directional_keys: set[tuple[str, str, str]] = set()
        degree: Counter[str] = Counter()
        self_relations: list[dict[str, Any]] = []
        broken_evidence: list[dict[str, Any]] = []
        low_confidence: list[dict[str, Any]] = []
        similarity_only: list[dict[str, Any]] = []
        valid_evidence_count = 0
        for relation in relations:
            source = str(relation.get("source_entity_id") or "")
            target = str(relation.get("target_entity_id") or "")
            relation_type = str(relation.get("relation_type") or "")
            evidence = relation.get("evidence") if isinstance(relation.get("evidence"), dict) else {}
            evidence_source = str(evidence.get("source") or "")
            exact_keys[(source, relation_type, target, evidence_source)] += 1
            directional_keys.add((source, relation_type, target))
            degree[source] += 1
            degree[target] += 1
            if source == target:
                self_relations.append(relation)
            valid, reason = _evidence_exists(self.root, evidence)
            if valid:
                valid_evidence_count += 1
            else:
                broken_evidence.append({"reason": reason, "relation": relation})
            confidence = float(relation.get("confidence") or 0.0)
            if confidence < 0.6:
                low_confidence.append(relation)
            note = _norm(evidence.get("note"))
            if any(token in note for token in ("title similarity", "slug similarity", "name similarity")):
                similarity_only.append(relation)

        duplicate_count = sum(count - 1 for count in exact_keys.values() if count > 1)
        duplicate_rate = duplicate_count / max(1, len(relations))
        symmetric_duplicates: list[dict[str, str]] = []
        for source, relation_type, target in sorted(directional_keys):
            if (
                relation_type in SYMMETRIC_RELATIONS
                and source < target
                and (target, relation_type, source) in directional_keys
            ):
                symmetric_duplicates.append(
                    {
                        "source_entity_id": source,
                        "relation_type": relation_type,
                        "target_entity_id": target,
                    }
                )

        generic_entities = [
            row
            for row in entities
            if _norm(row.get("canonical_name")) in GENERIC_NAMES
        ]
        entities_from_weak_names = [
            row
            for row in entities
            if any(
                token in _norm(note)
                for note in row.get("notes", [])
                if isinstance(note, str)
                for token in ("filename", "heading", "generic keyword")
            )
        ]
        missing_official = [
            row
            for row in entities
            if row.get("entity_type") in OFFICIAL_SOURCE_TYPES
            and not row.get("official_urls")
            and not row.get("repository_urls")
        ]
        official_coverage: dict[str, dict[str, Any]] = {}
        for entity_type in sorted(OFFICIAL_SOURCE_TYPES):
            rows = [row for row in entities if row.get("entity_type") == entity_type]
            covered = sum(
                1 for row in rows if row.get("official_urls") or row.get("repository_urls")
            )
            official_coverage[entity_type] = {
                "total": len(rows),
                "covered": covered,
                "coverage": round(covered / max(1, len(rows)), 4),
            }

        aliases: defaultdict[str, set[str]] = defaultdict(set)
        for row in entities:
            entity_id = str(row.get("entity_id") or "")
            aliases[_norm(row.get("canonical_name"))].add(entity_id)
            for alias in row.get("aliases", []):
                aliases[_norm(alias)].add(entity_id)
        alias_conflicts = [
            {"alias": alias, "entity_ids": sorted(ids)}
            for alias, ids in sorted(aliases.items())
            if alias and len(ids) > 1
        ]
        suspicious_hubs = [
            {
                "entity_id": entity_id,
                "canonical_name": entity_by_id.get(entity_id, {}).get("canonical_name", ""),
                "entity_type": entity_by_id.get(entity_id, {}).get("entity_type", ""),
                "degree": count,
            }
            for entity_id, count in degree.most_common(50)
            if count >= self.suspicious_hub_degree
        ]
        article_hubs = [
            row for row in suspicious_hubs if row["entity_type"] == "article"
        ]
        orphan_ids = [
            entity_id for entity_id in entity_by_id if degree.get(entity_id, 0) == 0
        ]
        unresolved = [
            row
            for row in entities
            if row.get("verification_status") in {"unknown", "unverified", "research_candidate"}
            or row.get("unknown_or_unverified")
        ]
        confidence_distribution = Counter(
            (
                "high"
                if float(row.get("confidence") or 0) >= 0.8
                else "medium"
                if float(row.get("confidence") or 0) >= 0.6
                else "low"
            )
            for row in relations
        )
        evidence_coverage = valid_evidence_count / max(1, len(relations))

        blocking: list[str] = []
        warnings: list[str] = []
        if self_relations:
            blocking.append(f"{len(self_relations)} self-relation(s) detected")
        if duplicate_rate > self.duplicate_rate_limit:
            blocking.append(
                f"duplicate relation rate {duplicate_rate:.2%} exceeds "
                f"{self.duplicate_rate_limit:.2%}"
            )
        if broken_evidence:
            blocking.append(f"{len(broken_evidence)} broken evidence reference(s)")
        if evidence_coverage < self.minimum_evidence_coverage:
            blocking.append(
                f"relation evidence coverage {evidence_coverage:.2%} is below "
                f"{self.minimum_evidence_coverage:.2%}"
            )
        if relations and len(low_confidence) / len(relations) > 0.5:
            blocking.append("more than half of graph relations are low confidence")
        if generic_entities:
            warnings.append(f"{len(generic_entities)} generic entity name(s) require filtering")
        if missing_official:
            warnings.append(
                f"{len(missing_official)} company/product/model/tool entities lack official sources"
            )
        if suspicious_hubs:
            warnings.append(f"{len(suspicious_hubs)} suspicious high-degree hub(s)")
        if alias_conflicts:
            warnings.append(f"{len(alias_conflicts)} alias conflict(s)")
        if similarity_only:
            warnings.append(f"{len(similarity_only)} similarity-only relation(s)")
        if symmetric_duplicates:
            warnings.append(f"{len(symmetric_duplicates)} unnecessary symmetric pair(s)")
        result = "FAIL" if blocking else "PASS_WITH_WARNINGS" if warnings else "PASS"

        def good_entity(row: dict[str, Any]) -> bool:
            return (
                float(row.get("confidence") or 0) >= 0.8
                and bool(row.get("source_evidence"))
                and row not in generic_entities
            )

        def suspicious_entity(row: dict[str, Any]) -> bool:
            return (
                row in generic_entities
                or row in missing_official
                or row in unresolved
                or degree.get(str(row.get("entity_id") or ""), 0) >= self.suspicious_hub_degree
            )

        good_relations = [
            row
            for row in relations
            if float(row.get("confidence") or 0) >= 0.8
            and _evidence_exists(
                self.root,
                row.get("evidence") if isinstance(row.get("evidence"), dict) else {},
            )[0]
        ]
        suspicious_relations = list(self_relations) + low_confidence + [
            row["relation"] for row in broken_evidence
        ]
        return {
            "schema_version": SCHEMA_VERSION,
            "generated_at": graph.get("generated_at", ""),
            "quality_gate_result": result,
            "blocking": blocking,
            "warnings": warnings,
            "entity_count_by_type": dict(sorted(entity_types.items())),
            "relation_count_by_type": dict(sorted(relation_types.items())),
            "metrics": {
                "entity_count": len(entities),
                "relation_count": len(relations),
                "duplicate_relation_count": duplicate_count,
                "duplicate_rate": round(duplicate_rate, 6),
                "symmetric_duplicate_count": len(symmetric_duplicates),
                "self_relation_count": len(self_relations),
                "similarity_only_relation_count": len(similarity_only),
                "generic_entity_count": len(generic_entities),
                "weak_name_entity_count": len(entities_from_weak_names),
                "missing_official_source_count": len(missing_official),
                "broken_evidence_path_count": len(broken_evidence),
                "alias_conflict_count": len(alias_conflicts),
                "suspicious_hub_count": len(suspicious_hubs),
                "suspicious_article_hub_count": len(article_hubs),
                "orphan_count": len(orphan_ids),
                "unresolved_count": len(unresolved),
                "evidence_coverage": round(evidence_coverage, 6),
            },
            "official_source_coverage": official_coverage,
            "confidence_distribution": dict(sorted(confidence_distribution.items())),
            "top_entities_by_degree": [
                {
                    "entity_id": entity_id,
                    "canonical_name": entity_by_id.get(entity_id, {}).get("canonical_name", ""),
                    "entity_type": entity_by_id.get(entity_id, {}).get("entity_type", ""),
                    "degree": count,
                }
                for entity_id, count in degree.most_common(50)
            ],
            "generic_entities": generic_entities[:200],
            "missing_official_sources": missing_official[:200],
            "suspicious_hubs": suspicious_hubs,
            "self_relations": self_relations[:200],
            "broken_evidence_paths": broken_evidence[:200],
            "alias_conflicts": alias_conflicts[:200],
            "symmetric_duplicates": symmetric_duplicates[:200],
            "sample_good_entities": [row for row in entities if good_entity(row)][:20],
            "sample_suspicious_entities": [
                row for row in entities if suspicious_entity(row)
            ][:20],
            "sample_good_relations": good_relations[:20],
            "sample_suspicious_relations": suspicious_relations[:20],
            "recommended_fixes": [
                "Keep generic and unresolved entities out of verified writer facts.",
                "Require existing local evidence or valid public URLs for writer-authorized facts.",
                "Review suspicious hubs and alias conflicts manually; never auto-merge them.",
                "Compute official-source coverage only for entity types that require it.",
            ],
            "safety": {
                "recommendation_only": True,
                "graph_modified": False,
                "merge_performed": False,
                "writer_authorization_granted": result != "FAIL",
            },
        }

    def write(self, payload: dict[str, Any], *, date: str) -> dict[str, str]:
        intelligence_root = self.root / "data" / "intelligence"
        report_root = self.root / "data" / "reports" / "operations_intelligence"
        json_path = intelligence_root / "entities" / "quality" / f"entity_graph_quality_{date}.json"
        report_path = report_root / f"entity_graph_quality_gate_{date}.md"
        atomic_write_json(json_path, payload, intelligence_root=intelligence_root)
        atomic_write_text(
            report_path,
            build_quality_report(payload),
            intelligence_root=self.root / "data",
        )
        return {"json": str(json_path), "report": str(report_path)}


def build_quality_report(payload: dict[str, Any]) -> str:
    metrics = payload["metrics"]
    lines = [
        "# Entity Graph Quality Gate",
        "",
        f"- Result: **{payload['quality_gate_result']}**",
        f"- Entities: {metrics['entity_count']}",
        f"- Relations: {metrics['relation_count']}",
        f"- Evidence coverage: {metrics['evidence_coverage']:.2%}",
        f"- Duplicate rate: {metrics['duplicate_rate']:.2%}",
        f"- Self relations: {metrics['self_relation_count']}",
        f"- Broken evidence paths: {metrics['broken_evidence_path_count']}",
        f"- Generic entities: {metrics['generic_entity_count']}",
        f"- Missing official sources: {metrics['missing_official_source_count']}",
        f"- Suspicious hubs: {metrics['suspicious_hub_count']}",
        "",
        "## Blocking",
        "",
        *([f"- {row}" for row in payload["blocking"]] or ["- None"]),
        "",
        "## Warnings",
        "",
        *([f"- {row}" for row in payload["warnings"]] or ["- None"]),
        "",
        "## Entity Count By Type",
        "",
        *[f"- {key}: {value}" for key, value in payload["entity_count_by_type"].items()],
        "",
        "## Relation Count By Type",
        "",
        *[f"- {key}: {value}" for key, value in payload["relation_count_by_type"].items()],
        "",
        "## Official Source Coverage",
        "",
        *[
            f"- {key}: {value['covered']}/{value['total']} ({value['coverage']:.2%})"
            for key, value in payload["official_source_coverage"].items()
        ],
        "",
        "## Confidence Distribution",
        "",
        *[f"- {key}: {value}" for key, value in payload["confidence_distribution"].items()],
        "",
        "## Top 50 Entities By Degree",
        "",
        *[
            f"- {row['canonical_name']} ({row['entity_type']}): {row['degree']}"
            for row in payload["top_entities_by_degree"]
        ],
        "",
        "## Samples",
        "",
        f"- Good entities: {len(payload['sample_good_entities'])}",
        f"- Suspicious entities: {len(payload['sample_suspicious_entities'])}",
        f"- Good relations: {len(payload['sample_good_relations'])}",
        f"- Suspicious relations: {len(payload['sample_suspicious_relations'])}",
        "",
        "Full samples and anomaly records are stored in the JSON report.",
        "",
        "## Recommended Fixes",
        "",
        *[f"- {row}" for row in payload["recommended_fixes"]],
        "",
        "No graph data, production content, queue, approval, or publish state was changed.",
        "",
    ]
    return "\n".join(lines)
