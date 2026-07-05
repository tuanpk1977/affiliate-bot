from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from modules.content_operations import CONTENT_CLUSTER_FIELDS, INTERNAL_LINK_CLUSTER_FIELDS, build_content_clusters
from modules.performance_tracking import DATA_DIR, write_csv, write_json


def main() -> int:
    clusters, links = build_content_clusters()
    write_csv(DATA_DIR / "content_clusters.csv", clusters, CONTENT_CLUSTER_FIELDS)
    write_json(DATA_DIR / "content_clusters.json", clusters)
    write_csv(DATA_DIR / "internal_link_cluster_plan.csv", links, INTERNAL_LINK_CLUSTER_FIELDS)
    write_json(DATA_DIR / "internal_link_cluster_plan.json", links)
    print(f"Content cluster rows: {len(clusters)}")
    print(f"Internal link cluster rows: {len(links)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
