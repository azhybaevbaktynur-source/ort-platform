"""One-line JSON logging with PII scrubbing."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

_SENSITIVE = ("email", "phone", "password", "token", "code", "answer", "secret", "authorization")
_STD_ATTRS = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {"message", "asctime", "taskName"}


def scrub(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {
            k: ("[redacted]" if isinstance(k, str) and any(s in k.lower() for s in _SENSITIVE) else scrub(v))
            for k, v in obj.items()
        }
    if isinstance(obj, (list, tuple, set)):
        return [scrub(v) for v in obj]
    return obj


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        data: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        extras = {k: v for k, v in record.__dict__.items() if k not in _STD_ATTRS}
        data.update(scrub(extras))
        if record.exc_info:
            data["exc"] = self.formatException(record.exc_info)
        return json.dumps(data, default=str, ensure_ascii=False)


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not any(isinstance(h.formatter, JsonFormatter) for h in logger.handlers):
        h = logging.StreamHandler()
        h.setFormatter(JsonFormatter())
        logger.addHandler(h)
        logger.propagate = False
        if logger.level == logging.NOTSET:
            logger.setLevel(logging.INFO)
    return logger
