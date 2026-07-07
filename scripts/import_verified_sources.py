from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.knowledge_dashboard import KnowledgeDashboard  # noqa: E402
from modules.knowledge_registry import KnowledgeRegistry, _write_csv as registry_write_csv  # noqa: E402
from modules.source_review import SourceReview  # noqa: E402


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_md(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Normalize the local verified source registry.")
    parser.add_argument("--data-dir", default=str(ROOT / "data"), help="Data directory containing source_registry files.")
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    registry = KnowledgeRegistry(data_dir)
    review = SourceReview(data_dir, registry=registry)
    dashboard = KnowledgeDashboard(data_dir, registry=registry)
    normalized = registry.normalize_rows(registry.load_registry())
    registry.save_registry(normalized)
    review.sync_from_registry(normalized)
    dashboard_report = dashboard.generate()

    report = {
        "records": len(normalized),
        "verified": sum(1 for row in normalized if str(row.get("verification_status", "")) == "verified"),
        "pending": sum(1 for row in normalized if str(row.get("verification_status", "")) == "pending"),
        "needs_review": sum(1 for row in normalized if str(row.get("verification_status", "")) == "needs_review"),
        "expired": sum(1 for row in normalized if str(row.get("verification_status", "")) == "expired"),
        "duplicate": sum(1 for row in normalized if str(row.get("verification_status", "")) == "duplicate"),
        "brands": sorted({str(row.get("brand", "")) for row in normalized if str(row.get("brand", "")).strip()}),
        "average_trust": dashboard_report.get("average_trust", 0),
        "average_freshness": dashboard_report.get("average_freshness", 0),
    }
    _write_json(data_dir / "source_registry_report.json", report)
    registry_write_csv(
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
            f"- Pending: {report['pending']}",
            f"- Needs review: {report['needs_review']}",
            f"- Expired: {report['expired']}",
            f"- Duplicate: {report['duplicate']}",
            f"- Brands: {', '.join(report['brands']) if report['brands'] else 'none'}",
        ],
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
