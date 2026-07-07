from __future__ import annotations

from pathlib import Path


def write_topical_hubs(site_output_dir: Path) -> dict[str, int]:
    """Compatibility shim for legacy build hooks.

    Some branches reference a standalone topical-hub writer while the current
    repository keeps hub generation elsewhere. Returning a stable no-op result
    keeps incremental builds valid without changing page output unexpectedly.
    """

    _ = site_output_dir
    return {"topical_hubs_written": 0}
