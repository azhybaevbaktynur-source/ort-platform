// Phase 8c S4a: pair the recorded before/after ORT screens (record.sh) and classify them with the harness's own
// rule (frontend/e2e/helpers.ts: pixelmatch, threshold 0.1, anti-aliased pixels ignored, more than 0.5 % of the
// pixels differ or a different size = changed). Changed screens get a side-by-side image (before left, after right,
// magenta gap) `sbs-<name>.png`; every screen is listed with its ratio in `differences.txt`. Identical-enough
// screens stay only in before/ and after/.
//
//   node compare.mjs        (run by record.sh; resolves pixelmatch / pngjs from frontend/node_modules)
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const fe = path.resolve(here, "../../../../frontend");
const require = createRequire(path.join(fe, "package.json"));
const { PNG } = require("pngjs");
const pixelmatch = (await import(pathToFileURL(require.resolve("pixelmatch")).href)).default;

const MAX = 0.005;
const bDir = path.join(here, "before");
const aDir = path.join(here, "after");
const names = fs.readdirSync(aDir).filter((f) => f.endsWith(".png") && fs.existsSync(path.join(bDir, f))).sort();
const changed = [];
const same = [];
for (const f of names) {
  const b = PNG.sync.read(fs.readFileSync(path.join(bDir, f)));
  const a = PNG.sync.read(fs.readFileSync(path.join(aDir, f)));
  let ratio = 1;
  let size = `${b.width}x${b.height}`;
  if (a.width === b.width && a.height === b.height) {
    const bad = pixelmatch(b.data, a.data, null, a.width, a.height, { threshold: 0.1, includeAA: false });
    ratio = bad / (a.width * a.height);
  } else {
    size = `${b.width}x${b.height} -> ${a.width}x${a.height}`;
  }
  (ratio > MAX ? changed : same).push({ f, ratio, size });
  if (ratio > MAX) {
    const gap = 24;
    const out = new PNG({ width: b.width + gap + a.width, height: Math.max(a.height, b.height) });
    for (let i = 0; i < out.data.length; i += 4) { out.data[i] = 255; out.data[i + 1] = 0; out.data[i + 2] = 255; out.data[i + 3] = 255; }
    PNG.bitblt(b, out, 0, 0, b.width, b.height, 0, 0);
    PNG.bitblt(a, out, 0, 0, a.width, a.height, b.width + gap, 0);
    fs.writeFileSync(path.join(here, `sbs-${f}`), PNG.sync.write(out));
  }
}
for (const { f } of same) { fs.rmSync(path.join(bDir, f)); fs.rmSync(path.join(aDir, f)); }
const line = ({ f, ratio, size }) => `  ${f.padEnd(48)} ${(ratio * 100).toFixed(3).padStart(8)} %  ${size}\n`;
fs.writeFileSync(
  path.join(here, "differences.txt"),
  `Changed (more than ${MAX * 100} % of the pixels differ, or the size differs): ${changed.length}\n${changed.map(line).join("")}\n` +
    `Unchanged by the harness rule (must stay pixel-identical, pass against the existing baselines): ${same.length}\n${same.map(line).join("")}`,
);
console.log(`${changed.length} changed, ${same.length} unchanged`);
