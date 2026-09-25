from __future__ import annotations

import csv
import hashlib
import json
import re
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlsplit, urlunsplit

from modules.official_source_registry import OfficialSourceRegistry

from .analytics_feedback import AnalyticsFeedbackStore
from .editorial_memory import EditorialMemoryStore
from .feature_flags import feature_enabled
from .knowledge_graph_store import KnowledgeGraphStore


SCHEMA_NAME = "social_signal_ingestion_sqlite_v1"
SCHEMA_VERSION = 4
IMPORT_SCHEMA_VERSION = "social_signal_manual_import_v1"
MIGRATION_PATH = Path(__file__).with_name("migrations") / "004_social_signal_ingestion.sql"
SUPPORTED_FORMATS = {"csv", "json"}
SOCIAL_HOSTS = {
    "linkedin.com": "linkedin",
    "www.linkedin.com": "linkedin",
    "x.com": "x",
    "twitter.com": "x",
    "www.reddit.com": "reddit",
    "reddit.com": "reddit",
    "quora.com": "quora",
    "www.quora.com": "quora",
    "dev.to": "devto",
    "www.producthunt.com": "producthunt",
}
DISCOVERY_ONLY_PLATFORMS = {"linkedin", "x", "reddit", "quora", "devto", "producthunt"}
REVIEW_ACTIONS = {
    "approve": "APPROVED_FOR_MENU_H",
    "reject": "REJECTED",
    "archive": "ARCHIVED",
    "needs-official-source": "NEEDS_OFFICIAL_SOURCE",
}


def _now(value: datetime | None = None) -> datetime:
    resolved = value or datetime.now(UTC)
    return resolved.astimezone(UTC) if resolved.tzinfo else resolved.replace(tzinfo=UTC)


def _hash(*parts: Any) -> str:
    return hashlib.sha256("|".join(str(part) for part in parts).encode("utf-8")).hexdigest()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def normalize_url(value: Any) -> str:
    raw = str(value or "").strip()
    if not re.match(r"^https?://", raw, flags=re.I):
        return ""
    parts = urlsplit(raw)
    if not parts.hostname:
        return ""
    path = re.sub(r"/{2,}", "/", parts.path or "/")
    if path != "/":
        path = path.rstrip("/")
    return urlunsplit((parts.scheme.casefold(), parts.netloc.casefold(), path, "", ""))


def normalize_platform(value: Any, url: str = "") -> str:
    raw = re.sub(r"[^a-z0-9]+", "", str(value or "").casefold())
    aliases = {"twitter": "x", "linkedinnewsletter": "linkedin", "producthunt": "producthunt", "devto": "devto"}
    if raw:
        return aliases.get(raw, raw)
    return SOCIAL_HOSTS.get(str(urlsplit(url).hostname or "").casefold(), "web")


def _tokens(value: str) -> set[str]:
    stop = {"the", "and", "for", "with", "from", "that", "this", "new", "official", "announces", "launches"}
    return {token for token in re.findall(r"[a-z0-9]+", value.casefold()) if len(token) > 2 and token not in stop}


def _date(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return (parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)).astimezone(UTC).isoformat()
    except ValueError:
        return ""


def _number(value: Any) -> float:
    try:
        return max(0.0, float(str(value or "0").replace(",", "")))
    except ValueError:
        return 0.0


class SocialSignalStore:
    """Manual/local discovery signals; this store has no queue, writer, approval, or publish API."""

    def __init__(self, *, root: Path, db_path: Path | None = None, now: datetime | None = None) -> None:
        self.root = root.resolve()
        self.db_path = (db_path or self.root / "data/intelligence/social_signals/social_signals.sqlite3").resolve()
        self.now = _now(now)

    def enabled(self) -> bool:
        return feature_enabled(self.root, "social_signal_ingestion.enabled")

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            yield connection
        finally:
            connection.close()

    def migration_plan(self) -> dict[str, Any]:
        applied: list[int] = []
        if self.db_path.is_file():
            with self.connect() as connection:
                exists = connection.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='social_signal_schema_migrations'"
                ).fetchone()
                if exists:
                    applied = [int(row[0]) for row in connection.execute("SELECT version FROM social_signal_schema_migrations")]
        return {
            "schema": SCHEMA_NAME,
            "schema_version": SCHEMA_VERSION,
            "database_path": str(self.db_path),
            "applied_versions": sorted(applied),
            "pending_versions": [] if SCHEMA_VERSION in applied else [SCHEMA_VERSION],
            "idempotent": True,
        }

    def migrate(self) -> dict[str, Any]:
        before = self.migration_plan()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.executescript(MIGRATION_PATH.read_text(encoding="utf-8"))
            connection.execute(
                "INSERT OR IGNORE INTO social_signal_schema_migrations(version,name,applied_at) VALUES(?,?,?)",
                (SCHEMA_VERSION, "social_signal_ingestion", self.now.isoformat()),
            )
            connection.commit()
        result = self.migration_plan()
        result["newly_applied"] = [version for version in result["applied_versions"] if version not in before["applied_versions"]]
        return result

    @staticmethod
    def _read_rows(path: Path) -> list[dict[str, Any]]:
        suffix = path.suffix.casefold().lstrip(".")
        if suffix == "csv":
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                return [dict(row) for row in csv.DictReader(handle)]
        if suffix == "json":
            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                payload = payload.get("signals") or payload.get("rows") or payload.get("records") or []
            if not isinstance(payload, list):
                raise ValueError("JSON import must be a list or contain signals/rows/records.")
            return [dict(row) for row in payload if isinstance(row, dict)]
        raise ValueError("Only local CSV and JSON imports are supported.")

    def inspect_import(self, path: Path) -> dict[str, Any]:
        path = path.resolve()
        if not path.is_file():
            raise FileNotFoundError(str(path))
        checksum = hashlib.sha256(path.read_bytes()).hexdigest()
        rows = self._read_rows(path)
        accepted: list[dict[str, Any]] = []
        rejected: list[dict[str, Any]] = []
        seen: set[str] = set()
        for index, raw in enumerate(rows, start=1):
            normalized, errors = self._normalize_row(raw, source_row=index)
            if normalized.get("fingerprint") in seen:
                errors.append("duplicate row in import")
            if errors:
                rejected.append({"source_row": index, "errors": errors, "raw": raw})
                continue
            seen.add(normalized["fingerprint"])
            accepted.append(normalized)
        return {
            "schema_version": IMPORT_SCHEMA_VERSION,
            "import_id": _hash(checksum, IMPORT_SCHEMA_VERSION)[:24],
            "source_file": str(path),
            "source_format": path.suffix.casefold().lstrip("."),
            "checksum": checksum,
            "imported_at": self.now.isoformat(),
            "row_count": len(rows),
            "accepted_count": len(accepted),
            "rejected_count": len(rejected),
            "accepted": accepted,
            "rejected": rejected,
            "warnings": [],
            "dry_run": True,
            "production_state_changed": False,
            "paid_api_used": False,
            "api_key_required": False,
        }

    def inspect_urls(self, urls: Iterable[str]) -> dict[str, Any]:
        temp_rows = [{"url": url, "title": url, "detected_at": self.now.isoformat()} for url in urls]
        accepted, rejected = [], []
        for index, raw in enumerate(temp_rows, start=1):
            normalized, errors = self._normalize_row(raw, source_row=index)
            (rejected if errors else accepted).append(
                {"source_row": index, "errors": errors, "raw": raw} if errors else normalized
            )
        checksum = _hash(*urls)
        return {
            "schema_version": IMPORT_SCHEMA_VERSION,
            "import_id": _hash(checksum, "manual_urls")[:24],
            "source_file": "manual:url",
            "source_format": "url",
            "checksum": checksum,
            "imported_at": self.now.isoformat(),
            "row_count": len(temp_rows),
            "accepted_count": len(accepted),
            "rejected_count": len(rejected),
            "accepted": accepted,
            "rejected": rejected,
            "warnings": ["URL-only imports remain discovery-only until title and official evidence are reviewed."],
            "dry_run": True,
            "production_state_changed": False,
            "paid_api_used": False,
            "api_key_required": False,
        }

    def _normalize_row(self, raw: dict[str, Any], *, source_row: int) -> tuple[dict[str, Any], list[str]]:
        signal_url = normalize_url(raw.get("url") or raw.get("signal_url") or raw.get("post_url"))
        title = str(raw.get("title") or raw.get("headline") or raw.get("topic") or "").strip()
        platform = normalize_platform(raw.get("platform"), signal_url)
        company = str(raw.get("company") or raw.get("product") or "").strip()
        official = normalize_url(raw.get("official_source_url") or raw.get("official_url"))
        official_resolved_from = "import"
        if not official and company:
            official = self._resolve_official_source(company)
            official_resolved_from = "local_official_source_registry" if official else ""
        published = _date(raw.get("published_at") or raw.get("publication_date"))
        detected = _date(raw.get("detected_at")) or self.now.isoformat()
        errors: list[str] = []
        if not signal_url:
            errors.append("invalid or missing signal URL")
        if not title:
            errors.append("missing title/topic")
        if raw.get("published_at") and not published:
            errors.append("invalid published_at")
        engagement = {key: _number(raw.get(key)) for key in ("views", "impressions", "reactions", "comments", "shares", "clicks")}
        for key in engagement:
            try:
                if str(raw.get(key) or "").strip() and float(str(raw.get(key)).replace(",", "")) < 0:
                    errors.append(f"negative engagement metric: {key}")
            except ValueError:
                errors.append(f"invalid engagement metric: {key}")
        verification = self._verification_status(platform, signal_url, official, raw)
        risk_flags = []
        lower = f"{title} {raw.get('summary') or ''}".casefold()
        if any(marker in lower for marker in ("rumor", "rumour", "leak", "unconfirmed", "allegedly")):
            risk_flags.append("RUMOR_OR_UNCONFIRMED")
        if verification != "OFFICIAL_SOURCE_VERIFIED":
            risk_flags.append("NEEDS_OFFICIAL_SOURCE")
        freshness = self._freshness_score(published)
        if published and freshness < 35:
            risk_flags.append("STALE_SIGNAL")
        fingerprint = _hash(signal_url or title.casefold())
        novelty = freshness
        relevance = self._relevance_score(title, str(raw.get("topic") or ""))
        return {
            "signal_id": f"signal-{fingerprint[:20]}",
            "fingerprint": fingerprint,
            "source_row": source_row,
            "platform": platform,
            "signal_url": signal_url,
            "title": title,
            "topic": str(raw.get("topic") or title).strip(),
            "author_account": str(raw.get("author") or raw.get("account") or "").strip(),
            "company": company,
            "detected_at": detected,
            "published_at": published,
            "engagement": engagement,
            "official_source_url": official,
            "official_source_resolved_from": official_resolved_from,
            "verification_status": verification,
            "duplicate_status": "UNIQUE_IN_IMPORT",
            "novelty_score": novelty,
            "relevance_score": relevance,
            "risk_flags": risk_flags,
            "human_status": "PENDING_REVIEW",
            "data_quality_status": "PASS" if not errors else "REJECTED",
            "raw": raw,
        }, errors

    def _freshness_score(self, published_at: str) -> float:
        if not published_at:
            return 50.0
        try:
            published = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
        except ValueError:
            return 0.0
        age_days = max(0.0, (self.now - published.astimezone(UTC)).total_seconds() / 86400)
        return round(max(0.0, 100.0 - age_days * 2.5), 2)

    def _resolve_official_source(self, company: str) -> str:
        registry = OfficialSourceRegistry(self.root / "data/official_source_registry.json")
        preferred = {"release_notes": 0, "changelog": 1, "blog": 2, "official_website": 3, "docs": 4}
        rows = sorted(
            registry.sources_for(company),
            key=lambda row: preferred.get(str(row.get("source_type") or ""), 99),
        )
        return next((normalize_url(row.get("source_url")) for row in rows if normalize_url(row.get("source_url"))), "")

    @staticmethod
    def _verification_status(platform: str, signal_url: str, official: str, raw: dict[str, Any]) -> str:
        if not official:
            return "NEEDS_OFFICIAL_SOURCE"
        official_host = str(urlsplit(official).hostname or "").casefold()
        if official_host in SOCIAL_HOSTS and not bool(raw.get("official_account_verified")):
            return "NEEDS_OFFICIAL_SOURCE"
        if official == signal_url and platform in DISCOVERY_ONLY_PLATFORMS and not bool(raw.get("official_account_verified")):
            return "NEEDS_OFFICIAL_SOURCE"
        return "OFFICIAL_SOURCE_VERIFIED"

    @staticmethod
    def _relevance_score(title: str, topic: str) -> float:
        tokens = _tokens(f"{title} {topic}")
        ai_markers = {"ai", "model", "agent", "software", "automation", "copilot", "gemini", "openai", "anthropic"}
        return round(min(100.0, 45.0 + len(tokens & ai_markers) * 10.0 + min(25.0, len(tokens))), 2)

    def confirm_import(self, preview: dict[str, Any], *, confirm: bool) -> dict[str, Any]:
        if not confirm:
            raise ValueError("Explicit confirmation is required.")
        self.migrate()
        duplicate_count = 0
        with self.connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO social_signal_imports(import_id,source_file,source_format,checksum,imported_at,row_count,accepted_count,rejected_count,warnings_json,schema_version) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (
                    preview["import_id"], preview["source_file"], preview["source_format"], preview["checksum"],
                    self.now.isoformat(), preview["row_count"], preview["accepted_count"], preview["rejected_count"],
                    _json(preview.get("warnings") or []), IMPORT_SCHEMA_VERSION,
                ),
            )
            for row in preview.get("accepted") or []:
                exists = connection.execute("SELECT signal_id FROM social_signals WHERE fingerprint=?", (row["fingerprint"],)).fetchone()
                if exists:
                    duplicate_count += 1
                    continue
                connection.execute(
                    "INSERT INTO social_signals VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        row["signal_id"], row["fingerprint"], preview["import_id"], row["platform"], row["signal_url"],
                        row["title"], row["topic"], row["author_account"], row["company"], row["detected_at"],
                        row["published_at"], _json(row["engagement"]), row["official_source_url"], row["verification_status"],
                        row["duplicate_status"], row["novelty_score"], row["relevance_score"], _json(row["risk_flags"]),
                        row["human_status"], row["data_quality_status"], self.now.isoformat(),
                    ),
                )
                connection.execute(
                    "INSERT OR IGNORE INTO social_signal_provenance VALUES(?,?,?,?,?,?,?)",
                    (
                        _hash(row["signal_id"], preview["import_id"], row["source_row"]), row["signal_id"], preview["import_id"],
                        preview["source_file"], row["source_row"], self.now.isoformat(), _json(row.get("raw") or {}),
                    ),
                )
            connection.commit()
        return {
            **preview,
            "dry_run": False,
            "signals_inserted": preview["accepted_count"] - duplicate_count,
            "duplicate_signal_count": duplicate_count,
            "production_state_changed": False,
            "social_queue_changed": False,
        }

    def build_candidates(self, *, dry_run: bool = True) -> dict[str, Any]:
        if not self.db_path.is_file():
            return self._empty_candidate_report("Social signal database is missing.")
        with self.connect() as connection:
            rows = [dict(row) for row in connection.execute("SELECT * FROM social_signals ORDER BY created_at, signal_id")]
        clusters = self._cluster(rows)
        candidates = [self._candidate(cluster) for cluster in clusters]
        if not dry_run:
            self.migrate()
            with self.connect() as connection:
                for cluster, candidate in zip(clusters, candidates):
                    connection.execute(
                        "INSERT OR IGNORE INTO social_signal_clusters VALUES(?,?,?,?,?)",
                        (cluster["cluster_id"], cluster["announcement_key"], cluster["company"], cluster["topic"], self.now.isoformat()),
                    )
                    for row in cluster["signals"]:
                        connection.execute("INSERT OR IGNORE INTO social_signal_cluster_members VALUES(?,?)", (cluster["cluster_id"], row["signal_id"]))
                    connection.execute(
                        "INSERT OR IGNORE INTO social_signal_candidates VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (
                            candidate["candidate_id"], cluster["cluster_id"], candidate["title"], candidate["topic"], candidate["company"],
                            candidate["official_source_url"], candidate["verification_status"], candidate["score"], candidate["priority"],
                            candidate["reason"], _json(candidate["evidence"]), _json(candidate["integrations"]), candidate["status"],
                            candidate["human_status"], self.now.isoformat(), self.now.isoformat(),
                        ),
                    )
                connection.commit()
        verified = sum(row["verification_status"] == "OFFICIAL_SOURCE_VERIFIED" for row in candidates)
        rumors = sum("RUMOR_OR_UNCONFIRMED" in row["risk_flags"] for row in candidates)
        return {
            "schema_version": "social_signal_candidate_report_v1",
            "signal_count": len(rows),
            "cluster_count": len(clusters),
            "candidate_count": len(candidates),
            "official_source_verified_count": verified,
            "needs_official_source_count": len(candidates) - verified,
            "rumor_rejected_count": rumors,
            "hot_news_candidate_count": sum(row["eligible_for_menu_h"] for row in candidates),
            "candidates": candidates,
            "dry_run": dry_run,
            "recommendation_only": True,
            "social_queue_changed": False,
            "writer_called": False,
            "published": False,
        }

    def _cluster(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        clusters: list[dict[str, Any]] = []
        for row in rows:
            title_tokens = _tokens(str(row.get("title") or ""))
            company = str(row.get("company") or "").casefold().strip()
            match = None
            for cluster in clusters:
                left = _tokens(cluster["topic"])
                overlap = len(title_tokens & left) / max(1, len(title_tokens | left))
                company_match = bool(company and company == cluster["company"].casefold())
                if overlap >= 0.55 or (company_match and overlap >= 0.35):
                    match = cluster
                    break
            if match is None:
                key = _hash(company, " ".join(sorted(title_tokens)))[:20]
                match = {
                    "cluster_id": f"cluster-{key}", "announcement_key": key,
                    "company": str(row.get("company") or ""), "topic": str(row.get("title") or ""), "signals": [],
                }
                clusters.append(match)
            match["signals"].append(row)
        return clusters

    def _candidate(self, cluster: dict[str, Any]) -> dict[str, Any]:
        signals = cluster["signals"]
        official = next((row["official_source_url"] for row in signals if row["verification_status"] == "OFFICIAL_SOURCE_VERIFIED"), "")
        risk_flags = sorted({flag for row in signals for flag in json.loads(row.get("risk_flags_json") or "[]")})
        verified = bool(official) and "RUMOR_OR_UNCONFIRMED" not in risk_flags
        novelty = max(float(row["novelty_score"]) for row in signals)
        relevance = max(float(row["relevance_score"]) for row in signals)
        corroboration = min(15.0, max(0, len(signals) - 1) * 5.0)
        score = round(0.4 * novelty + 0.45 * relevance + corroboration - (35 if not verified else 0), 2)
        status = "PENDING_REVIEW" if verified else "NEEDS_OFFICIAL_SOURCE"
        if "RUMOR_OR_UNCONFIRMED" in risk_flags:
            status = "REJECTED_RUMOR"
        integrations = self._integration_context(cluster)
        return {
            "candidate_id": f"social-candidate-{cluster['announcement_key']}",
            "title": cluster["topic"],
            "topic": cluster["topic"],
            "company": cluster["company"],
            "official_source_url": official,
            "verification_status": "OFFICIAL_SOURCE_VERIFIED" if verified else "NEEDS_OFFICIAL_SOURCE",
            "score": score,
            "priority": "HIGH" if score >= 80 else "MEDIUM" if score >= 60 else "LOW",
            "reason": "Rule-based discovery candidate; operator review is required before Menu H can use it.",
            "evidence": [{"signal_id": row["signal_id"], "url": row["signal_url"], "platform": row["platform"]} for row in signals],
            "integrations": integrations,
            "risk_flags": risk_flags,
            "status": status,
            "human_status": "PENDING_REVIEW",
            "eligible_for_menu_h": verified,
        }

    def _integration_context(self, cluster: dict[str, Any]) -> dict[str, Any]:
        title = cluster["topic"]
        context: dict[str, Any] = {"editorial_memory": {}, "knowledge_graph": [], "analytics_feedback": {}}
        try:
            if feature_enabled(self.root, "editorial_memory.enabled"):
                context["editorial_memory"] = EditorialMemoryStore(root=self.root).detect_duplicates(
                    {"title": title, "slug": re.sub(r"[^a-z0-9]+", "-", title.casefold()).strip("-"), "keyword": title}
                )
        except (OSError, ValueError, sqlite3.Error):
            context["editorial_memory"] = {"warning": "unavailable"}
        try:
            if feature_enabled(self.root, "knowledge_graph.enabled"):
                context["knowledge_graph"] = KnowledgeGraphStore(root=self.root).find_entities(cluster.get("company") or title)[:5]
        except (OSError, ValueError, sqlite3.Error):
            context["knowledge_graph"] = []
        try:
            if feature_enabled(self.root, "analytics_feedback.enabled"):
                context["analytics_feedback"] = AnalyticsFeedbackStore(root=self.root, now=self.now).approved_backlog(
                    root_topics=[cluster.get("company") or title]
                )
        except (OSError, ValueError, sqlite3.Error):
            context["analytics_feedback"] = {"warning": "unavailable"}
        return context

    def review(self, candidate_id: str, *, action: str, actor: str, confirm: bool, note: str = "") -> dict[str, Any]:
        if not confirm:
            raise ValueError("Explicit confirmation is required for a review action.")
        if action not in REVIEW_ACTIONS:
            raise ValueError(f"Unsupported review action: {action}")
        if not actor.strip():
            raise ValueError("Actor is required.")
        with self.connect() as connection:
            candidate = connection.execute("SELECT * FROM social_signal_candidates WHERE candidate_id=?", (candidate_id,)).fetchone()
            if not candidate:
                raise FileNotFoundError(candidate_id)
            target = REVIEW_ACTIONS[action]
            if target == "APPROVED_FOR_MENU_H" and candidate["verification_status"] != "OFFICIAL_SOURCE_VERIFIED":
                raise ValueError("A valid official source is required before Menu H approval.")
            connection.execute(
                "UPDATE social_signal_candidates SET status=?,human_status=?,updated_at=? WHERE candidate_id=?",
                (target, target, self.now.isoformat(), candidate_id),
            )
            connection.execute(
                "INSERT INTO social_signal_review_events VALUES(?,?,?,?,?,?)",
                (_hash(candidate_id, action, actor, self.now.isoformat()), candidate_id, action, actor, note, self.now.isoformat()),
            )
            connection.commit()
        return {
            "candidate_id": candidate_id,
            "status": target,
            "human_status": target,
            "social_queue_changed": False,
            "writer_called": False,
            "published": False,
        }

    def menu_h_advisory(self) -> dict[str, Any]:
        if not self.enabled() or not self.db_path.is_file():
            return {"enabled": False, "count": 0, "candidates": [], "recommendation_only": True}
        with self.connect() as connection:
            rows = [dict(row) for row in connection.execute(
                "SELECT * FROM social_signal_candidates WHERE status='APPROVED_FOR_MENU_H' AND verification_status='OFFICIAL_SOURCE_VERIFIED' ORDER BY score DESC"
            )]
        return {"enabled": True, "count": len(rows), "candidates": rows, "recommendation_only": True}

    def report(self) -> dict[str, Any]:
        if not self.db_path.is_file():
            return self._empty_candidate_report("Social signal database is missing.")
        with self.connect() as connection:
            counts = {
                "signals": connection.execute("SELECT COUNT(*) FROM social_signals").fetchone()[0],
                "clusters": connection.execute("SELECT COUNT(*) FROM social_signal_clusters").fetchone()[0],
                "candidates": connection.execute("SELECT COUNT(*) FROM social_signal_candidates").fetchone()[0],
                "approved_for_menu_h": connection.execute("SELECT COUNT(*) FROM social_signal_candidates WHERE status='APPROVED_FOR_MENU_H'").fetchone()[0],
            }
            candidates = [dict(row) for row in connection.execute("SELECT * FROM social_signal_candidates ORDER BY score DESC")]
        return {"schema_version": SCHEMA_NAME, "mode": "read-only", **counts, "candidate_rows": candidates, "recommendation_only": True}

    @staticmethod
    def _empty_candidate_report(reason: str) -> dict[str, Any]:
        return {
            "schema_version": "social_signal_candidate_report_v1", "signal_count": 0, "cluster_count": 0,
            "candidate_count": 0, "official_source_verified_count": 0, "needs_official_source_count": 0,
            "rumor_rejected_count": 0, "hot_news_candidate_count": 0, "candidates": [], "reason": reason,
            "recommendation_only": True, "social_queue_changed": False, "writer_called": False, "published": False,
        }


def menu_h_signal_advisory(root: Path) -> dict[str, Any]:
    """Fail-open read-only hook for Menu H."""
    try:
        return SocialSignalStore(root=root).menu_h_advisory()
    except (OSError, ValueError, sqlite3.Error):
        return {"enabled": False, "count": 0, "candidates": [], "warning": "social signal advisory unavailable", "recommendation_only": True}
