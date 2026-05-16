from __future__ import annotations

from typing import Any


def _dry_run(platform: str, payload: dict[str, Any], config: dict[str, Any] | None = None) -> dict[str, Any]:
    config = config or {}
    if not bool(config.get("auto_post_enabled", False)):
        return {
            "platform": platform,
            "posted": False,
            "status": "dry_run",
            "message": "auto_post_enabled=false; content is approval/copy-ready only.",
            "payload_id": payload.get("id", ""),
        }
    return {
        "platform": platform,
        "posted": False,
        "status": "not_implemented",
        "message": "Real API publishing is intentionally disabled in this local-safe connector.",
        "payload_id": payload.get("id", ""),
    }


def prepare_facebook_post(payload: dict[str, Any]) -> dict[str, Any]:
    return {"platform": "facebook", "body": payload.get("content", ""), "url": payload.get("cta_url", "")}


def prepare_linkedin_post(payload: dict[str, Any]) -> dict[str, Any]:
    return {"platform": "linkedin", "body": payload.get("content", ""), "url": payload.get("cta_url", "")}


def prepare_twitter_post(payload: dict[str, Any]) -> dict[str, Any]:
    return {"platform": "twitter", "body": payload.get("content", ""), "url": payload.get("cta_url", "")}


def prepare_zalo_post(payload: dict[str, Any]) -> dict[str, Any]:
    return {"platform": "zalo", "body": payload.get("content", ""), "url": payload.get("cta_url", "")}


def dry_run_post(platform: str, payload: dict[str, Any], config: dict[str, Any] | None = None) -> dict[str, Any]:
    return _dry_run(platform, payload, config)
