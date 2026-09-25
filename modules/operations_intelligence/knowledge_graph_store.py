from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from .feature_flags import feature_enabled
from .models import ENTITY_TYPES, RELATION_TYPES, normalize_name
from .storage import atomic_write_json, atomic_write_text


SCHEMA_VERSION = 1
STORE_SCHEMA = "knowledge_graph_sqlite_v1"


MIGRATION_001_PATH = Path(__file__).with_name("migrations") / "001_knowledge_graph.sql"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clamp(value: Any) -> float:
    try:
        return round(max(0.0, min(1.0, float(value))), 4)
    except (TypeError, ValueError):
        return 0.0


def _hash(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


class KnowledgeGraphStore:
    """Versioned SQLite storage for advisory graph data only.

    The store has no imports from approval, publishing, deployment, or weekly
    planning modules. Deletion APIs are intentionally absent.
    """

    def __init__(self, *, root: Path, db_path: Path | None = None) -> None:
        self.root = root.resolve()
        self.intelligence_root = self.root / "data" / "intelligence"
        self.db_path = (
            db_path
            or self.intelligence_root / "knowledge_graph" / "knowledge_graph.sqlite3"
        ).resolve()
        if self.intelligence_root.resolve() not in self.db_path.parents:
            raise ValueError("Knowledge graph database must stay under data/intelligence.")

    @contextmanager
    def connect(self, *, create_parent: bool = False) -> Iterator[sqlite3.Connection]:
        if create_parent:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
        finally:
            connection.close()

    def migration_plan(self) -> dict[str, Any]:
        applied: list[int] = []
        if self.db_path.is_file():
            with self.connect() as connection:
                exists = connection.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
                ).fetchone()
                if exists:
                    applied = [
                        int(row[0])
                        for row in connection.execute(
                            "SELECT version FROM schema_migrations ORDER BY version"
                        )
                    ]
        return {
            "schema": STORE_SCHEMA,
            "schema_version": SCHEMA_VERSION,
            "database": str(self.db_path),
            "applied_versions": applied,
            "pending_versions": [version for version in (1,) if version not in applied],
            "idempotent": True,
            "history_deletion_supported": False,
        }

    def migrate(self) -> dict[str, Any]:
        before = self.migration_plan()
        with self.connect(create_parent=True) as connection:
            connection.executescript(MIGRATION_001_PATH.read_text(encoding="utf-8"))
            connection.execute(
                "INSERT OR IGNORE INTO schema_migrations(version, name, applied_at) VALUES(1, ?, ?)",
                ("initial_knowledge_graph", _utc_now()),
            )
            connection.commit()
        after = self.migration_plan()
        after["newly_applied"] = [
            version for version in after["applied_versions"] if version not in before["applied_versions"]
        ]
        return after

    @staticmethod
    def _identity_key(entity: dict[str, Any]) -> str:
        domain = str(entity.get("official_domain") or "").casefold().strip()
        if domain:
            return domain
        urls = entity.get("official_urls") or entity.get("repository_urls") or []
        return str(urls[0]).casefold().strip() if isinstance(urls, list) and urls else ""

    @staticmethod
    def _provenance_rows(entity_or_relation: dict[str, Any]) -> list[dict[str, Any]]:
        evidence = entity_or_relation.get("source_evidence")
        if not isinstance(evidence, list):
            one = entity_or_relation.get("evidence")
            evidence = [one] if isinstance(one, dict) else []
        return [row for row in evidence if isinstance(row, dict) and row.get("source")]

    def _insert_provenance(
        self,
        connection: sqlite3.Connection,
        *,
        subject_type: str,
        subject_id: str,
        evidence: dict[str, Any],
        article_slug: str = "",
        batch_date: str = "",
    ) -> None:
        source = str(evidence.get("source") or "").strip()
        source_kind = str(evidence.get("source_kind") or "").strip()
        source_url = source if source_kind == "public_url" else ""
        source_file = source if source_kind != "public_url" else ""
        observed = str(evidence.get("observed_at") or _utc_now())
        note = str(evidence.get("note") or "")
        if not source_file:
            ledger_match = re.search(r"Claim ledger:\s*([^\s]+)", note)
            if ledger_match:
                source_file = ledger_match.group(1)
        context_path = source_file.replace("\\", "/")
        if not article_slug:
            article_match = re.search(r"(?:^|/)data/research/([^/]+)/", context_path)
            if article_match:
                article_slug = article_match.group(1)
        if not batch_date:
            date_match = re.search(r"(?:^|/)(20\d{2}-\d{2}-\d{2})(?:/|$)", context_path)
            batch_date = date_match.group(1) if date_match else observed[:10]
        confidence = _clamp(evidence.get("confidence"))
        human_verified = int(bool(evidence.get("human_verified")))
        provenance_id = _hash(
            subject_type, subject_id, source_file, batch_date, article_slug, source_url
        )
        connection.execute(
            """
            INSERT INTO provenance(
                provenance_id, subject_type, subject_id, source_file, batch_date,
                article_slug, source_url, observed_at, confidence, human_verified, note
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(provenance_id) DO UPDATE SET
                observed_at=excluded.observed_at,
                confidence=MAX(provenance.confidence, excluded.confidence),
                human_verified=MAX(provenance.human_verified, excluded.human_verified),
                note=CASE WHEN excluded.note <> '' THEN excluded.note ELSE provenance.note END
            """,
            (
                provenance_id,
                subject_type,
                subject_id,
                source_file,
                batch_date,
                article_slug,
                source_url,
                observed,
                confidence,
                human_verified,
                note,
            ),
        )

    def ingest(self, graph: dict[str, Any]) -> dict[str, Any]:
        self.migrate()
        generated_at = str(graph.get("generated_at") or _utc_now())
        entities = [row for row in graph.get("entities", []) if isinstance(row, dict)]
        relations = [row for row in graph.get("relations", []) if isinstance(row, dict)]
        inserted_entities = inserted_relations = 0
        with self.connect() as connection:
            before_entities = int(connection.execute("SELECT COUNT(*) FROM entities").fetchone()[0])
            before_relations = int(
                connection.execute("SELECT COUNT(*) FROM relationships").fetchone()[0]
            )
            for entity in entities:
                entity_id = str(entity.get("entity_id") or "").strip()
                entity_type = str(entity.get("entity_type") or "").strip()
                name = str(entity.get("canonical_name") or "").strip()
                if not entity_id or entity_type not in ENTITY_TYPES or not name:
                    continue
                confidence = _clamp(entity.get("confidence"))
                human_verified = int(bool(entity.get("human_verified")))
                attributes = {
                    key: value
                    for key, value in entity.items()
                    if key
                    not in {
                        "entity_id", "entity_type", "canonical_name", "aliases",
                        "source_evidence", "confidence", "verification_status",
                    }
                }
                connection.execute(
                    """
                    INSERT INTO entities(
                        entity_id, entity_type, canonical_name, normalized_name, identity_key,
                        verification_status, confidence, human_verified, attributes_json,
                        first_seen_at, updated_at
                    ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(entity_id) DO UPDATE SET
                        canonical_name=excluded.canonical_name,
                        verification_status=CASE
                            WHEN entities.human_verified=1 THEN entities.verification_status
                            ELSE excluded.verification_status END,
                        confidence=MAX(entities.confidence, excluded.confidence),
                        human_verified=MAX(entities.human_verified, excluded.human_verified),
                        attributes_json=excluded.attributes_json,
                        updated_at=excluded.updated_at
                    """,
                    (
                        entity_id, entity_type, name, normalize_name(name), self._identity_key(entity),
                        str(entity.get("verification_status") or "unknown"), confidence,
                        human_verified, json.dumps(attributes, ensure_ascii=False, sort_keys=True),
                        str(entity.get("first_seen_at") or generated_at), generated_at,
                    ),
                )
                for alias in {name, *[str(value) for value in entity.get("aliases", [])]}:
                    normalized = normalize_name(alias)
                    if normalized:
                        connection.execute(
                            "INSERT OR IGNORE INTO aliases(entity_id, alias, normalized_alias, created_at) "
                            "VALUES(?, ?, ?, ?)",
                            (entity_id, alias.strip(), normalized, generated_at),
                        )
                slug_fact = entity.get("known_facts", {}).get("slug", {})
                article_slug = str(slug_fact.get("value") or "") if isinstance(slug_fact, dict) else ""
                for evidence in self._provenance_rows(entity):
                    self._insert_provenance(
                        connection,
                        subject_type="entity",
                        subject_id=entity_id,
                        evidence=evidence,
                        article_slug=article_slug,
                    )
            for relation in relations:
                source = str(relation.get("source_entity_id") or "").strip()
                target = str(relation.get("target_entity_id") or "").strip()
                relation_type = str(relation.get("relation_type") or "").strip()
                if (
                    not source
                    or not target
                    or source == target
                    or relation_type not in RELATION_TYPES
                ):
                    continue
                if not connection.execute(
                    "SELECT 1 FROM entities WHERE entity_id=?", (source,)
                ).fetchone() or not connection.execute(
                    "SELECT 1 FROM entities WHERE entity_id=?", (target,)
                ).fetchone():
                    continue
                relationship_id = _hash(source, relation_type, target)
                status = str(relation.get("status") or "candidate")
                if status not in {"candidate", "needs_review", "verified"}:
                    status = "needs_review"
                confidence = _clamp(relation.get("confidence"))
                human_verified = int(bool(relation.get("human_verified")))
                connection.execute(
                    """
                    INSERT INTO relationships(
                        relationship_id, source_entity_id, relation_type, target_entity_id,
                        status, confidence, human_verified, created_at, updated_at
                    ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(relationship_id) DO UPDATE SET
                        status=CASE WHEN relationships.human_verified=1 THEN relationships.status
                            WHEN excluded.status='verified' AND excluded.human_verified=0
                                THEN 'needs_review'
                            ELSE excluded.status END,
                        confidence=MAX(relationships.confidence, excluded.confidence),
                        human_verified=MAX(relationships.human_verified, excluded.human_verified),
                        updated_at=excluded.updated_at
                    """,
                    (
                        relationship_id, source, relation_type, target, status, confidence,
                        human_verified, generated_at, generated_at,
                    ),
                )
                for evidence in self._provenance_rows(relation):
                    self._insert_provenance(
                        connection,
                        subject_type="relationship",
                        subject_id=relationship_id,
                        evidence=evidence,
                    )
            connection.commit()
            after_entities = int(connection.execute("SELECT COUNT(*) FROM entities").fetchone()[0])
            after_relations = int(
                connection.execute("SELECT COUNT(*) FROM relationships").fetchone()[0]
            )
            inserted_entities = after_entities - before_entities
            inserted_relations = after_relations - before_relations
        return {
            "schema": STORE_SCHEMA,
            "database": str(self.db_path),
            "input_entities": len(entities),
            "input_relations": len(relations),
            "inserted_entities": inserted_entities,
            "inserted_relations": inserted_relations,
            "idempotent": inserted_entities == 0 and inserted_relations == 0,
            "publication_state_changed": False,
        }

    def find_entities(self, query: str, *, entity_type: str = "") -> list[dict[str, Any]]:
        normalized = normalize_name(query)
        if not self.db_path.is_file() or not normalized:
            return []
        sql = """
            SELECT DISTINCT e.* FROM entities e
            LEFT JOIN aliases a ON a.entity_id=e.entity_id
            WHERE (e.normalized_name LIKE ? OR a.normalized_alias LIKE ?)
        """
        params: list[Any] = [f"%{normalized}%", f"%{normalized}%"]
        if entity_type:
            sql += " AND e.entity_type=?"
            params.append(entity_type)
        sql += " ORDER BY e.confidence DESC, e.canonical_name LIMIT 100"
        with self.connect() as connection:
            return [dict(row) for row in connection.execute(sql, params)]

    def related(self, entity_id: str, *, relation_type: str = "") -> list[dict[str, Any]]:
        if not self.db_path.is_file():
            return []
        sql = """
            SELECT r.*, target.canonical_name AS target_name,
                   target.entity_type AS target_type
            FROM relationships r
            JOIN entities target ON target.entity_id=r.target_entity_id
            WHERE r.source_entity_id=?
        """
        params: list[Any] = [entity_id]
        if relation_type:
            sql += " AND r.relation_type=?"
            params.append(relation_type)
        sql += " ORDER BY r.relation_type, target.canonical_name"
        with self.connect() as connection:
            return [dict(row) for row in connection.execute(sql, params)]

    def report(self) -> dict[str, Any]:
        if not self.db_path.is_file():
            return {
                "schema": STORE_SCHEMA,
                "database": str(self.db_path),
                "exists": False,
                "entity_count": 0,
                "relationship_count": 0,
            }
        with self.connect() as connection:
            entity_types = {
                row[0]: row[1]
                for row in connection.execute(
                    "SELECT entity_type, COUNT(*) FROM entities GROUP BY entity_type ORDER BY entity_type"
                )
            }
            relation_types = {
                row[0]: row[1]
                for row in connection.execute(
                    "SELECT relation_type, COUNT(*) FROM relationships "
                    "GROUP BY relation_type ORDER BY relation_type"
                )
            }
            statuses = {
                row[0]: row[1]
                for row in connection.execute(
                    "SELECT status, COUNT(*) FROM relationships GROUP BY status ORDER BY status"
                )
            }
            provenance_count = int(connection.execute("SELECT COUNT(*) FROM provenance").fetchone()[0])
        return {
            "schema": STORE_SCHEMA,
            "schema_version": SCHEMA_VERSION,
            "database": str(self.db_path),
            "exists": True,
            "entity_count": sum(entity_types.values()),
            "relationship_count": sum(relation_types.values()),
            "provenance_count": provenance_count,
            "entity_types": entity_types,
            "relationship_types": relation_types,
            "relationship_statuses": statuses,
            "recommendation_only": True,
            "publication_state_changed": False,
        }


class KnowledgeGraphService:
    def __init__(self, *, root: Path, db_path: Path | None = None) -> None:
        self.root = root.resolve()
        self.store = KnowledgeGraphStore(root=self.root, db_path=db_path)

    def build(self, graph: dict[str, Any], *, mode: str = "dry-run") -> dict[str, Any]:
        if mode not in {"dry-run", "write"}:
            raise ValueError("mode must be dry-run or write")
        enabled = feature_enabled(self.root, "knowledge_graph.enabled")
        result: dict[str, Any] = {
            "schema": STORE_SCHEMA,
            "mode": mode,
            "enabled": enabled,
            "input_entities": len(graph.get("entities", [])),
            "input_relations": len(graph.get("relations", [])),
            "recommendation_only": True,
            "publication_state_changed": False,
        }
        if mode == "write" and not enabled:
            result.update({"status": "DISABLED", "reason": "knowledge_graph.enabled is false"})
            return result
        if mode == "dry-run":
            result.update({"status": "DRY_RUN", "migration": self.store.migration_plan()})
            return result
        result.update({"status": "WRITTEN", "ingest": self.store.ingest(graph)})
        report = self.store.report()
        report_dir = self.root / "data" / "intelligence" / "knowledge_graph"
        json_path = report_dir / "report.json"
        markdown_path = report_dir / "report.md"
        atomic_write_json(json_path, report, intelligence_root=self.store.intelligence_root)
        lines = [
            "# Internal Knowledge Graph (read-only report)", "",
            f"- Schema: {report['schema']}",
            f"- Entities: {report['entity_count']}",
            f"- Relationships: {report['relationship_count']}",
            f"- Provenance records: {report['provenance_count']}", "",
            "## Entity types", "",
            *[f"- {key}: {value}" for key, value in report["entity_types"].items()], "",
            "## Relationship types", "",
            *[f"- {key}: {value}" for key, value in report["relationship_types"].items()], "",
            "This graph is recommendation-only and cannot approve or publish content.", "",
        ]
        atomic_write_text(
            markdown_path, "\n".join(lines), intelligence_root=self.store.intelligence_root
        )
        result["outputs"] = {"json": str(json_path), "markdown": str(markdown_path)}
        return result
