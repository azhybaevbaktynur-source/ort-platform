import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { expect, test, type Locator, type Page } from "@playwright/test";
import { api, E2E_DIR, goToReviewPage, seed, settle, signIn, tr, VIEWPORTS, type SeedUser } from "./helpers";
import { gradientPng } from "./png";

/**
 * Lesson course requests C1–C6 (docs/phases/LESSON_COURSE_REQUESTS.md), integration walk in ru. An approved teacher
 * builds a general course (no exam) through the API: module 1 = a page with every lesson component (two screens split
 * by `---`, Главное / Приём / Ловушка / Вспомни callouts, «Проверь себя» with a hidden answer, «Почему так?», a «Разбор»
 * with steps and an answer, an image with a caption, a table, inline and display math) and a lesson quiz
 * (`placement = "lesson"`, two single-choice questions with three options); module 2 = one page. A second course has a
 * default (tests) quiz. The student: the course tabs are Обзор · Уроки · Аналитика · Повторение (no Тесты), the home
 * to-do never lists the lesson quiz, the self-check opens with Enter («Скрыть ответ»), "next" is the quiz card inside
 * the lesson (no lobby), «Начать» opens the player with Cyrillic letters А Б В, the result page belongs to Уроки and
 * «Следующий урок» opens module 2; the syllabus marks the quiz done. The default quiz of the other course is in Тесты.
 *
 * LC_SHOTS=1: lesson page, open self-check, quiz card, result page at 375 / 1440 / 1920 px (ru) as WebP (≤ 300 KB,
 * e2e/shots_webp.py, system python3 with Pillow) into docs/phases/LESSON_COURSE_screens/. Not baselines.
 */

const L = "ru" as const;
const t = (key: string, vars: Record<string, string | number> = {}) => tr(L, key, vars);
const SHOTS = process.env.LC_SHOTS === "1";
const PNG_DIR = path.join(E2E_DIR, "lesson-course-shots");
const OUT_DIR = path.resolve(__dirname, "../../docs/phases/LESSON_COURSE_screens");
const WIDTHS = [375, 1440, 1920] as const;

const COURSE = "Дроби: уроки E2E";
const OTHER = "Тесты по дробям E2E";
const M1 = "Сложение дробей";
const M2 = "Вычитание дробей";
const P1 = "Дроби с одинаковым знаменателем";
const P2 = "Вычитание: основы";
const P2_TEXT = "Вычитаем числители, знаменатель оставляем.";
const QUIZ = "Проверка: сложение дробей";
const TESTS_QUIZ = "Контрольный тест по дробям";
const ANSWER = "Ответ двух плюс двух E2E";

const lessonMd = (img: string) => `Сегодня складываем дроби с одинаковым знаменателем: $\\frac{1}{4} + \\frac{2}{4}$.

> **Главное.** Складываем числители, знаменатель оставляем прежним.

> **Приём.** Сначала проверьте, что знаменатели одинаковые.

> **Ловушка.** Знаменатели не складывают: $\\frac{1}{4} + \\frac{1}{4} \\ne \\frac{2}{8}$.

> **Вспомни.** Дробь $\\frac{a}{b}$ — это $a$ долей из $b$ равных частей.

| Дробь | Десятичная запись |
|---|---|
| $\\frac{1}{2}$ | 0,5 |
| $\\frac{1}{4}$ | 0,25 |
| $\\frac{3}{4}$ | 0,75 |

![Круг из четырёх долей](${img} "Рисунок 1. Четыре доли круга")

---

> **Проверь себя.** Сколько будет $2 + 2$?
>
> **Ответ.** 4 — ${ANSWER}.

> **Почему так?** Две доли и ещё две доли дают четыре доли того же размера.

> **Разбор.** Найдите $x$, если $x - 2 = 3$.
>
> 1. Перенесём $2$ в правую часть: $x = 3 + 2$.
> 2. Сложим числа.
>
> **Ответ:** 5

$$
\\frac{1}{4} + \\frac{2}{4} = \\frac{1 + 2}{4} = \\frac{3}{4}
$$
`;

const q3 = (stem: string, right: string, wrong1: string, wrong2: string) => ({
  type: "single_choice", language: "ru", stem, explanation: null,
  data: { choices: [{ id: "A", text: wrong1 }, { id: "B", text: right }, { id: "C", text: wrong2 }], correct: "B" },
});

/** A published course of `teacher` (ru) that `student` joins by its code. */
async function course(teacher: SeedUser, student: SeedUser, title: string): Promise<string> {
  const c = await api(teacher, "POST", "/courses", { title: { ru: title }, languages: ["ru"], default_language: "ru" });
  await api(teacher, "POST", `/courses/${c.id}/publish`, {});
  await api(student, "POST", "/courses/join", { code: c.join_code });
  return c.id;
}

/** A module quiz (`placement`), two published single-choice questions of three options. */
async function moduleQuiz(teacher: SeedUser, cid: string, mid: string, title: string, placement: "lesson" | "tests") {
  const out = await api(teacher, "POST", `/courses/${cid}/modules/${mid}/quiz`, {
    kind: "quiz", title: { ru: title }, quiz: { languages: ["ru"], ...(placement === "lesson" ? { placement } : {}) },
  });
  const bank = await api(teacher, "POST", `/courses/${cid}/banks`, { title: `Банк: ${title}`, default_language: "ru" });
  const ids: string[] = [];
  for (const q of [q3("Сколько будет $\\frac{1}{2} + \\frac{1}{4}$?", "3/4", "2/6", "1/8"),
    q3("Сколько будет $\\frac{1}{3} + \\frac{1}{3}$?", "2/3", "2/6", "1/9")]) {
    ids.push((await api(teacher, "POST", `/courses/${cid}/banks/${bank.id}/questions`, q)).id);
  }
  const base = `/courses/${cid}/assessments/${out.assessment_id}`;
  const sec = await api(teacher, "POST", `${base}/sections`, { title: { ru: "Часть 1" } });
  await api(teacher, "POST", `${base}/sections/${sec.id}/items/bulk`, { question_ids: ids });
  await api(teacher, "POST", `${base}/publish`, {});
  return { itemId: out.item.id as string, assessmentId: out.assessment_id as string, assignmentId: out.assignment.id as string };
}

async function noHorizontalScroll(page: Page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(0);
}

/** At 375 / 1440 / 1920: no page scroll sideways; with LC_SHOTS a PNG (the full page, or the viewport with `focus`
 * scrolled to its middle). Back at 1440 after. */
async function widths(page: Page, name: string, focus?: Locator) {
  for (const width of WIDTHS) {
    await page.setViewportSize({ width, height: 900 });
    await settle(page);
    await noHorizontalScroll(page);
    if (!SHOTS) continue;
    const file = path.join(PNG_DIR, `${name}-${width}-ru.png`);
    const opts = { path: file, animations: "disabled" as const, caret: "hide" as const };
    if (focus) {
      await focus.evaluate((el) => el.scrollIntoView({ block: "center" }));
      await settle(page);
      await page.screenshot(opts);
    } else await page.screenshot({ ...opts, fullPage: true });
  }
  await page.setViewportSize(VIEWPORTS.desktop);
  await settle(page);
}

test.describe("lesson course (ru)", () => {
  test("lesson components, self-check, lesson quiz inside Уроки, Cyrillic letters, result to the next lesson", async ({ page }) => {
    test.setTimeout(300_000);
    if (SHOTS) { fs.rmSync(PNG_DIR, { recursive: true, force: true }); fs.mkdirSync(PNG_DIR, { recursive: true }); }
    const s = seed();
    const { teacher, student } = s.lesson_course;

    // ---- the lesson course: image asset, module 1 (page with components + lesson quiz), module 2 (one page)
    const cid = await course(teacher, student, COURSE);
    const form = new FormData();
    form.append("file", new Blob([new Uint8Array(gradientPng(480, 270))], { type: "image/png" }), "doli.png");
    const up = await fetch(`${s.api}/api/v1/courses/${cid}/assets`, { method: "POST", headers: { Authorization: `Bearer ${teacher.token}` }, body: form });
    expect(up.status, await up.clone().text()).toBeLessThan(300);
    const asset = await up.json();
    expect(asset.url, "the image is served by the media route").toMatch(/^\/api\/v1\/media\//);

    const pageItem = async (mid: string, title: string, body: string) => {
      const pg = await api(teacher, "POST", `/courses/${cid}/pages`, { title, language: "ru", body_md: body, published: true });
      return (await api(teacher, "POST", `/courses/${cid}/modules/${mid}/items`, { kind: "page", page_id: pg.id, published: true })).id as string;
    };
    const m1 = (await api(teacher, "POST", `/courses/${cid}/modules`, { title: { ru: M1 }, published: true })).id as string;
    const p1 = await pageItem(m1, P1, lessonMd(asset.url));
    const quiz = await moduleQuiz(teacher, cid, m1, QUIZ, "lesson");
    const m2 = (await api(teacher, "POST", `/courses/${cid}/modules`, { title: { ru: M2 }, published: true })).id as string;
    const p2 = await pageItem(m2, P2, P2_TEXT);

    // the server's view: a lesson quiz, no tests; the home lists it nowhere
    const out = await api(student, "GET", `/courses/${cid}`);
    expect(out.features).toMatchObject({ lesson_quizzes: true, tests: false });
    const home = JSON.stringify(await api(student, "GET", "/me/home"));
    expect(home, "the home never lists a lesson quiz").not.toContain(quiz.assessmentId);
    expect(home).not.toContain(quiz.assignmentId);

    // ---- the default quiz of another course (cheap check below)
    const other = await course(teacher, student, OTHER);
    const om = (await api(teacher, "POST", `/courses/${other}/modules`, { title: { ru: "Контроль" }, published: true })).id as string;
    await moduleQuiz(teacher, other, om, TESTS_QUIZ, "tests");

    await signIn(page, student);
    await page.setViewportSize(VIEWPORTS.desktop);

    // ---- the home: the to-do never shows the lesson quiz
    await page.goto(`/${L}/home`);
    await settle(page);
    await expect(page.getByRole("main")).toBeVisible();
    await expect(page.getByText(QUIZ)).toHaveCount(0);

    // ---- the course: Обзор · Уроки · Аналитика · Повторение, no Тесты (nor Задания)
    const base = `/${L}/courses/${cid}`;
    await page.goto(base);
    const tabs = page.getByRole("navigation", { name: t("course.tabs.label") });
    const tab = (key: string) => tabs.getByRole("link", { name: t(`course.tabs.${key}`), exact: true });
    for (const key of ["overview", "lessons", "analytics", "saved"]) await expect(tab(key)).toBeVisible();
    await expect(tab("tests")).toHaveCount(0);
    await expect(tab("assignments")).toHaveCount(0);
    expect(await tabs.getByRole("link").allInnerTexts()).toEqual(["overview", "lessons", "analytics", "saved"].map((k) => t(`course.tabs.${k}`)));

    // ---- Уроки → page 1
    await tab("lessons").click();
    await page.waitForURL(new RegExp(`${base}/lessons$`));
    const sec1 = page.locator(`#module-${m1}`);
    await sec1.getByRole("link", { name: new RegExp(P1) }).click();
    await page.waitForURL(new RegExp(`/modules/${m1}/items/${p1}$`));
    await expect(page.getByRole("heading", { level: 1, name: P1 })).toBeVisible();
    const body = page.locator(".page-body");
    await expect(body.locator("section.lesson-card")).toHaveCount(2);
    for (const kind of ["key", "tip", "trap", "recall", "check"]) await expect(body.locator(`aside.callout--${kind}`).first()).toBeVisible();
    await expect(body.locator("aside.callout--key .callout__label")).toHaveText("Главное");
    await expect(body.locator("details.why > summary")).toBeVisible();
    await expect(body.locator("div.worked ol.worked__steps > li")).toHaveCount(2);
    await expect(body.locator("div.worked p.worked__answer")).toContainText("5");
    await expect(body.locator("figure figcaption")).toHaveText("Рисунок 1. Четыре доли круга");
    const img = body.locator("figure img");
    await expect(img).toBeVisible();
    await expect.poll(() => img.evaluate((el: HTMLImageElement) => el.complete && el.naturalWidth > 0), { message: "the image loads" }).toBe(true);
    await expect(body.locator("table tr")).toHaveCount(4);
    await expect(body.locator(".katex").first()).toBeVisible();
    await expect(body.locator(".katex-display")).toHaveCount(1);
    await widths(page, "lesson-page");

    // ---- «Проверь себя»: the answer is hidden; Enter on the summary opens it, the summary reads «Скрыть ответ»
    const check = body.locator("aside.callout--check");
    const details = check.locator("details").first();
    const summary = details.locator(":scope > summary");
    const answer = check.getByText(ANSWER);
    await expect(answer).toBeHidden();
    const closedText = (await summary.innerText()).trim();
    expect(closedText).toBe("Показать ответ");
    await summary.focus();
    await page.keyboard.press("Enter");
    await expect(details).toHaveAttribute("open", "");
    await expect(answer).toBeVisible();
    await expect(summary).toHaveText("Скрыть ответ");
    await widths(page, "self-check-open", check);

    // ---- next: the quiz card inside the lesson (no lobby)
    const pager = page.getByRole("navigation", { name: t("modules.lesson.pagerLabel") });
    await pager.getByRole("link", { name: new RegExp(t("modules.lesson.next")) }).click();
    await page.waitForURL(new RegExp(`/modules/${m1}/items/${quiz.itemId}$`));
    const card = page.locator(`section[aria-labelledby="quiz-${quiz.itemId}"]`);
    await expect(card.getByRole("heading", { name: QUIZ })).toBeVisible();
    await expect(card).toContainText(t("modules.lesson.quiz.eyebrow"));
    await expect(card).toContainText("2 вопроса");
    const startBtn = card.getByRole("button", { name: t("modules.lesson.quiz.start"), exact: true });
    await expect(startBtn).toBeVisible();
    expect(page.url()).not.toContain("/assessments/");
    await widths(page, "quiz-card");

    // ---- «Начать»: the player with Cyrillic letters А Б В; answer both right (B), finish
    await startBtn.click();
    await page.waitForURL(/\/attempts\/[0-9a-f-]{36}\?return=/);
    const attemptId = /\/attempts\/([0-9a-f-]{36})/.exec(page.url())![1];
    for (let i = 0; i < 2; i += 1) {
      const radios = page.getByRole("radiogroup", { name: t("player.answers") }).getByRole("radio");
      await expect(radios).toHaveCount(3);
      for (const [j, letter] of ["А", "Б", "В"].entries()) await expect(radios.nth(j).locator("span").first()).toHaveText(letter);
      await radios.nth(1).click();
      await expect(radios.nth(1)).toHaveAttribute("aria-checked", "true");
      if (i === 0) await page.getByRole("button", { name: t("player.next") }).click();
    }
    await goToReviewPage(page);
    await page.getByRole("button", { name: t("player.finishTest") }).first().click();
    await page.getByRole("dialog").getByRole("button", { name: t("player.submit.confirm") }).click();

    // ---- the result belongs to Уроки; «Следующий урок» is the primary step
    await page.waitForURL(new RegExp(`/attempts/${attemptId}/result`));
    await expect(tab("lessons")).toHaveAttribute("aria-current", "page");
    await expect(tab("tests")).toHaveCount(0);
    const nextLesson = page.getByRole("main").getByRole("link", { name: t("modules.lesson.next") });
    await expect(nextLesson).toBeVisible();
    await expect(page.getByRole("link", { name: t("results.lesson.backToLesson") })).toHaveAttribute("href", `${base}/modules/${m1}/items/${quiz.itemId}`);
    await widths(page, "result");
    await nextLesson.click();
    await page.waitForURL(new RegExp(`/modules/${m2}/items/${p2}$`));
    await expect(page.getByRole("heading", { level: 1, name: P2 })).toBeVisible();
    await expect(page.getByText(P2_TEXT)).toBeVisible();

    // ---- the syllabus: the quiz row is done (✓)
    await page.goto(`${base}/lessons`);
    await expect(sec1.getByRole("button", { name: M1, exact: true })).toBeVisible();
    if ((await sec1.getByRole("button", { name: M1, exact: true }).getAttribute("aria-expanded")) === "false") {
      await sec1.getByRole("button", { name: M1, exact: true }).click();
    }
    const quizRow = sec1.getByRole("link", { name: new RegExp(QUIZ) });
    await expect(quizRow).toContainText(t("modules.syllabus.status.done"));

    // ---- still not on the home after the attempt
    const homeAfter = JSON.stringify((await api(student, "GET", "/me/home")).todo ?? []);
    expect(homeAfter).not.toContain(quiz.assessmentId);

    // ---- the other course: its default (tests) quiz is in Тесты
    await page.goto(`/${L}/courses/${other}`);
    await tab("tests").click();
    await page.waitForURL(new RegExp(`/courses/${other}/tests$`));
    await expect(page.getByRole("main").getByText(TESTS_QUIZ).first()).toBeVisible();

    if (SHOTS) {
      const log = execFileSync("python3", [path.resolve(__dirname, "shots_webp.py"), PNG_DIR, OUT_DIR], { encoding: "utf-8" });
      console.log(log);
    }
  });
});
