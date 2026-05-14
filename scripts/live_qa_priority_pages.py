from __future__ import annotations

import argparse
import csv
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import pandas as pd


BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
INDEX_PATH = DATA_DIR / "priority_pages_index.csv"
OUTPUT_PATH = DATA_DIR / "live_priority_page_qa.csv"
DEFAULT_DOMAIN = "https://review.mssmileenglish.com"


PLACEHOLDER_PATTERNS = [
    r"localhost",
    r"yourdomain\.com",
    r"example\.com",
    r"lorem ipsum",
    r"\btodo\b",
    r"\bundefined\b",
    r"page not found",
    r"404 not found",
    r"error loading",
    r"placeholder image",
]


@dataclass
class PageCheck:
    keyword: str
    slug: str
    url: str
    status_code: str
    has_h1: bool
    has_meta_description: bool
    go_link_count: int
    has_bad_placeholder: bool
    canonical_ok: bool
    passed: bool
    error: str
    checked_at: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Live QA for deployed priority money pages.")
    parser.add_argument("--domain", default=DEFAULT_DOMAIN, help="Live site domain, default: https://review.mssmileenglish.com")
    parser.add_argument("--limit", type=int, default=10, help="Number of priority pages to check. Default: 10")
    parser.add_argument("--timeout", type=int, default=20, help="HTTP timeout seconds. Default: 20")
    return parser.parse_args()


def load_priority_pages(limit: int) -> pd.DataFrame:
    if not INDEX_PATH.exists():
        raise FileNotFoundError(f"Missing {INDEX_PATH}")
    df = pd.read_csv(INDEX_PATH).fillna("")
    required = {"keyword", "suggested_slug", "status"}
    missing = required.difference(df.columns)
    if missing:
        raise ValueError(f"Missing columns in {INDEX_PATH}: {', '.join(sorted(missing))}")
    built = df[df["status"].astype(str).str.lower() == "built"].copy()
    if built.empty:
        raise ValueError("No built priority pages found")
    return built.head(max(1, limit))


def fetch(url: str, timeout: int) -> tuple[str, str, str]:
    request = Request(url, headers={"User-Agent": "AI-Tool-Review-Hub-Live-QA/1.0"})
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="ignore")
            return str(response.status), body, ""
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")
        return str(exc.code), body, str(exc)
    except URLError as exc:
        return "ERROR", "", str(exc)
    except TimeoutError as exc:
        return "ERROR", "", str(exc)


def check_page(row: pd.Series, domain: str, timeout: int) -> PageCheck:
    slug = str(row.get("suggested_slug", "")).strip("/")
    keyword = str(row.get("keyword", "")).strip()
    base = domain.rstrip("/")
    url = f"{base}/{slug}/"
    status_code, body, error = fetch(url, timeout)
    lower = body.lower()

    has_h1 = bool(re.search(r"<h1\b[^>]*>.*?</h1>", body, re.IGNORECASE | re.DOTALL))
    has_meta = bool(re.search(r'<meta\s+name=["\']description["\']\s+content=["\'][^"\']{40,}["\']', body, re.IGNORECASE))
    go_count = body.count("/go/")
    has_placeholder = any(re.search(pattern, lower, re.IGNORECASE) for pattern in PLACEHOLDER_PATTERNS)
    canonical = f'<link rel="canonical" href="{url}"'
    canonical_ok = canonical.lower() in lower
    passed = status_code == "200" and has_h1 and has_meta and go_count >= 3 and not has_placeholder and canonical_ok
    if status_code == "200" and not passed and not error:
        failures = []
        if not has_h1:
            failures.append("missing_h1")
        if not has_meta:
            failures.append("missing_meta_description")
        if go_count < 3:
            failures.append("fewer_than_3_go_links")
        if has_placeholder:
            failures.append("placeholder_or_error_text_found")
        if not canonical_ok:
            failures.append("canonical_mismatch")
        error = "|".join(failures)

    return PageCheck(
        keyword=keyword,
        slug=slug,
        url=url,
        status_code=status_code,
        has_h1=has_h1,
        has_meta_description=has_meta,
        go_link_count=go_count,
        has_bad_placeholder=has_placeholder,
        canonical_ok=canonical_ok,
        passed=passed,
        error=error,
        checked_at=datetime.now(timezone.utc).isoformat(),
    )


def write_results(results: list[PageCheck]) -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(PageCheck.__dataclass_fields__.keys()))
        writer.writeheader()
        for result in results:
            writer.writerow(result.__dict__)


def main() -> int:
    args = parse_args()
    pages = load_priority_pages(args.limit)
    results = [check_page(row, args.domain, args.timeout) for _, row in pages.iterrows()]
    write_results(results)

    passed = sum(1 for result in results if result.passed)
    failed = len(results) - passed
    print(f"Live QA checked {len(results)} priority pages")
    print(f"Passed: {passed} | Failed: {failed}")
    print(f"Output: {OUTPUT_PATH}")
    for result in results:
        status = "PASS" if result.passed else "FAIL"
        detail = result.error or "ok"
        print(f"- {status} {result.status_code} {result.url} ({detail})")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Live QA failed: {exc}")
        raise SystemExit(1)
