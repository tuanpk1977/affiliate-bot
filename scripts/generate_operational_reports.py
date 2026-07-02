from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from modules.content_quality import inspect_content, write_content_qa_report  # noqa: E402
from modules.operational_health import audit_site, safe_repair_pages, write_health_reports, write_internal_link_map  # noqa: E402


def read_urls(path: Path) -> list[str]:
    if not path.exists():
        return []
    if path.suffix.lower() == ".json":
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        rows = payload if isinstance(payload, list) else payload.get("articles", payload.get("rows", []))
    else:
        with path.open(newline="", encoding="utf-8-sig") as handle:
            rows = list(csv.DictReader(handle))
    return [
        str(row.get("published_url") or row.get("article_url") or row.get("url") or "").strip()
        for row in rows
        if isinstance(row, dict)
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate daily site health, SEO dashboard, content QA, and link graph reports.")
    parser.add_argument("--publish-root", default="docs")
    parser.add_argument("--reports", default="reports")
    parser.add_argument("--urls-file", default="")
    parser.add_argument("--repair", action="store_true")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    root = ROOT / args.publish_root
    report_dir = ROOT / args.reports
    urls = read_urls(ROOT / args.urls_file) if args.urls_file else []
    if args.repair and urls:
        repair = safe_repair_pages(root, urls)
        (report_dir / "auto-repair.json").parent.mkdir(parents=True, exist_ok=True)
        (report_dir / "auto-repair.json").write_text(json.dumps(repair, indent=2) + "\n", encoding="utf-8")
    audit = audit_site(root)
    write_health_reports(audit, report_dir, today_urls=urls)
    write_internal_link_map(audit, report_dir / "internal-link-map.md")
    qa_pages = [page for page in audit.indexable_pages if not urls or page.url in urls]
    qa = [inspect_content(Path(page.file), repair=args.repair) for page in qa_pages]
    write_content_qa_report(qa, report_dir / "content-qa.md")
    summary = audit.summary()
    print(f"Health: {summary['status']}")
    print(f"Pages: {summary['indexable_pages']}")
    print(f"Sitemap URLs: {summary['sitemap_urls']}")
    print(f"Broken links: {summary['broken_internal_links']}")
    print(f"Orphans: {summary['orphan_pages']}")
    print(f"Content QA failures: {sum(not item.ok for item in qa)}")
    return 1 if args.strict and (summary["status"] != "PASS" or any(not item.ok for item in qa)) else 0


if __name__ == "__main__":
    raise SystemExit(main())
