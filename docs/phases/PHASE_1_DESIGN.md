# Phase 1 design: courses, enrollment, authorization

**Status**: design for implementation, 2026-10-22 (architect). Builds on Phase 0 interfaces as they exist on `phase-0/foundations` (`app/core/authz.py`, `app/core/route_inventory.py`, `app/lms/core/*`, Alembic `0001_baseline`).
**Sources**: `IMPLEMENTATION_PLAN.md` Phase 1 and section 0 gates, `LMS_ARCHITECTURE.md` sections 1, 3, 10, `PRODUCT_DECISIONS.md` (teachers 2026-10-22).
**Rule for implementers**: anything not stated here is out of scope. If a brief and this doc disagree, ask the orchestrator.

---

## 1. Decisions (defaults taken; record them in `PRODUCT_DECISIONS.md` at merge)

| # | Decision | Reason |
|---|---|---|
| P1-1 | Join code: 8 chars from `23456789ABCDEFGHJKMNPQRSTUVWXYZ` (31 symbols, no 0/1/I/L/O), `secrets.choice`. Stored uppercase; input normalized by uppercasing and removing spaces and `-`. UI shows `ABCD-EFGH`. | 31^8 ≈ 8.5·10^11 makes guessing hopeless under the rate limits; no look-alike characters for students typing from a board. |
| P1-2 | Every course always has a join code (`NOT NULL UNIQUE`); it only works while `status=published`, `enrollment_mode=invite_code`, not deleted. Regenerating replaces it at once. | One code path, no null handling; switching modes back and forth keeps the same code. |
| P1-3 | Phase 1 accepts only `enrollment_mode ∈ {invite_code, closed}` (default `invite_code`). `open`, `form_auto`, `form_review` are allowed by the CHECK but rejected by the API until Phase 7. | An open course needs a catalog or preview page to be found; that is Phase 7. |
| P1-4 | `enrollment_limit` (nullable, 1..10000) caps **active students** only; staff never count. It cannot be set below the current active-student count (409). | Teachers limit class size, not co-teachers. |
| P1-5 | All join failures (unknown code, draft, concluded, deleted, closed mode, course full, malformed input) return the same 404 `join_code_invalid` with the same message. | No code-validity oracle. Teachers see the count in Settings. |
| P1-6 | Re-joining revives the same enrollment row as `student/active` (old role is not restored), keeps its id, logs `rejoined`. A teacher-removed student can rejoin with a valid code; the teacher's tool to stop that is "regenerate code". | Canvas behaviour; history follows the row. Blocking is a Phase 7 feature. |
| P1-7 | Roster visibility: teachers and assistants see the full roster (name, email, role, state, dates). Students see only staff (display name + role), never other students and never emails. | Minors' privacy; students need to know who teaches. |
| P1-8 | Only the owner can: delete, restore, transfer ownership, remove or demote another teacher, or make someone a teacher. Any teacher can manage students and assistants. Assistants cannot manage the roster. | Clear single accountability; prevents co-teacher takeover. |
| P1-9 | Ownership transfer target must already be an `active teacher` enrollment in the course, with `teacher_status=approved` and not disabled. The old owner stays a teacher (and can then leave). Platform admins can transfer to any approved, enabled user (enrollment created or revived as teacher). | Owner powers only go to vetted teachers. |
| P1-10 | Teacher-status revoke: blocks creating courses, receiving ownership, and being made `teacher` in any course. Existing courses and enrollments are unchanged (the person keeps managing them). Admin may then moderate the courses. | Architecture section 3: revoke does not delete courses. |
| P1-11 | `role="admin"` users get `is_platform_admin=true` **and** `teacher_status='approved'` in the data migration. New code never reads `users.role`. `make_admin.py` sets both `role='admin'` (old app) and `is_platform_admin=true`; `--revoke` clears both. No API grants platform admin. | The owner already authors exams; platform admin is a script-only power. |
| P1-12 | Platform admins get **no** bypass inside `/courses/*` routes; all admin access goes through `/platform/*`, which checks `is_platform_admin` from the DB and writes the audit log (including roster views). | "Never silent": one audited entry point for admin power. |
| P1-13 | Account disable: `users.disabled_at` set. Effect: every API call (old and new) returns 401, login returns 403 `account_disabled`. Enrollments and owned courses are untouched. Admin cannot disable self or another platform admin. Re-enable clears the fields. | Immediate effect because `get_current_user` reads the DB on every request. |
| P1-14 | Teacher requests: one `pending` per user (partial unique index), max 3 per user per 24 h. Rejection sets `teacher_status='none'` (user may ask again later). No emails in Phase 1; the admin nav shows the pending count. | Simple queue; email notifications later. |
| P1-15 | Rate limits are **DB-backed fixed windows** (`rate_limit_buckets`, atomic `INSERT … ON CONFLICT DO UPDATE … RETURNING count`), committed on a separate connection so they survive the request's rollback. | Works across several Render workers with no Redis; costs one indexed write per limited call. |
| P1-16 | Numbers: join by code: per user 10 / 10 min and 30 / 24 h (all attempts); per IP 60 / 10 min (**failures only**, so a school behind one NAT can join in a burst). Teacher request: 3 / 24 h per user. Add staff by email: 30 / h per actor. 429 `rate_limited` with `details.retry_after_seconds`. | User limit is the main defense (accounts need email verification); IP limit is defense in depth. |
| P1-17 | Client IP = `X-Forwarded-For` entry at position `-RATE_LIMIT_PROXY_HOPS` from the right (setting, default 2 for Vercel rewrite → Render), else `request.client.host`. Stored only as `sha256(SECRET_KEY + ip)[:32]`. | XFF is spoofable at the left; the hop count picks the address our proxies wrote. Verify on staging (open question Q1). |
| P1-18 | Course languages stored as JSON list (not `text[]`), validated ⊆ `en/ru/ky`, unique, non-empty; `default_language ∈ languages`; `title[default_language]` must be non-empty; title/description keys ⊆ `languages`. | Same model works on SQLite and PG. |
| P1-19 | Lifecycle: `draft → published` (publish), `published → draft` (unpublish, only with 0 active students, else 409 `has_students`), `published → concluded` (conclude), `concluded → published` (reopen). Soft delete from any status; restore returns to `draft`. No automatic conclude by `ends_at` in Phase 1. | Explicit, testable state machine. |
| P1-20 | Admin audit log fields: `id, created_at, actor_id, action, target_type, target_id, reason, details(JSON, ids and before/after values only, no emails/names), ip_hash, request_id`. Append-only (no update/delete API). | Enough to answer "who did what to whom, when, why" without storing PII twice. |
| P1-21 | Enrollment history: `enrollment_events` written for every create/state/role/ownership change, in the same transaction as the change. Teachers do not get a UI for it in Phase 1 (data only). | Required by architecture; UI is cheap later. |
| P1-22 | New endpoints use the LMS error shape `{"error":{code,message,details}}`; the frontend maps `code` to `lms.errors.<code>`. Old endpoints keep `detail`. | Phase 0 error contract. |
| P1-23 | Visibility `private|catalog` is stored and editable by the owner/teachers but has no effect until Phase 7; admin "unlist" sets `visibility=private` and `unlisted_by_admin_at`, which blocks teachers from setting `catalog` (409 `unlisted_by_admin`) until admin relists. | Plan lists "unlist from catalog" in Phase 1 admin. |

## 2. Schema and migration

All new models use SQLAlchemy 2.0 `Mapped` style, `UUIDPKMixin`, `TimestampMixin`, `JSONType`. FK columns to `users.id` are `String(64)` (users ids are `usr_<12 hex>`). Constraint names are the short suffix; Phase 0's naming convention adds the prefix (e.g. `ck_courses_status_valid`). All CHECKs are plain `IN (...)` / comparisons, valid on SQLite and PG. Partial indexes use both `postgresql_where=` and `sqlite_where=`.

### 2.1 `users` (old model `app/models/user.py`, add columns; keep classic `Column` style)

| column | type | null | default | notes |
|---|---|---|---|---|
| `is_platform_admin` | Boolean | no | `False`, `server_default=sa.false()` | only `make_admin.py` sets it |
| `teacher_status` | String(16) | no | `'none'`, `server_default='none'` | CHECK `teacher_status IN ('none','pending','approved','revoked')` name `teacher_status_valid` |
| `locale` | String(2) | yes | – | CHECK `locale IS NULL OR locale IN ('en','ru','ky')` name `locale_valid` |
| `age_band` | String(16) | yes | – | reserved; CHECK `age_band IS NULL OR age_band IN ('under_14','14_17','18_plus')` |
| `disabled_at` | DateTime(tz) | yes | – | |
| `disabled_by_id` | String(64) FK `users.id` ON DELETE SET NULL | yes | – | |
| `disabled_reason` | String(500) | yes | – | |

Index: `ix_users_teacher_status` on `teacher_status` (admin filter). `role` column untouched.

### 2.2 `courses` (`app/lms/courses/models.py`, `Course(UUIDPKMixin, TimestampMixin, SoftDeleteMixin, Base)`)

| column | type | null | default / constraint |
|---|---|---|---|
| `owner_id` | String(64) FK users ON DELETE RESTRICT | no | index `ix_courses_owner_id` |
| `title` | JSONType | no | LocalizedText, ≤200 chars per value |
| `description` | JSONType | yes | LocalizedText, ≤5000 |
| `languages` | JSONType | no | list, validated in service/schema |
| `default_language` | String(2) | no | CHECK `IN ('en','ru','ky')` |
| `status` | String(16) | no | `'draft'`; CHECK `IN ('draft','published','concluded')` |
| `visibility` | String(16) | no | `'private'`; CHECK `IN ('private','catalog')` |
| `enrollment_mode` | String(16) | no | `'invite_code'`; CHECK `IN ('closed','open','invite_code','form_auto','form_review')` |
| `join_code` | String(16) | no | `UNIQUE` (`uq_courses_join_code`) |
| `join_code_rotated_at` | DateTime(tz) | yes | |
| `enrollment_limit` | Integer | yes | CHECK `enrollment_limit IS NULL OR (enrollment_limit >= 1 AND enrollment_limit <= 10000)` |
| `starts_at`, `ends_at` | DateTime(tz) | yes | CHECK `starts_at IS NULL OR ends_at IS NULL OR ends_at > starts_at` |
| `settings` | JSONType | no | ORM default `dict` |
| `copied_from_id` | Uuid FK courses ON DELETE SET NULL | yes | reserved |
| `published_at`, `concluded_at` | DateTime(tz) | yes | |
| `unlisted_by_admin_at` | DateTime(tz) | yes | |
| `deleted_at`, `deleted_by_id` | from mixin; override `deleted_by_id` with FK users ON DELETE SET NULL | yes | |

Indexes: `ix_courses_status_created_at (status, created_at)`, `ix_courses_deleted_at (deleted_at)`. (`default_grading_scheme_version_id` arrives in Phase 4.)

### 2.3 `enrollments` (`app/lms/enrollments/models.py`)

| column | type | null | default / constraint |
|---|---|---|---|
| `course_id` | Uuid FK courses **ON DELETE RESTRICT** | no | |
| `user_id` | String(64) FK users **ON DELETE RESTRICT** | no | |
| `role` | String(16) | no | CHECK `IN ('teacher','assistant','student')` |
| `state` | String(16) | no | CHECK `IN ('requested','invited','active','declined','removed')` |
| `source` | String(16) | no | CHECK `IN ('owner','join_code','staff_add','admin','invite','form','open')` |
| `content_language` | String(2) | yes | CHECK `IS NULL OR IN ('en','ru','ky')` |
| `invite_token_hash` (String 64), `invite_expires_at` | | yes | reserved for Phase 7 |
| `activated_at`, `removed_at` | DateTime(tz) | yes | |
| `removed_by_id` | String(64) FK users ON DELETE SET NULL | yes | |
| `created_at`, `updated_at` | mixin | no | |

Constraints and indexes: `UniqueConstraint(course_id, user_id)` → `uq_enrollments_course_id_user_id` (also serves the role resolver); `ix_enrollments_user_id_state (user_id, state)` for "my courses"; `ix_enrollments_course_id_role_state (course_id, role, state)` for roster and limit counts. No soft delete: state `removed` is the delete.

### 2.4 `enrollment_events` (append-only)

`id` Uuid PK; `enrollment_id` Uuid FK enrollments ON DELETE RESTRICT, not null; `course_id` Uuid FK courses ON DELETE RESTRICT, not null; `actor_id` String(64) FK users ON DELETE SET NULL, null; `event` String(32) not null CHECK `IN ('created','joined','rejoined','staff_added','left','removed','role_changed','owner_transferred_in','owner_transferred_out','admin_restored')`; `from_role`, `to_role`, `from_state`, `to_state` String(16) null; `details` JSONType null; `created_at` not null. Index `ix_enrollment_events_course_id_created_at`, `ix_enrollment_events_enrollment_id_created_at`.

### 2.5 `teacher_requests` (`app/lms/teachers/models.py`)

`id` Uuid; `user_id` String(64) FK users ON DELETE RESTRICT not null; `message` Text null (≤2000 by schema); `status` String(16) not null default `'pending'` CHECK `IN ('pending','approved','rejected','cancelled')`; `decided_by_id` FK users SET NULL null; `decided_at` null; `reason` String(500) null; timestamps. Indexes: `ix_teacher_requests_status_created_at (status, created_at)`, `ix_teacher_requests_user_id`, and **partial unique** `uq_teacher_requests_user_pending` on `(user_id)` `WHERE status = 'pending'` (`Index(..., unique=True, postgresql_where=text("status = 'pending'"), sqlite_where=text("status = 'pending'"))`).

### 2.6 `admin_audit_log` (`app/lms/audit/models.py`)

`id` Uuid; `created_at` not null; `actor_id` String(64) FK users ON DELETE RESTRICT not null; `action` String(64) not null; `target_type` String(32) not null CHECK `IN ('user','course','teacher_request','enrollment')`; `target_id` String(64) not null; `reason` String(500) null; `details` JSONType null; `ip_hash` String(32) null; `request_id` String(64) null. Indexes: `ix_admin_audit_log_created_at (created_at, id)`, `ix_admin_audit_log_target (target_type, target_id, created_at)`, `ix_admin_audit_log_actor_id_created_at`.

Actions: `teacher_request.approve`, `teacher_request.reject`, `user.teacher_status.set`, `user.disable`, `user.enable`, `course.delete`, `course.restore`, `course.unlist`, `course.relist`, `course.transfer_ownership`, `course.roster.view`.

### 2.7 `rate_limit_buckets` (`app/lms/core/ratelimit.py`)

`key` String(128) + `window_start` BigInteger (epoch seconds, floored to the window) = composite PK; `count` Integer not null; `expires_at` BigInteger not null, index `ix_rate_limit_buckets_expires_at`. No FKs (keys are hashed).

### 2.8 Model registration

`app/lms/models.py` imports every Phase 1 model; `app/models/__init__.py` gets one line at the end: `import app.lms.models  # noqa: F401` so Alembic `env.py` and `init_db.create_all` see them.

### 2.9 Alembic revision `0002_phase1_courses` (down_revision `0001_baseline`)

Upgrade order:
1. `with op.batch_alter_table("users")`: add the 7 columns (with server defaults), the two CHECKs, the `disabled_by_id` FK, index.
2. Create `courses`, `enrollments`, `enrollment_events`, `teacher_requests`, `admin_audit_log`, `rate_limit_buckets` with all constraints and indexes above (partial index via `op.create_index(..., unique=True, postgresql_where=sa.text("status = 'pending'"), sqlite_where=...)`).
3. Data migration with a lightweight `sa.table("users", sa.column("role"), sa.column("is_platform_admin"), sa.column("teacher_status"))`: `op.execute(users.update().where(users.c.role == "admin").values(is_platform_admin=sa.true(), teacher_status="approved"))`.

Downgrade: drop the six tables (reverse FK order), drop users index, constraints and columns in batch mode. `alembic check` must report no diff against the models (every index/constraint above must be in both).
Dev note: existing local SQLite files will not gain the columns (runtime migrations stay for old columns only). Scratch test DBs use `create_all`, so tests are unaffected. Do not touch `backend/test.db`.

## 3. Services

Conventions: services take `db: Session` and the acting `User` row; they **own the transaction** (call `db.commit()` once at the end of the use case; raise `LMSError` before commit on failure; `get_db` closes and so rolls back). Datetime comparisons use `utcnow()` and treat naive values from SQLite as UTC. `SELECT … FOR UPDATE` is `select(...).with_for_update()`; SQLite ignores it, so its effect is proven only by the PG concurrency tests (section 7.4).

### 3.1 Core (`app/lms/core/`)

```python
# deps.py
def get_lms_user(profile: UserProfile = Depends(get_current_user), db: Session = Depends(get_db)) -> User
    # db.get(User, profile.id); None or disabled -> 401 (old UnauthorizedException). Returns the ORM row in the request session.
def require_platform_admin(user: User = Depends(get_lms_user)) -> User
    # not user.is_platform_admin -> Forbidden(code="platform_admin_required")
def client_ip_hash(request: Request) -> Optional[str]   # P1-17

# ratelimit.py
@dataclass
class Limit: name: str; limit: int; window_seconds: int
def hit(key: str, rule: Limit) -> tuple[bool, int]          # increments; returns (allowed, retry_after_seconds)
def peek(key: str, rule: Limit) -> tuple[bool, int]         # read only
def enforce(key: str, rule: Limit) -> None                  # hit(); raises RateLimited(details={"retry_after_seconds": n})
```
`hit` runs in `with engine.begin() as conn:` (own connection, own commit) using the dialect's `insert(...).on_conflict_do_update(index_elements=[key, window_start], set_={"count": table.c.count + 1}).returning(table.c.count)` (`sqlalchemy.dialects.postgresql.insert` / `sqlalchemy.dialects.sqlite.insert`; SQLite ≥ 3.35). With probability 1/200 it also deletes rows with `expires_at < now`. Call `hit/peek` only when the request session has no uncommitted writes (before the use case starts, or after its rollback), so SQLite never deadlocks on its file lock.

### 3.2 Audit (`app/lms/audit/service.py`)

`record(db, *, actor: User, action: str, target_type: str, target_id: str, reason: str | None = None, details: dict | None = None, request: Request | None = None) -> None` — adds the row to the **caller's** session (same transaction as the admin change; no commit here).

### 3.3 Courses (`app/lms/courses/service.py`)

```python
def generate_join_code() -> str
def normalize_join_code(raw: str) -> str
def load_course(db, course_id: UUID, *, include_deleted=False, for_update=False) -> Course   # NotFound("course_not_found")
def create_course(db, actor: User, data: CourseCreateIn) -> Course
def update_course(db, ctx: AuthzContext, course: Course, data: CourseUpdateIn) -> Course
def set_status(db, ctx, course: Course, transition: Literal["publish","unpublish","conclude","reopen"]) -> Course
def soft_delete_course(db, actor: User, course: Course, *, by_admin=False, reason=None) -> None
def restore_course(db, actor: User, course: Course, *, by_admin=False, reason=None) -> Course
def transfer_ownership(db, actor: User, course: Course, new_owner_id: str, *, by_admin=False, reason=None) -> Course
def regenerate_join_code(db, ctx, course: Course) -> Course
def active_student_count(db, course_id) -> int
```
- **create_course**: re-check `actor.teacher_status == 'approved' and actor.disabled_at is None` (else Forbidden `teacher_not_approved`; never trust the client). Insert course, then owner enrollment (`teacher/active`, `source='owner'`, `activated_at=now`) and event `created`, in one transaction. Join code: insert inside `db.begin_nested()`; on `IntegrityError` for `uq_courses_join_code` retry with a new code up to 5 times, then 409 `join_code_exhausted`.
- **update_course**: fields `title, description, languages, default_language, starts_at, ends_at` need `A.COURSE_UPDATE`; `enrollment_mode, enrollment_limit, visibility` additionally need `A.ROSTER_MANAGE`. Removing a language from `languages` drops that key from title/description only if another key remains, else 422 `title_required`. Limit below current active students → 409 `limit_below_current` (lock course `FOR UPDATE` when the limit changes, so a concurrent join cannot slip past). `visibility='catalog'` with `unlisted_by_admin_at` set → 409 `unlisted_by_admin`.
- **set_status**: transitions per P1-19 else 409 `invalid_transition`; `unpublish` locks the course row and counts students → 409 `has_students`. Sets `published_at`/`concluded_at`.
- **soft_delete_course**: non-admin: actor must be owner (403 `owner_only`). Sets `deleted_at/deleted_by_id`; enrollments untouched. Admin path writes audit `course.delete`.
- **restore_course**: course loaded with `include_deleted=True`; non-admin: not owner → **404** (a deleted course does not exist for anyone else). Not deleted → 409 `not_deleted`. Sets `status='draft'`, clears delete fields; event `admin_restored` only on the admin path (plus audit `course.restore`).
- **transfer_ownership**: lock course `FOR UPDATE`; non-admin: actor is owner (403 `owner_only`), target has `active teacher` enrollment (422 `invalid_new_owner`); both paths: target `teacher_status='approved'`, not disabled, `≠ current owner` (422 `invalid_new_owner`). Admin path creates or revives the target's enrollment as `teacher/active`, `source='admin'`. Update `owner_id`; events `owner_transferred_out` (old owner's enrollment) and `owner_transferred_in`; admin audit on admin path.

### 3.4 Enrollments (`app/lms/enrollments/service.py`)

```python
def join_by_code(db, user: User, raw_code: str, ip_hash: str | None) -> tuple[Enrollment, Course, bool]  # (enrollment, course, already_enrolled)
def leave(db, ctx, course: Course) -> None
def add_staff(db, ctx, course: Course, email: str, role: Literal["teacher","assistant"]) -> Enrollment
def change_role(db, ctx, course: Course, enrollment_id: UUID, role: str) -> Enrollment
def remove(db, ctx, course: Course, enrollment_id: UUID) -> None
def load_enrollment_in_course(db, course_id, enrollment_id, *, for_update=False) -> Enrollment   # 404 if course_id differs (anti-IDOR)
def roster_query(course_id, *, role=None, state="active", q=None) -> Select   # joins users once; no N+1
def staff_query(course_id) -> Select                                          # teacher/assistant active only
```
**join_by_code** (the hot path, one transaction):
1. `ratelimit.enforce(f"join:u:{user.id}", JOIN_USER_10M)` and `JOIN_USER_24H`; `peek(f"join:ip:{ip_hash}", JOIN_IP_FAIL_10M)` → 429 if exhausted.
2. `code = normalize_join_code(raw)`; if it does not match `^[23456789A-HJKMNP-Z]{8}$` → fail.
3. `SELECT course WHERE join_code = :code` — **with `FOR UPDATE` only if `enrollment_limit IS NOT NULL`** (read `enrollment_limit` first with a plain select, then re-select `FOR UPDATE` when needed). Unlimited courses (the national ORT course) therefore never serialize joins on one row.
4. Fail unless course exists, `deleted_at IS NULL`, `status='published'`, `enrollment_mode='invite_code'`.
5. Existing row for `(course_id, user_id)`: `active` → return it, `already_enrolled=True` (no event, role unchanged). Otherwise (`removed`/`declined`/`invited`/`requested`) it will be revived.
6. If limited: `active_student_count(course) >= enrollment_limit` → fail.
7. Insert (inside `begin_nested`) or revive: `role='student', state='active', source='join_code', activated_at=now, removed_at=None, removed_by_id=None`; event `joined` or `rejoined`. On `IntegrityError` (same user joining twice in parallel): roll back the savepoint, re-read the row, return `already_enrolled=True`.
8. Commit. On any failure: `db.rollback()`, then `ratelimit.hit(f"join:ip:{ip_hash}", JOIN_IP_FAIL_10M)`, then raise `NotFound(code="join_code_invalid", message=JOIN_FAIL_MESSAGE)` — one constant message.

**leave**: `require(ctx, A.COURSE_LEAVE, course)`; owner → 409 `owner_cannot_leave`; state `removed`, `removed_by_id = user`, event `left`.
**add_staff**: `require(ctx, A.ROSTER_MANAGE)`; rate limit `staff_add:{actor}`; email lowercased lookup among `email_verified` users → 404 `user_not_found`; `role='teacher'` needs actor = owner (403 `owner_only`) and target approved + enabled (422 `not_approved_teacher`); existing active row → 409 `already_enrolled`; removed row → revive with that role; new row `source='staff_add'`; event `staff_added`.
**change_role**: `require(ctx, A.ROSTER_MANAGE)`; lock the enrollment; target is owner → 409 `owner_immutable`; target currently `teacher` or new role `teacher` → actor must be owner (403 `owner_only`); new role `teacher` → target approved + enabled (422); target state must be `active` (409 `not_active`); no-op returns unchanged; event `role_changed`.
**remove**: `require(ctx, A.ROSTER_MANAGE)`; owner → 409 `owner_immutable`; teacher target → owner only; self → 422 `use_leave`; state `removed`, `removed_at`, `removed_by_id`; event `removed`. History rows (later attempts) stay.

### 3.5 Teacher requests (`app/lms/teachers/service.py`)

```python
def submit_request(db, user: User, message: str | None) -> TeacherRequest
def my_requests(db, user: User, limit=10) -> list[TeacherRequest]
def approve(db, admin: User, request_id: UUID, note: str | None, request: Request) -> TeacherRequest
def reject(db, admin: User, request_id: UUID, reason: str, request: Request) -> TeacherRequest
def set_teacher_status(db, admin: User, user_id: str, status: Literal["approved","revoked"], reason: str | None, request) -> User
```
- **submit**: rate limit `teacher_req:{user}` (3/24h); `approved` → 409 `already_teacher`; `pending` → 409 `request_pending`; insert request + `user.teacher_status='pending'`; `IntegrityError` on the partial unique index → 409 `request_pending`.
- **approve/reject**: lock the request `FOR UPDATE`; not `pending` → 409 `not_pending`; set status, `decided_by_id`, `decided_at`, `reason`; user `teacher_status` → `approved` / `none`; audit row. Reject requires `reason` (1..500).
- **set_teacher_status** (direct grant/revoke): `approved` allowed from `none|pending|revoked` (a pending request becomes `approved` with this admin as decider); `revoked` allowed only from `approved` (else 409 `invalid_transition`); audit `user.teacher_status.set` with `details={"from","to"}`.

### 3.6 Users admin (`app/lms/platform_admin/users_service.py`)

`disable_user(db, admin, user_id, reason, request)` — target is admin itself → 409 `cannot_disable_self`; target `is_platform_admin` → 409 `cannot_disable_admin`; sets `disabled_*`; audit. `enable_user(...)` clears; audit. `search_users(q, teacher_status, disabled) -> Select` (`lower(email) LIKE q%` or `lower(display_name) LIKE %q%`).

### 3.7 Changes to old code (minimal, owned by S1)

- `app/core/security.py::get_current_user`: after loading the SQL user, `if sql_user.disabled_at is not None: raise UnauthorizedException("Account disabled")`.
- `auth.py::login_user`: after the password check, disabled → `_error(403, "account_disabled", "This account is disabled.")`.
- `make_admin.py`: set `role='admin'` and `is_platform_admin=True`; `--revoke` sets `role='student'`, `is_platform_admin=False`; stop listing all users' emails when the email is not found (print only "not found").
- `tests/auth_helpers.py`: admin test account gets `is_platform_admin=True, teacher_status='approved'`.
- `app/main.py`: call `register_error_handlers(app)` if Phase 0 has not wired it.

## 4. Authorization completion (`app/core/authz.py`, S1)

New actions on `A`: `COURSE_TRANSFER = "course.transfer"`, `COURSE_LEAVE = "course.leave"`. Grants: teacher = all; assistant = all − `{COURSE_DELETE, COURSE_PUBLISH, ROSTER_MANAGE, COURSE_TRANSFER}`; student = `{COURSE_READ, CONTENT_READ, ASSESSMENT_TAKE, ATTEMPT_READ_OWN, GRADES_READ_OWN, COURSE_LEAVE}`. Join codes are visible exactly to holders of `ROSTER_READ` (teacher, assistant).

`decide()` status gates (replace the Phase 0 body; keep the signature):
- `COURSE_LEAVE`: allowed in every status for any role holding it.
- `draft`: role ∈ {teacher, assistant} and action in grants.
- `published`: action in grants.
- `concluded`: action in grants and action ∈ `READ_ONLY_ACTIONS ∪ {COURSE_PUBLISH (reopen), COURSE_DELETE, COURSE_TRANSFER, COURSE_LEAVE}`.
- No role: `is_platform_admin and action in PLATFORM_ADMIN_ACTIONS` (kept for later phases; course routes pass `is_platform_admin=False`, P1-12).

Row rules live in services (owner-only actions, owner immutability, enrollment-belongs-to-course).

`AuthzContext(user, db, role_resolver=_no_role, allow_platform_admin=False)`: `is_platform_admin` returns `allow_platform_admin and bool(user.is_platform_admin)`; it no longer looks at `role`. Update `tests/test_authz.py` accordingly (`SimpleNamespace(role="admin")` alone grants nothing).

Real resolver and dependency:
```python
def enrollment_role_resolver(db: Session, user_id: str) -> Callable[[UUID], Optional[str]]:
    # SELECT role FROM enrollments WHERE course_id=:c AND user_id=:u AND state='active'
def get_authz(user: User = Depends(get_lms_user), db: Session = Depends(get_db)) -> AuthzContext:
    return AuthzContext(user, db, enrollment_role_resolver(db, user.id))
AuthzContext.prefetch(course_ids: Iterable[UUID]) -> None   # one IN query fills enrollment_cache (for future multi-course pages)
```
`require()` keeps Phase 0 semantics: deleted → 404, no role → 404, role but denied → 403 `forbidden`.

SQL scopes (`app/lms/courses/scopes.py`), used by every list endpoint; never `can()` in a loop:
```python
def my_courses(user_id: str, *, as_: Literal["teaching","learning","all"] = "all") -> Select[tuple[Course, str]]
    # Course JOIN enrollments e ON e.course_id = Course.id AND e.user_id = :u AND e.state = 'active'
    # WHERE Course.deleted_at IS NULL AND (e.role IN ('teacher','assistant') OR Course.status != 'draft')
    # teaching: e.role IN ('teacher','assistant'); learning: e.role = 'student'. Selects (Course, e.role) + owner display name via one JOIN.
def courses_visible_to(user_id: str) -> Select   # select(Course.id) with the same predicate, for IN-subqueries in later phases
def my_deleted_courses(user_id: str) -> Select   # owner_id = :u AND deleted_at IS NOT NULL (trash)
```

## 5. API (all under `/api/v1`)

Policy names for `ROUTE_POLICIES` (a test asserts each policy is in this set): `authenticated` (signed-in, enabled; acts on self only), `authenticated+ratelimit`, `teacher_approved`, `course:<action>` (route calls `require(ctx, action, course)`), `course:<action>+owner`, `course:owner_restore`, `platform_admin` (`require_platform_admin`; mutations audited), `legacy` (existing).

### 5.1 Me and teacher requests (S2, router `app/lms/teachers/router.py`, prefix `/me`)

| method path | request | response | policy | errors |
|---|---|---|---|---|
| GET `/me/lms` | – | `MeOut` | authenticated | 401 |
| PATCH `/me/lms` | `MePatchIn{locale: en\|ru\|ky}` | `MeOut` | authenticated | 422 |
| POST `/me/teacher-requests` | `TeacherRequestIn{message?: str ≤2000}` | 201 `MyTeacherRequestOut` | authenticated+ratelimit | 409 `already_teacher`, `request_pending`; 429 |
| GET `/me/teacher-requests` | – | `list[MyTeacherRequestOut]` (latest 10) | authenticated | |

`MeOut{id, email, display_name, locale, is_platform_admin, teacher_status, can_create_courses}` (`can_create_courses = approved and not disabled`). `MyTeacherRequestOut{id, message, status, reason, created_at, decided_at}` (no decider identity).

### 5.2 Courses (S3, router `app/lms/courses/router.py`, prefix `/courses`; declare static paths before `/{course_id}`)

| method path | request | response | policy | errors |
|---|---|---|---|---|
| GET `/courses` | query `as=teaching\|learning\|all`, `cursor`, `limit≤100` | `PageOut[CourseCard]` | authenticated (scope `my_courses`) | |
| GET `/courses/trash` | `cursor`, `limit` | `PageOut[CourseCard]` | authenticated (scope `my_deleted_courses`) | |
| POST `/courses` | `CourseCreateIn` | 201 `CourseStaffOut` | teacher_approved | 403 `teacher_not_approved`; 422 |
| POST `/courses/join` | `JoinIn{code: str ≤32}` | `JoinOut` | authenticated+ratelimit | 404 `join_code_invalid`; 429 |
| GET `/courses/{course_id}` | – | `CourseStaffOut` (teacher/assistant) or `CourseStudentOut` (student) | course:course.read | 404, 403 |
| PATCH `/courses/{course_id}` | `CourseUpdateIn` (all optional) | `CourseStaffOut` | course:course.update (+roster.manage for enrollment fields) | 403, 404, 409 `limit_below_current`/`unlisted_by_admin`, 422 |
| POST `/courses/{course_id}/publish` · `/unpublish` · `/conclude` · `/reopen` | – | `CourseStaffOut` | course:course.publish | 409 `invalid_transition`/`has_students` |
| DELETE `/courses/{course_id}` | – | 204 | course:course.delete+owner | 403 `owner_only` |
| POST `/courses/{course_id}/restore` | – | `CourseStaffOut` | course:owner_restore | 404, 409 `not_deleted` |
| POST `/courses/{course_id}/transfer-ownership` | `TransferIn{new_owner_user_id}` | `CourseStaffOut` | course:course.transfer+owner | 403 `owner_only`; 422 `invalid_new_owner` |
| POST `/courses/{course_id}/join-code/regenerate` | – | `JoinCodeOut{join_code}` | course:roster.manage | |
| POST `/courses/{course_id}/leave` | – | 204 | course:course.leave | 409 `owner_cannot_leave` |
| GET `/courses/{course_id}/people` | `role?`, `state=active\|removed`, `q?`, `cursor`, `limit` | staff: `PageOut[RosterEntryOut]`; student: `PageOut[StaffPublicOut]` (staff only, ignores filters) | course:course.read (+roster.read for full) | |
| POST `/courses/{course_id}/staff` | `AddStaffIn{email, role: teacher\|assistant}` | 201 `RosterEntryOut` | course:roster.manage | 404 `user_not_found`; 409 `already_enrolled`; 422 `not_approved_teacher`; 403 `owner_only`; 429 |
| PATCH `/courses/{course_id}/enrollments/{enrollment_id}` | `RoleChangeIn{role}` | `RosterEntryOut` | course:roster.manage | 404, 403 `owner_only`, 409 `owner_immutable`/`not_active`, 422 |
| DELETE `/courses/{course_id}/enrollments/{enrollment_id}` | – | 204 | course:roster.manage | 404, 403, 409 `owner_immutable`, 422 `use_leave` |

Schemas (`app/lms/courses/schemas.py`, `app/lms/enrollments/schemas.py`):
- `CourseCreateIn{title: localized_text(200), description?: localized_text(5000), languages: list[Lang] (1..3, unique), default_language: Lang, enrollment_mode: "invite_code"|"closed" = "invite_code", enrollment_limit?: int 1..10000, starts_at?, ends_at?}`; model validator enforces P1-18.
- `CourseUpdateIn`: same fields optional + `visibility: "private"|"catalog"`; `extra="forbid"` (so `status`, `owner_id`, `join_code` cannot be patched).
- `CourseCard{id, title, languages, default_language, status, my_role, owner_display_name, starts_at, ends_at, deleted_at?}` — **no join code, no counts**; used for every role.
- `CourseStudentOut{id, title, description, languages, default_language, status, starts_at, ends_at, owner_display_name, my_enrollment: MyEnrollmentOut}` — exact key set asserted by contract test.
- `CourseStaffOut = CourseStudentOut + {join_code, enrollment_mode, enrollment_limit, visibility, unlisted_by_admin: bool, active_student_count, owner: UserBrief, is_owner, created_at, updated_at, published_at, concluded_at}`.
- `MyEnrollmentOut{id, course_id, role, state, activated_at}`; `JoinOut{course: CourseCard, enrollment: MyEnrollmentOut, already_enrolled: bool}`.
- `UserBrief{id, display_name, email}` (staff/admin views only); `RosterEntryOut{enrollment_id, user: UserBrief, role, state, source, activated_at, removed_at, is_owner}`; `StaffPublicOut{display_name, role}`.

Serializer selection: the route picks `CourseStaffOut` iff `ctx.role_for(course.id) in ("teacher","assistant")`, else `CourseStudentOut`; never by a client flag. Display name fallback is the email local part **only in staff/admin views**; student views fall back to `"—"`.

### 5.3 Platform admin (router prefix `/platform`, every route `platform_admin`)

S2 owns `app/lms/platform_admin/router.py` (users, teacher requests, audit). S3 owns `app/lms/platform_admin/courses_router.py` (course moderation).

| method path | request | response | owner | errors |
|---|---|---|---|---|
| GET `/platform/summary` | – | `{pending_teacher_requests: int}` | S2 | |
| GET `/platform/teacher-requests` | `status=pending\|approved\|rejected\|cancelled\|all`, `cursor`, `limit` | `PageOut[TeacherRequestAdminOut]` | S2 | |
| POST `/platform/teacher-requests/{id}/approve` | `{note?: str ≤500}` | `TeacherRequestAdminOut` | S2 | 404, 409 `not_pending` |
| POST `/platform/teacher-requests/{id}/reject` | `{reason: str 1..500}` | `TeacherRequestAdminOut` | S2 | 404, 409, 422 |
| GET `/platform/users` | `q`, `teacher_status`, `disabled: bool`, `cursor`, `limit` | `PageOut[AdminUserOut]` | S2 | |
| GET `/platform/users/{user_id}` | – | `AdminUserDetailOut` | S2 | 404 |
| POST `/platform/users/{user_id}/teacher-status` | `{status: approved\|revoked, reason?}` | `AdminUserOut` | S2 | 409 `invalid_transition` |
| POST `/platform/users/{user_id}/disable` | `{reason: 1..500}` | `AdminUserOut` | S2 | 409 `cannot_disable_self`/`cannot_disable_admin` |
| POST `/platform/users/{user_id}/enable` | – | `AdminUserOut` | S2 | |
| GET `/platform/audit-log` | `actor_id`, `action`, `target_type`, `target_id`, `cursor`, `limit` | `PageOut[AuditEntryOut]` | S2 | |
| GET `/platform/courses` | `q`, `status`, `deleted: bool`, `owner_id`, `cursor`, `limit` | `PageOut[AdminCourseOut]` | S3 | |
| GET `/platform/courses/{course_id}` | – | `AdminCourseOut` (deleted included) | S3 | 404 |
| GET `/platform/courses/{course_id}/people` | `cursor`, `limit` | `PageOut[RosterEntryOut]` (audited `course.roster.view`) | S3 | |
| POST `/platform/courses/{course_id}/delete` · `/restore` | `{reason: 1..500}` | `AdminCourseOut` | S3 | 409 `not_deleted`/`already_deleted` |
| POST `/platform/courses/{course_id}/unlist` · `/relist` | `{reason?}` | `AdminCourseOut` | S3 | |
| POST `/platform/courses/{course_id}/transfer-ownership` | `{new_owner_user_id, reason}` | `AdminCourseOut` | S3 | 422 `invalid_new_owner` |

- `TeacherRequestAdminOut{id, user: UserBrief, user_teacher_status, message, status, reason, created_at, decided_at, decided_by: UserBrief?}`.
- `AdminUserOut{id, email, display_name, created_at, email_verified, is_platform_admin, teacher_status, disabled_at, disabled_reason}`; `AdminUserDetailOut = AdminUserOut + {owned_courses: list[CourseCard] (≤50), active_enrollment_count, teacher_requests: list[TeacherRequestAdminOut] (≤10)}`.
- `AdminCourseOut{id, title, owner: UserBrief, status, visibility, enrollment_mode, unlisted_by_admin_at, active_student_count, created_at, deleted_at, deleted_by_id}` — no join code (admins do not need it). `active_student_count` comes from one correlated scalar subquery on `ix_enrollments_course_id_role_state` (no N+1).
- `AuditEntryOut{id, created_at, actor: UserBrief, action, target_type, target_id, reason, details}`.

Non-admins get 403 `platform_admin_required` on every `/platform` route (route existence is public in OpenAPI anyway).

### 5.4 Error codes (frontend keys `lms.errors.<code>`)
`not_found, course_not_found, forbidden, owner_only, owner_immutable, owner_cannot_leave, use_leave, not_active, teacher_not_approved, not_approved_teacher, invalid_new_owner, join_code_invalid, join_code_exhausted, rate_limited, already_enrolled, user_not_found, limit_below_current, unlisted_by_admin, invalid_transition, has_students, not_deleted, already_deleted, title_required, already_teacher, request_pending, not_pending, cannot_disable_self, cannot_disable_admin, platform_admin_required, validation_failed, invalid_cursor, account_disabled`.

## 6. Frontend

### 6.1 Routes (no collisions)
Old `(admin)` group serves `/[lang]/{exams,questions,bulk-upload,students,analytics}` and old `(student)` serves `/[lang]/{dashboard,mock-tests,practice,progress,mistakes,review}`; `middleware.ts` matches only those top-level paths. New real segments `courses/` and `admin/` do not collide and are not matched by the middleware. Do not name any new **top-level** segment after an old one.

| path | file (under `frontend/src/app/[lang]/`) | who |
|---|---|---|
| `/[lang]/courses` | `courses/page.tsx` — tabs Teaching / Learning, buttons Join, Create (if `can_create_courses`), "Become a teacher" CTA (if `teacher_status ∈ none,revoked`), pending badge | all |
| `/[lang]/courses/new` | `courses/new/page.tsx` | approved teachers |
| `/[lang]/courses/join` | `courses/join/page.tsx` — `?code=` prefill, `JoinCodeInput` | all |
| `/[lang]/courses/trash` | `courses/trash/page.tsx` — restore | owners |
| `/[lang]/courses/become-teacher` | `courses/become-teacher/page.tsx` — form + history of own requests | students |
| `/[lang]/courses/[courseId]` | `courses/[courseId]/layout.tsx` (loads course once, `CourseContext`, role-aware tabs) + `page.tsx` (Home) | enrolled |
| `/[lang]/courses/[courseId]/people` | `people/page.tsx` — staff: roster table, filters, add staff, role change, remove; student: staff list | enrolled |
| `/[lang]/courses/[courseId]/settings` | `settings/page.tsx` — general, languages, enrollment (code + copy + regenerate, mode, limit), lifecycle, danger zone (transfer, delete) | staff (owner-only controls hidden for others) |
| `/[lang]/admin` | `admin/layout.tsx` (fetch `/me/lms`; not admin → render not-found) + `page.tsx` (redirect to teacher-requests) | platform admin |
| `/[lang]/admin/teacher-requests` | queue with approve / reject (reason dialog) | |
| `/[lang]/admin/users`, `/[lang]/admin/users/[userId]` | search, teacher status, disable/enable | |
| `/[lang]/admin/courses`, `/[lang]/admin/courses/[courseId]` | search, delete/restore, unlist/relist, transfer, roster (audited) | |
| `/[lang]/admin/audit-log` | filterable list | |

All pages are client components (`"use client"`, `useParams`); `courses/layout.tsx` redirects to `/[lang]/login?redirect=…` when signed out. The server is the only authority; UI hiding is convenience.

### 6.2 Shared code
- `lib/lms/client.ts` (S4): `lmsFetch<T>(path, {method, body, params})` on top of `getAuthHeader()`; throws `LmsApiError{status, code, message, details}` parsed from `{"error":…}`; falls back to `code="network"`/`"unknown"`. `lib/lms/useLmsMe.ts`: hook + context for `MeOut`.
- `lib/lms/types.ts` (S4): TS mirrors of every schema in section 5 (single source; S5 imports).
- `lib/lms/courses.ts` (S4): `listMyCourses, listTrash, createCourse, getCourse, updateCourse, publishCourse, unpublishCourse, concludeCourse, reopenCourse, deleteCourse, restoreCourse, transferOwnership, regenerateJoinCode, joinByCode, leaveCourse, listPeople, addStaff, changeEnrollmentRole, removeEnrollment, getMe, patchMe`.
- `lib/lms/admin.ts` (S5): `getPlatformSummary, listTeacherRequests, approveTeacherRequest, rejectTeacherRequest, listUsers, getUser, setTeacherStatus, disableUser, enableUser, listAdminCourses, getAdminCourse, adminDeleteCourse, adminRestoreCourse, unlistCourse, relistCourse, adminTransferOwnership, adminCoursePeople, listAuditLog`; `lib/lms/teacher.ts` (S5): `submitTeacherRequest, listMyTeacherRequests`.
- Components (S4, `components/lms/`): `LmsShell` (top bar: My courses, Join, Create/Become a teacher, Platform admin if `is_platform_admin`, link back to old portal, language switcher), `CourseCard`, `CourseTabs`, `LocalizedTextInput` (one tab per selected course language), `LanguagePicker`, `JoinCodeInput`, `JoinCodeDisplay`, `RosterTable`, `ConfirmDialog`, `ErrorMessage` (maps `code` → `lms.errors.*`), `Pager` (cursor). Helper `pickLocalized(text, uiLang, defaultLang)` in `lib/lms/localized.ts`.
- Components (S5, `components/lms/admin/`): `AdminShell` (side nav with pending badge), `ReasonDialog`, `AuditTable`, `UserStatusBadge`.
- Entry points into old UI (one link each, nothing else changed): `components/common/Sidebar.tsx` → "Courses" (`/[lang]/courses`) for everyone; old `(admin)/layout.tsx` nav → "Platform admin" (`/[lang]/admin`) shown when the old `role === "admin"` (UI convenience only; the server checks the DB flag, and `admin/layout.tsx` re-checks `/me/lms`).

### 6.3 i18n namespaces (keys in `en.json`, `ky.json`, `ru.json`, parity enforced)
S4: `lms.nav.*`, `lms.common.*` (save, cancel, confirm, loading, empty, retry, copy, copied), `lms.errors.*` (every code in 5.4 + `network`, `unknown`), `courses.list.*`, `courses.create.*`, `courses.join.*`, `courses.home.*`, `courses.people.*`, `courses.settings.*`, `courses.status.*`, `courses.roles.*`, `courses.languages.*`, `courses.trash.*`, `nav.courses`.
S5: `teacherRequest.*`, `platformAdmin.nav.*`, `platformAdmin.requests.*`, `platformAdmin.users.*`, `platformAdmin.courses.*`, `platformAdmin.audit.*`, `platformAdmin.auditActions.*` (one per audit action), `nav.platformAdmin`.
Each slice adds only its own top-level namespaces. If S4 and S5 run in parallel worktrees, the three JSON files will conflict textually; a `helper` merges them at integration and re-runs the parity check.

## 7. Test plan

Location `backend/tests/lms/` (`__init__.py`). Factories (S1, `tests/lms/factories.py`): `make_user(db, *, teacher_status="none", platform_admin=False, disabled=False, role="student") -> User`, `auth(user) -> dict` (real JWT via `create_access_token({"sub": user.id})`), `make_course(db, owner, **overrides) -> Course` (via `create_course`), `enroll(db, course, user, role="student", state="active")`, `set_status(db, course, status)`. Every test uses the scratch DB per `AGENTS.md` 6.1.

### 7.1 Authz unit (S1) `test_authz_phase1.py`
Full table `decide(role ∈ {teacher, assistant, student, None}, status ∈ {draft, published, concluded}, action ∈ ALL_ACTIONS, is_platform_admin ∈ {F, T})` against an explicit expected table written in the test (not computed by `decide`). Cases that must be pinned: student draft → all False except `COURSE_LEAVE`; assistant `ROSTER_MANAGE` False; teacher concluded: `COURSE_UPDATE` False, `COURSE_PUBLISH` True, `ROSTER_MANAGE` False; `is_platform_admin=True` but `allow_platform_admin=False` context grants nothing; `SimpleNamespace(role="admin")` grants nothing.
`test_role_resolver.py`: active → role; removed/declined/invited → None; other user's enrollment → None; one SQL query per course per request (count with a `before_cursor_execute` listener); `prefetch` = one query.

### 7.2 Endpoint matrix (S3) `test_course_matrix.py`
Actors: O owner, T co-teacher, AS assistant, S student, R removed student, X outsider, P platform admin with no enrollment (and `role='admin'`). Statuses: draft, published, concluded, deleted. Table-driven over every `/courses/{id}…` route. Pinned expectations (the test file holds the full table):

| route | draft | published | concluded | deleted |
|---|---|---|---|---|
| GET course | O,T,AS 200 · S 403 · R,X,P 404 | O,T,AS,S 200 · R,X,P 404 | same as published | all 404 |
| PATCH title | O,T,AS 200 · S 403 · R,X,P 404 | same | O,T,AS,S 403 · R,X,P 404 | all 404 |
| PATCH enrollment_limit | O,T 200 · AS,S 403 | same | 403 | 404 |
| publish/conclude/reopen (valid transition) | O,T 200 · AS,S 403 | O,T 200 | reopen O,T 200 | 404 |
| DELETE | O 204 · T,AS,S 403 · R,X,P 404 | same | O 204 | all 404 |
| restore | 409 for O (not deleted) | – | – | O 200 · everyone else 404 |
| transfer-ownership | O 200 · T,AS,S 403 | same | O 200 | 404 |
| join-code/regenerate | O,T 200 · AS,S 403 | same | 403 | 404 |
| people (full) | O,T,AS full · S 403 | O,T,AS full · S staff-only | same | 404 |
| add staff / role change / remove | O,T 2xx (students/assistants) · AS,S 403 | same | 403 | 404 |
| leave | S 204 · O 409 | S,T,AS 204 · O 409 | S 204 | 404 |

P has `is_platform_admin=True`: the 404s above prove there is no admin bypass inside `/courses/*` (P1-12). Separately, a user with old `role='admin'` but `is_platform_admin=False` gets 403 on every `/platform/*` route (proves the DB flag, not the old role, is used).

### 7.3 Isolation suite (S3) `test_isolation_suite.py`
Teachers TA, TB; students s1, s2, s3. TA owns CA (s1, s2); TB owns CB (s2, s3). Assert: TA gets 404 on every CB route (GET, PATCH, people, staff, enrollments, publish, delete, transfer, regenerate); `GET /courses` for each user lists exactly their courses; s1 never sees CB; s3's list excludes CA; TA's roster has no s3; `PATCH /courses/{CA}/enrollments/{enrollment_of_s3_in_CB}` → 404 (anti-IDOR); TA cannot transfer CA to s1 (422) nor add s3 as teacher (422 unless approved); raw response bodies of every student-facing call contain neither CA's nor CB's join code string nor any other student's email or id.

### 7.4 Concurrency on Postgres (S1 for rate limit, S3 for join) — `test_pg_concurrency.py`
Skipped unless `LMS_PG_TEST_DATABASE_URL` is set (an empty PG database, separate from `ALEMBIC_TEST_DATABASE_URL`); the fixture runs `Base.metadata.create_all` on it and drops all at the end; services are called directly with one `Session` per thread and a `threading.Barrier`.
- Course with `enrollment_limit=5`, 20 distinct users join at once → exactly 5 active students, 15 `join_code_invalid`, no other exception.
- Same user joins from 10 threads → exactly one row, one `joined` event, all calls succeed.
- 6 joins racing with `PATCH enrollment_limit=3` → final active ≤ max(limit at commit) and never above the stored limit.
- Two admins approve and reject the same request concurrently → one 200, one 409 `not_pending`.
- `ratelimit.hit` from 20 threads with limit 10 → exactly 10 allowed.
On SQLite the same scenarios run sequentially (logic only).

### 7.5 Feature tests
- S1 `test_ratelimit.py`: window rollover; counter survives the caller's rollback; cleanup deletes expired rows; `peek` does not increment. `test_account_disable.py`: disabled → 401 on old `/auth/me` and new `/me/lms`; login 403 `account_disabled`. `test_make_admin.py`: sets both flags; `--revoke` clears both; no email listing. `tests/test_migrations.py` (PG only): seed a `role='admin'` user at `0001`, upgrade to `0002` → `is_platform_admin` and `approved`; downgrade to `0001` and up again clean; `alembic check` clean. `test_phase1_constraints.py`: duplicate `(course_id,user_id)` rejected; second pending request rejected by the partial index while a rejected + pending pair is allowed; CHECKs reject bad status/role/state/limit 0.
- S2 `test_teacher_requests.py`: submit → `pending`; duplicate → 409; 4th in 24 h → 429; approve → `POST /courses` works; reject → `none`, reason visible to requester; revoke → `POST /courses` 403 but existing course still editable by them; direct grant cancels/approves pending request. `test_platform_admin.py`: every `/platform` route 403 for a student, for an approved teacher, and for a forged JWT carrying `"role":"admin","is_platform_admin":true` claims; each mutation writes exactly one audit row with the right action/target and no email in `details`; cannot disable self/another admin; audit log pagination and filters.
- S3 `test_courses_api.py`: create inserts owner enrollment + event in one transaction (inject a failure after the course insert → nothing persisted); `teacher_status` bypass attempts (`none`, `pending`, `revoked`, approved-but-disabled, old `role='admin'` without approval) → 403/401; P1-18 validation; lifecycle transitions; delete/restore; trash; transfer; join-code regenerate invalidates the old code. `test_enrollments_api.py`: join happy path; already enrolled → `already_enrolled=true`; every failure kind returns a byte-identical body; malformed code identical too; 11th attempt in 10 min → 429; IP failure limit (61st failure from one IP hash → 429, while successes from that IP do not count); remove → rejoin revives the **same enrollment id**, logs `rejoined`, role student; owner cannot be removed, demoted or leave; non-owner teacher cannot remove/demote another teacher; enrollment from another course → 404. `test_serializer_contracts.py`: exact key sets of `CourseCard`, `CourseStudentOut`, `StaffPublicOut`, `MyEnrollmentOut`, `JoinOut`; no `join_code`, `enrollment_limit`, `email`, `user_id` keys in student payloads.
- Route inventory (Phase 0 test) passes with all new routes listed; new test: every policy string is in the section 5 set.
- `test_phase1_flow.py` (integration, after S2+S3): register → verify → request teacher → admin approves → create course → publish → student joins by code → teacher removes → student rejoins (same enrollment id) → owner transfers to co-teacher → old owner leaves.

### 7.6 Frontend
`tsc --noEmit` and isolated `next build` clean; i18n parity check green; manual scripted flow on local dev (screens: join error, 429, become-teacher, admin approve).

## 8. Slices

| slice | owns (only these files) | depends on | must pass |
|---|---|---|---|
| **S1 Foundation** (Sonnet; architect reviews) | `app/models/user.py`, `app/models/__init__.py` (one import line), `app/lms/models.py`, `app/lms/courses/models.py`, `app/lms/enrollments/models.py`, `app/lms/teachers/models.py`, `app/lms/audit/{models,service}.py`, `app/lms/core/{deps,ratelimit}.py`, `app/lms/courses/scopes.py`, `app/core/authz.py`, `app/core/security.py` (disable check), `app/api/v1/endpoints/auth.py` (login disable only), `app/core/route_inventory.py` (merge `ROUTE_POLICIES = {**LEGACY, **ME_POLICIES, **COURSE_POLICIES, **PLATFORM_POLICIES, **PLATFORM_COURSE_POLICIES}`), empty stub routers + empty `policies.py` in `app/lms/{teachers,courses,enrollments,platform_admin}/` wired in `app/api/v1/router.py`, `app/main.py` (error handlers if missing), `alembic/versions/0002_phase1_courses.py`, `make_admin.py`, `app/core/config.py` (`RATE_LIMIT_PROXY_HOPS`), `tests/auth_helpers.py`, `tests/test_authz.py`, `tests/test_migrations.py`, `tests/lms/{__init__,factories}.py`, `tests/lms/test_{authz_phase1,role_resolver,ratelimit,account_disable,make_admin,phase1_constraints}.py`, rate-limit part of `tests/lms/test_pg_concurrency.py` | Phase 0 merged | full old suite + S1 tests on SQLite; migration tests + `alembic check` on PG |
| **S2 Teachers + platform admin backend** | `app/lms/teachers/{service,schemas,router,policies}.py`, `app/lms/platform_admin/{users_service,schemas,router,policies}.py`, `tests/lms/test_{teacher_requests,platform_admin}.py` | S1 | S2 tests, route inventory, full suite |
| **S3 Courses + enrollments backend** | `app/lms/courses/{service,schemas,router,policies}.py`, `app/lms/enrollments/{service,schemas}.py` (routes live in the courses router), `app/lms/platform_admin/{courses_router,courses_policies}.py`, `tests/lms/test_{courses_api,enrollments_api,course_matrix,isolation_suite,serializer_contracts}.py`, join part of `test_pg_concurrency.py` | S1 (S2 not needed: tests set `teacher_status` via factories) | S3 tests, route inventory, PG concurrency (when env set), full suite |
| **S4 Frontend courses** | `frontend/src/lib/lms/{client,types,courses,localized,useLmsMe}.ts`, `frontend/src/components/lms/*` (not `admin/`), `frontend/src/app/[lang]/courses/**` except `become-teacher/`, `components/common/Sidebar.tsx` (one link), i18n S4 namespaces | contract in this doc; live check after S3 | `tsc`, isolated `next build`, i18n parity |
| **S5 Frontend admin + become-a-teacher** | `frontend/src/lib/lms/{admin,teacher}.ts`, `frontend/src/components/lms/admin/*`, `frontend/src/app/[lang]/admin/**`, `frontend/src/app/[lang]/courses/become-teacher/page.tsx`, old `(admin)/layout.tsx` (one nav link), i18n S5 namespaces | S4's `client.ts`, `types.ts`, `LmsShell` (S4 commits these first, within its first hour) | `tsc`, isolated `next build`, i18n parity |
| **Integration** (orchestrator + implementer) | `tests/lms/test_phase1_flow.py`, `docs/phases/PHASE_1.md`, `PRODUCT_DECISIONS.md` (P1 decisions), i18n merge | S2, S3, S4, S5 | all gates in plan section 0; `/security-review` |

Parallelism: after S1 merges, S2 and S3 run in parallel; S4 can start immediately against this contract (types first); S5 starts once S4's client and types land.

## 9. Open questions and risks

- **Q1 Proxy hops** (P1-17): confirm on staging what `X-Forwarded-For` looks like through Vercel rewrite → Render. If wrong, all users share one IP bucket and failed joins nationwide block each other. Mitigation until confirmed: the IP limit counts only failures, and S3 logs (hashed) the computed IP at debug level for one deploy.
- **Risk: one hot course row.** Joins to a course with a limit serialize on `FOR UPDATE`. Fine for classes (≤ a few hundred); the mass ORT course must keep `enrollment_limit = NULL`. Settings UI shows a hint.
- **Risk: SQLite cannot prove locking.** Locking claims are only proven when CI sets `LMS_PG_TEST_DATABASE_URL`; CI must set it (Phase 0 CI has a PG service).
- **Risk: rate-limit table growth.** About one row per user per window; cleanup is probabilistic. Phase 9 load test should check the table stays small.
- **Risk: old `role` drift.** `make_admin.py` keeps both flags in sync; nothing else writes them. Phase 5 drops `users.role`.
- **Risk: dev SQLite DBs** created before Phase 1 lack the new user columns; developers recreate them (never `backend/test.db` by agents).
