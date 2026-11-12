/**
 * Dependency-free check of the choose step's rules (STUDENT_IA_DESIGN §2.4, §4, decision N9).
 * Run: cd frontend && npx tsc --outDir /tmp/agy_choose --module commonjs --target es2020 --skipLibCheck \
 *   src/lib/lms/chooseCourses.ts src/lib/lms/chooseCourses.check.ts && node /tmp/agy_choose/chooseCourses.check.js
 */
import {
  chooseCoursesHref, defaultChecked, defaultFamily, idsToJoin, joinedOfRefusal, mainLanguageFor, subjectSections,
} from "./chooseCourses";

let failed = 0;
function ok(cond: boolean, msg: string) {
  if (!cond) { failed++; console.error("FAIL", msg); } else console.log("ok  ", msg);
}

const ORDER = ["math", "physics", "chemistry"];
const c = (id: string, subject: string | null, lang = "ru", enrolled = false) => ({ id, subject, default_language: lang, enrolled });

ok(chooseCoursesHref("ky") === "/ky/courses/choose", "the choose step's URL");

// --- sections: main first, then the registry's subject order, empty ones left out ---
const list = [c("chem", "chemistry"), c("ru", null), c("m1", "math"), c("ky", null, "ky"), c("m2", "math"), c("x", "astronomy")];
const secs = subjectSections(list, ORDER);
ok(secs.map((s) => s.key).join(",") === "main,math,chemistry,astronomy", "main, math, chemistry, then an unknown subject last");
ok(secs[0].courses.map((x) => x.id).join(",") === "ru,ky", "main courses keep the server's order");
ok(secs[1].courses.map((x) => x.id).join(",") === "m1,m2", "a subject's courses keep the server's order");
ok(subjectSections([], ORDER).length === 0, "no courses: no sections");

// --- the pre-checked main course: the UI language's (en -> ru), never one the student is in ---
ok(mainLanguageFor("ru") === "ru" && mainLanguageFor("ky") === "ky" && mainLanguageFor("en") === "ru", "en -> ru");
ok(defaultChecked(list, "ru").join(",") === "ru", "ru: ОРТ (на русском)");
ok(defaultChecked(list, "ky").join(",") === "ky", "ky: ОРТ (кыргызча)");
ok(defaultChecked(list, "en").join(",") === "ru", "en: the Russian main course");
ok(defaultChecked([c("ru", null, "ru", true), c("ky", null, "ky")], "ru").length === 0, "already in the main course: nothing pre-checked");
ok(defaultChecked([c("m1", "math")], "ru").length === 0, "no main course: nothing pre-checked");

// --- the default family (N9) ---
ok(defaultFamily(["ort", "nct"], [{ exam_family: "nct" }, { exam_family: "ort" }]) === "nct", "the newest exam course's family");
ok(defaultFamily(["ort", "nct"], [{ exam_family: null }]) === "ort", "no exam course: ОРТ");
ok(defaultFamily(["nct"], [{ exam_family: "ort" }]) === "nct", "a family without listed courses is skipped");
ok(defaultFamily([], []) === null, "no family at all");

// --- what «Записаться» sends ---
ok(idsToJoin([c("a", null), c("b", "math", "ru", true), c("d", "math")], new Set(["a", "b"])).join(",") === "a", "only checked courses the student is not in");

// --- a refusal's joined ids ---
ok(joinedOfRefusal([{ msg: "course_not_choosable", course_id: "x" }, { msg: "joined", joined: ["a", "b"] }]).join(",") === "a,b", "partial joins read");
ok(joinedOfRefusal({}).length === 0 && joinedOfRefusal(null).length === 0, "no details: none joined");

if (failed) {
  console.error(`${failed} failed`);
  process.exit(1);
}
console.log("all ok");
