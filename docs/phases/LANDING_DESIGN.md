# Landing page: directions and recommendation (fix round 2026-11-12, step 3c)

**Status**: design only (architect on Fable, 2026-11-12). Base: `lms` 15fffb8. Owner brief: `FIX_ROUND_2026-11-12.md`
step 3c. Direction: `ROADMAP_EXAM_PREP.md` (individual students, ORT first, then olympiads and НЦТ; free and paid;
tutors and schools later). The page leads into the one student interface of step 3a (`STUDENT_IA_DESIGN.md`).

Before (production, anonymous, 2026-11-12): `LANDING_screens/before/landing-ru-1440.jpg`, `landing-ru-375.jpg`,
`landing-ky-375-fold.jpg`, `for-teachers-ru-1440.jpg`. (The blank teacher card and the blank circle in the 1440 shot
are a capture artefact: `fullPage` does not scroll, so lazy images below the fold never loaded; the files are served.)

**What is wrong today** (`frontend/src/app/[lang]/page.tsx`): the page sells an LMS ("Учитесь и преподавайте в одном
месте") to two audiences with equal weight; the first phone screen is a role choice, not an action; nothing says
"ORT" until the subline; nothing says "free"; the proof is three generic feature cards; the screenshots are the old
staff and dashboard screens (one of them a teacher page); no `<title>` per page, no description per language, no
`hreflang`, no OpenGraph image, no sitemap. The build itself is fine: the HTML is prerendered with the text in it
(verified on `/ru`), 34 kB HTML, mascot WebP 23–30 kB, screenshots 17–38 kB, no heavy library.

## 1. Audience and the one job of the page

| Who lands here | How | What they need in 5 seconds |
|---|---|---|
| A student in grade 10–11 (15–17), from a friend's link, a Telegram/Instagram post, or a search "ОРТ тест онлайн" / "ЖРТ тест" | a phone, often Android low-end, slow 4G, data-metered | "This is ORT practice. The first full test is free. Start." |
| A parent who pays | a phone, from the student's link, or a search in Russian | "Real ORT format, honest scores, made here, what it costs, safe for my child." |
| A teacher or a tutor (later) | desktop | "There is a place for me too." One link is enough |

Languages: ky and ru first (about 55 % of ORT candidates sit the test in Kyrgyz), en exists and must stay complete.

**The one job**: a student creates an account and starts the first free full ORT test in the language of the page.
Every section either moves toward that or is cut.

**Must be true in the first screen (375 × 812, no scroll):** the word ОРТ / ЖРТ in the headline; the word бесплатно /
акысыз; one primary button; the mascot (small); no role choice, no carousel, no second button competing; the language
switcher and "Войти" in the top bar. Desktop adds one real phone screenshot beside the text.

**Honest proof we can show today** (and nothing else): the test follows the real ORT: five sections in the official
order, section timers, forward-only sections; the score is the real scaled score with percentile and the golden
certificate threshold (the scoring tables are data, `app/lms/ort/`); every question has an explanation (from the
owner's CSV, shown in the result review); Kyrgyz and Russian; works on a phone and installs as an app (S5, PWA);
results stay after Pro ends; no advertising. **Not shown until true**: number of students, number of tests (the ru
course has one published test, ky none), success rates, reviews, "best in Kyrgyzstan", partner schools. Real quotes
come later with written permission (first name, city, age ≥ 16 or a parent's consent).

Form of address: "вы" / "сиз" as in the rest of the student UI (glossary rule in `UX_GUIDELINES.md` §5); the ORT
is "ОРТ" (ru) and "ЖРТ" (ky). The platform name stays `common.appName` ("Платформа") until the owner names it.

## 2. Directions

Common to all three: `PublicShell` (header: brand, language, Войти, Регистрация; footer as today plus a Pro link),
the existing six mascot poses only (`hello`, `reading`, `thinking`, `celebrating`, `working`, `encouraging`; concept
PNG/WebP now, an illustrator's SVG per pose drops into `public/mascot/` with no code change), never the mascot inside
a screenshot of the player, at most one mascot per phone screen, no animation. Screenshots are phone-shaped (375 px
CSS width in a thin device outline, 2× WebP ≤ 40 kB): the audience is on phones, phone shots are light and readable
in a text column, and one component serves both widths. They are recorded by `frontend/e2e/landing-screens.spec.ts`
from `seed_landing` demo data (fictional names) on a scratch backend, in all three languages, never from real
student data, and re-recorded whenever a shown screen changes.

### Direction A: "First test free" (conversion page, exam-centred)

One line: *say ORT, say free, one button; prove the format is real; show what happens after the test.*

Sections in order: 1 Hero · 2 How it works (3 steps) · 3 Screens (overview with countdown and target, player,
result with scaled score, analytics) · 4 What is real (honest facts strip) · 5 Free vs Pro · 6 Short FAQ · 7 One
line for teachers and schools · 8 Final CTA · 9 Footer.

Hero copy:
- ru H1 «Подготовка к ОРТ онлайн. Первый пробный тест — бесплатно.» Subline «Полные пробные тесты в формате ОРТ:
  таймер по разделам, баллы как на настоящем экзамене и разбор каждого вопроса. На кыргызском и русском.»
- ky H1 «ЖРТга онлайн даярдык. Биринчи сынамык тест — акысыз.» Subline «ЖРТ форматындагы толук сынамык тесттер:
  бөлүм боюнча таймер, чыныгы экзамендегидей баллдар жана ар бир суроонун чечилиши. Кыргызча жана орусча.»
- Primary CTA «Начать бесплатный тест» / «Акысыз тестти баштоо» → `/{lang}/register` (signed in: «Продолжить» →
  `/{lang}/home`). Under it one quiet line: «Без карты · на телефоне · 2 минуты на регистрацию» /
  «Картасыз · телефондо · катталуу 2 мүнөт». No second button; "Войти" is in the header.
- Optional chip when the exam date is set (§4, v2): «До ОРТ: 123 дня» / «ЖРТга чейин: 123 күн».

Mascot: hero `hello` (eager, beside the text; on a phone 96 px high at the right of the H1); step 1 `thinking`, step
2 `reading`, step 3 `celebrating`; final CTA `encouraging`. Four poses, nowhere else.

Screens (from 3a): ORT course Overview (countdown tiles, target 200, five section bars; `STUDENT_IA_DESIGN.md` §4.4),
the player on a `math_1` comparison question (unchanged player), the result page (scaled score, percentile, section
breakdown), Аналитика (weak topics). Captions are one sentence each.

Proof: section 4 is a strip of four facts with an icon and one line: «5 разделов в официальном порядке и таймеры как
на экзамене», «Баллы по шкале ОРТ, процентиль и порог золотого сертификата», «Разбор каждого вопроса», «На кыргызском
и русском, на телефоне». No numbers.

Free vs Pro: two columns from the existing `access.pro.compare.*` keys (free: free tests, analytics by topic, results
and reviews, practice; Pro: all paid tests, practice in platform courses, Pro lessons, results stay). Price line hidden
while `pro_prices` is unset; one sentence «Цены появятся к началу сезона; оплата кодом или переводом» and a link
«Подробнее о Pro» → `/{lang}/pro` (sign-in first; fine). No fake "from 990 сом".

Teachers/schools: one tinted line near the bottom: «Преподаватель или школа? Создавайте курсы и группы.» → link
`/for-teachers`. No mascot, no screenshot. Footer: brand + tagline, Платформа (О платформе, Pro, Преподавателям),
Поддержка (Помощь, Контакты, Конфиденциальность), Язык.

```
1440                                                                  375
┌──────────────────────────────────────────────────────────────┐  ┌───────────────────────┐
│ ◉ Платформа                       RU ▾   Войти  [Регистрация]│  │ ◉        KY ▾  Кирүү  │
├──────────────────────────────────────────────────────────────┤  ├───────────────────────┤
│  Подготовка к ОРТ онлайн.            ┌ phone ┐    🐆 hello   │  │ ЖРТга онлайн      🐆  │
│  Первый пробный тест — бесплатно.    │ 123 дн│               │  │ даярдык. Биринчи      │
│  Полные пробные тесты … ky и ru.     │ цель  │               │  │ сынамык тест —        │
│  [ Начать бесплатный тест → ]        │ ▮▮▮▯▯ │               │  │ акысыз.               │
│  Без карты · на телефоне · 2 минуты  └───────┘               │  │ ЖРТ форматындагы …    │
├──────────────────────────────────────────────────────────────┤  │ [Акысыз тестти баштоо]│
│  Как это работает                                            │  │ Картасыз · телефондо  │
│  🐆 1 Пройдите тест   🐆 2 Увидьте балл   🐆 3 Подтяните    │  ├───────────────────────┤ fold
│    как на экзамене      и слабые разделы    темы, повторите  │  │ Как это работает      │
├──────────────────────────────────────────────────────────────┤  │ 🐆 1 … / 2 … / 3 …    │
│  [overview] [player] [result] [analytics]  (4 phone shots)   │  │ [phone shot] caption  │
│   caption    caption   caption   caption                     │  │ [phone shot] caption  │
├──────────────────────────────────────────────────────────────┤  │ … (4, one column)     │
│  Что здесь настоящее:  ✓ 5 разделов ✓ шкала ОРТ ✓ разбор ✓ ky/ru│  │ Что здесь настоящее   │
├──────────────────────────────────────────────────────────────┤  │ ✓ … ✓ … ✓ … ✓ …       │
│  Бесплатно            │  Pro (gold chip)                     │  │ Бесплатно / Pro       │
│  ✓ … ✓ … ✓ …          │  ✓ всё из Free ✓ все тесты ✓ уроки   │  │ (stacked cards)       │
│  Цены появятся к сезону · Подробнее о Pro →                  │  │ Подробнее о Pro →     │
├──────────────────────────────────────────────────────────────┤  │ Вопросы (5 ▸)         │
│  Вопросы: ▸ Это настоящий формат? ▸ Сколько стоит? ▸ … (5)   │  │ Преподаватель? →      │
├──────────────────────────────────────────────────────────────┤  │ 🐆 Готовы? [Начать]   │
│  Преподаватель или школа? Создавайте курсы → /for-teachers   │  │ footer                │
├──────────────────────────────────────────────────────────────┤  └───────────────────────┘
│  🐆 encouraging   Готовы к первому тесту?   [Начать бесплатно]│
├──────────────────────────────────────────────────────────────┤
│  footer: brand · Платформа · Поддержка · Язык                 │
└──────────────────────────────────────────────────────────────┘
```

### Direction B: "The road to your score" (season journey, parent-friendly)

One line: *tell the student's season as five steps with the mascot as guide, from target to exam day.*

Sections: 1 Hero (phone mockup with countdown and target score, `hello`) · 2 The road: Цель → Диагностика →
Слабые темы → Полные пробники → День экзамена, each step a card with a pose and one screen (home with target,
analytics, saved/mistakes, test library, result) · 3 For parents («Что видит родитель»: results, honest scores,
no ads, what Pro is; the observer/parent link of Phase 11) · 4 Free vs Pro as a "season pass" · 5 FAQ · 6 Teachers
line · 7 Final CTA · 8 Footer.

Hero copy: ru H1 «Ваш путь к высокому баллу ОРТ» subline «Поставьте цель, пройдите диагностику, подтяните слабые
темы и приходите на экзамен готовыми. Первый тест бесплатно.» ky H1 «ЖРТда жогорку баллга жолуңуз» subline «Максат
коюңуз, диагностика өтүңүз, алсыз темаларды бекемдеңиз. Биринчи тест акысыз.» CTA as in A.

Mascot: five poses along the road (`thinking`, `reading`, `working`, `celebrating`, `encouraging`) plus `hello` in
the hero: six on one page, which is the maximum the sheet allows and already feels like a cartoon strip.

Screens: home with countdown and target, analytics weak topics, saved mistakes, test library, result. Five shots.

Proof: the same honest facts, placed inside the steps. Parents' section adds the privacy policy link and «Без рекламы».

```
1440                                                              375
┌ ◉ Платформа                      RU ▾  Войти [Регистрация] ┐   ┌ ◉     KY ▾  Кирүү ┐
│ Ваш путь к высокому баллу ОРТ          ┌ phone: 123 дн ┐  🐆│   │ 🐆 Ваш путь к …    │
│ Поставьте цель … Первый тест бесплатно │ цель 200 ▮▮▯  │    │   │ subline            │
│ [Начать бесплатный тест →]             └───────────────┘    │   │ [Начать …]         │
├─────────────────────────────────────────────────────────────┤   ├────────────────────┤ fold
│ 1 Цель 🐆 ─ 2 Диагностика 🐆 ─ 3 Слабые темы 🐆 ─ 4 … ─ 5 … │   │ 1 Цель 🐆 [shot]   │
│ [shot]        [shot]            [shot]          [shot][shot] │   │ 2 Диагностика …    │
├─────────────────────────────────────────────────────────────┤   │ 3 … 4 … 5 …        │
│ Родителям: честные баллы · без рекламы · что такое Pro       │   │ Родителям          │
├─────────────────────────────────────────────────────────────┤   │ Free / Pro         │
│ Free │ Pro «абонемент на сезон»     Вопросы (5)             │   │ Вопросы            │
│ Преподавателям →   🐆 Готовы? [Начать]   footer             │   │ 🐆 Готовы? footer  │
└─────────────────────────────────────────────────────────────┘   └────────────────────┘
```

### Direction C: "The exam catalog" (platform page that grows with olympiads and НЦТ)

One line: *the landing is the public catalog: one card per exam, ORT ru and ORT ky today, more later.*

Sections: 1 Hero (short: «Готовьтесь к экзаменам Кыргызстана онлайн. Сейчас ОРТ, дальше олимпиады и тесты НЦТ.»,
`hello`) · 2 Exam cards (ОРТ на кыргызском, ОРТ на русском: free tests count, Начать; greyed «Скоро» cards for
olympiads and НЦТ) · 3 Feature grid (timer, scaled score, explanations, analytics, saved, app) · 4 Free vs Pro ·
5 Teachers and schools (a real band, with the staff course screenshot) · 6 Final CTA · 7 Footer.

Hero copy: ru «Экзамены Кыргызстана — подготовка онлайн» ky «Кыргызстандын экзамендерине онлайн даярдык»; CTA
«Выбрать экзамен» (anchor to the cards), each card has its own «Начать бесплатно».

Mascot: hero `hello`, one `working` in the teachers band. Screens: one per card (the course Overview) plus the
staff course page in the teachers band. Proof: counts per card, which today read "1 тест" and "0 тестов": honest,
and bad.

```
1440                                                             375
┌ ◉ Платформа                     RU ▾  Войти [Регистрация] ┐   ┌ ◉     RU ▾  Войти ┐
│ Экзамены Кыргызстана — подготовка онлайн            🐆    │   │ Экзамены … 🐆     │
│ Сейчас ОРТ, дальше олимпиады и тесты НЦТ. [Выбрать экзамен]│   │ [Выбрать экзамен] │
├────────────────────────────────────────────────────────────┤   ├───────────────────┤ fold
│ [ОРТ кырг · 1 бесплатный тест · Начать] [ОРТ рус · …]      │   │ [ОРТ кырг]        │
│ [Олимпиады · скоро]  [НЦТ · скоро]                          │   │ [ОРТ рус]         │
│ feature grid 2×3 · Free/Pro · Преподавателям [shot] 🐆      │   │ [скоро][скоро]    │
│ Готовы? [Создать аккаунт] · footer                          │   │ grid · Pro · …    │
└────────────────────────────────────────────────────────────┘   └───────────────────┘
```

## 3. Recommendation: Direction A, with B's "road" folded into its three steps

Reasons:
1. **It matches the one job and the phone fold.** A's first screen is headline + free + one button; B spends the
   fold on a story, C on a choice. UX rule: one main action per screen.
2. **It is honest with today's content.** C shows "0 тестов" on the Kyrgyz card until the owner imports tests; B
   promises a five-step season the product only partly has (no planner, no exam-day panel yet). A shows four real
   screens that exist after 3a and four facts that are true now.
3. **It survives the roadmap.** Olympiads and НЦТ later become a second line in the hero and a card row above the
   FAQ; the catalog is already `/courses/catalog`, no need to make the landing one.
4. **Mascot discipline.** Four poses with a role each (greet, think, read, celebrate, encourage at the end) reads as
   one character, not a sticker pack (B uses all six; the owner wants "one natural product").
5. **Parents are served without a section**: the facts strip, the Free/Pro block and the FAQ answer their questions
   («Это настоящий формат?», «Сколько стоит?», «Данные ребёнка?» with the privacy link); B's parents block can be
   added later as one FAQ group if the owner wants it.

Take from B: the three steps are phrased as the student's road (test → score and weak sections → practise and
repeat), and the ORT course Overview with the countdown is the hero screenshot, so the "season" is visible without
a separate section. Take from C: nothing now; the "Скоро: олимпиады, НЦТ" line is one i18n string in the hero
subline when the owner wants to announce it (not before a date is known).

## 4. Technical notes

**Rendering.** Keep the page static: `[lang]/page.tsx` becomes a server component that exports `generateMetadata`
and renders `components/landing/LandingPage.tsx` (client, as today: `useAuth` for the signed-in variant, `useTranslation`).
`generateStaticParams` already prerenders ky/ru/en; the HTML contains the copy (verified), so no ISR. Live numbers
(countdown, test counts) are fetched client-side after paint from one public endpoint (v2, §5 S4) and are absent
without harm; the page is never server-rendered per request.

**Performance budget** (Lighthouse mobile, slow 4G, Moto G class; recorded in the slice result): LCP ≤ 2.5 s, CLS
≤ 0.05, TBT ≤ 200 ms, score ≥ 90. Means: the H1 is the LCP element (system font stack on public pages as today; if
Inter is ever applied here, `display: swap` only); hero mascot `hello.webp` ≤ 30 kB with `fetchpriority="high"`, width
and height set (`Mascot eager`), everything else `loading="lazy"`; screenshots WebP, 750 px wide (2× of 375), ≤ 40 kB
each, four of them, with explicit dimensions; no AVIF pipeline for now (Pillow in `landing_webp.py` stays); first view
≤ 250 kB transfer, whole page ≤ 500 kB; no new dependency (no carousel, slider, animation or chart library; FAQ is
`<details>`; the device outline is CSS); transitions only, honouring `prefers-reduced-motion`; no video (a 10-second
player clip is tempting; it is 1–2 MB on a metered phone: no). The service worker must not precache the screenshots.

**SEO.** Per language in i18n (`landing.seo.*`): `<title>` «Подготовка к ОРТ онлайн: бесплатный пробный тест | Платформа»
/ «ЖРТга онлайн даярдык: акысыз сынамык тест | Платформа» / en; `description` ≤ 155 chars; `alternates.canonical`
`/{lang}` and `alternates.languages` `{ ru, ky, en, "x-default": "/" }` (`/` redirects to `/ky`, `app/page.tsx`);
`openGraph` `{ type: "website", locale: ru_RU | ky_KG | en_US, images: ["/og/landing-{lang}.png"] }` and
`twitter.card = summary_large_image`. OG images: 1200 × 630 PNG ≤ 120 kB per language, generated once by a Playwright
script from an HTML template (headline, mascot, brand) and committed under `public/og/`; regenerated when the name or
headline changes. Add `app/sitemap.ts` (public routes × 3 languages: `/`, `about`, `help`, `contacts`, `for-teachers`,
`for-teachers/apply`, `policies/privacy`) and `app/robots.ts` (allow public routes, disallow `/*/courses`, `/*/admin`,
`/*/org`, `/*/home`, `/*/pro`, auth routes). JSON-LD: `Organization` + `WebSite` only; never `AggregateRating`,
`Review` or `Course` with invented data. Headline text is real text, never in an image.

**Analytics.** None by default: no GA, no Yandex.Metrica, no pixel (children's data, the 2026 Digital Code, and the
CSP stays strict). Sign-ups per day are already visible in the admin overview. If the owner wants page-view counts,
Vercel Web Analytics is cookie-less and first-party, but it is a spend question (owner decision D5).

**Accessibility.** One `<h1>`; sections are `<section aria-labelledby>`; the skip link exists in `PublicShell`;
mascot `alt=""`; each screenshot has a one-sentence `alt` (the caption is visible text, the alt names the screen);
contrast ≥ 4.5:1 (gold chip text `#78350f` on `#fef3c7` passes); every button ≥ 44 px; focus visible; FAQ
`<details>/<summary>` is keyboard-native; language switcher keeps the path; the `lang` attribute is per page; ky
letters ң ө ү exist in the system stack and in Inter (`cyrillic-ext`). No autoplay, no parallax.

**i18n keys** (core dictionary; `landing` is not a staff prefix): keep `landing.badge`, `landing.myCourses`,
`landing.footer.*`, `landing.forTeachers.*`, `landing.about.*`, `landing.help.*`, `landing.contacts.*`. Replace
`landing.hero.*`, `landing.why.*`, `landing.students.*`, `landing.exam.*`, `landing.teachers.*`, `landing.final.*`,
`landing.shots.*` with: `landing.hero` {title, subtitle, cta, ctaHint, continue, countdown (with `{days}` and plural
forms as `access.pro.status.daysLeft_*`)}; `landing.steps` {title, s1..s3.title/text}; `landing.screens` {title,
overview/player/result/analytics .caption/.alt}; `landing.facts` {title, f1..f4}; `landing.pro` {title, freeTitle,
proTitle, note, link} reusing `access.pro.compare.*` for the rows; `landing.faq` {title, q1..q5, a1..a5};
`landing.teachersLine` {text, link}; `landing.final` {title, body, button, titleSignedIn, bodySignedIn};
`landing.seo` {title, description, ogAlt}. About 55 keys × 3; `scripts/check_i18n_parity.py` must pass; the
`landing.spec.ts` e2e is updated to the new structure (links per language, signed-in variant, 375 and 1440).

## 5. Build slices (after the owner's OK; 3a is built first, so the screens exist)

| # | Slice | Model | Owns | Done when |
|---|---|---|---|---|
| S1 | Structure, copy and styling | Sonnet | `components/landing/LandingPage.tsx` (new, from today's `page.tsx` sections), `landing/Facts.tsx`, `landing/Faq.tsx`, `landing/PhoneShot.tsx`, `PublicFooter.tsx` (Pro link), i18n keys in en/ky/ru | ru/ky/en copy as in §2 A (the orchestrator reviews ky), parity passes, `tsc`, `landing.spec.ts` green, screenshots at 375/1440/1920 ru checked by the orchestrator; placeholders for the four shots |
| S2 | Record the four screens | Opus | `e2e/landing-screens.spec.ts`, `e2e/seed_backend.py` (`seed_landing`: an ORT course with a target, one finished attempt, analytics data; fictional names), `landing_webp.py` (750 px, phone viewport) | 4 shots × 3 languages committed under `public/landing/`, each ≤ 40 kB; the spec is the only way they are made |
| S3 | Metadata, OG, sitemap, robots | Opus (small) | `[lang]/page.tsx` server/client split, `app/sitemap.ts`, `app/robots.ts`, `scripts/og_images.mjs`, `public/og/` | `curl /ru` shows title, description, hreflang ×4, og:image; Lighthouse mobile ≥ 90 recorded in the slice result |
| S4 (v2, optional) | Live numbers | Opus | backend `GET /public/landing` (no auth, cached 10 min, rate-limited; `{exam_date, tests: {ru, ky}}`, `route_inventory` entry, tests) and the hero chip | shown only when the exam date is set and a language has ≥ 5 published tests |

S1–S3 are one deploy each; S4 waits for content. Total: 3 slices (+1 optional).

**What the owner must provide**: the platform name (the title, OG image and footer say «Платформа» until then; S3
can ship with the placeholder and be regenerated); the ORT exam date per course (admin setting, already exists) and
Pro prices and season end (Pro settings) when known; the public contact address (`landing.contacts.body`, still a
placeholder); optionally the illustrator's final mascot SVGs; later real quotes with permission. No photos are
needed: the page uses the mascot and real screens, not stock people.

## 6. Owner decisions

| # | Decision | Recommendation |
|---|---|---|
| D1 | Direction A, B or C | **A**, with B's road as the three steps (§3) |
| D2 | What the primary button does | **`/register`**, and after sign-up the student lands on `/home` with the ORT course of the UI language already joined (auto-join the platform ORT course of the sign-up language: one line in the sign-up flow, belongs to 3a/3b build). Without auto-join the promise "start a free test" takes four taps |
| D3 | Live numbers on the landing (countdown, test counts) | **Not in v1.** Add S4 when both languages have ≥ 5 published tests and the exam date is set; counts under 5 look like weakness |
| D4 | Pro on the landing before prices are set | **Show the Free/Pro comparison without prices** and the sentence «Цены появятся к сезону»; hiding Pro would surprise students at the first locked test |
| D5 | Page-view analytics | **None.** Sign-ups are counted in the admin overview; revisit with a custom domain if the owner wants funnel numbers (Vercel Web Analytics, cookie-less; a spend question) |
| D6 | Teachers in the hero | **No role entries.** One line before the final CTA plus the footer link; `/for-teachers` stays as it is |
| D7 | "Сделано в Кыргызстане" line in the footer | **Yes** (true, and parents read it); wording «Сделано в Кыргызстане» / «Кыргызстанда жасалган» |
| D8 | FAQ questions (five) | «Это настоящий формат ОРТ?», «Что бесплатно, что в Pro?», «Можно на кыргызском?», «Работает на телефоне?», «Как хранятся данные ребёнка?» (links the privacy policy) |
