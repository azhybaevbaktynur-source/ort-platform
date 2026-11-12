/**
 * Dependency-free check of the last-place write (STUDENT_IA_DESIGN §2.5).
 * Run: cd frontend && npx tsc --outDir /tmp/agy_place --module commonjs --target es2020 --skipLibCheck \
 *   src/lib/lms/lastPlace.ts src/lib/lms/lastPlace.check.ts && node /tmp/agy_place/lastPlace.check.js
 */
import {
  RECENT_MAX, lastPlaceKey, lobbyPlace, placeOfPath, readLastPlace, readRecentCourses, recentCoursesKey, writePlace,
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

if (failed) {
  console.error(`${failed} check(s) failed`);
  process.exit(1);
}
console.log("all last-place checks passed");
