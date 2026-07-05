from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VIDEO = ROOT / "video_output"
BASE_URL = "https://smileaireviewhub.com"
ITEMS = [
    ("Surfer SEO Review 2026: Pricing, Pros, Cons & Best Alternatives", "review/surfer-seo-review-2026", "review-surfer-seo-review-2026", "surfer seo review"),
    ("Surfer SEO Free Trial: Is It Worth Trying in 2026?", "surfer-seo-free-trial", "surfer-seo-free-trial", "surfer seo free trial"),
    ("Surfer SEO Alternatives: Best SEO Content Optimization Tools", "surfer-seo-alternatives", "review-surfer-seo-alternatives", "surfer seo alternatives"),
    ("Surfer SEO vs Frase: Which AI SEO Tool Is Better?", "comparisons/surfer-seo-vs-frase", "compare-surfer-seo-vs-frase", "surfer seo vs frase"),
    ("Surfer SEO vs Clearscope: Best Content Optimization Software", "surfer-seo-vs-clearscope", "surfer-seo-vs-clearscope", "surfer seo vs clearscope"),
    ("Best AI SEO Tools for Content Creators in 2026", "best-ai-seo-tools-2026", "best-ai-seo-tools-2026", "best ai seo tools"),
    ("Best Website Builder for Small Businesses in 2026", "best-website-builder-2026", "best-website-builder-2026", "best website builder for small business"),
    ("Best AI Website Builders Compared: Wix, Webflow, Durable, Framer", "best-ai-website-builders-compared", "best-ai-website-builders-compared", "best ai website builders"),
    ("Best Affiliate Marketing Software for SaaS Companies", "best-affiliate-marketing-software-saas", "best-affiliate-marketing-software-saas", "best affiliate marketing software for saas"),
    ("Trackdesk Review 2026: Affiliate Tracking, Pricing, Pros & Cons", "trackdesk-review-2026", "review-trackdesk-review-2026", "trackdesk review"),
]
CHAPTERS = [
    "00:00 Introduction",
    "00:50 Overview and buyer context",
    "02:10 Key features and workflow",
    "04:20 Pricing and total cost",
    "05:45 Pros and cons",
    "07:15 Best use cases",
    "08:20 Alternatives",
    "09:30 Final verdict",
]


def main() -> None:
    sitemap = (ROOT / "site_output" / "sitemap.xml").read_text(encoding="utf-8")
    rows = []
    for title, path, slug, focus in ITEMS:
        folder = VIDEO / slug
        metadata_path = folder / "metadata.json"
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        fast_audio = folder / "audio" / "voiceover_fast.mp3"
        standard_audio = folder / "audio" / "voiceover.mp3"
        if fast_audio.exists() and not standard_audio.exists():
            shutil.copy2(fast_audio, standard_audio)
        metadata["chapter_timestamps"] = CHAPTERS
        metadata["focus_keyword"] = focus
        metadata["pinned_comment"] = f"Read the full buyer guide: {BASE_URL}/{path}/"
        metadata_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
        required = ["review_video.mp4", "thumbnail.png", "script.txt", "voiceover.txt", "subtitles.srt", "subtitles_vi.srt", "subtitles_vi.txt", "metadata.json", "short_script.txt"]
        missing = [name for name in required if not (folder / name).exists() or (folder / name).stat().st_size == 0]
        rows.append({
            "Title": title,
            "ArticleUrl": f"{BASE_URL}/{path}/",
            "FocusKeyword": focus,
            "VideoFolder": f"video_output/{slug}",
            "VideoFile": f"video_output/{slug}/review_video.mp4",
            "DurationSeconds": metadata.get("review_video_duration_seconds", ""),
            "FileSizeBytes": (folder / "review_video.mp4").stat().st_size if (folder / "review_video.mp4").exists() else 0,
            "Status": "READY" if not missing and metadata.get("render_status") == "success" else "FAILED",
            "MissingFiles": ", ".join(missing),
            "InSitemap": str(f"{BASE_URL}/{path}/" in sitemap).upper(),
            "SchemaStatus": "Article+FAQ+SoftwareApplication",
        })
    report = VIDEO / "gsc_growth_final_report.csv"
    with report.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(report)
    for row in rows:
        print(f"{row['Status']} {row['VideoFolder']} {row['DurationSeconds']}s")


if __name__ == "__main__":
    main()
