"""Phase 11 S6: request log carries no personal data; Sentry is off without a DSN; restore drill helpers."""
import importlib.util
import json
import logging
import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core import sentry
from app.core.config import settings
from app.core.logging import JsonFormatter
from app.core.security import create_access_token
from app.main import app

EMAIL = "sentinel.person@example.org"
PASSWORD = "Sentinel-Pass-1"


class _Capture(logging.Handler):
    def __init__(self):
        super().__init__()
        self.setFormatter(JsonFormatter())
        self.lines = []

    def emit(self, record):
        self.lines.append(self.format(record))


@pytest.fixture
def captured(monkeypatch):
    monkeypatch.setattr(settings, "LOG_SAMPLE_2XX", 1.0)
    handler = _Capture()
    logger = logging.getLogger("app.request")
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    yield handler.lines
    logger.removeHandler(handler)


def test_request_log_has_no_email_ip_query_token_or_body(captured):
    token = create_access_token({"sub": "user-123"})
    client = TestClient(app)
    client.get(
        f"/health?email={EMAIL}&token=abc",
        headers={"Authorization": f"Bearer {token}", "X-Forwarded-For": "203.0.113.77"},
    )
    client.post("/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD})
    client.get(f"/api/v1/courses/{EMAIL}/x?code=SECRETCODE")
    assert len(captured) >= 3
    blob = "\n".join(captured)
    for forbidden in (EMAIL, PASSWORD, "203.0.113.77", "SECRETCODE", "token=abc", token, "?"):
        assert forbidden not in blob, forbidden
    first = json.loads(captured[0])
    assert first["route"] == "/health" and first["status"] == 200 and first["user_id"] == "user-123"
    assert {"request_id", "ms", "method"} <= set(first)


def test_production_logs_are_json_and_masked_and_development_logs_are_plain(monkeypatch):
    from app.core import logging as app_logging
    from app.core.config import settings

    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    assert isinstance(app_logging._formatter(), app_logging.JsonFormatter)
    monkeypatch.setattr(settings, "ENVIRONMENT", "development")
    assert not isinstance(app_logging._formatter(), app_logging.JsonFormatter)


def test_a_forged_token_writes_no_user_id():
    import jwt

    from app.core.request_log import _user_id

    forged = jwt.encode({"sub": "someone-else"}, "not-the-real-key-not-the-real-key", algorithm="HS256")
    assert _user_id({"headers": [(b"authorization", f"Bearer {forged}".encode())]}) is None
    real = create_access_token({"sub": "user-123"})
    assert _user_id({"headers": [(b"authorization", f"Bearer {real}".encode())]}) == "user-123"


def test_2xx_not_logged_when_sampling_is_zero(monkeypatch, captured):
    monkeypatch.setattr(settings, "LOG_SAMPLE_2XX", 0.0)
    TestClient(app).get("/health")
    assert captured == []


def test_formatter_masks_personal_values_in_message_extra_and_traceback():
    logger = logging.getLogger("t.mask")
    handler = _Capture()
    logger.addHandler(handler)
    logger.propagate = False
    try:
        try:
            raise ValueError(f"bad {EMAIL}")
        except ValueError:
            logger.exception(
                "failed for %s password=%s", EMAIL, PASSWORD,
                extra={"note": f"Bearer eyJabcdef.ghijkl.mnopqr {EMAIL}"},
            )
    finally:
        logger.removeHandler(handler)
    blob = handler.lines[0]
    for forbidden in (EMAIL, PASSWORD, "eyJabcdef"):
        assert forbidden not in blob


def test_sentry_not_started_without_dsn(monkeypatch):
    monkeypatch.setattr(settings, "SENTRY_DSN", "")
    sys.modules.pop("sentry_sdk", None)
    assert sentry.init_sentry() is False
    assert "sentry_sdk" not in sys.modules


def test_sentry_scrub_drops_request_data_and_user():
    event = {
        "request": {"data": {"a": 1}, "headers": {"x": "y"}, "query_string": "q", "url": "u"},
        "user": {"email": EMAIL},
    }
    assert sentry._scrub_event(event, {}) == {"request": {"url": "u"}}


def _drill():
    path = Path(__file__).resolve().parents[2] / "scripts" / "restore_drill.py"
    spec = importlib.util.spec_from_file_location("restore_drill", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod, path


def test_restore_drill_helpers_on_local_db_and_needs_url():
    from app.db.session import engine

    mod, path = _drill()
    counts = dict(mod.count_rows(engine))
    assert counts["users"] is not None and counts["grade_events"] is not None
    mod.pick_student(engine)  # runs without error on any local data
    env = {k: v for k, v in os.environ.items() if k != "DRILL_DATABASE_URL"}
    res = subprocess.run([sys.executable, str(path)], env=env, capture_output=True, text=True, timeout=60)
    assert res.returncode == 2
