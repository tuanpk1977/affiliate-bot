from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from modules.content_operations import AUTO_EDITOR_REPORT_FIELDS, optimize_article_text
from modules.performance_tracking import DATA_DIR, read_csv, slugify, write_csv


def main() -> int:
    parser = argparse.ArgumentParser(description="Non-invasive article optimizer for drafts.")
    parser.add_argument("--input", required=True, help="Input article draft file.")
    parser.add_argument("--output", required=True, help="Output optimized draft file.")
    parser.add_argument("--slug", default="", help="Existing slug to preserve.")
    parser.add_argument("--youtube-url", default="", help="Optional YouTube URL for placeholder/link.")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)
    text = input_path.read_text(encoding="utf-8")
    optimized, report = optimize_article_text(text, slug=args.slug or slugify(input_path.stem), youtube_url=args.youtube_url)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(optimized, encoding="utf-8")

    report.update({"input_file": str(input_path), "output_file": str(output_path)})
    report_path = DATA_DIR / "ai_auto_editor_report.csv"
    rows = read_csv(report_path)
    rows.append(report)
    write_csv(report_path, rows, AUTO_EDITOR_REPORT_FIELDS)
    print(f"Optimized draft written: {output_path}")
    print("Report updated: data/ai_auto_editor_report.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
