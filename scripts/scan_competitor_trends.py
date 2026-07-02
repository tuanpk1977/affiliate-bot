from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from modules.competitor_trends import scan_competitors, write_reports  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Discover competitor topics from RSS and sitemaps without copying content.")
    parser.add_argument("--config", default="data/competitors.json")
    parser.add_argument("--publish-root", default="docs")
    parser.add_argument("--reports", default="reports")
    parser.add_argument("--max-items", type=int, default=12)
    parser.add_argument("--delay", type=float, default=1.0)
    args = parser.parse_args()
    competitors = json.loads((ROOT / args.config).read_text(encoding="utf-8"))
    candidates, failures = scan_competitors(
        competitors,
        ROOT / args.publish_root,
        max_items=max(1, args.max_items),
        delay_seconds=max(0.0, args.delay),
    )
    md_path, json_path = write_reports(candidates, failures, ROOT / args.reports)
    production = [
        candidate.__dict__
        for candidate in candidates
        if candidate.trend_score >= 70
        and candidate.recommended_action in {"create", "refresh"}
        and candidate.commercial_intent_score >= 50
    ]
    target = ROOT / "data" / "competitor_topic_candidates.json"
    target.write_text(json.dumps(production, indent=2) + "\n", encoding="utf-8")
    print(f"Competitor candidates: {len(candidates)}")
    print(f"Daily-pipeline candidates: {len(production)}")
    print(f"Failures/warnings: {len(failures)}")
    print(f"Markdown: {md_path}")
    print(f"JSON: {json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
