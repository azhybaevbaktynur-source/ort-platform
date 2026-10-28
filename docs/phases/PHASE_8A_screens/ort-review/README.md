# Phase 8a ORT review

ORT parity (S5c, macOS, system Chrome): `ort.spec.ts`, `ort-visual.spec.ts` and `quiz-editor.spec.ts` ran twice
against the 8a build, 11 passed both times, no screen over the 0.5 % threshold. `docs/phases/ORT_BASELINE/` was not
changed.

To see every pixel (also below the threshold), the 47 ORT screens were recorded into a scratch folder
(`ORT_BASELINE_DIR=<tmp> UPDATE_BASELINES=1`) twice, once with the 8a frontend and once with the `main` frontend
(Phase 7c, same 8a backend), and compared with pixelmatch (threshold 0.1, anti-aliasing ignored).

## Student screens

8a vs `main`: **zero diffs** on all 33 student screens, except `result-desktop-ru` (16 px): the width of the magenta
mask over the "submitted" date, which depends on the time of the run.

8a vs the baseline (all below 0.5 %, all already on `main`, none from 8a):
- `result-*`: the date mask width (as above).
- `review-*-ru`: "1 из 1 балла" instead of "1 из 1 баллов" (plural forms, Phase 6b S12).
- `section-end-*-ky`: «...» quotes instead of "..." in the Kyrgyz section-end title (Phase 7b UX fixes).

## Teacher screens (intended, owner Q5 default)

8a vs `main`: the only difference is the course tab bar. Staff in the ORT course now also see **Модули, Страницы,
Файлы, Объявления** (main: Главная, Участники, Задания, Тесты, Оценки, Банк вопросов, Настройки).

8a vs the baseline additionally shows changes already on `main`: the "Шаблоны тестов" link in the teaching row
(Phase 7b), the "Тесты" tab (Phase 7c) and a few pixels of spacing in the builder's question rows (Phase 7b/7c).
`teacher-publish-*` (element only) is identical.

Per screen: `-before` = `ORT_BASELINE`, `-after` = 8a, `-diff` = after vs before, `-diff-vs-main` = 8a vs `main`
(only the tab bar).

| Screen | Diff vs baseline | Diff vs main |
|---|---|---|
| `teacher-attempts-desktop-ru` | 0.298 % | 0.232 % |
| `teacher-attempts-phone-ru` | 0.355 % | 0.196 % |
| `teacher-bank-desktop-ru` | 0.232 % | 0.225 % |
| `teacher-bank-phone-ru` | 0.060 % | 0.119 % |
| `teacher-builder-desktop-ru` | 0.493 % | 0.217 % |
| `teacher-builder-phone-ru` | 0.355 % | 0.188 % |
| `teacher-import-desktop-ru` | 0.233 % | 0.221 % |
| `teacher-import-phone-ru` | 0.056 % | 0.081 % |
| `teacher-passage-desktop-ru` | 0.232 % | 0.225 % |
| `teacher-passage-phone-ru` | 0.060 % | 0.119 % |
| `teacher-question-comparison-desktop-ru` | 0.110 % | 0.105 % |
| `teacher-question-comparison-phone-ru` | 0.021 % | 0.033 % |

Note: `teacher-builder-desktop-ru` is at 0.493 % against the baseline, just under the 0.5 % gate. One more tab or
header change will fail it; the teacher baselines should be re-recorded after the owner accepts the 8a tabs.

## Other images (modules.spec.ts test 2)

- `ort-student-course-home-before-*`: ORT student course home before any structure (no new tabs).
- `ort-teacher-course-home-after-*`: ORT staff course home with the new tabs.
- `ort-student-course-home-with-structure-*`: student home after a published module and file (Modules and Files tabs,
  home unchanged).
- `ort-student-modules-*`: ORT module with the exam locked by date; the exam still starts (design 13).
