# Service worker: switch it off (S5, 2026-11-06)

The installable app uses `frontend/public/sw.js`, loaded by the generated `/service-worker.js` (carries the build id, so every deploy is an update). It caches only the app shell and `/_next/static`; never API responses or pages.

If it ever misbehaves (old pages stuck, blank screen after a deploy):
1. Replace the body of `frontend/public/sw.js` with:
   ```js
   self.addEventListener("install", () => self.skipWaiting());
   self.addEventListener("activate", async () => {
     for (const k of await caches.keys()) await caches.delete(k);
     await self.registration.unregister();
     for (const c of await self.clients.matchAll({ type: "window" })) c.navigate(c.url);
   });
   ```
2. Deploy. Every browser that opens the site picks up the new worker, deletes the caches, unregisters it and reloads once.
3. Keep that version for at least a few weeks before bringing the real worker back.
Never just delete `sw.js`: browsers keep the old worker running when the file is missing.
