"""Organization settings (PHASE_9_DESIGN 2.1, 4.3, D7). Settings live on the **root** of a tree; departments store
`{}` and read their root's. The stored JSON is validated by `schemas.OrganizationSettingsIn` (unknown keys rejected);
`effective_settings` fills the defaults. S1 provides the validation and the read helpers; the `PATCH
/org/{org}/settings` route (audited with before/after) is slice S2.

Defaults: `teachers_can_create_courses` false (the platform and personal organizations store true since Phase 6),
`bank_sharing_enabled` false (personal organizations: always false, P9-3), `catalog_defaults` {private,
invite_code}, `application_retention_days` 30 (30-90), `student_invitations_enabled` true."""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.lms.core.errors import Conflict, ValidationFailed
from app.lms.organizations import ids
from app.lms.organizations.models import Organization
from app.lms.organizations.schemas import OrganizationSettingsIn, OrganizationSettingsOut


def effective_settings(root_settings: Optional[dict], kind: str = "school") -> OrganizationSettingsOut:
    """The settings of a tree from its root's stored JSON (unknown or invalid stored keys fall back to defaults)."""
    known = {k: v for k, v in dict(root_settings or {}).items() if k in OrganizationSettingsIn.model_fields}
    values = {}
    for key, value in known.items():  # key by key, so one bad stored value does not reset the others
        try:
            values.update(OrganizationSettingsIn.model_validate({key: value}).model_dump(exclude_none=True))
        except ValueError:
            continue
    out = OrganizationSettingsOut(**values)
    if kind == "personal":
        out.bank_sharing_enabled = False  # P9-3, invariant 2
    return out


def settings_of(db: Session, org: Organization) -> OrganizationSettingsOut:
    """Effective settings for any organization of a tree (a department reads its root; one query for a department,
    none for a root)."""
    from app.lms.organizations.tree import load_root

    root = load_root(db, org)
    return effective_settings(root.settings, root.kind)


def validate_settings_write(org: Organization, patch: OrganizationSettingsIn) -> dict:
    """The stored JSON after merging `patch` into `org.settings`, or the refusal:
    409 `settings_on_root` on a department, 422 `sharing_disabled` when a personal organization turns sharing on."""
    if org.parent_id is not None or org.kind == "department":
        raise Conflict("Settings are set on the root organization", code=ids.E_SETTINGS_ON_ROOT)
    changes = patch.model_dump(exclude_none=True)
    if org.kind == "personal" and changes.get("bank_sharing_enabled"):
        raise ValidationFailed("Personal organizations cannot share banks", code=ids.E_SHARING_DISABLED,
                               details=[{"loc": ["bank_sharing_enabled"], "msg": ids.E_SHARING_DISABLED}])
    merged = {k: v for k, v in dict(org.settings or {}).items() if k in OrganizationSettingsIn.model_fields}
    merged.update(changes)
    OrganizationSettingsIn.model_validate(merged)  # the stored object stays valid as a whole
    return merged
