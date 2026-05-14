from __future__ import annotations

import logging

import pandas as pd


LOGGER = logging.getLogger(__name__)


def export_csv(df: pd.DataFrame, path) -> None:
    try:
        df.to_csv(path, index=False)
        LOGGER.info("Exported %s rows to %s", len(df), path)
    except Exception:
        LOGGER.exception("Could not export CSV: %s", path)
        raise
