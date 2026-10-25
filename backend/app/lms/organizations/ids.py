"""Fixed organization ids (PHASE_6_DESIGN section 4). Migration 0008 copies these formulas; keep them identical."""
from __future__ import annotations

import hashlib
import uuid

ORG_NS = uuid.uuid5(uuid.NAMESPACE_URL, "https://ort-platform/lms/organizations")


def platform_org_id() -> uuid.UUID:
    return uuid.uuid5(ORG_NS, "org:platform")


def personal_org_id(user_id: str) -> uuid.UUID:
    return uuid.uuid5(ORG_NS, f"org:personal:{user_id}")


def personal_org_slug(user_id: str) -> str:
    return "t-" + hashlib.sha256(str(user_id).encode("utf-8")).hexdigest()[:12]
