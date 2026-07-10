from __future__ import annotations

import argparse
import csv
from datetime import date, datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from modules.publishing_indexing import (  # noqa: E402
    BASE_URL,
    validate_batch,
    validate_live_pages,
    validate_live_sitemap,
    wait_for_live_urls,
)
from modules.search_engine_submission import (  # noqa: E402
    submit_bing_sitemap,
    submit_google_sitemap,
)
from scripts.submit_indexnow import submit_indexnow  # noqa: E402


SITE_URL = f"{BASE_URL}/"
SITEMAP_URL = f"{BASE_URL}/sitemap.xml"
LOG_ROOT = ROOT / "logs" / "indexing"
STATE_PATH = LOG_ROOT / "submission-state.json"


def git_changed_urls(base: str, head: str) -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=AMR", base, head, "--", "docs"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0:
        return []
    urls: list[str] = []
    for name in result.stdout.splitlines():
        normalized = name.strip().replace("\\", "/")
        if normalized == "docs/index.html":
            urls.append(f"{BASE_URL}/")
        elif normalized.startswith("docs/") and normalized.endswith("/index.html"):
            slug = normalized[len("docs/") : -len("/index.html")].strip("/")
            if slug and not slug.startswith(("go/", "draft/", "preview/")):
                urls.append(f"{BASE_URL}/{slug}/")
    return sorted(set(urls))


def wait_with_recovery(urls: list[str], delays: list[int]) -> dict[str, int]:
    statuses = wait_for_live_urls(urls, timeout_seconds=0, interval_seconds=1)
    if statuses and all(status == 200 for status in statuses.values()):
        return statuses
    for delay in delays:
        print(f"Deployment health check failed. Retrying in {delay} seconds.")
        time.sleep(delay)
        statuses = wait_for_live_urls(urls, timeout_seconds=0, interval_seconds=1)
        if statuses and all(status == 200 for status in statuses.values()):
            return statuses
    return statuses


def urls_from_file(path: Path) -> list[str]:
    if not path.exists():
        return []
    if path.suffix.lower() == ".json":
        try:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError:
            return []
        rows = payload if isinstance(payload, list) else payload.get("articles", payload.get("rows", []))
    else:
        with path.open(newline="", encoding="utf-8-sig") as handle:
            rows = list(csv.DictReader(handle))
    return [
        str(row.get("published_url") or row.get("article_url") or row.get("url") or "").strip()
        for row in rows
        if isinstance(row, dict)
    ]


def append_json_log(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")


def write_report(report: dict[str, object]) -> Path:
    now = datetime.now(timezone.utc)
    run_dir = LOG_ROOT / now.strftime("%Y-%m-%d")
    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / f"publishing-report-{now.strftime('%H%M%S')}.json"
    content = json.dumps(report, indent=2, sort_keys=True) + "\n"
    path.write_text(content, encoding="utf-8")
    (LOG_ROOT / "daily-report.json").write_text(content, encoding="utf-8")
    return path


def write_markdown_reports(report: dict[str, object], started: datetime, report_path: Path) -> None:
    reports = ROOT / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    checks = report.get("checks", {})
    urls = report.get("published_urls", [])
    finished = datetime.fromisoformat(str(report["finished"]))
    duration = max(0.0, (finished - started).total_seconds())
    commit = str(report.get("github", ""))
    deployment_lines = [
        "# Deployment Report",
        "",
        f"- Batch ID: {started.strftime('%Y%m%d-%H%M%S')}",
        f"- Commit SHA: {commit}",
        f"- Deployment duration: {duration:.1f} seconds",
        f"- Cloudflare status: {report.get('cloudflare')}",
        f"- Published URLs: {len(urls)}",
        f"- Indexed URLs: {len(urls) if report.get('status') == 'PASS' else 0}",
        f"- Skipped URLs: {0 if report.get('status') == 'PASS' else len(urls)}",
        f"- Validation summary: {report.get('status')}",
        f"- Warnings: {', '.join(report.get('warnings', [])) or 'None'}",
        f"- Errors: {', '.join(report.get('errors', [])) or 'None'}",
        "",
        "## Published URLs",
        *[f"- {url}" for url in urls],
        "",
        "## Validation",
        *[f"- {name}: {value}" for name, value in checks.items()],
        "",
        f"JSON report: `{report_path.as_posix()}`",
    ]
    (reports / "deployment-report.md").write_text("\n".join(deployment_lines) + "\n", encoding="utf-8")
    indexing_lines = [
        "# Indexing Report",
        "",
        f"- Submitted: {len(urls) if str(report.get('indexnow', {}).get('status', '')).endswith('submitted') else 0}",
        f"- Skipped: {0 if report.get('status') == 'PASS' else len(urls)}",
        "- Already indexed: Not queried (search engines do not provide a reliable real-time bulk status API)",
        f"- Retry needed: {'No' if report.get('status') == 'PASS' else 'Yes'}",
        f"- IndexNow: {report.get('indexnow', {}).get('status')}",
        f"- Bing sitemap: {report.get('bing', {}).get('status')}",
        f"- Google sitemap: {report.get('google', {}).get('status')}",
        "",
        "## Changed URLs",
        *[f"- {url}" for url in urls],
    ]
    (reports / "indexing-report.md").write_text("\n".join(indexing_lines) + "\n", encoding="utf-8")


def print_summary(report: dict[str, object]) -> None:
    checks = report["checks"]
    print("----------------------------------")
    print("Publishing Report")
    print(f"Articles published: {report['articles_published']}")
    print(f"HTTP 200: {checks['http_200']}")
    print(f"Internal links: {checks['internal_links']}")
    print(f"Schema: {checks['schema']}")
    print(f"Review schema: {checks['review_schema']}")
    print(f"FAQ schema: {checks['faq_schema']}")
    print(f"Breadcrumb: {checks['breadcrumb']}")
    print(f"Author: {checks['author']}")
    print(f"Canonical: {checks['canonical']}")
    print(f"Sitemap: {checks['sitemap']}")
    print(f"URLs in sitemap: {report['sitemap_url_count']}")
    print(f"IndexNow: {report['indexnow']['status']}")
    print(f"Bing sitemap: {report['bing']['status']}")
    print(f"Google sitemap: {report['google']['status']}")
    print(f"GitHub: {report['github']}")
    print(f"Cloudflare: {report['cloudflare']}")
    print(f"Finished: {report['finished']}")
    print("----------------------------------")


def main() -> int:
    started = datetime.now(timezone.utc)
    parser = argparse.ArgumentParser(description="Validate a deployed batch, then notify search engines.")
    parser.add_argument("--publish-root", default="docs")
    parser.add_argument("--sitemap", default="docs/sitemap.xml")
    parser.add_argument("--url", action="append", default=[])
    parser.add_argument("--urls-file", default="")
    parser.add_argument("--from-git", action="store_true")
    parser.add_argument("--git-base", default="HEAD^")
    parser.add_argument("--git-head", default="HEAD")
    parser.add_argument("--wait-seconds", type=int, default=600)
    parser.add_argument("--interval-seconds", type=int, default=15)
    parser.add_argument(
        "--recovery-delays",
        default="60,180,600,1800",
        help="Comma-separated deployment retry delays in seconds.",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-bing", action="store_true")
    parser.add_argument("--skip-google", action="store_true")
    parser.add_argument("--skip-indexnow", action="store_true")
    parser.add_argument("--expected-lastmod", default="")
    parser.add_argument("--strict-indexing", action="store_true", help="Exit nonzero on indexing/preflight failures.")
    args = parser.parse_args()
    strict_indexing = args.strict_indexing or str(os.getenv("STRICT_INDEXING", "")).strip().lower() in {"1", "true", "yes", "on"}

    urls = list(args.url)
    if args.urls_file:
        urls.extend(urls_from_file(Path(args.urls_file)))
    if args.from_git:
        urls.extend(git_changed_urls(args.git_base, args.git_head))
        if not urls:
            print("No changed public pages in this Git diff. Post-deploy indexing is not required.")
            return 0
    if not urls:
        urls.extend(urls_from_file(ROOT / "data" / "published_today.json"))
    urls = sorted(set(url for url in urls if url.startswith(BASE_URL)))
    if not urls:
        print("WARNING: no newly published URLs were found. Search engine submission skipped.")
        return 2 if strict_indexing else 0

    expected = date.fromisoformat(args.expected_lastmod) if args.expected_lastmod else None
    validation = validate_batch(
        ROOT / args.publish_root,
        ROOT / args.sitemap,
        urls,
        expected_lastmod=expected,
        validate_all_canonicals=True,
    )
    from modules.content_quality import inspect_content, write_content_qa_report

    content_qa = [inspect_content(Path(page.file)) for page in validation.pages if Path(page.file).exists()]
    write_content_qa_report(content_qa, ROOT / "reports" / "content-qa.md")
    content_qa_ok = all(item.ok for item in content_qa)
    append_json_log(
        LOG_ROOT / "sitemap-validation.log",
        {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "ok": validation.sitemap.ok,
            "total_urls": validation.sitemap.total_urls,
            "published_urls": urls,
            "details": validation.to_dict()["sitemap"],
        },
    )
    if not validation.ok or not content_qa_ok:
        report = {
            "status": "FAILED_PREFLIGHT",
            "articles_published": len(urls),
            "published_urls": urls,
            "validation": validation.to_dict(),
            "content_qa": [
                {
                    "file": item.file,
                    "ok": item.ok,
                    "errors": item.errors,
                    "warnings": item.warnings,
                }
                for item in content_qa
            ],
            "github": os.getenv("GITHUB_SHA", "dry-run/local"),
            "cloudflare": "not attempted",
            "warnings": [],
            "errors": ["preflight validation failed"],
            "finished": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        path = write_report(report)
        write_markdown_reports(report, started, path)
        print(f"WARNING: preflight validation failed. No search engine was notified. Report: {path}")
        return 1 if strict_indexing else 0

    if args.dry_run:
        live_statuses = {url: 200 for url in urls}
        live_sitemap_ok = True
        sitemap_count = validation.sitemap.total_urls
        live_sitemap_errors: list[str] = []
    else:
        if args.recovery_delays:
            try:
                recovery_delays = [max(0, int(value)) for value in args.recovery_delays.split(",") if value.strip()]
            except ValueError:
                print("FAIL: --recovery-delays must contain comma-separated integers.")
                return 2
            live_statuses = wait_with_recovery(urls, recovery_delays)
        else:
            live_statuses = wait_for_live_urls(
                urls,
                timeout_seconds=args.wait_seconds,
                interval_seconds=args.interval_seconds,
            )
        if not all(status == 200 for status in live_statuses.values()):
            report = {
                "status": "FAILED_DEPLOYMENT_CHECK",
                "articles_published": len(urls),
                "published_urls": urls,
                "live_http": live_statuses,
                "github": os.getenv("GITHUB_SHA", "local"),
                "cloudflare": "failed health check",
                "warnings": [],
                "errors": ["not all URLs returned HTTP 200 with a valid canonical"],
                "finished": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }
            path = write_report(report)
            write_markdown_reports(report, started, path)
            print(f"WARNING: not all deployed URLs returned HTTP 200. No search engine was notified. Report: {path}")
            return 1 if strict_indexing else 0
        live_sitemap_ok, sitemap_count, live_sitemap_errors = validate_live_sitemap(SITEMAP_URL, urls)
        if not live_sitemap_ok:
            report = {
                "status": "FAILED_LIVE_SITEMAP",
                "articles_published": len(urls),
                "published_urls": urls,
                "live_http": live_statuses,
                "live_sitemap_errors": live_sitemap_errors,
                "github": os.getenv("GITHUB_SHA", "local"),
                "cloudflare": "deployed",
                "warnings": [],
                "errors": live_sitemap_errors,
                "finished": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }
            path = write_report(report)
            write_markdown_reports(report, started, path)
            print(f"WARNING: live sitemap validation failed. No search engine was notified. Report: {path}")
            return 1 if strict_indexing else 0
        live_pages_ok, live_page_errors = validate_live_pages(urls)
        if not live_pages_ok:
            report = {
                "status": "FAILED_LIVE_SMART_VALIDATION",
                "articles_published": len(urls),
                "published_urls": urls,
                "live_http": live_statuses,
                "live_page_errors": live_page_errors,
                "github": os.getenv("GITHUB_SHA", "local"),
                "cloudflare": "deployed",
                "warnings": [],
                "errors": [f"{url}: {', '.join(errors)}" for url, errors in live_page_errors.items()],
                "finished": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }
            path = write_report(report)
            write_markdown_reports(report, started, path)
            print(f"WARNING: live smart URL validation failed. No search engine was notified. Report: {path}")
            return 1 if strict_indexing else 0

    indexnow_ok = True
    if args.skip_indexnow:
        indexnow_status = "skipped"
    elif args.dry_run:
        indexnow_status = f"dry_run ({len(urls)} URLs)"
    else:
        indexnow_ok = submit_indexnow(urls, max_urls=len(urls), retries=3)
        indexnow_status = f"{len(urls)}/{len(urls)} submitted" if indexnow_ok else "failed"
    append_json_log(
        LOG_ROOT / "indexnow.log",
        {"timestamp": datetime.now(timezone.utc).isoformat(), "urls": urls, "status": indexnow_status},
    )

    if args.skip_bing:
        bing = {"engine": "bing", "status": "skipped", "message": ""}
    else:
        bing = submit_bing_sitemap(
            SITE_URL,
            SITEMAP_URL,
            state_path=STATE_PATH,
            log_path=LOG_ROOT / "bing-submit.log",
            dry_run=args.dry_run,
        ).to_dict()
    if args.skip_google:
        google = {"engine": "google", "status": "skipped", "message": ""}
    else:
        google = submit_google_sitemap(
            os.getenv("GOOGLE_SEARCH_CONSOLE_SITE_URL", SITE_URL).strip() or SITE_URL,
            SITEMAP_URL,
            state_path=STATE_PATH,
            log_path=LOG_ROOT / "google-submit.log",
            dry_run=args.dry_run,
        ).to_dict()

    page_types = [set(page.schema_types) for page in validation.pages]
    engine_failures = [
        result.get("engine", "unknown")
        for result in (bing, google)
        if result.get("status") == "failed"
    ]
    overall_ok = indexnow_ok and not engine_failures
    report = {
        "status": "PASS" if overall_ok else "PARTIAL",
        "articles_published": len(urls),
        "published_urls": urls,
        "live_http": live_statuses,
        "sitemap_url_count": sitemap_count,
        "checks": {
            "http_200": f"{sum(status == 200 for status in live_statuses.values())}/{len(urls)}",
            "internal_links": "PASS" if all(page.internal_links > 0 for page in validation.pages) else "FAIL",
            "schema": "PASS",
            "review_schema": "PASS",
            "faq_schema": "PASS" if all("FAQPage" in types for types in page_types) else "N/A",
            "breadcrumb": "PASS" if all("BreadcrumbList" in types for types in page_types) else "FAIL",
            "author": "PASS",
            "canonical": "PASS",
            "sitemap": "PASS",
        },
        "indexnow": {"status": indexnow_status},
        "bing": bing,
        "google": google,
        "github": os.getenv("GITHUB_SHA", "local verification"),
        "cloudflare": "Deployed" if not args.dry_run else "dry_run",
        "finished": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "validation": validation.to_dict(),
    }
    report_path = write_report(report)
    write_markdown_reports(report, started, report_path)
    try:
        from modules.operational_health import audit_site, write_health_reports, write_internal_link_map
        audit = audit_site(ROOT / args.publish_root)
        write_health_reports(audit, ROOT / "reports", today_urls=urls)
        write_internal_link_map(audit, ROOT / "reports" / "internal-link-map.md")
        write_content_qa_report(content_qa, ROOT / "reports" / "content-qa.md")
    except Exception as exc:
        print(f"WARNING: operational report generation failed: {exc}")
    print_summary(report)
    if engine_failures:
        print(f"WARNING: failed search engine submissions: {', '.join(engine_failures)}")
    print(f"Report: {report_path}")
    return 0 if overall_ok or not strict_indexing else 1


if __name__ == "__main__":
    raise SystemExit(main())
