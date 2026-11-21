/**
 * Dependency-free check of the hosted lesson video rules (LESSON_VIDEOS V4).
 * Run: cd frontend && npx tsx src/components/lms/modules/videoPlayback.check.ts
 */
import {
  MIN_REFRESH_MS, REFRESH_BEFORE_MS, VIDEO_RATES, isStale, positionToSave, reachedWatched, refreshDelay, resolveApiUrl,
  restorablePosition, storedRate,
} from "./videoPlayback";

let failed = 0;
function ok(cond: boolean, msg: string) {
  if (!cond) { failed++; console.error("FAIL", msg); } else console.log("ok  ", msg);
}

const origin = "https://ort.example";
// relative API base (Next.js rewrite) and an absolute backend origin
ok(resolveApiUrl("/api/v1/videos/s?t=1", origin, "/api/v1") === "https://ort.example/api/v1/videos/s?t=1", "absolute path on the same origin");
ok(resolveApiUrl("courses/c/x.vtt", origin, "/api/v1") === "https://ort.example/api/v1/courses/c/x.vtt", "path relative to the API base");
ok(resolveApiUrl("/api/v1/s?t=1", origin, "https://api.example/api/v1") === "https://api.example/api/v1/s?t=1", "absolute path on the API origin");
ok(resolveApiUrl("https://b.r2.cloudflarestorage.com/k?X-Amz=1", origin, "/api/v1") === "https://b.r2.cloudflarestorage.com/k?X-Amz=1", "presigned R2 URL kept");

const now = Date.parse("2026-11-22T10:00:00Z");
ok(refreshDelay("2026-11-22T10:20:00Z", now) === 20 * 60_000 - REFRESH_BEFORE_MS, "refresh 60 s before a 20 min expiry");
ok(refreshDelay("2026-11-22T10:00:30Z", now) === MIN_REFRESH_MS, "an almost expired address waits the minimum");
ok(refreshDelay("not a date", now) === null, "unreadable expiry: no timer");
ok(!isStale("2026-11-22T10:20:00Z", now), "fresh address");
ok(isStale("2026-11-22T10:00:59Z", now), "inside the last minute is stale");
ok(isStale("2026-11-22T09:59:00Z", now), "expired is stale");

ok(restorablePosition(null, 300) === null, "nothing saved");
ok(restorablePosition(3, 300) === null, "the first seconds start from 0");
ok(restorablePosition(120, 300) === 120, "a middle position is restored");
ok(restorablePosition(298, 300) === null, "near the end starts over");
ok(restorablePosition(120, NaN) === 120, "unknown duration still restores");

ok(positionToSave(125.7, 300) === 125, "whole seconds saved");
ok(positionToSave(297, 300) === null, "near the end is forgotten");
ok(positionToSave(0, 300) === null, "nothing to save at 0");

ok(!reachedWatched(269, 300), "89.7 % is not watched");
ok(reachedWatched(270, 300), "90 % is watched");
ok(!reachedWatched(10, 0), "no duration: never");

ok(storedRate(1.5) === 1.5 && storedRate(3) === null && storedRate(null) === null, "only menu rates are restored");
ok(VIDEO_RATES.join(",") === "0.75,1,1.25,1.5,2", "speed menu 0.75-2");

if (failed) { console.error(`${failed} failed`); process.exit(1); }
console.log("all ok");
