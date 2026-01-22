"""Basic logging configuration helpers."""
from __future__ import annotations

import logging
import os


def setup_logging(level: int | None = None) -> None:
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    if level is not None:
        log_level = level
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
