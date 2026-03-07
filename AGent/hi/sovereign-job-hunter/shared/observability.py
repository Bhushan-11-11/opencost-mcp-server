from __future__ import annotations

import contextvars
import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_CORRELATION_ID: contextvars.ContextVar[str] = contextvars.ContextVar(
    "correlation_id", default=""
)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "correlation_id": _CORRELATION_ID.get(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=True)


def configure_json_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    root.handlers.clear()
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)
    root.setLevel(level.upper())


def set_correlation_id(correlation_id: str | None = None) -> str:
    cid = correlation_id or str(uuid.uuid4())
    _CORRELATION_ID.set(cid)
    return cid


def redact_secrets(text: str) -> str:
    redacted = text
    for key in [
        "SJH_GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "GITHUB_TOKEN",
    ]:
        value = os.getenv(key)
        if value and value in redacted:
            redacted = redacted.replace(value, "***REDACTED***")
    return redacted


def emit_metric(out_dir: Path, event_name: str, fields: dict[str, Any]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": event_name,
        "correlation_id": _CORRELATION_ID.get(),
        "fields": fields,
    }
    metric_path = out_dir / "metrics.jsonl"
    with metric_path.open("a", encoding="utf-8") as fp:
        fp.write(json.dumps(record, ensure_ascii=True))
        fp.write("\n")


class time_block:
    def __init__(self, out_dir: Path, event_name: str, **fields: Any):
        self.out_dir = out_dir
        self.event_name = event_name
        self.fields = fields
        self._start = 0.0

    def __enter__(self) -> "time_block":
        self._start = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        elapsed_ms = int((time.perf_counter() - self._start) * 1000)
        payload = dict(self.fields)
        payload["duration_ms"] = elapsed_ms
        payload["status"] = "error" if exc else "ok"
        emit_metric(self.out_dir, self.event_name, payload)
