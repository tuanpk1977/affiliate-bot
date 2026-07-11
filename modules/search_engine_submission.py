from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
import json
import os
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


BING_ENDPOINT = "https://ssl.bing.com/webmaster/api.svc/json/SubmitFeed"
GOOGLE_ENDPOINT = "https://www.googleapis.com/webmasters/v3/sites/{site}/sitemaps/{feed}"
TEMPORARY_CODES = {408, 425, 429, 500, 502, 503, 504}


@dataclass
class SubmissionResult:
    engine: str
    status: str
    http_status: int = 0
    attempted: bool = False
    message: str = ""
    submitted_at: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_state(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def write_state(path: Path, state: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def append_log(path: Path, result: SubmissionResult) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(result.to_dict(), sort_keys=True) + "\n")


def already_submitted_today(state: dict[str, str], engine: str) -> bool:
    value = state.get(f"{engine}_sitemap_submitted_at", "")
    if not value:
        return False
    try:
        submitted = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return submitted.astimezone(timezone.utc).date() == datetime.now(timezone.utc).date()


def request_with_retry(
    request_factory,
    *,
    retries: int = 3,
    retry_delay: float = 3.0,
) -> tuple[int, str]:
    for attempt in range(1, max(1, retries) + 1):
        request = request_factory()
        try:
            with urlopen(request, timeout=30) as response:
                return int(response.status), response.read().decode("utf-8", errors="replace")
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            if exc.code not in TEMPORARY_CODES or attempt >= retries:
                return int(exc.code), body
        except (URLError, TimeoutError, OSError) as exc:
            if attempt >= retries:
                return 0, str(exc)
        time.sleep(retry_delay * attempt)
    return 0, "request failed"


def submit_bing_sitemap(
    site_url: str,
    sitemap_url: str,
    *,
    state_path: Path,
    log_path: Path,
    dry_run: bool = False,
) -> SubmissionResult:
    state = read_state(state_path)
    if already_submitted_today(state, "bing"):
        result = SubmissionResult(
            engine="bing",
            status="skipped_daily_limit",
            message="Bing sitemap was already submitted today.",
            submitted_at=utc_now(),
        )
        append_log(log_path, result)
        return result

    api_key = os.getenv("BING_WEBMASTER_API_KEY", "").strip()
    if not api_key:
        result = SubmissionResult(
            engine="bing",
            status="skipped_credentials_missing",
            message="Set BING_WEBMASTER_API_KEY to enable authenticated Bing sitemap submission.",
            submitted_at=utc_now(),
        )
        append_log(log_path, result)
        return result
    if dry_run:
        result = SubmissionResult(
            engine="bing",
            status="dry_run",
            message="Bing SubmitFeed request validated but not sent.",
            submitted_at=utc_now(),
        )
        append_log(log_path, result)
        return result

    endpoint = f"{BING_ENDPOINT}?apikey={quote(api_key, safe='')}"
    body = json.dumps({"siteUrl": site_url, "feedUrl": sitemap_url}).encode("utf-8")
    status, response = request_with_retry(
        lambda: Request(
            endpoint,
            data=body,
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )
    )
    ok = 200 <= status < 300
    result = SubmissionResult(
        engine="bing",
        status="submitted" if ok else "failed",
        http_status=status,
        attempted=True,
        message="Bing accepted the sitemap." if ok else f"Bing response: {response[:300]}",
        submitted_at=utc_now(),
    )
    if ok:
        state["bing_sitemap_submitted_at"] = result.submitted_at
        write_state(state_path, state)
    append_log(log_path, result)
    return result


def google_access_token() -> tuple[str, str]:
    direct = os.getenv("GOOGLE_SEARCH_CONSOLE_ACCESS_TOKEN", "").strip()
    if direct:
        return direct, "access_token"

    raw_json = os.getenv("GOOGLE_SEARCH_CONSOLE_CREDENTIALS_JSON", "").strip()
    credentials_file = os.getenv("GOOGLE_SEARCH_CONSOLE_CREDENTIALS_FILE", "").strip()
    if not raw_json and not credentials_file:
        return "", ""
    try:
        from google.auth.transport.requests import Request as GoogleAuthRequest
        from google.oauth2 import service_account
    except ImportError:
        return "", "google-auth is not installed"

    try:
        if raw_json:
            info = json.loads(raw_json)
            credentials = service_account.Credentials.from_service_account_info(
                info,
                scopes=["https://www.googleapis.com/auth/webmasters"],
            )
        else:
            credentials = service_account.Credentials.from_service_account_file(
                credentials_file,
                scopes=["https://www.googleapis.com/auth/webmasters"],
            )
        credentials.refresh(GoogleAuthRequest())
        return str(credentials.token or ""), "service_account"
    except Exception as exc:
        return "", f"credential error: {exc}"


def submit_google_sitemap(
    site_url: str,
    sitemap_url: str,
    *,
    state_path: Path,
    log_path: Path,
    dry_run: bool = False,
) -> SubmissionResult:
    state = read_state(state_path)
    if already_submitted_today(state, "google"):
        result = SubmissionResult(
            engine="google",
            status="skipped_daily_limit",
            message="Google sitemap was already submitted today.",
            submitted_at=utc_now(),
        )
        append_log(log_path, result)
        return result

    token, source = google_access_token()
    if not token:
        message = (
            "No Search Console API credentials are configured. Google will discover the updated "
            "sitemap through robots.txt and the existing Search Console registration."
        )
        if source:
            message += f" ({source})"
        result = SubmissionResult(
            engine="google",
            status="skipped_credentials_missing",
            message=message,
            submitted_at=utc_now(),
        )
        append_log(log_path, result)
        return result
    if dry_run:
        result = SubmissionResult(
            engine="google",
            status="dry_run",
            message=f"Google Search Console sitemap request validated using {source}; not sent.",
            submitted_at=utc_now(),
        )
        append_log(log_path, result)
        return result

    endpoint = GOOGLE_ENDPOINT.format(
        site=quote(site_url, safe=""),
        feed=quote(sitemap_url, safe=""),
    )
    status, response = request_with_retry(
        lambda: Request(
            endpoint,
            data=b"",
            headers={"Authorization": f"Bearer {token}", "Content-Length": "0"},
            method="PUT",
        )
    )
    ok = 200 <= status < 300
    result = SubmissionResult(
        engine="google",
        status="submitted" if ok else "failed",
        http_status=status,
        attempted=True,
        message="Google Search Console accepted the sitemap." if ok else f"Google response: {response[:300]}",
        submitted_at=utc_now(),
    )
    if ok:
        state["google_sitemap_submitted_at"] = result.submitted_at
        write_state(state_path, state)
    append_log(log_path, result)
    return result
