from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd

from config import settings
from modules.social_draft_generator import STATUS_DIRS, load_all_social_drafts


REPORT_COLUMNS = [
    "total_drafts",
    "approved_count",
    "rejected_count",
    "scheduled_count",
    "posted_count",
    "platform",
    "language",
    "source_url",
    "scheduled_time",
]


def build_report() -> pd.DataFrame:
    records = load_all_social_drafts()
    status_counts = Counter(str(row.get("status", "")).lower() for row in records)
    rows = []
    for row in records:
        rows.append(
            {
                "total_drafts": len(records),
                "approved_count": status_counts.get("approved", 0),
                "rejected_count": status_counts.get("rejected", 0),
                "scheduled_count": status_counts.get("scheduled", 0),
                "posted_count": status_counts.get("posted", 0),
                "platform": row.get("platform", ""),
                "language": row.get("language", ""),
                "source_url": row.get("source_url", ""),
                "scheduled_time": row.get("scheduled_at", ""),
            }
        )
    return pd.DataFrame(rows, columns=REPORT_COLUMNS)


def main() -> None:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    report = build_report()
    output = settings.data_dir / "social_automation_report.csv"
    report.to_csv(output, index=False, encoding="utf-8-sig")
    print(f"Wrote {output}")
    if report.empty:
        print("No social automation drafts found.")
        return
    print(f"Total drafts: {int(report['total_drafts'].iloc[0])}")
    print(f"Approved: {int(report['approved_count'].iloc[0])}")
    print(f"Rejected: {int(report['rejected_count'].iloc[0])}")
    print(f"Scheduled: {int(report['scheduled_count'].iloc[0])}")
    print(f"Posted: {int(report['posted_count'].iloc[0])}")


if __name__ == "__main__":
    main()
