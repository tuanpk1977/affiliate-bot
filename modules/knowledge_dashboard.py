from __future__ import annotations

from pathlib import Path
from typing import Any

from config import settings
from modules.knowledge_registry import KnowledgeRegistry, REVIEWABLE_TYPES, _read_json, _write_csv, _write_json


def _write_md(path: Path, lines: list[str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return path


class KnowledgeDashboard:
    def __init__(self, data_dir: Path | None = None, config: dict[str, Any] | None = None, registry: KnowledgeRegistry | None = None) -> None:
        self.data_dir = data_dir or settings.data_dir
        self.config = config or {}
        self.registry = registry or KnowledgeRegistry(self.data_dir, self.config)
        self.queue_path = self.data_dir / "source_review_queue.json"
        self.json_path = self.data_dir / "knowledge_dashboard.json"
        self.csv_path = self.data_dir / "knowledge_dashboard.csv"
        self.md_path = self.data_dir / "knowledge_dashboard.md"

    def generate(self) -> dict[str, Any]:
        rows = self.registry.load_registry()
        queue = _read_json(self.queue_path, [])
        total = len(rows)
        verified = [row for row in rows if str(row.get("verification_status", "")) == "verified"]
        pending = [row for row in rows if str(row.get("verification_status", "")) in {"pending", "needs_review"}]
        expired = [row for row in rows if str(row.get("verification_status", "")) == "expired"]
        duplicate = [row for row in rows if str(row.get("verification_status", "")) == "duplicate"]
        average_trust = round(sum(float(row.get("trust_score", 0)) for row in rows) / max(1, total), 2)
        average_freshness = round(sum(float(row.get("freshness_score", 0)) for row in rows) / max(1, total), 2)
        slugs = sorted({str(row.get("slug", "")) for row in rows if str(row.get("slug", "")).strip()})
        missing_by_type = {
            "official_docs": self._count_missing(slugs, rows, "official_docs"),
            "pricing": self._count_missing(slugs, rows, "pricing_page"),
            "release_notes": self._count_missing(slugs, rows, "release_notes"),
            "affiliate": self._count_missing(slugs, rows, "affiliate_program_page"),
            "competitor": self._count_missing(slugs, rows, "competitor_article"),
        }
        weak_topics = self._top_weak_topics(rows)
        report = {
            "verified_sources": len(verified),
            "pending_review": len(pending),
            "expired_sources": len(expired),
            "duplicate_sources": len(duplicate),
            "coverage": round(len(verified) / max(1, total) * 100, 2),
            "average_trust": average_trust,
            "average_freshness": average_freshness,
            "verified_percent": round(len(verified) / max(1, total) * 100, 2),
            "pending_percent": round(len(pending) / max(1, total) * 100, 2),
            "expired_percent": round(len(expired) / max(1, total) * 100, 2),
            "duplicate_percent": round(len(duplicate) / max(1, total) * 100, 2),
            "official_docs_percent": round(sum(1 for row in rows if str(row.get("source_type", "")) == "official_docs") / max(1, total) * 100, 2),
            "pricing_percent": round(sum(1 for row in rows if str(row.get("source_type", "")) == "pricing_page") / max(1, total) * 100, 2),
            "affiliate_percent": round(sum(1 for row in rows if str(row.get("source_type", "")) == "affiliate_program_page") / max(1, total) * 100, 2),
            "competitor_percent": round(sum(1 for row in rows if str(row.get("source_type", "")) == "competitor_article") / max(1, total) * 100, 2),
            "missing_official_docs": missing_by_type["official_docs"],
            "missing_pricing": missing_by_type["pricing"],
            "missing_release_notes": missing_by_type["release_notes"],
            "missing_affiliate": missing_by_type["affiliate"],
            "missing_competitor_snapshots": missing_by_type["competitor"],
            "top_weak_topics": weak_topics,
            "queue_items": len(queue) if isinstance(queue, list) else 0,
        }
        rows_for_csv = [{"metric": key, "value": ", ".join(value) if isinstance(value, list) else value} for key, value in report.items()]
        _write_json(self.json_path, report)
        _write_csv(self.csv_path, rows_for_csv)
        _write_md(
            self.md_path,
            [
                "# Knowledge Dashboard",
                "",
                f"- Verified Sources: {report['verified_sources']}",
                f"- Pending Review: {report['pending_review']}",
                f"- Expired Sources: {report['expired_sources']}",
                f"- Duplicate Sources: {report['duplicate_sources']}",
                f"- Coverage: {report['coverage']}",
                f"- Average Trust: {report['average_trust']}",
                f"- Average Freshness: {report['average_freshness']}",
                f"- Missing Official Docs: {report['missing_official_docs']}",
                f"- Missing Pricing: {report['missing_pricing']}",
                f"- Missing Release Notes: {report['missing_release_notes']}",
                f"- Missing Affiliate: {report['missing_affiliate']}",
                f"- Missing Competitor Snapshots: {report['missing_competitor_snapshots']}",
            ],
        )
        return report

    def _count_missing(self, slugs: list[str], rows: list[dict[str, Any]], source_type: str) -> int:
        return sum(
            1
            for slug in slugs
            if not any(
                str(row.get("slug", "")) == slug
                and str(row.get("source_type", "")) == source_type
                and str(row.get("verification_status", "")) == "verified"
                for row in rows
            )
        )

    def _top_weak_topics(self, rows: list[dict[str, Any]]) -> list[str]:
        counts: dict[str, int] = {}
        for row in rows:
            slug = str(row.get("slug", "")).strip()
            if not slug:
                continue
            if str(row.get("verification_status", "")) == "verified":
                continue
            counts[slug] = counts.get(slug, 0) + 1
        ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        return [slug for slug, _ in ranked[:10]]
