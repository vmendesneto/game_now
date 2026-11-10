"""GN-015: bounded JSON request logs without source URLs, payloads or credentials."""
from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
from uuid import uuid4


DEFAULT_LOG = Path(__file__).resolve().parents[1] / "data" / "game_now.log"


class JsonRequestFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "event": record.getMessage(),
        }
        entry.update(getattr(record, "safe_details", {}))
        return json.dumps(entry, ensure_ascii=False, separators=(",", ":"))


def request_logger(path: str | Path | None = None, *,
                   max_bytes: int = 2_000_000, backup_count: int = 3) -> logging.Logger:
    destination = Path(path or os.environ.get("GAME_NOW_LOG_PATH", DEFAULT_LOG))
    destination.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("game_now.http." + uuid4().hex)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    handler = RotatingFileHandler(destination, maxBytes=max_bytes,
                                  backupCount=backup_count, encoding="utf-8")
    handler.setFormatter(JsonRequestFormatter())
    logger.addHandler(handler)
    return logger
