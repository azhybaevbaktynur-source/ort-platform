"""Organization tree (PHASE_9_DESIGN 2.1, 4.1, invariant 4, P9-1): departments are `organizations` rows under a root,
depth <= 2, with a materialized `path` "<root hex>/<dept hex>/<self hex>" (32 lowercase hex characters per segment,
see `models.path_segment`). Org-admin authority over an organization is decided from its **ancestor path** on every
request: an active org admin of any non-deleted organization on the path administers it (so the admin of a root
administers every department below it, never the other way round). Personal organizations are always roots
(`kind = personal`, depth 0, CHECK), so their admin never reaches anyone else's rows.

S1 provides the pure path helpers and the SQL scopes; the department create / move use cases are slice S2.

Path matching is exact: every segment has the same length (32 hex characters, no `%` or `_`), so the descendants of
`p` are exactly `path = p OR path LIKE p || '/%'`."""
from __future__ import annotations

import uuid
from typing import Iterable, Optional

from sqlalchemy import exists, false, literal, or_, select
from sqlalchemy.orm import Session, aliased
from sqlalchemy.sql import ColumnElement

from app.lms.organizations.models import MAX_DEPTH, PATH_SEP, Organization, OrganizationMember, path_segment


# ------------------------------------------------------------------ pure path helpers

def split_path(path: str) -> list[str]:
    return [seg for seg in (path or "").split(PATH_SEP) if seg]


def ancestor_ids(path: str) -> list[uuid.UUID]:
    """Ids on the path, root first and the organization itself last (a pure split, no query)."""
    return [uuid.UUID(seg) for seg in split_path(path)]


def root_id(path: str) -> uuid.UUID:
    return ancestor_ids(path)[0]


def depth_of(path: str) -> int:
    return len(split_path(path)) - 1


def child_path(parent_path: str, child_id) -> str:
    """Path of a new child of the organization at `parent_path`."""
    return f"{parent_path}{PATH_SEP}{path_segment(child_id)}"


def is_within(path: str, ancestor_path: str) -> bool:
    """True when `path` is `ancestor_path` itself or below it."""
    return path == ancestor_path or path.startswith(ancestor_path + PATH_SEP)


def rebase(path: str, old_prefix: str, new_prefix: str) -> str:
    """Path after moving the subtree at `old_prefix` under a new place (`new_prefix` = the moved node's new path)."""
    if not is_within(path, old_prefix):
        raise ValueError("path is not inside the moved subtree")
    return new_prefix + path[len(old_prefix):]


def fits_depth(new_node_depth: int, subtree_height: int) -> bool:
    """A node placed at `new_node_depth` whose deepest descendant is `subtree_height` levels below it."""
    return new_node_depth + subtree_height <= MAX_DEPTH


def within_clause(path_col, ancestor_path) -> ColumnElement[bool]:
    """SQL: `path_col` is `ancestor_path` or below it (`ancestor_path` may be a literal or another column)."""
    if isinstance(ancestor_path, str):
        return or_(path_col == ancestor_path, path_col.like(ancestor_path + PATH_SEP + "%"))
    return or_(path_col == ancestor_path, path_col.like(ancestor_path.concat(literal(PATH_SEP + "%"))))


# ------------------------------------------------------------------ SQL scopes

def _admin_memberships(user_id: str):
    """(organization id, path) of every active org-admin membership in a non-deleted organization."""
    return (
        select(Organization.id, Organization.path)
        .join(OrganizationMember, OrganizationMember.organization_id == Organization.id)
        .where(OrganizationMember.user_id == user_id, OrganizationMember.state == "active",
               OrganizationMember.role == "org_admin", Organization.deleted_at.is_(None))
    )


def administered_scope(user_id: str):
    """SELECT of the ids of every non-deleted organization the user administers: the organizations of their active
    org-admin memberships **plus all their descendants** (design 4.1). Usable as an `IN (...)` subquery."""
    admin = _admin_memberships(user_id).subquery("admin_orgs")
    org = aliased(Organization, name="administered")
    return (
        select(org.id)
        .join(admin, within_clause(org.path, admin.c.path))
        .where(org.deleted_at.is_(None))
        .distinct()
    )


def organizations_administered_by(db: Session, user_id: str) -> list[uuid.UUID]:
    """Ids of the organizations the user administers, descendants included (one SQL), ordered by name."""
    return list(db.execute(
        select(Organization.id).where(Organization.id.in_(administered_scope(user_id)))
        .order_by(Organization.name, Organization.id)
    ).scalars())


def admin_of_any(db: Session, user_id: str, organization_ids: Iterable) -> bool:
    """Active org-admin membership in any of these (non-deleted) organizations (one SQL)."""
    ids = [uuid.UUID(str(i)) for i in organization_ids]
    if not ids:
        return False
    return bool(db.execute(select(exists(
        _admin_memberships(user_id).where(Organization.id.in_(ids))
    ))).scalar())


def is_org_admin_in_tree(db: Session, user_id: str, org: Optional[Organization]) -> bool:
    """The user administers `org` through it or one of its ancestors (one SQL; the path is already loaded)."""
    if org is None or org.deleted_at is not None:
        return False
    return admin_of_any(db, user_id, ancestor_ids(org.path))


def member_tree_roots(db: Session, user_id: str) -> list[uuid.UUID]:
    """Root ids of every tree the user belongs to (any active membership, teacher or org admin, in a non-deleted
    organization; one SQL). The shared-bank scope (design 4.2) reads the banks of these trees."""
    paths = db.execute(
        select(Organization.path).join(OrganizationMember, OrganizationMember.organization_id == Organization.id)
        .where(OrganizationMember.user_id == user_id, OrganizationMember.state == "active",
               Organization.deleted_at.is_(None))
    ).scalars()
    return list(dict.fromkeys(root_id(p) for p in paths))


def subtree_scope(org_path: str):
    """SELECT of the ids of `org_path`'s organization and all its non-deleted descendants."""
    return select(Organization.id).where(within_clause(Organization.path, org_path),
                                         Organization.deleted_at.is_(None))


def trees_scope(root_ids: Iterable):
    """SELECT of the ids of every non-deleted organization inside these roots' trees."""
    roots = [path_segment(r) for r in root_ids]
    if not roots:
        return select(Organization.id).where(false())
    return select(Organization.id).where(
        or_(*(within_clause(Organization.path, r) for r in roots)), Organization.deleted_at.is_(None))


def load_root(db: Session, org: Organization, *, for_update: bool = False) -> Organization:
    """The root of `org`'s tree (`org` itself for a root). `for_update` serializes tree writes per root (4.1)."""
    rid = root_id(org.path)
    if rid == org.id and not for_update:
        return org
    stmt = select(Organization).where(Organization.id == rid)
    if for_update:
        stmt = stmt.with_for_update()
    return db.execute(stmt).scalar_one()
