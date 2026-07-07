from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.verified_source_acquisition import VerifiedSourceAcquisition  # noqa: E402


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "brand",
        "slug",
        "source_type",
        "source_name",
        "source_url",
        "source_status",
        "confidence",
        "notes",
        "last_verified_at",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def _write_md(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Normalize the local verified source registry.")
    parser.add_argument("--data-dir", default=str(ROOT / "data"), help="Data directory containing source_registry files.")
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    acquisition = VerifiedSourceAcquisition(
        registry_json=data_dir / "source_registry.json",
        registry_csv=data_dir / "source_registry.csv",
    )
    rows = acquisition.load_registry()
    normalized = acquisition.normalize_rows([row.to_dict() for row in rows])
    _write_json(data_dir / "source_registry.json", normalized)
    _write_csv(data_dir / "source_registry.csv", normalized)

    report = {
        "records": len(normalized),
        "verified": sum(1 for row in normalized if str(row.get("source_status", "")) == "verified"),
        "estimated": sum(1 for row in normalized if str(row.get("source_status", "")) == "estimated"),
        "needs_review": sum(1 for row in normalized if str(row.get("source_status", "")) == "needs_review"),
        "missing": sum(1 for row in normalized if str(row.get("source_status", "")) == "missing"),
        "brands": sorted({str(row.get("brand", "")) for row in normalized if str(row.get("brand", "")).strip()}),
    }
    _write_json(data_dir / "source_registry_report.json", report)
    _write_csv(
        data_dir / "source_registry_report.csv",
        [{"metric": key, "value": ", ".join(value) if isinstance(value, list) else value} for key, value in report.items()],
    )
    _write_md(
        data_dir / "source_registry_report.md",
        [
            "# Verified Source Registry Report",
            "",
            f"- Records: {report['records']}",
            f"- Verified: {report['verified']}",
            f"- Estimated: {report['estimated']}",
            f"- Needs review: {report['needs_review']}",
            f"- Missing: {report['missing']}",
            f"- Brands: {', '.join(report['brands']) if report['brands'] else 'none'}",
        ],
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
