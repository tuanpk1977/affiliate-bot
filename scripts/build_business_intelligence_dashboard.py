from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from modules.business_intelligence import write_business_intelligence_outputs
from modules.ceo_phase2 import write_phase2_outputs


def main() -> int:
    result = write_business_intelligence_outputs()
    print("Business intelligence dashboard updated.")
    print(f"Opportunity rows: {result['opportunity']}")
    print(f"Money score rows: {result['money']}")
    print(f"Execution tracker rows: {result['execution']}")
    print(f"Trend momentum rows: {result['momentum']}")
    print(f"Excel formatted: {result['formatted']}")
    phase2 = write_phase2_outputs()
    print("Phase 2 AI CEO dashboard updated.")
    print(f"ROI analysis rows: {phase2['roi_analysis']}")
    print(f"AI decision rows: {phase2['ai_decision_engine']}")
    print("Workbook: data/master_dashboard.xlsx")
    print("HTML dashboard: data/daily_ceo_dashboard.html")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
