from __future__ import annotations

import hashlib
import json

import pytest

from modules.social.draft_workflow import SocialDraftWorkflow


def _render(payload: dict, *, data_json: str | None = None) -> str:
    # The legacy method does not use self; this avoids constructing live services.
    return SocialDraftWorkflow.render_review_dashboard_html(None, payload, data_json=data_json)


@pytest.mark.parametrize(
    ("payload", "data_json", "length", "sha256"),
    [
        ({}, None, 49951, "4e22bb44945b3a4005b64520db41f24ae8377b465c98797044f38a0ccaec02cd"),
        (
            {"batch_date": "2026-09-28", "articles": [], "title": "Cafe & <x>", "approval_blocked": True},
            None,
            50072,
            "cac9b9e6ec40d9450aa23d0830bd10d709341346b9f18bf522a8362048f76c39",
        ),
        (
            {"batch_date": "<2026&09>", "articles": [{"slug": "alpha", "approval_blocked": True}]},
            json.dumps({"fixed": "<x>& Cafe"}, ensure_ascii=False),
            50019,
            "b7cf7c066685a8aebe4273d0eb78947794a12054853655d1deb790e2b70f3eae",
        ),
    ],
)
def test_rendered_html_is_exact_and_deterministic(
    payload: dict, data_json: str | None, length: int, sha256: str
) -> None:
    first = _render(payload, data_json=data_json)
    assert first == _render(payload, data_json=data_json)
    assert len(first) == length
    assert hashlib.sha256(first.encode("utf-8")).hexdigest() == sha256
    assert "approval_blocked" in first
    assert "<!doctype html>" in first
    assert first.endswith("</html>\n")


def test_default_data_json_and_empty_override_have_same_output() -> None:
    payload = {"batch_date": "2026-09-28", "articles": []}
    assert _render(payload, data_json="") == _render(payload)


def test_non_mapping_payload_preserves_exception() -> None:
    with pytest.raises(AttributeError):
        SocialDraftWorkflow.render_review_dashboard_html(None, None)
