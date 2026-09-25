from __future__ import annotations

import argparse
import json
import os
import sys
import zipfile
from pathlib import Path

from modules.external_writer_pipeline import (
    TASK_TYPES,
    UniversalExternalWriterExporter,
    UniversalExternalWriterImporter,
    UniversalWriteQueue,
    rebuild_completed_manifest,
)
from modules.verified_writer_package import validate_verified_package
from modules.research_enrichment import ResearchEnrichmentPipeline
from modules.system_health_check import SystemHealthCheck


ROOT = Path(__file__).resolve().parent


def _export_batches_for_requested_date(
    active: list[dict[str, object]],
    *,
    requested_date: str,
) -> list[dict[str, object]]:
    """Match Menu X selection to the exporter's date semantics.

    ``latest`` means the newest batch date across the whole queue.  Older
    per-lane backlogs remain visible in the status listing, but must not force
    an interactive choice when a newer batch is ready.
    """
    if requested_date != "latest" or not active:
        return active
    latest_date = max(str(row.get("batch_date") or "") for row in active)
    return [row for row in active if str(row.get("batch_date") or "") == latest_date]


def _choose_export_task_type(
    active: list[dict[str, object]],
    *,
    requested_date: str,
    explicit_task_type: str | None,
) -> tuple[str | None, bool]:
    """Return (task_type, cancelled) without allowing a closed stdin to crash."""
    if explicit_task_type:
        return explicit_task_type, False
    selectable = _export_batches_for_requested_date(active, requested_date=requested_date)
    choices = [str(row["task_type"]) for row in selectable]
    if len(choices) == 1:
        row = selectable[0]
        print(
            "AUTO_SELECTED_LATEST_BATCH: "
            f"{row['task_type']} @ {row['batch_date']} "
            f"({row['eligible']} eligible, {row['held']} held)"
        )
        return choices[0], False
    if len(choices) <= 1:
        return None, False
    if not sys.stdin.isatty():
        raise RuntimeError(
            "Multiple task types share the requested batch date; rerun with "
            "--task-type to choose one explicitly."
        )
    print("Choose the exact workflow lane:")
    for index, row in enumerate(selectable, start=1):
        print(
            f"{index}. {row['task_type']} @ {row['batch_date']} "
            f"({row['eligible']} eligible, {row['held']} held)"
        )
    try:
        selected = input(f"Choose package [1-{len(choices)}], or 0 to cancel: ").strip()
    except (EOFError, KeyboardInterrupt) as exc:
        raise RuntimeError(
            "The Menu X selection input was closed. No package was exported; "
            "return to Runbot Menu and try again."
        ) from exc
    if not selected.isdigit() or not 1 <= int(selected) <= len(choices):
        print("[INFO] Export cancelled.")
        return None, True
    return choices[int(selected) - 1], False


def _choose_zip(importer: UniversalExternalWriterImporter, explicit: str) -> Path | None:
    if not explicit:
        reconciled = importer.reconcile_returned()
        for row in reconciled:
            print(
                "RETURNED_CLASSIFIED: "
                f"{row.get('source_filename', '')} -> {row.get('status', '')} "
                f"({row.get('destination_path') or row.get('move_error') or 'source preserved'})"
            )
    candidates = importer.discover(explicit=explicit)
    if not candidates:
        if not sys.stdin.isatty():
            return None
        print(f"No completed ZIP found in Menu W inbox: {importer.returned_root}")
        value = input("Paste the full ZIP path (blank to cancel): ").strip().strip('"')
        return Path(value) if value else None
    if len(candidates) == 1:
        candidate = candidates[0]
        print(
            f"Found: {candidate.path} | date={candidate.modified_at} | "
            f"package_id={candidate.package_id or 'unknown'} | "
            f"lane={candidate.lane or 'unknown'} | status={candidate.status}"
        )
        if not sys.stdin.isatty():
            return candidate.path
        answer = input("Import this ZIP? [Y/N]: ").strip().lower()
        return candidate.path if answer in {"y", "yes"} else None
    print("Completed ZIP files:")
    for index, candidate in enumerate(candidates, start=1):
        print(
            f"{index}. {candidate.path} | date={candidate.modified_at} | "
            f"package_id={candidate.package_id or 'unknown'} | "
            f"lane={candidate.lane or 'unknown'} | status={candidate.status}"
        )
    if not sys.stdin.isatty():
        raise RuntimeError("Multiple completed ZIP files found; pass --zip explicitly.")
    value = input(f"Choose [1-{len(candidates)}], or 0 to cancel: ").strip()
    if not value.isdigit() or int(value) < 1 or int(value) > len(candidates):
        return None
    return candidates[int(value) - 1].path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Model-neutral external writer package exchange.")
    sub = parser.add_subparsers(dest="command", required=True)
    sync = sub.add_parser("sync", help="Synchronize legacy workflow tasks into data/write_queue.")
    sync.add_argument("--date", default="latest")
    sync.add_argument("--lane", choices=("website", "social", "all"), default="all")
    export = sub.add_parser("export", help="Create one upload-ready external writer ZIP.")
    export.add_argument("--date", default="latest")
    export.add_argument("--task-type", choices=sorted(TASK_TYPES))
    validate_package = sub.add_parser(
        "validate-package",
        help="Validate a verified package without repository context.",
    )
    validate_package.add_argument("package", type=Path)
    validate_completed = sub.add_parser(
        "validate-completed",
        help="Validate completed_drafts.zip through the exact Menu W contract.",
    )
    validate_completed.add_argument("zip", type=Path)
    validate_completed.add_argument("--package", type=Path)
    validate_completed.add_argument("--json", action="store_true", dest="json_output")
    validate_completed.add_argument("--report", type=Path)
    stage_completed = sub.add_parser(
        "stage-completed",
        help="Validate and safely copy completed_drafts.zip into Menu W's Returned inbox.",
    )
    stage_completed.add_argument("zip", type=Path)
    stage_completed.add_argument("--package", type=Path)
    stage_completed.add_argument("--json", action="store_true", dest="json_output")
    rebuild = sub.add_parser(
        "rebuild-completed-manifest",
        help="Recompute return checksums and build a validated completed ZIP.",
    )
    rebuild.add_argument("directory", type=Path)
    rebuild.add_argument("--output", type=Path, required=True)
    import_zip = sub.add_parser("import", help="Discover, validate, and import completed_drafts.zip.")
    import_zip.add_argument("--zip", default="")
    import_zip.add_argument("--fallback-pending", action="store_true")
    import_zip.add_argument("--refresh-social-dashboard", action="store_true")
    archive_report = sub.add_parser(
        "archive-report",
        help="Read-only report of archived completed ZIPs older than a threshold.",
    )
    archive_report.add_argument("--days", type=int, default=30)
    archive_report.add_argument("--json", action="store_true", dest="json_output")
    revision = sub.add_parser(
        "request-revision",
        help="Safely reopen one unapproved website task for an external-writer rewrite.",
    )
    revision.add_argument("--task-id", default="")
    revision.add_argument("--date", default="latest")
    revision.add_argument("--slug", default="")
    revision.add_argument("--reason", required=True)
    enrich = sub.add_parser(
        "enrich-research",
        help="Retrieve approved sources and build article-ready evidence artifacts.",
    )
    enrich.add_argument("--date", default="latest")
    enrich.add_argument("--task-type", choices=sorted(TASK_TYPES))
    enrich.add_argument("--slug", default="")
    enrich.add_argument("--dry-run", action="store_true")
    enrich.add_argument("--refresh-sources", action="store_true")
    enrich.add_argument("--no-reuse-cache", action="store_true")
    enrich.add_argument("--json-report", type=Path)
    enrich.add_argument("--human-report", type=Path)
    health = sub.add_parser(
        "health-check",
        help="Run a read-only repository-first system health check.",
    )
    health.add_argument("--json", action="store_true", dest="json_output")
    health.add_argument("--report", type=Path)
    mode = health.add_mutually_exclusive_group()
    mode.add_argument("--offline", action="store_true")
    mode.add_argument("--live", action="store_true")
    health.add_argument("--scope", choices=("website", "social", "full"), default="full")
    health.add_argument("--deep", action="store_true")
    health.add_argument("--open", action="store_true", dest="open_report")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    queue = UniversalWriteQueue(root=ROOT)
    if args.command == "archive-report":
        result = UniversalExternalWriterImporter(root=ROOT).archive_report(
            older_than_days=args.days
        )
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    if args.command == "health-check":
        result = SystemHealthCheck(root=ROOT).run(
            scope=args.scope,
            live=bool(args.live),
            deep=bool(args.deep),
            report_path=args.report,
        )
        if args.json_output:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print("SYSTEM HEALTH CHECK")
            print(f"Mode: {result['mode']} | Scope: {result['scope']} | Deep: {result['deep']}")
            print(
                "Website: {website_pipeline} | Social: {social_pipeline} | "
                "Research: {research_engine} | External Writer: {external_writer} | "
                "Deployment: {deployment}".format(**result["overall"])
            )
            print(
                "WEBSITE-DERIVED SOCIAL: "
                f"{result['social_go_no_go']['website_derived_social']}"
            )
            print(f"SOCIAL_HOT: {result['social_go_no_go']['social_hot']}")
            print(f"Recommendation: {result['operator_recommendation']}")
            print(
                f"Issues: {len(result['issues'])} | "
                f"Current batch: {result['current_batch'].get('date') or 'none'} | "
                f"Current articles live: "
                f"{sum(row.get('cached_live_http_status') == 200 or row.get('live_http_status') == 200 for row in result['current_articles'])}/"
                f"{len(result['current_articles'])}"
            )
            print(f"HTML: {result['reports']['html']}")
            print(f"Markdown: {result['reports']['markdown']}")
            print(f"JSON: {result['reports']['json']}")
            print("Read-only: no approval, publish, Git, deploy, indexing, or API action occurred.")
        if args.open_report:
            os.startfile(result["reports"]["html"])
        return 2 if any(value == "BLOCKED" for value in result["overall"].values()) else 0
    if args.command == "validate-package":
        result = validate_verified_package(args.package)
        print(json.dumps(result.as_dict(), indent=2, ensure_ascii=False))
        return 0 if result.valid else 2
    if args.command == "validate-completed":
        result = UniversalExternalWriterImporter(root=ROOT).validate_zip(
            args.zip,
            verified_package=args.package,
        )
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(
                json.dumps(result, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        if args.json_output or not sys.stdout.isatty():
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(f"Status: {result['status']}")
            for error in result.get("rejected", []):
                print(json.dumps(error, indent=2, ensure_ascii=False))
        return 0 if result["status"] == "VALIDATION_PASS" else 2
    if args.command == "stage-completed":
        result = UniversalExternalWriterImporter(root=ROOT).stage_completed_zip(
            args.zip,
            verified_package=args.package,
        )
        if args.json_output or not sys.stdout.isatty():
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(f"Status: {result['status']}")
            if result.get("destination_path"):
                print(f"Menu W inbox: {result['destination_path']}")
            if result.get("reason"):
                print(f"Reason: {result['reason']}")
        return 0 if result["status"] in {"STAGED", "ALREADY_STAGED"} else 2
    if args.command == "rebuild-completed-manifest":
        try:
            result = rebuild_completed_manifest(
                args.directory,
                output=args.output,
                project_root=ROOT,
            )
        except (OSError, ValueError, zipfile.BadZipFile) as exc:
            print(f"[ERROR] {exc}")
            return 2
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    if args.command == "sync":
        if args.lane == "website":
            rows = queue.sync_website(batch_date=args.date)
        elif args.lane == "social":
            rows = queue.sync_social(batch_date=args.date)
        else:
            rows = queue.sync_all(batch_date=args.date)
        print(f"WRITE_QUEUE_SYNCED: {len(rows)}")
        for row in rows:
            print(f"- {row['task_type']} | {row['task_id']} | {row['article_slug']} | {row['status']}")
        print("No writing, approval, publish, Git, deploy, index, or API action occurred.")
        return 0
    if args.command == "enrich-research":
        queue.sync_all(batch_date=args.date)
        rows = queue.list_tasks()
        if args.date != "latest":
            rows = [row for row in rows if row.get("batch_date") == args.date]
        if args.task_type:
            rows = [row for row in rows if row.get("task_type") == args.task_type]
        if args.slug:
            rows = [row for row in rows if row.get("article_slug") == args.slug]
        if not rows:
            print("[ERROR] No matching research tasks were found.")
            return 2
        tasks: dict[str, dict[str, object]] = {}
        slugs: list[str] = []
        for row in rows:
            slug = str(row.get("article_slug") or "").strip()
            if not slug or slug in tasks:
                continue
            slugs.append(slug)
            tasks[slug] = {
                **row,
                "slug": slug,
                "title": str(row.get("title") or slug.replace("-", " ")),
                "primary_source_url": str(row.get("primary_source_url") or ""),
                "supporting_source_urls": list(row.get("supporting_source_urls") or []),
            }
        config = json.loads((ROOT / "config" / "editorial_system.json").read_text(encoding="utf-8"))
        report = ResearchEnrichmentPipeline(
            root=ROOT,
            data_dir=ROOT / "data",
            config=config,
        ).enrich_batch(
            slugs,
            tasks=tasks,
            refresh_sources=args.refresh_sources,
            reuse_cache=not args.no_reuse_cache,
            dry_run=args.dry_run,
        )
        json_path = args.json_report or ROOT / "data" / "research_enrichment_v2_report.json"
        human_path = args.human_report or ROOT / "data" / "research_enrichment_v2_report.md"
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        lines = [
            "# Research Enrichment v2 Report",
            "",
            f"- Tasks processed: {report['tasks_processed']}",
            f"- ARTICLE_READY: {report['article_ready']}",
            f"- BLOCKED_RESEARCH: {report['blocked_research']}",
            "",
        ]
        for item in report["items"]:
            lines.extend(
                [
                    f"## {item['slug']}",
                    f"- Status: {item['status']}",
                    f"- Sources: {item['sources_retrieved']}/{item['sources_attempted']} retrieved",
                    f"- Usable paragraphs: {item['usable_paragraphs']}",
                    (
                        f"- Claims: {item.get('candidate_claims', 0)} candidate / "
                        f"{item['publishable_claims']} accepted / "
                        f"{item.get('rejected_claims', 0)} rejected"
                    ),
                    (
                        f"- Mandatory sections: {item['mandatory_sections_covered']}/"
                        f"{item['mandatory_sections_total']} covered"
                    ),
                    f"- Blockers: {'; '.join(item['blockers']) or 'none'}",
                    f"- Warnings: {'; '.join(item['warnings']) or 'none'}",
                    "",
                ]
            )
        human_path.parent.mkdir(parents=True, exist_ok=True)
        human_path.write_text("\n".join(lines), encoding="utf-8")
        for item in report["items"]:
            ready = "YES" if item["article_ready"] else "NO"
            print(
                f"{item['slug']}: ARTICLE_READY={ready} | "
                f"sources={item['sources_retrieved']}/{item['sources_attempted']} | "
                f"paragraphs={item['usable_paragraphs']} | "
                f"claims={item.get('candidate_claims', 0)}/"
                f"{item['publishable_claims']}/{item.get('rejected_claims', 0)}"
            )
            for blocker in item["blockers"]:
                print(f"  BLOCKER: {blocker}")
        print(f"JSON report: {json_path}")
        print(f"Human report: {human_path}")
        print("No writing, approval, publish, Git, deploy, index, or API action occurred.")
        return 0 if report["blocked_research"] == 0 else 2
    if args.command == "export":
        task_type = args.task_type
        exporter = UniversalExternalWriterExporter(root=ROOT)
        queue.sync_all(batch_date=args.date)
        active = exporter.active_batches()
        if args.date != "latest":
            active = [row for row in active if row.get("batch_date") == args.date]
        if task_type:
            active = [row for row in active if row.get("task_type") == task_type]
        if active:
            print("ACTIVE_EXTERNAL_WRITER_BATCHES:")
            for row in active:
                print(
                    f"- {row['task_type']} | {row['batch_date']} | "
                    f"tasks={row['task_count']} | eligible={row['eligible']} | held={row['held']}"
                )
                for task in row.get("tasks") or []:
                    print(
                        "  "
                        f"{task['task_id']} | slug={task['article_slug']} | "
                        f"root={task.get('root_topic_id') or '-'} | "
                        f"sequence={task.get('sequence') or '-'} | "
                        f"angle={task.get('daily_angle') or '-'} | "
                        f"state={task.get('research_state') or '-'} | "
                        f"paragraphs={task.get('paragraphs', 0)} | "
                        f"claims={task.get('claims', 0)} | "
                        f"coverage={task.get('coverage_score', 0):.2f} | "
                        f"eligible={'YES' if task.get('eligible') else 'NO'} | "
                        f"path={task.get('research_artifact_dir') or '-'}"
                    )
                    if not task.get("eligible"):
                        print(f"    HOLD: {task.get('reason') or 'Research evidence is not ready.'}")
        try:
            task_type, cancelled = _choose_export_task_type(
                active,
                requested_date=args.date,
                explicit_task_type=task_type,
            )
        except RuntimeError as exc:
            print(f"[ERROR] {exc}")
            return 2
        if cancelled:
            return 0
        try:
            result = exporter.export(
                batch_date=args.date,
                task_type=task_type,
            )
        except RuntimeError as exc:
            message = str(exc)
            if message.startswith("NO_ELIGIBLE_TASKS"):
                print(f"[BLOCKED_RESEARCH] {message}")
                print("No ZIP was created and no workflow, approval, or publish state was changed.")
                print("Next: use Source Review for the held slug, verify real official sources, then rerun Menu X.")
                return 3
            print(f"[ERROR] {message}")
            return 2
        print("External writer package ready.")
        print(f"Type: {result['package_type']}")
        print(f"Tasks: {result['task_count']}")
        print(f"Articles: {result['article_count']}")
        print(f"Platforms: {result['platform_count']}")
        print(f"Languages: {result['language_count']}")
        print(f"ZIP: {result['zip_path']}")
        print(f"ZIP size: {result['zip_size']} bytes")
        print(f"SHA-256: {result['sha256']}")
        print(f"Validation: {result['validation']}")
        recovery = result.get("research_recovery") or {}
        if recovery.get("RECOVERY_ATTEMPTED"):
            print("Research recovery:")
            for key in (
                "RECOVERY_ATTEMPTED", "RESEARCH_RECOVERY_ATTEMPTED",
                "SOURCES_BEFORE", "SOURCES_AFTER", "EVIDENCE_COVERAGE_BEFORE",
                "EVIDENCE_COVERAGE_AFTER", "TASKS_RECOVERED", "TASKS_STILL_HELD", "TASKS_HELD",
                "SOURCES_FOUND", "OFFICIAL_SOURCES_FOUND", "SOURCE_FAMILIES",
                "VERIFIED_CLAIMS", "ENTITY_COVERAGE", "EVIDENCE_COVERAGE",
                "RESEARCH_TASKS_REMAINING", "FINAL_EXPORTABLE_COUNT",
                "FINAL_HELD_COUNT", "OPERATOR_ACTION_REQUIRED",
            ):
                print(f"- {key}: {recovery.get(key)}")
        print("Next:")
        print("1. Upload this ZIP to any capable external AI writer.")
        print('2. Send only: "Read START_HERE.txt. Complete every article. Return completed_drafts.zip."')
        print("3. Download the returned ZIP.")
        print("4. Run Menu W.")
        return 0
    if args.command == "request-revision":
        queue.sync_website(batch_date=args.date)
        selected = queue.get(args.task_id) if args.task_id else None
        if selected is None and args.slug:
            candidates = [
                row
                for row in queue.list_tasks()
                if row.get("article_slug") == args.slug
                and str(row.get("task_type") or "").startswith("WEBSITE_")
            ]
            if args.date != "latest":
                candidates = [row for row in candidates if row.get("batch_date") == args.date]
            if candidates:
                selected = max(candidates, key=lambda row: str(row.get("batch_date") or ""))
        if selected is None:
            print("[ERROR] Website task not found. Pass --task-id or --slug.")
            return 2
        try:
            revised = queue.request_website_revision(
                str(selected["task_id"]),
                reason=args.reason,
            )
        except ValueError as exc:
            print(f"[ERROR] {exc}")
            return 2
        print("WEBSITE_REVISION_REQUESTED")
        print(f"Task: {revised['task_id']}")
        print(f"Slug: {revised['article_slug']}")
        print(f"Revision: {revised['revision']}")
        print("Next: run Menu X and choose the website package.")
        print("No approval, publish, Git, deploy, index, or API action occurred.")
        return 0
    importer = UniversalExternalWriterImporter(root=ROOT)
    try:
        zip_path = _choose_zip(importer, args.zip)
    except RuntimeError as exc:
        print(f"[ERROR] {exc}")
        return 2
    if zip_path is None:
        print("[INFO] No pending completed_drafts*.zip remains in Returned. Nothing was imported.")
        return 0
    try:
        result = importer.process_returned_zip(zip_path)
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        print(f"[ERROR] External writer import failed: {exc}")
        return 2
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if args.refresh_social_dashboard and any(row.get("type") == "social" for row in result.get("imported", [])):
        from modules.social.draft_workflow import SocialDraftWorkflow

        date = queue.get(result["imported"][0]["task_id"])["batch_date"]
        print(f"Dashboard refreshed: {SocialDraftWorkflow(root=ROOT).build_review_dashboard(batch_date=date)}")
    print("All imported drafts remain unapproved. Nothing was published.")
    return 2 if result.get("rejected") or result.get("move_error") else 0


if __name__ == "__main__":
    raise SystemExit(main())
