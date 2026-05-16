from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.social_draft_generator import generate_social_drafts, load_all_social_drafts, summarize_drafts
from modules.social_scheduler import ensure_automation_schedule_config


def main() -> None:
    ensure_automation_schedule_config()
    paths = generate_social_drafts()
    records = load_all_social_drafts()
    summary = summarize_drafts(records)
    platforms = Counter(row.get("platform", "") for row in records)
    languages = Counter(row.get("language", "") for row in records)
    print(f"Social draft generation complete. Files present: {len(paths)}")
    print(f"Total drafts: {summary.get('total', 0)}")
    print(f"English: {languages.get('en', 0)}")
    print(f"Vietnamese: {languages.get('vi', 0)}")
    for platform in ["facebook", "linkedin", "twitter", "short_video"]:
        print(f"{platform}: {platforms.get(platform, 0)}")


if __name__ == "__main__":
    main()
