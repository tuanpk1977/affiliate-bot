from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, UTC
from pathlib import Path
from typing import Any

from modules.daily_editorial_workflow import DailyEditorialWorkflow
from modules.publish_gate import PublishGate


RELEASE_STATE_NEEDS_HUMAN_REVIEW = "NEEDS_HUMAN_REVIEW"
RELEASE_STATE_READY_FOR_PUBLISH = "READY_FOR_PUBLISH"
RELEASE_STATE_PUBLISHING = "PUBLISHING"
RELEASE_STATE_SITE_GENERATED = "SITE_GENERATED"
RELEASE_STATE_DEPLOYING = "DEPLOYING"
RELEASE_STATE_DEPLOYED = "DEPLOYED"
RELEASE_STATE_WEBSITE_VERIFIED = "WEBSITE_VERIFIED"

RELEASE_STATE_PUBLISH_FAILED = "PUBLISH_FAILED"
RELEASE_STATE_DEPLOY_FAILED = "DEPLOY_FAILED"
RELEASE_STATE_VERIFY_FAILED = "VERIFY_FAILED"

TERMINAL_SUCCESS_STATES = {
    RELEASE_STATE_WEBSITE_VERIFIED,
}
TERMINAL_FAILURE_STATES = {
    RELEASE_STATE_PUBLISH_FAILED,
    RELEASE_STATE_DEPLOY_FAILED,
    RELEASE_STATE_VERIFY_FAILED,
}
RELEASE_STATES = {
    RELEASE_STATE_NEEDS_HUMAN_REVIEW,
    RELEASE_STATE_READY_FOR_PUBLISH,
    RELEASE_STATE_PUBLISHING,
    RELEASE_STATE_SITE_GENERATED,
    RELEASE_STATE_DEPLOYING,
    RELEASE_STATE_DEPLOYED,
    RELEASE_STATE_WEBSITE_VERIFIED,
    RELEASE_STATE_PUBLISH_FAILED,
    RELEASE_STATE_DEPLOY_FAILED,
    RELEASE_STATE_VERIFY_FAILED,
}


@dataclass
class WebsiteReleaseResult:
    slug: str
    task_id: str = ""
    release_state: str = RELEASE_STATE_NEEDS_HUMAN_REVIEW
    human_approval_state: str = ""
    approval_binding_status: str = ""
    publish_gate_state: str = ""
    published_state: str = ""
    deployment_state: str = ""
    verification_state: str = ""
    failure_stage: str = ""
    failure_reason: str = ""
    published_count: int = 0
    skipped_count: int = 0
    live_url: str = ""
    live_http_status: int | None = None
    live_check_status: str = ""
    source_binding_checks: list[dict[str, Any]] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "website_release_orchestrator_v1",
            "slug": self.slug,
            "task_id": self.task_id,
            "release_state": self.release_state,
            "human_approval_state": self.human_approval_state,
            "approval_binding_status": self.approval_binding_status,
            "publish_gate_state": self.publish_gate_state,
            "published_state": self.published_state,
            "deployment_state": self.deployment_state,
            "verification_state": self.verification_state,
            "failure_stage": self.failure_stage,
            "failure_reason": self.failure_reason,
            "published_count": self.published_count,
            "skipped_count": self.skipped_count,
            "live_url": self.live_url,
            "live_http_status": self.live_http_status,
            "live_check_status": self.live_check_status,
            "source_binding_checks": self.source_binding_checks,
            "blockers": self.blockers,
            "warnings": self.warnings,
            "metadata": self.metadata,
            "success": self.release_state in TERMINAL_SUCCESS_STATES,
            "failure": self.release_state in TERMINAL_FAILURE_STATES,
            "terminal": self.release_state in TERMINAL_SUCCESS_STATES | TERMINAL_FAILURE_STATES,
        }


class WebsiteReleaseOrchestrator:
    def __init__(
        self,
        *,
        root: Path,
        data_dir: Path,
        site_output_dir: Path,
        upload_root: Path,
        review_root: Path,
        workflow: DailyEditorialWorkflow | None = None,
    ) -> None:
        self.root = Path(root)
        self.data_dir = Path(data_dir)
        self.site_output_dir = Path(site_output_dir)
        self.upload_root = Path(upload_root)
        self.review_root = Path(review_root)
        self._workflow = workflow

    def _get_workflow(self) -> DailyEditorialWorkflow:
        if self._workflow is None:
            self._workflow = DailyEditorialWorkflow(
                root=self.root,
                data_dir=self.data_dir,
                site_output_dir=self.site_output_dir,
            )
        return self._workflow

    def release_article(self, *, slug: str, validation_mode: str = "smart") -> WebsiteReleaseResult:
        now = datetime.now(UTC).isoformat()
        result = WebsiteReleaseResult(slug=slug)

        try:
            workflow = self._get_workflow()
            preflight = workflow.exact_slug_preflight(slug=slug, validation_mode=validation_mode)
        except Exception as exc:
            result.release_state = RELEASE_STATE_PUBLISH_FAILED
            result.failure_stage = "preflight"
            result.failure_reason = str(exc)
            result.blockers.append(f"preflight:{exc}")
            return result

        result.task_id = str(preflight.get("topic", {}).get("task_id") or "")
        result.human_approval_state = str(preflight.get("approved_by") or "").strip() or "missing"
        result.approval_binding_status = str(preflight.get("approval_binding_status") or "")
        result.publish_gate_state = str(preflight.get("publish_gate") or "")
        result.blockers.extend(str(item) for item in preflight.get("blockers", []))
        result.warnings.extend(str(item) for item in preflight.get("warnings", []))
        result.metadata["preflight"] = preflight

        approval_blockers = [str(item) for item in preflight.get("blockers", []) if "approval" in str(item).lower()]
        if str(result.human_approval_state).casefold() in {"", "missing", "system", "system_optional", "auto", "automation"}:
            result.release_state = RELEASE_STATE_NEEDS_HUMAN_REVIEW
            result.failure_stage = "human_approval_gate"
            result.failure_reason = "current human approval is missing or not a valid human operator"
            result.blockers.append("human approval missing")
            return result

        if preflight.get("blockers"):
            result.release_state = RELEASE_STATE_PUBLISH_FAILED
            result.failure_stage = "preflight"
            result.failure_reason = "; ".join(result.blockers[:5])
            return result

        if str(result.approval_binding_status).upper() != "MATCHED":
            result.release_state = RELEASE_STATE_PUBLISH_FAILED
            result.failure_stage = "approval_binding_gate"
            result.failure_reason = f"approval binding mismatch: {result.approval_binding_status}"
            result.blockers.append("approval binding mismatch")
            return result

        if str(result.publish_gate_state).upper() not in {"READY_FOR_PUBLISH", "READY FOR PUBLISH"}:
            result.release_state = RELEASE_STATE_PUBLISH_FAILED
            result.failure_stage = "publish_gate"
            result.failure_reason = f"publish gate is not READY_FOR_PUBLISH: {result.publish_gate_state}"
            result.blockers.append("publish gate not ready")
            return result

        result.release_state = RELEASE_STATE_PUBLISHING
        try:
            publish_result = workflow.publish_exact_slug(slug=slug, validation_mode=validation_mode)
        except Exception as exc:
            result.release_state = RELEASE_STATE_PUBLISH_FAILED
            result.failure_stage = "publish"
            result.failure_reason = str(exc)
            result.blockers.append(f"publish:{exc}")
            return result

        result.published_count = int(publish_result.get("published_count") or 0)
        result.skipped_count = int(publish_result.get("skipped_count") or 0)
        result.source_binding_checks = list(publish_result.get("source_binding_checks") or [])
        result.metadata["publish"] = publish_result

        if result.published_count == 0:
            result.release_state = RELEASE_STATE_PUBLISH_FAILED
            result.failure_stage = "publish_validation"
            result.failure_reason = "no publishable articles passed validation"
            result.blockers.append("no publishable articles passed validation")
            return result

        valid_published = list(publish_result.get("published") or [])
        result.live_url = str((valid_published[0].get("url") or "") if valid_published else "")
        post_push = publish_result.get("post_push_live_check") or {}
        result.live_check_status = str(post_push.get("status") or "")
        result.live_http_status = None
        if post_push.get("items"):
            first = next(iter(post_push["items"]), {})
            result.live_http_status = first.get("http_status") if isinstance(first, dict) else None
        result.metadata["post_push_live_check"] = post_push

        if str(post_push.get("status") or "") == "live_ok":
            result.release_state = RELEASE_STATE_WEBSITE_VERIFIED
            result.verification_state = "VERIFIED"
            result.deployment_state = "DEPLOYED"
            result.published_state = "LIVE"
        else:
            result.release_state = RELEASE_STATE_VERIFY_FAILED
            result.failure_stage = "verification"
            result.failure_reason = str(post_push.get("message") or "post-push live check did not return live_ok")
            result.deployment_state = "DEPLOYED"
            result.published_state = "PUSHED"
            result.verification_state = str(post_push.get("status") or "UNKNOWN")
            result.blockers.append("post-push live verification failed")

        return result

    @staticmethod
    def current_release_state_for_slug(*, slug: str, data_dir: Path) -> str | None:
        publish_rows = [
            row for row in _read_json(Path(data_dir) / "publish_queue.json", [])
            if isinstance(row, dict) and str(row.get("slug") or "") == slug
        ]
        if not publish_rows:
            return None
        row = publish_rows[0]
        status = str(row.get("status") or row.get("publish_queue_status") or "").upper()
        deployment_state = str(row.get("deployment_state") or row.get("deployment_status") or "").upper()
        post_push_status = str(row.get("post_push_live_status") or "").upper()
        if post_push_status == "LIVE_OK" or status == "LIVE":
            return RELEASE_STATE_WEBSITE_VERIFIED
        if post_push_status and post_push_status not in {"NOT_RUN", ""}:
            return RELEASE_STATE_VERIFY_FAILED
        if status in {"PUSHED", "AWAITING_PUSH"}:
            return RELEASE_STATE_DEPLOYED
        if status in {"COMMITTED_LOCAL", "PUBLISHED_LOCAL"}:
            return RELEASE_STATE_SITE_GENERATED
        if status == "APPROVED_FOR_PUBLISH":
            return RELEASE_STATE_READY_FOR_PUBLISH
        if status in {"BLOCKED", "REVISION_REQUESTED", "REJECTED"}:
            return RELEASE_STATE_PUBLISH_FAILED
        return None


def _read_json(path: Path, default: Any) -> Any:
    if not path.is_file():
        return default
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError):
        return default
