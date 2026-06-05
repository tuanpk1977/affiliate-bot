from __future__ import annotations

import csv
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VIDEO_OUTPUT = ROOT / "video_output"
UPLOAD_LINKS_CSV = VIDEO_OUTPUT / "upload_links.csv"
STATUS_CSV = VIDEO_OUTPUT / "render_status.csv"
REPORT_MD = VIDEO_OUTPUT / "bulk_upload_update_report.md"


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    if not path.exists():
        raise FileNotFoundError(f"Missing CSV: {path}")
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)
    if not fieldnames:
        raise ValueError(f"CSV has no header: {path}")
    return fieldnames, rows


def write_status(fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    temp_path = STATUS_CSV.with_suffix(".csv.tmp")
    with temp_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    try:
        temp_path.replace(STATUS_CSV)
    except PermissionError:
        try:
            with STATUS_CSV.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
                writer.writeheader()
                writer.writerows(rows)
        except PermissionError as exc:
            raise PermissionError(
                f"Cannot update {STATUS_CSV}. Close Excel or any app previewing render_status.csv, then run again."
            ) from exc
        try:
            temp_path.unlink()
        except OSError:
            pass


def run_command(command: list[str]) -> tuple[bool, str]:
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
    output = (result.stdout or "") + (result.stderr or "")
    return result.returncode == 0, output.strip()


def run_website_sync() -> list[tuple[str, bool, str]]:
    commands = [
        [sys.executable, "build_site.py"],
        [sys.executable, "scripts/sync_site_output_to_docs.py"],
    ]
    results: list[tuple[str, bool, str]] = []
    for command in commands:
        label = " ".join(command)
        print(f"Running: {label}")
        ok, output = run_command(command)
        results.append((label, ok, output))
        if output:
            print(output)
        if not ok:
            print(f"WARNING: Command failed: {label}", file=sys.stderr)
            print("render_status.csv was already saved. No video files were modified or deleted.", file=sys.stderr)
            break
    return results


def update_rows() -> tuple[list[dict[str, str]], list[str], list[str], list[str], list[str]]:
    upload_fieldnames, upload_rows = read_csv(UPLOAD_LINKS_CSV)
    required_upload = {"FolderName", "YoutubeVideoUrl"}
    missing_upload = sorted(required_upload - set(upload_fieldnames))
    if missing_upload:
        raise ValueError(f"Missing columns in {UPLOAD_LINKS_CSV}: {', '.join(missing_upload)}")

    status_fieldnames, status_rows = read_csv(STATUS_CSV)
    required_status = {"FolderName", "UploadStatus", "YoutubeVideoUrl", "LastModified"}
    missing_status = sorted(required_status - set(status_fieldnames))
    if missing_status:
        raise ValueError(f"Missing columns in {STATUS_CSV}: {', '.join(missing_status)}")

    by_folder = {row.get("FolderName", ""): row for row in status_rows if row.get("FolderName")}
    now = datetime.now(timezone.utc).isoformat()
    updated: list[str] = []
    missing: list[str] = []
    skipped: list[str] = []
    duplicate_inputs: list[str] = []
    seen_inputs: set[str] = set()

    for input_row in upload_rows:
        folder = str(input_row.get("FolderName") or "").strip()
        url = str(input_row.get("YoutubeVideoUrl") or "").strip()
        if not folder and not url:
            continue
        if not folder or not url:
            skipped.append(folder or "(missing FolderName)")
            continue
        if folder in seen_inputs:
            duplicate_inputs.append(folder)
        seen_inputs.add(folder)
        status_row = by_folder.get(folder)
        if not status_row:
            missing.append(folder)
            continue
        status_row["UploadStatus"] = "UPLOADED"
        status_row["YoutubeVideoUrl"] = url
        status_row["LastModified"] = now
        updated.append(folder)

    write_status(status_fieldnames, status_rows)
    return status_rows, updated, missing, skipped, duplicate_inputs


def write_report(
    updated: list[str],
    missing: list[str],
    skipped: list[str],
    duplicate_inputs: list[str],
    command_results: list[tuple[str, bool, str]],
) -> None:
    lines = [
        "# Bulk Upload Update Report",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
        f"- Updated rows: {len(updated)}",
        f"- Missing FolderName warnings: {len(missing)}",
        f"- Skipped incomplete rows: {len(skipped)}",
        f"- Duplicate input rows: {len(duplicate_inputs)}",
        "",
        "## Updated",
        "",
    ]
    lines.extend(f"- {folder}" for folder in updated) if updated else lines.append("- None")
    lines.extend(["", "## Missing FolderName", ""])
    lines.extend(f"- {folder}" for folder in missing) if missing else lines.append("- None")
    lines.extend(["", "## Skipped Incomplete Rows", ""])
    lines.extend(f"- {folder}" for folder in skipped) if skipped else lines.append("- None")
    lines.extend(["", "## Duplicate Input Rows", ""])
    lines.extend(f"- {folder}" for folder in duplicate_inputs) if duplicate_inputs else lines.append("- None")
    lines.extend(["", "## Commands", ""])
    for command, ok, output in command_results:
        lines.append(f"- {'OK' if ok else 'FAILED'}: `{command}`")
        if output:
            excerpt = output.replace("\r\n", "\n").strip()
            lines.append("")
            lines.append("```")
            lines.append(excerpt[-1500:])
            lines.append("```")
            lines.append("")
    REPORT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    try:
        _, updated, missing, skipped, duplicate_inputs = update_rows()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    for folder in missing:
        print(f"WARNING: FolderName not found in render_status.csv: {folder}", file=sys.stderr)
    for folder in skipped:
        print(f"WARNING: Skipped incomplete upload_links row: {folder}", file=sys.stderr)
    for folder in duplicate_inputs:
        print(f"WARNING: Duplicate FolderName in upload_links.csv: {folder}", file=sys.stderr)

    command_results = run_website_sync()
    write_report(updated, missing, skipped, duplicate_inputs, command_results)

    print(f"Updated rows: {len(updated)}")
    print(f"Report: {REPORT_MD}")
    print(f"Status CSV: {STATUS_CSV}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
