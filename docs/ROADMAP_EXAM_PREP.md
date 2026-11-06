# Exam-prep roadmap (owner direction 2026-11-06)

Strategy research is kept outside the public repo (`docs/strategy/`, git-excluded). This file is the product plan only.

## Direction (owner)
- An exam-prep platform for **individual students** first. Tutors and schools come later, once there are enough students.
- **ORT first**, then olympiads and the national test (owner: "NCT"), on the same exam-prep page.
- **One ORT course per language**, run by the platform. No family of similar ORT courses.
- **Free and paid:** some exams free; a payment unlocks all exams.
- **Explanations** come from the CSV the owner prepares (already imported and shown in the result review). No AI spending per student for them.
- **AI chat** later, as cheap or free as possible (decision D5).
- Teacher-side tools for ORT are not needed now.

## Slices, in order
| # | Slice | What the owner sees | Needs |
|---|---|---|---|
| S1 | **Protect control** (admin review part A) | Two-step login for platform admins with recovery codes; "end all sessions"; `make_admin.py` refuses to remove the last admin and no longer makes the person a teacher; a real health check on the admin overview | D1 (Neon room) to deploy |
| S2 | **Exam-prep home and ORT page** | Platform courses on every student's home ("От платформы") with one-tap join; the ORT course opens on an exam-prep page: exam date countdown, the student's target, last scaled score and history, five section bars, one "Next" card, the test library with a source filter. The exam player and result page don't change | D1 |
| S3 | **Free and paid exams** | Admin marks exams free or paid; a student without access sees a lock and "unlock all exams"; access comes from an **activation code** (admin creates batches with a duration, sells them by QR transfer) or an admin grant. Automatic online payment comes later with a provider contract (D3) | D1, D2–D4 |
| S4 | **Person page and payments control** (admin review part B, plus payments) | Find a student; their access, codes used, email confirmed, last login, attempts (status only); change email (A9), send a password reset, end sessions; list of codes and how many were used | D1 |
| S5 | **Installable app** | "Install" on Android and iPhone home screens, the website's own icon, offline reading of past results. Then an Android shell on Google Play (needs a Google Play account: owner money) | D6 |
| S6 | **AI chat** | A hint chat in practice and result review only, never inside a timed exam, with a monthly limit | D5 |
| Later | Exam day panel and banner (part D), harmful content tools (part C), tutors and schools with groups and join QR (part E), olympiads, national test | | |

**Content is the biggest gap, and it's yours:** on production, ORT (Russian) has one published test and ORT (Kyrgyz) has none. About 55% of test-takers sit the test in Kyrgyz. The free/paid model needs a library of full tests in both languages, imported with the CSV you already use.

## Decisions for the owner
| # | Question | Default until you answer |
|---|---|---|
| D1 | Delete the four oldest Neon backups (before phases 7b, 7c, 8a, 8b; all later ones stay) so new database changes can get their own backup? | Waiting: nothing reaches production without it |
| D2 | What is free? | The first full test in each language, plus the result review; the admin can switch any test at any time |
| D3 | First payment method | Activation codes you sell by QR transfer; automatic payment later with a provider contract |
| D4 | Length of paid access | Set per code batch; suggested "until 31 May" for the season |
| D5 | AI chat provider | Not built before S1–S4. Free tiers (e.g. Google's free Gemini) may use what students type to train their models, which the 2026 Digital Code doesn't allow for children's data without consent, and they allow few requests per minute. A paid low-cost model with a hard monthly cap is the safe option |
| D6 | Android app in Google Play | After S5's installable web app shows use |
| D7 | The national test: its exact name and format, for later | — |
