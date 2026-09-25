from __future__ import annotations

import html
import re
from typing import Any

from modules.revision_binding import approval_binding_status, binding_for_content


DEPLOYMENT_STATES = {
    "publishing": ("PUBLISHING", "Publishing"),
    "published_local": ("PUBLISHED_LOCAL", "Published Local"),
    "committed_local": ("COMMITTED", "Committed"),
    "awaiting_push": ("COMMITTED", "Committed"),
    "push_blocked": ("COMMITTED", "Committed"),
    "pushed": ("PUSHED", "Pushed"),
    "deploy_pending": ("DEPLOY_PENDING", "Deploy Pending"),
    "live": ("LIVE_200", "Live 200"),
    "published": ("LIVE_200", "Live 200"),
}


def has_publish_cta_block(text: str) -> bool:
    """Recognize a real actionable CTA, independent of one renderer class."""
    if re.search(r">\s*(?:Visit official website|Check current pricing)\s*</a>", text, flags=re.I):
        return True
    if re.search(
        r"<a\b(?=[^>]*\bhref=['\"][^'\"]+['\"])(?=[^>]*\bclass=['\"][^'\"]*\bcta-button\b)[^>]*>",
        text,
        flags=re.I,
    ):
        return True
    section_pattern = re.compile(
        r"<h2\b[^>]*>\s*(?:Final recommendation(?: and verification checklist)?|Final strategic recommendation and next steps|Next steps?|What to do next|Continue the same-root series)\s*</h2>(?P<body>[\s\S]*?)(?=<h2\b|</article>|</main>|$)",
        flags=re.I,
    )
    for section in section_pattern.finditer(text):
        for anchor in re.findall(
            r"<a\b[^>]*\bhref=['\"][^'\"]+['\"][^>]*>([\s\S]*?)</a>",
            section.group("body"),
            flags=re.I,
        ):
            label = " ".join(re.sub(r"<[^>]+>", " ", html.unescape(anchor)).split())
            if re.search(r"\b(?:read|compare|check|visit|explore|learn|get|start|review|see|try|download)\b", label, flags=re.I):
                return True
    return False


def _quality_state(
    review: dict[str, Any],
    publish: dict[str, Any],
    *,
    revision_id: str,
    content_hash: str,
) -> str:
    if not review:
        return "MISSING"
    reviewed_revision = str(review.get("reviewed_revision_id") or "")
    reviewed_hash = str(review.get("reviewed_content_hash") or "").casefold()
    if not reviewed_revision or not reviewed_hash:
        return "LEGACY_UNBOUND"
    if reviewed_revision != revision_id or reviewed_hash != content_hash.casefold():
        return "STALE"
    quality_status = str(review.get("quality_review_status") or review.get("status") or "").lower()
    quality_state = str(review.get("quality_review_state") or review.get("review_state") or "").upper()
    if (
        quality_status in {"needs_revision", "rejected", "error", "review_error", "not_run"}
        or quality_state == "BLOCKED"
        or bool(review.get("hard_blockers"))
        or not bool(review.get("publishable", False))
    ):
        return "FAILED"
    return "PASS_MATCHED"


def resolve_article_operational_state(
    *,
    slug: str,
    html_text: str,
    review: dict[str, Any] | None,
    approval: dict[str, Any] | None,
    publish: dict[str, Any] | None,
    structure_errors: list[str] | None = None,
    live_http_status: int | None = None,
) -> dict[str, Any]:
    """Resolve the one canonical operational state for one exact revision.

    Persisted queues are evidence/projections. Eligibility is derived here from
    the current production bytes plus revision-bound quality and human review.
    """
    review = review or {}
    approval = approval or {}
    publish = publish or {}
    blockers: list[dict[str, str]] = []
    warnings = [str(item) for item in list(publish.get("warnings") or []) if str(item).strip()]
    if not html_text:
        deployment_status = str(publish.get("status") or "").lower()
        missing_draft_blockers = [{"code": "DRAFT_MISSING", "reason": "production draft is missing"}]
        for reason in list(publish.get("hard_blockers") or publish.get("failures") or []):
            normalized = str(reason).strip()
            if normalized:
                missing_draft_blockers.append({"code": "PUBLISH_GATE_BLOCKER", "reason": normalized})
        for error in structure_errors or []:
            missing_draft_blockers.append({"code": "PRE_PUBLISH_STRUCTURE", "reason": str(error)})
        if live_http_status == 200:
            state, label = "LIVE_200", "Live 200"
        elif deployment_status in DEPLOYMENT_STATES:
            state, label = DEPLOYMENT_STATES[deployment_status]
        elif deployment_status == "blocked" or len(missing_draft_blockers) > 1:
            state, label = "PUBLISH_BLOCKED", "Publish Blocked"
        else:
            state, label = "WAITING_FOR_DRAFT", "Waiting for Draft"
        return {
            "slug": slug,
            "state": state,
            "state_label": label,
            "revision_id": "",
            "content_hash": "",
            "quality_review": "MISSING",
            "cta_validation": "FAIL",
            "structure_validation": {"status": "FAILED", "cta": "FAIL", "errors": [row["reason"] for row in missing_draft_blockers]},
            "human_approval_binding": "MISSING",
            "editorial_state": "Waiting for Draft",
            "publish_gate": label,
            "deployment_state": label if state in {value[0] for value in DEPLOYMENT_STATES.values()} or state == "LIVE_200" else "Not Started",
            "publish_eligible": False,
            "blockers": missing_draft_blockers if state in {"WAITING_FOR_DRAFT", "PUBLISH_BLOCKED"} else [],
            "warnings": warnings,
        }

    binding = binding_for_content(html_text)
    revision_id = str(binding["revision_id"])
    content_hash = str(binding["content_hash"])
    quality = _quality_state(
        review,
        publish,
        revision_id=revision_id,
        content_hash=content_hash,
    )
    raw_approval_binding = approval_binding_status(
        approval,
        current_content_hash=content_hash,
        current_revision_id=revision_id,
    )
    if str(approval.get("status") or "") != "human_approved":
        approval_binding = "MISSING"
    elif raw_approval_binding == "MATCHED":
        approval_binding = "MATCHED"
    else:
        approval_binding = "STALE"

    cta_pass = has_publish_cta_block(html_text)
    if quality != "PASS_MATCHED":
        blockers.append({"code": f"QUALITY_REVIEW_{quality}", "reason": f"quality review is {quality.lower()} for current revision"})
    if not cta_pass:
        blockers.append({"code": "CTA_MISSING", "reason": "production draft is missing CTA block"})
    for error in structure_errors or []:
        if "missing CTA block" in error:
            continue
        blockers.append({"code": "PRE_PUBLISH_STRUCTURE", "reason": str(error)})

    gate_revision = str(publish.get("current_revision_id") or "")
    gate_hash = str(publish.get("current_content_hash") or "").casefold()
    gate_bound = bool(gate_revision and gate_hash)
    gate_current = gate_bound and gate_revision == revision_id and gate_hash == content_hash.casefold()
    deployment_status = str(publish.get("status") or "").lower()
    # The publish queue is a projection, but an exact-revision publish gate is
    # still required before an article can be eligible. Stale projections fail
    # closed and must be refreshed from the canonical evidence above.
    if not gate_bound and deployment_status not in DEPLOYMENT_STATES:
        blockers.append({"code": "PUBLISH_GATE_MISSING", "reason": "publish gate validation is not bound to the current revision"})
    elif gate_bound and not gate_current and deployment_status not in DEPLOYMENT_STATES:
        blockers.append({"code": "PUBLISH_GATE_STALE", "reason": "publish gate validation belongs to a different revision"})
    if gate_current:
        for reason in list(publish.get("hard_blockers") or publish.get("failures") or []):
            normalized = str(reason).strip()
            if not normalized:
                continue
            # Quality and CTA are recomputed above from canonical evidence.
            if "AI review" in normalized or "missing CTA block" in normalized or "human approval" in normalized.lower():
                continue
            blockers.append({"code": "PUBLISH_GATE_BLOCKER", "reason": normalized})

    if live_http_status == 200:
        state, label = "LIVE_200", "Live 200"
    elif deployment_status in DEPLOYMENT_STATES:
        state, label = DEPLOYMENT_STATES[deployment_status]
    elif blockers:
        state, label = "PUBLISH_BLOCKED", "Publish Blocked"
    elif approval_binding != "MATCHED":
        state, label = "NEEDS_REVIEW", "Needs Review"
    else:
        state, label = "READY_FOR_PUBLISH", "Ready for Publish"

    deployment_label = (
        "Live 200"
        if live_http_status == 200
        else DEPLOYMENT_STATES.get(deployment_status, ("", "Not Started"))[1]
    )
    editorial_state = "Human Approved" if approval_binding == "MATCHED" else "Needs Review"

    return {
        "slug": slug,
        "state": state,
        "state_label": label,
        "revision_id": revision_id,
        "content_hash": content_hash,
        "quality_review": quality,
        "cta_validation": "PASS" if cta_pass else "FAIL",
        "structure_validation": {
            "status": "PASS" if cta_pass and not structure_errors else "FAILED",
            "cta": "PASS" if cta_pass else "FAIL",
            "errors": [str(item) for item in structure_errors or []] + ([] if cta_pass else ["production draft is missing CTA block"]),
        },
        "human_approval_binding": approval_binding,
        "editorial_state": editorial_state,
        "publish_gate": label,
        "deployment_state": deployment_label,
        "publish_gate_binding": "MATCHED" if gate_current else ("MISSING" if not gate_bound else "STALE"),
        "publish_eligible": state == "READY_FOR_PUBLISH",
        "blockers": blockers,
        "warnings": warnings,
    }
