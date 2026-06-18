from __future__ import annotations

import csv
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
SITE_OUTPUT = ROOT / "site_output"
VIDEO_OUTPUT = ROOT / "video_output"
PRIMARY_UPLOAD_CSV = DATA_DIR / "upload_links.csv"
FALLBACK_UPLOAD_CSV = VIDEO_OUTPUT / "upload_links.csv"
RENDER_STATUS_CSV = VIDEO_OUTPUT / "render_status.csv"
REPORT_CSV = DATA_DIR / "youtube_links_injected_report.csv"
REPORT_FIELDS = ["slug", "article_url", "youtube_url", "status", "reason"]


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


def upload_csv_path() -> Path:
    return PRIMARY_UPLOAD_CSV if PRIMARY_UPLOAD_CSV.exists() else FALLBACK_UPLOAD_CSV


def row_value(row: dict[str, str], *names: str) -> str:
    normalized = {str(key or "").strip().lower(): value for key, value in row.items()}
    for name in names:
        value = normalized.get(name.lower())
        if value is not None:
            return str(value).strip()
    return ""


def youtube_video_id(url: str) -> str:
    value = (url or "").strip()
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", value):
        return value
    parsed = urlparse(value)
    host = parsed.netloc.lower()
    if "youtu.be" in host:
        candidate = parsed.path.strip("/").split("/", 1)[0]
        return candidate if re.fullmatch(r"[A-Za-z0-9_-]{11}", candidate) else ""
    if "youtube.com" in host:
        query = dict(part.split("=", 1) for part in parsed.query.split("&") if "=" in part)
        candidate = query.get("v", "")
        if re.fullmatch(r"[A-Za-z0-9_-]{11}", candidate):
            return candidate
        match = re.search(r"/(?:embed|shorts)/([A-Za-z0-9_-]{11})", parsed.path)
        if match:
            return match.group(1)
    return ""


def clean_article_path(article_url: str) -> str:
    path = urlparse(article_url).path.strip()
    if not path:
        return ""
    return path if path.endswith("/") else path + "/"


def site_output_page(article_url: str) -> Path | None:
    path = clean_article_path(article_url).strip("/")
    if not path:
        return None
    return SITE_OUTPUT / path / "index.html"


def page_contains_youtube(article_url: str, youtube_url: str) -> bool:
    page = site_output_page(article_url)
    if not page or not page.exists():
        return False
    source = page.read_text(encoding="utf-8", errors="ignore")
    video_id = youtube_video_id(youtube_url)
    return bool(video_id and video_id in source and "youtube-review-card" in source)


def sync_render_status(upload_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    status_fields, status_rows = read_csv(RENDER_STATUS_CSV)
    if not status_fields:
        raise FileNotFoundError(f"Missing or empty render status CSV: {RENDER_STATUS_CSV}")

    by_folder = {row.get("FolderName", "").strip(): row for row in status_rows if row.get("FolderName")}
    by_article = {
        clean_article_path(row.get("ArticleUrl", "")): row
        for row in status_rows
        if clean_article_path(row.get("ArticleUrl", ""))
    }
    now = datetime.now(timezone.utc).isoformat()
    report_rows: list[dict[str, str]] = []
    changed = False

    for upload_row in upload_rows:
        slug = row_value(upload_row, "FolderName", "folder", "slug")
        article_url = row_value(upload_row, "PageUrl", "article_url", "url")
        youtube_url = row_value(upload_row, "YoutubeVideoUrl", "youtube_url", "video_url")
        if not slug and not article_url:
            continue
        if not youtube_url:
            report_rows.append({"slug": slug, "article_url": article_url, "youtube_url": "", "status": "skipped", "reason": "missing YouTube URL"})
            continue
        if not youtube_video_id(youtube_url):
            report_rows.append({"slug": slug, "article_url": article_url, "youtube_url": youtube_url, "status": "skipped", "reason": "invalid YouTube URL"})
            continue

        status_row = by_folder.get(slug) or by_article.get(clean_article_path(article_url))
        if not status_row:
            report_rows.append({"slug": slug, "article_url": article_url, "youtube_url": youtube_url, "status": "not_found", "reason": "no matching render_status row"})
            continue

        if status_row.get("YoutubeVideoUrl", "").strip() == youtube_url and status_row.get("UploadStatus", "").strip().upper() == "UPLOADED":
            status = "already_exists"
            reason = "render_status already has this YouTube URL"
        else:
            status_row["YoutubeVideoUrl"] = youtube_url
            status_row["UploadStatus"] = "UPLOADED"
            if article_url:
                status_row["ArticleUrl"] = article_url
            if "LastModified" in status_fields:
                status_row["LastModified"] = now
            status = "updated"
            reason = "render_status updated"
            changed = True

        report_rows.append({"slug": slug or status_row.get("FolderName", ""), "article_url": article_url or status_row.get("ArticleUrl", ""), "youtube_url": youtube_url, "status": status, "reason": reason})

    if changed:
        write_csv(RENDER_STATUS_CSV, status_fields, status_rows)
    return report_rows


def run_build() -> tuple[bool, str]:
    result = subprocess.run([sys.executable, "build_site.py"], cwd=ROOT, text=True, capture_output=True)
    return result.returncode == 0, ((result.stdout or "") + (result.stderr or "")).strip()


def verify_report_rows(report_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    verified: list[dict[str, str]] = []
    for row in report_rows:
        if row["status"] in {"updated", "already_exists"}:
            article_url = row["article_url"]
            youtube_url = row["youtube_url"]
            page = site_output_page(article_url)
            if page and page.exists() and page_contains_youtube(article_url, youtube_url):
                row = {**row, "status": "already_exists" if row["status"] == "already_exists" else "updated", "reason": f"{row['reason']}; verified in site_output"}
            elif page and page.exists():
                row = {**row, "status": "not_found", "reason": f"{row['reason']}; YouTube section not found after build"}
            else:
                row = {**row, "status": "not_found", "reason": f"{row['reason']}; article HTML not found after build"}
        verified.append(row)
    return verified


def main() -> int:
    path = upload_csv_path()
    _, upload_rows = read_csv(path)
    if not upload_rows:
        write_csv(REPORT_CSV, REPORT_FIELDS, [])
        print(f"No upload rows found: {path}")
        return 1

    report_rows = sync_render_status(upload_rows)
    ok, output = run_build()
    if output:
        print(output)
    if not ok:
        report_rows = [
            {**row, "status": row["status"] if row["status"] not in {"updated", "already_exists"} else "skipped", "reason": f"{row['reason']}; build failed"}
            for row in report_rows
        ]
        write_csv(REPORT_CSV, REPORT_FIELDS, report_rows)
        print(f"Build failed. Report: {REPORT_CSV}")
        return 1

    report_rows = verify_report_rows(report_rows)
    write_csv(REPORT_CSV, REPORT_FIELDS, report_rows)
    counts: dict[str, int] = {}
    for row in report_rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    print(f"Upload CSV: {path}")
    print(f"Report: {REPORT_CSV}")
    print(f"site_output exists: {SITE_OUTPUT.exists()}")
    for status, count in sorted(counts.items()):
        print(f"{status}: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
