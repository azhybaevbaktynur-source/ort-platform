import fs from "node:fs";
import path from "node:path";
import type { NextConfig } from "next";

const rawBackend = (process.env.BACKEND_INTERNAL_URL || process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
const BACKEND_URL = rawBackend.endsWith("/api/v1") ? rawBackend.slice(0, -7) : rawBackend;

// --- Phase 11 S4 begin --- (PHASE_11_DESIGN 5.5; docs/SECURITY_AUDIT.md)
function originOf(url: string | undefined): string {
  try {
    return url ? new URL(url).origin : "";
  } catch {
    return ""; // relative "/api/v1": the same origin, already 'self'
  }
}

const IS_DEV = process.env.NODE_ENV !== "production";
// The browser calls the API here; question images may also come from it (`/api/v1/media`, without R2).
const API_ORIGIN = originOf(process.env.NEXT_PUBLIC_API_URL);
// Public images. The backend's R2_PUBLIC_BASE_URL is an r2.dev address until the owner buys a domain, and this must not
// depend on a Vercel variable to keep images working. Set NEXT_PUBLIC_R2_PUBLIC_BASE_URL BEFORE moving to a custom domain.
const R2_PUBLIC = ["https://*.r2.dev", originOf(process.env.NEXT_PUBLIC_R2_PUBLIC_BASE_URL)].filter(Boolean).join(" ");

// 'unsafe-inline' in script-src is a deliberate limit: nonces force dynamic rendering on every page.
const CSP = [
  "default-src 'self'",
  `script-src 'self' 'unsafe-inline'${IS_DEV ? " 'unsafe-eval'" : ""}`, // eval: only the Next.js dev overlay
  "style-src 'self' 'unsafe-inline'", // KaTeX positions with inline styles
  `img-src 'self' data: blob: ${API_ORIGIN} ${R2_PUBLIC}`.replace(/\s+/g, " "),
  "font-src 'self' data:", // KaTeX fonts are bundled
  `connect-src 'self' ${API_ORIGIN} ${R2_PUBLIC}${IS_DEV ? " ws:" : ""}`.replace(/\s+/g, " "),
  "media-src 'self'",
  "object-src 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "frame-ancestors 'none'",
  "frame-src 'self' blob: https://www.youtube-nocookie.com https://player.vimeo.com", // U7: click-to-load lesson videos
  "worker-src 'self'", // S5: the service worker (/service-worker.js loads public/sw.js)
  "manifest-src 'self'", // S5: /manifest.webmanifest
].join("; ");

const SECURITY_HEADERS = [
  { key: "Content-Security-Policy", value: CSP },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=(), payment=(), usb=()" },
];
// --- Phase 11 S4 end ---

// Final mascot art: an SVG dropped into public/mascot replaces that pose's WebP and PNG at the next build, with no code change.
function mascotSvgPoses(): string {
  try {
    return fs.readdirSync(path.join(process.cwd(), "public", "mascot")).filter((f) => f.endsWith(".svg")).map((f) => f.slice(0, -4)).join(",");
  } catch {
    return "";
  }
}

// S5 installable app: one build id for the service worker loader (src/app/service-worker.js) and the page that
// registers it. Kept on process.env so the build's worker processes, which load this file again, see the same value.
process.env.NEXT_PUBLIC_SW_VERSION ||= (process.env.VERCEL_GIT_COMMIT_SHA || "").slice(0, 12) || Date.now().toString(36);
const NO_CACHE = [{ key: "Cache-Control", value: "no-cache" }];

const nextConfig: NextConfig = {
  env: { NEXT_PUBLIC_MASCOT_SVG: mascotSvgPoses(), NEXT_PUBLIC_SW_VERSION: process.env.NEXT_PUBLIC_SW_VERSION },
  async headers() {
    // Not on the /api rewrite: the API sets its own (a download's CSP must not be replaced by a page's).
    return [
      { source: "/((?!api/).*)", headers: SECURITY_HEADERS },
      // S5: the browser must always fetch the newest worker files (the loader's bytes carry the build)
      { source: "/service-worker.js", headers: NO_CACHE },
      { source: "/sw.js", headers: NO_CACHE },
    ];
  },
  async rewrites() {
    return [
      {
        source: "/api/v1/:path*",
        destination: `${BACKEND_URL}/api/v1/:path*`,
      },
    ];
  },
};

export default nextConfig;
