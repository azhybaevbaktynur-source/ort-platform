/**
 * Dependency-free check of the stale-while-revalidate cache (PERFORMANCE_AUDIT S2): fresh, stale, in-flight dedup,
 * token change, invalidate, markStale, 401, session storage.
 * Run (from repo root):
 *   cd frontend && npx tsc --outDir /tmp/agy_swr_check --module commonjs --target es2020 --skipLibCheck \
 *     --esModuleInterop src/lib/lms/swr.ts src/lib/lms/swr.check.ts && \
 *     ln -sfn "$PWD/node_modules" /tmp/agy_swr_check/node_modules && node /tmp/agy_swr_check/swr.check.js
 */
import { cached, clearAll, configureSwr, invalidate, markStale, peek, put, revalidate, subscribe } from "./swr";

let failed = 0;
function ok(cond: boolean, msg: string) {
  if (!cond) { failed++; console.error("FAIL", msg); } else console.log("ok  ", msg);
}
const flush = () => new Promise((r) => setImmediate(r));

let t = 1_000_000;
let token = "tok-a";
const disk: Record<string, string> = {};
const storage = {
  getItem: (k: string) => (k in disk ? disk[k] : null),
  setItem: (k: string, v: string) => { disk[k] = v; },
  removeItem: (k: string) => { delete disk[k]; },
};
configureSwr({ now: () => t, token: () => token, storage: () => storage });

function counter<T>(values: T[]) {
  const f = () => { f.calls++; return Promise.resolve(values[Math.min(f.calls - 1, values.length - 1)]); };
  f.calls = 0;
  return f;
}

async function main() {
  // missing: one request; fresh: no request
  const a = counter(["a1", "a2"]);
  ok((await cached("a", a, { ttl: 1000 })) === "a1" && a.calls === 1, "missing key fetches once");
  ok((await cached("a", a, { ttl: 1000 })) === "a1" && a.calls === 1, "fresh answer returned without a request");

  // stale: old value at once, one background request, then the new value
  t += 1001;
  ok((await cached("a", a, { ttl: 1000 })) === "a1", "stale answer returned at once");
  ok(a.calls === 2, "stale answer triggers one background request");
  await flush();
  ok(peek<string>("a")?.value === "a2", "background answer replaces the stale one");

  // in-flight dedup
  let resolve!: (v: string) => void;
  const slow = Object.assign(() => { slow.calls++; return new Promise<string>((r) => { resolve = r; }); }, { calls: 0 });
  const p1 = cached("b", slow);
  const p2 = cached("b", slow);
  ok(slow.calls === 1, "two callers of the same key share one request");
  resolve("b1");
  ok((await p1) === "b1" && (await p2) === "b1", "both callers get the shared answer");

  // invalidate by prefix; a request dropped by invalidate does not land
  put("bootstrap", 1);
  put("course:1", "c1");
  put("course:2", "c2");
  let notified = 0;
  const off = subscribe(() => { notified++; });
  invalidate("course:");
  ok(peek("course:1") === null && peek("course:2") === null && peek("bootstrap") !== null, "invalidate drops the prefix only");
  ok(notified === 1, "invalidate notifies subscribers once");
  off();
  const late = Object.assign(() => { late.calls++; return new Promise<string>((r) => { resolve = r; }); }, { calls: 0 });
  const pl = cached("course:1", late);
  invalidate("course:");
  resolve("old");
  ok((await pl) === "old" && peek("course:1") === null, "an answer asked before invalidate is not stored");
  const fresh = counter(["new"]);
  ok((await cached("course:1", fresh)) === "new" && fresh.calls === 1, "after invalidate the next read fetches");
  ok((await revalidate("course:1", counter(["newer"]))) === "newer" && peek("course:1")?.value === "newer", "revalidate asks again");

  // session storage: kept per token; another token sees nothing
  put("me", { id: "u1" }, { storage: "session" });
  ok(!!disk.ort_swr_v1 && disk.ort_swr_v1.includes("tok-a"), "session entries are written with the token");
  ok(!disk.ort_swr_v1.includes("course:1"), "memory entries are not written to the session");
  configureSwr({}); // a reload: memory gone, the session copy comes back for the same token only
  ok((peek<{ id: string }>("me")?.value)?.id === "u1", "same token after a reload reads the session copy");
  const again = counter([{ id: "u1b" }]);
  ok((await cached("me", again, { storage: "session" }))?.id === "u1" && again.calls === 1, "a session copy after a reload is shown and asked again once");
  await flush();
  ok(peek<{ id: string }>("me")?.value.id === "u1b", "the reload's answer replaces the session copy");
  ok(peek("course:1") === null, "memory entries do not survive a reload");
  token = "tok-b";
  ok(peek("me") === null && peek("a") === null, "another token sees nothing");
  const b = counter(["b-me"]);
  ok((await cached("me", b)) === "b-me" && b.calls === 1, "another token fetches its own");
  ok(!disk.ort_swr_v1 || !disk.ort_swr_v1.includes("u1"), "the previous token's session copy is gone");
  token = "tok-a";
  configureSwr({});
  ok(peek("me") === null, "back to the first token: nothing of the other token, nothing stale of its own");

  // a request asked under one token never lands under another
  const swap = Object.assign(() => { swap.calls++; return new Promise<string>((r) => { resolve = r; }); }, { calls: 0 });
  const ps = cached("x", swap);
  token = "tok-c";
  resolve("x-a");
  await ps;
  ok(peek("x") === null, "an answer for the previous token is not stored under the new one");
  token = "tok-a";
  configureSwr({});

  // 401 clears everything; other errors keep the cache
  put("keep", 1);
  const boom = () => Promise.reject(Object.assign(new Error("x"), { status: 500 }));
  await cached("y", boom).catch(() => undefined);
  ok(peek("keep") !== null, "a non-401 error keeps the cache");
  const unauthorized = () => Promise.reject(Object.assign(new Error("x"), { status: 401 }));
  await cached("z", unauthorized).catch(() => undefined);
  ok(peek("keep") === null && peek("me") === null && !disk.ort_swr_v1, "a 401 clears memory and session");

  // markStale: the answer stays and is shown, the next read asks again; a request asked before is dropped
  put("bootstrap", "b1", { ttl: 60_000 });
  const before = Object.assign(() => { before.calls++; return new Promise<string>((r) => { resolve = r; }); }, { calls: 0 });
  const pb = revalidate("bootstrap", before, { ttl: 60_000 });
  const resolveBefore = resolve;
  markStale("bootstrap");
  ok(peek("bootstrap")?.value === "b1", "markStale keeps the answer");
  const after = counter(["b2"]);
  ok((await cached("bootstrap", after, { ttl: 60_000 })) === "b1" && after.calls === 1, "a stale-marked answer is shown and asked again");
  resolveBefore("b-old");
  await pb;
  await flush();
  ok(peek("bootstrap")?.value === "b2", "the request asked before markStale does not overwrite the new answer");

  // clearAll (sign-out)
  put("q", 1, { storage: "session" });
  clearAll();
  ok(peek("q") === null && !disk.ort_swr_v1, "clearAll drops everything");

  // a failed background refresh keeps the stale answer
  put("s", "old", { ttl: 10 });
  t += 11;
  ok((await cached("s", boom, { ttl: 10 })) === "old", "stale answer returned when the refresh will fail");
  await flush();
  ok(peek("s")?.value === "old", "a failed refresh keeps the stale answer");

  if (failed) { console.error(`${failed} check(s) failed`); process.exit(1); }
  console.log("all swr checks passed");
}

void main();
