"""RFC 4226 HOTP / RFC 6238 TOTP with the standard library only (tests: the RFC 6238 appendix B vectors)."""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from typing import Optional

STEP_SECONDS = 30
DIGITS = 6
WINDOW = 1  # one step either side: a phone clock up to ~30 s off still works


def new_secret() -> str:
    """160 random bits (RFC 4226 recommends at least 128), base32 without padding, as authenticator apps expect."""
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def secret_bytes(secret_b32: str) -> bytes:
    s = secret_b32.strip().replace(" ", "").upper()
    return base64.b32decode(s + "=" * (-len(s) % 8))


def hotp(key: bytes, counter: int, digits: int = DIGITS, digest=hashlib.sha1) -> str:
    mac = hmac.new(key, counter.to_bytes(8, "big"), digest).digest()
    offset = mac[-1] & 0x0F
    value = (int.from_bytes(mac[offset:offset + 4], "big") & 0x7FFFFFFF) % (10 ** digits)
    return f"{value:0{digits}d}"


def step_at(unix_time: float) -> int:
    return int(unix_time) // STEP_SECONDS


def totp(key: bytes, unix_time: float, digits: int = DIGITS, digest=hashlib.sha1) -> str:
    return hotp(key, step_at(unix_time), digits, digest)


def matching_step(key: bytes, code: str, unix_time: float, last_step: Optional[int] = None) -> Optional[int]:
    """The time step (now ± WINDOW) whose code is `code`, never one at or before `last_step` (replay). Every candidate is
    compared in constant time."""
    if len(code) != DIGITS or not code.isdigit():
        return None
    now = step_at(unix_time)
    found = None
    for step in range(now - WINDOW, now + WINDOW + 1):
        if last_step is not None and step <= last_step:
            continue
        if hmac.compare_digest(hotp(key, step), code) and found is None:
            found = step
    return found
