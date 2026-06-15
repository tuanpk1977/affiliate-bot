from __future__ import annotations

import csv
import json
import shutil
import xml.etree.ElementTree as ET
from datetime import date, datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site_output"
DOCS = ROOT / "docs"
VIDEO = ROOT / "video_output"
BASE = "https://smileaireviewhub.com"
SLUGS = [
    "skillspector-review-2026",
    "ai-design-software-review",
    "ai-video-software-review",
    "ai-writing-software-review",
    "automation-software-comparison",
    "ai-tools-in-2026-what-each-platform-does-best-in-real-world-workflows",
    "ai-assistant-software-comparison",
    "aisuite-review-2026",
    "best-ai-assistant-software",
    "ai-coding-software-comparison",
]
NS = "http://www.sitemaps.org/schemas/sitemap/0.9"


def update_sitemap() -> None:
    path = SITE / "sitemap.xml"
    tree = ET.parse(path)
    root = tree.getroot()
    existing = {
        node.text.strip()
        for node in root.findall(f"{{{NS}}}url/{{{NS}}}loc")
        if node.text
    }
    for slug in SLUGS:
        url = f"{BASE}/{slug}/"
        if url in existing:
            continue
        item = ET.SubElement(root, f"{{{NS}}}url")
        ET.SubElement(item, f"{{{NS}}}loc").text = url
        ET.SubElement(item, f"{{{NS}}}lastmod").text = date.today().isoformat()
    ET.register_namespace("", NS)
    tree.write(path, encoding="utf-8", xml_declaration=True)
    shutil.copy2(path, DOCS / "sitemap.xml")


def srt_cues(path: Path) -> int:
    return path.read_text(encoding="utf-8", errors="ignore").count("-->")


def main() -> None:
    update_sitemap()
    rows = []
    failures = []
    for slug in SLUGS:
        folder = VIDEO / slug
        metadata = json.loads((folder / "metadata.json").read_text(encoding="utf-8"))
        video = folder / "review_video.mp4"
        article = DOCS / slug / "index.html"
        image = DOCS / "assets" / "og" / "pages" / f"{slug}.png"
        en = srt_cues(folder / "subtitles.srt")
        vi = srt_cues(folder / "subtitles_vi.srt")
        ready = video.exists() and video.stat().st_size > 100_000 and article.exists() and image.exists() and en > 0 and en == vi
        if not ready:
            failures.append(slug)
        rows.append(
            {
                "Title": metadata.get("title", slug),
                "ArticleUrl": f"{BASE}/{slug}/",
                "VideoFolder": f"video_output/{slug}",
                "DurationSeconds": metadata.get("review_video_duration_seconds", ""),
                "VideoSizeMB": f"{video.stat().st_size / 1024 / 1024:.2f}" if video.exists() else "0",
                "EnglishCues": en,
                "VietnameseCues": vi,
                "FeatureImage": "YES" if image.exists() else "NO",
                "Status": "READY" if ready else "FAILED",
            }
        )
    report = VIDEO / "trending_topics_final_report.csv"
    with report.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    (VIDEO / "trending_topics_final_report.json").write_text(
        json.dumps({"generated_at": datetime.now(timezone.utc).isoformat(), "failures": failures, "items": rows}, indent=2),
        encoding="utf-8",
    )
    print(f"Final report: {report}")
    print(f"READY: {len(rows) - len(failures)}")
    print(f"FAILED: {len(failures)}")
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
