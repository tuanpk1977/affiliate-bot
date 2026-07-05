from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from modules.performance_tracking import DATA_DIR, write_business_outputs


def main() -> int:
    result = write_business_outputs()
    print(f"Executive dashboard JSON: {DATA_DIR / 'daily_executive_dashboard.json'}")
    print(f"Executive dashboard HTML: {DATA_DIR / 'daily_executive_dashboard.html'}")
    print(f"Master workbook updated: {result['excel']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
