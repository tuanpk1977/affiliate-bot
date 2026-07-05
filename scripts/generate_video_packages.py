from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from modules.video_package_generator import generate_video_packages


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate manual YouTube video packages for selected topics. No upload is performed.")
    parser.add_argument("--selected", default="data/today_selected_topics.csv", help="Selected topics CSV.")
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()

    reports = generate_video_packages(Path(args.selected), limit=args.limit)
    print(f"Video package report rows: {len(reports)}")
    print("Report: data/video_package_report.csv")
    for row in reports:
        print(f"- {row.get('slug')}: {row.get('status')} -> {row.get('video_folder')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
