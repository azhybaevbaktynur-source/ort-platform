/**
 * Dependency-free check of quizAssignmentId against the backend formula (values from Python's uuid module).
 * Run: cd frontend && npx tsc --outDir /tmp/agy_qa --module commonjs --target es2020 --skipLibCheck \
 *   src/lib/lms/quizAssignmentId.ts src/lib/lms/quizAssignmentId.check.ts && node /tmp/agy_qa/quizAssignmentId.check.js
 */
import { ASSIGN_NS, quizAssignmentId, uuid5 } from "./quizAssignmentId";

let failed = 0;
function ok(cond: boolean, msg: string) {
  if (!cond) { failed++; console.error("FAIL", msg); } else console.log("ok  ", msg);
}

ok(uuid5("6ba7b810-9dad-11d1-80b4-00c04fd430c8", "python.org") === "886313e1-3b8a-5372-9b90-0c9aee199e5d", "RFC/Python uuid5 vector (DNS, python.org)");
ok(ASSIGN_NS === "8f23ef10-81b2-521d-aba0-570d12981e4d", "ASSIGN_NS matches ids.py");
ok(quizAssignmentId("00000000-0000-0000-0000-000000000001") === "f4ab092c-441e-536c-a267-8ff320253d93", "assignment id of a fixed assessment id");
ok(quizAssignmentId("00000000000000000000000000000001") === "f4ab092c-441e-536c-a267-8ff320253d93", "hex form normalized like uuid.UUID(str(..))");

if (failed) { console.error(`${failed} failed`); process.exit(1); }
console.log("all passed");
