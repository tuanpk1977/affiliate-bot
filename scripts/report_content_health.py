from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import settings
from modules.content_health_report import audit_content_health, format_content_health


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read-only local content health report for the production static site."
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    parser.add_argument(
        "--root",
        type=Path,
        default=settings.site_output_dir,
        help="Local production-output root to inspect (default: site_output).",
    )
    parser.add_argument(
        "--sitemap",
        type=Path,
        help="Optional local sitemap path (default: <root>/sitemap.xml).",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Return exit code 1 when required trust pages or core metadata are missing.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    base_url = (settings.base_site_url or settings.site_domain).rstrip("/")
    report = audit_content_health(
        args.root,
        base_url=base_url,
        sitemap_path=args.sitemap,
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(format_content_health(report))
    if not args.strict:
        return 0
    summary = report["summary"]
    required_missing = any(not value for value in report["trust_pages"].values())
    metadata_missing = any(
        summary[key] > 0
        for key in (
            "missing_title_count",
            "missing_description_count",
            "missing_canonical_count",
        )
    )
    return 1 if required_missing or metadata_missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
