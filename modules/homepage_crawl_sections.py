from __future__ import annotations

from pathlib import Path


def enrich_homepage_crawl_sections(site_output_dir: Path) -> dict[str, int]:
    """Best-effort homepage post-processor used by the incremental build.

    The legacy build expects this hook to exist. In repositories where the
    homepage crawler enrichment logic has not been implemented yet, keep the
    build stable by returning a no-op result.
    """

    homepage = site_output_dir / "index.html"
    if not homepage.exists():
        return {"homepage_crawl_sections": 0}
    return {"homepage_crawl_sections": 0}
