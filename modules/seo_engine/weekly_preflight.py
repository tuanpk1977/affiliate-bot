from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Callable

from .keyword_research import collect_candidates
from .seo_pipeline import SeoPipeline


VALID_STATUSES = {"RUN", "SKIP", "REVIEW", "BLOCKED", "ERROR"}


def configured_seed_keywords(config: dict[str, Any]) -> list[str]:
    """Return the deduplicated primary + reserve evergreen candidate inventory."""
    values = [
        *list(config.get("seed_keywords") or []),
        *list(config.get("evergreen_root_reserve_keywords") or []),
    ]
    return list(dict.fromkeys(str(value).strip() for value in values if str(value).strip()))


def _fingerprint(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _mtime(path: Path) -> float:
    return path.stat().st_mtime if path.exists() else 0.0


def _step(status: str, reason: str, **details: Any) -> dict[str, Any]:
    if status not in VALID_STATUSES:
        raise ValueError(status)
    return {"status": status, "reason": reason, **details}


@dataclass
class WeeklySeoPreflight:
    root: Path
    now: datetime | None = None

    def __post_init__(self) -> None:
        self.root = self.root.resolve()
        self.now = (self.now or datetime.now(UTC)).astimezone(UTC)
        self.pipeline = SeoPipeline(root=self.root)

    def detect(
        self, *, seeds: list[str] | None = None, imports: list[Path] | None = None
    ) -> dict[str, Any]:
        seeds = list(seeds) if seeds else configured_seed_keywords(self.pipeline.config)
        imports = [path.resolve() for path in (imports or [])]
        run_id = f"weekly-seo-{self.now:%Y%m%dT%H%M%SZ}-{_fingerprint([seeds, [str(p) for p in imports]])[:8]}"
        missing = [str(path) for path in imports if not path.is_file()]
        if not seeds and not imports:
            source = _step("BLOCKED", "No seed keywords or keyword import files are configured.")
            prospective: list[dict[str, Any]] = []
        elif missing:
            source = _step("BLOCKED", "One or more keyword import files are missing.", missing=missing)
            prospective = []
        else:
            try:
                prospective = collect_candidates(seeds, imports)
                current = self.pipeline._read(self.pipeline.data_dir / "keyword_candidates.json", [])
                changed = _fingerprint(prospective) != _fingerprint(current)
                source = _step(
                    "RUN" if changed else "SKIP",
                    "New or changed keyword evidence detected."
                    if changed
                    else "Keyword evidence is unchanged from the saved candidate inventory.",
                    candidate_count=len(prospective),
                )
            except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
                prospective = []
                source = _step("ERROR", f"Keyword source could not be inspected: {exc}")

        clusters = self.pipeline._read(self.pipeline.data_dir / "keyword_clusters.json", [])
        assigned = {
            str(value).casefold()
            for row in clusters if isinstance(row, dict)
            for value in [row.get("primary_keyword"), *(row.get("secondary_keywords") or [])]
            if value
        }
        unassigned = [
            row.get("keyword") for row in prospective
            if str(row.get("keyword") or "").casefold() not in assigned
        ]
        invalid_clusters = [
            row.get("cluster_id")
            for row in clusters if isinstance(row, dict)
            if not row.get("cluster_name") or not row.get("primary_keyword")
        ]
        source_blocked = source["status"] in {"BLOCKED", "ERROR"}
        cluster_run = source["status"] == "RUN" or not clusters or bool(unassigned or invalid_clusters)
        cluster = _step(
            "BLOCKED" if source_blocked else ("RUN" if cluster_run else "SKIP"),
            "Keyword input is blocked."
            if source_blocked
            else (
                "New/unassigned keywords or incomplete clusters require rebuilding."
                if cluster_run else "All current keywords have complete cluster assignments."
            ),
            unassigned_count=len(unassigned),
            invalid_cluster_count=len(invalid_clusters),
        )

        gap_path = self.pipeline.data_dir / "content_gaps.json"
        newest_inventory = max(
            [_mtime(path) for base in (self.root / "docs", self.root / "data/production_article_drafts")
             if base.exists() for path in base.glob("*/index.html")]
            or [0.0]
        )
        gap_run = cluster["status"] == "RUN" or not gap_path.exists() or newest_inventory > _mtime(gap_path)
        gaps = _step(
            "BLOCKED" if cluster["status"] == "BLOCKED" else ("RUN" if gap_run else "SKIP"),
            "Cluster input is blocked."
            if cluster["status"] == "BLOCKED"
            else ("Clusters or local content inventory changed." if gap_run else "Gap report is newer than its inputs."),
        )

        opportunity_path = self.pipeline.data_dir / "opportunities.json"
        opportunity_run = gap_run or not opportunity_path.exists() or _mtime(gap_path) > _mtime(opportunity_path)
        opportunities = _step(
            "BLOCKED" if gaps["status"] == "BLOCKED" else ("RUN" if opportunity_run else "SKIP"),
            "Gap input is blocked."
            if gaps["status"] == "BLOCKED"
            else ("New gaps or stale opportunity scores detected." if opportunity_run else "Opportunity ranking is current."),
        )

        link_path = self.pipeline.data_dir / "internal_link_plan.json"
        cutoff = self.now - timedelta(days=8)
        new_articles = [
            path.parent.name
            for base in (self.root / "data/production_article_drafts", self.root / "docs")
            if base.exists()
            for path in base.glob("*/index.html")
            if datetime.fromtimestamp(path.stat().st_mtime, UTC) >= cutoff
            and path.stat().st_mtime > _mtime(link_path)
        ]
        orphan_count = self._latest_orphan_count()
        link_run = not link_path.exists() or bool(new_articles) or orphan_count > 0
        links = _step(
            "REVIEW" if link_run else "SKIP",
            "New articles, orphan findings, or a missing link plan require recommendations."
            if link_run else "No new article or orphan signal since the saved link plan.",
            new_article_count=len(set(new_articles)),
            orphan_count=orphan_count,
            recommendation_only=True,
        )

        existing = {row["slug"] for row in self.pipeline.existing_pages()}
        gap_rows = self.pipeline._read(gap_path, [])
        duplicate_slugs = sorted({str(row.get("slug")) for row in gap_rows if row.get("slug") in existing})
        warnings = [f"Duplicate/canonical candidate excluded: {slug}" for slug in duplicate_slugs]
        roots = self._weekly_roots()
        actions = {
            "import_keywords": source,
            "build_clusters": cluster,
            "analyze_gaps": gaps,
            "rank_opportunities": opportunities,
            "plan_internal_links": links,
        }
        executable = [name for name, row in actions.items() if row["status"] in {"RUN", "REVIEW"}]
        blocked = any(row["status"] in {"BLOCKED", "ERROR"} for row in actions.values())
        return {
            "schema_version": "weekly_seo_preflight_v1",
            "run_id": run_id,
            "timestamp": self.now.isoformat(),
            "mode": "dry-run",
            "actions": actions,
            "weekly_roots": roots,
            "weekly_roots_changed": False,
            "warnings": warnings,
            "recommended_steps": executable,
            "recommended_next_action": "Resolve blocked inputs."
            if blocked else ("Run the recommended steps after operator confirmation." if executable else "No SEO work is required."),
            "blocked": blocked,
            "production_content_modified": False,
            "queue_modified": False,
            "approval_changed": False,
            "published": False,
        }

    def execute(self, report: dict[str, Any]) -> dict[str, Any]:
        if report.get("blocked"):
            return {**report, "execution_status": "BLOCKED", "reason": "Preflight has blocked inputs."}
        steps = list(report.get("recommended_steps") or [])
        pipeline_steps = [step for step in steps if step != "plan_internal_links" or report["actions"][step]["status"] == "REVIEW"]
        result = self.pipeline.run_selected(
            pipeline_steps,
            weekly_roots=list(report.get("weekly_roots") or []),
        )
        final = {**report, "mode": "write", "execution_status": "EXECUTED", "execution": result}
        path = self.report_path(report["run_id"])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(final, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        final["report_path"] = str(path)
        return final

    def run(
        self,
        *,
        seeds: list[str] | None = None,
        imports: list[Path] | None = None,
        dry_run: bool = False,
        yes: bool = False,
        confirm: Callable[[str], str] = input,
    ) -> dict[str, Any]:
        report = self.detect(seeds=seeds, imports=imports)
        if dry_run or report["blocked"]:
            return report
        approved = yes or confirm("Tiếp tục chạy các bước được đề xuất? [Y/N] ").strip().casefold() == "y"
        if not approved:
            return {**report, "execution_status": "CANCELLED", "reason": "Operator selected N; no data was written."}
        return self.execute(report)

    def report_path(self, run_id: str) -> Path:
        return self.root / "data/reports/weekly_preflight/seo" / f"{run_id}.json"

    def _latest_orphan_count(self) -> int:
        paths = sorted((self.root / "data/intelligence/calibration").glob("*/orphan_validation.json"))
        if not paths:
            return 0
        payload = self.pipeline._read(paths[-1], {})
        return int(payload.get("production_true_orphan_unique_count") or 0)

    def _weekly_roots(self) -> list[str]:
        paths = sorted((self.root / "data/editorial_queue/weeks").glob("*/week.json"))
        if not paths:
            return []
        payload = self.pipeline._read(paths[-1], {})
        return [str(row.get("slug") or row.get("root_topic_id") or "") for row in payload.get("topics", [])[:2]]


def render_console(report: dict[str, Any], *, verbose: bool = False) -> str:
    labels = (
        ("Import keywords", "import_keywords"),
        ("Build clusters", "build_clusters"),
        ("Analyze content gaps", "analyze_gaps"),
        ("Rank opportunities", "rank_opportunities"),
        ("Plan internal links", "plan_internal_links"),
    )
    lines = ["WEEKLY SEO PREFLIGHT", ""]
    for label, key in labels:
        row = report["actions"][key]
        lines.append(f"- {label}: {row['status']} - {row['reason']}")
        if verbose:
            details = {k: v for k, v in row.items() if k not in {"status", "reason"}}
            if details:
                lines.append(f"  details: {json.dumps(details, ensure_ascii=False)}")
    lines.append(f"- Warnings: {report['warnings'] or 'none'}")
    lines.append(f"- Recommended next action: {report['recommended_next_action']}")
    return "\n".join(lines)
