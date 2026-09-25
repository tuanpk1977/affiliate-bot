from __future__ import annotations

import argparse
from pathlib import Path

from modules.source_review_operator import MANUAL_SOURCE_FAMILIES, SourceReviewOperator


def _print_task(row: dict) -> None:
    print(f"\n{row['title']} [{row['slug']}]")
    print(f"   State={row['research_state']} | total={row['total_sources']} | official={row['official_sources']} | verified={row['verified_sources']}")
    print(f"   families={','.join(row['source_families']) or 'none'} | evidence={row['evidence_coverage']:.2f} | entity={row['entity_coverage']:.2f}")
    for entity_name, metrics in row.get("entity_coverage_by_product", {}).items():
        print(
            f"   entity {entity_name}: coverage={metrics['coverage']:.2f} | "
            f"sources={metrics['sources']} | claims={metrics['claims']} | "
            f"status={metrics['status'] or 'unknown'}"
        )
        print(
            f"      families={','.join(metrics.get('source_families', [])) or 'none'} | "
            f"official URLs={', '.join(metrics.get('official_sources', [])) or 'none'}"
        )
    scores = row.get("source_scores", {})
    if scores:
        print(
            "   scores: verified={total_verified_source_score:g} | "
            "docs={official_docs_score:g} | pricing={pricing_source_score:g} | "
            "affiliate={affiliate_source_score:g}".format(**scores)
        )
    print(
        f"   unique thesis={row.get('unique_thesis_status', 'MISSING')}"
        + (f" | {row['unique_thesis']}" if row.get("unique_thesis") else "")
    )
    print(f"   failing gates: {', '.join(row['failing_gates']) or 'none'}")
    program = row.get("affiliate_program", {})
    print(
        "   affiliate: status={status} | program={url} | commission={commission} | "
        "cookie={cookie} | verification={verification}".format(
            status=program.get("affiliate_program_status", "UNKNOWN"),
            url=program.get("affiliate_program_url") or "UNKNOWN",
            commission=(
                f"{program.get('commission_value')}%"
                if program.get("commission_type") == "PERCENTAGE" and program.get("commission_value") is not None
                else program.get("commission_value") or "UNKNOWN"
            ),
            cookie=(
                f"{program.get('cookie_window_days')} days"
                if program.get("cookie_window_days") is not None else "UNKNOWN"
            ),
            verification=("VERIFIED" if program.get("affiliate_program_status") == "VERIFIED" else "UNVERIFIED"),
        )
    )
    for source in program.get("verified_sources", []):
        print(
            f"      affiliate source={source.get('source_family')} | "
            f"{source.get('verification_status')} | {source.get('url')}"
        )


def _print_sources(operator: SourceReviewOperator, slug: str) -> list[dict]:
    candidates = operator.candidates(slug)
    print(f"\nSources for {slug}:")
    if not candidates:
        print(" none")
    for index, row in enumerate(candidates, 1):
        manual = " | MANUAL_OPERATOR" if row.get("provenance") == "MANUAL_OPERATOR" else ""
        print(
            f" {index}. [{row.get('status','pending')}] {row.get('family') or row.get('source_family')}"
            f"{manual} | {row.get('label')} | {row.get('url')}"
        )
    return candidates


def action_menu() -> str:
    return "A <n> approve | J <n> reject | F refresh free research | M add manual source | B back"


def dry_run(operator: SourceReviewOperator, slug: str) -> int:
    tasks = operator.tasks(include_ready=True, scope="all")
    task = next((row for row in tasks if row["slug"] == slug), None)
    print("\nSOURCE REVIEW / VERIFY RESEARCH SOURCES — READ-ONLY DRY RUN")
    if not task:
        print(f"Task not found: {slug}")
        return 1
    _print_task(task)
    _print_sources(operator, slug)
    print(action_menu())
    print("DRY RUN: no manual source was requested, validated, added, approved, or published.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Review and verify canonical research sources.")
    parser.add_argument("--dry-run", action="store_true", help="Render one task without writes or network access.")
    parser.add_argument("--slug", default="", help="Task slug for --dry-run.")
    args = parser.parse_args(argv)
    operator = SourceReviewOperator(Path(__file__).resolve().parent)
    if args.dry_run:
        if not args.slug:
            parser.error("--dry-run requires --slug")
        return dry_run(operator, args.slug)
    while True:
        tasks = operator.tasks()
        print("\nSOURCE REVIEW / VERIFY RESEARCH SOURCES")
        if not tasks:
            print("No WEBSITE tasks currently require source review.")
            return 0
        for index, row in enumerate(tasks, 1):
            print(f"\n{index}.", end="")
            _print_task(row)
        raw = input("\nChoose task number, R to return: ").strip()
        if raw.casefold() == "r":
            return 0
        if not raw.isdigit() or not 1 <= int(raw) <= len(tasks):
            continue
        task = tasks[int(raw) - 1]
        while True:
            candidates = _print_sources(operator, task["slug"])
            print(action_menu())
            action = input("Action: ").strip().split(maxsplit=1)
            if not action:
                continue
            if action[0].casefold() == "b":
                break
            if action[0].casefold() == "f":
                try:
                    result = operator.refresh(task)
                except Exception as exc:
                    print(f"[ERROR] Source refresh failed safely: {exc}")
                    print("No approval or publish state was changed. Review this task again or retry later.")
                    input("Press Enter to continue...")
                    continue
                print(
                    "Refresh complete: "
                    f"root_foundation_exportable={result.draft_exportable}; "
                    f"gates={list(result.failing_gates)}; scope=ROOT_FOUNDATION"
                )
                print(
                    "Note: this result covers the Monday/root research package only. "
                    "Menu 2 evaluates the scheduled deep-dive contract separately."
                )
                if not result.draft_exportable:
                    refreshed = next(
                        (
                            row for row in operator.tasks(include_ready=True)
                            if row.get("slug") == task.get("slug")
                        ),
                        {},
                    )
                    if result.official_source_count == 0:
                        print(
                            "Free-research next action: add and validate an official product/docs URL "
                            "with Menu S -> M, then run F again."
                        )
                    blockers = list(refreshed.get("canonical_blockers") or result.failing_gates)
                    if blockers:
                        print("Remaining root blockers: " + "; ".join(blockers))
                    actionable = []
                    for row in refreshed.get("research_tasks") or []:
                        families = ", ".join(row.get("recommended_source_families") or []) or "verified relevant evidence"
                        line = f"{row.get('section')}: {families}"
                        if line not in actionable:
                            actionable.append(line)
                    if actionable:
                        print("Evidence needed: " + " | ".join(actionable[:6]))
                break
            if action[0].casefold() == "m":
                url = input("Source URL: ").strip()
                entity_name = input("Entity/product name: ").strip()
                print("Source family/type: " + " | ".join(sorted(MANUAL_SOURCE_FAMILIES)))
                source_family = input("Source family/type: ").strip()
                result = operator.add_manual_source(
                    task,
                    url=url,
                    entity_name=entity_name,
                    source_family=source_family,
                )
                if result["added"]:
                    source = result.get("source", {})
                    print(
                        f"[PASS] Manual source added: {source.get('source_family')} | "
                        f"{source.get('canonical_entity_name')} | {source.get('canonical_url')}"
                    )
                    print(
                        f"Canonical recalculation: {result.get('recalculated')} | "
                        f"research={result.get('research_state', 'UNKNOWN')} | "
                        f"exportable={result.get('draft_exportable', False)}"
                    )
                else:
                    print(f"[REJECTED] Manual source not added: {result['reason']}")
                    print("Research eligibility and article approval were not changed.")
                break
            if action[0].casefold() in {"a", "j"} and len(action) == 2 and action[1].isdigit():
                pos = int(action[1]) - 1
                if 0 <= pos < len(candidates):
                    operator.review_source(task["slug"], str(candidates[pos].get("url") or ""), approve=action[0].casefold() == "a")
                    print("Source review recorded. Use F to refresh and recompute eligibility.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
