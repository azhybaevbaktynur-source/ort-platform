# Phase 7b: exam templates I (data model, versions, general import format)

**Status**: **deployed 2026-10-26** (`main` 77c5b32; Render /health OK; Neon at `0010_phase7b_exam_templates`, verified: ORT exams keep `preset` with no template, 3 assignments, 1 submission, 299 question versions, 4 attempts; Vercel build started — confirm READY). Backup: `backup-2026-10-26-before-phase7b`. **Owner checkpoint: waiting.** Design: `docs/phases/EXAM_TEMPLATES_DESIGN.md` (approved) and `docs/phases/PHASE_7B_DESIGN.md`. Decisions: `docs/PRODUCT_DECISIONS.md` "Owner decisions 2026-10-25 (third round)", 7b-Q1, "Phase 7b implementation decisions" K1–K3.

## What changed

| Area | Change |
|---|---|
| Exam templates | A reusable, versioned exam structure: sections in order (name, question count min/max, time limit, allowed question types, passage rules), navigation (free / forward-only), display mode, grading scheme version, result view, parameters, lock scope. Owners: the **platform** (visible to every organization, structure only, no questions), an **organization** (visible inside it), a **teacher** (own). Drafts are edited in a plain form; **publish** creates an immutable version; archive, lock / unlock (by the template's owner), promote a teacher template to the organization; every action audited. |
| Create from template | Quiz assignments and assessments can be created from a published template version; the structure is copied in one transaction together with the quiz assignment. A locked template's structure cannot be changed in the builder (greyed out with a note; API 409). Running exams keep their version; "upgrade to latest" only for drafts without attempts. |
| Save as template | "Save as template" in the builder turns an existing general exam into a draft template (teacher scope). Refused for ORT exams (7b-Q1) and for exams built from a locked template (K1). |
| General import format | One CSV / `lms-bundle` zip format for all 7 question types; a template version derives its accepted sections, types, columns and counts, offers a CSV header with one example row per section, validates uploads against it and attaches the questions to the matching sections. Hardened: column caps (K2), formula-safe downloads. |
| Block catalog | `GET /exam-templates/blocks` (question types, scheme versions, result views, passage displays, display modes, navigation, importer profiles); the frontend map is contract-tested against it. |
| Migration | `0010_phase7b_exam_templates` (templates, immutable versions, assessment columns `exam_template_version_id`, `display_mode`, `passage_display`, `result_view`, `structure_locked`, CHECK that `preset` and a template are exclusive, `min_items`). |

## ORT review

**Function unchanged** — ORT stays on its `preset` path and never uses a template:
- ORT importer files (`ort_csv.py`, `bundle.py`, `rules.py`) byte-for-byte unchanged (diff checked); `test_ort_import_golden.py` green.
- ORT tests, `test_ort_gradebook_golden.py`, ORT browser suite (both specs twice, zero screenshot differences, no baseline changed).
- **ORT expressibility dry-run test** (owner B9): a template spec built from the ORT constants instantiates the same section rows as `create_assessment(preset="ort_main")` and every subject key — without switching ORT. This is the evidence for the later "move ORT onto the constructor?" decision.
- New snapshot keys are additive: the engine reads the same values with or without them for ORT exams (test).

**Visible in ORT courses**: nothing new; ORT exams show no "Save as template".

## How to verify

```bash
# SQLite ~3041 passed, 31 skipped; PG ~3099 passed; alembic head 0010_phase7b_exam_templates, `alembic check` clean.
```
Rehearsal on the production copy (0007 → 0010 + lifespan): 0008 and 0009 checks pass; the ORT exams keep `preset`, no template linked. Walkthrough `docs/phases/PHASE_7_screens/7b/WALKTHROUGH.md` (32/32). UX gate `docs/phases/PHASE_7_screens/7b/`. Security review: one high (CSV column DoS) and lower findings, all fixed with tests.

## Deferred

- The visual constructor, scrolling display mode and result-view choice in the player → **Phase 8b**.
- General result page section titles, translated spec validation messages, transliterated CSV file names (being fixed in the UX round) — see the UX section below once done.

## Owner items

- Checkpoint review (this phase).
- Neon: six obsolete pre-LMS backup branches deleted with the owner's OK (2026-10-26); 4 backups + production remain.
