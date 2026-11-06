"""Activation codes (docs/phases/S3_ACCESS_DESIGN.md 3): 12 characters of Crockford base32 without I, L, O, U (about
60 bits), shown as `XXXX-XXXX-XXXX`. Input is case-insensitive, ignores spaces and dashes, and reads O as 0, I and L
as 1.

Stored twice, never in plain text: a keyed hash for the redemption lookup (HMAC-SHA256) and an AES-256-GCM sealed copy
with the code id as associated data, so the admin can show an unsold code again. Both keys are derived from SECRET_KEY
with S1's HKDF helper (`mfa.service._derive`, own purposes); SECRET_KEY_PREVIOUS still matches and opens, so rotating
the key loses no code."""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import secrets
import uuid
from typing import Optional

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import settings
from app.lms.core.deps import _signing_keys
from app.lms.mfa.service import _derive

logger = logging.getLogger(__name__)

ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"  # Crockford base32: no I, L, O, U
LENGTH = 12
_READ_AS = {"O": "0", "I": "1", "L": "1"}
_ENC_PREFIX = "v1."
_HMAC_PURPOSE = b"activation-code-lookup"
_ENC_PURPOSE = b"activation-code-seal"


def generate() -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(LENGTH))


def normalize(raw: Optional[str]) -> Optional[str]:
    """The canonical 12 characters, or None when the input cannot be a code (never says which part is wrong)."""
    if not raw or len(raw) > 64:
        return None
    out = []
    for ch in raw.upper():
        if ch in " -\t":
            continue
        ch = _READ_AS.get(ch, ch)
        if ch not in ALPHABET:
            return None
        out.append(ch)
    return "".join(out) if len(out) == LENGTH else None


def display(code: str) -> str:
    return f"{code[0:4]}-{code[4:8]}-{code[8:12]}"


def lookup_hashes(code: str) -> list[str]:
    """The keyed hash under the current key first, then under the previous one."""
    return [hmac.new(_derive(key, _HMAC_PURPOSE), code.encode("ascii"), hashlib.sha256).hexdigest()
            for key in _signing_keys()]


def seal(code: str, code_id: uuid.UUID) -> str:
    nonce = secrets.token_bytes(12)
    sealed = AESGCM(_derive(settings.SECRET_KEY, _ENC_PURPOSE)).encrypt(nonce, code.encode("ascii"),
                                                                       str(code_id).encode("ascii"))
    return _ENC_PREFIX + base64.urlsafe_b64encode(nonce + sealed).decode("ascii")


def unseal(blob: Optional[str], code_id: uuid.UUID) -> Optional[str]:
    if not blob or not blob.startswith(_ENC_PREFIX):
        return None
    raw = base64.urlsafe_b64decode(blob[len(_ENC_PREFIX):].encode("ascii"))
    nonce, sealed = raw[:12], raw[12:]
    for key in _signing_keys():
        try:
            return AESGCM(_derive(key, _ENC_PURPOSE)).decrypt(nonce, sealed, str(code_id).encode("ascii")).decode(
                "ascii")
        except InvalidTag:
            continue
    logger.warning("activation code %s does not open with the current or previous key", code_id)
    return None
