from __future__ import annotations

import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VIDEO = ROOT / "video_output"
REPORT = VIDEO / "next_seo_review_batch_report.csv"
MANIFEST = VIDEO / "next_seo_review_batch_2026.json"
REQUIRED = ["review_video.mp4", "metadata.json", "script.txt", "subtitles.srt", "subtitles_vi.srt", "subtitles_vi.txt", "thumbnail.png", "thumbnail_text.txt"]
SLUGS = [
    "hubspot-review-2026",
    "constant-contact-review-2026",
    "aweber-review-2026",
    "moz-review-2026",
    "ubersuggest-review-2026",
    "serpstat-review-2026",
    "wordtune-review-2026",
    "jasper-ai-review-2026",
    "unbounce-review-2026",
    "leadpages-review-2026",
]


def main() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.exists() else {
        "reviews": [{"slug": slug, "video_folder": f"review-{slug}"} for slug in SLUGS]
    }
    with (VIDEO / "render_status.csv").open("r", encoding="utf-8-sig", newline="") as handle:
        status_by_folder = {row["FolderName"]: row for row in csv.DictReader(handle)}
    rows = []
    for item in manifest["reviews"]:
        folder_name = item["video_folder"]
        folder = VIDEO / folder_name
        metadata_path = folder / "metadata.json"
        metadata = json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path.exists() else {}
        status = status_by_folder.get(folder_name, {})
        video = folder / "review_video.mp4"
        rows.append(
            {
                "ArticleUrl": f"https://smileaireviewhub.com/{item['slug']}/",
                "VideoFolder": folder_name,
                "VideoDuration": str(status.get("VideoDuration") or metadata.get("video_duration_seconds") or metadata.get("duration_seconds") or ""),
                "FileSizeMB": f"{video.stat().st_size / 1024 / 1024:.2f}" if video.exists() else "",
                "AllRequiredFiles": "YES" if all((folder / name).exists() and (folder / name).stat().st_size > 0 for name in REQUIRED) else "NO",
            }
        )
    with REPORT.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(REPORT)
    for row in rows:
        print(f"{row['VideoFolder']}: files={row['AllRequiredFiles']} duration={row['VideoDuration']} size={row['FileSizeMB']} MB")


if __name__ == "__main__":
    main()
