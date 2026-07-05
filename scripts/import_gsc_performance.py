from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from modules.performance_tracking import (
    DATA_DIR,
    GSC_PAGE_FIELDS,
    GSC_QUERY_FIELDS,
    ensure_template,
    parse_gsc_export,
    write_business_outputs,
    write_csv,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Import a manual Google Search Console CSV export into lifecycle tracking.")
    parser.add_argument("--input", help="Path to GSC CSV export. If omitted, empty templates are created.")
    parser.add_argument("--pages-output", default=str(DATA_DIR / "gsc_performance_pages.csv"))
    parser.add_argument("--queries-output", default=str(DATA_DIR / "gsc_performance_queries.csv"))
    args = parser.parse_args()

    pages_output = Path(args.pages_output)
    queries_output = Path(args.queries_output)
    if not args.input:
        ensure_template(pages_output, GSC_PAGE_FIELDS)
        ensure_template(queries_output, GSC_QUERY_FIELDS)
        print("GSC templates verified. No input CSV was imported.")
    else:
        pages, queries = parse_gsc_export(Path(args.input))
        write_csv(pages_output, pages, GSC_PAGE_FIELDS)
        write_csv(queries_output, queries, GSC_QUERY_FIELDS)
        print(f"Imported GSC rows: pages={len(pages)} queries={len(queries)}")

    result = write_business_outputs()
    print(f"Lifecycle rows: {result['lifecycle']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
