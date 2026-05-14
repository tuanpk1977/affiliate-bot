from __future__ import annotations

import logging
import os
from datetime import datetime


def ensure_dirs() -> None:
    for path in [
        "data/input",
        "data/output",
        "data/logs",
    ]:
        os.makedirs(path, exist_ok=True)


def setup_logging() -> None:
    logging.basicConfig(
        filename="data/logs/bot.log",
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")