from __future__ import annotations

import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / "video_output" / "review-semrush-vs-ahrefs-2026"
DATA = ROOT / "data"
SITE = ROOT / "site_output"

TITLE = "Semrush vs Ahrefs 2026 | Which SEO Tool Should You Buy?"
DESCRIPTION = """SEO professionals often compare Semrush and Ahrefs.
In this review we compare pricing, keyword research,
backlink analysis, site audits, rank tracking,
AI features, and overall value.

Read full review:
https://smileaireviewhub.com

Subscribe for more AI and SEO tool reviews."""
TAGS = [
    "semrush",
    "ahrefs",
    "semrush vs ahrefs",
    "seo tools",
    "keyword research",
    "backlink analysis",
    "seo software",
    "semrush review",
    "ahrefs review",
    "seo 2026",
    "best seo tools",
    "digital marketing",
    "search engine optimization",
]


def file_ok(path: Path, minimum: int = 1) -> bool:
    return path.exists() and path.stat().st_size >= minimum


def main() -> None:
    metadata_path = FOLDER / "metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata.update(
        {
            "youtube_title": TITLE,
            "title": TITLE,
            "youtube_description": DESCRIPTION,
            "description": DESCRIPTION,
            "youtube_tags": TAGS,
            "tags": TAGS,
            "source_url": "https://smileaireviewhub.com/compare/semrush-vs-ahrefs/",
            "article_url": "https://smileaireviewhub.com/compare/semrush-vs-ahrefs/",
            "focus_keywords": ["semrush vs ahrefs", "semrush review", "ahrefs review", "best seo tools"],
        }
    )
    metadata_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")

    page = SITE / "compare" / "semrush-vs-ahrefs" / "index.html"
    text = page.read_text(encoding="utf-8")
    plain = re.sub(r"<[^>]+>", " ", text)
    word_count = len(re.findall(r"\b[\w'-]+\b", plain))
    sitemap = (SITE / "sitemap.xml").read_text(encoding="utf-8")
    files = {
        "review_video.mp4": file_ok(FOLDER / "review_video.mp4", 1024 * 1024),
        "thumbnail.png": file_ok(FOLDER / "thumbnail.png"),
        "metadata.json": file_ok(metadata_path),
        "script.txt": file_ok(FOLDER / "script.txt"),
        "voiceover.txt": file_ok(FOLDER / "voiceover.txt"),
        "scenes.json": file_ok(FOLDER / "scenes.json"),
        "subtitles.srt": file_ok(FOLDER / "subtitles.srt"),
        "subtitles_vi.srt": file_ok(FOLDER / "subtitles_vi.srt"),
    }
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "url": "https://smileaireviewhub.com/compare/semrush-vs-ahrefs/",
        "status": "READY_FOR_INDEXING" if word_count >= 3000 and all(files.values()) else "FAILED",
        "word_count": word_count,
        "canonical_ok": 'rel="canonical" href="https://smileaireviewhub.com/compare/semrush-vs-ahrefs/' in text,
        "sitemap_ok": "/compare/semrush-vs-ahrefs/" in sitemap,
        "seo_category_link_ok": "/category/seo-tools/" in text,
        "comparisons_link_ok": "/comparisons/" in text,
        "youtube_placeholder_ok": "data-youtube-placeholder" in text,
        "video_folder": str(FOLDER),
        "files": files,
    }
    (DATA / "semrush_vs_ahrefs_2026_indexing_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    fields = list(report.keys())
    csv_report = DATA / "semrush_vs_ahrefs_2026_indexing_report.csv"
    with csv_report.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerow({**report, "files": json.dumps(files)})
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
