/*
 * S5 installable app (docs/ROADMAP_EXAM_PREP.md): the service worker, hand-written, no library.
 *
 * Loaded by /service-worker.js (src/app/service-worker.js/route.ts), a one-line loader that sets self.SW_VERSION to
 * the build and imports this file: a new deploy changes the loader's bytes, so the browser installs a new worker.
 *
 * What it does, and nothing more:
 * - caches the app shell (the offline page in three languages, its CSS/JS/mascot, the icons, the manifest) and the
 *   hashed build files under /_next/static/ (cache first: their names change when their content does);
 * - page navigations go to the network first; only when the network fails, the offline page of the URL's language;
 * - never touches the API (another origin, or /api/ on this one) or any other origin, never caches a page, an RSC
 *   payload or anything that belongs to a signed-in person (shared phones, exam integrity). The exam player's pages
 *   get the same treatment as any page: network, and the offline page only when there is no network;
 * - a new version waits; the page shows "New version: update" (components/pwa/UpdateToast.tsx), never on exam
 *   routes, and sends SKIP_WAITING when the person taps it.
 */
/* eslint-disable no-restricted-globals */
const VERSION = self.SW_VERSION || new URL(self.location.href).searchParams.get("v") || "dev";
const PREFIX = "app-";
const SHELL = `${PREFIX}shell-${VERSION}`;
const STATIC = `${PREFIX}static-${VERSION}`;
const LANGS = ["ru", "ky", "en"];
const DEFAULT_LANG = "ky"; // the site's default (src/app/page.tsx)
const offlinePath = (lang) => `/${lang}/offline`;
const SHELL_FILES = [
  "/manifest.webmanifest",
  "/icons/icon-192.png",
  "/icons/icon-512.png",
  "/icons/icon-maskable-512.png",
  "/icons/apple-touch-icon.png",
  "/icons/favicon-32.png",
];
// Files the offline page needs: build files (script tags and the inline RSC payload name them) and mascot images.
const PAGE_ASSETS = /(?:\/_next\/|["'])(static\/(?:chunks|css|media)\/[^"'\s\\)]+)|(\/mascot\/[\w.-]+)/g;

self.addEventListener("install", (event) => {
  // No skipWaiting here: a new version waits until the person chooses to update.
  event.waitUntil((async () => {
    const shell = await caches.open(SHELL);
    const stat = await caches.open(STATIC);
    await shell.addAll(SHELL_FILES);
    for (const lang of LANGS) {
      const res = await fetch(offlinePath(lang), { cache: "no-store", credentials: "omit" });
      if (!res.ok) throw new Error(`offline page ${lang}: ${res.status}`);
      const html = await res.clone().text();
      await shell.put(offlinePath(lang), res);
      const assets = new Set();
      for (const m of html.matchAll(PAGE_ASSETS)) assets.add(m[1] ? `/_next/${m[1]}` : m[2]);
      await Promise.all([...assets].map((url) =>
        (url.startsWith("/_next/static/") ? stat : shell).add(url).catch(() => undefined)));
    }
  })());
});

self.addEventListener("activate", (event) => {
  event.waitUntil((async () => {
    const keep = new Set([SHELL, STATIC]);
    for (const name of await caches.keys()) {
      if (name.startsWith(PREFIX) && !keep.has(name)) await caches.delete(name);
    }
    await self.clients.claim();
  })());
});

self.addEventListener("message", (event) => {
  if (event.data && event.data.type === "SKIP_WAITING") self.skipWaiting();
});

async function cacheFirst(request) {
  const hit = await caches.match(request);
  if (hit) return hit;
  const res = await fetch(request);
  if (res.ok && res.type === "basic") {
    const copy = res.clone();
    caches.open(STATIC).then((c) => c.put(request, copy)).catch(() => undefined);
  }
  return res;
}

async function networkFirstPage(request, url) {
  try {
    return await fetch(request);
  } catch (err) {
    const first = url.pathname.split("/")[1];
    const lang = LANGS.includes(first) ? first : DEFAULT_LANG;
    const offline = await caches.match(offlinePath(lang), { cacheName: SHELL });
    if (offline) return offline;
    throw err;
  }
}

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return; // the API origin, R2 images, anything else: untouched
  if (url.pathname.startsWith("/api/")) return; // the API through this origin: untouched
  if (request.mode === "navigate") {
    event.respondWith(networkFirstPage(request, url)); // never cached
    return;
  }
  if (url.pathname.startsWith("/_next/static/") || SHELL_FILES.includes(url.pathname)) {
    event.respondWith(cacheFirst(request));
    return;
  }
  if (url.pathname.startsWith("/mascot/")) {
    event.respondWith(fetch(request).catch(async (err) => (await caches.match(request, { cacheName: SHELL })) || Promise.reject(err)));
  }
  // Everything else (RSC payloads, pages' data, other public files) goes to the network as if there were no worker.
});
