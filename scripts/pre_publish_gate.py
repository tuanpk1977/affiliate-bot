from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the mandatory local health gate before Git push/deployment.")
    parser.add_argument("--urls-file", default="data/published_today.json")
    parser.add_argument("--publish-root", default="docs")
    parser.add_argument("--sitemap", default="docs/sitemap.xml")
    parser.add_argument("--expected-lastmod", default="")
    parser.add_argument("--repair", action="store_true")
    args = parser.parse_args()
    validation = [
        sys.executable,
        "scripts/validate_publishing_batch.py",
        "--urls-file",
        args.urls_file,
        "--publish-root",
        args.publish_root,
        "--sitemap",
        args.sitemap,
        "--new-pages-only",
    ]
    if args.expected_lastmod:
        validation.extend(["--expected-lastmod", args.expected_lastmod])
    if args.repair:
        validation.append("--repair-content")
    result = subprocess.run(validation, cwd=ROOT, check=False)
    if result.returncode:
        print("STOP: publishing preflight failed. Do not push or deploy.")
        return result.returncode
    report = subprocess.run(
        [
            sys.executable,
            "scripts/generate_operational_reports.py",
            "--publish-root",
            args.publish_root,
            "--urls-file",
            args.urls_file,
        ],
        cwd=ROOT,
        check=False,
    )
    if report.returncode:
        print("STOP: operational report generation failed. Do not push or deploy.")
        return report.returncode
    print("PASS: pre-publish gate completed. Git push/deployment may proceed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
