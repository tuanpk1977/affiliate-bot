from __future__ import annotations

import csv
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from config import settings


TELEGRAM_LOG_COLUMNS = ["time", "post_id", "status", "error", "telegram_message_id"]
MAX_TELEGRAM_TEXT = 3900
MAX_RETRIES = 2


def telegram_log_path() -> Path:
    return settings.data_dir / "telegram_publish_log.csv"


def ensure_telegram_log() -> None:
    path = telegram_log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        with path.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=TELEGRAM_LOG_COLUMNS)
            writer.writeheader()


def write_telegram_log(post_id: str, status: str, error: str = "", telegram_message_id: str = "") -> None:
    ensure_telegram_log()
    with telegram_log_path().open("a", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=TELEGRAM_LOG_COLUMNS)
        writer.writerow({
            "time": datetime.now().isoformat(timespec="seconds"),
            "post_id": post_id,
            "status": status,
            "error": error,
            "telegram_message_id": telegram_message_id,
        })


def telegram_credentials() -> tuple[str, str]:
    load_dotenv()
    return os.getenv("TELEGRAM_BOT_TOKEN", "").strip(), os.getenv("TELEGRAM_CHAT_ID", "").strip()


def validate_telegram_config() -> tuple[bool, str]:
    token, chat_id = telegram_credentials()
    if not token:
        return False, "missing TELEGRAM_BOT_TOKEN"
    if not chat_id:
        return False, "missing TELEGRAM_CHAT_ID"
    if ":" not in token:
        return False, "invalid TELEGRAM_BOT_TOKEN format"
    return True, "telegram config ok"


def escape_markdown(text: str) -> str:
    # Telegram MarkdownV2 reserved characters.
    reserved = r"_*[]()~`>#+-=|{}.!"
    result = []
    for char in str(text or ""):
        result.append("\\" + char if char in reserved else char)
    return "".join(result)


def split_long_text(text: str, max_chars: int = MAX_TELEGRAM_TEXT) -> list[str]:
    value = str(text or "").strip()
    if not value:
        return []
    if len(value) <= max_chars:
        return [value]
    parts: list[str] = []
    current = ""
    for paragraph in value.splitlines():
        candidate = f"{current}\n{paragraph}".strip() if current else paragraph
        if len(candidate) <= max_chars:
            current = candidate
            continue
        if current:
            parts.append(current)
        while len(paragraph) > max_chars:
            cut = paragraph.rfind(" ", 0, max_chars)
            if cut < max_chars * 0.5:
                cut = max_chars
            parts.append(paragraph[:cut].strip())
            paragraph = paragraph[cut:].strip()
        current = paragraph
    if current:
        parts.append(current)
    return parts


def send_message(text: str, post_id: str = "manual_test", parse_mode: str = "MarkdownV2") -> dict[str, object]:
    ok, message = validate_telegram_config()
    if not ok:
        write_telegram_log(post_id, "failed", message)
        return {"ok": False, "error": message, "message_ids": []}
    if not str(text or "").strip():
        error = "empty Telegram message text"
        write_telegram_log(post_id, "failed", error)
        return {"ok": False, "error": error, "message_ids": []}

    token, chat_id = telegram_credentials()
    message_ids: list[str] = []
    for part in split_long_text(text):
        payload_text = escape_markdown(part) if parse_mode == "MarkdownV2" else part
        payload = {
            "chat_id": chat_id,
            "text": payload_text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": False,
        }
        result = _telegram_request(token, "sendMessage", payload, post_id)
        if not result.get("ok"):
            return {"ok": False, "error": result.get("error", "telegram_send_failed"), "message_ids": message_ids}
        message_id = str(result.get("message_id", ""))
        if message_id:
            message_ids.append(message_id)
    write_telegram_log(post_id, "published", "", "|".join(message_ids))
    return {"ok": True, "error": "", "message_ids": message_ids}


def send_photo_post(image_path: str | Path, caption: str, post_id: str = "photo_post") -> dict[str, object]:
    ok, message = validate_telegram_config()
    if not ok:
        write_telegram_log(post_id, "failed", message)
        return {"ok": False, "error": message, "message_ids": []}
    path = Path(image_path)
    if not path.exists():
        return send_message(caption, post_id=post_id)
    if not str(caption or "").strip():
        error = "empty Telegram photo caption"
        write_telegram_log(post_id, "failed", error)
        return {"ok": False, "error": error, "message_ids": []}

    token, chat_id = telegram_credentials()
    boundary = "----MSSmileTelegramBoundary"
    caption_text = escape_markdown(caption[:1000])
    body = _multipart_body(boundary, {
        "chat_id": chat_id,
        "caption": caption_text,
        "parse_mode": "MarkdownV2",
    }, "photo", path)
    headers = {"Content-Type": f"multipart/form-data; boundary={boundary}"}
    result = _telegram_request(token, "sendPhoto", body, post_id, headers=headers, raw_body=True)
    if not result.get("ok"):
        return {"ok": False, "error": result.get("error", "telegram_photo_failed"), "message_ids": []}
    message_id = str(result.get("message_id", ""))
    write_telegram_log(post_id, "published", "", message_id)
    return {"ok": True, "error": "", "message_ids": [message_id] if message_id else []}


def send_post(post_object: dict[str, object]) -> dict[str, object]:
    post_id = str(post_object.get("post_id", "") or post_object.get("queue_id", "") or "telegram_post")
    text = str(post_object.get("content", "") or post_object.get("post_body", "") or post_object.get("title", ""))
    image_path = str(post_object.get("image_path", "") or "")
    if image_path:
        return send_photo_post(image_path, text, post_id=post_id)
    return send_message(text, post_id=post_id)


def _telegram_request(
    token: str,
    method: str,
    payload: dict[str, object] | bytes,
    post_id: str,
    headers: dict[str, str] | None = None,
    raw_body: bool = False,
) -> dict[str, object]:
    url = f"https://api.telegram.org/bot{token}/{method}"
    if raw_body:
        data = payload if isinstance(payload, bytes) else bytes(payload)
        request_headers = headers or {}
    else:
        data = json.dumps(payload).encode("utf-8")
        request_headers = {"Content-Type": "application/json"}
    for attempt in range(MAX_RETRIES + 1):
        request = urllib.request.Request(url, data=data, headers=request_headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=25) as response:
                body = json.loads(response.read().decode("utf-8", errors="ignore"))
                if body.get("ok"):
                    result = body.get("result", {})
                    return {"ok": True, "message_id": result.get("message_id", "")}
                error = str(body.get("description", "telegram_api_error"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            error = str(exc)
        if attempt < MAX_RETRIES:
            time.sleep(2 * (attempt + 1))
    write_telegram_log(post_id, "failed", error)
    return {"ok": False, "error": error}


def _multipart_body(boundary: str, fields: dict[str, str], file_field: str, file_path: Path) -> bytes:
    lines: list[bytes] = []
    for name, value in fields.items():
        lines.extend([
            f"--{boundary}".encode(),
            f'Content-Disposition: form-data; name="{name}"'.encode(),
            b"",
            str(value).encode("utf-8"),
        ])
    file_bytes = file_path.read_bytes()
    filename = file_path.name
    lines.extend([
        f"--{boundary}".encode(),
        f'Content-Disposition: form-data; name="{file_field}"; filename="{filename}"'.encode(),
        b"Content-Type: application/octet-stream",
        b"",
        file_bytes,
        f"--{boundary}--".encode(),
        b"",
    ])
    return b"\r\n".join(lines)
