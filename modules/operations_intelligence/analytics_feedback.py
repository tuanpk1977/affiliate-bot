from __future__ import annotations

import csv
import hashlib
import json
import math
import re
import sqlite3
from collections import defaultdict
from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlsplit, urlunsplit

from modules.performance_engine.engine import PerformanceEngine

from .feature_flags import feature_enabled
from .inventory import article_inventory


SCHEMA_NAME = "analytics_feedback_sqlite_v1"
SCHEMA_VERSION = 3
IMPORT_SCHEMA_VERSION = "analytics_manual_import_v1"
MIGRATION_PATH = Path(__file__).with_name("migrations") / "003_analytics_feedback.sql"
CANDIDATE_STATES = {
    "PENDING_REVIEW", "APPROVED_FOR_BACKLOG", "REJECTED", "NEEDS_MORE_DATA",
    "EXPIRED", "ARCHIVED", "IMPLEMENTED",
}
REVIEW_ACTIONS = {
    "approve": "APPROVED_FOR_BACKLOG",
    "reject": "REJECTED",
    "needs-more-data": "NEEDS_MORE_DATA",
    "archive": "ARCHIVED",
    "implemented": "IMPLEMENTED",
}


DEFAULT_RULES: dict[str, dict[str, Any]] = {
    "REFRESH_ARTICLE": {"version": 1, "required": ["article_age_days"], "minimum_sample": 30, "minimum_age_days": 120, "thresholds": {"article_age_days": 180}},
    "PRICING_UPDATE": {"version": 1, "required": ["stale_claim_types"], "minimum_sample": 1, "minimum_age_days": 1, "thresholds": {}},
    "FEATURE_UPDATE": {"version": 1, "required": ["stale_claim_types"], "minimum_sample": 1, "minimum_age_days": 1, "thresholds": {}},
    "SECURITY_UPDATE": {"version": 1, "required": ["stale_claim_types"], "minimum_sample": 1, "minimum_age_days": 1, "thresholds": {}},
    "IMPROVE_TITLE_META": {"version": 1, "required": ["impressions", "ctr"], "minimum_sample": 100, "minimum_age_days": 14, "thresholds": {"max_ctr": 0.02}},
    "STRENGTHEN_INTERNAL_LINKS": {"version": 1, "required": ["average_position", "impressions"], "minimum_sample": 100, "minimum_age_days": 14, "thresholds": {"position_min": 8, "position_max": 30}},
    "EXPAND_FAQ": {"version": 1, "required": ["query_count", "impressions"], "minimum_sample": 100, "minimum_age_days": 14, "thresholds": {"query_count": 5}},
    "CREATE_COMPARISON_FOLLOWUP": {"version": 1, "required": ["query_text"], "minimum_sample": 30, "minimum_age_days": 14, "thresholds": {}},
    "CREATE_USE_CASE_FOLLOWUP": {"version": 1, "required": ["query_text"], "minimum_sample": 30, "minimum_age_days": 14, "thresholds": {}},
    "PROMOTE_HIGH_PERFORMING_TOPIC": {"version": 1, "required": ["clicks", "conversions"], "minimum_sample": 100, "minimum_age_days": 14, "thresholds": {"clicks": 100, "conversions": 3}},
    "REVIEW_LOW_CTR": {"version": 1, "required": ["impressions", "ctr"], "minimum_sample": 100, "minimum_age_days": 14, "thresholds": {"max_ctr": 0.02}},
    "REVIEW_POSITION_OPPORTUNITY": {"version": 1, "required": ["impressions", "average_position"], "minimum_sample": 100, "minimum_age_days": 14, "thresholds": {"position_min": 4, "position_max": 20}},
    "REVIEW_CONVERSION_GAP": {"version": 1, "required": ["affiliate_clicks", "conversions"], "minimum_sample": 20, "minimum_age_days": 14, "thresholds": {"max_conversion_rate": 0.02}},
    "REVIEW_HIGH_TRAFFIC_LOW_REVENUE": {"version": 1, "required": ["page_views", "revenue"], "minimum_sample": 100, "minimum_age_days": 14, "thresholds": {"page_views": 500, "max_revenue": 1}},
    "KEEP_OBSERVING": {"version": 1, "required": [], "minimum_sample": 30, "minimum_age_days": 14, "thresholds": {}},
    "RETIRE_LOW_VALUE_ANGLE": {"version": 1, "required": ["impressions", "clicks", "article_age_days"], "minimum_sample": 30, "minimum_age_days": 180, "thresholds": {"max_impressions": 20, "max_clicks": 1}},
    "NEEDS_MORE_DATA": {"version": 1, "required": [], "minimum_sample": 30, "minimum_age_days": 14, "thresholds": {}},
}


SOURCE_ALIASES: dict[str, dict[str, tuple[str, ...]]] = {
    "gsc": {
        "date": ("date", "day"), "url": ("page", "url", "landing_page"), "query": ("query", "keyword"),
        "clicks": ("clicks",), "impressions": ("impressions",), "ctr": ("ctr",),
        "average_position": ("position", "average_position"), "country": ("country",), "device": ("device",),
    },
    "content": {
        "date": ("date", "day", "period_end"), "url": ("page", "url", "canonical_url"), "slug": ("slug", "article_slug"),
        "page_views": ("page_views", "views"), "users": ("users",), "sessions": ("sessions",),
        "engagement": ("engagement", "engagement_rate"), "time_on_page": ("time_on_page", "average_engagement_time"),
        "publication_date": ("publication_date", "publish_date"),
    },
    "affiliate": {
        "date": ("date", "day", "period_end"), "url": ("url", "page", "canonical_url"), "slug": ("slug", "article_slug"),
        "offer_id": ("offer_id", "offer", "affiliate_offer"), "affiliate_clicks": ("affiliate_clicks", "clicks"),
        "conversions": ("conversions",), "revenue": ("revenue",), "commission": ("commission",),
        "cost": ("cost", "spend"), "currency": ("currency",), "roi": ("roi",),
    },
    "social": {
        "date": ("date", "day", "period_end"), "platform": ("platform", "network"),
        "post_url": ("post_url", "url"), "post_id": ("post_id", "id"),
        "url": ("linked_article", "article_url", "canonical_url"), "slug": ("article_slug", "slug"),
        "impressions": ("impressions",), "views": ("views",), "reactions": ("reactions", "likes"),
        "comments": ("comments",), "shares": ("shares",), "clicks": ("clicks",),
        "publication_date": ("publication_date", "published_at"),
    },
}

REQUIRED = {
    "gsc": {"date", "url", "clicks", "impressions", "ctr", "average_position"},
    "content": {"date", "page_views"},
    "affiliate": {"date", "affiliate_clicks", "conversions"},
    "social": {"date", "platform", "impressions"},
}


def _utc_now(now: datetime | None = None) -> datetime:
    value = now or datetime.now(UTC)
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash(*parts: Any) -> str:
    return hashlib.sha256("|".join(str(part) for part in parts).encode("utf-8")).hexdigest()


def normalize_url(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    if not re.match(r"^https?://", raw, flags=re.I):
        return ""
    parts = urlsplit(raw)
    if not parts.hostname:
        return ""
    path = re.sub(r"/{2,}", "/", parts.path or "/")
    if path != "/":
        path = path.rstrip("/") + "/"
    return urlunsplit((parts.scheme.casefold(), parts.netloc.casefold(), path, "", ""))


def normalize_slug(value: Any, url: str = "") -> str:
    raw = str(value or "").strip() or (urlsplit(url).path.strip("/").split("/")[-1] if url else "")
    return re.sub(r"[^a-z0-9]+", "-", raw.casefold()).strip("-")[:160]


def normalize_date(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        try:
            return date.fromisoformat(text[:10]).isoformat()
        except ValueError:
            return ""


def normalize_platform(value: Any) -> str:
    raw = re.sub(r"[^a-z0-9]+", "", str(value or "").casefold())
    aliases = {"x": "twitter", "twittercom": "twitter", "linkedincom": "linkedin", "devto": "devto", "pinterestcom": "pinterest"}
    return aliases.get(raw, raw)


def _number(value: Any, *, percent: bool = False) -> float | None:
    text = str(value if value is not None else "").strip().replace(",", "")
    if not text:
        return None
    had_percent = text.endswith("%")
    try:
        result = float(text.rstrip("%"))
    except ValueError:
        return None
    if percent and (had_percent or result > 1):
        result /= 100
    return result


class AnalyticsFeedbackStore:
    """Manual/local analytics feedback; it has no publication or queue APIs."""

    def __init__(self, *, root: Path, db_path: Path | None = None, now: datetime | None = None, config: dict[str, Any] | None = None) -> None:
        self.root = root.resolve()
        self.db_path = (db_path or self.root / "data/intelligence/analytics_feedback/analytics_feedback.sqlite3").resolve()
        self.now = _utc_now(now)
        self.config = config or self._load_config()
        self.rules = {**DEFAULT_RULES, **dict(self.config.get("rules") or {})}

    def _load_config(self) -> dict[str, Any]:
        try:
            payload = json.loads((self.root / "config/operations_intelligence.json").read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            payload = {}
        config = dict(payload.get("analytics_feedback") or {}) if isinstance(payload, dict) else {}
        try:
            rules_payload = json.loads((self.root / "config/analytics_feedback_rules.json").read_text(encoding="utf-8"))
            if isinstance(rules_payload, dict) and isinstance(rules_payload.get("rules"), dict):
                config["rules"] = rules_payload["rules"]
                config["rules_schema_version"] = rules_payload.get("schema_version")
        except (OSError, UnicodeError, json.JSONDecodeError):
            pass
        return config

    def enabled(self) -> bool:
        return feature_enabled(self.root, "analytics_feedback.enabled")

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
                exists = connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='analytics_schema_migrations'").fetchone()
                if exists:
                    applied = [int(row[0]) for row in connection.execute("SELECT version FROM analytics_schema_migrations")]
        return {"schema": SCHEMA_NAME, "schema_version": SCHEMA_VERSION, "database_path": str(self.db_path), "applied_versions": sorted(applied), "pending_versions": [] if SCHEMA_VERSION in applied else [SCHEMA_VERSION], "idempotent": True}

    def migrate(self) -> dict[str, Any]:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        before = self.migration_plan()
        with self.connect() as connection:
            connection.executescript(MIGRATION_PATH.read_text(encoding="utf-8"))
            connection.execute("INSERT OR IGNORE INTO analytics_schema_migrations(version,name,applied_at) VALUES(?,?,?)", (SCHEMA_VERSION, "analytics_feedback", self.now.isoformat()))
            connection.commit()
        after = self.migration_plan()
        after["newly_applied"] = [v for v in after["applied_versions"] if v not in before["applied_versions"]]
        return after

    @staticmethod
    def _read_rows(path: Path) -> list[dict[str, Any]]:
        if path.suffix.casefold() == ".csv":
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                return [dict(row) for row in csv.DictReader(handle)]
        if path.suffix.casefold() == ".json":
            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                payload = payload.get("rows") or payload.get("records") or payload.get("data") or []
            if not isinstance(payload, list):
                raise ValueError("JSON import must be a list or contain rows/records/data.")
            return [dict(row) for row in payload if isinstance(row, dict)]
        raise ValueError("Only CSV and JSON manual exports are supported.")

    @staticmethod
    def _columns(row: dict[str, Any], source_type: str) -> dict[str, str]:
        actual = {str(key).casefold().strip(): str(key) for key in row}
        output: dict[str, str] = {}
        for canonical, aliases in SOURCE_ALIASES[source_type].items():
            match = next((actual[name] for name in aliases if name in actual), "")
            if match:
                output[canonical] = match
        return output

    def _inventory_slugs(self) -> set[str]:
        try:
            return {str(row.get("slug") or "") for row in article_inventory(self.root) if row.get("slug")}
        except (OSError, ValueError, TypeError):
            return set()

    def inspect_import(self, path: Path, *, source_type: str) -> dict[str, Any]:
        source_type = source_type.casefold().strip()
        if source_type not in SOURCE_ALIASES:
            raise ValueError(f"Unsupported source type: {source_type}")
        path = path.resolve()
        if not path.is_file():
            raise FileNotFoundError(str(path))
        raw = path.read_bytes()
        checksum = hashlib.sha256(raw).hexdigest()
        rows = self._read_rows(path)
        mapping = self._columns(rows[0], source_type) if rows else {}
        missing_columns = sorted(REQUIRED[source_type] - set(mapping))
        accepted: list[dict[str, Any]] = []
        rejected: list[dict[str, Any]] = []
        warnings: list[str] = []
        if missing_columns:
            warnings.append("missing_columns: " + ", ".join(missing_columns))
        seen: set[str] = set()
        inventory = self._inventory_slugs()
        for index, row in enumerate(rows, start=2):
            normalized, row_warnings, errors = self._normalize_row(row, mapping, source_type)
            identity = _hash(source_type, _json(normalized))
            if identity in seen:
                errors.append("duplicate_row")
            seen.add(identity)
            slug = str(normalized.get("slug") or "")
            if slug and inventory and slug not in inventory:
                row_warnings.append("article_not_in_inventory")
            if errors or missing_columns:
                rejected.append({"row_number": index, "errors": sorted(set(errors or ["schema_missing_columns"])), "source": row})
            else:
                normalized["warnings"] = sorted(set(row_warnings))
                accepted.append(normalized)
            warnings.extend(row_warnings)
        dates = sorted(row["date"] for row in accepted if row.get("date"))
        unique_dates = sorted(set(dates))
        if any(
            (date.fromisoformat(current) - date.fromisoformat(previous)).days > 31
            for previous, current in zip(unique_dates, unique_dates[1:])
        ):
            warnings.append("mixed_time_windows")
        if 0 < len(accepted) < int(self.config.get("minimum_rows", 30)):
            warnings.append("insufficient_sample")
        if dates and (self.now.date() - date.fromisoformat(dates[-1])).days < int(self.config.get("minimum_observation_age_days", 7)):
            warnings.append("data_too_recent")
        numeric = [float(row.get("impressions") or row.get("page_views") or 0) for row in accepted]
        if len(numeric) >= 4:
            mean = sum(numeric) / len(numeric)
            variance = sum((value - mean) ** 2 for value in numeric) / len(numeric)
            ordered = sorted(numeric)
            median = (ordered[(len(ordered) - 1) // 2] + ordered[len(ordered) // 2]) / 2
            if max(numeric) > mean + 3 * math.sqrt(variance) or max(numeric) > max(10, median * 10):
                warnings.append("outlier_detected")
        return {
            "schema_version": IMPORT_SCHEMA_VERSION,
            "dry_run": True,
            "production_state_changed": False,
            "import_id": f"analytics-{checksum[:16]}", "source_type": source_type,
            "source_file": str(path), "imported_at": self.now.isoformat(),
            "date_start": dates[0] if dates else "", "date_end": dates[-1] if dates else "",
            "row_count": len(rows), "accepted_row_count": len(accepted), "rejected_row_count": len(rejected),
            "warnings": sorted(set(warnings)), "missing_columns": missing_columns, "checksum": checksum,
            "accepted_rows": accepted, "quarantine": rejected,
        }

    def _normalize_row(self, row: dict[str, Any], mapping: dict[str, str], source_type: str) -> tuple[dict[str, Any], list[str], list[str]]:
        value = lambda key: row.get(mapping.get(key, ""), "")
        url = normalize_url(value("url"))
        slug = normalize_slug(value("slug"), url)
        day = normalize_date(value("date"))
        warnings: list[str] = []
        errors: list[str] = []
        if not day:
            errors.append("invalid_date")
        if value("url") and not url:
            errors.append("invalid_url")
        if source_type == "social" and not (slug or url):
            warnings.append("unmapped_article")
        elif source_type != "social" and not (slug or url):
            errors.append("missing_article_identity")
        output: dict[str, Any] = {"date": day, "url": url, "slug": slug}
        numeric_fields = set(SOURCE_ALIASES[source_type]) - {"date", "url", "slug", "query", "country", "device", "platform", "post_url", "post_id", "publication_date", "offer_id", "currency"}
        for key in numeric_fields:
            parsed = _number(value(key), percent=key in {"ctr", "engagement", "roi"})
            output[key] = None if source_type == "affiliate" and key in {"revenue", "commission", "cost", "roi"} and parsed is None else (0.0 if parsed is None else parsed)
            if parsed is not None and parsed < 0:
                errors.append(f"negative_{key}")
        for key in (set(SOURCE_ALIASES[source_type]) - numeric_fields - {"date", "url", "slug"}):
            output[key] = str(value(key) or "").strip()
        if source_type == "gsc":
            if not 0 <= output.get("ctr", 0) <= 1:
                errors.append("invalid_ctr")
            if output.get("impressions", 0) == 0:
                warnings.append("zero_impressions")
        if source_type == "affiliate":
            if output.get("conversions", 0) > output.get("affiliate_clicks", 0):
                errors.append("conversions_exceed_clicks")
            if output.get("revenue", 0) and not output.get("currency"):
                warnings.append("revenue_missing_currency")
        if source_type == "social":
            output["platform"] = normalize_platform(output.get("platform"))
            output["post_url"] = normalize_url(output.get("post_url"))
            output["publication_date"] = normalize_date(output.get("publication_date"))
            if not output["platform"]:
                errors.append("invalid_platform")
        if output.get("publication_date"):
            try:
                output["article_age_days"] = max(0, (self.now.date() - date.fromisoformat(output["publication_date"])).days)
            except ValueError:
                warnings.append("invalid_publication_date")
        return output, warnings, errors

    def confirm_import(self, report: dict[str, Any], *, confirm: bool) -> dict[str, Any]:
        if not confirm:
            raise ValueError("Explicit confirm is required.")
        if not self.enabled():
            return {"status": "FEATURE_DISABLED", "imported": False, "production_state_changed": False}
        self.migrate()
        with self.connect() as connection:
            existing = connection.execute("SELECT import_id FROM analytics_imports WHERE checksum=?", (report["checksum"],)).fetchone()
            if existing:
                return {"status": "UNCHANGED", "import_id": existing[0], "inserted_rows": 0, "production_state_changed": False}
            connection.execute(
                "INSERT INTO analytics_imports VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (report["import_id"], report["source_type"], report["source_file"], self.now.isoformat(), report["date_start"], report["date_end"], report["row_count"], report["accepted_row_count"], report["rejected_row_count"], _json(report["warnings"]), IMPORT_SCHEMA_VERSION, report["checksum"]),
            )
            window_id = _hash(report["import_id"], report["date_start"], report["date_end"])
            connection.execute("INSERT OR IGNORE INTO metric_windows VALUES(?,?,?,?,?,?,?)", (window_id, report["import_id"], report["date_start"], report["date_end"], report["accepted_row_count"], int("mixed_time_windows" not in report["warnings"]), self.now.isoformat()))
            for row in report["accepted_rows"]:
                self._insert_metric(connection, report, row)
            connection.commit()
        return {"status": "IMPORTED", "import_id": report["import_id"], "inserted_rows": report["accepted_row_count"], "rejected_rows": report["rejected_row_count"], "production_state_changed": False}

    def _insert_metric(self, connection: sqlite3.Connection, report: dict[str, Any], row: dict[str, Any]) -> None:
        source, import_id = report["source_type"], report["import_id"]
        confidence = max(0.1, min(1.0, 0.9 - 0.1 * len(row.get("warnings") or [])))
        quality = "WARNING" if row.get("warnings") else "PASS"
        metric_id = _hash(import_id, source, _json(row))
        common = (metric_id, import_id, row.get("slug", ""), row.get("url", ""))
        if source == "gsc":
            connection.execute("INSERT OR IGNORE INTO search_query_metrics VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (*common, row.get("query", ""), row["date"], row["date"], row.get("clicks", 0), row.get("impressions", 0), row.get("ctr", 0), row.get("average_position", 0), row.get("country", ""), row.get("device", ""), confidence, quality, self.now.isoformat()))
        elif source == "affiliate":
            connection.execute("INSERT OR IGNORE INTO affiliate_metrics VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (*common, row.get("offer_id", ""), row["date"], row["date"], row.get("affiliate_clicks", 0), row.get("conversions", 0), row.get("revenue") if "revenue" in row else None, row.get("commission") if "commission" in row else None, row.get("cost") if "cost" in row else None, row.get("currency", ""), row.get("roi") if "roi" in row else None, confidence, quality, self.now.isoformat()))
        elif source == "social":
            connection.execute("INSERT OR IGNORE INTO social_metrics VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (*common, row.get("platform", ""), row.get("post_id", ""), row.get("post_url", ""), row.get("publication_date", ""), row["date"], row["date"], row.get("impressions", 0), row.get("views", 0), row.get("reactions", 0), row.get("comments", 0), row.get("shares", 0), row.get("clicks", 0), confidence, quality, self.now.isoformat()))
        else:
            for metric_type in ("page_views", "users", "sessions", "engagement", "time_on_page", "article_age_days"):
                if metric_type not in row:
                    continue
                one_id = _hash(metric_id, metric_type)
                connection.execute("INSERT OR IGNORE INTO article_metrics VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (one_id, import_id, row.get("slug", ""), row.get("url", ""), metric_type, row["date"], row["date"], row.get(metric_type, 0), int(row.get("page_views") or row.get("sessions") or 0), source, confidence, quality, _json({"publication_date": row.get("publication_date", "")}), self.now.isoformat()))

    def _aggregate(self) -> dict[str, dict[str, Any]]:
        data: dict[str, dict[str, Any]] = defaultdict(lambda: {"source_import_ids": set(), "queries": set(), "dates": [], "warnings": set()})
        if not self.db_path.is_file():
            return {}
        with self.connect() as connection:
            import_warnings = {
                row["import_id"]: set(json.loads(row["warnings_json"] or "[]"))
                for row in connection.execute("SELECT import_id,warnings_json FROM analytics_imports")
            }
            for row in connection.execute("SELECT * FROM search_query_metrics"):
                key = row["article_slug"] or normalize_slug("", row["canonical_url"])
                if not key:
                    continue
                target = data[key]; target["slug"] = key; target["source_import_ids"].add(row["import_id"]); target["dates"].extend([row["date_start"], row["date_end"]]); target["queries"].add(row["query"])
                target["warnings"].update(import_warnings.get(row["import_id"], set()))
                for field in ("clicks", "impressions"):
                    target[field] = target.get(field, 0.0) + float(row[field])
                if target["impressions"]:
                    target["ctr"] = target["clicks"] / target["impressions"]
                target["average_position"] = float(row["average_position"])
            for row in connection.execute("SELECT * FROM article_metrics"):
                key = row["article_slug"] or normalize_slug("", row["canonical_url"])
                if not key: continue
                target = data[key]; target["slug"] = key; target["source_import_ids"].add(row["import_id"]); target["dates"].extend([row["date_start"], row["date_end"]]); target[row["metric_type"]] = target.get(row["metric_type"], 0.0) + float(row["value"])
                target["warnings"].update(import_warnings.get(row["import_id"], set()))
            for row in connection.execute("SELECT * FROM affiliate_metrics"):
                key = row["article_slug"] or normalize_slug("", row["canonical_url"])
                if not key: continue
                target = data[key]; target["slug"] = key; target["source_import_ids"].add(row["import_id"]); target["dates"].extend([row["date_start"], row["date_end"]])
                target["warnings"].update(import_warnings.get(row["import_id"], set()))
                for field in ("clicks", "conversions", "revenue", "cost"):
                    source_field = "affiliate_clicks" if field == "clicks" else field
                    if row[field] is not None: target[source_field] = target.get(source_field, 0.0) + float(row[field])
                if row["revenue"] is None or row["cost"] is None: target["warnings"].add("affiliate_revenue_or_cost_missing")
            for row in connection.execute("SELECT * FROM social_metrics"):
                key = row["article_slug"] or normalize_slug("", row["canonical_url"])
                if not key: continue
                target = data[key]; target["slug"] = key; target["source_import_ids"].add(row["import_id"]); target["dates"].extend([row["date_start"], row["date_end"]]); target["social_impressions"] = target.get("social_impressions", 0.0) + float(row["impressions"])
                target["warnings"].update(import_warnings.get(row["import_id"], set()))
        for target in data.values():
            queries = sorted(target.pop("queries"))
            target["query_count"] = len(queries)
            target["query_text"] = " ".join(queries)
            target["source_import_ids"] = sorted(target["source_import_ids"])
            target["warnings"] = sorted(target["warnings"])
            target["outlier"] = "outlier_detected" in target["warnings"]
            target["dates"] = sorted(set(value for value in target["dates"] if value))
            target["observation_age_days"] = (self.now.date() - date.fromisoformat(target["dates"][-1])).days if target["dates"] else 0
            target["sample_size"] = int(max(target.get("impressions", 0), target.get("page_views", 0), target.get("affiliate_clicks", 0), target.get("social_impressions", 0)))
        return data

    def evaluate_rules(self, row: dict[str, Any]) -> list[str]:
        """Return every deterministic rule match, with weak data short-circuiting."""
        threshold = lambda rule, key, default: float((self.rules.get(rule, {}).get("thresholds") or {}).get(key, default))
        sample = int(row.get("sample_size") or 0)
        age = int(row.get("observation_age_days") or 0)
        stale = {str(value).casefold() for value in row.get("stale_claim_types") or []}
        if sample < 30 or age < 7 or row.get("outlier"):
            return ["NEEDS_MORE_DATA"]
        matches: list[str] = []
        if "pricing" in stale: matches.append("PRICING_UPDATE")
        if "security" in stale: matches.append("SECURITY_UPDATE")
        if "feature" in stale: matches.append("FEATURE_UPDATE")
        if row.get("affiliate_clicks", 0) and (row.get("revenue") is None or row.get("cost") is None):
            return ["NEEDS_MORE_DATA"]
        if row.get("impressions", 0) >= self.rules["REVIEW_LOW_CTR"]["minimum_sample"] and row.get("ctr", 1) < threshold("REVIEW_LOW_CTR", "max_ctr", 0.02):
            matches.extend(["REVIEW_LOW_CTR", "IMPROVE_TITLE_META"])
        if row.get("impressions", 0) >= self.rules["REVIEW_POSITION_OPPORTUNITY"]["minimum_sample"] and threshold("REVIEW_POSITION_OPPORTUNITY", "position_min", 4) <= row.get("average_position", 100) <= threshold("REVIEW_POSITION_OPPORTUNITY", "position_max", 20):
            matches.extend(["REVIEW_POSITION_OPPORTUNITY", "STRENGTHEN_INTERNAL_LINKS"])
        if row.get("query_count", 0) >= threshold("EXPAND_FAQ", "query_count", 5): matches.append("EXPAND_FAQ")
        query_text = str(row.get("query_text") or "").casefold()
        if any(token in query_text for token in (" vs ", "alternative", "compare", "comparison")):
            matches.append("CREATE_COMPARISON_FOLLOWUP")
        if any(token in query_text for token in ("use case", "workflow", "how to")):
            matches.append("CREATE_USE_CASE_FOLLOWUP")
        if row.get("affiliate_clicks", 0) >= self.rules["REVIEW_CONVERSION_GAP"]["minimum_sample"] and row.get("conversions", 0) / max(1, row["affiliate_clicks"]) < threshold("REVIEW_CONVERSION_GAP", "max_conversion_rate", 0.02):
            matches.append("REVIEW_CONVERSION_GAP")
        if row.get("page_views", 0) >= threshold("REVIEW_HIGH_TRAFFIC_LOW_REVENUE", "page_views", 500) and row.get("revenue") is not None and row.get("cost") is not None and row.get("revenue", 0) <= threshold("REVIEW_HIGH_TRAFFIC_LOW_REVENUE", "max_revenue", 1):
            matches.append("REVIEW_HIGH_TRAFFIC_LOW_REVENUE")
        if row.get("clicks", 0) >= threshold("PROMOTE_HIGH_PERFORMING_TOPIC", "clicks", 100) or row.get("conversions", 0) >= threshold("PROMOTE_HIGH_PERFORMING_TOPIC", "conversions", 3):
            matches.append("PROMOTE_HIGH_PERFORMING_TOPIC")
        if row.get("article_age_days", 0) >= self.rules["RETIRE_LOW_VALUE_ANGLE"]["minimum_age_days"] and row.get("impressions", 0) <= threshold("RETIRE_LOW_VALUE_ANGLE", "max_impressions", 20) and row.get("clicks", 0) <= threshold("RETIRE_LOW_VALUE_ANGLE", "max_clicks", 1):
            matches.append("RETIRE_LOW_VALUE_ANGLE")
        elif row.get("article_age_days", 0) >= threshold("REFRESH_ARTICLE", "article_age_days", 180):
            matches.append("REFRESH_ARTICLE")
        return list(dict.fromkeys(matches)) or ["KEEP_OBSERVING"]

    def _references(self, slug: str) -> tuple[list[str], list[str], list[str]]:
        memory_refs: list[str] = []
        graph_refs: list[str] = []
        warnings: list[str] = []
        if feature_enabled(self.root, "editorial_memory.enabled"):
            try:
                from .editorial_memory import EditorialMemoryStore
                memory = EditorialMemoryStore(root=self.root)
                if memory.database_path.is_file():
                    memory_refs = [str(row.get("record_id") or row.get("slug") or "") for row in memory.latest_records() if str(row.get("slug") or "") == slug][:5]
                else: warnings.append("editorial_memory_missing")
            except (OSError, ValueError, sqlite3.Error): warnings.append("editorial_memory_unavailable")
        if feature_enabled(self.root, "knowledge_graph.enabled"):
            try:
                from .knowledge_graph_store import KnowledgeGraphStore
                graph = KnowledgeGraphStore(root=self.root)
                if graph.db_path.is_file(): graph_refs = [str(row.get("entity_id") or "") for row in graph.find_entities(slug.replace("-", " "))[:5]]
                else: warnings.append("knowledge_graph_missing")
            except (OSError, ValueError, sqlite3.Error): warnings.append("knowledge_graph_unavailable")
        return memory_refs, graph_refs, warnings

    def _memory_context(self) -> dict[str, dict[str, Any]]:
        context: dict[str, dict[str, Any]] = defaultdict(lambda: {"stale_claim_types": set(), "warnings": set()})
        if not feature_enabled(self.root, "editorial_memory.enabled"):
            return {}
        try:
            from .editorial_memory import EditorialMemoryStore
            memory = EditorialMemoryStore(root=self.root)
            if not memory.database_path.is_file():
                return {}
            for row in memory.latest_records():
                slug = str(row.get("slug") or "")
                written = normalize_date(row.get("written_date"))
                if written and (self.now.date() - date.fromisoformat(written)).days <= 30:
                    context[slug]["warnings"].add("recently_refreshed")
                for reason in row.get("rejection_reasons") or []:
                    context[slug]["warnings"].add(f"previous_rejection:{reason}")
            stale = memory.detect_stale_claims(as_of=self.now.date(), persist=False)
            for review in stale.get("reviews") or []:
                context[str(review.get("slug") or "")]["stale_claim_types"].add(str(review.get("claim_type") or "general"))
        except (OSError, ValueError, sqlite3.Error):
            return {}
        return {slug: {"stale_claim_types": sorted(value["stale_claim_types"]), "warnings": sorted(value["warnings"])} for slug, value in context.items()}

    def generate_candidates(self, *, dry_run: bool = True) -> dict[str, Any]:
        if not self.enabled():
            return {"status": "FEATURE_DISABLED", "candidate_count": 0, "candidates": [], "workflow_state_changed": False}
        rows = self._aggregate()
        memory_context = self._memory_context()
        candidates: list[dict[str, Any]] = []
        for slug, row in sorted(rows.items()):
            context = memory_context.get(slug, {})
            row["stale_claim_types"] = list(context.get("stale_claim_types") or [])
            row["warnings"] = sorted(set(row.get("warnings") or []) | set(context.get("warnings") or []))
            row["legacy_performance_classification"] = PerformanceEngine(root=self.root, config=self.config).classify(row)
            memory_refs, graph_refs, reference_warnings = self._references(slug)
            for recommendation_type in self.evaluate_rules(row):
                if recommendation_type == "REFRESH_ARTICLE" and "recently_refreshed" in row["warnings"]:
                    recommendation_type = "KEEP_OBSERVING"
                rule = self.rules[recommendation_type]
                missing = [name for name in rule.get("required", []) if name not in row]
                if recommendation_type == "NEEDS_MORE_DATA" and row.get("affiliate_clicks"):
                    missing = sorted(set(missing + [name for name in ("revenue", "cost") if row.get(name) is None]))
                confidence = self._confidence(row, missing)
                status = "NEEDS_MORE_DATA" if recommendation_type == "NEEDS_MORE_DATA" else "PENDING_REVIEW"
                reason = self._reason(recommendation_type, row)
                fingerprint = _hash(slug, recommendation_type, row.get("dates"), row.get("source_import_ids"))
                candidates.append({
                "candidate_id": f"feedback-{fingerprint[:16]}", "fingerprint": fingerprint,
                "article_slug": slug, "topic": slug.replace("-", " "), "root_topic": "",
                "recommendation_type": recommendation_type,
                "recommendation": recommendation_type.replace("_", " ").title(), "reason": reason,
                "evidence": {"metrics": row, "rule_id": recommendation_type, "rule_version": rule["version"]},
                "metrics": row, "comparison_window": f"{row['dates'][0]}..{row['dates'][-1]}" if row.get("dates") else "",
                "confidence": confidence, "priority": self._priority(recommendation_type, row),
                "risk_flags": sorted(set(row.get("warnings", []) + reference_warnings)), "status": status,
                "human_status": "pending", "interpretation_type": "possible_opportunity" if status == "PENDING_REVIEW" else "insufficient_evidence",
                "causality_warning": "Observed metrics show correlation only; they do not establish that an editorial change caused the result.",
                "limitations": ["Manual/local exports may be incomplete or use non-comparable attribution windows."],
                "missing_data": missing, "source_import_ids": row.get("source_import_ids", []),
                "memory_references": memory_refs, "graph_references": graph_refs,
                    "created_at": self.now.isoformat(), "review_by": (self.now + timedelta(days=30)).date().isoformat(),
                    "expires_at": (self.now + timedelta(days=60)).date().isoformat(),
                })
        inserted = 0
        if not dry_run:
            self.migrate()
            with self.connect() as connection:
                for candidate in candidates:
                    cursor = connection.execute(
                        """INSERT OR IGNORE INTO feedback_candidates VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (candidate["candidate_id"], candidate["fingerprint"], candidate["article_slug"], candidate["topic"], candidate["root_topic"], candidate["recommendation_type"], candidate["recommendation"], candidate["reason"], _json(candidate["metrics"]), candidate["comparison_window"], candidate["confidence"], candidate["priority"], _json(candidate["risk_flags"]), candidate["status"], candidate["human_status"], candidate["interpretation_type"], candidate["causality_warning"], _json(candidate["limitations"]), _json(candidate["missing_data"]), _json(candidate["source_import_ids"]), _json(candidate["memory_references"]), _json(candidate["graph_references"]), candidate["created_at"], candidate["review_by"], candidate["expires_at"]),
                    )
                    inserted += cursor.rowcount
                    for import_id in candidate["source_import_ids"]:
                        evidence_id = _hash(candidate["candidate_id"], import_id, _json(candidate["evidence"]))
                        connection.execute("INSERT OR IGNORE INTO feedback_evidence VALUES(?,?,?,?,?)", (evidence_id, candidate["candidate_id"], import_id, _json(candidate["evidence"]), self.now.isoformat()))
                connection.commit()
        return {"status": "DRY_RUN" if dry_run else "GENERATED", "candidate_count": len(candidates), "inserted_count": inserted, "duplicate_count": len(candidates) - inserted if not dry_run else 0, "candidates": candidates, "workflow_state_changed": False}

    @staticmethod
    def _confidence(row: dict[str, Any], missing: list[str]) -> float:
        sample = min(1.0, float(row.get("sample_size") or 0) / 500)
        age = min(1.0, float(row.get("observation_age_days") or 0) / 30)
        completeness = max(0.0, 1 - len(missing) * 0.2 - len(row.get("warnings") or []) * 0.1)
        return round(max(0.05, min(1.0, sample * 0.4 + age * 0.2 + completeness * 0.4)), 3)

    @staticmethod
    def _priority(kind: str, row: dict[str, Any]) -> str:
        if kind in {"PRICING_UPDATE", "SECURITY_UPDATE"}: return "HIGH"
        if kind == "NEEDS_MORE_DATA": return "LOW"
        impact = max(float(row.get("impressions") or 0), float(row.get("page_views") or 0), float(row.get("affiliate_clicks") or 0))
        return "HIGH" if impact >= 1000 else "MEDIUM" if impact >= 100 else "LOW"

    @staticmethod
    def _reason(kind: str, row: dict[str, Any]) -> str:
        if kind in {"REVIEW_LOW_CTR", "IMPROVE_TITLE_META"}:
            return "CTR is below the configured reference level in the observed window; operator review of title/meta may be useful."
        if kind == "NEEDS_MORE_DATA":
            return "The available sample, observation age, mapping, or revenue/cost evidence is insufficient for a stronger recommendation."
        return f"Observed local metrics matched deterministic rule {kind}; this is an advisory opportunity, not a causal conclusion."

    def review(self, candidate_id: str, *, action: str, actor: str, confirm: bool, note: str = "") -> dict[str, Any]:
        if not confirm: raise ValueError("Explicit confirm is required for review state changes.")
        if not actor.strip(): raise ValueError("Actor is required for the audit event.")
        if action not in REVIEW_ACTIONS: raise ValueError(f"Unsupported action: {action}")
        if not self.enabled(): return {"status": "FEATURE_DISABLED", "workflow_state_changed": False}
        target = REVIEW_ACTIONS[action]
        with self.connect() as connection:
            row = connection.execute("SELECT status FROM feedback_candidates WHERE candidate_id=?", (candidate_id,)).fetchone()
            if not row: raise FileNotFoundError(candidate_id)
            previous = str(row[0])
            connection.execute("UPDATE feedback_candidates SET status=?, human_status=? WHERE candidate_id=?", (target, "approved" if target == "APPROVED_FOR_BACKLOG" else target.casefold(), candidate_id))
            event_id = _hash(candidate_id, previous, target, action, actor, self.now.isoformat())
            connection.execute("INSERT INTO feedback_review_events VALUES(?,?,?,?,?,?,?,?)", (event_id, candidate_id, previous, target, action, actor.strip(), note, self.now.isoformat()))
            connection.commit()
        return {"candidate_id": candidate_id, "from_status": previous, "status": target, "audit_event_id": event_id, "publication_state_changed": False, "workflow_state_changed": False}

    def approved_backlog(self, *, root_topics: Iterable[str] = (), include_expired: bool = False) -> dict[str, Any]:
        if not self.enabled() or not self.db_path.is_file():
            return {"enabled": self.enabled(), "count": 0, "candidates": [], "warning": "feature_disabled_or_store_missing", "advisory_only": True, "weekly_roots_changed": False, "daily_tasks_created": False}
        today = self.now.date().isoformat()
        tokens = {str(value).casefold() for value in root_topics if str(value).strip()}
        with self.connect() as connection:
            rows = [dict(row) for row in connection.execute("SELECT * FROM feedback_candidates WHERE status='APPROVED_FOR_BACKLOG' ORDER BY priority, confidence DESC")]
            links = {row["candidate_id"]: dict(row) for row in connection.execute("SELECT * FROM feedback_backlog_links")}
        output = []
        expired = 0
        for row in rows:
            is_expired = bool(row.get("expires_at") and row["expires_at"] < today)
            if is_expired:
                expired += 1
                if not include_expired: continue
            haystack = f"{row.get('article_slug','')} {row.get('topic','')} {row.get('root_topic','')}".casefold()
            row["related_to_current_roots"] = bool(tokens and any(token in haystack or haystack in token for token in tokens))
            row["used_in_plan"] = links.get(row["candidate_id"], {})
            row["expired"] = is_expired
            output.append(row)
        return {"enabled": True, "count": len(output), "expired_count": expired, "candidates": output, "advisory_only": True, "weekly_roots_changed": False, "daily_tasks_created": False}

    def list_candidates(
        self, *, article: str = "", topic: str = "", recommendation_type: str = "",
        priority: str = "", minimum_confidence: float = 0.0, status: str = "",
    ) -> list[dict[str, Any]]:
        if not self.db_path.is_file():
            return []
        clauses, values = ["confidence >= ?"], [float(minimum_confidence)]
        for column, value in (("article_slug", article), ("topic", topic), ("recommendation_type", recommendation_type), ("priority", priority), ("status", status)):
            if value:
                if column in {"article_slug", "topic"}:
                    clauses.append(f"{column} LIKE ?"); values.append(f"%{value}%")
                else:
                    clauses.append(f"{column} = ?"); values.append(value)
        with self.connect() as connection:
            rows = [dict(row) for row in connection.execute(f"SELECT * FROM feedback_candidates WHERE {' AND '.join(clauses)} ORDER BY created_at DESC", values)]
        for row in rows:
            for key in ("metrics_json", "risk_flags_json", "limitations_json", "missing_data_json", "source_import_ids_json", "memory_references_json", "graph_references_json"):
                row[key.removesuffix("_json")] = json.loads(row.pop(key) or "[]")
        return rows

    def candidate_evidence(self, candidate_id: str) -> dict[str, Any]:
        if not self.db_path.is_file():
            raise FileNotFoundError(candidate_id)
        with self.connect() as connection:
            candidate = connection.execute("SELECT * FROM feedback_candidates WHERE candidate_id=?", (candidate_id,)).fetchone()
            if not candidate: raise FileNotFoundError(candidate_id)
            evidence = [json.loads(row[0]) for row in connection.execute("SELECT evidence_json FROM feedback_evidence WHERE candidate_id=?", (candidate_id,))]
            events = [dict(row) for row in connection.execute("SELECT * FROM feedback_review_events WHERE candidate_id=? ORDER BY created_at", (candidate_id,))]
            links = [dict(row) for row in connection.execute("SELECT * FROM feedback_backlog_links WHERE candidate_id=? ORDER BY created_at", (candidate_id,))]
        return {"candidate": dict(candidate), "evidence": evidence, "review_events": events, "backlog_links": links, "read_only": True}

    def record_backlog_use(
        self, candidate_id: str, *, plan_id: str, source_week: str, target_week: str,
        actor: str, confirm: bool,
    ) -> dict[str, Any]:
        if not confirm: raise ValueError("Explicit confirm is required to record backlog provenance.")
        if not self.enabled(): return {"status": "FEATURE_DISABLED", "weekly_roots_changed": False, "daily_tasks_created": False, "publication_state_changed": False}
        if not actor.strip() or not plan_id.strip(): raise ValueError("Actor and plan_id are required.")
        if not normalize_date(source_week) or not normalize_date(target_week): raise ValueError("Valid source_week and target_week are required.")
        with self.connect() as connection:
            candidate = connection.execute("SELECT status FROM feedback_candidates WHERE candidate_id=?", (candidate_id,)).fetchone()
            if not candidate: raise FileNotFoundError(candidate_id)
            if candidate[0] != "APPROVED_FOR_BACKLOG": raise ValueError("Only a human-approved feedback candidate can be linked to planning.")
            link_id = _hash(candidate_id, plan_id)
            cursor = connection.execute("INSERT OR IGNORE INTO feedback_backlog_links VALUES(?,?,?,?,?,?,?)", (link_id, candidate_id, plan_id.strip(), source_week, target_week, self.now.isoformat(), self.now.isoformat()))
            event_id = _hash(link_id, actor, self.now.isoformat())
            connection.execute("INSERT OR IGNORE INTO feedback_review_events VALUES(?,?,?,?,?,?,?,?)", (event_id, candidate_id, candidate[0], candidate[0], "link-plan", actor.strip(), f"plan_id={plan_id}; source_week={source_week}; target_week={target_week}", self.now.isoformat()))
            connection.commit()
        return {"status": "LINKED" if cursor.rowcount else "UNCHANGED", "candidate_id": candidate_id, "plan_id": plan_id, "source_week": source_week, "target_week": target_week, "weekly_roots_changed": False, "daily_tasks_created": False, "publication_state_changed": False}

    def report(self) -> dict[str, Any]:
        if not self.db_path.is_file(): return {"schema": SCHEMA_NAME, "database_path": str(self.db_path), "imports": 0, "candidates": 0, "review_events": 0, "recommendation_only": True}
        with self.connect() as connection:
            counts = {table: int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]) for table in ("analytics_imports", "article_metrics", "search_query_metrics", "affiliate_metrics", "social_metrics", "feedback_candidates", "feedback_review_events", "feedback_backlog_links")}
            states = {row[0]: int(row[1]) for row in connection.execute("SELECT status,COUNT(*) FROM feedback_candidates GROUP BY status")}
        return {"schema": SCHEMA_NAME, "database_path": str(self.db_path), "counts": counts, "candidate_states": states, "recommendation_only": True, "publication_state_changed": False}


def planning_feedback_advisory(root: Path, *, root_topics: Iterable[str] = (), now: datetime | None = None) -> dict[str, Any]:
    """Fail-open, read-only bridge used by Menu 1/2."""
    try:
        return AnalyticsFeedbackStore(root=root, now=now).approved_backlog(root_topics=root_topics)
    except (OSError, ValueError, sqlite3.Error) as exc:
        return {"enabled": feature_enabled(root, "analytics_feedback.enabled"), "count": 0, "candidates": [], "warning": f"analytics_unavailable: {exc}", "advisory_only": True, "weekly_roots_changed": False, "daily_tasks_created": False}


def rule_catalog() -> list[dict[str, Any]]:
    return [{"rule_id": name, **value, "exclusions": ["outlier", "insufficient_sample", "too_recent"], "confidence_calculation": "completeness + sample size + observation age", "reason_template": "Observed metrics matched the configured rule; operator review is recommended."} for name, value in DEFAULT_RULES.items()]
