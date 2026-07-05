from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VIDEO_OUTPUT = ROOT / "video_output"
STATUS_CSV = VIDEO_OUTPUT / "render_status.csv"
SUMMARY_MD = VIDEO_OUTPUT / "render_summary.md"
UPLOAD_QUEUE_MD = VIDEO_OUTPUT / "upload_queue.md"
YOUTUBE_CHANNEL_URL = "https://youtube.com/@SmileAIReviewHub"
WEBSITE_URL = "https://smileaireviewhub.com"
AUTHOR = "Nguyen Quoc Tuan"
BRAND = "Smile AI Review Hub"
MIN_VIDEO_BYTES = 1024 * 1024

FIELDNAMES = [
    "FolderName",
    "Category",
    "VideoGenerated",
    "VideoDuration",
    "VideoFile",
    "ThumbnailGenerated",
    "SubtitleGenerated",
    "MetadataGenerated",
    "RenderStatus",
    "UploadStatus",
    "YoutubeVideoUrl",
    "YoutubeChannelUrl",
    "ArticleUrl",
    "WebsiteUrl",
    "Author",
    "Priority",
    "CreatedDate",
    "LastModified",
    "LastRenderDate",
    "Notes",
]

MANUAL_FIELDS = {"UploadStatus", "YoutubeVideoUrl", "ArticleUrl", "Notes"}
SUPPORT_DIRS = {
    "archive",
    "logs",
    "manifests",
    "scripts",
    "shorts",
    "subtitles",
    "thumbnails",
    "videos",
    "voiceovers",
}
ARCHIVE_BUCKETS = {"uploaded", "failed", "manual_review"}

HIGH_PRIORITY = {
    "chatgpt",
    "claude",
    "cursor",
    "windsurf",
    "lovable",
    "bolt",
    "midjourney",
    "runway",
}
MEDIUM_PRIORITY = {
    "surfer-seo",
    "semrush",
    "ahrefs-ai",
    "jasper-ai",
    "copy-ai",
    "grammarly",
}
PRIORITY_ORDER = {"HIGH": 0, "MEDIUM": 1, "LOW": 2, "": 3}

WATCH_MORE_SECTION = """Watch More AI Reviews

YouTube:
https://youtube.com/@SmileAIReviewHub

Website:
https://smileaireviewhub.com
"""


def iso_from_timestamp(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, timezone.utc).isoformat()


def load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def read_existing_rows() -> dict[str, dict[str, str]]:
    if not STATUS_CSV.exists():
        return {}
    with STATUS_CSV.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return {row.get("FolderName", ""): row for row in reader if row.get("FolderName")}


def canonical_slug(folder_name: str) -> str:
    if folder_name.startswith("review-"):
        return folder_name.removeprefix("review-")
    if folder_name.startswith("pricing-"):
        return folder_name.removeprefix("pricing-")
    if folder_name.startswith("category-"):
        return folder_name.removeprefix("category-")
    return folder_name


def priority_for(folder_name: str) -> str:
    slug = canonical_slug(folder_name)
    if slug in HIGH_PRIORITY:
        return "HIGH"
    if slug in MEDIUM_PRIORITY:
        return "MEDIUM"
    return "LOW"


def iter_video_folders() -> list[Path]:
    folders: dict[str, Path] = {}
    for folder in VIDEO_OUTPUT.iterdir():
        if folder.is_dir():
            folders[folder.name] = folder
    archive_root = VIDEO_OUTPUT / "archive"
    for bucket in ARCHIVE_BUCKETS:
        bucket_dir = archive_root / bucket
        if not bucket_dir.exists():
            continue
        for folder in bucket_dir.iterdir():
            if folder.is_dir() and folder.name not in folders:
                folders[folder.name] = folder
    return sorted(folders.values(), key=lambda path: path.name.lower())


def category_for(folder: Path, metadata: dict) -> str:
    if folder.name in SUPPORT_DIRS or folder.name in ARCHIVE_BUCKETS:
        return "SYSTEM"
    if metadata.get("content_type"):
        return str(metadata["content_type"]).upper()
    if folder.name.startswith("review-"):
        return "REVIEW"
    if folder.name.startswith("compare-") or "-vs-" in folder.name:
        return "COMPARISON"
    return "PACKAGE"


def last_modified(folder: Path) -> str:
    latest = folder.stat().st_mtime
    for path in folder.rglob("*"):
        try:
            latest = max(latest, path.stat().st_mtime)
        except OSError:
            continue
    return iso_from_timestamp(latest)


def update_metadata(metadata_path: Path) -> None:
    if not metadata_path.exists():
        return
    metadata = load_json(metadata_path)
    changed = False
    updates = {
        "youtube_channel_url": YOUTUBE_CHANNEL_URL,
        "website_url": WEBSITE_URL,
        "author": AUTHOR,
        "brand": BRAND,
    }
    for key, value in updates.items():
        if metadata.get(key) != value:
            metadata[key] = value
            changed = True
    if changed:
        write_json(metadata_path, metadata)


def add_watch_more_section(script_path: Path) -> None:
    if not script_path.exists():
        return
    text = script_path.read_text(encoding="utf-8", errors="ignore")
    if "Watch More AI Reviews" in text:
        return
    marker_index = text.lower().find("\nauthor")
    section = "\n\n" + WATCH_MORE_SECTION.strip() + "\n"
    if marker_index >= 0:
        text = text[:marker_index].rstrip() + section + text[marker_index:]
    else:
        text = text.rstrip() + section
    script_path.write_text(text, encoding="utf-8")


def folder_row(folder: Path, existing: dict[str, str]) -> dict[str, str]:
    metadata_path = folder / "metadata.json"
    update_metadata(metadata_path)
    add_watch_more_section(folder / "script.txt")

    metadata = load_json(metadata_path)
    mp4_path = folder / "review_video.mp4"
    thumbnail_path = folder / "thumbnail.png"
    subtitles_path = folder / "subtitles.srt"
    vietnamese_subtitles_path = folder / "subtitles_vi.txt"

    video_generated = mp4_path.exists() and mp4_path.stat().st_size > MIN_VIDEO_BYTES
    metadata_generated = metadata_path.exists()
    category = category_for(folder, metadata)
    upload_status = existing.get("UploadStatus") or "NOT_UPLOADED"
    youtube_video_url = existing.get("YoutubeVideoUrl") or ""
    uploaded_with_url = upload_status == "UPLOADED" and bool(youtube_video_url)

    if category == "SYSTEM":
        render_status = "N/A"
    elif video_generated or uploaded_with_url:
        render_status = "DONE"
    elif metadata.get("render_status") == "failed":
        render_status = "FAILED"
    else:
        render_status = "PENDING"

    article_url = str(metadata.get("source_url") or metadata.get("url") or "")
    if not article_url and category not in {"SYSTEM", "PACKAGE"}:
        article_url = f"{WEBSITE_URL}/{folder.name.replace('review-', 'review/')}/"

    row = {
        "FolderName": folder.name,
        "Category": category,
        "VideoGenerated": "YES" if video_generated else "NO",
        "VideoDuration": str(metadata.get("review_video_duration_seconds", "")),
        "VideoFile": str(mp4_path.relative_to(ROOT)) if mp4_path.exists() else "",
        "ThumbnailGenerated": "YES" if thumbnail_path.exists() else "NO",
        "SubtitleGenerated": "YES" if subtitles_path.exists() and subtitles_path.read_text(encoding="utf-8", errors="ignore").strip() and vietnamese_subtitles_path.exists() and vietnamese_subtitles_path.read_text(encoding="utf-8", errors="ignore").strip() else "NO",
        "MetadataGenerated": "YES" if metadata_generated else "NO",
        "RenderStatus": render_status,
        "UploadStatus": "NOT_UPLOADED",
        "YoutubeVideoUrl": "",
        "YoutubeChannelUrl": YOUTUBE_CHANNEL_URL,
        "ArticleUrl": article_url,
        "WebsiteUrl": WEBSITE_URL,
        "Author": AUTHOR,
        "Priority": priority_for(folder.name) if category != "SYSTEM" else "",
        "CreatedDate": iso_from_timestamp(folder.stat().st_ctime),
        "LastModified": last_modified(folder),
        "LastRenderDate": str(metadata.get("render_date") or metadata.get("research_summary_date") or ""),
        "Notes": "",
    }
    for field in MANUAL_FIELDS:
        if existing.get(field):
            row[field] = existing[field]
    return row


def write_status(rows: list[dict[str, str]]) -> None:
    rows = sorted(rows, key=lambda item: item["FolderName"].lower())
    with STATUS_CSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def write_summary(rows: list[dict[str, str]]) -> None:
    package_rows = [row for row in rows if row["Category"] != "SYSTEM"]
    completed = [row for row in package_rows if row["RenderStatus"] == "DONE"]
    pending = [row for row in package_rows if row["RenderStatus"] == "PENDING"]
    failed = [row for row in package_rows if row["RenderStatus"] == "FAILED"]
    missing_thumbnails = [row for row in package_rows if row["ThumbnailGenerated"] != "YES"]
    missing_subtitles = [row for row in package_rows if row["SubtitleGenerated"] != "YES"]
    missing_metadata = [row for row in package_rows if row["MetadataGenerated"] != "YES"]
    uploaded = [row for row in package_rows if row["UploadStatus"] and row["UploadStatus"] != "NOT_UPLOADED"]
    not_uploaded = [row for row in package_rows if row["UploadStatus"] == "NOT_UPLOADED"]
    recommended = failed + pending + [row for row in completed if row["UploadStatus"] == "NOT_UPLOADED"]

    lines = [
        "# Render Summary",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
        f"- Total folders: {len(rows)}",
        f"- Completed videos: {len(completed)}",
        f"- Pending videos: {len(pending)}",
        f"- Failed videos: {len(failed)}",
        f"- Missing thumbnails: {len(missing_thumbnails)}",
        f"- Missing subtitles: {len(missing_subtitles)}",
        f"- Missing metadata: {len(missing_metadata)}",
        f"- Uploaded videos: {len(uploaded)}",
        f"- Not uploaded videos: {len(not_uploaded)}",
        "",
        "## Next 10 Recommended Folders To Process Or Upload",
        "",
    ]
    for row in recommended[:10]:
        lines.append(f"- {row['FolderName']} - {row['RenderStatus']} - {row['UploadStatus']}")
    if not recommended:
        lines.append("- None")
    SUMMARY_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def sort_for_queue(row: dict[str, str]) -> tuple[int, str]:
    return (PRIORITY_ORDER.get(row.get("Priority", ""), 3), row.get("FolderName", "").lower())


def queue_line(row: dict[str, str]) -> str:
    duration = row.get("VideoDuration") or "-"
    article_url = row.get("ArticleUrl") or "-"
    return f"- **{row['Priority']}** - `{row['FolderName']}` - {row['RenderStatus']} - duration: {duration} - {article_url}"


def write_upload_queue(rows: list[dict[str, str]]) -> None:
    package_rows = [row for row in rows if row["Category"] != "SYSTEM"]
    sections = {
        "READY_TO_UPLOAD": [
            row
            for row in package_rows
            if row["RenderStatus"] == "DONE" and row["UploadStatus"] != "UPLOADED" and not row["YoutubeVideoUrl"]
        ],
        "UPLOADED": [
            row
            for row in package_rows
            if row["UploadStatus"] == "UPLOADED" or bool(row["YoutubeVideoUrl"])
        ],
        "FAILED": [row for row in package_rows if row["RenderStatus"] == "FAILED" or row["UploadStatus"] == "FAILED"],
        "MISSING_VIDEO": [row for row in package_rows if row["VideoGenerated"] != "YES"],
        "MISSING_METADATA": [row for row in package_rows if row["MetadataGenerated"] != "YES"],
        "MISSING_THUMBNAIL": [row for row in package_rows if row["ThumbnailGenerated"] != "YES"],
        "MISSING_SUBTITLES": [row for row in package_rows if row["SubtitleGenerated"] != "YES"],
    }
    lines = [
        "# Upload Queue",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
    ]
    for title, section_rows in sections.items():
        lines.extend([f"## {title}", ""])
        sorted_rows = sorted(section_rows, key=sort_for_queue)
        if sorted_rows:
            lines.extend(queue_line(row) for row in sorted_rows)
        else:
            lines.append("- None")
        lines.append("")
    UPLOAD_QUEUE_MD.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    VIDEO_OUTPUT.mkdir(exist_ok=True)
    existing_rows = read_existing_rows()
    rows = []
    seen = set()
    for folder in iter_video_folders():
        rows.append(folder_row(folder, existing_rows.get(folder.name, {})))
        seen.add(folder.name)
    for folder_name, existing in existing_rows.items():
        if folder_name not in seen:
            preserved = {field: existing.get(field, "") for field in FIELDNAMES}
            preserved["RenderStatus"] = existing.get("RenderStatus") or "PENDING"
            preserved["YoutubeChannelUrl"] = existing.get("YoutubeChannelUrl") or YOUTUBE_CHANNEL_URL
            preserved["WebsiteUrl"] = existing.get("WebsiteUrl") or WEBSITE_URL
            preserved["Author"] = existing.get("Author") or AUTHOR
            preserved["Priority"] = existing.get("Priority") or priority_for(folder_name)
            rows.append(preserved)
    write_status(rows)
    write_summary(rows)
    write_upload_queue(rows)
    package_rows = [row for row in rows if row["Category"] != "SYSTEM"]
    done = sum(1 for row in package_rows if row["RenderStatus"] == "DONE")
    pending = sum(1 for row in package_rows if row["RenderStatus"] == "PENDING")
    failed = sum(1 for row in package_rows if row["RenderStatus"] == "FAILED")
    print(f"Scanned folders: {len(rows)}")
    print(f"DONE: {done}")
    print(f"PENDING: {pending}")
    print(f"FAILED: {failed}")
    print(f"Status CSV: {STATUS_CSV}")
    print(f"Summary: {SUMMARY_MD}")


if __name__ == "__main__":
    main()
