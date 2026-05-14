from __future__ import annotations

import json
import sys
import uuid
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def sample_event() -> dict[str, str]:
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "session_id": f"test_session_{uuid.uuid4()}",
        "click_id": f"test_click_{uuid.uuid4()}",
        "tool_slug": "cursor",
        "tool_name": "Cursor",
        "source_page": "/cursor/",
        "source_page_type": "review",
        "cta_label": "official_site",
        "target_url": "https://cursor.com",
        "referrer": "manual_webhook_test",
        "event_type": "official_click",
        "page_load_seconds": "8.5",
        "user_agent_hint": "manual-python-webhook-test",
        "is_suspicious": "false",
        "suspicious_reason": "",
        "click_quality_score": "95",
    }


def post_event(webhook_url: str, event: dict[str, str]) -> tuple[int, str]:
    if webhook_url.upper() in {"MOCK", "MOCK://SUCCESS"}:
        return 200, json.dumps({"ok": True, "mock": True, "saved": True})
    body = json.dumps(event).encode("utf-8")
    request = Request(
        webhook_url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=30) as response:
        return response.status, response.read().decode("utf-8", errors="replace")


def main() -> int:
    webhook_url = sys.argv[1].strip() if len(sys.argv) > 1 else input("Dan Google Apps Script Web App URL: ").strip()
    if not webhook_url:
        print("ERROR: Ban chua nhap Web App URL.")
        return 1
    if "script.google.com" not in webhook_url or not webhook_url.endswith("/exec"):
        print("WARNING: URL khong giong Google Apps Script Web App URL. URL thuong ket thuc bang /exec.")

    event = sample_event()
    try:
        status, text = post_event(webhook_url, event)
    except HTTPError as exc:
        print(f"ERROR: Webhook tra ve HTTP {exc.code}")
        print(exc.read().decode("utf-8", errors="replace"))
        return 1
    except URLError as exc:
        print(f"ERROR: Khong ket noi duoc webhook: {exc}")
        return 1
    except Exception as exc:
        print(f"ERROR: Test webhook that bai: {exc}")
        return 1

    success = 200 <= status < 300
    print(f"HTTP status: {status}")
    print(f"Response body: {text[:1000]}")
    if success:
        print("SUCCESS: Da gui payload mau tool_slug=cursor.")
        if webhook_url.upper() not in {"MOCK", "MOCK://SUCCESS"}:
            print("Hay mo Google Sheet va kiem tra dong moi co tool_slug = cursor.")
        return 0
    print("FAIL: Webhook khong tra ve HTTP 2xx.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
