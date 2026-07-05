from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from modules.opportunity_forecast import write_opportunity_forecast


def main() -> int:
    forecast = write_opportunity_forecast()
    print(f"Opportunity forecast rows: {len(forecast.rows)}")
    print(f"Estimated monthly traffic: {int(forecast.totals['estimated_monthly_traffic'])}")
    print(f"Estimated monthly revenue: {forecast.totals['estimated_revenue']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
