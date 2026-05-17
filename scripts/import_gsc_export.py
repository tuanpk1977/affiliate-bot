from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.gsc_performance import run_performance_intelligence


def main() -> int:
    result = run_performance_intelligence()
    print("GSC performance import completed")
    for key, value in result.items():
        print(f"- {key}: {value}")
    print("Input file: data/gsc_performance_import.csv")
    print("Template: data/gsc_performance_import_template.csv")
    print("Outputs: data/gsc_page_performance_report.csv, data/gsc_query_performance_report.csv, data/traffic_performance_report.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
