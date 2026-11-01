"""JSON logs (PHASE_11_DESIGN 7). One line per record; nothing personal is written: emails, bearer tokens and JWTs are
masked in every message, extra field and traceback as a second line of defense (the request log never passes them)."""
from __future__ import annotations

import json
import logging
import re
import sys
from datetime import datetime, timezone

_EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_JWT = re.compile(r"eyJ[A-Za-z0-9_\-]{5,}\.[A-Za-z0-9_\-]{5,}\.[A-Za-z0-9_\-]*")
_BEARER = re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/=\-]+")
_SECRET_KV = re.compile(r"(?i)\b(password|passwd|token|secret|authorization|code)(\"?\s*[:=]\s*\"?)[^\s\",&}]+")
_RESERVED = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {"message", "asctime", "taskName"}


def scrub(text: str) -> str:
    text = _JWT.sub("[token]", text)
    text = _BEARER.sub("[token]", text)
    text = _EMAIL.sub("[email]", text)
    return _SECRET_KV.sub(lambda m: f"{m.group(1)}{m.group(2)}[hidden]", text)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        out = {
            "ts": datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": scrub(record.getMessage()),
        }
        for key, value in record.__dict__.items():
            if key in _RESERVED or key.startswith("_"):
                continue
            out[key] = scrub(value) if isinstance(value, str) else value
        if record.exc_info:
            out["exc"] = scrub(self.formatException(record.exc_info))
        return json.dumps(out, default=lambda o: scrub(str(o)), ensure_ascii=False)


def _formatter() -> logging.Formatter:
    """JSON with masking in production. Plain outside it: the dev-only console email provider must show the address and
    code to the developer, and the browser test seed reads them from this log."""
    from app.core.config import is_production

    return JsonFormatter() if is_production() else logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")


def configure_logging(level: int = logging.INFO) -> None:
    """Idempotent: one stream handler on the root logger. uvicorn's own access log (it prints the query string)
    is silenced; core/request_log.py replaces it."""
    root = logging.getLogger()
    if not any(getattr(h, "_ort_json", False) for h in root.handlers):
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(_formatter())
        handler._ort_json = True  # type: ignore[attr-defined]
        root.addHandler(handler)
    if root.level in (logging.WARNING, logging.NOTSET):
        root.setLevel(level)
    access = logging.getLogger("uvicorn.access")
    access.handlers.clear()
    access.propagate = False
    access.disabled = True
