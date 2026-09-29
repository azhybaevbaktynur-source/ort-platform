# ORT / ЖРТ Test-Prep Platform - Developer & Agent Guide

## 1. Project Overview & Mission
The **ORT Platform** (Жалпы республикалык тестирлөө / Общереспубликанское тестирование) is a free, high-performance, Canvas-style test preparation and learning management platform designed for Kyrgyz students.
The platform is designed to handle **12,000+ questions**, provide **instant mock test feedback**, simulate realistic exam conditions, and support simultaneous usage by both **students** and **instructors**.

---

## 2. Tech Stack Architecture

### Frontend
- **Framework**: React 19 / Next.js 15 (App Router)
- **Styling**: Tailwind CSS with CSS variables, Lucide React icons
- **Math Rendering**: KaTeX (`katex`, `rehype-katex`, `remark-math`) for LaTeX equations
- **State & Data Fetching**: Zustand / React Query (TanStack Query)
- **Internationalization (i18n)**: Bilingual Kyrgyz (`ky`) and Russian (`ru`) support across all UI strings and content schemas

### Backend
- **Framework**: Python 3.11+ / FastAPI
- **Data Validation & Schemas**: Pydantic v2
- **Data Processing**: Pandas / Tabulate for high-throughput CSV bulk parsing and validation
- **Testing**: Pytest, Pytest-asyncio, HTTPX

### Database & Authentication
- **Provider**: Google Firebase
- **Authentication**: Firebase Auth (Email/Password, Google OAuth, custom claims for `student` vs `instructor`/`admin` roles)
- **Database**: Cloud Firestore (NoSQL, indexed collections for high-volume question queries)
- **Storage**: Firebase Storage (for reading comprehension diagrams, math figures, and passage attachments)

---

## 3. Directory & Folder Structure

```text
ort-platform/
├── AGENTS.md                         # Project standards, commands, guidelines
├── backend/                          # FastAPI Backend
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                   # FastAPI application entrypoint
│   │   ├── core/
│   │   │   ├── config.py             # App configurations & environment variables
│   │   │   ├── security.py           # Firebase Auth token verification & role enforcement
│   │   │   └── exceptions.py         # Custom HTTP and business logic exceptions
│   │   ├── db/
│   │   │   └── firebase.py           # Firebase Admin SDK initialization & Firestore client
│   │   ├── schemas/                  # Pydantic v2 models
│   │   │   ├── question.py           # Question & option schemas (bilingual)
│   │   │   ├── mock_test.py          # Mock test session & submission schemas
│   │   │   ├── user.py               # User profile, target scores, planner
│   │   │   └── analytics.py          # Instructor & student analytics schemas
│   │   ├── services/                 # Business logic
│   │   │   ├── scoring_service.py    # ORT raw-to-scaled score conversion (normative scale)
│   │   │   ├── csv_service.py        # 12,000+ question bulk CSV parser & batch writer
│   │   │   ├── question_service.py   # Question bank retrieval, filtering, pagination
│   │   │   └── analytics_service.py  # Performance aggregations & mistake tracking
│   │   └── api/
│   │       └── v1/
│   │           ├── router.py         # Aggregated v1 router
│   │           └── endpoints/
│   │               ├── auth.py       # Auth verify & role sync
│   │               ├── questions.py  # Question bank CRUD & filtering
│   │               ├── bulk.py       # CSV upload, validation & batch ingest
│   │               ├── mock_tests.py # Test generation, submission & instant scoring
│   │               ├── planner.py    # Daily planner, streaks, target score tracker
│   │               └── analytics.py  # Student & instructor performance metrics
│   ├── tests/                        # Backend test suite
│   │   ├── conftest.py               # Shared fixtures & mock Firebase clients
│   │   ├── test_scoring.py           # ORT scoring algorithm unit tests
│   │   ├── test_csv_ingestion.py     # Bulk CSV parser & validation tests
│   │   └── test_api_endpoints.py     # FastAPI route integration tests
│   ├── requirements.txt              # Backend Python dependencies
│   └── pytest.ini                    # Pytest configuration
│
├── frontend/                         # Next.js Frontend
│   ├── src/
│   │   ├── app/                      # App router
│   │   │   ├── [lang]/               # i18n route wrapper (ky | ru)
│   │   │   │   ├── layout.tsx        # Base root layout with i18n provider
│   │   │   │   ├── page.tsx          # Landing / portal redirect
│   │   │   │   ├── (auth)/           # Login, register, forgot-password
│   │   │   │   ├── (student)/        # Student OnePrep-style dashboard
│   │   │   │   │   ├── layout.tsx    # Left-hand persistent navigation sidebar
│   │   │   │   │   ├── dashboard/    # Planner, streak widget, target score card
│   │   │   │   │   ├── practice/     # Topic-by-topic question practice
│   │   │   │   │   ├── mock-tests/   # Mock test simulator & results breakdown
│   │   │   │   │   └── mistakes/     # Mistake notebook (туура эмес жооптор)
│   │   │   │   └── (instructor)/     # Instructor / Admin portal
│   │   │   │       ├── layout.tsx    # Admin layout & navigation
│   │   │   │       ├── questions/    # Question bank viewer, editor, filters
│   │   │   │       ├── bulk-upload/  # CSV uploader with preview & dry-run validation
│   │   │   │       └── analytics/    # Student performance metrics & cohort analysis
│   │   ├── components/               # Modular UI components
│   │   │   ├── ui/                   # Reusable atomic UI (buttons, modals, badges, inputs)
│   │   │   ├── common/               # Header, LanguageSwitcher, Sidebar, UserMenu
│   │   │   ├── math/                 # MathRenderer (KaTeX)
│   │   │   ├── exam/                 # QuestionCard, QuestionGrid, Timer, PassageViewer
│   │   │   └── charts/               # ScoreDistribution, TargetScoreTracker
│   │   ├── lib/                      # Utilities & client libraries
│   │   │   ├── firebase.ts           # Firebase client SDK initialization
│   │   │   ├── api.ts                # API client with auto-attached Firebase ID tokens
│   │   │   └── i18n/                 # Localization dictionaries and helper functions
│   │   │       ├── ky.json           # Kyrgyz UI translations
│   │   │       ├── ru.json           # Russian UI translations
│   │   │       └── context.tsx       # i18n context & hook
│   │   └── styles/
│   │       └── globals.css           # Tailwind base, utilities, font configuration
│   ├── public/                       # Static assets
│   ├── package.json
│   ├── tsconfig.json
│   └── tailwind.config.ts
│
└── firebase/                         # Firebase rules & indexes
    ├── firestore.rules               # Firestore security rules (role-based)
    └── firestore.indexes.json        # Composite indexes for high-volume questions
```

---

## 4. UI/UX & Styling Guidelines
- **Palette**: Clean, academic, distraction-free modern look (OnePrep / Canvas inspired):
  - Primary: Deep Indigo / Slate (`#1E293B`, `#3B82F6`, `#2563EB`)
  - Accent / Goal: Emerald Green for correct answers & streaks (`#10B981`)
  - Warning / Review: Amber / Orange for flagged questions (`#F59E0B`)
  - Danger: Rose for incorrect answers (`#EF4444`)
  - Background: Soft neutral grey (`#F8FAFC`) with pure white card surfaces (`#FFFFFF`)
- **Typography**: Clean sans-serif with full Cyrillic support (Inter / Roboto) ensuring complete rendering for Kyrgyz specific letters: `Ң, ң, Ө, ө, Ү, ү`.
- **Accessibility & Responsiveness**:
  - Full keyboard shortcuts in mock exam interface (1-4 or A-D for answer choice, N for next, P for previous, F for flag).
  - Clear high-contrast text ratios conforming to WCAG AA.
  - Responsive layout with collapsible sidebar on mobile/tablet viewports.

---

## 5. Verification & Testing Commands

### Backend Verification (Python / FastAPI)
- **Activate virtual environment**:
  ```bash
  cd backend && source venv/bin/activate
  ```
- **Run all unit & API tests**:
  ```bash
  pytest -v
  ```
- **Run specific test file**:
  ```bash
  pytest tests/test_scoring.py -v
  pytest tests/test_csv_ingestion.py -v
  ```
- **Run backend development server**:
  ```bash
  uvicorn app.main:app --reload --port 8000
  ```

### Frontend Verification (Next.js / TypeScript)
- **Typecheck & Lint**:
  ```bash
  cd frontend && npm run type-check && npm run lint
  ```
- **Run Frontend tests**:
  ```bash
  npm run test
  ```
- **Run development server**:
  ```bash
  npm run dev
  ```

---

## 6. Execution & Verification Rules for Autonomous Agents
1. **Test-First Verification Loop**: Prior to implementing any feature, write or verify the standard test block first. Run the corresponding test command to ensure no regressions occur.
2. **Strict Bilingual Discipline**: Every new UI element or data model field must support both `ky` (Kyrgyz) and `ru` (Russian). Hardcoded single-language strings in UI are strictly prohibited.
3. **Data Integrity for 12,000+ Questions**: Always use pagination, indexed queries, and chunked batch writes (max 500 ops per Firestore batch). Never fetch unbounded collections into frontend memory.

