/**
 * Dependency-free check of the course mark (step 3a S9, STUDENT_IA_DESIGN §0.4, V11): the table subject → icon, the
 * family marks of the main courses, the fallbacks; never the brand's graduation cap.
 * Run: cd frontend && npx tsc --outDir /tmp/agy_cicon --module commonjs --target es2020 --skipLibCheck \
 *   src/lib/lms/courseMarkKey.ts src/lib/lms/courseIcon.check.ts && node /tmp/agy_cicon/courseIcon.check.js
 */
import { courseMarkKey, DEFAULT_MARK, FAMILY_MARK, SUBJECT_MARK } from "./courseMarkKey";

let failed = 0;
function ok(cond: boolean, msg: string) {
  if (!cond) { failed++; console.error("FAIL", msg); } else console.log("ok  ", msg);
}

// §0.4: the registry's ten subjects (backend `exam_families.SUBJECTS`), with either family
const TABLE: [string, string][] = [
  ["math", "sigma"], ["physics", "atom"], ["chemistry", "flask-conical"], ["biology", "dna"], ["history", "landmark"],
  ["geography", "globe"], ["kyrgyz", "languages"], ["russian", "languages"], ["english", "languages"],
  ["literature", "book-text"],
];
ok(Object.keys(SUBJECT_MARK).length === TABLE.length, "every registry subject has a mark");
for (const [subject, key] of TABLE) {
  ok(courseMarkKey({ exam_family: "ort", subject }) === key, `ORT ${subject} → ${key}`);
  ok(courseMarkKey({ exam_family: "nct", subject }) === key, `НЦТ ${subject} → ${key} (the subject wins over the family)`);
}

// main courses (no subject) by family
ok(courseMarkKey({ exam_family: "ort", subject: null }) === "award", "ORT main → award (the golden certificate)");
ok(courseMarkKey({ exam_family: "nct", subject: null }) === "clipboard-check", "НЦТ main → clipboard-check");
ok(courseMarkKey({ exam_family: "nct" }) !== "flask-conical", "НЦТ main is no longer the flask (chemistry's now)");

// fallbacks
ok(courseMarkKey({ exam_family: null, subject: null }) === "book-open", "teacher course (no family) → book-open");
ok(courseMarkKey({}) === "book-open", "older backend (fields absent) → book-open");
ok(courseMarkKey(null) === "book-open" && courseMarkKey(undefined) === "book-open", "no course → book-open");
ok(courseMarkKey({ exam_family: "ort", subject: "astrology" }) === "award", "unknown subject → the family's mark");
ok(courseMarkKey({ exam_family: "sat", subject: null }) === "book-open", "unknown family → book-open");
ok(courseMarkKey({ subject: "math" }) === "sigma", "a subject without a family still shows its subject");
ok(DEFAULT_MARK === "book-open", "the default mark is the book");

// the brand's cap is never a course mark
const all = [...Object.values(SUBJECT_MARK), ...Object.values(FAMILY_MARK), DEFAULT_MARK] as string[];
ok(!all.some((k) => /graduation/.test(k)), "no course mark is the graduation cap");

if (failed) { console.error(`${failed} check(s) failed`); process.exit(1); }
console.log("all course mark checks passed");
