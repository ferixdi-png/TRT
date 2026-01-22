"""Telemetry logging configuration (JSON or plain)."""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone


def configure_logging() -> None:
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    log_format = os.getenv("LOG_FORMAT", "plain").lower()

    if log_format == "json":
        class JsonFormatter(logging.Formatter):
            def format(self, record: logging.LogRecord) -> str:
                payload = {
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "level": record.levelname,
                    "logger": record.name,
                    "message": record.getMessage(),
                }
                return json.dumps(payload, ensure_ascii=False)

        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        root = logging.getLogger()
        root.handlers.clear()
        root.setLevel(log_level)
        root.addHandler(handler)
        return

    logging.basicConfig(
        level=log_level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
