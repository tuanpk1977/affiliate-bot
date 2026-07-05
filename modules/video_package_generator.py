from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from modules.morning_dashboard import VIDEO_PACKAGE_DAILY_FIELDS
from modules.performance_tracking import BASE_URL, ROOT, read_csv, slugify, write_csv, write_json


VIDEO_OUTPUT_DIR = ROOT / "video_output"

VIDEO_PACKAGE_REPORT_FIELDS = VIDEO_PACKAGE_DAILY_FIELDS

REQUIRED_VIDEO_PACKAGE_FILES = [
    "script.txt",
    "voiceover.txt",
    "scene_plan.json",
    "youtube_title.txt",
    "youtube_description.txt",
    "youtube_tags.txt",
    "thumbnail_prompt.txt",
    "shorts_script.txt",
    "video_metadata.json",
]


def _script(topic: str) -> str:
    return f"""# {topic} Video Review Script

## Hook
If you are researching {topic}, the real question is not whether the software looks impressive. The real question is whether it solves a buyer problem, fits your budget, and has safer alternatives.

## Overview
In this video, we explain what {topic} is, who it is for, and what to verify before buying.

## Features
Focus on workflow fit, integrations, team controls, reporting, and the limits that affect daily use.

## Pricing
Always verify current pricing on the official website. Check seats, usage caps, upgrade triggers, annual discounts, and cancellation terms.

## Pros and Cons
The main advantage is workflow leverage when the use case is clear. The main risk is paying for features that look good in demos but do not improve daily execution.

## Alternatives
Compare at least two alternatives before buying. Look at pricing, reliability, support, and migration risk.

## Verdict
Use {topic} if it solves a specific workflow and the current pricing is justified. Read the full review on Smile AI Review Hub.
"""


def _srt(topic: str) -> str:
    lines = [
        ("00:00:00,000", "00:00:08,000", f"If you are researching {topic}, start with workflow fit."),
        ("00:00:08,000", "00:00:16,000", "Check features, pricing, alternatives, and real buyer risks."),
        ("00:00:16,000", "00:00:24,000", "Always verify current pricing on the official website before buying."),
        ("00:00:24,000", "00:00:32,000", "Read the full review on Smile AI Review Hub."),
    ]
    return "\n\n".join(f"{idx}\n{start} --> {end}\n{text}" for idx, (start, end, text) in enumerate(lines, 1)) + "\n"


def _scenes(topic: str) -> list[dict[str, Any]]:
    sections = ["Hook", "Overview", "Features", "Pricing", "Pros and Cons", "Alternatives", "Verdict"]
    return [
        {
            "scene": index,
            "title": section,
            "duration_seconds": 22,
            "visual": f"Professional Smile AI Review Hub slide for {topic}: {section}",
            "motion": "slow zoom with subtle slide transition",
            "subtitle_rule": "Vietnamese subtitles bottom, English captions smaller and higher if burned in.",
        }
        for index, section in enumerate(sections, 1)
    ]


def generate_video_package(row: dict[str, Any], output_root: Path = VIDEO_OUTPUT_DIR) -> dict[str, Any]:
    topic = str(row.get("topic") or row.get("suggested_title") or "").strip()
    slug = slugify(row.get("slug") or topic)
    run_timestamp = datetime.now().isoformat(timespec="seconds")
    article_type = row.get("article_type", "")
    if not slug:
        return {
            "run_timestamp": run_timestamp,
            "slug": "",
            "topic": topic,
            "article_type": article_type,
            "video_package_path": "",
            "status": "skipped",
            "files_created": 0,
            "required_files_present": "NO",
            "error": "Missing slug.",
        }
    folder = output_root / slug
    folder.mkdir(parents=True, exist_ok=True)
    script = _script(topic)
    scenes = _scenes(topic)
    metadata = {
        "slug": slug,
        "topic": topic,
        "article_url": row.get("published_url") or row.get("article_url") or f"{BASE_URL}/{slug}/",
        "manual_youtube_upload": True,
        "auto_upload_youtube": False,
        "created_at": run_timestamp,
        "subtitle_policy": "Vietnamese bottom subtitles. English captions must not overlap Vietnamese subtitles.",
        "required_files": REQUIRED_VIDEO_PACKAGE_FILES,
    }
    files = {
        "script.txt": script,
        "voiceover.txt": script.replace("#", "").replace("##", ""),
        "youtube_title.txt": f"{topic} Review 2026 | What Buyers Should Know\n",
        "youtube_description.txt": f"Independent review of {topic}. We cover features, pricing checks, pros, cons, alternatives, and buyer fit.\n\nRead full review:\n{BASE_URL}/{slug}/\n\nSubscribe for more AI and SaaS tool reviews.\n",
        "youtube_tags.txt": f"{topic}, AI tools, SaaS review, software review, pricing, alternatives, Smile AI Review Hub\n",
        "thumbnail_prompt.txt": f"Clean YouTube thumbnail for '{topic}', bold readable text, SaaS dashboard style, Smile AI Review Hub branding.\n",
        "shorts_script.txt": f"Considering {topic}? Check workflow fit, pricing limits, alternatives, and real buyer risk before paying. Full review on Smile AI Review Hub.\n",
        "scene_plan.json": json.dumps(scenes, indent=2, ensure_ascii=False) + "\n",
        "video_metadata.json": json.dumps(metadata, indent=2, ensure_ascii=False) + "\n",
        # Compatibility aliases for older helper scripts.
        "video_script.md": script,
        "short_script.txt": f"Considering {topic}? Check workflow fit, pricing limits, alternatives, and real buyer risk before paying. Full review on Smile AI Review Hub.\n",
        "srt_subtitles.srt": _srt(topic),
        "scenes.json": json.dumps(scenes, indent=2, ensure_ascii=False) + "\n",
    }
    for name, content in files.items():
        (folder / name).write_text(content, encoding="utf-8")
    required_present = all((folder / name).exists() and (folder / name).stat().st_size > 0 for name in REQUIRED_VIDEO_PACKAGE_FILES)
    return {
        "run_timestamp": run_timestamp,
        "slug": slug,
        "topic": topic,
        "article_type": article_type,
        "status": "ready_for_manual_upload",
        "video_package_path": str(folder),
        "video_folder": str(folder),
        "files_created": len(REQUIRED_VIDEO_PACKAGE_FILES),
        "required_files_present": "YES" if required_present else "NO",
        "error": "",
    }


def generate_video_packages(selected_path: Path, limit: int = 10, output_root: Path = VIDEO_OUTPUT_DIR) -> list[dict[str, Any]]:
    rows = read_csv(selected_path)
    candidates = [row for row in rows if row.get("decision") in {"WRITE_NOW", "REFRESH_EXISTING", "VIDEO_ONLY"}]
    reports = [generate_video_package(row, output_root=output_root) for row in candidates[:limit]]
    write_csv(ROOT / "data" / "video_package_report.csv", reports, VIDEO_PACKAGE_REPORT_FIELDS)
    write_json(ROOT / "data" / "video_package_report.json", reports)
    return reports
