# S3: free and paid exams (design, 2026-11-06)

Roadmap slice S3 (`ROADMAP_EXAM_PREP.md`). Owner: some exams are free; a payment unlocks all exams. First payment method: **activation codes** the owner sells by QR transfer (D3); automatic payment later. Builds on S1 (admin two-step login, its encryption helper) and S2 (exam-prep page, library cards with a lock slot).

## 1. Rules
1. Only **platform-organization courses** (kind `platform`) can have paid exams. Teacher and school courses are always free; nobody else can sell through the platform.
2. Each assessment in a platform course has `access_tier` = `free` | `paid`. **New assessments in platform courses default to `paid`**; everywhere else the column is `free` and ignored. Migration sets every existing assessment to `free`, so nothing locks on deploy; the owner then switches what should be paid.
3. A student may **start a new attempt** of a paid exam only with an active pass. Checked server-side in `attempts.engine.start_attempt`, for non-staff only, right where the module gate runs and **only when no open attempt exists** (a student whose pass ended mid-attempt still finishes and submits; resuming never checks). Refusal: 403 `access_required`.
4. Already-taken attempts, results and the result review (with explanations) stay visible forever, pass or not.
5. **Practice** (Phase 10) in a platform course needs a pass, unless the course setting `practice_free` is true (default false).
6. Staff, previews and Student view are never locked (staff preview path is untouched).
7. One pass unlocks **every paid exam on the platform** (scope `all`). The column exists so later products (olympiads, НЦТ tests) can get their own scope.

## 2. Data (migration after S1/S2's)
- `assessments.access_tier` varchar(8) not null default `free`, check in (`free`,`paid`).
- `access_passes`: id, user_id, scope (`all`), starts_at, ends_at, source (`code` | `admin` | `payment`), code_id null, granted_by_id null, reason null, revoked_at null, revoked_by_id null, created_at. Active = not revoked and starts_at ≤ now < ends_at. Index (user_id, ends_at).
- `activation_code_batches`: id, label, duration_days null, ends_on date null (exactly one of the two), count, note (e.g. price), created_by_id, created_at, revoked_at.
- `activation_codes`: id, batch_id, code_hmac (unique; HMAC-SHA256 with a key derived from `SECRET_KEY`, for redemption lookup), code_enc (AES-GCM, S1 helper, so the admin can show unsold codes again), last4, given_at, given_note (who it was sold to), redeemed_by_id, redeemed_at, revoked_at.
- Passes and redemptions are personal data: privacy registry, export, anonymize, `tests/lms/isolation.py`.

## 3. Codes
- 12 characters from Crockford base32 without I, L, O, U (about 60 bits), shown as `XXXX-XXXX-XXXX`; input is case-insensitive, ignores spaces and dashes, maps O→0 and I/L→1.
- **Redeem** `POST /api/v1/me/access/redeem {code}`: rate-limited per user (10/h) and per IP (30/h) with the existing module, same error for unknown, used and revoked codes (`code_invalid`). Single use, enforced by an atomic `UPDATE … WHERE redeemed_at IS NULL AND revoked_at IS NULL` (no double redemption under concurrency).
- The new pass **extends** an active one: starts at the later of now and the current pass's end. `ends_on` batches end on that date (Asia/Bishkek end of day) regardless.
- Codes are never logged; the audit stores the code id and last4 only.

## 4. Endpoints
Student: `GET /me/access` (active pass end, or none; whether practice is free); `POST /me/access/redeem`. Assessment lists and the S2 exam-prep endpoint add `access_tier` and `locked` per test (one query, no N+1).
Platform admin (all audited, reason required where marked, behind S1's two-step login):
- `GET/POST /platform/access/batches` (create returns the batch; codes listed by the next call), `POST …/batches/{id}/revoke` (reason; unused codes only), `GET …/batches/{id}/codes` (status, last4, full code on demand per code: `POST …/codes/{id}/reveal`, audited), `POST …/codes/{id}/given` (note), CSV export of a batch's unused codes (audited).
- `GET /platform/users/{id}/access` (passes, redemptions), `POST …/access/grant` (days or end date, reason), `POST /platform/access/passes/{id}/revoke` (reason).
- `GET /platform/access/exams`: paid/free toggle list for every assessment in platform courses; `PATCH` one (audited). No change to ORT builder screens.

## 5. Screens
- Library card (S2) of a locked test: lock icon, "Платный" badge; tapping opens the unlock page. The "Next" card skips locked tests for students without a pass and, if only locked ones remain, says "Unlock all exams".
- `/[lang]/unlock`: what's included, how to pay (text the owner fills: `access.howToPay`, placeholder until then), code field, current status ("Доступ до 31 мая"). Reached from the lock, the student menu and the exam-prep goal strip.
- Admin: "Access" section: batches (create, list, revoke, export), codes (copy, mark given), paid exams toggles; on the user page (S4 later, now the existing page): passes, grant, revoke.

## 6. Tests to require
Locked start refused; resume of an open attempt allowed after expiry; staff/preview/Student view unaffected; non-platform courses never locked even if the column says paid; practice rule; redemption: wrong, used, revoked, case/dash variants, concurrent double redeem (PG), rate limits, extension arithmetic, `ends_on` in Bishkek time; admin actions audited; isolation (a student never sees another's pass); ORT parity unchanged for a student with access and for free tests.

## 7. Changes after the security review (2026-11-06, Fable; these override the sections above)
1. **Resume after a pass ends** (was "resuming never checks"): an open attempt of a paid exam may be resumed after the pass ended **only if it is timed** (`deadline_at` set), so it closes by itself. An untimed open attempt (including practice sets) is refused with `access_required` until the student has a pass again; its answers are kept. Otherwise a 1-day pass could open every exam and keep them for months.
2. **Per-user serialization:** redeem and admin grant lock the user's row (`SELECT … FOR UPDATE` on `users`) in the same transaction as the code `UPDATE` and the pass `INSERT`; the code is never burned in a separate commit. Concurrent redeem + grant can't overlap or lose days.
3. **Test students** (`Enrollment.is_test_student`, Student view) are never locked: the check reads the enrollment row `accommodations.start_context` already loads.
4. **No-benefit codes:** an `ends_on` code whose date is not later than the current pass end is refused with `code_no_benefit` before anything is written; a batch whose `ends_on` has passed refuses with `code_invalid`. Pass times are stored UTC-aware and compared through `timing.as_utc` (SQLite stores naive).
5. **Privacy:** `given_note` (the buyer, possibly a third person) is set to null when the redeeming user is anonymized and is never in a student's export; `access_passes` rows stay as tombstones (revenue record).
6. **Admin limits:** a grant needs a reason and is capped at 400 days; the CSV export is audited with batch id and count; revealing more than 20 codes in an hour puts an item on the admin attention list.
7. **Unnoticed paid exams:** no ORT screen changes (rule 9). Instead the admin "Access" page and the overview list exams published in the last 14 days with their tier, so the owner sees what became paid.
8. **Transfer and refund:** documented path = revoke the pass (reason) and grant to the other account (reason), both audited.
