from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.social_scheduler import ensure_automation_schedule_config, schedule_approved_posts


def main() -> None:
    config = ensure_automation_schedule_config()
    scheduled = schedule_approved_posts()
    print("Social scheduler complete.")
    print(f"Daily slots: {', '.join(config.get('daily_slots', []))}")
    print(f"Max posts/day: {config.get('max_posts_per_day')}")
    print(f"Scheduled approved posts: {len(scheduled)}")
    print("Auto posting: disabled in this phase.")


if __name__ == "__main__":
    main()
