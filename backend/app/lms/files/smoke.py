"""R2 smoke check (Phase 5, P5-12): put a fixed 1-px WebP, HEAD it, read it back from R2_PUBLIC_BASE_URL over HTTPS,
delete it. Used by `POST /platform/storage/smoke` and the CLI `python -m app.lms.files.smoke`.

No `assets` row is written; the probe object is deleted with `R2StorageService.delete_object_unsafe` (its ONLY
caller), and not at all if some asset references the same key. Errors carry the step and the S3 error code or the
exception class only: never credentials, never the endpoint URL."""
from __future__ import annotations

import base64
import hashlib
import json
import sys
import time
from typing import Callable, Optional
from urllib.parse import urlparse

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.lms.files.storage import IMMUTABLE_CACHE, R2StorageService, blob_key

PROBE_WEBP = base64.b64decode("UklGRh4AAABXRUJQVlA4TBEAAAAvAAAAAAfQ3EI0sP+BiOh/AAA=")  # 1x1 lossless WebP
PROBE_SHA = hashlib.sha256(PROBE_WEBP).hexdigest()
PROBE_KEY = blob_key(PROBE_SHA)
HTTP_TIMEOUT_S = 10.0


def _http_client() -> httpx.Client:
    """Seam for tests (httpx.MockTransport)."""
    return httpx.Client(timeout=HTTP_TIMEOUT_S, follow_redirects=False)


def _err(step: str, exc: Exception) -> str:
    code = getattr(exc, "response", None)
    code = code.get("Error", {}).get("Code") if isinstance(code, dict) else None
    return f"{step}_failed: {code or type(exc).__name__}"


def is_r2dev(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host == "r2.dev" or host.endswith(".r2.dev")


def _referenced(db: Optional[Session]) -> bool:
    if db is None:
        return False
    from app.lms.files.models import Asset

    return db.scalar(select(Asset.id).where(Asset.storage_key == PROBE_KEY).limit(1)) is not None


def run_smoke(storage: R2StorageService, db: Optional[Session] = None,
              http_factory: Optional[Callable[[], httpx.Client]] = None) -> dict:
    t0 = time.monotonic()
    res = {"put_ok": False, "head_ok": False, "public_read_ok": False, "public_url": None, "status_code": None,
           "deleted": False, "latency_ms": 0, "error": None}
    errors: list[str] = []
    ops_a = ops_b = 0
    bucket = storage.bucket
    try:
        storage.client.put_object(Bucket=bucket, Key=PROBE_KEY, Body=PROBE_WEBP, ContentType="image/webp",
                                  CacheControl=IMMUTABLE_CACHE)
        res["put_ok"] = True
    except Exception as e:  # noqa: BLE001
        errors.append(_err("put", e))
    ops_a += 1
    if res["put_ok"]:
        try:
            head = storage.client.head_object(Bucket=bucket, Key=PROBE_KEY)
            res["head_ok"] = int(head.get("ContentLength", len(PROBE_WEBP))) == len(PROBE_WEBP)
            if not res["head_ok"]:
                errors.append("head_failed: size_mismatch")
        except Exception as e:  # noqa: BLE001
            errors.append(_err("head", e))
        ops_b += 1
        url = storage.public_url(PROBE_KEY)
        res["public_url"] = url
        if not url:
            errors.append("public_read_failed: R2_PUBLIC_BASE_URL not set")
        elif not url.lower().startswith("https://"):
            errors.append("public_read_failed: R2_PUBLIC_BASE_URL is not https")
        else:
            try:
                with (http_factory or _http_client)() as client:
                    r = client.get(url)
                res["status_code"] = r.status_code
                res["public_read_ok"] = r.status_code == 200 and r.content == PROBE_WEBP
                if not res["public_read_ok"]:
                    errors.append(f"public_read_failed: HTTP {r.status_code}")
            except Exception as e:  # noqa: BLE001
                errors.append(_err("public_read", e))
            ops_b += 1
        if _referenced(db):
            errors.append("delete_skipped: key referenced by an asset")
        else:
            try:
                storage.delete_object_unsafe(PROBE_KEY)
                res["deleted"] = True
            except Exception as e:  # noqa: BLE001
                errors.append(_err("delete", e))
    res["latency_ms"] = int((time.monotonic() - t0) * 1000)
    res["error"] = "; ".join(errors) or None
    if db is not None:
        try:
            from app.lms.files.usage import record_ops

            record_ops(class_a=ops_a, class_b=ops_b)
        except Exception:  # noqa: BLE001  (accounting never fails the check)
            pass
    return res


def ok(res: dict) -> bool:
    return bool(res["put_ok"] and res["head_ok"] and res["public_read_ok"] and res["deleted"])


def main() -> int:
    """CLI: reads R2_* from the environment / settings; prints the result JSON (never the keys)."""
    try:
        storage = R2StorageService()
    except Exception as e:  # noqa: BLE001
        print(json.dumps({"error": f"config_failed: {e}"}))
        return 2
    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        try:
            db.execute(select(1))
        except Exception:  # noqa: BLE001  (no database: still check R2)
            db.close()
            db = None
        res = run_smoke(storage, db)
    finally:
        if db is not None:
            db.close()
    res["bucket"] = storage.bucket
    res["public_base_is_r2dev"] = is_r2dev(settings.R2_PUBLIC_BASE_URL)
    print(json.dumps(res, indent=2))
    return 0 if ok(res) else 1


if __name__ == "__main__":
    sys.exit(main())
