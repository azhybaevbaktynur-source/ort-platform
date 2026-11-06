// S5 installable app: renders the app icons in frontend/public/icons from the header's brand mark
// (lucide "graduation-cap", white, on brand-600 #2563eb). No new dependency: Playwright's Chrome draws the SVG.
//   node scripts/pwa_icons.mjs          (from the repository root; needs frontend/node_modules)
import { createRequire } from "node:module";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const OUT = path.join(ROOT, "frontend", "public", "icons");
const require = createRequire(path.join(ROOT, "frontend", "package.json"));
const { chromium } = require("@playwright/test");

const BRAND = "#2563eb";
const CAP = `<path d="M21.42 10.922a1 1 0 0 0-.019-1.838L12.83 5.18a2 2 0 0 0-1.66 0L2.6 9.08a1 1 0 0 0 0 1.832l8.57 3.908a2 2 0 0 0 1.66 0z"/>
  <path d="M22 10v6"/><path d="M6 12.5V16a6 3 0 0 0 12 0v-3.5"/>`;

/** radius: corner radius as a share of the side (0 = full bleed); glyph: the cap's 24-unit box as a share of the side. */
function svg(size, radius, glyph) {
  const s = (size * glyph) / 24;
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 ${size} ${size}">
  <rect width="${size}" height="${size}" rx="${size * radius}" fill="${BRAND}"/>
  <g transform="translate(${size / 2} ${size / 2}) scale(${s}) translate(-12 -12)" fill="none" stroke="#fff" stroke-width="2"
    stroke-linecap="round" stroke-linejoin="round">${CAP}</g></svg>`;
}

const ICONS = [
  { file: "icon-192.png", size: 192, radius: 0.22, glyph: 0.64 },
  { file: "icon-512.png", size: 512, radius: 0.22, glyph: 0.64 },
  // maskable: full bleed, the cap inside the 80 % safe circle
  { file: "icon-maskable-512.png", size: 512, radius: 0, glyph: 0.56 },
  // iOS rounds the corners itself and fills transparency with black: full bleed
  { file: "apple-touch-icon.png", size: 180, radius: 0, glyph: 0.6 },
  { file: "favicon-32.png", size: 32, radius: 0.22, glyph: 0.72 },
];

const browser = await chromium.launch({ channel: process.env.CI ? undefined : "chrome" });
const page = await browser.newPage({ deviceScaleFactor: 1 });
for (const icon of ICONS) {
  await page.setViewportSize({ width: icon.size, height: icon.size });
  await page.setContent(`<html><body style="margin:0;background:transparent">${svg(icon.size, icon.radius, icon.glyph)}</body></html>`);
  await page.screenshot({ path: path.join(OUT, icon.file), omitBackground: true, clip: { x: 0, y: 0, width: icon.size, height: icon.size } });
  console.log("wrote", icon.file);
}
await browser.close();
