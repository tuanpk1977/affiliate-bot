from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from modules.content_intelligence import build_content_intelligence_summary
from modules.business_intelligence import write_business_intelligence_outputs


def main() -> int:
    summary = build_content_intelligence_summary()
    business = write_business_intelligence_outputs()
    print(f"Intelligence topics: {summary['intelligence_topics']}")
    print(f"Auto priority rows: {summary['auto_priority_rows']}")
    print(f"Business intelligence rows: {business['recommendations']}")
    print("Dashboard: data/content_intelligence_dashboard.html")
    print("Workbook: data/master_dashboard.xlsx")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
