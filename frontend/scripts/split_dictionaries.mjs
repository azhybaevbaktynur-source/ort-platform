// Performance audit S4: splits src/lib/i18n/{en,ky,ru}.json (the single source of truth) into
// src/lib/i18n/generated/<lang>.core.json (loaded with every page) and <lang>.staff.json (loaded by staff areas and
// on demand). Run by `prebuild`/`predev` and by CI before tsc/next build; the generated files are git-ignored.
//
// Classification is by RULE, not by a frozen key list: a leaf belongs to `staff` when its dotted path starts with a
// prefix of STAFF_PREFIXES; everything else (including any new, unknown prefix) is `core`. Keys are never renamed.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const i18nDir = path.resolve(here, "../src/lib/i18n");
const outDir = path.join(i18nDir, "generated");

// staffPrefixes.json (shared with context.tsx): editors, administration, organization, grading set-up and exam
// construction, strings that only staff screens use. Add a prefix there to move it out of the first-screen
// dictionary; an unlisted prefix stays in core (safe default).
const STAFF_PREFIXES = JSON.parse(fs.readFileSync(path.join(i18nDir, "staffPrefixes.json"), "utf8"));

const isStaff = (p) => STAFF_PREFIXES.some((x) => p === x || p.startsWith(x + "."));

function split(node, prefix, core, staff) {
  for (const [k, v] of Object.entries(node)) {
    const p = prefix ? `${prefix}.${k}` : k;
    if (v && typeof v === "object" && !Array.isArray(v)) {
      core[k] = {};
      staff[k] = {};
      split(v, p, core[k], staff[k]);
      if (!Object.keys(core[k]).length) delete core[k];
      if (!Object.keys(staff[k]).length) delete staff[k];
    } else {
      (isStaff(p) ? staff : core)[k] = v;
    }
  }
}

fs.mkdirSync(outDir, { recursive: true });
for (const lang of ["en", "ky", "ru"]) {
  const source = JSON.parse(fs.readFileSync(path.join(i18nDir, `${lang}.json`), "utf8"));
  const core = {};
  const staff = {};
  split(source, "", core, staff);
  fs.writeFileSync(path.join(outDir, `${lang}.core.json`), JSON.stringify(core));
  fs.writeFileSync(path.join(outDir, `${lang}.staff.json`), JSON.stringify(staff));
}
