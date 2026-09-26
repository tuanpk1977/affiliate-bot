from __future__ import annotations

from pathlib import Path
from typing import Any, Callable


class ExternalWriterBatchPreflight:
    """Project active and advanced Writer batches for export review."""

    def __init__(
        self,
        *,
        root: Path,
        queue: Any,
        partition_research_ready: Callable[..., tuple[list[dict[str, Any]], list[dict[str, Any]]]],
        read_json: Callable[[Path, Any], Any],
        text: Callable[[Any], str],
        relative: Callable[[Path, Path], str],
        resolve_research_artifacts: Callable[..., Any],
    ) -> None:
        self.root = root
        self.queue = queue
        self.partition_research_ready = partition_research_ready
        self.read_json = read_json
        self.text = text
        self.relative = relative
        self.resolve_research_artifacts = resolve_research_artifacts

    def active_batches(self) -> list[dict[str, Any]]:
        """Return the newest active batch independently for each task type."""
        rows = self.queue.list_tasks(
            statuses={"PENDING", "EXPORTED", "REVISION_REQUESTED", "FAILED_IMPORT"}
        )
        grouped: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            grouped.setdefault(self.text(row.get("task_type")), []).append(row)
        result: list[dict[str, Any]] = []
        for task_type, task_rows in sorted(grouped.items()):
            batch_date = max(self.text(row.get("batch_date")) for row in task_rows)
            selected = [row for row in task_rows if self.text(row.get("batch_date")) == batch_date]
            ready, held = self.partition_research_ready(selected, task_type)
            result.append(
                {
                    "task_type": task_type,
                    "batch_date": batch_date,
                    "task_count": len(selected),
                    "eligible": len(ready),
                    "held": len(held),
                    "tasks": self._preflight_task_rows(selected, ready, held),
                }
            )
        advanced = self._advanced_editorial_preflight("latest")
        if advanced and not any(
            row["task_type"] == "WEBSITE_ADVANCED"
            and row["batch_date"] == advanced["batch_date"]
            for row in result
        ):
            result.append(advanced)
        return result

    def _advanced_editorial_preflight(self, requested_date: str) -> dict[str, Any] | None:
        try:
            batch_date = self.queue._resolve_website_date(requested_date)
        except (RuntimeError, FileNotFoundError):
            return None
        queue_path = self.root / "data" / "editorial_queue" / batch_date / "topics.json"
        payload = self.read_json(queue_path, {})
        if not isinstance(payload, dict) or self.text(payload.get("mode")) != "advanced":
            return None
        tasks: list[dict[str, Any]] = []
        for index, item in enumerate(payload.get("topics") or [], start=1):
            if not isinstance(item, dict):
                continue
            slug = self.text(item.get("slug"))
            if not slug:
                continue
            task_id = self.text(item.get("task_id")) or f"website-advanced-{batch_date}-{slug}"
            resolution = self.resolve_research_artifacts(
                self.root,
                task_id=task_id,
                slug=slug,
                batch_date=batch_date,
            )
            report = self.read_json(resolution.enrichment_report_file, {})
            blockers = [
                *resolution.missing_files,
                *resolution.legacy_reasons,
                *(report.get("blockers") or [] if isinstance(report, dict) else []),
            ]
            tasks.append(
                {
                    "task_id": task_id,
                    "article_slug": slug,
                    "batch_date": batch_date,
                    "root_topic_id": self.text(item.get("root_topic_id")),
                    "sequence": item.get("sequence_number") or item.get("sequence") or index,
                    "daily_angle": self.text(item.get("daily_angle")),
                    "research_artifact_dir": self.relative(
                        self.root, resolution.canonical_dir
                    ),
                    "research_state": resolution.status or "BLOCKED_RESEARCH",
                    "article_ready": resolution.article_ready,
                    "research_level": resolution.research_level,
                    "draft_exportable": resolution.draft_exportable,
                    "comparison_status": resolution.comparison_status,
                    "outstanding_research_tasks": resolution.outstanding_research_tasks,
                    "known_weak_sections": list(resolution.weak_sections),
                    "estimated_publish_readiness": resolution.estimated_publish_readiness,
                    "paragraphs": resolution.paragraph_count,
                    "claims": resolution.claim_count,
                    "coverage_score": resolution.coverage_score,
                    "angle_profile": resolution.angle_profile,
                    "required_entities": resolution.required_entity_count,
                    "resolved_entities": resolution.resolved_entity_count,
                    "entity_coverage_score": resolution.entity_coverage_score,
                    "candidate_claims": resolution.candidate_claim_count,
                    "rejected_claims": resolution.rejected_claim_count,
                    "eligible": resolution.draft_exportable,
                    "reason": "; ".join(
                        dict.fromkeys(
                            str(reason) for reason in blockers if str(reason).strip()
                        )
                    )
                    or (
                        "Research evidence is ready."
                        if resolution.draft_exportable
                        else "Research evidence is not safe for a first draft."
                    ),
                }
            )
        if not tasks:
            return None
        result = {
            "task_type": "WEBSITE_ADVANCED",
            "batch_date": batch_date,
            "task_count": len(tasks),
            "eligible": sum(bool(row["eligible"]) for row in tasks),
            "held": sum(not bool(row["eligible"]) for row in tasks),
            "tasks": tasks,
            "source": self.relative(self.root, queue_path),
        }
        return result

    def _preflight_task_rows(
        self,
        tasks: list[dict[str, Any]],
        ready: list[dict[str, Any]],
        held: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        ready_ids = {self.text(row.get("task_id")) for row in ready}
        held_by_id = {self.text(row.get("task_id")): row for row in held}
        result: list[dict[str, Any]] = []
        for index, task in enumerate(tasks, start=1):
            task_id = self.text(task.get("task_id"))
            slug = self.text(task.get("article_slug"))
            hold = held_by_id.get(task_id, {})
            if self.text(task.get("social_mode")) == "SOURCE_BASED_SOCIAL":
                result.append(
                    {
                        "task_id": task_id,
                        "article_slug": slug,
                        "batch_date": self.text(task.get("batch_date")),
                        "root_topic_id": self.text(task.get("root_topic_id")),
                        "sequence": task.get("sequence_number") or task.get("sequence") or index,
                        "daily_angle": self.text(task.get("social_angle") or task.get("daily_angle")),
                        "content_origin": "WEBSITE_ROOT_BASED",
                        "social_mode": "SOURCE_BASED_SOCIAL",
                        "source_article_slug": self.text(task.get("source_article_slug") or slug),
                        "source_revision_id": self.text(task.get("source_revision_id")),
                        "source_content_hash": self.text(task.get("source_content_hash")),
                        "research_artifact_dir": self.text(task.get("source_evidence_reference")),
                        "research_state": "EVIDENCE_INHERITED",
                        "article_ready": True,
                        "research_level": "SOURCE_BASED_SOCIAL",
                        "draft_exportable": True,
                        "comparison_status": "NOT_APPLICABLE",
                        "outstanding_research_tasks": [],
                        "known_weak_sections": [],
                        "estimated_publish_readiness": 1.0,
                        "paragraphs": 0,
                        "claims": 0,
                        "coverage_score": 1.0,
                        "angle_profile": "platform_adaptation",
                        "required_entities": 0,
                        "resolved_entities": 0,
                        "entity_coverage_score": 1.0,
                        "candidate_claims": 0,
                        "rejected_claims": 0,
                        "eligible": task_id in ready_ids,
                        "reason": self.text(hold.get("reason")) or "Verified Website source evidence is inherited; unrelated Website research gates are not applicable.",
                    }
                )
                continue
            resolution = self.resolve_research_artifacts(
                self.root,
                task_id=task_id,
                slug=slug,
                batch_date=self.text(task.get("batch_date")),
            )
            result.append(
                {
                    "task_id": task_id,
                    "article_slug": slug,
                    "batch_date": self.text(task.get("batch_date")),
                    "root_topic_id": self.text(task.get("root_topic_id")),
                    "sequence": task.get("sequence_number") or task.get("sequence") or index,
                    "daily_angle": self.text(task.get("daily_angle")),
                    "research_artifact_dir": self.relative(
                        self.root, resolution.canonical_dir
                    ),
                    "research_state": resolution.status,
                    "article_ready": resolution.article_ready,
                    "research_level": resolution.research_level,
                    "draft_exportable": resolution.draft_exportable,
                    "comparison_status": resolution.comparison_status,
                    "outstanding_research_tasks": resolution.outstanding_research_tasks,
                    "known_weak_sections": list(resolution.weak_sections),
                    "estimated_publish_readiness": resolution.estimated_publish_readiness,
                    "paragraphs": resolution.paragraph_count,
                    "claims": resolution.claim_count,
                    "coverage_score": resolution.coverage_score,
                    "angle_profile": resolution.angle_profile,
                    "required_entities": resolution.required_entity_count,
                    "resolved_entities": resolution.resolved_entity_count,
                    "entity_coverage_score": resolution.entity_coverage_score,
                    "candidate_claims": resolution.candidate_claim_count,
                    "rejected_claims": resolution.rejected_claim_count,
                    "eligible": task_id in ready_ids,
                    "reason": self.text(hold.get("reason")) or "Research evidence is ready.",
                }
            )
        return result
