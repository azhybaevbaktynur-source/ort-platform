/**
 * Dependency-free check of the course card palette: white text passes AA on every color, the hash is stable.
 * Run: cd frontend && npx tsc --outDir /tmp/agy_color --module commonjs --target es2020 --skipLibCheck \
 *   src/lib/lms/courseColor.ts src/lib/lms/courseColor.check.ts && node /tmp/agy_color/courseColor.check.js
 */
import { COURSE_COLORS, courseColor } from "./courseColor";

let failed = 0;
function ok(cond: boolean, msg: string) {
  if (!cond) { failed++; console.error("FAIL", msg); } else console.log("ok  ", msg);
}

function luminance(hex: string): number {
  const [r, g, b] = [1, 3, 5].map((i) => {
    const c = parseInt(hex.slice(i, i + 2), 16) / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

ok(COURSE_COLORS.length === 8, "8 colors");
ok(new Set(COURSE_COLORS).size === 8, "all different");
for (const c of COURSE_COLORS) {
  const ratio = 1.05 / (luminance(c) + 0.05);
  ok(ratio >= 4.5, `${c} with white text: ${ratio.toFixed(2)}`);
}
const id = "00000000-0000-4000-8000-000000000001";
ok(courseColor(id) === courseColor(id), "stable");
ok((COURSE_COLORS as readonly string[]).includes(courseColor(id)), "from the palette");
const seen = new Set(Array.from({ length: 200 }, (_, i) => courseColor(`00000000-0000-4000-8000-${String(i).padStart(12, "0")}`)));
ok(seen.size === 8, "ids reach every color");

if (failed) { console.error(`${failed} failed`); process.exit(1); }
console.log("all ok");
