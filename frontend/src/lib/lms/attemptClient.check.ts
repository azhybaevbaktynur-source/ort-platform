/**
 * Dependency-free check of the clock and autosave-queue logic.
 * Run (from repo root):
 *   cd frontend && npx tsc --outDir /tmp/agy_f2_check --module commonjs --target es2020 --skipLibCheck \
 *     src/lib/lms/attemptClient.ts src/lib/lms/attemptClient.check.ts && node /tmp/agy_f2_check/attemptClient.check.js
 */
import {
  AutosaveQueue, LAST_MINUTE_HEARTBEAT_MS, ServerClock, backoffMs, classifyCloseFailure, classifyFailure,
  parseUnsavedParam, remainingMs, storageKey, summarizeUnsaved, unsavedParam, type QueueEnv,
} from "./attemptClient";
import type { AnswerIn, SaveOut } from "./attemptTypes";

let failed = 0;
function ok(cond: boolean, msg: string) {
  if (!cond) { failed++; console.error("FAIL", msg); } else console.log("ok  ", msg);
}
const flush = () => new Promise((r) => setImmediate(r));

// fake timers
function makeEnv(saveImpl: (a: AnswerIn[]) => Promise<SaveOut>, store: Record<string, string>) {
  let t = 1_000_000;
  const timers = new Map<number, { at: number; fn: () => void }>();
  let id = 0;
  const env: QueueEnv = {
    save: saveImpl,
    setTimer: (fn, ms) => { timers.set(++id, { at: t + ms, fn }); return id; },
    clearTimer: (h) => { timers.delete(h as number); },
    now: () => t,
    rand: () => 0.5,
    storage: {
      getItem: (k) => (k in store ? store[k] : null),
      setItem: (k, v) => { store[k] = v; },
      removeItem: (k) => { delete store[k]; },
    },
  };
  const advance = async (ms: number) => {
    const end = t + ms;
    for (;;) {
      const due = [...timers.entries()].filter(([, x]) => x.at <= end).sort((a, b) => a[1].at - b[1].at)[0];
      if (!due) break;
      timers.delete(due[0]);
      t = Math.max(t, due[1].at);
      due[1].fn();
      await flush();
    }
    t = end;
  };
  return { env, advance, timers };
}
const out = (): SaveOut => ({ saved: [], stale: [], server_now: new Date().toISOString(), status: "in_progress", current_section_pos: 0 });

(async () => {
  // clock: lowest-RTT sample wins
  const c = new ServerClock();
  c.sample(new Date(10_000).toISOString(), 0, 2000); // rtt 2000 -> offset 10000-1000 = 9000
  c.sample(new Date(20_050).toISOString(), 10_000, 10_100); // rtt 100 -> offset 20050-10050 = 10000
  c.sample(new Date(99_999).toISOString(), 30_000, 36_000); // worse rtt ignored
  ok(c.offset === 10_000, "clock keeps lowest-RTT sample");
  const st = { sections: [{ pos: 0, started_at: null, deadline_at: new Date(50_000).toISOString(), closed_at: null }], current_section_pos: 0, deadline_at: new Date(80_000).toISOString(), navigation: "section_forward_only" as const };
  ok(remainingMs(st, c, 30_000) === 10_000, "remaining uses min(section, attempt) and server offset");
  ok(remainingMs({ ...st, deadline_at: null, navigation: "free" }, c, 0) === null, "no limit -> null");

  // backoff
  ok([0, 1, 2, 3, 4, 5, 9].map((n) => backoffMs(n, () => 0.5)).join() === "1000,2000,4000,8000,16000,30000,30000", "backoff steps");
  ok(classifyFailure({ status: 409, code: "section_closed" }).kind === "closed", "409 -> closed");
  ok(classifyFailure({ status: 0, code: "network" }).kind === "transient", "network -> transient");
  ok(classifyFailure({ status: 401, code: "unknown" }).kind === "auth", "401 -> auth");

  // coalescing + batching + persistence
  const store: Record<string, string> = {};
  const calls: AnswerIn[][] = [];
  const m = makeEnv(async (a) => { calls.push(a); return out(); }, store);
  const q = new AutosaveQueue("A1", m.env);
  q.set(1, { response: { choice_id: "a" } });
  q.set(1, { response: { choice_id: "b" } });
  q.set(1, { flagged: true });
  ok(q.pending === 1, "coalesced per position");
  const e = q.peek()[0];
  ok(JSON.stringify(e.response) === '{"choice_id":"b"}' && e.flagged === true, "latest response kept, flag merged");
  ok(!!store[storageKey("A1")], "mirrored to storage");
  await m.advance(1400);
  ok(calls.length === 0, "no flush before idle 1.5 s");
  await m.advance(200);
  ok(calls.length === 1 && q.pending === 0, "flush after idle; queue empty");
  ok(!(storageKey("A1") in store), "storage cleared when empty");
  for (let i = 0; i < 45; i++) q.set(i, { response: { value: String(i) } });
  await q.flushNow();
  ok(calls.slice(1).map((c2) => c2.length).join() === "20,20,5", "batches of <= 20");

  // retry with backoff, replay keeps client_ts
  let fail = 2;
  const seen: AnswerIn[][] = [];
  const m2 = makeEnv(async (a) => { seen.push(a); if (fail-- > 0) throw { status: 0, code: "network" }; return out(); }, {});
  const q2 = new AutosaveQueue("A2", m2.env);
  q2.set(3, { response: { text: "x" } });
  const ts = q2.peek()[0].client_ts;
  await m2.advance(1600);
  ok(seen.length === 1 && q2.snapshot().status === "offline", "first failure -> offline, queue kept");
  await m2.advance(1000); // backoff 1s (rand .5 -> exactly 1000)
  ok(seen.length === 2, "retry after backoff 1 s");
  await m2.advance(2000);
  ok(seen.length === 3 && q2.pending === 0, "third attempt succeeds");
  ok(seen.every((b) => b[0].client_ts === ts), "replays carry the original client_ts");

  // entry changed while in flight survives ack
  let release: () => void = () => {};
  const m3 = makeEnv(() => new Promise<SaveOut>((r) => { release = () => r(out()); }), {});
  const q3 = new AutosaveQueue("A3", m3.env);
  q3.set(1, { response: { text: "a" } });
  void q3.flushNow();
  await flush();
  q3.set(1, { response: { text: "ab" } });
  release();
  await flush(); await flush();
  ok(q3.pending === 1, "newer edit made during flight is not dropped by the ack");

  // beyond grace -> closed, queue cleared, handler fired
  let closed = "";
  const m4 = makeEnv(async () => { throw { status: 409, code: "attempt_closed", details: {} }; }, { [storageKey("A4")]: JSON.stringify([{ position: 7, client_ts: 5, response: { text: "late" } }]) });
  const q4 = new AutosaveQueue("A4", m4.env, { onClosed: (i) => { closed = i.code; } });
  ok(q4.pending === 1, "restored from storage");
  q4.kick();
  await flush(); await flush();
  ok(closed === "attempt_closed" && q4.pending === 0, "409 attempt_closed clears queue and notifies");

  // invalid -> drop those positions only
  let rej: number[] = [];
  const m5 = makeEnv(async () => { throw { status: 422, code: "invalid_response", details: { positions: [2] } }; }, {});
  const q5 = new AutosaveQueue("A5", m5.env, { onRejected: (p2) => { rej = p2; } });
  q5.set(1, { response: { text: "a" } }); q5.set(2, { response: { text: "b" } });
  await q5.flushNow();
  ok(rej.join() === "2" && q5.pending === 1, "422 drops only reported positions");

  // 401 keeps queue and stops retrying
  let n6 = 0;
  const m6 = makeEnv(async () => { n6++; throw { status: 401, code: "unknown" }; }, {});
  const q6 = new AutosaveQueue("A6", m6.env);
  q6.set(1, { response: { text: "a" } });
  await q6.flushNow(); await m6.advance(60_000);
  ok(n6 === 1 && q6.pending === 1 && q6.snapshot().status === "auth", "401 keeps queue, no retry storm");

  // too_many_answers (422): batch is split, nothing is dropped
  const sizes: number[] = [];
  const saved7: number[] = [];
  const m7 = makeEnv(async (b) => {
    sizes.push(b.length);
    if (b.length > 3) throw { status: 422, code: "too_many_answers" };
    saved7.push(...b.map((x) => x.position));
    return out();
  }, {});
  const q7 = new AutosaveQueue("A7", m7.env);
  for (let i = 1; i <= 10; i++) q7.set(i, { response: { text: "x" } });
  await q7.flushNow(); await m7.advance(60_000);
  ok(classifyFailure({ status: 422, code: "too_many_answers" }).kind === "too_large", "too_many_answers -> too_large (split)");
  ok(saved7.length === 10 && new Set(saved7).size === 10 && q7.pending === 0, "split batches deliver every entry");

  // close-section outcomes are explicit, not "closed"
  ok(classifyCloseFailure({ status: 409, code: "use_submit" }) === "use_submit", "close: use_submit");
  ok(classifyCloseFailure({ status: 409, code: "section_not_current" }) === "not_current", "close: section_not_current");
  ok(classifyCloseFailure({ status: 409, code: "attempt_closed" }) === "closed", "close: attempt_closed");
  ok(classifyCloseFailure({ status: 0, code: "network" }) === "other", "close: network -> other");

  // last minute (B2): every change goes out at once, no debounce
  const lm: AnswerIn[][] = [];
  const m8 = makeEnv(async (b) => { lm.push(b); return out(); }, {});
  const q8 = new AutosaveQueue("A8", m8.env);
  q8.setContinuous(true);
  ok(q8.lastMinute, "last-minute mode on");
  q8.set(1, { response: { text: "a" } });
  await m8.advance(0);
  ok(lm.length === 1 && q8.pending === 0, "last minute: change sent immediately (no 1.5 s debounce)");
  q8.set(2, { response: { text: "b" } });
  q8.set(3, { response: { text: "c" } });
  await m8.advance(0);
  ok(lm.length === 2 && lm[1].length === 2, "last minute: same-tick changes go in one request");
  q8.setContinuous(false);
  q8.set(4, { response: { text: "d" } });
  await m8.advance(100);
  ok(lm.length === 2 && q8.pending === 1, "normal mode debounces again");
  await m8.advance(1500);
  ok(lm.length === 3 && q8.pending === 0, "normal mode flushes after idle");

  // last minute: the 5 s heartbeat re-sends dirty entries and cuts a long backoff short
  let down = 3;
  const hb: number[] = [];
  const m9 = makeEnv(async (b) => {
    hb.push(b.length);
    if (down-- > 0) throw { status: 503, code: "unknown" };
    return out();
  }, {});
  const q9 = new AutosaveQueue("A9", m9.env);
  q9.set(1, { response: { text: "a" } });
  await q9.flushNow(); // fail 1 -> backoff 1 s
  await m9.advance(1000); // fail 2 -> backoff 2 s
  await m9.advance(2000); // fail 3 -> backoff 4 s, next retry would be at +4 s
  ok(hb.length === 3 && q9.pending === 1, "three failures, entry kept");
  q9.setContinuous(true);
  await m9.advance(LAST_MINUTE_HEARTBEAT_MS - 1);
  ok(hb.length === 4 && q9.pending === 0, "backoff retry delivers the entry");
  q9.set(2, { response: { text: "b" } });
  await m9.advance(0);
  ok(hb.length === 5 && q9.pending === 0, "and later changes go out immediately");
  // heartbeat with nothing dirty sends nothing
  await m9.advance(LAST_MINUTE_HEARTBEAT_MS * 3);
  ok(hb.length === 5, "heartbeat is silent while nothing is dirty");

  // heartbeat beats a 30 s backoff in the last minute
  let fails = 10;
  const hb2: number[] = [];
  const m10 = makeEnv(async (b) => { hb2.push(b.length); if (fails-- > 0) throw { status: 0, code: "network" }; return out(); }, {});
  const q10 = new AutosaveQueue("A10", m10.env);
  q10.set(1, { response: { text: "a" } });
  for (let i = 0; i < 6; i++) { await q10.flushNow(); } // drive the backoff up without advancing time
  const before = hb2.length;
  fails = 0;
  q10.setContinuous(true);
  await m10.advance(LAST_MINUTE_HEARTBEAT_MS);
  ok(hb2.length === before + 1 && q10.pending === 0, "heartbeat retries within 5 s despite a long backoff");
  q10.dispose();
  ok(m10.timers.size === 0, "dispose clears the heartbeat");

  // after-submit notice helpers
  const rejs = [
    { position: 3, reason: "deadline" as const }, { position: 4, reason: "deadline" as const },
    { position: 5, reason: "stale" as const }, { position: 5, reason: "deadline" as const },
    { position: 6, reason: "already_submitted" as const },
  ];
  const sum = summarizeUnsaved(rejs);
  ok(sum.deadline === 2 && sum.other === 1 && sum.already_submitted === 1 && !sum.section_closed, "rejected grouped, positions counted once");
  ok(unsavedParam(rejs) === "deadline:2,already_submitted:1,other:1", "unsaved param encodes groups in a fixed order");
  ok(unsavedParam([]) === "" && unsavedParam(undefined) === "", "nothing rejected -> no param");
  ok(JSON.stringify(parseUnsavedParam("deadline:2,bogus:4,other:x,section_closed:1")) === '[["deadline",2],["section_closed",1]]', "parse ignores junk");

  if (failed) { console.error(failed + " check(s) failed"); process.exit(1); }
  console.log("all checks passed");
})();
