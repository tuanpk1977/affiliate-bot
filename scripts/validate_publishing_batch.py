from __future__ import annotations

import argparse
import csv
from datetime import date
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from modules.publishing_indexing import BASE_URL, validate_batch  # noqa: E402
from modules.content_quality import inspect_content, write_content_qa_report  # noqa: E402


def urls_from_file(path: Path) -> list[str]:
    if not path.exists():
        raise FileNotFoundError(path)
    if path.suffix.lower() == ".json":
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        rows = payload if isinstance(payload, list) else payload.get("articles", payload.get("rows", []))
        return [
            str(row.get("published_url") or row.get("article_url") or row.get("url") or "").strip()
            for row in rows
            if isinstance(row, dict)
        ]
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return [
            str(row.get("published_url") or row.get("article_url") or row.get("url") or "").strip()
            for row in csv.DictReader(handle)
        ]


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a published article batch before deployment.")
    parser.add_argument("--publish-root", default="docs")
    parser.add_argument("--sitemap", default="docs/sitemap.xml")
    parser.add_argument("--url", action="append", default=[])
    parser.add_argument("--urls-file")
    parser.add_argument("--expected-lastmod", default=date.today().isoformat())
    parser.add_argument("--report", default="data/publishing_preflight_report.json")
    parser.add_argument("--published-today", default="data/published_today.json")
    parser.add_argument("--new-pages-only", action="store_true", help="Skip the full sitemap canonical scan.")
    parser.add_argument("--repair-content", action="store_true", help="Remove exact duplicate paragraphs before validation.")
    args = parser.parse_args()

    urls = list(args.url)
    source_file = Path(args.urls_file) if args.urls_file else Path(args.published_today)
    if source_file.exists():
        urls.extend(urls_from_file(source_file))
    urls = [url for url in urls if url.startswith(BASE_URL)]
    if not urls:
        print("FAIL: no published URLs were provided or found.")
        return 2

    expected_lastmod = date.fromisoformat(args.expected_lastmod)
    result = validate_batch(
        Path(args.publish_root),
        Path(args.sitemap),
        urls,
        expected_lastmod=expected_lastmod,
        validate_all_canonicals=not args.new_pages_only,
    )
    qa_results = [
        inspect_content(Path(page.file), repair=args.repair_content)
        for page in result.pages
        if Path(page.file).exists()
    ]
    write_content_qa_report(qa_results, ROOT / "reports" / "content-qa.md")
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(result.to_dict(), indent=2) + "\n", encoding="utf-8")

    print(f"Published URLs: {len(result.published_urls)}")
    print(f"Sitemap URLs: {result.sitemap.total_urls}")
    print(f"Pages valid: {sum(page.ok for page in result.pages)}/{len(result.pages)}")
    print(f"Sitemap: {'PASS' if result.sitemap.ok else 'FAIL'}")
    qa_ok = all(item.ok for item in qa_results)
    overall_ok = result.ok and qa_ok
    print(f"Content QA: {'PASS' if qa_ok else 'FAIL'}")
    print(f"Overall: {'PASS' if overall_ok else 'FAIL'}")
    if not overall_ok:
        for error in result.sitemap.errors:
            print(f"- sitemap: {error}")
        for error in result.sitemap.duplicate_urls:
            print(f"- duplicate sitemap URL: {error}")
        for error in result.sitemap.published_urls_missing:
            print(f"- URL missing from sitemap: {error}")
        for error in result.sitemap.invalid_lastmod:
            print(f"- lastmod: {error}")
        for error in result.sitemap.canonical_mismatches[:50]:
            print(f"- canonical: {error}")
        for page in result.pages:
            for error in page.errors:
                print(f"- {page.url}: {error}")
        for item in qa_results:
            for error in item.errors:
                print(f"- content QA {item.file}: {error}")
    print(f"Report: {report_path}")
    return 0 if overall_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
