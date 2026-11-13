/**
 * Dependency-free check of the last-place write (STUDENT_IA_DESIGN §2.5).
 * Run: cd frontend && npx tsc --outDir /tmp/agy_place --module commonjs --target es2020 --skipLibCheck \
 *   src/lib/lms/lastPlace.ts src/lib/lms/lastPlace.check.ts && node /tmp/agy_place/lastPlace.check.js
 */
import {
  RECENT_MAX, continueTarget, courseRowHref, lastPlaceKey, lessonStepHref, lobbyPlace, placeHref, placeOfPath, readLastPlace,
  readRecentCourses, recentCoursesKey, recentFirst, writePlace, type LastPlace,
  type PlaceStorage,
} from "./lastPlace";

let failed = 0;
function ok(cond: boolean, msg: string) {
  if (!cond) { failed++; console.error("FAIL", msg); } else console.log("ok  ", msg);
}

class Mem implements PlaceStorage {
  m = new Map<string, string>();
  getItem(k: string) { return this.m.has(k) ? (this.m.get(k) as string) : null; }
  setItem(k: string, v: string) { this.m.set(k, v); }
}
class Broken implements PlaceStorage {
  getItem(): string | null { throw new Error("SecurityError"); }
  setItem(): void { throw new Error("QuotaExceededError"); }
}

// paths -> kinds
const KINDS: [string, string | null][] = [
  ["/ru/courses/c1", "overview"], ["/ru/courses/c1/lessons", "lessons"], ["/ru/courses/c1/tests", "tests"],
  ["/ky/courses/c1/analytics", "analytics"], ["/en/courses/c1/saved", "saved"],
  ["/ru/courses/c1/modules/m1/items/i1", "lesson"], ["/ru/courses/c1/pages/p1", "lesson"],
  ["/ru/courses/c1/assessments/a1", "lobby"], ["/ru/courses/c1/assignments/x1", "assignment"],
  ["/ru/courses/c1/attempts/t1", null], ["/ru/courses/c1/attempts/t1/result", null],
  ["/ru/courses/c1/settings", null], ["/ru/courses/c1/announcements", null], ["/ru/courses/c1/assessments/a1/edit", null],
  ["/ru/courses/catalog", null], ["/ru/courses/choose", null], ["/ru/courses/join", null], ["/ru/home", null], ["/courses/c1", null],
];
for (const [path, kind] of KINDS) {
  const p = placeOfPath(path);
  ok((p?.kind ?? null) === kind, `${path} -> ${kind}`);
  if (p) ok(p.courseId === "c1" && p.path === path, `${path}: course and path kept`);
}
ok(placeOfPath("/ru/courses/c1/tests?x=1#practice")?.path === "/ru/courses/c1/tests", "query and hash are not stored");

// writes
const s = new Mem();
writePlace(s, "u1", placeOfPath("/ru/courses/c1/tests"), 1000);
ok(JSON.parse(s.getItem(lastPlaceKey("u1")) as string).path === "/ru/courses/c1/tests", "last place written under ort_last_place:{userId}");
ok(lastPlaceKey("u1") === "ort_last_place:u1" && recentCoursesKey("u1") === "ort_recent_courses:u1", "key names");
ok(readLastPlace(s, "u1")?.at === 1000 && readLastPlace(s, "u1")?.kind === "tests", "read back with its time and kind");
writePlace(s, "u1", placeOfPath("/ru/courses/c2"), 2000);
writePlace(s, "u1", lobbyPlace("ru", "c1", "a9"), 3000);
ok(readLastPlace(s, "u1")?.path === "/ru/courses/c1/assessments/a9", "the player / result write the lobby path");
ok(readRecentCourses(s, "u1").join(",") === "c1,c2", "recent courses: most recent first, no duplicates");
for (let i = 0; i < 15; i++) writePlace(s, "u1", placeOfPath(`/ru/courses/k${i}`), 4000 + i);
const recent = readRecentCourses(s, "u1");
ok(recent.length === RECENT_MAX && recent[0] === "k14", "recent courses capped at 10, newest first");

// per user (Student view: the test student is another user on the same device)
ok(readLastPlace(s, "u2") === null && readRecentCourses(s, "u2").length === 0, "another user sees nothing");
writePlace(s, "u2", placeOfPath("/ru/courses/c5/saved"), 9000);
ok(readLastPlace(s, "u1")?.courseId === "k14" && readLastPlace(s, "u2")?.courseId === "c5", "users kept apart");

// nothing written for pages that are not places, empty users or missing storage
const before = s.getItem(lastPlaceKey("u1"));
writePlace(s, "u1", placeOfPath("/ru/courses/c1/attempts/t1"));
ok(s.getItem(lastPlaceKey("u1")) === before, "the player URL is never stored");
writePlace(s, "", placeOfPath("/ru/courses/c1"));
ok(s.getItem(lastPlaceKey("")) === null, "no user: nothing written");
writePlace(null, "u1", placeOfPath("/ru/courses/c1"));
ok(true, "no storage: no throw");

// broken storage never throws
let threw = false;
try {
  writePlace(new Broken(), "u1", placeOfPath("/ru/courses/c1"));
  ok(readLastPlace(new Broken(), "u1") === null, "blocked storage: read gives null");
  ok(readRecentCourses(new Broken(), "u1").length === 0, "blocked storage: no recent courses");
} catch {
  threw = true;
}
ok(!threw, "blocked storage: no throw");

// garbage values
const g = new Mem();
g.setItem(lastPlaceKey("u1"), "{not json");
g.setItem(recentCoursesKey("u1"), JSON.stringify({ a: 1 }));
ok(readLastPlace(g, "u1") === null && readRecentCourses(g, "u1").length === 0, "garbage is ignored");
writePlace(g, "u1", placeOfPath("/ru/courses/c1"), 1);
ok(readRecentCourses(g, "u1").join(",") === "c1", "a write repairs a garbage list");

// --- step 3a S3: the readers ---
const at = (courseId: string, path: string, kind: LastPlace["kind"]): LastPlace => ({ courseId, path, kind, at: 1 });
ok(placeHref("ky", { path: "/ru/courses/c1/tests" }) === "/ky/courses/c1/tests", "the place opens in the current language");
ok(courseRowHref("ru", "c1", at("c1", "/ru/courses/c1/saved", "saved")) === "/ru/courses/c1/saved", "row: the remembered tab");
ok(courseRowHref("ru", "c1", at("c1", "/ru/courses/c1/modules/m/items/i", "lesson")) === "/ru/courses/c1/lessons", "row: a lesson reopens Уроки");
ok(courseRowHref("ru", "c1", at("c1", "/ru/courses/c1/assessments/a", "lobby")) === "/ru/courses/c1/tests", "row: a lobby reopens Тесты");
ok(courseRowHref("ru", "c2", at("c1", "/ru/courses/c1/saved", "saved")) === "/ru/courses/c2", "row of another course: Обзор");
ok(courseRowHref("ru", "c2", null) === "/ru/courses/c2", "row without a place: Обзор");
ok(recentFirst([{ id: "a" }, { id: "b" }, { id: "c" }], ["c", "x", "a", "c"]).map((c) => c.id).join() === "c,a,b",
  "recent first (unknown and repeated ids ignored), then the list's order");

const lessonStep = { kind: "page", module_id: "m1", item_id: "i1", link: null };
ok(lessonStepHref("ru", "c1", lessonStep) === "/ru/courses/c1/modules/m1/items/i1", "a lesson opens the lesson page");
ok(lessonStepHref("ru", "c1", { kind: "assignment", module_id: "m1", item_id: "i1", link: { assignment_kind: "quiz", assessment_id: "q1" } })
  === "/ru/courses/c1/assessments/q1", "a quiz item opens its lobby");
ok(lessonStepHref("ru", "c1", { kind: "assignment", module_id: "m1", item_id: "i1", link: { assignment_kind: "text", assignment_id: "h1" } })
  === "/ru/courses/c1/assignments/h1", "a hand-in item opens its page");
ok(lessonStepHref("ru", "c1", { kind: "page" }) === null, "no ids: no link");

const courses = [
  { id: "t1", student_layout: "general", next_step: { kind: "open" } },
  { id: "e1", student_layout: "exam_prep", next_step: { kind: "start" } },
  { id: "l1", student_layout: "general", next_step: { kind: "continue_lesson", module_id: "m", item_id: "i", item_kind: "page" } },
  { id: "e2", student_layout: "exam_prep", next_step: { kind: "resume_test", attempt_id: "att" } },
];
const home = { in_progress: [{ attempt_id: "h-att", course_id: "e1" }], modules_next: [{ course_id: "l1", module_id: "m9", item_id: "i9", kind: "page" }] };
const place = at("t1", "/ru/courses/t1/tests", "tests");
ok(continueTarget("ru", place, courses, home).href === "/ru/courses/t1/tests" && continueTarget("ru", place, courses, home).kind === "place",
  "continue: the remembered place first");
ok(continueTarget("ru", at("gone", "/ru/courses/gone", "overview"), courses, home).kind === "resume", "a place of a course left: the server fallback");
ok(continueTarget("ru", null, courses, home).href === "/ru/courses/e1/attempts/h-att", "fallback 1: the in-progress attempt (the home's)");
ok(continueTarget("ru", null, courses, { in_progress: [], modules_next: home.modules_next }).href === "/ru/courses/l1/modules/m9/items/i9",
  "fallback 2: the first next lesson");
ok(continueTarget("ru", null, courses, { in_progress: [], modules_next: [] }).href === "/ru/courses/e1", "fallback 3: the newest exam course's Обзор");
ok(continueTarget("ru", null, [courses[0]], { in_progress: [] }).href === "/ru/courses/t1", "no exam course: the newest course's Обзор");
ok(continueTarget("ru", null, courses).href === "/ru/courses/e2/attempts/att", "phone bar (no home): a course's resume step");
ok(continueTarget("ru", null, courses.filter((c) => c.id !== "e2")).href === "/ru/courses/l1/modules/m/items/i", "phone bar: a course's next lesson");
// a course's Обзор stands for its own next step (the hub's main button is the real next step)
const withStart = courses.map((c) => (c.id === "e1" ? { ...c, next_step: { kind: "start", assessment_id: "q7" } } : c));
const step = continueTarget("ru", null, withStart, { in_progress: [], modules_next: [] });
ok(step.kind === "step" && step.href === "/ru/courses/e1/assessments/q7" && step.stepLabel === "home.hub.step.start",
  "fallback 3 with a test to start: the test's lobby, «Начать тест»");
const placedOverview = continueTarget("ru", at("e1", "/ru/courses/e1", "overview"), withStart, home);
ok(placedOverview.kind === "step" && placedOverview.href === "/ru/courses/e1/assessments/q7", "a remembered Обзор: the course's next step");
ok(continueTarget("ru", at("t1", "/ru/courses/t1", "overview"), courses, home).kind === "place", "a remembered Обзор of a course with nothing to do: the Обзор");
ok(continueTarget("ru", at("e1", "/ru/courses/e1/tests", "tests"), withStart, home).href === "/ru/courses/e1/tests", "a remembered tab stays the tab");

const none = continueTarget("ky", null, []);
ok(none.kind === "catalog" && none.href === "/ky/courses/catalog" && none.courseId === null, "no courses: the catalog (v3 V8)");

if (failed) {
  console.error(`${failed} check(s) failed`);
  process.exit(1);
}
console.log("all last-place checks passed");
