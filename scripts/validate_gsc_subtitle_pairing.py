from __future__ import annotations

import csv
import json
import re
from pathlib import Path

from render_gsc_growth_batch_fast import SLUGS


ROOT = Path(__file__).resolve().parents[1]
VIDEO = ROOT / "video_output"
TIMESTAMP = re.compile(r"\d\d:\d\d:\d\d,\d{3} --> \d\d:\d\d:\d\d,\d{3}")


def timestamps(path: Path) -> list[str]:
    return TIMESTAMP.findall(path.read_text(encoding="utf-8")) if path.exists() else []


def main() -> None:
    rows = []
    for slug in SLUGS:
        folder = VIDEO / slug
        metadata = json.loads((folder / "metadata.json").read_text(encoding="utf-8"))
        english = timestamps(folder / "subtitles.srt")
        vietnamese = timestamps(folder / "subtitles_vi.srt")
        duration = float(metadata.get("review_video_duration_seconds") or 0)
        paired = bool(english) and english == vietnamese
        status = "OK" if paired and 270 <= duration <= 480 else "FAILED"
        rows.append({
            "FolderName": slug,
            "EnglishCues": len(english),
            "VietnameseCues": len(vietnamese),
            "SameTimestamps": "YES" if paired else "NO",
            "DurationSeconds": f"{duration:.3f}",
            "Status": status,
        })
    report = VIDEO / "subtitle_pairing_report.csv"
    with report.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    for row in rows:
        print(f"{row['Status']} {row['FolderName']} cues={row['EnglishCues']} duration={row['DurationSeconds']}")


if __name__ == "__main__":
    main()
