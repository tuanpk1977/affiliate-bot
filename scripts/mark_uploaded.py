from __future__ import annotations

import argparse
import csv
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATUS_CSV = ROOT / "video_output" / "render_status.csv"
VALID_STATUSES = {"UPLOADED", "FAILED", "NOT_UPLOADED"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Update YouTube upload status in video_output/render_status.csv.")
    parser.add_argument("--folder", required=True, help="FolderName value to update, for example review-surfer-seo.")
    parser.add_argument("--url", default="", help="YouTube video URL after successful upload.")
    parser.add_argument("--status", default="", help="Upload status: UPLOADED, FAILED, or NOT_UPLOADED.")
    parser.add_argument("--notes", default="", help="Optional notes to store in the Notes column.")
    return parser.parse_args()


def read_rows() -> tuple[list[str], list[dict[str, str]]]:
    if not STATUS_CSV.exists():
        raise FileNotFoundError(f"Missing status file: {STATUS_CSV}")
    with STATUS_CSV.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)
    if not fieldnames:
        raise ValueError(f"Status file has no header: {STATUS_CSV}")
    return fieldnames, rows


def write_rows(fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    temp_path = STATUS_CSV.with_suffix(".csv.tmp")
    with temp_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    temp_path.replace(STATUS_CSV)


def run_website_sync() -> bool:
    commands = [
        [sys.executable, "build_site.py"],
        [sys.executable, "scripts/sync_site_output_to_docs.py"],
    ]
    ok = True
    for command in commands:
        print(f"Running: {' '.join(command)}")
        result = subprocess.run(command, cwd=ROOT)
        if result.returncode != 0:
            ok = False
            print(
                f"WARNING: Website sync command failed with exit code {result.returncode}: {' '.join(command)}",
                file=sys.stderr,
            )
            print("render_status.csv was already saved. No video files were modified or deleted.", file=sys.stderr)
            break
    return ok


def main() -> int:
    args = parse_args()
    status = (args.status or "").strip().upper()
    if args.url and not status:
        status = "UPLOADED"
    if not status:
        status = "UPLOADED"
    if status not in VALID_STATUSES:
        print(f"Invalid --status '{args.status}'. Use one of: {', '.join(sorted(VALID_STATUSES))}", file=sys.stderr)
        return 2

    fieldnames, rows = read_rows()
    required = ["FolderName", "UploadStatus", "YoutubeVideoUrl", "LastModified", "Notes"]
    missing = [field for field in required if field not in fieldnames]
    if missing:
        print(f"Missing required columns in {STATUS_CSV}: {', '.join(missing)}", file=sys.stderr)
        return 2

    matches = [row for row in rows if row.get("FolderName") == args.folder]
    if not matches:
        print(f"FolderName not found: {args.folder}", file=sys.stderr)
        return 1

    now = datetime.now(timezone.utc).isoformat()
    for row in matches:
        row["UploadStatus"] = status
        if args.url:
            row["YoutubeVideoUrl"] = args.url
        elif status != "UPLOADED":
            row["YoutubeVideoUrl"] = row.get("YoutubeVideoUrl", "")
        row["LastModified"] = now
        if args.notes:
            row["Notes"] = args.notes

    write_rows(fieldnames, rows)
    url_text = matches[0].get("YoutubeVideoUrl", "")
    print(f"Updated {args.folder}: UploadStatus={status}")
    if url_text:
        print(f"YoutubeVideoUrl={url_text}")
    if args.notes:
        print(f"Notes={args.notes}")
    print(f"Saved: {STATUS_CSV}")
    if run_website_sync():
        print("Website rebuild and docs sync completed.")
    else:
        print("WARNING: Upload status saved, but website rebuild/sync did not complete.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
