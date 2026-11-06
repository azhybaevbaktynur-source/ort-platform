"use client";

import React, { useEffect, useMemo, useState, useSyncExternalStore } from "react";
import Link from "next/link";
import { CheckCircle2, ChevronRight, Circle } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { useLmsMe } from "@/lib/lms/useLmsMe";
import { useAuth } from "@/lib/auth-context";
import { getExamPrep, type ExamPrepOut } from "@/lib/lms/examPrep";
import { listPractice } from "@/lib/lms/practice";
import { usePwa } from "@/components/pwa/PwaProvider";
import { Sheet } from "@/components/ui/Sheet";
import { cn, focusRing } from "@/components/ui/utils";
import { useStudentShellDataContext } from "./StudentShellDataContext";

/*
 * Student UI U8 (STUDENT_UI_DESIGN §3.6): "Начало работы", a client-side checklist of the current exam course from data
 * that already exists: a target score is set (exam-prep page), a test has a result (exam-prep page), a practice set was
 * started (practice list, only when the course has practice), the app is installed (PWA; only where the browser can
 * install it or already did). Shown as a sidebar pill with a sheet and a small home card; gone once every item is done.
 * One store per tab, so the pill and the home card share one answer; the home seeds it from the page it already loaded.
 * Data items that are done are remembered on this device (no more requests); the install item is always read live.
 */

export type GettingStartedKey = "goal" | "test" | "practice" | "install";
export interface GettingStartedItem { key: GettingStartedKey; done: boolean; href: string | null }
export interface GettingStartedState {
  /** False until every applicable item is known (nothing is drawn before). */
  ready: boolean;
  items: GettingStartedItem[];
  done: number;
  total: number;
  complete: boolean;
}

interface Facts { goal: boolean | null; test: boolean | null; practice: boolean | null; prepAt: number; practiceAt: number }

const STALE_MS = 30_000;
const EMPTY: Facts = { goal: null, test: null, practice: null, prepAt: 0, practiceAt: 0 };
const store = new Map<string, Facts>();
const listeners = new Set<() => void>();
const busy = new Set<string>();

function emit() { listeners.forEach((l) => l()); }
function subscribe(l: () => void) { listeners.add(l); return () => { listeners.delete(l); }; }
function patch(courseId: string, p: Partial<Facts>) {
  store.set(courseId, { ...(store.get(courseId) ?? EMPTY), ...p });
  emit();
}

const doneKey = (userId: string, courseId: string) => `ort_getting_started:${userId}:${courseId}`;
function readDone(userId: string, courseId: string): boolean {
  try { return window.localStorage.getItem(doneKey(userId, courseId)) === "1"; } catch { return false; }
}
function writeDone(userId: string, courseId: string) {
  try { window.localStorage.setItem(doneKey(userId, courseId), "1"); } catch { /* the checklist is asked again */ }
}

/** The home already loaded the exam-prep page: its goal and results feed the checklist without another request. */
export function noteExamPrep(courseId: string, prep: ExamPrepOut) {
  patch(courseId, { goal: prep.goal.target_score !== null, test: !!prep.latest || prep.history.length > 0, prepAt: Date.now() });
}

async function loadPrep(courseId: string) {
  const key = `prep:${courseId}`;
  if (busy.has(key)) return;
  busy.add(key);
  try { noteExamPrep(courseId, await getExamPrep(courseId)); } catch { /* the pill waits for the next page */ } finally { busy.delete(key); }
}

async function loadPractice(courseId: string) {
  const key = `practice:${courseId}`;
  if (busy.has(key)) return;
  busy.add(key);
  try {
    const page = await listPractice(courseId, { limit: 25 });
    patch(courseId, { practice: page.items.some((s) => (s.my_attempts ?? 0) > 0), practiceAt: Date.now() });
  } catch { /* as above */ } finally { busy.delete(key); }
}

/**
 * `courseId`: the shell's current exam course; `practice`: whether it has practice (null: not known yet); `pathKey`
 * changes on every navigation (stale facts are read again then); `seeded`: the page seeds the exam-prep facts itself.
 */
export function useGettingStarted({ courseId, practice, pathKey, enabled, seeded = false }: {
  courseId: string | null; practice: boolean | null; pathKey: string; enabled: boolean; seeded?: boolean;
}): GettingStartedState {
  const { lang } = useTranslation();
  const { me } = useLmsMe();
  const pwa = usePwa();
  const userId = me?.id ?? null;
  const facts = useSyncExternalStore(subscribe, () => (courseId ? store.get(courseId) ?? EMPTY : EMPTY), () => EMPTY);
  // the shell renders only on the client (after sign-in), so reading the device's memory here is safe
  const [marked, setMarked] = useState<string | null>(null);
  const rememberedHere = useMemo(() => !!userId && !!courseId && typeof window !== "undefined" && readDone(userId, courseId), [userId, courseId]);
  const remembered = rememberedHere || (!!courseId && marked === courseId);

  const active = enabled && !!courseId && !!userId && !remembered;
  useEffect(() => {
    if (!active || !courseId) return;
    const now = Date.now();
    const f = store.get(courseId) ?? EMPTY;
    if (!seeded && now - f.prepAt > STALE_MS) void loadPrep(courseId);
    if (practice && now - f.practiceAt > STALE_MS) void loadPractice(courseId);
  }, [active, courseId, practice, pathKey, seeded]);

  const dataDone = remembered || (facts.goal === true && facts.test === true && (practice === false || facts.practice === true));
  useEffect(() => {
    if (enabled && userId && courseId && !remembered && dataDone) {
      writeDone(userId, courseId);
      setMarked(courseId);
    }
  }, [enabled, userId, courseId, remembered, dataDone]);

  const base = `/${lang}/courses`;
  const items: GettingStartedItem[] = [];
  if (courseId) {
    items.push({ key: "goal", done: remembered || facts.goal === true, href: `${base}#home-score` }); // the home's score tiles
    items.push({ key: "test", done: remembered || facts.test === true, href: `${base}/${courseId}/tests` });
    if (practice) items.push({ key: "practice", done: remembered || facts.practice === true, href: `${base}/${courseId}/practice` });
    if (pwa.installed || pwa.installKind) items.push({ key: "install", done: pwa.installed, href: null });
  }
  const ready = !!courseId && !!userId && practice !== null
    && (remembered || (facts.goal !== null && facts.test !== null && (!practice || facts.practice !== null)));
  const done = items.filter((i) => i.done).length;
  return { ready, items, done, total: items.length, complete: ready && done === items.length };
}

/** A small progress ring (decoration; the text says "2/4"). */
export function ProgressRing({ done, total, className }: { done: number; total: number; className?: string }) {
  const r = 8;
  const c = 2 * Math.PI * r;
  const part = total > 0 ? done / total : 0;
  return (
    <svg viewBox="0 0 20 20" aria-hidden="true" className={cn("h-5 w-5", className)}>
      <circle cx="10" cy="10" r={r} fill="none" stroke="currentColor" strokeOpacity="0.3" strokeWidth="2.5" />
      {part > 0 && (
        <circle cx="10" cy="10" r={r} fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"
          strokeDasharray={`${c * part} ${c}`} transform="rotate(-90 10 10)" />
      )}
    </svg>
  );
}

/** The items as a list: a done item is a check and its label; an open one is a link (or the install button). */
export function GettingStartedList({ state, onNavigate, compact = false }: { state: GettingStartedState; onNavigate?: () => void; compact?: boolean }) {
  const { t } = useTranslation();
  const pwa = usePwa();
  return (
    <ol className={cn(compact ? "grid gap-2 sm:grid-cols-2" : "space-y-1")}>
      {state.items.map((it) => {
        const label = t(`student.gettingStarted.items.${it.key}`);
        const icon = it.done
          ? <CheckCircle2 aria-hidden="true" className="h-5 w-5 shrink-0 text-success-700" />
          : <Circle aria-hidden="true" className="h-5 w-5 shrink-0 text-slate-400" />;
        const status = <span className="sr-only">{t(it.done ? "student.gettingStarted.done" : "student.gettingStarted.todo")}: </span>;
        const row = "flex min-h-11 w-full items-center gap-3 rounded-control px-3 text-left text-sm leading-5";
        if (it.done) {
          return (
            <li key={it.key} className={cn(row, "text-slate-600")}>
              {icon}<span className="min-w-0 flex-1 break-words line-through decoration-slate-400">{status}{label}</span>
            </li>
          );
        }
        const body = <>{icon}<span className="min-w-0 flex-1 break-words font-semibold">{status}{label}</span><ChevronRight aria-hidden="true" className="h-4 w-4 shrink-0 text-slate-400" /></>;
        const live = cn(row, "border border-slate-200 bg-white text-slate-900 hover:border-brand-300 hover:bg-brand-50", focusRing, "focus-visible:ring-offset-0");
        return (
          <li key={it.key}>
            {it.href ? (
              <Link href={it.href} onClick={onNavigate} className={live}>{body}</Link>
            ) : (
              <button type="button" onClick={() => { onNavigate?.(); pwa.install(); }} className={live}>{body}</button>
            )}
          </li>
        );
      })}
    </ol>
  );
}

/** The sheet opened by the sidebar pill (desktop) or from "More" (phone). */
export function GettingStartedSheet({ state, open, onClose, id }: { state: GettingStartedState; open: boolean; onClose: () => void; id?: string }) {
  const { t } = useTranslation();
  return (
    <Sheet id={id} open={open} onClose={onClose} title={t("student.nav.gettingStarted")}>
      <div className="space-y-3 px-3 pb-2">
        <div className="flex items-center gap-3">
          <ProgressRing done={state.done} total={state.total} className="h-8 w-8 text-brand-600" />
          <div className="min-w-0 flex-1 text-sm leading-5">
            <p className="font-semibold text-slate-900">{t("student.gettingStarted.progress", { done: state.done, total: state.total })}</p>
            <p className="text-slate-700">{t("student.gettingStarted.intro")}</p>
          </div>
        </div>
        <GettingStartedList state={state} onNavigate={onClose} />
      </div>
    </Sheet>
  );
}

/** Home (§3.6): a small card until every item is done; nothing afterwards. Seeds the store from the loaded page. */
export function GettingStartedCard({ courseId, prep, className }: { courseId: string; prep: ExamPrepOut; className?: string }) {
  const { t } = useTranslation();
  const shell = useStudentShellDataContext();
  const { userProfile } = useAuth();
  // only inside the student frame, for its current exam course (the test student never sees it)
  const mine = !!shell && shell.current?.id === courseId && !userProfile?.is_test_student;
  const practice = mine && shell ? shell.features?.practice ?? null : null;
  useEffect(() => { noteExamPrep(courseId, prep); }, [courseId, prep]);
  const state = useGettingStarted({ courseId, practice, pathKey: "home", enabled: mine, seeded: true });
  if (!mine || !state.ready || state.complete) return null;
  return (
    <section aria-labelledby="home-getting-started" className={cn("min-w-0 rounded-card border border-slate-200 bg-white p-4 sm:p-5", className)}>
      <div className="mb-3 flex items-center gap-3">
        <ProgressRing done={state.done} total={state.total} className="h-7 w-7 shrink-0 text-brand-600" />
        <h2 id="home-getting-started" className="min-w-0 flex-1 break-words text-lg font-semibold leading-7 text-slate-900">
          {t("student.nav.gettingStarted")}
        </h2>
        <span className="shrink-0 text-sm font-semibold tabular-nums text-slate-600">
          {t("student.gettingStarted.progress", { done: state.done, total: state.total })}
        </span>
      </div>
      <GettingStartedList state={state} compact />
    </section>
  );
}
