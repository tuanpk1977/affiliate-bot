from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.research_intelligence import ResearchIntelligencePlatform  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run offline research enrichment for queued topics.")
    parser.add_argument("--slug", default="", help="Optional single slug to enrich.")
    args = parser.parse_args()

    platform = ResearchIntelligencePlatform()
    if args.slug:
        result = platform.run_enrichment(topics=[{"slug": args.slug, "topic": args.slug.replace("-", " ")}])
    else:
        result = platform.run_enrichment()
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
