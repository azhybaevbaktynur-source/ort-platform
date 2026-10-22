# Codebase Audit & Ground-Truth Architecture Report
**Generated**: October 2026  
**Auditor**: Senior Codebase Auditor (Autonomous Architecture Audit)  
**Workspace**: `/Users/baktynurazhybaev/ort-platform`  
**Current Branch**: `fix/question-order` (Commit: `94e8124`)  
**Scope**: Complete read-only inspection of backend code, frontend implementation, database schemas, auth mechanisms, commit history, and LMS abstractions.

---

## Executive Summary

A comprehensive, read-only audit of the ORT Platform codebase reveals a critical divergence between the documentation in `AGENTS.md` and the actual production-ready implementation. 

While `AGENTS.md` claims the application is built on a pure Google Firebase stack (Firebase Auth, Cloud Firestore, Firebase Storage) with Zustand/React Query state management, the **ground truth in code is entirely different**:
1. **Primary Persistence**: The active source of truth is **SQLAlchemy 2.0** backed by **SQLite** in development/testing and **PostgreSQL** in production (via `psycopg2`).
2. **Authentication**: Fully independent, self-hosted **FastAPI JWT Authentication** (`HS256`) using **bcrypt** password hashing, database-backed roles, and a 6-digit email verification / password-reset flow powered by **Resend** and **Brevo** APIs. Firebase Auth is not used by the application.
3. **Frontend Architecture**: Modern **Next.js 15 (App Router)** and **React 19** utilizing native React hooks (`useState`, `useEffect`, React Context) and standard `fetch` API wrappers. Zustand, React Query, and Firebase Client SDK are entirely absent from active runtime consumption.
4. **Current Status**: The core testing, question bank management, scoring, and digitizer bundle ingestion engines are 100% operational and covered by 106 passing backend tests. However, the platform remains an "Exam Bank" rather than a full LMS: cohort management, course structures, modules, and teacher grading workflows remain to be implemented.

---

## 1. Real Architecture vs. Claimed Architecture

### 1.1 True Database & Persistence Architecture
* **Primary Database**: Relational SQL managed via **SQLAlchemy 2.0** (`app.db.session`).
  * **Local / Development**: `sqlite:///./test.db` (with path normalization in `backend/app/db/session.py`).
  * **Automated Tests**: Isolated SQLite databases created dynamically in `/tmp` per test run.
  * **Production (Render)**: PostgreSQL via connection URI (`postgresql://...`) with connection pre-ping enabled (`pool_pre_ping=True`).
* **Active ORM Models** (`backend/app/models/`):
  1. `User` (`users` table): User credentials, bcrypt hash, role (`student` vs `admin`), email verification tokens/codes, target scores, and exam counters.
  2. `ExamSet` (`exam_sets` table): Curated exam packages, section configurations, time limits, access codes (PINs), availability windows, and status (`draft` vs `published`). Cascades deletion to questions, access rules, and test attempts.
  3. `Question` (`questions` table): Multilingual questions, section types, topics, LaTeX stems, column A/B comparisons, options A-E, explanations, passage texts, image URLs, document order positions (`position`), and printed question numbers (`q_num`).
  4. `ExamAccess` (`exam_access` table): Granular student-to-exam permission grants with composite unique constraint `(user_id, exam_set_id)`.
  5. `TestAttempt` (`test_attempts` table): User test sessions, autosaved in-flight answers, section progress, remaining time, scaled scores, full detailed reviews, and the `is_preview` flag for admin student mode.
  6. `QuestionSource` (`question_sources` table): External ID linkage (`<source_id>:<section>:<q_num>`) ensuring idempotency and deduplication when importing question bundles from `ort-digitizer`.
* **Database Migrations**:
  * Lightweight runtime schema synchronizers in `backend/app/db/` (`user_migrations.py`, `attempt_migrations.py`, `question_order_migration.py`, and `init_db.py`).
  * Executes safe `ALTER TABLE ADD COLUMN` queries upon server startup for both SQLite and PostgreSQL. No Alembic dependency is currently used.
* **The Role of Firebase**:
  * In the backend (`backend/app/db/firebase.py`), `FIREBASE_MOCK_MODE=True` by default. It provides an in-memory dictionary-backed mock class (`PersistentLocalFirestore`).
  * It serves as a **secondary best-effort mirror** for legacy query shapes. Writes to SQL are mirrored to the in-memory store; reads fall back to in-memory only when the SQL database has not yet seeded a canonical set.
  * Live Google Cloud Firestore client is only instantiated if an explicit `FIREBASE_CREDENTIALS_PATH` is passed in environment variables.
  * In the frontend (`frontend/src/lib/firebase.ts`), a dummy mock config exists, but **zero active components import or interact with Firebase**.

### 1.2 True Authentication & Authorization Mechanism
* **Backend JWT**: `PyJWT` issuing signed tokens with `HS256` using `settings.SECRET_KEY`.
* **Password Hashing**: `bcrypt` using configurable rounds (default 10 for performance on constrained cloud instances).
* **Role Verification**:
  * Roles are strictly **enforced from the database on every request** in `backend/app/core/security.py:get_current_user`.
  * Client JWT claims for `role` are never trusted blindly; the SQL `users` table is re-queried to verify active account standing and role (`student` vs `admin`).
* **Self-Registration & Verification Flow**:
  1. User registers via `POST /api/v1/auth/register`.
  2. System issues a random 6-digit verification code hashed with HMAC-SHA256 (`_secret_hash(f"{user.id}:{code}")`), with a 10-minute TTL and 60-second resend cooldown.
  3. Code is dispatched via `backend/app/services/email_service.py`.
  4. Verification completed via `POST /api/v1/auth/verify-email`.
* **Email Providers**:
  * Supported drivers in `email_service.py`: **Resend** (HTTPS API), **Brevo** (HTTPS API), **SMTP** (fallback), and **Console** (local terminal logging).
  * Automatically selected based on available environment variables (`RESEND_API_KEY`, `BREVO_API_KEY`, `SMTP_SERVER`).
* **Frontend Session Management**:
  * `frontend/src/lib/auth-context.tsx` and `api.ts` manage tokens via `localStorage` (`ort_token`, `ort_role`, `ort_dev_auth_user`) and cookies (`SameSite=Lax`).
  * Every API call injects `Authorization: Bearer <token>` via `getAuthHeader()`.

### 1.3 Media & File Storage
* **Backend Storage Engine** (`backend/app/services/storage_service.py`):
  * Abstract `BaseStorageService` with `LocalStorageService` and `CloudStorageService` implementations.
  * Default mode is `local`: files are stored in `backend/data/uploads` and mounted statically by FastAPI at `/uploads`.
  * Supports content-addressed deduplication via SHA-256 for digitizer bundle imports.
  * Firebase Storage is **not used**.

---

## 2. AGENTS.md Discrepancy Matrix

The following table explicitly contrasts every claim in `AGENTS.md` against the real code found in the repository:

| Architectural Component | Claimed in `AGENTS.md` | Ground Truth in Code | Verification Source |
| :--- | :--- | :--- | :--- |
| **Primary Database** | Google Cloud Firestore (NoSQL, indexed collections) | **SQLAlchemy 2.0 + SQLite / PostgreSQL** | `backend/app/db/session.py`, `backend/app/models/` |
| **Database Migrations** | None mentioned (NoSQL collections) | **Runtime SQL column migrations** (`init_db.py`, `*_migrations.py`) | `backend/app/db/init_db.py` |
| **Authentication System** | Firebase Auth (Email/Pass, Google OAuth, custom claims) | **Custom FastAPI JWT (`HS256`) + bcrypt** + 6-digit email verification codes | `backend/app/core/security.py`, `backend/app/api/v1/endpoints/auth.py` |
| **Social Logins** | Google OAuth via Firebase | **Not Implemented** (only local email/password exists) | `frontend/src/app/[lang]/(auth)/login/page.tsx` |
| **Email Delivery** | None mentioned | **Resend API, Brevo API, SMTP, or Console logging** | `backend/app/services/email_service.py` |
| **Frontend State & Cache** | Zustand / React Query (TanStack Query) | **Zero Zustand/React Query**. Native React `useState`, `useEffect`, and Context API | `frontend/package.json`, `frontend/src/` |
| **LaTeX Math Engine** | KaTeX (`katex`, `rehype-katex`, `remark-math`) | **Direct KaTeX `renderToString`** with custom string splitter; no rehype/remark packages installed | `frontend/package.json`, `frontend/src/components/math/MathRenderer.tsx` |
| **File / Media Storage** | Firebase Storage | **Local disk (`backend/data/uploads`)** served at `/uploads`, or Cloud S3/Cloudinary adapter | `backend/app/services/storage_service.py`, `backend/app/main.py` |
| **Admin Route Structure** | `(instructor)` folder route | **`(admin)` folder route** (`frontend/src/app/[lang]/(admin)/`) | `frontend/src/app/[lang]/(admin)/` |
| **Digitizer Bundle Import**| Not mentioned | **Full Zip Import Engine (`BundleService`)** with SHA-256 image addressing & single-tx upserts | `backend/app/services/bundle_service.py`, `docs/BUNDLE_FORMAT.md` |
| **Question Order Control**| Unordered queries | **Strict document order (`position`)** + Admin move up/down endpoints | `backend/app/services/question_order.py`, `backend/app/api/v1/endpoints/questions.py` |
| **Math I Section Rule** | Generic multiple choice | **Quantitative Comparison Rule Enforced**: `math_1` requires Column A & B | `backend/app/services/csv_image_rule.py`, `backend/tests/test_math_section_rule.py` |

---

## 3. Operational Status of Backend Endpoints

The API router (`backend/app/api/v1/router.py`) mounts 12 specialized endpoint routers under `/api/v1`:

| Router Prefix | Endpoint File | Operational Status | Underlying Persistence | Notes |
| :--- | :--- | :--- | :--- | :--- |
| `/auth` | `auth.py` | **100% Complete** | SQL (`users`) | Register, verify email, resend code, login, forgot password, reset password, get `/me`. |
| `/users` | `users.py` | **100% Complete** | SQL (`users`) + Firestore mirror | Profile inspection, target score updates (`PUT /me/target-score`). |
| `/questions` | `questions.py` | **100% Complete** | SQL (`questions`, `exam_sets`) | List/filter questions, practice questions, CRUD, move question up/down within section. |
| `/exam-sets` & `/exams` | `exam_sets.py` | **100% Complete** | SQL (`exam_sets`, `exam_access`, `test_attempts`) | List exams, student exam access filtering (`/student`), attempt count tracking. |
| `/mock-tests` | `mock_tests.py` | **100% Complete** | SQL + Firestore mirror | Start test session (`/start`), save progress (`/save`), submit & score, attempts list. |
| `/admin` | `admin.py` | **100% Complete** | SQL (`users`, `exam_access`, `exam_sets`) | List students, inspect student access, toggle exam access per student, list all exams. |
| `/bulk` | `bulk.py` | **100% Complete** | SQL (`questions`, `exam_sets`, `question_sources`) | Dry-run CSV validation, CSV upload, digitizer `.zip` bundle validation and ingestion. |
| `/practice` | `practice.py` | **100% Complete** | SQL (`questions`) + Firestore | Random question feed by section/topic, distinct topics list, submit practice set. |
| `/analytics` | `analytics.py` | **100% Complete** | Firestore `test_attempts` & SQL `users` | Student analytics (section mastery, weak spots), instructor cohort analytics & distribution. |
| `/upload` | `upload.py` | **100% Complete** | Local disk / Cloud Storage | Accepts images (PNG, JPG, WebP), returns public URL `/uploads/...`. |
| `/planner` | `planner.py` | **Mocked / In-Memory** | Python global dict (`USER_DAILY_TASKS`) | Returns static hardcoded tasks (`task_1`, `task_2`, `task_3`); resets on process restart. |

---

## 4. Frontend Page Audit: Active vs. Placeholder UI

Every page inside `frontend/src/app` was inspected for actual data binding and functionality:

### 4.1 Student Portal (`frontend/src/app/[lang]/(student)/`)
* **`dashboard/page.tsx` — Active (100%)**:
  * Real dynamic calls to `/api/v1/analytics/student`, `/api/v1/exam-sets/student`, and `/api/v1/mock-tests/in-progress`.
  * Renders `TargetScoreWidget`, `DailyPlannerWidget`, active test attempts, and quick links to practice.
* **`mock-tests/page.tsx` — Active (100%)**:
  * Fetches published tests filtered by student language and granted access.
  * Handles in-progress attempt resumption, 4-digit PIN verification modals, attempt limits, and completed test badges.
* **`mock-tests/[testId]/page.tsx` — Active (100%)**:
  * 1,779 lines of robust testing UI.
  * Per-section timers, strict section ordering, question palette, autosave on answer selection, flagged question toggles, passage viewer with line numbers, quantitative comparison layouts, and final submission scoring.
* **`mock-tests/[testId]/lobby/page.tsx` — Active (100%)**:
  * Exam briefing lobby showing section breakdowns, question counts, time limits, and test instructions before session initiation.
* **`mock-tests/[testId]/result/page.tsx` — Partially Mocked**:
  * Top scaled score card, percentile, and section breakdown grids are **dynamically bound** to the test attempt results.
  * **Stubbed Element**: The detailed question review section at the bottom of the page renders a **static hardcoded 2-question mock array** (`reviewedQuestions`: `mq_1`, `mq_2`) instead of iterating over `resultData.review`.
* **`practice/page.tsx` — Active (100%)**:
  * Dynamic practice mode. Fetches distinct topics from `/practice/topics`, loads questions from `/practice/questions`, tracks answers, and submits completed sets to `/practice/submit-set`.
* **`mistakes/page.tsx` — Active (100%)**:
  * Fully functional error notebook ("туура эмес жооптор"). Loads completed test attempts from `/mock-tests/attempts`, filters out incorrect answers, and opens full LaTeX review modals with explanations.
* **`progress/page.tsx` — Active (100%)**:
  * Full analytics view consuming `/analytics/student`. Visualizes section mastery percentages, accuracy bars, and recent score history.
* **`review/page.tsx` — Active (Alias)**:
  * Drop-in alias rendering `<MistakesPortalPage />`.

### 4.2 Admin & Instructor Portal (`frontend/src/app/[lang]/(admin)/`)
* **`exams/page.tsx` — Active (100%)**:
  * ExamSet management. Lists custom and standard exams, creates new sets, edits time limits, toggles `draft`/`published`, configures 4-digit PINs, and schedules availability windows.
* **`exams/[examId]/page.tsx` — Active (100%)**:
  * Deep-dive exam set builder. Allows reordering questions up and down within sections (modifying `position`), editing questions, deleting questions, and previewing LaTeX formatting.
* **`students/page.tsx` — Active (100%)**:
  * Real student roster consuming `/api/v1/admin/students`. Displays student emails, target scores, registration dates, and modal controls to grant/revoke access to published exams.
* **`questions/page.tsx` — Active (100%)**:
  * Question bank management. Search by stem, filter by section, topic, language, and exam set. Full CRUD with KaTeX preview.
* **`bulk-upload/page.tsx` — Active (100%)**:
  * Dual-mode bulk uploader. Handles 15-column CSV dry-run validation and upload, as well as binary `.zip` bundle imports from `ort-digitizer` via `BundleImportPanel.tsx`.
* **`analytics/page.tsx` — Active (100%)**:
  * Cohort metrics consuming `/api/v1/analytics/instructor`. Score distributions (<110, 110-140, ..., 219+), Golden Certificate counts, and discrimination indices on hard questions.

### 4.3 Authentication & Public Routes (`frontend/src/app/[lang]/(auth)/` & Root)
* **`login/page.tsx` & `register/page.tsx` — Active (100%)**:
  * Integrated with custom FastAPI auth. Handles unverified account redirection, code resend cooldowns, and role-based redirects (`admin` to `/exams`, `student` to `/dashboard`).
* **`forgot-password/page.tsx` & `reset-password/page.tsx` — Active (100%)**:
  * Operational password reset loop via backend-issued reset tokens.
* **`page.tsx` (Landing Page) — Active (100%)**:
  * Bilingual landing portal with navigation links and role-aware CTAs.

---

## 5. Review of Recent Commits & `.handoff/` Notes

### 5.1 Commit History Analysis
Inspection of `git log -n 5 --stat` reveals key recent architectural upgrades:
1. **Commit `94e8124` (`feat: admin student mode is a real preview`)**:
   * Added `test_attempts.is_preview` column with automatic startup migration.
   * Excluded preview attempts from instructor analytics, score averages, and user stats.
   * Added persistent amber preview banner (`frontend/src/app/[lang]/(student)/layout.tsx`) with instant navigation back to `/exams`.
   * Enforced server-side role check from database (preventing client JWT tampering).
2. **Commit `c166d61` (`fix: questions always in document order; database as the source for tests`)**:
   * Migrated question ordering from random/unordered queries to strict source document order (`position`, `q_num`).
   * Added `backend/app/services/question_order.py` and move up/down endpoints.
   * Established SQL database as the primary source for tests, making Firestore secondary.
3. **Commit `4782ff3` (`feat: zip bundle import, math_1 comparison rule, rendering fixes, local work`)**:
   * Created `backend/app/services/bundle_service.py` for `.zip` bundle imports from `ort-digitizer`.
   * Enforced strict validation: `math_1` must always be quantitative comparison with Columns A and B.
   * Added content-addressed image storage via SHA-256 hashes.
4. **Commits `e7cede0` & `0a14734` (`fix(auth): security hardening`)**:
   * Removed public hardcoded admin passwords from seeding.
   * Improved email code resend ergonomics (clearing cooldowns on provider failures).

### 5.2 Test Verification
Running the backend test suite under isolated scratch conditions:
```bash
DATABASE_URL="sqlite:////tmp/test.db" LOCAL_UPLOAD_DIR="/tmp/up" pytest -q
```
**Result**: **106 passed in 7.21s**. All unit, integration, scoring, order, bundle, and student-mode preview tests pass without errors.

---

## 6. Functional Status & Missing LMS Abstractions

### 6.1 Features 100% Complete & Verified
* Timed exam engine with section switching, autosave, and keyboard shortcuts.
* Calibrated normative ORT scoring (60–245 points for Main Test, 60–150 for Subject Tests) and percentile ranks.
* Admin exam access management (gating exams per student account).
* Bulk ingestion via 15-column CSV and `ort-digitizer` ZIP bundles.
* Question reordering preserving original document page structure.
* Self-hosted JWT auth with email verification codes.
* Student mistake notebook ("Каталар менен иштөө") with full explanations.
* Comprehensive bilingual support (Kyrgyz `ky` and Russian `ru`) across UI and data models.

### 6.2 Features Mocked / Partially Stubbed
1. **Daily Planner (`planner.py`)**:
   * Tasks are currently stored in an in-memory dictionary (`USER_DAILY_TASKS = {}`).
   * The returned tasks are hardcoded stubs (`task_1`, `task_2`, `task_3`) rather than being generated dynamically by a study planner model based on user weak spots.
2. **Mock Test Result Breakdown (`[testId]/result/page.tsx`)**:
   * The individual question review list at the bottom of the result page is hardcoded to 2 dummy questions (`mq_1`, `mq_2`). The real attempt reviews are properly calculated by the backend and displayed on `mistakes/page.tsx`, but not yet wired into the immediate post-test result page.
3. **Cloud Storage Adapter (`storage_service.py`)**:
   * `CloudStorageService` is currently a logging stub; production deployment relies on local filesystem mounts.
4. **Firestore Backend**:
   * Operates as an in-memory mock store that does not persist across backend container restarts unless real Firebase credentials are provided.

### 6.3 Missing LMS Abstractions (as detailed in `docs/CANVAS_INTEGRATION_SPEC.md`)
The platform currently functions as a **Question Bank and Exam Simulator**, not a structured **Learning Management System**. The following key Canvas-style abstractions are absent:
* **No `Course` Entity**: There is no container grouping multiple mock exams, practice sets, and lessons into a structured 8-week or 12-week curriculum.
* **No `Section` (Classroom / Cohort) Entity**: Students cannot be grouped into classrooms (e.g., "Class 11-A", "Bishkek Morning Group") with specific cohort start/end dates.
* **No `Module` & `ModuleItem` Hierarchy**: No support for sequential learning units with gating rules (e.g., "Must score >= 70% on Geometry Practice before unlocking Full Mock #2").
* **No Multi-Tenancy (`Account` / `Sub-Account`)**: High schools, lyceums, and commercial test-prep centers cannot manage their own student bodies or teachers under isolated organizational umbrellas.
* **No `SpeedGrader` / Teacher Review**: No interface for instructors to inspect open-ended responses, review student scratch work, or leave text/audio feedback.
* **Binary RBAC**: The system only supports `student` and `admin` roles, lacking `instructor` (scoped to specific courses), `ta` (teaching assistant), and `observer` (parent/guardian).

---

## 7. Recommendations for Next Development Phase

1. **Synchronize `AGENTS.md`**: Update `AGENTS.md` immediately to reflect the reality of SQLAlchemy, PostgreSQL/SQLite, FastAPI JWT Auth, and the absence of Zustand/React Query.
2. **Promote Daily Planner to Database**: Create a SQL model `study_tasks` to persist student daily tasks and connect them to real performance weak spots from `/analytics/student`.
3. **Connect Real Reviews to `result/page.tsx`**: Replace the static `reviewedQuestions` array in `[testId]/result/page.tsx` with the real `attempt.review` data already available in the backend response.
4. **Implement Phase 1 of Canvas LMS Integration**: Implement the non-destructive `Account`, `Course`, `Section`, and `Enrollment` models as specified in `docs/CANVAS_INTEGRATION_SPEC.md` to support cohort-based learning.

