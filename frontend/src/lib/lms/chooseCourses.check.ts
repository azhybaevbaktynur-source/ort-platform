/**
 * Dependency-free check of the catalog's rules (STUDENT_IA_DESIGN §2.4, decision N9; S7 removed the choose step's).
 * Run: cd frontend && npx tsc --outDir /tmp/agy_choose --module commonjs --target es2020 --skipLibCheck \
 *   src/lib/lms/chooseCourses.ts src/lib/lms/chooseCourses.check.ts && node /tmp/agy_choose/chooseCourses.check.js
 */
import { defaultFamily, subjectSections } from "./chooseCourses";

let failed = 0;
function ok(cond: boolean, msg: string) {
  if (!cond) { failed++; console.error("FAIL", msg); } else console.log("ok  ", msg);
}

const ORDER = ["math", "physics", "chemistry"];
const c = (id: string, subject: string | null, lang = "ru") => ({ id, subject, default_language: lang });

// --- sections: main first, then the registry's subject order, empty ones left out ---
const list = [c("chem", "chemistry"), c("ru", null), c("m1", "math"), c("ky", null, "ky"), c("m2", "math"), c("x", "astronomy")];
const secs = subjectSections(list, ORDER);
ok(secs.map((s) => s.key).join(",") === "main,math,chemistry,astronomy", "main, math, chemistry, then an unknown subject last");
ok(secs[0].courses.map((x) => x.id).join(",") === "ru,ky", "main courses keep the server's order");
ok(secs[1].courses.map((x) => x.id).join(",") === "m1,m2", "a subject's courses keep the server's order");
ok(subjectSections([], ORDER).length === 0, "no courses: no sections");

// --- the default family (N9) ---
ok(defaultFamily(["ort", "nct"], [{ exam_family: "nct" }, { exam_family: "ort" }]) === "nct", "the newest exam course's family");
ok(defaultFamily(["ort", "nct"], [{ exam_family: null }]) === "ort", "no exam course: ОРТ");
ok(defaultFamily(["nct"], [{ exam_family: "ort" }]) === "nct", "a family without listed courses is skipped");
ok(defaultFamily([], []) === null, "no family at all");

if (failed) {
  console.error(`${failed} failed`);
  process.exit(1);
}
console.log("all ok");
