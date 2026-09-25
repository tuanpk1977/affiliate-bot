from __future__ import annotations

import hashlib
import html
import json
import os
import re
import subprocess
import tempfile
import urllib.error
import urllib.request
import zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

from modules.external_writer_pipeline import UniversalExternalWriterImporter
from modules.external_writer_return_validator import validate_public_output_files
from modules.research_artifacts import resolve_research_artifacts
from modules.revision_binding import approval_binding_status, binding_for_file
from modules.verified_writer_package import validate_verified_package


STATUSES = {"PASS", "WARNING", "BLOCKED", "SKIPPED", "UNKNOWN"}
RESEARCH_FILES = (
    "SOURCE_EXCERPTS.json",
    "FACT_LEDGER.json",
    "ARTICLE_BLUEPRINT.json",
    "evidence_coverage.json",
)
EXPECTED_FILES = (
    "external_writer_console.py",
    "runbot_menu.bat",
    "config/editorial_system.json",
    "modules/external_writer_pipeline.py",
    "modules/verified_writer_package.py",
)
PAID_DEPENDENCY_MARKERS = (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GEMINI_API_KEY",
    "PERPLEXITY_API_KEY",
    "SERPAPI_API_KEY",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return default


def _items(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [row for row in value if isinstance(row, dict)]
    if isinstance(value, dict):
        for key in ("items", "tasks", "records", "articles"):
            rows = value.get(key)
            if isinstance(rows, list):
                return [row for row in rows if isinstance(row, dict)]
    return []


def _status_rank(status: str) -> int:
    return {"BLOCKED": 5, "UNKNOWN": 4, "WARNING": 3, "PASS": 2, "SKIPPED": 1}.get(
        status, 4
    )


def _aggregate(checks: Iterable[dict[str, Any]]) -> str:
    values = [str(row.get("status") or "UNKNOWN") for row in checks]
    if not values:
        return "UNKNOWN"
    effective = [value for value in values if value != "SKIPPED"]
    if not effective:
        return "SKIPPED"
    return max(effective, key=_status_rank)


class SystemHealthCheck:
    """Read-only repository health audit with report generation as its only write."""

    def __init__(
        self,
        *,
        root: Path,
        http_checker: Callable[[str], tuple[int | None, str]] | None = None,
    ) -> None:
        self.root = root.resolve()
        self.data_dir = self.root / "data"
        self.http_checker = http_checker or self._http_status
        self.checks: list[dict[str, Any]] = []

    def run(
        self,
        *,
        scope: str = "full",
        live: bool = False,
        deep: bool = False,
        report_path: Path | None = None,
    ) -> dict[str, Any]:
        if scope not in {"website", "social", "full"}:
            raise ValueError(f"Unsupported health-check scope: {scope}")
        self.checks = []
        self.menu_readiness: dict[str, Any] = {}
        self._repository_health()
        self._configuration_health()
        if scope in {"website", "full"}:
            self._research_health()
            self.menu_readiness = self._menu2_menu_x_health()
            self._verified_package_health()
            self._external_return_health(deep=deep)
            self._editorial_queue_health()
            _, current_slugs = self._current_batch_selection()
            self._approval_publish_health(current_slugs=set(current_slugs))
            current_articles, site_totals, batch_totals = self._deployment_health(live=live)
        else:
            current_articles, site_totals, batch_totals = self._deployment_health(
                live=live, current_only=True
            )
        social = self._social_health(current_articles=current_articles, live=live)
        self._validator_health(deep=deep)

        domains = self._domain_summary()
        readiness = self._readiness(domains)
        operational_readiness = self._operational_readiness(
            current_articles=current_articles,
            social=social,
        )
        overall = {
            "website_pipeline": self._combine_domains(
                domains,
                (
                    "research",
                    "verified_package",
                    "external_return",
                    "editorial_queue",
                    "approval_publish",
                    "deployment",
                ),
            ),
            "social_pipeline": domains.get("social", {}).get("status", "UNKNOWN"),
            "research_engine": domains.get("research", {}).get("status", "SKIPPED"),
            "external_writer": self._combine_domains(
                domains, ("verified_package", "external_return", "validators")
            ),
            "deployment": domains.get("deployment", {}).get("status", "UNKNOWN"),
        }
        payload = {
            "schema_version": "system_health_report_v1",
            "generated_at": _now(),
            "mode": "live" if live else "offline",
            "scope": scope,
            "deep": deep,
            "read_only": True,
            "overall": overall,
            "readiness": readiness,
            "operational_readiness": operational_readiness,
            # Stable, operator-facing answers.  Keep these at the top level so
            # Menu Y and automation callers do not have to infer an answer
            # from domain diagnostics or historical warnings.
            "CAN_I_CONTINUE_DAILY_OPERATION": bool(
                operational_readiness.get("ready_for_normal_daily_operation")
            ),
            "WHAT_EXACTLY_DO_I_DO_NEXT": self._exact_next_action(
                operational_readiness
            ),
            "CURRENT_FILES_LOADED": len(current_articles),
            "HISTORICAL_FILES_LOADED": 0,
            "HISTORICAL_ARTICLES_RESOLVED": 0,
            "menu_readiness": self.menu_readiness,
            "operator_recommendation": self._recommend(readiness),
            "site_wide_totals": site_totals,
            "current_batch": batch_totals,
            "current_articles": current_articles,
            "social_go_no_go": social,
            "domains": domains,
            "checks": self.checks,
            "issues": [
                row
                for row in self.checks
                if row["status"] in {"WARNING", "BLOCKED", "UNKNOWN"}
            ],
            "safety": {
                "paid_api_or_key_required": False,
                "approval_changed": False,
                "published": False,
                "committed": False,
                "pushed": False,
                "deployed": False,
                "indexing_submitted": False,
            },
        }
        payload["reports"] = self.write_reports(payload, report_path=report_path)
        return payload

    def _exact_next_action(self, operational: dict[str, Any]) -> str:
        """Return one deterministic, safe operator action for the current batch."""
        classes = operational.get("classifications") or {}
        blockers = list(classes.get("OPERATIONAL BLOCKER") or [])
        if blockers:
            blocker_ids = set(str(value) for value in blockers)
            for row in self.checks:
                if (
                    str(row.get("check_id") or "") in blocker_ids
                    and row.get("status") == "BLOCKED"
                ):
                    return str(
                        row.get("safe_command")
                        or row.get("next_action")
                        or f"Resolve {row.get('check_id')}."
                    )
            return f"Resolve {blockers[0]}."
        for category in ("ACTION REQUIRED", "WAITING FOR OPERATOR"):
            actions = list(classes.get(category) or [])
            if actions:
                return str(actions[0])
        return "Continue normal daily operation."

    def add(
        self,
        domain: str,
        check_id: str,
        status: str,
        reason: str,
        *,
        severity: str | None = None,
        path: Path | str | None = None,
        slug: str = "",
        task_id: str = "",
        actual: Any = None,
        expected: str = "",
        next_action: str = "",
        safe_command: str = "",
    ) -> None:
        if status not in STATUSES:
            raise ValueError(f"Invalid health status: {status}")
        self.checks.append(
            {
                "domain": domain,
                "check_id": check_id,
                "status": status,
                "severity": severity
                or {
                    "PASS": "info",
                    "WARNING": "attention",
                    "BLOCKED": "blocking",
                    "SKIPPED": "info",
                    "UNKNOWN": "attention",
                }[status],
                "file_or_path": str(path or ""),
                "task_id": task_id,
                "slug": slug,
                "actual_value": actual,
                "expected_condition": expected,
                "reason": reason,
                "next_action": next_action,
                "safe_command": safe_command,
            }
        )

    def _repository_health(self) -> None:
        domain = "repository"
        git_dir = self.root / ".git"
        self.add(
            domain,
            "REPOSITORY_EXISTS",
            "PASS" if git_dir.exists() else "BLOCKED",
            "Git repository is available." if git_dir.exists() else "The .git directory is missing.",
            path=git_dir,
            expected="A readable Git repository.",
            next_action="Restore or clone the repository." if not git_dir.exists() else "",
        )
        missing = [name for name in EXPECTED_FILES if not (self.root / name).is_file()]
        self.add(
            domain,
            "EXPECTED_PROJECT_FILES",
            "BLOCKED" if missing else "PASS",
            "Required project entry points are present." if not missing else "Required files are missing.",
            actual=missing,
            expected="All required project entry points exist.",
            next_action="Restore the listed files before running an editorial workflow." if missing else "",
        )
        branch = self._git("branch", "--show-current")
        self.add(
            domain,
            "CURRENT_BRANCH",
            "PASS" if branch else "UNKNOWN",
            f"Current branch is {branch}." if branch else "Current branch could not be determined.",
            actual=branch,
            expected="A named local branch.",
        )
        porcelain = self._git("status", "--porcelain", allow_failure=True)
        dirty = [line for line in porcelain.splitlines() if line]
        untracked = [line for line in dirty if line.startswith("??")]
        self.add(
            domain,
            "WORKTREE_STATE",
            "WARNING" if dirty else "PASS",
            (
                f"Worktree has {len(dirty)} changed entries, including {len(untracked)} untracked."
                if dirty
                else "Worktree is clean."
            ),
            actual={"changed": len(dirty), "untracked": len(untracked)},
            expected="A clean tree is preferred but is not required for a read-only health check.",
            next_action="Review changes before a later commit or publish operation." if dirty else "",
            safe_command="git status --short" if dirty else "",
        )
        conflict_markers = (
            self.root / ".git" / "MERGE_HEAD",
            self.root / ".git" / "rebase-merge",
            self.root / ".git" / "rebase-apply",
        )
        unmerged = self._git("diff", "--name-only", "--diff-filter=U", allow_failure=True)
        conflicted = bool(unmerged.strip()) or any(path.exists() for path in conflict_markers)
        self.add(
            domain,
            "MERGE_REBASE_CONFLICT",
            "BLOCKED" if conflicted else "PASS",
            "An unresolved merge or rebase state exists." if conflicted else "No merge or rebase conflict detected.",
            actual=unmerged.splitlines(),
            expected="No unresolved Git conflict.",
            next_action="Resolve the conflict before export, import, or publish." if conflicted else "",
            safe_command="git status" if conflicted else "",
        )
        sync = self._git(
            "rev-list", "--left-right", "--count", "HEAD...origin/main", allow_failure=True
        )
        parts = sync.split()
        if len(parts) == 2 and all(part.isdigit() for part in parts):
            actual = {"ahead": int(parts[0]), "behind": int(parts[1])}
            status = "WARNING" if actual["behind"] else "PASS"
            reason = f"Local branch is {actual['ahead']} ahead and {actual['behind']} behind origin/main."
        else:
            actual = {}
            status = "UNKNOWN"
            reason = "Ahead/behind state is unavailable from local Git refs."
        self.add(
            domain,
            "ORIGIN_SYNC",
            status,
            reason,
            actual=actual,
            expected="Local origin/main reference is available and the branch is not behind.",
            next_action="Run git fetch before a publish operation." if status != "PASS" else "",
            safe_command="git fetch origin" if status != "PASS" else "",
        )
        invalid_json: list[str] = []
        invalid_utf8: list[str] = []
        candidates = [
            self.root / "config" / "editorial_system.json",
            self.data_dir / "official_source_registry.json",
            self.data_dir / "publish_queue.json",
            self.data_dir / "human_approval_queue.json",
            self.data_dir / "write_queue" / "index.json",
        ]
        for path in candidates:
            if not path.is_file():
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeError:
                invalid_utf8.append(str(path))
                continue
            try:
                json.loads(text)
            except json.JSONDecodeError:
                invalid_json.append(str(path))
        self.add(
            domain,
            "CORE_JSON_UTF8",
            "BLOCKED" if invalid_json or invalid_utf8 else "PASS",
            "Core JSON and UTF-8 files are valid." if not invalid_json and not invalid_utf8 else "Core state files are unreadable.",
            actual={"invalid_json": invalid_json, "invalid_utf8": invalid_utf8},
            expected="Core state files contain valid UTF-8 JSON.",
            next_action="Repair only the listed state file from a known-good copy." if invalid_json or invalid_utf8 else "",
        )
        stale_locks = [
            str(path)
            for path in self.data_dir.rglob("*.lock")
            if path.is_file() and (datetime.now().timestamp() - path.stat().st_mtime) > 86400
        ]
        self.add(
            domain,
            "STALE_LOCK_FILES",
            "WARNING" if stale_locks else "PASS",
            f"Found {len(stale_locks)} lock file(s) older than 24 hours." if stale_locks else "No stale lock files found.",
            actual=stale_locks,
            expected="No stale runtime lock files.",
            next_action="Inspect lock owners before manually removing any lock." if stale_locks else "",
        )

    def _configuration_health(self) -> None:
        domain = "configuration"
        path = self.root / "config" / "editorial_system.json"
        config = _read_json(path, None)
        if not isinstance(config, dict):
            self.add(
                domain,
                "EDITORIAL_CONFIG",
                "BLOCKED",
                "Editorial configuration is missing or invalid JSON.",
                path=path,
                expected="A JSON object.",
                next_action="Repair config/editorial_system.json.",
            )
            return
        required = (
            "research_intelligence",
            "research_enrichment",
            "content_review",
            "human_approval",
            "publish_gate",
            "topic_scoring",
        )
        missing = [field for field in required if not isinstance(config.get(field), dict)]
        self.add(
            domain,
            "REQUIRED_CONFIG_SECTIONS",
            "BLOCKED" if missing else "PASS",
            "Required configuration sections are present." if not missing else "Configuration sections are missing.",
            path=path,
            actual=missing,
            expected=", ".join(required),
            next_action=f"Add valid objects for: {', '.join(missing)}." if missing else "",
        )
        raw = json.dumps(config, ensure_ascii=False)
        paid = [marker for marker in PAID_DEPENDENCY_MARKERS if marker in raw]
        llm = config.get("llm_provider") if isinstance(config.get("llm_provider"), dict) else {}
        requires_key = bool(llm.get("required_api_key") or llm.get("api_key_required"))
        self.add(
            domain,
            "NO_PAID_API_REQUIREMENT",
            "BLOCKED" if paid or requires_key else "PASS",
            "Health check requires no paid API or API key." if not paid and not requires_key else "A paid API key appears mandatory.",
            actual={"markers": paid, "required_api_key": requires_key},
            expected="No paid API dependency is required.",
            next_action="Make the dependency optional or local-only." if paid or requires_key else "",
        )
        contract = _read_json(self.root / "config" / "external_writer.json", {})
        self.add(
            domain,
            "EXTERNAL_WRITER_CONFIG",
            "PASS" if isinstance(contract, dict) else "BLOCKED",
            "External writer configuration is readable.",
            path=self.root / "config" / "external_writer.json",
            expected="Readable local configuration; API keys are not required.",
        )

    def _research_health(self) -> None:
        domain = "research"
        registry_path = self.data_dir / "official_source_registry.json"
        registry = _read_json(registry_path, None)
        entities = registry.get("entities", {}) if isinstance(registry, dict) else {}
        sources = []
        if isinstance(entities, dict):
            for entity in entities.values():
                if isinstance(entity, dict):
                    sources.extend(_items(entity.get("sources", [])))
        self.add(
            domain,
            "OFFICIAL_SOURCE_REGISTRY",
            "PASS" if isinstance(registry, dict) else "BLOCKED",
            f"Official Source Registry is readable with {len(sources)} source records."
            if isinstance(registry, dict)
            else "Official Source Registry is missing or invalid.",
            path=registry_path,
            actual={"entities": len(entities) if isinstance(entities, dict) else 0, "sources": len(sources)},
            expected="Readable registry JSON.",
            next_action="Run the local verified-source import workflow." if not isinstance(registry, dict) else "",
        )
        kb_root = self.data_dir / "entity_knowledge_base"
        profiles = list(kb_root.glob("*/profile.json")) if kb_root.is_dir() else []
        claims: list[dict[str, Any]] = []
        conflicts: list[dict[str, Any]] = []
        conflicts_by_entity: dict[str, list[dict[str, Any]]] = {}
        for profile in profiles:
            claims.extend(_items(_read_json(profile.parent / "claims.json", {})))
            entity_conflicts = _items(_read_json(profile.parent / "conflicts.json", {}))
            conflicts.extend(entity_conflicts)
            conflicts_by_entity[profile.parent.name] = entity_conflicts
        stale_claims = [
            row for row in claims if str(row.get("freshness_status") or row.get("status") or "").lower() in {"stale", "expired"}
        ]
        active_claims = [row for row in claims if row not in stale_claims]
        self.add(
            domain,
            "ENTITY_KNOWLEDGE_BASE",
            "PASS" if profiles else "WARNING",
            f"Entity Knowledge Base contains {len(profiles)} entities and {len(claims)} claims."
            if profiles
            else "Entity Knowledge Base has no entity profiles.",
            path=kb_root,
            actual={
                "entities": len(profiles),
                "active_claims": len(active_claims),
                "stale_claims": len(stale_claims),
                "conflicted_claims": len(conflicts),
            },
            expected="Readable entity profiles and claim records.",
            next_action="Run research enrichment for approved entities." if not profiles else "",
        )
        if conflicts:
            current_batch_date, current_slugs = self._current_batch_selection()
            current_entity_ids: set[str] = set()
            all_research_entity_ids: set[str] = set()
            research_root = self.data_dir / "research"
            for entity_profile in research_root.glob("*/entity_profile.json") if research_root.is_dir() else []:
                entity_payload = _read_json(entity_profile, {})
                entity_id = str(entity_payload.get("entity_id") or "") if isinstance(entity_payload, dict) else ""
                if entity_id:
                    all_research_entity_ids.add(entity_id)
                    if entity_profile.parent.name in current_slugs:
                        current_entity_ids.add(entity_id)
            current_conflicts = sum(
                len(rows) for entity_id, rows in conflicts_by_entity.items()
                if entity_id in current_entity_ids
            )
            historical_conflicts = sum(
                len(rows) for entity_id, rows in conflicts_by_entity.items()
                if entity_id not in current_entity_ids and entity_id in all_research_entity_ids
            )
            orphan_conflicts = len(conflicts) - current_conflicts - historical_conflicts
            self.add(
                domain,
                "CLAIM_CONFLICTS",
                "BLOCKED" if current_conflicts else "WARNING",
                (
                    f"{current_conflicts} current, {historical_conflicts} historical, "
                    f"and {orphan_conflicts} orphan conflict record(s)."
                ),
                actual={
                    "total": len(conflicts),
                    "current_batch_date": current_batch_date,
                    "current_entity_ids": sorted(current_entity_ids),
                    "current": current_conflicts,
                    "historical": historical_conflicts,
                    "orphan": orphan_conflicts,
                    "classification": "OPERATIONAL BLOCKER" if current_conflicts else "HISTORICAL/BACKLOG",
                },
                expected="Conflicts are explicitly recorded and reviewed.",
                next_action=(
                    "Review conflicts_and_caveats.json before writing the affected current article."
                    if current_conflicts
                    else "Review historical/orphan conflicts during backlog maintenance; they do not block the current batch."
                ),
            )
        cache_root = self.data_dir / "research_cache" / "source_content"
        cache_json = list(cache_root.rglob("*.json")) if cache_root.is_dir() else []
        stale_cache: list[str] = []
        invalid_cache: list[str] = []
        now = datetime.now().timestamp()
        for path in cache_json:
            payload = _read_json(path, None)
            if not isinstance(payload, dict):
                invalid_cache.append(str(path))
            if now - path.stat().st_mtime > 90 * 86400:
                stale_cache.append(str(path))
        cache_status = "BLOCKED" if invalid_cache else ("WARNING" if stale_cache else "PASS")
        self.add(
            domain,
            "SOURCE_CACHE",
            cache_status,
            f"Source cache has {len(cache_json)} JSON entries; {len(stale_cache)} stale and {len(invalid_cache)} invalid.",
            path=cache_root,
            actual={"cached_pages": len(cache_json), "stale": len(stale_cache), "invalid": len(invalid_cache)},
            expected="Readable cache metadata; stale entries are visible.",
            next_action="Refresh only stale or invalid source cache entries." if stale_cache or invalid_cache else "",
        )
        ready = blocked = 0
        research_levels: dict[str, int] = {}
        outstanding_research_tasks = 0
        research_errors: list[dict[str, Any]] = []
        for folder in (self.data_dir / "research").iterdir() if (self.data_dir / "research").is_dir() else []:
            if not folder.is_dir():
                continue
            quality = _read_json(folder / "research_quality.json", {})
            report = _read_json(folder / "enrichment_report.json", {})
            status = str(report.get("status") or quality.get("status") or "").upper()
            level = str(
                report.get("research_level")
                or ("RESEARCH_COMPLETE" if status == "ARTICLE_READY" else status)
                or "UNKNOWN"
            ).upper()
            research_levels[level] = research_levels.get(level, 0) + 1
            outstanding_research_tasks += len(
                [
                    row
                    for row in report.get("research_tasks", [])
                    if isinstance(row, dict)
                ]
            )
            if status in {"ARTICLE_READY", "PASSED", "PASS"} or bool(report.get("article_ready")):
                ready += 1
            if status in {"BLOCKED_RESEARCH", "NEEDS_ENRICHMENT", "BLOCKED"}:
                blocked += 1
            present = [name for name in RESEARCH_FILES if (folder / name).is_file()]
            if present and len(present) != len(RESEARCH_FILES):
                research_errors.append({"slug": folder.name, "missing": sorted(set(RESEARCH_FILES) - set(present))})
                continue
            if len(present) == len(RESEARCH_FILES):
                ledger = _read_json(folder / "FACT_LEDGER.json", None)
                excerpts = _read_json(folder / "SOURCE_EXCERPTS.json", None)
                blueprint = _read_json(folder / "ARTICLE_BLUEPRINT.json", None)
                if not all(isinstance(value, dict) for value in (ledger, excerpts, blueprint)):
                    research_errors.append({"slug": folder.name, "reason": "invalid evidence JSON"})
                    continue
                marker = "validated by weekly topic source-readiness preflight"
                if marker in json.dumps((ledger, excerpts)).lower():
                    research_errors.append({"slug": folder.name, "reason": "placeholder evidence remains"})
        self.add(
            domain,
            "RESEARCH_ARTIFACTS",
            "BLOCKED" if research_errors else "PASS",
            "Research artifact sets are structurally valid." if not research_errors else f"{len(research_errors)} research artifact set(s) are incomplete or invalid.",
            actual={
                "article_ready": ready,
                "blocked_research": blocked,
                "research_levels": research_levels,
                "outstanding_research_tasks": outstanding_research_tasks,
                "errors": research_errors[:20],
            },
            expected="Complete, valid evidence files with no placeholder facts.",
            next_action="Run `python external_writer_console.py enrich-research --date latest` for affected tasks." if research_errors else "",
            safe_command="python external_writer_console.py enrich-research --date latest" if research_errors else "",
        )

    def _menu2_menu_x_health(self) -> dict[str, Any]:
        queue_root = self.data_dir / "editorial_queue"
        advanced_batches: list[tuple[str, dict[str, Any]]] = []
        for queue_file in queue_root.glob("*/topics.json") if queue_root.is_dir() else []:
            payload = _read_json(queue_file, {})
            if isinstance(payload, dict) and str(payload.get("mode") or "").lower() == "advanced":
                advanced_batches.append((queue_file.parent.name, payload))
        if not advanced_batches:
            result = {
                "batch_date": "",
                "menu_2_status": "WARNING",
                "menu_x_status": "WARNING",
                "article_ready": 0,
                "blocked_research": 0,
                "legacy_or_missing": 0,
                "tasks": [],
            }
            self.add(
                "research",
                "MENU_2_MENU_X_READINESS",
                "SKIPPED",
                "No Tue-Sun advanced batch is available.",
                actual=result,
                expected="A current advanced batch with terminal enrichment states.",
                next_action="Run Menu 2 for the current locked week.",
            )
            return result

        batch_date, payload = sorted(advanced_batches, key=lambda row: row[0])[-1]
        task_rows: list[dict[str, Any]] = []
        ready = blocked = legacy = terminal = complete = 0
        comparator_candidates = verified_comparators = unresolved_comparators = 0
        ambiguous_comparators = stale_relationships = 0
        balanced_scores: list[float] = []
        for item in _items(payload.get("topics")):
            slug = str(item.get("slug") or "")
            task_id = str(item.get("task_id") or f"website-advanced-{batch_date}-{slug}")
            resolution = resolve_research_artifacts(
                self.root,
                task_id=task_id,
                slug=slug,
                batch_date=batch_date,
            )
            if resolution.draft_exportable:
                ready += 1
                terminal += 1
                if resolution.article_ready:
                    complete += 1
            elif resolution.enrichment_report_file.is_file():
                blocked += 1
                terminal += 1
            else:
                legacy += 1
            angle_plan = _read_json(resolution.angle_research_plan_file, {})
            comparator_report = (
                angle_plan.get("comparator_discovery")
                if isinstance(angle_plan, dict)
                else {}
            ) or {}
            candidate_rows = _items(comparator_report.get("candidates"))
            comparator_candidates += len(candidate_rows)
            verified_comparators += sum(
                1 for row in candidate_rows
                if str(row.get("verification_status") or "") == "VERIFIED"
            )
            ambiguous_comparators += sum(
                1 for row in candidate_rows
                if str(row.get("verification_status") or "") == "AMBIGUOUS"
            )
            stale_relationships += sum(
                1 for row in candidate_rows
                if str(row.get("verification_status") or "") == "STALE"
            )
            required_comparators = int(
                comparator_report.get("required_comparator_count") or 0
            )
            selected_comparators = len(
                _items(comparator_report.get("selected_comparators"))
            )
            unresolved_comparators += max(
                0, required_comparators - selected_comparators
            )
            balanced_entity_coverage = None
            if str(angle_plan.get("angle_profile") or "") == "comparison_and_alternatives":
                evidence_coverage = _read_json(
                    resolution.evidence_coverage_file,
                    {},
                )
                entity_summary = (
                    evidence_coverage.get("entity_coverage_summary", {})
                    if isinstance(evidence_coverage, dict)
                    else {}
                )
                balanced_entity_coverage = float(
                    entity_summary.get("balanced_section_coverage_score") or 0.0
                )
                balanced_scores.append(balanced_entity_coverage)
            task_rows.append(
                {
                    "task_id": task_id,
                    "slug": slug,
                    "status": resolution.status,
                    "research_level": resolution.research_level,
                    "draft_exportable": resolution.draft_exportable,
                    "outstanding_research_tasks": resolution.outstanding_research_tasks,
                    "draft_status": str(item.get("status") or "not_started"),
                    "revision_count": resolution.revision_count,
                    "comparison_status": resolution.comparison_status,
                    "known_weak_sections": list(resolution.weak_sections),
                    "estimated_publish_readiness": (
                        resolution.estimated_publish_readiness
                    ),
                    "paragraphs": resolution.paragraph_count,
                    "claims": resolution.claim_count,
                    "coverage_score": resolution.coverage_score,
                    "angle_profile": resolution.angle_profile,
                    "required_entities": resolution.required_entity_count,
                    "resolved_entities": resolution.resolved_entity_count,
                    "entity_coverage_score": resolution.entity_coverage_score,
                    "balanced_entity_coverage": balanced_entity_coverage,
                    "candidate_claims": resolution.candidate_claim_count,
                    "accepted_claims": resolution.claim_count,
                    "rejected_claims": resolution.rejected_claim_count,
                    "comparator_candidates": len(candidate_rows),
                    "verified_comparators": sum(
                        1 for row in candidate_rows
                        if str(row.get("verification_status") or "") == "VERIFIED"
                    ),
                    "selected_comparators": selected_comparators,
                    "comparator_approval_mode": comparator_report.get("approval_mode"),
                    "legacy_reasons": list(resolution.legacy_reasons),
                    "missing_files": list(resolution.missing_files),
                }
            )
        total = len(task_rows)
        menu_2_status = "PASS" if total and terminal == total else "BLOCKED"
        menu_x_status = "PASS" if ready else "BLOCKED"
        result = {
            "batch_date": batch_date,
            "menu_2_status": menu_2_status,
            "menu_x_status": menu_x_status,
            "article_ready": ready,
            "research_complete": complete,
            "blocked_research": blocked,
            "legacy_or_missing": legacy,
            "tasks": task_rows,
        }
        self.add(
            "research",
            "MENU_2_MENU_X_READINESS",
            "PASS" if menu_2_status == "PASS" and menu_x_status == "PASS" else "BLOCKED",
            (
                f"Advanced batch {batch_date}: {ready} draft-exportable, "
                f"{complete} RESEARCH_COMPLETE, "
                f"{blocked} BLOCKED_RESEARCH, {legacy} legacy/missing."
            ),
            actual=result,
            expected="Menu 2 reaches terminal research states and Menu X has at least one eligible task.",
            next_action=(
                "Run Menu X for WEBSITE_ADVANCED."
                if menu_x_status == "PASS"
                else "Run Menu 2 enrichment and resolve the grouped research blockers."
            ),
            safe_command=(
                f"python external_writer_console.py export --date {batch_date} --task-type WEBSITE_ADVANCED"
                if menu_x_status == "PASS"
                else f"python editorial_console.py daily-followup --date {batch_date} --count 2 --confirm"
            ),
        )
        comparator_status = (
            "PASS"
            if balanced_scores and unresolved_comparators == 0
            and all(score >= 0.60 for score in balanced_scores)
            else "WARNING"
            if ready
            else "BLOCKED"
        )
        current_batch_date, _ = self._current_batch_selection()
        comparator_scope = "CURRENT" if batch_date == current_batch_date else "HISTORICAL/BACKLOG"
        self.add(
            "research",
            "COMPARATOR_READINESS",
            comparator_status,
            (
                f"{comparator_candidates} candidate(s), "
                f"{verified_comparators} verified, "
                f"{unresolved_comparators} unresolved."
            ),
            actual={
                "candidate_comparators": comparator_candidates,
                "verified_comparators": verified_comparators,
                "unresolved_comparators": unresolved_comparators,
                "ambiguous_candidates": ambiguous_comparators,
                "stale_relationships": stale_relationships,
                "balanced_entity_coverage": balanced_scores,
                "audited_batch_date": batch_date,
                "current_batch_date": current_batch_date,
                "classification": comparator_scope,
            },
            expected=(
                "Two verified comparators and balanced entity coverage >= 0.60 "
                "for every comparison task."
            ),
            next_action=(
                f"Review comparator candidates for batch {batch_date} and confirm "
                "exactly two only after deterministic verification."
                if comparator_status != "PASS"
                else ""
            ),
            safe_command=(
                f"python editorial_console.py comparator-candidates --date "
                f"{batch_date} --slug <comparison-slug>"
                if comparator_status != "PASS"
                else ""
            ),
        )
        return result

    def _verified_package_health(self) -> None:
        domain = "verified_package"
        packages = sorted(
            (self.root / "exports" / "external_writer").glob("*/*_verified_package.zip"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        if not packages:
            self.add(
                domain,
                "LATEST_VERIFIED_PACKAGE",
                "BLOCKED",
                "No verified external-writer package exists.",
                expected="At least one validated verified package.",
                next_action="Run Menu X after research reaches ARTICLE_READY.",
            )
            return
        latest = packages[0]
        result = validate_verified_package(latest)
        details = self._verified_package_details(latest)
        self.add(
            domain,
            "LATEST_VERIFIED_PACKAGE",
            "PASS" if result.valid else "BLOCKED",
            "Latest verified package passes its bundled contract." if result.valid else "Latest verified package is invalid.",
            path=latest,
            actual={
                **details,
                "sha256": self._sha256(latest),
                "article_count": result.article_count,
                "errors": result.errors,
                "warnings": result.warnings,
            },
            expected="Manifest integrity, complete evidence, and valid output contracts.",
            next_action="Rebuild Menu X package after resolving listed validation errors." if not result.valid else "",
            safe_command=f'python external_writer_console.py validate-package "{latest}"',
        )

    def _external_return_health(self, *, deep: bool) -> None:
        domain = "external_return"
        returned = sorted(
            (self.root / "exports" / "external_writer" / "returned").glob("*.zip"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        if not returned:
            self.add(
                domain,
                "LATEST_COMPLETED_RETURN",
                "SKIPPED",
                "No returned completed_drafts ZIP exists.",
                expected="A completed ZIP is optional until Menu W.",
            )
            return
        latest = returned[0]
        importer = UniversalExternalWriterImporter(root=self.root)
        try:
            standalone = importer.validate_zip(latest)
            dry_run = importer.import_zip(latest, dry_run=True)
            accepted_statuses = {"VALIDATION_PASS", "DRY_RUN_PASS", "UNCHANGED"}
            standalone_ok = standalone.get("status") in accepted_statuses
            dry_ok = dry_run.get("status") in accepted_statuses
            compatible = standalone_ok == dry_ok and standalone.get("rejected", []) == dry_run.get(
                "rejected", []
            )
            status = "PASS" if standalone_ok and compatible else "BLOCKED"
            actual = {
                "zip": str(latest),
                "sha256": self._sha256(latest),
                "standalone_status": standalone.get("status"),
                "menu_w_dry_run_status": dry_run.get("status"),
                "validated": len(standalone.get("validated", standalone.get("imported", []))),
                "rejected": standalone.get("rejected", []),
                "skipped": standalone.get("skipped", []),
                "consistent": compatible,
            }
        except (OSError, ValueError, zipfile.BadZipFile) as exc:
            status = "BLOCKED"
            actual = {"zip": str(latest), "error": str(exc)}
        self.add(
            domain,
            "LATEST_COMPLETED_RETURN",
            status,
            "Standalone validation and Menu W dry-run agree." if status == "PASS" else "Completed return is not safe for Menu W.",
            path=latest,
            actual=actual,
            expected="Checksums, canonical URLs, public HTML, and Menu W shared validation all pass.",
            next_action="Run validate-completed and repair only the exact rejected file." if status != "PASS" else "",
            safe_command=f'python external_writer_console.py validate-completed "{latest}"',
        )

    def _editorial_queue_health(self) -> None:
        domain = "editorial_queue"
        queue_dir = self.data_dir / "write_queue"
        rows = _items(_read_json(queue_dir / "index.json", {}))
        ids = [str(row.get("task_id") or "") for row in rows]
        slugs = [str(row.get("article_slug") or "") for row in rows]
        duplicate_ids = [key for key, count in Counter(ids).items() if key and count > 1]
        duplicate_slugs = [key for key, count in Counter(slugs).items() if key and count > 1]
        orphaned = [
            str(row.get("task_id") or "")
            for row in rows
            if row.get("task_id") and not (queue_dir / f"{row['task_id']}.json").is_file()
        ]
        missing_research = []
        for row in rows:
            if str(row.get("task_type") or "").startswith("WEBSITE_"):
                slug = str(row.get("article_slug") or "")
                if slug and not (self.data_dir / "research" / slug).is_dir():
                    missing_research.append(slug)
        blocked = bool(duplicate_ids or orphaned)
        status = "BLOCKED" if blocked else ("WARNING" if duplicate_slugs or missing_research else "PASS")
        self.add(
            domain,
            "WRITE_QUEUE_INTEGRITY",
            status,
            f"Write queue contains {len(rows)} indexed tasks.",
            path=queue_dir / "index.json",
            actual={
                "tasks": len(rows),
                "duplicate_task_ids": duplicate_ids,
                "duplicate_slugs": duplicate_slugs,
                "orphaned_tasks": orphaned,
                "tasks_without_research": missing_research,
            },
            expected="Unique task IDs, resolvable task files, and website research artifacts.",
            next_action="Repair only the affected queue index/task references; do not change weekly locks." if status != "PASS" else "",
        )
        weekly = self.data_dir / "editorial_queue" / "current_week.json"
        self.add(
            domain,
            "WEEKLY_ROOT_MANIFEST",
            "PASS" if weekly.is_file() and isinstance(_read_json(weekly, None), dict) else "WARNING",
            "Weekly root manifest is readable." if weekly.is_file() else "Weekly root manifest is not available.",
            path=weekly,
            expected="A readable current-week manifest when a weekly workflow is active.",
            next_action="Run Menu 1 only if starting a new weekly cycle." if not weekly.is_file() else "",
        )

    def _current_batch_selection(self) -> tuple[str, list[str]]:
        """Resolve current articles from the canonical dated daily queue.

        The write queue is a handoff authority, not daily selection authority;
        it is retained only as a compatibility fallback for older fixtures and
        repositories that do not yet have dated topic manifests.
        """
        queue_root = self.data_dir / "editorial_queue"
        dated: list[tuple[str, Path]] = []
        if queue_root.is_dir():
            for candidate in queue_root.iterdir():
                if candidate.is_dir() and re.fullmatch(r"\d{4}-\d{2}-\d{2}", candidate.name):
                    topics_path = candidate / "topics.json"
                    if topics_path.is_file():
                        dated.append((candidate.name, topics_path))
        for batch_date, path in sorted(dated, reverse=True):
            payload = _read_json(path, {})
            topic_rows = (
                payload.get("topics", [])
                if isinstance(payload, dict)
                else _items(payload)
            )
            slugs = [
                str(row.get("slug") or "")
                for row in topic_rows
                if isinstance(row, dict)
                if str(row.get("slug") or "")
            ]
            if slugs:
                return batch_date, list(dict.fromkeys(slugs))
        write_rows = _items(_read_json(self.data_dir / "write_queue" / "index.json", {}))
        batch_date = max((str(row.get("batch_date") or "") for row in write_rows), default="")
        slugs = [
            str(row.get("article_slug") or "")
            for row in write_rows
            if str(row.get("batch_date") or "") == batch_date
            and str(row.get("article_slug") or "")
        ]
        return batch_date, list(dict.fromkeys(slugs))

    def _approval_publish_health(self, *, current_slugs: set[str]) -> None:
        domain = "approval_publish"
        approval = _items(_read_json(self.data_dir / "human_approval_queue.json", []))
        publish = _items(_read_json(self.data_dir / "publish_queue.json", []))
        approval_by_slug = {str(row.get("slug") or ""): row for row in approval}
        invalid_bypass = []
        historically_deployed_now_invalid = []
        historical_non_current_invalid = []
        counts = Counter()
        for row in publish:
            status = str(row.get("status") or "").lower()
            if status in {"live", "published", "published_local"}:
                counts["Published"] += 1
            elif status in {"ready_for_publish", "approved_for_publish"}:
                counts["Ready for Publish"] += 1
            elif status in {"rejected"}:
                counts["Rejected"] += 1
            elif status in {"blocked", "publish_blocked"}:
                counts["Publish Blocked"] += 1
            else:
                counts["Needs Review"] += 1
            if status in {"live", "published", "published_local", "ready_for_publish", "approved_for_publish"}:
                slug = str(row.get("slug") or "")
                approved = approval_by_slug.get(slug, {})
                required = bool(
                    approved.get("required")
                    if approved
                    else row.get("human_approval_required", False)
                )
                draft = self.data_dir / "production_article_drafts" / slug / "index.html"
                if draft.is_file():
                    binding = binding_for_file(draft)
                    binding_status = approval_binding_status(
                        approved,
                        current_content_hash=binding["content_hash"],
                        current_revision_id=binding["revision_id"],
                    )
                    passed = binding_status == "MATCHED"
                else:
                    binding_status = "CURRENT_CONTENT_UNAVAILABLE"
                    passed = False
                if required and not passed:
                    finding = {"slug": slug, "approval_binding_status": binding_status}
                    if status in {"live", "published", "published_local"}:
                        historically_deployed_now_invalid.append(finding)
                    elif slug not in current_slugs:
                        historical_non_current_invalid.append(finding)
                    else:
                        invalid_bypass.append(finding)
        counts["Human Approved"] = sum(
            str(row.get("status") or "").lower() == "human_approved" for row in approval
        )
        self.add(
            domain,
            "APPROVAL_PUBLISH_CANONICAL_STATE",
            "BLOCKED" if invalid_bypass else "PASS",
            "No current authorization violation was found."
            if not invalid_bypass
            else "Current publish authorization is invalid for at least one ready item.",
            actual={
                "counts": dict(counts),
                "current_authorization_violations": invalid_bypass,
                "historically_deployed_now_invalid": historically_deployed_now_invalid,
                "historical_non_current_invalid": historical_non_current_invalid,
            },
            expected="Required human approval precedes publish readiness.",
            next_action="Require re-review and a fresh revision-bound human approval before any new publish operation." if invalid_bypass else "",
        )
        self.add(
            domain,
            "HISTORICAL_DEPLOYMENT_APPROVAL_EVIDENCE",
            "WARNING" if historically_deployed_now_invalid or historical_non_current_invalid else "PASS",
            "Historical deployment records with unbound approval remain visible as audit evidence."
            if historically_deployed_now_invalid
            else "No historical deployment record with invalidated approval was found.",
            actual=historically_deployed_now_invalid + historical_non_current_invalid,
            expected="Historical deployment evidence is visible but is not current publish authorization.",
            next_action="Re-review affected historical content before any new publish operation for those slugs." if historically_deployed_now_invalid else "",
        )
        queue_rows = _items(_read_json(self.data_dir / "write_queue" / "index.json", {}))
        imported_unapproved = [
            row
            for row in queue_rows
            if str(row.get("status") or "") == "NEEDS_REVIEW"
            and str(approval_by_slug.get(str(row.get("article_slug") or ""), {}).get("status") or "")
            != "human_approved"
        ]
        self.add(
            domain,
            "IMPORTED_DRAFT_SAFETY",
            "PASS",
            f"{len(imported_unapproved)} imported draft(s) remain unapproved as required.",
            actual=len(imported_unapproved),
            expected="Import never grants approval or publication.",
        )

    def _deployment_health(
        self, *, live: bool, current_only: bool = False
    ) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
        domain = "deployment"
        report = _read_json(self.data_dir / "live_status_report.json", {})
        report_rows = _items(report)
        report_by_slug = {str(row.get("slug") or ""): row for row in report_rows}
        publish = _items(_read_json(self.data_dir / "publish_queue.json", []))
        publish_by_slug = {str(row.get("slug") or ""): row for row in publish}
        approval = _items(_read_json(self.data_dir / "human_approval_queue.json", []))
        approval_by_slug = {str(row.get("slug") or ""): row for row in approval}
        batch_date, current_slugs = self._current_batch_selection()
        current: list[dict[str, Any]] = []
        for slug in current_slugs:
            live_row = report_by_slug.get(slug, {})
            publish_row = publish_by_slug.get(slug, {})
            approval_row = approval_by_slug.get(slug, {})
            url = str(
                publish_row.get("url")
                or live_row.get("url")
                or f"https://smileaireviewhub.com/{slug}/"
            )
            site_file = self.root / "site_output" / slug / "index.html"
            docs_file = self.root / "docs" / slug / "index.html"
            static_file = self.data_dir / "published_static_pages" / slug / "index.html"
            canonical = self._canonical(site_file)
            if live:
                http_status, live_reason = self.http_checker(url)
                live_status = "PASS" if http_status and 200 <= http_status < 400 else "BLOCKED"
            else:
                http_status = live_row.get("live_http_status")
                live_reason = "Live HTTP intentionally skipped; cached live report value shown separately."
                live_status = "SKIPPED"
            git_status = str(live_row.get("git_status") or "")
            article = {
                "slug": slug,
                "editorial_status": live_row.get("editorial_status") or "UNKNOWN",
                "publish_gate_status": live_row.get("publish_gate_status")
                or publish_row.get("final_gate")
                or "UNKNOWN",
                "human_approval_status": approval_row.get("status") or "UNKNOWN",
                "publish_queue_status": publish_row.get("status") or "UNKNOWN",
                "local_output": site_file.is_file(),
                "docs_output": docs_file.is_file(),
                "published_static_output": static_file.is_file(),
                "git_state": git_status or "UNKNOWN",
                "canonical_url": canonical,
                "expected_url": url,
                "cached_live_http_status": live_row.get("live_http_status"),
                "live_http_status": http_status if live else None,
                "live_check_status": live_status,
                "live_reason": live_reason,
            }
            current.append(article)
            local_ok = site_file.is_file() and docs_file.is_file() and static_file.is_file()
            self.add(
                domain,
                "CURRENT_ARTICLE_OUTPUT",
                "PASS" if local_ok else "BLOCKED",
                "All local deployment outputs exist." if local_ok else "One or more local deployment outputs are missing.",
                slug=slug,
                actual={
                    "site_output": site_file.is_file(),
                    "docs": docs_file.is_file(),
                    "published_static": static_file.is_file(),
                },
                expected="site_output, docs, and published-static index.html exist.",
                next_action="Rebuild and sync approved output before publish." if not local_ok else "",
            )
            canonical_ok = canonical.rstrip("/") == url.rstrip("/") if canonical else False
            self.add(
                domain,
                "CURRENT_ARTICLE_CANONICAL",
                "PASS" if canonical_ok else "BLOCKED",
                "Canonical URL matches the publish URL." if canonical_ok else "Canonical URL is missing or mismatched.",
                slug=slug,
                path=site_file,
                actual=canonical,
                expected=url,
                next_action="Correct the canonical URL and rerun public validation." if not canonical_ok else "",
            )
            self.add(
                domain,
                "CURRENT_ARTICLE_LIVE_HTTP",
                live_status,
                (
                    f"Live URL returned HTTP {http_status}."
                    if live
                    else "Live HTTP check skipped in offline mode."
                ),
                slug=slug,
                actual=http_status if live else {"cached": live_row.get("live_http_status")},
                expected="HTTP 200-399 in --live mode.",
                next_action="Verify Pages deployment and canonical path." if live_status == "BLOCKED" else "",
                safe_command=f'python external_writer_console.py health-check --scope website --live',
            )
        summary_keys = (
            "total_items",
            "live_200",
            "published_local",
            "publish_blocked",
            "awaiting_publish",
            "awaiting_push",
            "committed_local",
            "pushed",
            "deploy_pending",
            "push_blocked",
            "rebase_conflict",
            "missing_local_output",
            "missing_docs",
            "unexpected_live_404",
            "unknown",
        )
        summary = report.get("summary")
        summary_source = summary if isinstance(summary, dict) else report
        site_totals = {key: summary_source.get(key, 0) for key in summary_keys}
        batch_slugs = set(current_slugs)
        batch_totals = {
            "date": batch_date,
            "task_count": len(batch_slugs),
            "article_count": len(batch_slugs),
            "live_200": sum(
                int((report_by_slug.get(slug, {}).get("live_http_status") or 0) == 200)
                for slug in batch_slugs
            ),
            "published": sum(
                str(publish_by_slug.get(slug, {}).get("status") or "").lower()
                in {"live", "published", "published_local"}
                for slug in batch_slugs
            ),
            "blocked": sum(
                str(publish_by_slug.get(slug, {}).get("status") or "").lower()
                in {"blocked", "publish_blocked"}
                for slug in batch_slugs
            ),
            "note": "Current-batch totals use the latest canonical daily topic manifest, with write_queue fallback for legacy data; site-wide totals come from live_status_report.json.",
        }
        if current_only:
            return current, site_totals, batch_totals
        sitemap = self.root / "docs" / "sitemap.xml"
        sitemap_text = sitemap.read_text(encoding="utf-8") if sitemap.is_file() else ""
        missing_sitemap = [slug for slug in current_slugs if f"/{slug}/" not in sitemap_text]
        self.add(
            domain,
            "SITEMAP_CURRENT_ARTICLES",
            "WARNING" if missing_sitemap else "PASS",
            "Current production articles are present in sitemap." if not missing_sitemap else "Current production articles are missing from sitemap.",
            path=sitemap,
            actual=missing_sitemap,
            expected="Each current article URL is listed in docs/sitemap.xml.",
            next_action="Rebuild sitemap before the next publish." if missing_sitemap else "",
        )
        return current, site_totals, batch_totals

    def _social_health(
        self, *, current_articles: list[dict[str, Any]], live: bool
    ) -> dict[str, Any]:
        domain = "social"
        social_records = []
        for path in (self.data_dir / "social_drafts").rglob("*.json") if (self.data_dir / "social_drafts").is_dir() else []:
            social_records.extend(_items(_read_json(path, {})))
        statuses = Counter(str(row.get("status") or "").lower() for row in social_records)
        eligible: list[str] = []
        blocked: dict[str, list[str]] = {}
        for article in current_articles:
            reasons = []
            published = str(article.get("publish_queue_status") or "").lower() in {
                "live",
                "published",
                "published_local",
            }
            if not published:
                reasons.append("website article is not published")
            canonical_ok = str(article.get("canonical_url") or "").rstrip("/") == str(
                article.get("expected_url") or ""
            ).rstrip("/")
            if not canonical_ok:
                reasons.append("canonical URL mismatch")
            status_value = (
                article.get("live_http_status")
                if live
                else article.get("cached_live_http_status")
            )
            if int(status_value or 0) != 200:
                reasons.append("website article is not verified Live HTTP 200")
            if str(article.get("publish_gate_status") or "").lower() in {
                "blocked",
                "publish blocked",
            }:
                reasons.append("unresolved editorial publish blocker")
            duplicate = [
                row
                for row in social_records
                if str(row.get("slug") or row.get("article_slug") or "") == article["slug"]
                and str(row.get("status") or "").lower()
                not in {"rejected", "not_recommended", "published_manual", "published"}
            ]
            if duplicate:
                reasons.append("active social package already exists")
            if reasons:
                blocked[article["slug"]] = reasons
            else:
                eligible.append(article["slug"])
        website_ready = bool(eligible)
        self.add(
            domain,
            "WEBSITE_DERIVED_SOCIAL_GO_NO_GO",
            "PASS" if website_ready else "BLOCKED",
            f"{len(eligible)} exact live article(s) are eligible for Menu F."
            if website_ready
            else "No exact current article satisfies all Menu F eligibility rules.",
            actual={"eligible": eligible, "blocked": blocked},
            expected="Published, canonical-correct, Live 200, no blocker, no active duplicate.",
            next_action="Run Menu F for eligible articles only." if eligible else "Resolve the per-article blocker before Menu F.",
        )
        hot_files = list((self.data_dir / "social_drafts").rglob("*hot*.json")) if (self.data_dir / "social_drafts").is_dir() else []
        hot_records = []
        for path in hot_files:
            hot_records.extend(_items(_read_json(path, {})))
        invalid_hot = [
            row
            for row in hot_records
            if not row.get("source_url")
            and not row.get("source_urls")
            and not row.get("source_references")
        ]
        auto_published = [
            row
            for row in social_records + hot_records
            if str(row.get("status") or "").lower() in {"published", "auto_published"}
            and not row.get("published_url")
        ]
        hot_status = "BLOCKED" if invalid_hot or auto_published else "PASS"
        self.add(
            domain,
            "SOCIAL_HOT_SEPARATION",
            hot_status,
            "SOCIAL_HOT artifacts preserve a separate, non-auto-publish lane."
            if hot_status == "PASS"
            else "SOCIAL_HOT artifacts violate source or publish-state safety.",
            actual={
                "hot_records": len(hot_records),
                "missing_source": len(invalid_hot),
                "automatic_publish_records": len(auto_published),
            },
            expected="Sources/timestamps retained; no website canonical or automatic publish state.",
            next_action="Repair the listed local social record before Menu H/G/E." if hot_status != "PASS" else "",
        )
        return {
            "website_derived_social": "READY" if website_ready else "BLOCKED",
            "social_hot": "READY" if hot_status == "PASS" else "BLOCKED",
            "eligible_menu_f_candidates": eligible,
            "blocked_candidates": blocked,
            "counts": {
                "social_packages_ready": len(social_records),
                "awaiting_review": statuses.get("needs_social_review", 0),
                "approved_for_copy": statuses.get("approved_for_copy", 0),
                "revision_requested": statuses.get("revision_requested", 0),
                "rejected": statuses.get("rejected", 0),
                "not_recommended": statuses.get("not_recommended", 0),
                "hot_news_drafts_awaiting_review": len(hot_records),
            },
        }

    def _validator_health(self, *, deep: bool) -> None:
        domain = "validators"
        fixture = (
            "<!doctype html><html><head><meta charset='utf-8'>"
            "<title>Health Fixture</title><link rel='canonical' "
            "href='https://smileaireviewhub.com/health-fixture/'></head>"
            "<body><h1>Health Fixture</h1><p>Public editorial content.</p></body></html>"
        )
        validation = validate_public_output_files(
            task_id="health-fixture",
            slug="health-fixture",
            files={
                "website/health-fixture/article.html": (fixture, "html"),
            },
        )
        self.add(
            domain,
            "PUBLIC_HTML_MARKER_VALIDATOR",
            "PASS" if not validation else "BLOCKED",
            "Public HTML marker validator accepts a safe local fixture."
            if not validation
            else "Public HTML marker validator rejected a safe local fixture.",
            actual=validation,
            expected="Safe public HTML passes the shared validator.",
        )
        if not deep:
            self.add(
                domain,
                "DEEP_VALIDATOR_FIXTURES",
                "SKIPPED",
                "Targeted tests and model-consistency fixtures are only run with --deep.",
                expected="Skipped during normal fast health checks.",
                safe_command="python external_writer_console.py health-check --deep",
            )
            return
        command = [
            os.environ.get("PYTHON", "python"),
            "-m",
            "pytest",
            "tests/test_external_writer_return_validator.py",
            "tests/test_verified_writer_package.py",
            "tests/test_model_consistency_fixtures.py",
            "-q",
        ]
        try:
            completed = subprocess.run(
                command,
                cwd=self.root,
                capture_output=True,
                text=True,
                timeout=180,
                check=False,
            )
            status = "PASS" if completed.returncode == 0 else "BLOCKED"
            output = (completed.stdout + completed.stderr)[-4000:]
        except (OSError, subprocess.TimeoutExpired) as exc:
            status = "UNKNOWN"
            output = str(exc)
        self.add(
            domain,
            "DEEP_VALIDATOR_FIXTURES",
            status,
            "Targeted validator tests passed." if status == "PASS" else "Targeted validator tests did not pass.",
            actual=output,
            expected="Targeted validator tests exit with code 0.",
            next_action="Run the shown targeted tests directly and fix only failing validators." if status != "PASS" else "",
            safe_command="python -m pytest tests/test_external_writer_return_validator.py tests/test_verified_writer_package.py tests/test_model_consistency_fixtures.py -q",
        )

    def _domain_summary(self) -> dict[str, dict[str, Any]]:
        domains: dict[str, dict[str, Any]] = {}
        for row in self.checks:
            domain = row["domain"]
            domains.setdefault(domain, {"checks": [], "counts": {}})
            domains[domain]["checks"].append(row["check_id"])
            domains[domain]["counts"][row["status"]] = (
                domains[domain]["counts"].get(row["status"], 0) + 1
            )
        for domain, value in domains.items():
            rows = [row for row in self.checks if row["domain"] == domain]
            value["status"] = _aggregate(rows)
        return domains

    def _operational_readiness(
        self,
        *,
        current_articles: list[dict[str, Any]],
        social: dict[str, Any],
    ) -> dict[str, Any]:
        """Report stage-aware readiness without treating unfinished work as damage.

        Domain health remains strict for diagnostics.  This projection answers a
        different operator question: can today's workflow safely continue, and
        which stage is waiting for a human action?
        """
        batch_date, current_slugs = self._current_batch_selection()
        checks_by_id: dict[str, list[dict[str, Any]]] = {}
        for row in self.checks:
            checks_by_id.setdefault(str(row.get("check_id") or ""), []).append(row)

        def blocked(check_id: str) -> bool:
            return any(row.get("status") == "BLOCKED" for row in checks_by_id.get(check_id, []))

        core_blockers = [
            check_id
            for check_id in (
                "REPOSITORY_EXISTS",
                "EXPECTED_PROJECT_FILES",
                "MERGE_REBASE_CONFLICT",
                "WRITE_QUEUE_INTEGRITY",
                "APPROVAL_PUBLISH_CANONICAL_STATE",
            )
            if blocked(check_id)
        ]
        research_missing: dict[str, list[str]] = {}
        research_blockers: dict[str, list[str]] = {}
        current_topics_path = (
            self.data_dir / "editorial_queue" / batch_date / "topics.json"
        )
        current_topics_payload = _read_json(current_topics_path, {})
        current_topic_rows = (
            current_topics_payload.get("topics", [])
            if isinstance(current_topics_payload, dict)
            else _items(current_topics_payload)
        )
        current_topics_by_slug = {
            str(row.get("slug") or ""): row
            for row in current_topic_rows
            if isinstance(row, dict) and str(row.get("slug") or "")
        }
        for slug in current_slugs:
            research_dir = self.data_dir / "research" / slug
            missing = [name for name in RESEARCH_FILES if not (research_dir / name).is_file()]
            if missing:
                research_missing[slug] = missing
            topic = current_topics_by_slug.get(slug, {})
            readiness = topic.get("article_readiness") if isinstance(topic, dict) else {}
            if isinstance(readiness, dict) and readiness:
                exportable = readiness.get("draft_exportable")
                article_ready = readiness.get("article_ready")
                reasons = [
                    str(value)
                    for value in list(readiness.get("blockers") or [])
                    if str(value).strip()
                ]
                if exportable is False or article_ready is False or reasons:
                    research_blockers[slug] = reasons or [
                        "Current article research is not draft-exportable."
                    ]
        if (
            isinstance(current_topics_payload, dict)
            and str(current_topics_payload.get("batch_state") or "").upper()
            == "RESEARCH_BLOCKED"
        ):
            for slug in current_slugs:
                research_blockers.setdefault(
                    slug, ["Current daily batch is RESEARCH_BLOCKED."]
                )

        queue_rows = _items(_read_json(self.data_dir / "write_queue" / "index.json", {}))
        current_tasks = [
            row for row in queue_rows
            if str(row.get("batch_date") or "") == batch_date
            and str(row.get("article_slug") or "") in current_slugs
            and str(row.get("task_type") or "").startswith("WEBSITE_")
        ]
        exportable_tasks = [
            str(row.get("task_id") or "") for row in current_tasks
            if str(row.get("status") or "").upper() in {"PENDING", "READY", "READY_FOR_EXPORT"}
            and (self.data_dir / "write_queue" / f"{row.get('task_id')}.json").is_file()
        ]

        publish_rows = _items(_read_json(self.data_dir / "publish_queue.json", []))
        approval_rows = _items(_read_json(self.data_dir / "human_approval_queue.json", []))
        approval_by_slug = {str(row.get("slug") or ""): row for row in approval_rows}
        publishable: list[str] = []
        for row in publish_rows:
            slug = str(row.get("slug") or "")
            if slug not in current_slugs:
                continue
            status = str(row.get("status") or "").lower()
            if status not in {"ready_for_publish", "approved_for_publish"}:
                continue
            draft = self.data_dir / "production_article_drafts" / slug / "index.html"
            approval = approval_by_slug.get(slug, {})
            if draft.is_file():
                binding = binding_for_file(draft)
                if approval_binding_status(
                    approval,
                    current_content_hash=binding["content_hash"],
                    current_revision_id=binding["revision_id"],
                ) == "MATCHED":
                    publishable.append(slug)

        website_ready = bool(current_slugs) and not core_blockers
        research_ready = (
            bool(current_slugs) and not research_missing and not research_blockers
        )
        external_writer_ready = not blocked("WRITE_QUEUE_INTEGRITY") and (
            bool(exportable_tasks) or all(
                str(row.get("status") or "").upper() not in {"PENDING", "READY", "READY_FOR_EXPORT"}
                for row in current_tasks
            )
        )
        social_ready = str(social.get("website_derived_social") or "") == "READY"
        classifications = {
            "OPERATIONAL BLOCKER": core_blockers,
            "ACTION REQUIRED": [
                f"create/import draft for {slug}"
                for slug in current_slugs
                if not (self.data_dir / "production_article_drafts" / slug / "index.html").is_file()
                and slug not in research_blockers
            ] + [
                f"resolve research evidence for {slug}: {reasons[0]}"
                for slug, reasons in research_blockers.items()
            ],
            "WAITING FOR OPERATOR": [f"publish exact slug {slug}" for slug in publishable],
            "BACKLOG": ["claim conflicts outside the current batch"]
            if any(row.get("check_id") == "CLAIM_CONFLICTS" and row.get("status") == "WARNING" for row in self.checks)
            else [],
            "HISTORICAL": ["latest advanced-batch comparator audit"]
            if self.menu_readiness.get("batch_date") and self.menu_readiness.get("batch_date") != batch_date
            else [],
            "OPTIONAL SUBSYSTEM": [] if social_ready else ["website-derived social distribution"],
        }
        return {
            "current_batch_date": batch_date,
            "ready_for_normal_daily_operation": website_ready,
            "website_daily_ready": website_ready,
            "research_ready": research_ready,
            "external_writer_ready": external_writer_ready,
            "publish_ready": bool(publishable),
            "publishable_slugs": publishable,
            "deployment_ready": bool(publishable),
            "social_ready": social_ready,
            "research_missing": research_missing,
            "research_blockers": research_blockers,
            "exportable_task_ids": exportable_tasks,
            "classifications": classifications,
        }

    def _readiness(self, domains: dict[str, dict[str, Any]]) -> dict[str, str]:
        status = lambda key: domains.get(key, {}).get("status", "SKIPPED")
        return {
            "website_research_readiness": status("research"),
            "external_writer_readiness": self._combine_domains(
                domains, ("research", "verified_package")
            ),
            "import_readiness": status("external_return"),
            "editorial_review_readiness": self._combine_domains(
                domains, ("editorial_queue", "approval_publish")
            ),
            "publish_readiness": self._combine_domains(
                domains, ("approval_publish", "deployment")
            ),
            "live_deployment_health": status("deployment"),
            "website_derived_social_readiness": next(
                (
                    row["status"]
                    for row in self.checks
                    if row["check_id"] == "WEBSITE_DERIVED_SOCIAL_GO_NO_GO"
                ),
                "UNKNOWN",
            ),
            "social_hot_readiness": next(
                (
                    row["status"]
                    for row in self.checks
                    if row["check_id"] == "SOCIAL_HOT_SEPARATION"
                ),
                "UNKNOWN",
            ),
            "repository_health": status("repository"),
        }

    @staticmethod
    def _combine_domains(
        domains: dict[str, dict[str, Any]], names: tuple[str, ...]
    ) -> str:
        return _aggregate(
            {"status": domains.get(name, {}).get("status", "SKIPPED")} for name in names
        )

    @staticmethod
    def _recommend(readiness: dict[str, str]) -> str:
        if (
            readiness.get("repository_health") == "BLOCKED"
            or readiness.get("publish_readiness") == "BLOCKED"
        ):
            return "ACTION REQUIRED"
        candidates = (
            ("SAFE TO RUN MENU W", "import_readiness"),
            ("SAFE TO RUN MENU X", "external_writer_readiness"),
            ("SAFE TO RUN MENU F", "website_derived_social_readiness"),
            ("SAFE TO RUN MENU H", "social_hot_readiness"),
            ("SAFE TO RUN MENU 4", "editorial_review_readiness"),
            ("SAFE TO RUN MENU 1", "website_research_readiness"),
        )
        for label, key in candidates:
            if readiness.get(key) == "PASS":
                return label
        return "ACTION REQUIRED"

    def write_reports(
        self, payload: dict[str, Any], *, report_path: Path | None = None
    ) -> dict[str, str]:
        base = report_path or self.data_dir / "system_health_report"
        if base.suffix.lower() in {".json", ".md", ".html"}:
            base = base.with_suffix("")
        base.parent.mkdir(parents=True, exist_ok=True)
        json_path = base.with_suffix(".json")
        md_path = base.with_suffix(".md")
        html_path = base.with_suffix(".html")
        report_paths = {
            "json": str(json_path),
            "markdown": str(md_path),
            "html": str(html_path),
        }
        payload["reports"] = report_paths
        json_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        md_path.write_text(self._markdown(payload), encoding="utf-8")
        html_path.write_text(self._html(payload), encoding="utf-8")
        return report_paths

    @staticmethod
    def _markdown(payload: dict[str, Any]) -> str:
        lines = [
            "# System Health Report",
            "",
            f"- Generated: {payload['generated_at']}",
            f"- Mode: {payload['mode']}",
            f"- Scope: {payload['scope']}",
            f"- Recommendation: **{payload['operator_recommendation']}**",
            "",
            "## Pipeline Readiness",
            "",
        ]
        for key, value in payload["overall"].items():
            lines.append(f"- {key.replace('_', ' ').title()}: **{value}**")
        operational = payload["operational_readiness"]
        lines.extend(["", "## Scoped Operational Readiness", ""])
        for key in (
            "ready_for_normal_daily_operation",
            "website_daily_ready",
            "research_ready",
            "external_writer_ready",
            "publish_ready",
            "deployment_ready",
            "social_ready",
        ):
            lines.append(f"- {key.replace('_', ' ').title()}: **{operational[key]}**")
        lines.extend(["", "### Finding classifications", ""])
        for category, findings in operational["classifications"].items():
            lines.append(f"- {category}: {', '.join(findings) if findings else 'none'}")
        lines.extend(["", "## Current Batch", ""])
        for key, value in payload["current_batch"].items():
            lines.append(f"- {key.replace('_', ' ').title()}: {value}")
        lines.extend(["", "## Current Articles", ""])
        for article in payload["current_articles"]:
            lines.extend(
                [
                    f"### {article['slug']}",
                    f"- Editorial: {article['editorial_status']}",
                    f"- Publish gate: {article['publish_gate_status']}",
                    f"- Approval: {article['human_approval_status']}",
                    f"- Local/docs/static: {article['local_output']}/{article['docs_output']}/{article['published_static_output']}",
                    f"- Git: {article['git_state']}",
                    f"- Canonical: {article['canonical_url']}",
                    f"- Live: {article['live_check_status']} ({article.get('live_http_status') or 'offline'})",
                    "",
                ]
            )
        lines.extend(["## Issues", ""])
        if not payload["issues"]:
            lines.append("- No warning, blocker, or unknown state.")
        for issue in payload["issues"]:
            lines.extend(
                [
                    f"### {issue['status']} - {issue['check_id']}",
                    f"- Domain: {issue['domain']}",
                    f"- Path: {issue['file_or_path'] or 'n/a'}",
                    f"- Slug/task: {issue['slug'] or issue['task_id'] or 'n/a'}",
                    f"- Reason: {issue['reason']}",
                    f"- Expected: {issue['expected_condition']}",
                    f"- Next action: {issue['next_action'] or 'No action required'}",
                    f"- Safe command: `{issue['safe_command']}`" if issue["safe_command"] else "- Safe command: n/a",
                    "",
                ]
            )
        return "\n".join(lines).rstrip() + "\n"

    @staticmethod
    def _html(payload: dict[str, Any]) -> str:
        def esc(value: Any) -> str:
            return html.escape(str(value))

        readiness = "".join(
            f"<div class='kpi'><span>{esc(key.replace('_', ' ').title())}</span>"
            f"<strong class='{esc(value.lower())}'>{esc(value)}</strong></div>"
            for key, value in payload["overall"].items()
        )
        article_rows = "".join(
            "<tr>"
            f"<td><strong>{esc(row['slug'])}</strong></td>"
            f"<td>{esc(row['editorial_status'])}</td>"
            f"<td>{esc(row['publish_gate_status'])}</td>"
            f"<td>{esc(row['human_approval_status'])}</td>"
            f"<td>{esc(row['local_output'])}/{esc(row['docs_output'])}/{esc(row['published_static_output'])}</td>"
            f"<td>{esc(row['git_state'])}</td>"
            f"<td>{esc(row['live_check_status'])} {esc(row.get('live_http_status') or '')}</td>"
            f"<td><a href='{esc(row['expected_url'])}'>{esc(row['expected_url'])}</a></td>"
            "</tr>"
            for row in payload["current_articles"]
        )
        issue_rows = "".join(
            "<tr>"
            f"<td><span class='badge {esc(row['status'].lower())}'>{esc(row['status'])}</span></td>"
            f"<td>{esc(row['domain'])}</td><td>{esc(row['check_id'])}</td>"
            f"<td>{esc(row['slug'] or row['task_id'])}</td>"
            f"<td>{esc(row['reason'])}</td><td>{esc(row['next_action'])}</td>"
            f"<td><code>{esc(row['safe_command'])}</code></td></tr>"
            for row in payload["issues"]
        )
        batch = "".join(
            f"<li><strong>{esc(key.replace('_', ' ').title())}:</strong> {esc(value)}</li>"
            for key, value in payload["current_batch"].items()
        )
        operational = payload["operational_readiness"]
        operational_rows = "".join(
            f"<div class='kpi'><span>{esc(key.replace('_', ' ').title())}</span>"
            f"<strong>{esc(operational[key])}</strong></div>"
            for key in (
                "ready_for_normal_daily_operation",
                "website_daily_ready",
                "research_ready",
                "external_writer_ready",
                "publish_ready",
                "deployment_ready",
                "social_ready",
            )
        )
        classification_rows = "".join(
            f"<li><strong>{esc(category)}:</strong> {esc(', '.join(findings) if findings else 'none')}</li>"
            for category, findings in operational["classifications"].items()
        )
        return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>System Health Report</title>
<style>
:root{{--ink:#172033;--muted:#61708a;--line:#dce4ef;--bg:#f4f7fb;--card:#fff;--green:#147d4f;--red:#b42318;--amber:#a15c00;--blue:#2463eb}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 "Segoe UI",sans-serif}}
main{{max-width:1500px;margin:auto;padding:32px}}section{{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:24px;margin:18px 0;box-shadow:0 8px 24px #23314d0d}}
h1,h2{{margin-top:0}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px}}.kpi{{padding:14px;border:1px solid var(--line);border-radius:12px;display:flex;flex-direction:column;gap:5px}}
.pass{{color:var(--green)}}.warning,.unknown{{color:var(--amber)}}.blocked{{color:var(--red)}}.skipped{{color:var(--muted)}}.badge{{font-weight:700}}
.table{{overflow:auto}}table{{width:100%;border-collapse:collapse;min-width:980px}}th,td{{padding:12px;text-align:left;border-bottom:1px solid var(--line);vertical-align:top}}th{{background:#eef3f9}}code{{white-space:pre-wrap}}a{{color:var(--blue)}}ul{{padding-left:20px}}
</style></head><body><main>
<section><h1>System Health Report</h1><p>Generated {esc(payload['generated_at'])} | {esc(payload['mode'])} | {esc(payload['scope'])}</p>
<h2>{esc(payload['operator_recommendation'])}</h2><div class="grid">{readiness}</div></section>
<section><h2>Scoped Operational Readiness</h2><div class="grid">{operational_rows}</div><h3>Finding classifications</h3><ul>{classification_rows}</ul></section>
<section><h2>Current Batch</h2><ul>{batch}</ul><p>Site-wide totals and current-batch totals are separate datasets. A site-wide Live 200 count must not be read as the latest batch count.</p></section>
<section><h2>Current Production Articles</h2><div class="table"><table><thead><tr><th>Slug</th><th>Editorial</th><th>Publish gate</th><th>Approval</th><th>Local/docs/static</th><th>Git</th><th>Live</th><th>URL</th></tr></thead><tbody>{article_rows}</tbody></table></div></section>
<section><h2>Social Go/No-Go</h2><p>Website-derived: <strong>{esc(payload['social_go_no_go']['website_derived_social'])}</strong> | SOCIAL_HOT: <strong>{esc(payload['social_go_no_go']['social_hot'])}</strong></p><p>Menu F candidates: {esc(', '.join(payload['social_go_no_go']['eligible_menu_f_candidates']) or 'none')}</p></section>
<section><h2>Actionable Issues</h2><div class="table"><table><thead><tr><th>Status</th><th>Domain</th><th>Check</th><th>Slug/task</th><th>Reason</th><th>Next action</th><th>Safe command</th></tr></thead><tbody>{issue_rows}</tbody></table></div></section>
</main></body></html>"""

    def _git(self, *args: str, allow_failure: bool = False) -> str:
        try:
            result = subprocess.run(
                ["git", *args],
                cwd=self.root,
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return ""
        if result.returncode and not allow_failure:
            return ""
        return result.stdout.strip()

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _canonical(path: Path) -> str:
        if not path.is_file():
            return ""
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            return ""
        match = re.search(
            r"<link[^>]+rel=[\"']canonical[\"'][^>]+href=[\"']([^\"']+)",
            text,
            re.IGNORECASE,
        )
        if not match:
            match = re.search(
                r"<link[^>]+href=[\"']([^\"']+)[\"'][^>]+rel=[\"']canonical[\"']",
                text,
                re.IGNORECASE,
            )
        return match.group(1).strip() if match else ""

    @staticmethod
    def _verified_package_details(path: Path) -> dict[str, Any]:
        try:
            with zipfile.ZipFile(path) as archive:
                contract = json.loads(
                    archive.read("verified_package_contract.json").decode("utf-8")
                )
                selection = (
                    json.loads(archive.read("batch_selection.json").decode("utf-8"))
                    if "batch_selection.json" in archive.namelist()
                    else {}
                )
        except (OSError, KeyError, UnicodeError, json.JSONDecodeError, zipfile.BadZipFile):
            return {}
        tasks = _items(contract.get("tasks", []))
        return {
            "schema_version": contract.get("schema_version"),
            "package_id": contract.get("package_id"),
            "included_tasks": [row.get("task_id") for row in tasks],
            "held_tasks": selection.get("held_tasks", []),
            "partial_package": bool(selection.get("held_tasks")),
        }

    @staticmethod
    def _http_status(url: str) -> tuple[int | None, str]:
        request = urllib.request.Request(
            url,
            method="GET",
            headers={"User-Agent": "SmileAIReviewHub-SystemHealth/1.0"},
        )
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                return int(response.status), "reachable"
        except urllib.error.HTTPError as exc:
            return int(exc.code), f"HTTP {exc.code}: {exc.reason}"
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            return None, str(exc)
