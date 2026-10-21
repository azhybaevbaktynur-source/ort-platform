# ORT / ЖРТ Test-Prep & Learning Management Platform
# Developer & Autonomous Agent Guide (Ground Truth)

> **Document Version**: 2.0.0 (Updated October 2026)  
> **Source of Truth**: Verified against real application code, SQLAlchemy models, FastAPI routes, and Next.js 15 pages.  
> **Note for Autonomous Agents**: Read this entire document before executing any task. It documents the real architecture, operational commands, schemas, and hard constraints so you can start building immediately without exploratory token burn.

> **Next agent: start with `docs/HANDOFF_NEXT_AGENT.md`** (current state, decisions, plan, model/token rules). Direction: teacher-owned LMS, see `docs/IMPLEMENTATION_PLAN.md`. Target: ~6,000 concurrent students.

---

## 1. Project Overview & Mission

The **ORT Platform** (Жалпы республикалык тестирлөө / Общереспубликанское тестирование) is a high-performance, bilingual exam preparation and learning management system designed for Kyrgyz high-school students.

### Key Capabilities
* **12,000+ Multilingual Questions**: Monolingual Kyrgyz (`ky`) and Russian (`ru`) questions with LaTeX math equations, reading passages, geometry diagrams, and quantitative comparisons.
* **Bluebook-Style Exam Simulator**: Realistic timed mock exams with strict section progression, autosave, question flags, and keyboard shortcuts.
* **Calibrated Normative Scoring**: Converts raw scores into official ORT scaled scores (60–245 for Main Test, 60–150 for Subject Tests) and percentile ranks.
* **Canvas LMS Architecture**: Evolving from an unguided exam bank into an Instructure Canvas-style LMS with Course blueprints, Cohorts/Sections, Modules, and Gating rules (see `docs/CANVAS_INTEGRATION_SPEC.md`).
* **Digitizer Bundle Import**: Binary `.zip` import engine accepting question packages from `ort-digitizer` with content-addressed image deduplication.

---

## 2. Real Tech Stack Architecture (Ground Truth)

### 2.1 Backend (Python / FastAPI)
* **Framework**: Python 3.11+ / FastAPI (`backend/app/main.py`).
* **Database & ORM**: **SQLAlchemy 2.0** (`app.db.session`).
  * **Development / Local**: SQLite (`sqlite:///./test.db`).
  * **Automated Tests**: Dynamic scratch SQLite databases in `/tmp`.
  * **Production (Render)**: PostgreSQL via `psycopg2-binary`.
* **Migrations**: Automated lightweight runtime migrations in `backend/app/db/` (`init_db.py`, `user_migrations.py`, `attempt_migrations.py`, `question_order_migration.py`) applying `ALTER TABLE ADD COLUMN` at server startup.
* **Firebase Role**: In-memory dictionary mock (`PersistentLocalFirestore` in `app/db/firebase.py`) enabled by default (`FIREBASE_MOCK_MODE=True`). Acts as a secondary mirror; SQL is the primary source of truth.
* **Authentication**: Self-hosted **FastAPI JWT (`HS256`, PyJWT)** + **bcrypt** password hashing. Roles are verified from the database on every request. 6-digit email confirmation codes and password resets dispatched via **Resend API**, **Brevo API**, **SMTP**, or terminal **Console**.
* **Storage Engine**: `LocalStorageService` saving files to disk (`backend/data/uploads`, mounted at `/uploads`), with cloud provider interface stub (`app/services/storage_service.py`).

### 2.2 Frontend (Next.js 15 / React 19)
* **Framework**: Next.js 15 (App Router) + React 19 (`frontend/src/app/`).
* **Styling**: Tailwind CSS (`tailwind.config.ts`), Lucide React icons.
* **Math Rendering**: KaTeX (`katex.renderToString`) via custom parsing in `frontend/src/components/math/MathRenderer.tsx`.
* **State & Data Fetching**: Native React hooks (`useState`, `useEffect`, `useCallback`) and React Context (`AuthContext`, `I18nContext`). Standard `fetch` wrapped in `frontend/src/lib/api.ts`. *(Zustand and React Query are NOT used).*
* **Internationalization (i18n)**: 100% bilingual Kyrgyz (`ky`) and Russian (`ru`) dictionaries in `frontend/src/lib/i18n/ky.json` and `ru.json`.

---

## 3. Directory & File Map

```text
ort-platform/
├── AGENTS.md                               # This guide (canonical instructions for all agents)
├── CLAUDE.md -> AGENTS.md                  # Symlink for Claude Code agents
├── sample_ort_questions.csv                # Sample Kyrgyz question dataset
├── sample_ort_questions_ru.csv             # Sample Russian question dataset
│
├── backend/                                # FastAPI Backend Application
│   ├── app/
│   │   ├── main.py                         # FastAPI entrypoint, CORS, /uploads static mount, /health
│   │   ├── core/
│   │   │   ├── config.py                   # Pydantic BaseSettings, JWT keys, email settings
│   │   │   ├── security.py                 # get_current_user, bcrypt, JWT create/verify, role checkers
│   │   │   └── exceptions.py               # Custom HTTP exceptions (EntityNotFound, Validation, etc.)
│   │   ├── db/
│   │   │   ├── session.py                  # SQLAlchemy engine, SessionLocal, get_db dependency
│   │   │   ├── init_db.py                  # Schema creation, canonical exam set seeding, migrations
│   │   │   ├── firebase.py                 # PersistentLocalFirestore (mock Firestore store)
│   │   │   ├── user_migrations.py          # User auth columns runtime migration
│   │   │   ├── attempt_migrations.py       # TestAttempt is_preview column migration
│   │   │   └── question_order_migration.py # Question position/q_num migration & backfill
│   │   ├── models/                         # SQLAlchemy 2.0 ORM Models
│   │   │   ├── user.py                     # User model (auth, role, target_score, email_code)
│   │   │   ├── exam_set.py                 # ExamSet model (exam_type, status, PIN, time_limit)
│   │   │   ├── question.py                 # Question model (stem, column_a/b, position, passage)
│   │   │   ├── exam_access.py              # ExamAccess model (student-to-exam permissions)
│   │   │   ├── test_attempt.py             # TestAttempt model (answers, scores, review, is_preview)
│   │   │   └── question_source.py          # QuestionSource model (external_id deduplication)
│   │   ├── schemas/                        # Pydantic v2 Request/Response Schemas
│   │   │   ├── user.py                     # UserProfile, registration, login, token schemas
│   │   │   ├── question.py                 # QuestionCreate/Update, SectionType, math_1 rule
│   │   │   ├── mock_test.py                # ExamSet, session start/progress/result schemas
│   │   │   ├── bundle_import.py            # Zip bundle manifest and import report schemas
│   │   │   ├── bulk_upload.py              # CSV dry-run validation report schemas
│   │   │   ├── analytics.py                # Student and instructor analytics schemas
│   │   │   └── practice.py                 # Practice question and set submission schemas
│   │   ├── services/                       # Business Logic Layer
│   │   │   ├── scoring_service.py          # ORT normative raw-to-scaled score & percentile engine
│   │   │   ├── bundle_service.py           # .zip bundle parser, SHA-256 image addressing, upsert
│   │   │   ├── csv_service.py              # 15-column CSV parser, preview validator, Cyrillic checks
│   │   │   ├── csv_image_rule.py           # Image URL rules & PlainCsvService
│   │   │   ├── question_service.py         # Question bank queries, CRUD, section reordering
│   │   │   ├── question_order.py           # Strict document order sorting & position management
│   │   │   ├── mock_test_service.py        # Exam sessions, PIN check, attempt limits, autosave, grading
│   │   │   ├── practice_service.py         # Fast practice questions feed & topic extraction
│   │   │   ├── email_service.py            # Resend/Brevo/SMTP/Console outgoing email dispatcher
│   │   │   └── storage_service.py          # Local disk / Cloud file storage interface
│   │   └── api/v1/
│   │       ├── router.py                   # Master v1 router aggregating all endpoints
│   │       └── endpoints/
│   │           ├── auth.py                 # Login, register, email verification, password reset
│   │           ├── users.py                # Profile inspection, target score updates
│   │           ├── questions.py            # Question bank listing, CRUD, move up/down
│   │           ├── exam_sets.py            # LMS exam sets & student-gated exam listing
│   │           ├── mock_tests.py           # Test start, progress autosave, submit & score, history
│   │           ├── admin.py                # Student roster, toggle exam access per student
│   │           ├── bulk.py                 # CSV dry-run validation, zip bundle import endpoints
│   │           ├── practice.py             # Section practice questions & set submissions
│   │           ├── analytics.py            # Student mastery breakdown & instructor cohort metrics
│   │           ├── upload.py               # Image upload handler (/uploads)
│   │           └── planner.py              # Daily planner tasks (currently in-memory stub)
│   ├── tests/                              # Pytest Test Suite (106 tests)
│   │   ├── conftest.py                     # Test environment setup, mock tokens, DB reset fixtures
│   │   ├── auth_helpers.py                 # Test account seeds (usr_admin_01, usr_student_01)
│   │   ├── test_api_endpoints.py           # Integration tests across all endpoints
│   │   ├── test_auth_flow.py               # Registration, code verification, password reset tests
│   │   ├── test_bundle_import.py           # Zip bundle validation and import tests
│   │   ├── test_csv_ingestion.py           # CSV validation and parsing tests
│   │   ├── test_math_section_rule.py       # math_1 quantitative comparison enforcement tests
│   │   ├── test_mock_test_service.py       # Session initiation, PIN gating, autosave tests
│   │   ├── test_practice_endpoints.py      # Practice feed and submission tests
│   │   ├── test_question_order.py          # Document order preservation and move up/down tests
│   │   ├── test_question_service.py        # Question bank CRUD tests
│   │   ├── test_scoring.py                 # ORT and Subject scoring algorithm unit tests
│   │   └── test_student_mode.py            # Admin student mode preview & preview exclusion tests
│   ├── requirements.txt                    # Python dependencies
│   └── pytest.ini                          # Pytest configuration
│
├── frontend/                               # Next.js 15 Frontend Application
│   ├── src/
│   │   ├── app/
│   │   │   ├── layout.tsx                  # Root layout (fonts, metadata)
│   │   │   ├── page.tsx                    # Root redirect to /[lang]
│   │   │   └── [lang]/                     # i18n language route wrapper (ky | ru)
│   │   │       ├── layout.tsx              # Bilingual layout with I18nProvider
│   │   │       ├── page.tsx                # Public landing page with role-aware CTAs
│   │   │       ├── (auth)/                 # Authentication pages
│   │   │       │   ├── login/page.tsx      # Email/password login with code verification redirect
│   │   │       │   ├── register/page.tsx   # Student registration with 6-digit code modal
│   │   │       │   ├── forgot-password/    # Password reset link requester
│   │   │       │   └── reset-password/     # Password reset token consumer
│   │   │       ├── (student)/              # Student dashboard & examination portal
│   │   │       │   ├── layout.tsx          # Persistent sidebar, header, admin preview banner
│   │   │       │   ├── dashboard/page.tsx  # Student overview, target score, recent tests
│   │   │       │   ├── mock-tests/page.tsx # Available mock exams, in-progress resumes, PIN modal
│   │   │       │   ├── mock-tests/[testId]/page.tsx       # 1,779-line exam simulator UI
│   │   │       │   ├── mock-tests/[testId]/lobby/page.tsx # Pre-exam briefing & rules
│   │   │       │   ├── mock-tests/[testId]/result/page.tsx# Score report, percentile, breakdown
│   │   │       │   ├── practice/page.tsx   # Topic-by-topic drill practice
│   │   │       │   ├── mistakes/page.tsx   # Mistake notebook with full LaTeX reviews
│   │   │       │   ├── progress/page.tsx   # Student performance analytics & section mastery
│   │   │       │   └── review/page.tsx     # Alias to mistakes page
│   │   │       └── (admin)/                # Admin / Instructor management suite
│   │   │           ├── layout.tsx          # Admin dark navigation sidebar & role guard
│   │   │           ├── exams/page.tsx      # Exam set management (create, publish, PIN, schedule)
│   │   │           ├── exams/[examId]/page.tsx # Question reordering & exam detail builder
│   │   │           ├── questions/page.tsx  # 12,000+ question bank manager (search, filter, CRUD)
│   │   │           ├── students/page.tsx   # Student roster & per-exam access permission toggles
│   │   │           ├── bulk-upload/page.tsx# CSV upload validator & zip bundle importer
│   │   │           └── analytics/page.tsx  # Cohort score distribution (<110 to 219+) & hard Qs
│   │   ├── components/
│   │   │   ├── auth/VerifyEmailStep.tsx    # 6-digit email confirmation code modal
│   │   │   ├── bulk/BundleImportPanel.tsx  # Ort-digitizer zip bundle upload panel
│   │   │   ├── common/Header.tsx           # Global header with language switcher & user menu
│   │   │   ├── common/Sidebar.tsx          # Student collapsible navigation sidebar
│   │   │   ├── exam/ComparisonQuestionCard.tsx # Math I quantitative comparison layout (Col A vs B)
│   │   │   ├── exam/ExamTimer.tsx          # Timed section countdown timer
│   │   │   ├── exam/NumberedPassage.tsx    # Reading passage renderer with [N] line numbering
│   │   │   ├── exam/QuestionCard.tsx       # Multiple-choice question card with option buttons
│   │   │   ├── exam/QuestionPalette.tsx    # Exam navigation grid with answered/flagged indicators
│   │   │   ├── math/MathRenderer.tsx       # KaTeX LaTeX equation renderer
│   │   │   ├── planner/DailyPlannerWidget.tsx # Daily study planner widget
│   │   │   ├── planner/TargetScoreWidget.tsx  # 60–245 target score tracker & Golden Cert delta
│   │   │   └── ui/Toast.tsx                # Toast notifications
│   │   └── lib/
│   │       ├── api.ts                      # apiClient and getAuthHeader attaching JWT
│   │       ├── auth-context.tsx            # AuthProvider, token persistence, userProfile state
│   │       ├── useBackendWarmup.ts         # Cold-start warmup pinger for Render instances
│   │       └── i18n/                       # Localization
│   │           ├── ky.json                 # Kyrgyz translations
│   │           ├── ru.json                 # Russian translations
│   │           └── context.tsx             # Translation provider & useTranslation hook
│   ├── package.json
│   ├── tsconfig.json
│   └── tailwind.config.ts
│
└── docs/
    ├── CURRENT_STATE_AUDIT.md              # Comprehensive architecture audit report
    ├── BUNDLE_FORMAT.md                    # Ort-digitizer zip bundle specification
    ├── CANVAS_INTEGRATION_SPEC.md          # Complete Canvas LMS integration specification
    └── CANVAS_EXPLAINER_FOR_FOUNDER.md     # Strategic LMS vision for product leadership
```

---

## 4. Database Models & Schema Reference (SQLAlchemy)

All models inherit from `app.db.session.Base` and are defined in `backend/app/models/`:

### 4.1 `User` (`users` table)
* `id` (String, PK)
* `email` (String, Unique, Index, Not Null)
* `password_hash` (String, Not Null) — bcrypt hash
* `role` (String, Default "student", Not Null) — `"student"` or `"admin"`
* `phone` (String, Nullable)
* `target_score` (Integer, Default 200) — ORT target (60–245)
* `display_name` (String, Nullable)
* `email_verified` (Boolean, Default True) — False for pending self-registrations
* `email_code_hash` (String, Nullable) — HMAC-SHA256 of 6-digit confirmation code
* `email_code_expires` (DateTime, Nullable)
* `email_code_attempts` (Integer, Default 0)
* `email_code_sent_at` (DateTime, Nullable)
* `reset_token` (String, Nullable) — SHA-256 of reset token
* `reset_token_expires` (DateTime, Nullable)
* `exams_taken` (Integer, Default 0)
* `current_score` (Integer, Default 0)
* `starting_score` (Integer, Default 0)
* `created_at` (DateTime, UTC)

### 4.2 `ExamSet` (`exam_sets` table)
* `id` (String, PK) — e.g. `"ort_main_standard"`, `"ort_subject_chemistry_ky"`
* `title` (String, Not Null)
* `description` (Text, Nullable)
* `language` (String, Default "ky") — `"ky"` or `"ru"`
* `exam_type` (String, Default "full_main") — `"full_main"`, `"subject"`, or `"practice_bank"`
* `status` (String, Default "draft") — `"draft"` or `"published"`
* `available_from` / `available_until` (String, ISO UTC, Nullable)
* `access_code` (String, Nullable) — 4-digit PIN access code
* `max_attempts` (Integer, Default 1)
* `sections` (JSON) — `[{"section": "math_1", "questionCount": 30, "timeLimitMinutes": 45}, ...]`
* `total_questions` (Integer, Default 0)
* `total_time_minutes` (Integer, Default 170)
* `time_limit_minutes` (Integer, Nullable)
* `question_ids` (JSON) — Ordered array of question IDs
* Relationships: `questions` (cascade delete), `access_rules` (cascade delete), `attempts` (cascade delete).

### 4.3 `Question` (`questions` table)
* `id` (String, PK) — e.g. `"q_123456789abc"`
* `language` (String, Default "ky")
* `section` (String, Index, Not Null) — `math_1`, `math_2`, `analogies`, `reading`, `grammar`, `chemistry`, `biology`, `physics`, `history`, `english`, `advanced_math`, `native_language`
* `topic` (String, Index, Not Null)
* `difficulty` (String, Default "medium") — `"easy"`, `"medium"`, `"hard"`
* `stem` (Text, Default "") — Question text with KaTeX LaTeX formulas
* `column_a` / `column_b` (Text, Nullable) — **Mandatory for `math_1`**
* `option_a` .. `option_d` (Text, Default "")
* `option_e` (Text, Nullable) — Used in 5-option subject questions
* `correct_option` (String, Not Null) — `"A"`, `"B"`, `"C"`, `"D"`, `"E"`
* `explanation` (Text, Nullable)
* `image_url` (String, Nullable) — Public path `/uploads/...` or external URL
* `passage_text` (Text, Nullable) — Reading comprehension text with `[N]` line markers
* `tags` (JSON, Default `[]`)
* `exam_set_id` (String, FK `exam_sets.id`, Index, Nullable)
* `position` (Integer, Nullable) — 1-based order within original document
* `q_num` (String, Nullable) — Question number printed in original source
* `stats` (JSON) — `{"totalAttempts": N, "correctAttempts": N, "discriminationIndex": F}`

### 4.4 `ExamAccess` (`exam_access` table)
* `id` (String, PK)
* `user_id` (String, FK `users.id`, Index, Not Null)
* `exam_set_id` (String, FK `exam_sets.id`, Index, Not Null)
* `granted_at` (DateTime, UTC)
* Unique Constraint: `(user_id, exam_set_id)`

### 4.5 `TestAttempt` (`test_attempts` table)
* `id` (String, PK)
* `user_id` (String, FK `users.id`, Index, Not Null)
* `template_id` (String, Index, Not Null) — Refers to `exam_sets.id`
* `language` (String, Default "ky")
* `status` (String, Default "in_progress") — `"in_progress"`, `"completed"`, `"timed_out"`
* `started_at` (DateTime, UTC)
* `completed_at` (DateTime, Nullable)
* `total_time_seconds` (Integer, Default 0)
* `remaining_time_seconds` (Integer, Nullable)
* `current_section_index` (Integer, Default 0)
* `question_ids` (JSON)
* `answers` (JSON) — `{"<q_id>": {"selectedOption": "B", "isFlagged": false, ...}}`
* `scores` (JSON) — Scaled scores, raw scores, section breakdowns, percentile
* `review` (JSON) — Detailed question review items
* `is_preview` (Boolean, Default False) — **True for admin student mode; excluded from all analytics**

### 4.6 `QuestionSource` (`question_sources` table)
* `external_id` (String, PK) — `<source_id>:<section>:<q_num>`
* `question_id` (String, FK `questions.id`, Unique, Index, Not Null)
* `source_id` (String, Index, Not Null)
* `section` / `q_num` (String, Nullable)
* `fixed` (Boolean, Default False)
* `image_sha256` (String, Nullable)

---

## 5. Core Business Logic & Scoring Rules

### 5.1 ORT Standard Normative Scoring (`app/services/scoring_service.py`)
* **Main Test Scale**: 60 to 245 points (Mean: 150.0, Standard Deviation: 30.0).
  * Uses a calibrated logistic-normative curve modeling Kyrgyz national scholarship data.
  * Formula rewards high accuracy near the top while modeling guessing thresholds at the bottom.
* **Subject Test Scale**: 60 to 150 points (Mean: 105.0, Standard Deviation: 20.0).
* **Golden Certificate Threshold**: **219+ points** (`settings.GOLDEN_CERTIFICATE_MIN_SCORE`).
* **Percentile Calculation**: Cumulative percentile rank computed using the standard normal cumulative distribution function (CDF).

### 5.2 Section Ordering & Math I Rule
* **Strict Section Order**:
  `math_1` $\rightarrow$ `math_2` $\rightarrow$ `analogies` $\rightarrow$ `reading` $\rightarrow$ `grammar` $\rightarrow$ (subject sections: `chemistry`, `biology`, `physics`, `advanced_math`, `history`, `english`, `native_language`).
* **Quantitative Comparison Rule** (`app/services/csv_image_rule.py`):
  * `math_1` is **always** quantitative comparison: `column_a` and `column_b` are strictly required.
  * Standard choices:
    * A: Колонка А чоңураак / Колонка А больше
    * B: Колонка Б чоңураак / Колонка Б больше
    * C: Эки чоңдук барабар / Величины равны
    * D: Маалымат жетишсиз / Недостаточно информации
  * `math_2` and other sections are standard multiple-choice and must NOT use columns.

### 5.3 Student Access Control & Admin Student Mode
* **Practice Banks (`practice_bank`)**: Always open to all registered students without permissions or PINs.
* **Full Main & Subject Exams**:
  * Normal students can **only** see and start exams if an explicit record exists in `exam_access` (granted by an admin in `students/page.tsx`).
  * If a PIN is configured (`access_code`), the student must enter the correct 4-digit code.
* **Admin Student Mode (Preview)**:
  * When an admin enters the student portal, the server role check identifies them as admin.
  * Admins see **all published exams** regardless of `exam_access` records and are not limited by `max_attempts`.
  * Every attempt started by an admin is marked with `is_preview = True`.
  * **Preview Exclusion**: Admin preview attempts are strictly excluded from student analytics (`/analytics/instructor`), completion counts, and user score cards.
  * A persistent amber banner (`"Режим ученика (предпросмотр)"`) is shown on every student page with a quick link back to `/exams`.

---

## 6. Verification & Testing Commands

### 6.1 Backend Verification (Python / FastAPI)
> [!IMPORTANT]
> **Always use a scratch SQLite database and scratch upload folder** for backend tests. Never touch the developer database `backend/test.db` or `backend/data/`.

```bash
# Run the entire test suite in isolated scratch mode:
cd backend && /bin/rm -rf /tmp/agy_t && /bin/mkdir -p /tmp/agy_t/up && \
DATABASE_URL="sqlite:////tmp/agy_t/test.db" LOCAL_UPLOAD_DIR="/tmp/agy_t/up" \
venv/bin/python -m pytest -q -p no:cacheprovider -W ignore
```
*(Expected output: 106 passed in ~7 seconds).*

```bash
# Run specific test modules:
DATABASE_URL="sqlite:////tmp/agy_t/test.db" LOCAL_UPLOAD_DIR="/tmp/agy_t/up" \
venv/bin/python -m pytest tests/test_student_mode.py -v

DATABASE_URL="sqlite:////tmp/agy_t/test.db" LOCAL_UPLOAD_DIR="/tmp/agy_t/up" \
venv/bin/python -m pytest tests/test_question_order.py -v

DATABASE_URL="sqlite:////tmp/agy_t/test.db" LOCAL_UPLOAD_DIR="/tmp/agy_t/up" \
venv/bin/python -m pytest tests/test_bundle_import.py -v
```

```bash
# Run backend development server:
cd backend && venv/bin/uvicorn app.main:app --reload --port 8000
```

### 6.2 Frontend Verification (Next.js / TypeScript)
> [!NOTE]
> Do NOT run `npm run build` directly inside `frontend/` if a dev server is active or `.next` is locked. Use a clean temporary copy for isolated verification:

```bash
# Fast TypeScript typecheck:
cd frontend && npx tsc --noEmit
```

```bash
# Clean isolated frontend build check:
/bin/rm -rf /tmp/agy_fe && /bin/mkdir -p /tmp/agy_fe && \
rsync -a --exclude node_modules --exclude .next frontend/ /tmp/agy_fe/ && \
ln -s "$PWD/frontend/node_modules" /tmp/agy_fe/node_modules && \
cd /tmp/agy_fe && npx tsc --noEmit && npx next build
```

```bash
# Run frontend development server:
cd frontend && npm run dev
```

---

## 7. Hard Operational Rules for Agents

1. **NEVER read, print, or modify `backend/.env`**:
   * It contains live third-party API credentials (Brevo, Resend, database keys).
   * Reference `backend/.env.example` or `app/core/config.py` for environment variables.
2. **Never commit passwords to code or seeds**:
   * Repository is public. `init_db.py` must never create accounts with hardcoded passwords.
   * Admins are created via `make_admin.py` after registration, or via test helpers with dynamic passwords in `tests/auth_helpers.py`.
3. **Strict Bilingual Discipline**:
   * Every user-facing UI label, button, error message, or prompt MUST exist in both Kyrgyz (`ky`) and Russian (`ru`).
   * Add keys to both `frontend/src/lib/i18n/ky.json` and `ru.json`. Hardcoded single-language strings are prohibited.
4. **Shell Alias Safety**:
   * Interactive shells alias `rm`, `cp`, `mv` to interactive `-i`. Always use `/bin/rm -f`, `/bin/cp -f`, `/bin/mv -f` in automation scripts.
5. **Server-Side Authorization**:
   * Never trust client JWT claims for role checks. Always query the `users` table via `get_current_user` to verify permissions.
6. **No Unbounded Firestore Reads**:
   * Always paginate question queries using `limit` and `offset`. Never load the entire 12,000+ question bank into frontend memory.

---

## 8. Current Roadmap & High-Priority Tasks

Autonomous agents continuing work on this platform should focus on these concrete next steps:

1. **Persist the Daily Study Planner**:
   * Current status: `backend/app/api/v1/endpoints/planner.py` uses an in-memory dictionary `USER_DAILY_TASKS` with static dummy tasks.
   * Task: Create a SQL model `StudyTask` linked to `users.id`, generating tasks dynamically from the student's weak topics identified in `/analytics/student`.
2. **Wire Real Reviews to Mock Test Result Page**:
   * Current status: `frontend/src/app/[lang]/(student)/mock-tests/[testId]/result/page.tsx` renders real score cards, but the bottom question review section renders a static 2-item mock array (`reviewedQuestions`).
   * Task: Replace the static mock array with the real `attempt.review` data already calculated by `submit_and_score_test` and displayed in `mistakes/page.tsx`.
3. **Canvas LMS Orchestration Layer (Phase 1)**:
   * Implement the non-destructive Canvas wrapper specified in `docs/CANVAS_INTEGRATION_SPEC.md` and `docs/CANVAS_EXPLAINER_FOR_FOUNDER.md`:
   * Models to add: `Account` (School/Center), `Course` (Curriculum), `Section` (Cohort), `Enrollment` (Student/Teacher linkage), `Module`, and `ModuleItem`.
   * Gating Engine: Add sequential completion rules unlocking Module $N+1$ based on Module $N$ quiz scores.
