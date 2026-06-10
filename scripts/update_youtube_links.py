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
SUBTITLE_REPORT_CSV = VIDEO_OUTPUT / "subtitle_report.csv"
RENDER_REPORT_CSV = VIDEO_OUTPUT / "render_report.csv"

UPLOAD_FIELDS = ["FolderName", "PageUrl", "YoutubeVideoUrl", "UploadStatus", "Notes"]
MIN_VALID_MP4_BYTES = 1024 * 1024


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    if not path.exists():
        return [], []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    with temp_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    temp_path.replace(path)


def discover_upload_rows(existing_rows: list[dict[str, str]] | None = None) -> list[dict[str, str]]:
    existing_by_folder = {
        str(row.get("FolderName") or "").strip(): row
        for row in (existing_rows or [])
        if str(row.get("FolderName") or "").strip()
    }
    rows = []
    for folder in sorted(VIDEO_OUTPUT.iterdir(), key=lambda path: path.name.lower()):
        video = folder / "review_video.mp4"
        if not folder.is_dir() or not video.exists() or video.stat().st_size <= MIN_VALID_MP4_BYTES:
            continue
        existing = existing_by_folder.get(folder.name, {})
        rows.append(
            {
                "FolderName": folder.name,
                "PageUrl": str(existing.get("PageUrl") or default_page_url(folder.name)).strip(),
                "YoutubeVideoUrl": str(existing.get("YoutubeVideoUrl") or "").strip(),
                "UploadStatus": str(existing.get("UploadStatus") or ("UPLOADED" if existing.get("YoutubeVideoUrl") else "NOT_UPLOADED")).strip(),
                "Notes": str(existing.get("Notes") or "").strip(),
            }
        )
    return rows


def ensure_upload_links_csv() -> list[dict[str, str]]:
    if not UPLOAD_LINKS_CSV.exists():
        rows = discover_upload_rows()
        write_csv(UPLOAD_LINKS_CSV, UPLOAD_FIELDS, rows)
        print(f"Created template: {UPLOAD_LINKS_CSV}")
        return rows

    fieldnames, rows = read_csv(UPLOAD_LINKS_CSV)
    if not fieldnames:
        rows = discover_upload_rows()
        write_csv(UPLOAD_LINKS_CSV, UPLOAD_FIELDS, rows)
        print(f"Created template: {UPLOAD_LINKS_CSV}")
        return rows

    if "FolderName" not in fieldnames or "YoutubeVideoUrl" not in fieldnames:
        raise ValueError(f"{UPLOAD_LINKS_CSV} must include FolderName and YoutubeVideoUrl columns")

    normalized = discover_upload_rows(rows)
    write_csv(UPLOAD_LINKS_CSV, UPLOAD_FIELDS, normalized)
    print(f"Upload template folders: {len(normalized)}")
    return normalized


def default_page_url(folder_name: str) -> str:
    if folder_name.startswith("review-"):
        return f"https://smileaireviewhub.com/review/{folder_name.removeprefix('review-')}/"
    if folder_name.startswith("category-"):
        return f"https://smileaireviewhub.com/category/{folder_name.removeprefix('category-')}/"
    if folder_name.startswith("pricing-"):
        return f"https://smileaireviewhub.com/pricing/{folder_name.removeprefix('pricing-')}/"
    if folder_name.startswith("compare-"):
        return f"https://smileaireviewhub.com/compare/{folder_name.removeprefix('compare-')}/"
    return f"https://smileaireviewhub.com/{folder_name}/" if folder_name else ""


def run_command(command: list[str]) -> tuple[bool, str]:
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
    output = ((result.stdout or "") + (result.stderr or "")).strip()
    return result.returncode == 0, output


def run_required_command(command: list[str], errors: list[str]) -> bool:
    label = " ".join(command)
    print(f"Running: {label}")
    ok, output = run_command(command)
    if output:
        print(output)
    if not ok:
        errors.append(f"{label} failed")
        print(f"ERROR: {label} failed", file=sys.stderr)
    return ok


def read_status_rows() -> tuple[list[str], list[dict[str, str]]]:
    fieldnames, rows = read_csv(STATUS_CSV)
    if not fieldnames:
        raise FileNotFoundError(f"Missing or empty status CSV: {STATUS_CSV}")
    required = {"FolderName", "UploadStatus", "YoutubeVideoUrl", "LastModified", "ArticleUrl"}
    missing = sorted(required - set(fieldnames))
    if missing:
        raise ValueError(f"Missing columns in {STATUS_CSV}: {', '.join(missing)}")
    return fieldnames, rows


def apply_youtube_links(upload_rows: list[dict[str, str]]) -> tuple[list[str], list[str], list[str]]:
    status_fieldnames, status_rows = read_status_rows()
    by_folder = {row.get("FolderName", ""): row for row in status_rows if row.get("FolderName")}
    now = datetime.now(timezone.utc).isoformat()
    updated: list[str] = []
    skipped: list[str] = []
    missing: list[str] = []

    for row in upload_rows:
        folder = str(row.get("FolderName") or "").strip()
        page_url = str(row.get("PageUrl") or "").strip()
        youtube_url = str(row.get("YoutubeVideoUrl") or "").strip()
        if not folder:
            skipped.append("(missing FolderName)")
            continue
        if not youtube_url:
            skipped.append(folder)
            continue
        if not (VIDEO_OUTPUT / folder).is_dir():
            missing.append(folder)
            continue
        status_row = by_folder.get(folder)
        if not status_row:
            missing.append(folder)
            continue
        status_row["UploadStatus"] = "UPLOADED"
        status_row["YoutubeVideoUrl"] = youtube_url
        if page_url:
            status_row["ArticleUrl"] = page_url
        status_row["LastModified"] = now
        row["UploadStatus"] = "UPLOADED"
        updated.append(folder)
        print(f"✓ updated {folder}")

    for folder in missing:
        print(f"⚠ folder not found {folder}")

    write_csv(STATUS_CSV, status_fieldnames, status_rows)
    return updated, skipped, missing


def file_has_text(path: Path) -> bool:
    return path.exists() and bool(path.read_text(encoding="utf-8", errors="ignore").strip())


def write_validation_reports() -> None:
    folders = sorted(
        [folder for folder in VIDEO_OUTPUT.iterdir() if folder.is_dir() and (folder / "metadata.json").exists()],
        key=lambda path: path.name.lower(),
    )
    subtitle_rows = []
    render_rows = []
    for folder in folders:
        english_ok = file_has_text(folder / "subtitles.srt")
        vietnamese_ok = file_has_text(folder / "subtitles_vi.txt")
        subtitle_status = "OK" if english_ok and vietnamese_ok else "WARNING" if english_ok or vietnamese_ok else "FAILED"
        subtitle_rows.append(
            {
                "FolderName": folder.name,
                "EnglishSubtitle": "YES" if english_ok else "NO",
                "VietnameseSubtitle": "YES" if vietnamese_ok else "NO",
                "Status": subtitle_status,
            }
        )

        checks = {
            "Video": (folder / "review_video.mp4").exists() and (folder / "review_video.mp4").stat().st_size > 1024 * 1024,
            "Audio": (folder / "audio" / "voiceover.mp3").exists() and (folder / "audio" / "voiceover.mp3").stat().st_size > 10_000,
            "EnglishSub": english_ok,
            "VietnameseSub": vietnamese_ok,
            "Thumbnail": (folder / "thumbnail.png").exists() and (folder / "thumbnail.png").stat().st_size > 0,
        }
        render_rows.append(
            {
                "FolderName": folder.name,
                **{key: "YES" if value else "NO" for key, value in checks.items()},
                "Status": "READY" if all(checks.values()) else "FAILED",
            }
        )

    write_csv(SUBTITLE_REPORT_CSV, ["FolderName", "EnglishSubtitle", "VietnameseSubtitle", "Status"], subtitle_rows)
    write_csv(RENDER_REPORT_CSV, ["FolderName", "Video", "Audio", "EnglishSub", "VietnameseSub", "Thumbnail", "Status"], render_rows)


def main() -> int:
    errors: list[str] = []
    try:
        upload_rows = ensure_upload_links_csv()
        if not run_required_command([sys.executable, "scripts/update_render_status.py"], errors):
            return 1
        updated, skipped, missing = apply_youtube_links(upload_rows)
        write_csv(UPLOAD_LINKS_CSV, UPLOAD_FIELDS, upload_rows)
        write_validation_reports()
        run_required_command([sys.executable, "build_site.py"], errors)
        if not errors:
            run_required_command([sys.executable, "scripts/sync_site_output_to_docs.py"], errors)
    except Exception as exc:
        errors.append(str(exc))
        print(f"ERROR: {exc}", file=sys.stderr)
        updated, skipped, missing = [], [], []

    print("")
    print("Summary")
    print(f"Folders updated: {len(updated)}")
    print(f"Folders skipped: {len(skipped)}")
    print(f"Errors: {len(errors) + len(missing)}")
    print(f"Status CSV: {STATUS_CSV}")
    print(f"Subtitle report: {SUBTITLE_REPORT_CSV}")
    print(f"Render report: {RENDER_REPORT_CSV}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
