from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from modules.ceo_phase2 import write_phase2_outputs


def main() -> int:
    result = write_phase2_outputs()
    print("Phase 2 AI CEO dashboard updated.")
    print(f"CEO dashboard rows: {result['ceo_dashboard']}")
    print(f"ROI analysis rows: {result['roi_analysis']}")
    print(f"AI decision rows: {result['ai_decision_engine']}")
    print(f"Prediction rows: {result['predictions']}")
    print(f"Content calendar rows: {result['content_calendar']}")
    print("Workbook: data/master_dashboard.xlsx")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
