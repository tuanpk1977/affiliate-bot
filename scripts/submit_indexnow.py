from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import subprocess
import time
from pathlib import Path
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
SITE_OUTPUT = ROOT / "site_output"
PUBLISH_ROOT = ROOT / "docs"
SITEMAP = PUBLISH_ROOT / "sitemap.xml" if (PUBLISH_ROOT / "sitemap.xml").exists() else SITE_OUTPUT / "sitemap.xml"
KEY_FILE = PUBLISH_ROOT / "indexnow-key.txt" if (PUBLISH_ROOT / "indexnow-key.txt").exists() else SITE_OUTPUT / "indexnow-key.txt"
UPLOAD_LINKS = ROOT / "video_output" / "upload_links.csv"
RENDER_STATUS = ROOT / "video_output" / "render_status.csv"
STATE_FILE = ROOT / "data" / "indexnow_state.json"

HOST = os.getenv("INDEXNOW_HOST", "smileaireviewhub.com").strip().lower() or "smileaireviewhub.com"
BASE_URL = f"https://{HOST}"
KEY_LOCATION = os.getenv("INDEXNOW_KEY_LOCATION", f"{BASE_URL}/indexnow-key.txt").strip()
ENDPOINT = "https://api.indexnow.org/indexnow"
DEFAULT_MAX_URLS = 100
TEMPORARY_STATUS_CODES = {408, 425, 429, 500, 502, 503, 504}
BLOCKED_HOSTS = {"localhost", "127.0.0.1", "::1"}


def read_key(path: Path = KEY_FILE) -> str:
    configured = os.getenv("INDEXNOW_KEY", "").strip()
    if configured:
        return configured
    if not path.exists():
        raise FileNotFoundError(f"IndexNow key file is missing: {path}")
    key = path.read_text(encoding="utf-8").strip()
    if not key or any(char.isspace() for char in key):
        raise ValueError("IndexNow key must be one non-empty line without whitespace.")
    return key


def is_allowed_url(url: str) -> bool:
    try:
        parsed = urlparse(str(url).strip())
    except ValueError:
        return False
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or host != HOST:
        return False
    if host in BLOCKED_HOSTS or host.endswith(".netlify.app"):
        return False
    path = parsed.path.lower()
    return not any(part in path for part in ("/draft/", "/drafts/", "/preview/", "/.netlify/"))


def normalize_urls(urls: Iterable[str], max_urls: int = DEFAULT_MAX_URLS) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in urls:
        url = str(value or "").strip().split("#", 1)[0]
        if not is_allowed_url(url) or url in seen:
            continue
        seen.add(url)
        result.append(url)
        if len(result) >= max(1, max_urls):
            break
    return result


def read_all_sitemap_urls(path: Path = SITEMAP) -> list[str]:
    if not path.exists():
        raise FileNotFoundError(f"Sitemap is missing: {path}")
    root = ET.fromstring(path.read_text(encoding="utf-8", errors="ignore"))
    return [
        node.text.strip()
        for node in root.findall(".//{http://www.sitemaps.org/schemas/sitemap/0.9}loc")
        if node.text
    ]


def read_sitemap_urls(path: Path = SITEMAP) -> list[str]:
    return [url for url in read_all_sitemap_urls(path) if is_allowed_url(url)]


def read_latest_sitemap_urls(path: Path = SITEMAP) -> list[str]:
    if not path.exists():
        raise FileNotFoundError(f"Sitemap is missing: {path}")
    root = ET.fromstring(path.read_text(encoding="utf-8", errors="ignore"))
    rows: list[tuple[str, str]] = []
    namespace = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
    for node in root.findall(f".//{namespace}url"):
        loc = node.find(f"{namespace}loc")
        lastmod = node.find(f"{namespace}lastmod")
        url = loc.text.strip() if loc is not None and loc.text else ""
        if is_allowed_url(url):
            rows.append((lastmod.text.strip() if lastmod is not None and lastmod.text else "", url))
    rows.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [url for _, url in rows]


def csv_url_rows_from_text(text: str) -> dict[str, str]:
    rows: dict[str, str] = {}
    for row in csv.DictReader(text.lstrip("\ufeff").splitlines()):
        url = str(row.get("PageUrl") or row.get("ArticleUrl") or "").strip()
        if not is_allowed_url(url):
            continue
        fingerprint_source = json.dumps(row, ensure_ascii=False, sort_keys=True)
        rows[url] = hashlib.sha256(fingerprint_source.encode("utf-8")).hexdigest()
    return rows


def csv_url_rows(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    return csv_url_rows_from_text(path.read_text(encoding="utf-8-sig", errors="ignore"))


def previous_csv_url_rows(path: Path) -> dict[str, str] | None:
    try:
        rel = path.relative_to(ROOT).as_posix()
        result = subprocess.run(
            ["git", "show", f"HEAD^:{rel}"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            check=False,
        )
    except (OSError, ValueError):
        return None
    return csv_url_rows_from_text(result.stdout) if result.returncode == 0 else None


def read_state(path: Path = STATE_FILE) -> dict[str, str]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return payload if isinstance(payload, dict) else {}


def write_state(state: dict[str, str], path: Path = STATE_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def changed_site_urls_from_git() -> list[str]:
    commands = [
        ["git", "diff", "--name-only", "HEAD^", "HEAD", "--", "site_output"],
        ["git", "diff", "--name-only", "--", "site_output"],
        ["git", "diff", "--cached", "--name-only", "--", "site_output"],
    ]
    files: set[str] = set()
    for command in commands:
        try:
            result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
        except OSError:
            continue
        if result.returncode == 0:
            files.update(line.strip().replace("\\", "/") for line in result.stdout.splitlines() if line.strip())
    urls: list[str] = []
    for name in sorted(files):
        if not name.startswith("site_output/") or not name.endswith("/index.html"):
            continue
        rel = name[len("site_output/") : -len("index.html")]
        urls.append(f"{BASE_URL}/{rel.strip('/')}/" if rel.strip("/") else f"{BASE_URL}/")
    return urls


def collect_incremental_urls() -> tuple[list[str], dict[str, str]]:
    csv_paths = [path for path in (UPLOAD_LINKS, RENDER_STATUS) if path.exists()]
    if not csv_paths:
        return read_sitemap_urls(), {}

    current: dict[str, str] = {}
    previous_from_git: dict[str, str] = {}
    git_history_available = False
    for path in csv_paths:
        current.update(csv_url_rows(path))
        previous_rows = previous_csv_url_rows(path)
        if previous_rows is not None:
            git_history_available = True
            previous_from_git.update(previous_rows)
    previous = previous_from_git if git_history_available else read_state()
    changed_rows = [url for url, fingerprint in current.items() if previous.get(url) != fingerprint]
    changed_pages = changed_site_urls_from_git()
    candidates = normalize_urls([*changed_pages, *changed_rows], max_urls=10_000)
    return candidates, current


def build_payload(urls: Iterable[str], max_urls: int = DEFAULT_MAX_URLS) -> dict[str, object]:
    key = read_key()
    return {
        "host": HOST,
        "key": key,
        "keyLocation": KEY_LOCATION,
        "urlList": normalize_urls(urls, max_urls=max_urls),
    }


def submit_indexnow(
    urls: Iterable[str],
    *,
    max_urls: int = DEFAULT_MAX_URLS,
    retries: int = 3,
    retry_delay: float = 5.0,
    endpoint: str = ENDPOINT,
) -> bool:
    payload = build_payload(urls, max_urls=max_urls)
    url_list = payload["urlList"]
    if not url_list:
        print("[IndexNow] No eligible URLs to submit.")
        return True
    body = json.dumps(payload).encode("utf-8")
    print(f"[IndexNow] Submitting {len(url_list)} URL(s) to {endpoint}")
    for attempt in range(1, max(1, retries) + 1):
        request = Request(endpoint, data=body, headers={"Content-Type": "application/json; charset=utf-8"}, method="POST")
        try:
            with urlopen(request, timeout=30) as response:
                status = response.status
                print(f"[IndexNow] Accepted with HTTP {status}.")
                return 200 <= status < 300
        except HTTPError as exc:
            print(f"[IndexNow] HTTP {exc.code} on attempt {attempt}/{retries}.")
            if exc.code not in TEMPORARY_STATUS_CODES or attempt >= retries:
                return False
        except (URLError, TimeoutError, OSError) as exc:
            print(f"[IndexNow] Temporary request failure on attempt {attempt}/{retries}: {exc}")
            if attempt >= retries:
                return False
        time.sleep(retry_delay * attempt)
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Submit Smile AI Review Hub URLs to IndexNow.")
    parser.add_argument("--max-urls", type=int, default=int(os.getenv("INDEXNOW_MAX_URLS", DEFAULT_MAX_URLS)))
    parser.add_argument("--latest", type=int, default=0, help="Submit the newest N sitemap URLs.")
    parser.add_argument("--all", action="store_true", help="Submit URLs from sitemap instead of incremental candidates.")
    parser.add_argument("--dry-run", action="store_true", help="Print payload without sending.")
    args = parser.parse_args()

    state: dict[str, str] = {}
    sitemap_total = len(read_all_sitemap_urls())
    if args.latest > 0:
        urls = read_latest_sitemap_urls()[: args.latest]
        args.max_urls = args.latest
        source = f"latest {args.latest} sitemap URLs"
    elif args.all:
        urls = read_sitemap_urls()
        source = "sitemap"
    else:
        urls, state = collect_incremental_urls()
        source = "incremental CSV/git changes" if UPLOAD_LINKS.exists() or RENDER_STATUS.exists() else "sitemap"
        if not urls:
            urls = read_latest_sitemap_urls()[: args.max_urls]
            source = f"latest {args.max_urls} sitemap URLs (incremental fallback)"
    payload = build_payload(urls, max_urls=args.max_urls)
    print(f"[IndexNow] Sitemap URLs: {sitemap_total}")
    print(f"[IndexNow] Source: {source}; URLs selected: {len(payload['urlList'])}; max: {args.max_urls}")
    if args.dry_run:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    ok = submit_indexnow(payload["urlList"], max_urls=args.max_urls)
    if ok and state:
        write_state(state)
    if not ok:
        print("[IndexNow] Submission failed. Build/deploy should continue; retry later.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
