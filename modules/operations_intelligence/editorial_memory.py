from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from collections import Counter
from datetime import date, datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .inventory import article_inventory, internal_slug, schema_types
from .feature_flags import feature_enabled
from .knowledge_graph_store import KnowledgeGraphStore
from .storage import atomic_write_json


SCHEMA_VERSION = "editorial_memory_v1"
SQLITE_SCHEMA_VERSION = "editorial_memory_sqlite_v2"
STATES = {"pending", "approved", "rejected", "best", "archive"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalise(value: Any) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", str(value or "").casefold()))


def _values(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, dict):
        return [str(key) for key in value if str(key).strip()]
    if isinstance(value, list):
        output: list[str] = []
        for row in value:
            if isinstance(row, dict):
                candidate = row.get("name") or row.get("title") or row.get("claim") or row.get("url") or row.get("text")
            else:
                candidate = row
            if str(candidate or "").strip():
                output.append(str(candidate).strip())
        return output
    return []


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _set_similarity(left: Any, right: Any) -> float:
    a = {_normalise(value) for value in _values(left) if _normalise(value)}
    b = {_normalise(value) for value in _values(right) if _normalise(value)}
    if not a and not b:
        return 0.0
    return len(a & b) / len(a | b)


def _text_similarity(left: Any, right: Any) -> float:
    a, b = _normalise(left), _normalise(right)
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def _fingerprint(payload: dict[str, Any]) -> str:
    return hashlib.sha256(_json(payload).encode("utf-8")).hexdigest()


def _record_id(slug: str, batch_date: str) -> str:
    digest = hashlib.sha256(f"{slug}|{batch_date}".encode("utf-8")).hexdigest()[:16]
    return f"memory-{digest}"


def _thesis_pattern(paragraphs: list[str]) -> str:
    if not paragraphs:
        return ""
    words = paragraphs[0].split()
    return " ".join(words[:32])


class EditorialMemoryStore:
    """Store compact editorial metadata; never copy complete article bodies."""

    def __init__(self, *, root: Path, memory_root: Path | None = None) -> None:
        self.root = root.resolve()
        self.memory_root = memory_root or self.root / "editorial_memory"
        self.database_path = self.root / "data" / "intelligence" / "editorial_memory" / "editorial_memory.sqlite3"

    def migrate(self, database_path: Path | None = None) -> dict[str, Any]:
        """Apply the append-only Phase 2 schema. Safe to run repeatedly."""
        path = (database_path or self.database_path).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        migration = Path(__file__).with_name("migrations") / "002_editorial_memory.sql"
        sql = migration.read_text(encoding="utf-8")
        with sqlite3.connect(path) as connection:
            connection.executescript(sql)
            connection.execute(
                "INSERT OR IGNORE INTO editorial_memory_migrations(migration_id, applied_at) VALUES(?, ?)",
                (SQLITE_SCHEMA_VERSION, _now()),
            )
            connection.commit()
            count = int(connection.execute("SELECT COUNT(*) FROM editorial_memory_snapshots").fetchone()[0])
        return {"schema_version": SQLITE_SCHEMA_VERSION, "database_path": str(path), "snapshot_count": count, "idempotent": True}

    @staticmethod
    def _read_json(path: Path) -> Any:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return {}

    def _research_values(self, slug: str, filename: str, keys: tuple[str, ...]) -> list[str]:
        payload = self._read_json(self.root / "data" / "research" / slug / filename)
        pools: list[Any] = []
        if isinstance(payload, list):
            pools.append(payload)
        elif isinstance(payload, dict):
            for key in keys:
                pools.append(payload.get(key))
        output: list[str] = []
        for pool in pools:
            output.extend(_values(pool))
        return sorted(dict.fromkeys(value for value in output if value))

    def _research_objects(self, slug: str, filename: str, keys: tuple[str, ...]) -> list[Any]:
        payload = self._read_json(self.root / "data" / "research" / slug / filename)
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict):
            for key in keys:
                if isinstance(payload.get(key), list):
                    return list(payload[key])
        return []

    def record_from_inventory(self, record: dict[str, Any]) -> dict[str, Any]:
        """Convert repository inventory into metadata only; full article bodies are excluded."""
        slug = str(record.get("slug") or "").strip()
        metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
        html = record.get("html") if isinstance(record.get("html"), dict) else {}
        links = [row for row in html.get("links") or [] if isinstance(row, dict)]
        related = sorted({internal_slug(str(row.get("href") or "")) for row in links if internal_slug(str(row.get("href") or ""))})
        entities = _values(metadata.get("entities")) or self._research_values(slug, "entities.json", ("entities", "items"))
        if feature_enabled(self.root, "knowledge_graph.enabled"):
            try:
                graph = KnowledgeGraphStore(root=self.root)
                graph_matches = [
                    *graph.find_entities(str(record.get("title") or "")),
                    *graph.find_entities(str(record.get("root_topic_id") or "")),
                ]
                entities.extend(str(row.get("canonical_name") or "") for row in graph_matches[:25])
            except (OSError, ValueError, sqlite3.Error):
                pass
        raw_claims = metadata.get("claims")
        claims: list[Any] = list(raw_claims) if isinstance(raw_claims, list) else []
        if not claims:
            claims = self._research_objects(slug, "FACT_LEDGER.json", ("claims", "facts", "items"))
        sources = _values(metadata.get("cited_sources") or metadata.get("verified_sources") or metadata.get("source_urls"))
        if not sources:
            sources = self._research_values(slug, "sources.json", ("sources", "items", "urls"))
        approval = str(metadata.get("approval_status") or metadata.get("human_approval_state") or record.get("editorial_state") or "")
        written = str(metadata.get("written_date") or metadata.get("created_at") or record.get("batch_date") or "")
        published = str(metadata.get("published_date") or metadata.get("published_at") or "")
        social = _values(metadata.get("social_derivatives"))
        if not social:
            social_root = self.root / "data" / "social_drafts"
            social = sorted(str(path.relative_to(self.root)) for path in social_root.glob(f"**/{slug}/*") if path.is_file()) if social_root.exists() else []
        return {
            "slug": slug,
            "title": str(record.get("title") or metadata.get("title") or ""),
            "root_topic": str(record.get("root_topic_id") or metadata.get("root_topic") or ""),
            "angle": str(record.get("daily_angle") or metadata.get("angle") or ""),
            "keyword": str(metadata.get("primary_keyword") or metadata.get("keyword") or ""),
            "entities": sorted(dict.fromkeys(entities)),
            "claims": claims,
            "cited_sources": sorted(dict.fromkeys(sources)),
            "approval_status": approval,
            "revision_reasons": _values(metadata.get("revision_reasons") or metadata.get("revision_reason")),
            "rejection_reasons": _values(metadata.get("rejection_reasons") or metadata.get("rejection_reason")),
            "written_date": written,
            "published_date": published,
            "related_articles": related,
            "social_derivatives": social,
            "source_path": str((html or {}).get("path") or record.get("draft_dir") or ""),
            "is_published": bool(record.get("is_published_local") or published),
        }

    def capture_history(
        self,
        records: list[dict[str, Any]] | None = None,
        *,
        database_path: Path | None = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        rows = [self.record_from_inventory(row) for row in (records if records is not None else article_inventory(self.root))]
        rows = [row for row in rows if row["slug"]]
        if dry_run:
            return {"schema_version": SQLITE_SCHEMA_VERSION, "dry_run": True, "record_count": len(rows), "records": rows}
        path = (database_path or self.database_path).resolve()
        self.migrate(path)
        inserted = 0
        with sqlite3.connect(path) as connection:
            connection.execute("PRAGMA foreign_keys=ON")
            for row in rows:
                timestamp = _now()
                connection.execute(
                    "INSERT OR IGNORE INTO editorial_memory_articles(slug, first_seen_at, last_seen_at) VALUES(?,?,?)",
                    (row["slug"], timestamp, timestamp),
                )
                connection.execute("UPDATE editorial_memory_articles SET last_seen_at=? WHERE slug=?", (timestamp, row["slug"]))
                article_id = int(connection.execute("SELECT article_id FROM editorial_memory_articles WHERE slug=?", (row["slug"],)).fetchone()[0])
                stable = dict(row)
                fingerprint = _fingerprint(stable)
                cursor = connection.execute(
                    """INSERT OR IGNORE INTO editorial_memory_snapshots(
                    article_id,fingerprint,title,root_topic,angle,keyword,entities_json,claims_json,cited_sources_json,
                    approval_status,revision_reasons_json,rejection_reasons_json,written_date,published_date,
                    related_articles_json,social_derivatives_json,source_path,captured_at,is_published)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (article_id, fingerprint, row["title"], row["root_topic"], row["angle"], row["keyword"],
                     _json(row["entities"]), _json(row["claims"]), _json(row["cited_sources"]), row["approval_status"],
                     _json(row["revision_reasons"]), _json(row["rejection_reasons"]), row["written_date"], row["published_date"],
                     _json(row["related_articles"]), _json(row["social_derivatives"]), row["source_path"], timestamp, int(row["is_published"])),
                )
                inserted += int(cursor.rowcount > 0)
                reasons = row["revision_reasons"] + row["rejection_reasons"]
                if row["approval_status"] or reasons:
                    event = {"slug": row["slug"], "status": row["approval_status"], "reasons": reasons, "written_date": row["written_date"], "published_date": row["published_date"]}
                    connection.execute(
                        "INSERT OR IGNORE INTO editorial_memory_events(article_id,event_fingerprint,event_type,status,reasons_json,occurred_at,source_path) VALUES(?,?,?,?,?,?,?)",
                        (article_id, _fingerprint(event), "editorial_state", row["approval_status"], _json(reasons), row["published_date"] or row["written_date"] or timestamp, row["source_path"]),
                    )
            connection.commit()
            total = int(connection.execute("SELECT COUNT(*) FROM editorial_memory_snapshots").fetchone()[0])
        return {"schema_version": SQLITE_SCHEMA_VERSION, "dry_run": False, "record_count": total, "inserted": inserted, "database_path": str(path)}

    def latest_records(self, database_path: Path | None = None) -> list[dict[str, Any]]:
        path = (database_path or self.database_path).resolve()
        if not path.is_file():
            return []
        query = """SELECT s.snapshot_id,a.slug,s.title,s.root_topic,s.angle,s.keyword,s.entities_json,s.claims_json,
        s.cited_sources_json,s.approval_status,s.revision_reasons_json,s.rejection_reasons_json,s.written_date,
        s.published_date,s.related_articles_json,s.social_derivatives_json,s.source_path,s.is_published
        FROM editorial_memory_snapshots s JOIN editorial_memory_articles a ON a.article_id=s.article_id
        WHERE s.snapshot_id=(SELECT s2.snapshot_id FROM editorial_memory_snapshots s2 WHERE s2.article_id=s.article_id ORDER BY s2.snapshot_id DESC LIMIT 1)"""
        keys = ("snapshot_id","slug","title","root_topic","angle","keyword","entities","claims","cited_sources","approval_status","revision_reasons","rejection_reasons","written_date","published_date","related_articles","social_derivatives","source_path","is_published")
        with sqlite3.connect(path) as connection:
            output = []
            for raw in connection.execute(query).fetchall():
                row = dict(zip(keys, raw))
                for key in ("entities","claims","cited_sources","revision_reasons","rejection_reasons","related_articles","social_derivatives"):
                    try:
                        row[key] = json.loads(row[key])
                    except (TypeError, json.JSONDecodeError):
                        row[key] = []
                row["is_published"] = bool(row["is_published"])
                output.append(row)
        return output

    def detect_duplicates(self, candidate: dict[str, Any], *, database_path: Path | None = None, persist: bool = False, exclude_same_slug: bool = False) -> dict[str, Any]:
        """Return advisory matches only. This method never blocks, deletes, or edits content."""
        candidate = dict(candidate)
        matches: list[dict[str, Any]] = []
        weights = {"title": .20, "slug": .15, "keyword": .15, "entity": .12, "claim": .16, "source": .10, "angle": .12}
        for row in self.latest_records(database_path):
            if exclude_same_slug and candidate.get("slug") and _normalise(candidate.get("slug")) == _normalise(row.get("slug")):
                continue
            scores = {
                "title": _text_similarity(candidate.get("title"), row.get("title")),
                "slug": _text_similarity(candidate.get("slug"), row.get("slug")),
                "keyword": _set_similarity(candidate.get("keyword"), row.get("keyword")),
                "entity": _set_similarity(candidate.get("entities"), row.get("entities")),
                "claim": _set_similarity(candidate.get("claims"), row.get("claims")),
                "source": _set_similarity(candidate.get("cited_sources"), row.get("cited_sources")),
                "angle": _text_similarity(candidate.get("angle"), row.get("angle")),
            }
            overall = sum(scores[key] * weights[key] for key in weights)
            if overall >= .35 or max(scores.values(), default=0) >= .82:
                matches.append({"slug": row["slug"], "title": row["title"], "snapshot_id": row["snapshot_id"], "overall_score": round(overall, 4), "scores": {k: round(v, 4) for k, v in scores.items()}})
        matches.sort(key=lambda item: item["overall_score"], reverse=True)
        warning = bool(matches and (matches[0]["overall_score"] >= .55 or max(matches[0]["scores"].values()) >= .9))
        result = {"schema_version": SQLITE_SCHEMA_VERSION, "advisory_only": True, "warning": warning, "recommendation": "EDIT" if warning else "CONTINUE", "matches": matches[:5], "workflow_state_changed": False, "content_changed": False}
        if persist and matches:
            path = (database_path or self.database_path).resolve()
            self.migrate(path)
            with sqlite3.connect(path) as connection:
                for match in matches[:5]:
                    connection.execute("INSERT OR IGNORE INTO editorial_memory_duplicate_reports(candidate_fingerprint,matched_snapshot_id,scores_json,recommendation,created_at) VALUES(?,?,?,?,?)", (_fingerprint(candidate), match["snapshot_id"], _json(match["scores"]), result["recommendation"], _now()))
                connection.commit()
        return result

    def detect_stale_claims(self, *, database_path: Path | None = None, as_of: date | None = None, persist: bool = False) -> dict[str, Any]:
        as_of = as_of or datetime.now(timezone.utc).date()
        reviews: list[dict[str, Any]] = []
        for row in self.latest_records(database_path):
            for raw in row.get("claims") or []:
                claim = raw if isinstance(raw, dict) else {"claim": str(raw)}
                text = str(claim.get("claim") or claim.get("text") or "")
                normal = _normalise(text)
                claim_type = str(claim.get("claim_type") or ("pricing" if any(token in normal for token in ("price", "pricing", "cost", "usd", "plan")) else "feature" if any(token in normal for token in ("feature", "supports", "integration", "available")) else "general"))
                verified = str(claim.get("last_verified_at") or claim.get("verified_at") or "")
                age = None
                try:
                    age = (as_of - date.fromisoformat(verified[:10])).days
                except (ValueError, TypeError):
                    pass
                reasons: list[str] = []
                if bool(claim.get("source_superseded") or claim.get("superseded")):
                    reasons.append("source_replaced")
                if not bool(claim.get("verified") or claim.get("human_verified") or verified):
                    reasons.append("claim_not_reverified")
                if claim_type == "pricing" and (age is None or age > 90):
                    reasons.append("pricing_stale")
                if claim_type == "feature" and (age is None or age > 180):
                    reasons.append("feature_may_have_changed")
                for reason in dict.fromkeys(reasons):
                    reviews.append({"snapshot_id": row["snapshot_id"], "slug": row["slug"], "claim": text, "claim_type": claim_type, "source_url": str(claim.get("source_url") or ""), "last_verified_at": verified, "reason": reason, "state": "needs_review"})
        if persist and reviews:
            path = (database_path or self.database_path).resolve()
            self.migrate(path)
            with sqlite3.connect(path) as connection:
                for review in reviews:
                    connection.execute("INSERT OR IGNORE INTO editorial_memory_claim_reviews(snapshot_id,claim_fingerprint,claim_text,claim_type,source_url,last_verified_at,reason,state,detected_at) VALUES(?,?,?,?,?,?,?,?,?)", (review["snapshot_id"], hashlib.sha256(_normalise(review["claim"]).encode()).hexdigest(), review["claim"], review["claim_type"], review["source_url"], review["last_verified_at"], review["reason"], "needs_review", _now()))
                connection.commit()
        return {"schema_version": SQLITE_SCHEMA_VERSION, "advisory_only": True, "state": "needs_review" if reviews else "current", "review_count": len(reviews), "reviews": reviews, "content_changed": False}

    def memory_brief(self, candidates: list[dict[str, Any]], *, database_path: Path | None = None) -> dict[str, Any]:
        return {
            "schema_version": SQLITE_SCHEMA_VERSION,
            "purpose": "Recommendation-only history brief. Do not copy prior wording and do not change approval or publication state.",
            "generated_at": _now(),
            "articles": [{"candidate": {key: row.get(key) for key in ("task_id","slug","title","root_topic","angle","keyword")}, "duplicate_advisory": self.detect_duplicates(row, database_path=database_path)} for row in candidates],
            "operator_approval_required": True,
            "workflow_state_changed": False,
        }

    def build_candidates(
        self,
        records: list[dict[str, Any]] | None = None,
        *,
        mode: str = "dry-run",
    ) -> dict[str, Any]:
        records = records if records is not None else article_inventory(self.root)
        candidates: list[dict[str, Any]] = []
        for record in records:
            html = record.get("html") if isinstance(record.get("html"), dict) else {}
            metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
            headings = [str(row.get("text") or "") for row in html.get("headings") or [] if isinstance(row, dict)]
            paragraphs = [str(value) for value in html.get("paragraphs") or []]
            links = [row for row in html.get("links") or [] if isinstance(row, dict)]
            internal = sorted(
                {
                    internal_slug(str(row.get("href") or ""))
                    for row in links
                    if internal_slug(str(row.get("href") or ""))
                }
            )
            source_domains = sorted(
                {
                    (urlparse(str(value)).hostname or "").casefold().removeprefix("www.")
                    for value in (
                        list(metadata.get("source_urls") or [])
                        + list(metadata.get("verified_sources") or [])
                    )
                    if urlparse(str(value)).hostname
                }
            )
            faq_themes = [value for value in headings if value.endswith("?")]
            record_id = _record_id(record["slug"], record.get("batch_date") or "")
            origin_state = str(record.get("editorial_state") or "").casefold()
            candidate = {
                "schema_version": SCHEMA_VERSION,
                "record_id": record_id,
                "state": "pending",
                "origin_state": origin_state,
                "eligible_for_best": not any(word in origin_state for word in ("reject", "block")),
                "slug": record["slug"],
                "title": record["title"],
                "canonical": record["canonical"],
                "batch_date": record.get("batch_date") or "",
                "root_topic_id": record.get("root_topic_id") or "",
                "daily_angle": record.get("daily_angle") or "",
                "thesis_pattern": _thesis_pattern(paragraphs),
                "heading_patterns": headings[:20],
                "faq_themes": faq_themes[:10],
                "source_domains": source_domains,
                "internal_link_targets": internal,
                "schema_types": sorted(schema_types(html.get("schemas") or [])),
                "cta_type": str(metadata.get("cta_type") or metadata.get("required_cta") or ""),
                "risk_notes": list(metadata.get("warnings") or metadata.get("hard_blockers") or []),
                "approved_by_human": False,
                "human_checkpoint_required": True,
                "body_stored": False,
            }
            candidates.append(candidate)
            if mode == "write":
                path = self.memory_root / "pending" / f"{record_id}.json"
                atomic_write_json(path, candidate, intelligence_root=self.memory_root, archive_existing=False)
        return {
            "schema_version": SCHEMA_VERSION,
            "mode": mode,
            "candidate_count": len(candidates),
            "candidates": candidates,
            "summary": {
                "eligible_for_best": sum(bool(row["eligible_for_best"]) for row in candidates),
                "human_checkpoint_required": len(candidates),
            },
        }

    def list_records(self, state: str = "pending") -> list[dict[str, Any]]:
        if state not in STATES:
            raise ValueError(f"Unsupported editorial memory state: {state}")
        output: list[dict[str, Any]] = []
        for path in sorted((self.memory_root / state).glob("*.json")):
            from .inventory import read_json

            payload = read_json(path, {})
            if isinstance(payload, dict):
                output.append(payload)
        return output

    def transition(self, record_id: str, action: str, *, actor: str) -> dict[str, Any]:
        if action not in {"approve", "reject", "archive", "best"}:
            raise ValueError(f"Unsupported memory action: {action}")
        if not actor.strip():
            raise ValueError("A named human actor is required for editorial memory transitions.")
        destination = {"approve": "approved", "reject": "rejected", "archive": "archive", "best": "best"}[action]
        source_states = ("approved",) if action == "best" else ("pending", "approved", "rejected", "best")
        source = next(
            (
                self.memory_root / state / f"{record_id}.json"
                for state in source_states
                if (self.memory_root / state / f"{record_id}.json").is_file()
            ),
            None,
        )
        if source is None:
            if action == "best":
                existing = next(
                    (
                        self.memory_root / state / f"{record_id}.json"
                        for state in ("pending", "rejected", "archive", "best")
                        if (self.memory_root / state / f"{record_id}.json").is_file()
                    ),
                    None,
                )
                if existing is not None:
                    raise ValueError("Only a human-approved memory record can become a best example.")
            raise FileNotFoundError(record_id)
        from .inventory import read_json

        payload = read_json(source, {})
        if not isinstance(payload, dict):
            raise ValueError("Editorial memory record is invalid.")
        if action == "best" and not payload.get("eligible_for_best"):
            raise ValueError("Rejected or blocked content cannot become a best example.")
        payload.update(
            {
                "state": destination,
                "approved_by_human": action in {"approve", "best"},
                "human_actor": actor.strip(),
                "reviewed_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        target = self.memory_root / destination / source.name
        atomic_write_json(target, payload, intelligence_root=self.memory_root, archive_existing=False)
        source.unlink()
        return payload


def memory_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "count": len(records),
        "root_topics": dict(Counter(str(row.get("root_topic_id") or "unknown") for row in records)),
        "angles": dict(Counter(str(row.get("daily_angle") or "unknown") for row in records)),
    }
