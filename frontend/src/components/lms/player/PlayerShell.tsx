"use client";

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ChevronLeft, ChevronRight, Eye, LayoutGrid, TriangleAlert } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { useLmsMe } from "@/lib/lms/useLmsMe";
import { ErrorMessage } from "@/components/lms/ErrorMessage";
import { Button, Dialog, LoadingState, Skeleton, SkeletonText, cn, focusRing } from "@/components/ui";
import { pickLocalized } from "@/lib/lms/localized";
import {
  closeSection, getAttempt, getAttemptContent, saveAnswers, saveAnswersKeepalive, submitAttempt,
} from "@/lib/lms/attempts";
import type { AttemptContent, AttemptItemState, AttemptState, SubmitOut } from "@/lib/lms/attemptTypes";
import type { Lang, LocalizedText } from "@/lib/lms/types";
import { getAssessment } from "@/lib/lms/assessments";

/** Section title/instructions: plain string, or LocalizedText resolved to the attempt language. */
function sectionText(v: string | LocalizedText | null | undefined, lang: Lang): string {
  if (!v) return "";
  return typeof v === "string" ? v : pickLocalized(v, lang);
}
import {
  AutosaveQueue, LAST_MINUTE_MS, ServerClock, browserQueueEnv, classifyCloseFailure, classifyFailure, backoffMs,
  effectiveDeadlineMs, timeUpSubmitDelayMs, unsavedParam, watchOtherTabs, type QueueSnapshot,
} from "@/lib/lms/attemptClient";
import { DeadlineTimer } from "./DeadlineTimer";
import { ItemView } from "./ItemView";
import { PassagePane, PassageToggle } from "./PassagePane";
import { Palette, type PaletteGroup } from "./Palette";
import { SaveStatus } from "./SaveStatus";
import { ClosedDialog, SectionEndDialog, SubmitDialog, TimeUpDialog } from "./PlayerDialogs";
import { isAnswered, isTypingTarget, itemPassage, itemQuestion, mergeContent, type ResponseObj } from "./playerUtils";
import { ScrollingItems, type ScrollRequest } from "./ScrollingItems"; // Phase 8b S3
import { useReturnPath, withReturn } from "./returnPath"; // Phase 8b S3

type LocalAnswer = { response: ResponseObj; flagged: boolean };
const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));

export function PlayerShell({ courseId, attemptId }: { courseId: string; attemptId: string }) {
  const { lang, t } = useTranslation();
  const router = useRouter();

  const clock = useRef(new ServerClock()).current;
  const queueRef = useRef<AutosaveQueue | null>(null);
  const stateRef = useRef<AttemptState | null>(null);
  const busyRef = useRef({ sectionTimeout: false, timeUp: false });

  const [state, setState] = useState<AttemptState | null>(null);
  const [content, setContent] = useState<AttemptContent | null>(null);
  const [loadError, setLoadError] = useState<unknown>(null);
  const [answers, setAnswers] = useState<Record<number, LocalAnswer>>({});
  const answersRef = useRef<Record<number, LocalAnswer>>({});
  const [currentPos, setCurrentPos] = useState<number>(0);
  const [snap, setSnap] = useState<QueueSnapshot>({ status: "idle", pending: 0, lastError: null });
  const [dialog, setDialog] = useState<"section" | "submit" | null>(null);
  const [dialogBusy, setDialogBusy] = useState(false);
  const [dialogError, setDialogError] = useState<unknown>(null);
  const [timeUp, setTimeUp] = useState(false);
  const [timeUpError, setTimeUpError] = useState<unknown>(null);
  const [closedInfo, setClosedInfo] = useState<{ finished: boolean } | null>(null);
  const [rejected, setRejected] = useState<number[]>([]);
  const [otherTab, setOtherTab] = useState(false);
  // Forward-only: content arrives one section at a time (state.content_url names the current section).
  const loadedUrlsRef = useRef<Set<string>>(new Set());
  const [sectionLoading, setSectionLoading] = useState(false);
  const [sectionError, setSectionError] = useState<unknown>(null);
  const [sectionRetry, setSectionRetry] = useState(0);
  // Phone / tablet (S7b, P1): the palette opens as a sheet from the header instead of sitting below the question.
  const [paletteOpen, setPaletteOpen] = useState(false);
  const paletteCurrentRef = useRef<HTMLButtonElement>(null);
  const paletteButtonRef = useRef<HTMLButtonElement>(null);
  // Phone / tablet (S7b, P6): the reading text folds away under a sticky bar; open by default, per passage.
  const [passageClosed, setPassageClosed] = useState<Record<string, boolean>>({});
  const headerRef = useRef<HTMLElement>(null);
  const [headerH, setHeaderH] = useState(0);
  const passageRef = useRef<HTMLElement>(null);
  const questionAreaRef = useRef<HTMLDivElement>(null);
  // --- Phase 8b S3 begin --- (PHASE_8B_DESIGN 8.1, 7.2): scrolling display mode and the `?return=` link
  const scrollRootRef = useRef<HTMLDivElement>(null);
  const [scrollReq, setScrollReq] = useState<ScrollRequest | null>(null);
  const returnPath = useReturnPath(lang);
  const returnRef = useRef<string | null>(null);
  returnRef.current = returnPath;
  // --- Phase 8b S3 end ---

  const { me } = useLmsMe();
  const meIdRef = useRef<string | null>(null);
  meIdRef.current = me?.id ?? null;
  answersRef.current = answers;
  const resultHref = `/${lang}/courses/${courseId}/attempts/${attemptId}/result`;
  /** To the result page; body answers the server did not store (B2) ride along as `?unsaved=` for the notice. */
  const goResult = useCallback((out?: SubmitOut | null) => {
    const unsaved = unsavedParam(out?.rejected);
    const href = withReturn(resultHref, returnRef.current); // Phase 8b S3: no `return` (ORT, courses) = unchanged
    router.replace(unsaved ? `${href}${href.includes("?") ? "&" : "?"}unsaved=${encodeURIComponent(unsaved)}` : href);
  }, [router, resultHref]);

  /** Run a request and feed the clock estimator with its `server_now`. */
  const timed = useCallback(async <T extends { server_now?: string }>(fn: () => Promise<T>): Promise<T> => {
    const sent = Date.now();
    const res = await fn();
    clock.sample(res?.server_now, sent, Date.now());
    return res;
  }, [clock]);

  const firstPositionOf = (s: AttemptState): number => {
    const items = s.navigation === "section_forward_only" ? s.items.filter((i) => i.section_pos === s.current_section_pos) : s.items;
    return (items[0] ?? s.items[0])?.position ?? 0;
  };

  const applyState = useCallback((s: AttemptState, opts: { resetPos?: boolean } = {}) => {
    if (s.status !== "in_progress") {
      queueRef.current?.dispose();
      goResult();
      return;
    }
    const prev = stateRef.current;
    stateRef.current = s;
    setState(s);
    if (opts.resetPos || !prev || prev.current_section_pos !== s.current_section_pos) setCurrentPos(firstPositionOf(s));
  }, [goResult]);

  // ---- load ----
  const load = useCallback(async () => {
    setLoadError(null);
    try {
      const s = await timed(() => getAttempt(attemptId));
      if (s.status !== "in_progress") {
        goResult();
        return;
      }
      const c = await getAttemptContent(s);
      loadedUrlsRef.current = new Set([s.content_url]);
      setSectionError(null);
      setSectionLoading(false);
      const local: Record<number, LocalAnswer> = {};
      for (const it of s.items) local[it.position] = { response: it.response, flagged: it.flagged };

      queueRef.current?.dispose();
      const q = new AutosaveQueue(
        attemptId,
        browserQueueEnv(
          async (batch) => {
            const sent = Date.now();
            const out = await saveAnswers(attemptId, batch);
            clock.sample(out.server_now, sent, Date.now());
            return out;
          },
          (batch) => { void saveAnswersKeepalive(attemptId, batch); },
        ),
        {
          onChange: setSnap,
          onRejected: (positions) => setRejected((prev) => Array.from(new Set([...prev, ...positions]))),
          onServerState: (out) => {
            const cur = stateRef.current;
            if (cur && (out.status !== "in_progress" || out.current_section_pos !== cur.current_section_pos)) void refresh();
          },
          onClosed: () => { void refresh(true); },
        },
        meIdRef.current,
      );
      // Entries that survived a reload are newer than the server copy.
      for (const e of q.peek(1_000_000)) {
        const prev = local[e.position] ?? { response: null, flagged: false };
        local[e.position] = {
          response: e.response !== undefined ? e.response : prev.response,
          flagged: e.flagged !== undefined ? e.flagged : prev.flagged,
        };
      }
      queueRef.current = q;
      setAnswers(local);
      setContent(c);
      stateRef.current = s;
      setState(s);
      setCurrentPos(firstPositionOf(s));
      q.kick();
    } catch (e) {
      setLoadError(e);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [attemptId, goResult, timed, clock]);

  /** Reload attempt state after a server-side change (closed section, expiry, another tab). */
  const refresh = useCallback(async (announce = false) => {
    try {
      const s = await timed(() => getAttempt(attemptId));
      const before = stateRef.current;
      if (s.status !== "in_progress") {
        if (announce) setClosedInfo({ finished: true });
        else goResult();
        return;
      }
      applyState(s);
      if (announce && before && before.current_section_pos !== s.current_section_pos) setClosedInfo({ finished: false });
    } catch (e) {
      const info = classifyFailure(e);
      if (info.kind === "closed") setClosedInfo({ finished: true });
    }
  }, [attemptId, applyState, goResult, timed]);

  useEffect(() => {
    void load();
    return () => {
      queueRef.current?.dispose();
    };
  }, [load]);

  // ---- browser events ----
  useEffect(() => {
    const onOnline = () => queueRef.current?.retryNow();
    const onVis = () => {
      if (document.visibilityState === "hidden") queueRef.current?.onHidden();
      else if (queueRef.current?.pending) queueRef.current.retryNow();
    };
    const onUnload = (e: BeforeUnloadEvent) => {
      if (queueRef.current?.pending) {
        e.preventDefault();
        e.returnValue = "";
      }
    };
    window.addEventListener("online", onOnline);
    document.addEventListener("visibilitychange", onVis);
    window.addEventListener("pagehide", onVis);
    window.addEventListener("beforeunload", onUnload);
    const stopWatch = watchOtherTabs(attemptId, () => setOtherTab(true));
    return () => {
      window.removeEventListener("online", onOnline);
      document.removeEventListener("visibilitychange", onVis);
      window.removeEventListener("pagehide", onVis);
      window.removeEventListener("beforeunload", onUnload);
      stopWatch();
    };
  }, [attemptId]);

  // Forward-only: after the section advances (close, lazy advance, another tab) fetch the new section's content.
  // Free navigation keeps one content_url, so this never refetches.
  const contentUrl = state?.content_url;
  useEffect(() => {
    if (!contentUrl || loadedUrlsRef.current.has(contentUrl)) return;
    const ctrl = new AbortController();
    setSectionLoading(true);
    setSectionError(null);
    getAttemptContent({ content_url: contentUrl }, ctrl.signal)
      .then((c) => {
        loadedUrlsRef.current.add(contentUrl);
        setContent((prev) => mergeContent(prev, c));
        setSectionLoading(false);
      })
      .catch((e) => {
        if (ctrl.signal.aborted) return;
        setSectionError(e);
        setSectionLoading(false);
      });
    return () => ctrl.abort();
  }, [contentUrl, sectionRetry]);

  // Preload images named by the payload (lobby may already have warmed the HTTP cache).
  useEffect(() => {
    if (!content) return;
    const urls = content.image_urls.slice(0, 300);
    const id = setTimeout(() => {
      for (const u of urls) {
        const img = new Image();
        img.decoding = "async";
        img.src = u;
      }
    }, 300);
    return () => clearTimeout(id);
  }, [content]);

  // ---- derived ----
  const forwardOnly = state?.navigation === "section_forward_only";
  const sortedItems = useMemo(() => (state ? [...state.items].sort((a, b) => a.position - b.position) : []), [state]);
  const visibleItems = useMemo(
    () => (forwardOnly && state ? sortedItems.filter((i) => i.section_pos === state.current_section_pos) : sortedItems),
    [sortedItems, forwardOnly, state],
  );

  // Phase 7c UX: a quiz with one untitled, unkeyed section (the hidden default section of the quiz editor) shows the
  // quiz title instead of "Section 1". Only that case fetches the title; timed, keyed sections (ORT) are unchanged.
  const hiddenSection = !!content && content.sections.length === 1 && !sectionText(content.sections[0].title, content.language ?? lang)
    && !content.sections[0].key;
  const [quizTitle, setQuizTitle] = useState<string | null>(null);
  const assessmentId = state?.assessment_id;
  useEffect(() => {
    if (!hiddenSection || !assessmentId) return;
    let alive = true;
    getAssessment(courseId, assessmentId)
      .then((a) => { if (alive) setQuizTitle(pickLocalized(a.title, content?.language ?? lang) || t("assessments.untitled")); })
      .catch(() => { if (alive) setQuizTitle(t("assessments.untitled")); });
    return () => { alive = false; };
  }, [hiddenSection, assessmentId, courseId]); // eslint-disable-line react-hooks/exhaustive-deps

  const sectionTitle = useCallback((pos: number): string => {
    if (hiddenSection) return quizTitle ?? "";
    const s = content?.sections.find((x) => x.pos === pos);
    const title = sectionText(s?.title, content?.language ?? lang);
    if (title) return title;
    if (s?.key) {
      const label = t(`sections.${s.key}`);
      if (label !== `sections.${s.key}`) return label;
    }
    return `${t("player.section")} ${pos}`;
  }, [content, lang, t, hiddenSection, quizTitle]);

  const answeredOf = useCallback((it: AttemptItemState): boolean => {
    if (!state || !content) return false;
    return isAnswered(itemQuestion(state, content, it)?.type, answers[it.position]?.response);
  }, [state, content, answers]);

  const counts = useMemo(() => {
    let unanswered = 0;
    let flagged = 0;
    for (const it of visibleItems) {
      if (!answeredOf(it)) unanswered++;
      if (answers[it.position]?.flagged) flagged++;
    }
    return { unanswered, flagged, answered: visibleItems.length - unanswered };
  }, [visibleItems, answers, answeredOf]);

  const totalCounts = useMemo(() => {
    let unanswered = 0;
    let flagged = 0;
    for (const it of sortedItems) {
      if (!answeredOf(it)) unanswered++;
      if (answers[it.position]?.flagged) flagged++;
    }
    return { unanswered, flagged };
  }, [sortedItems, answers, answeredOf]);

  const lastSectionPos = state ? Math.max(...state.sections.map((s) => s.pos), 0) : 0;
  const isLastSection = !forwardOnly || (state ? state.current_section_pos >= lastSectionPos : true);

  const paletteGroups: PaletteGroup[] = useMemo(() => {
    const groups = new Map<number, PaletteGroup>();
    for (const it of visibleItems) {
      let g = groups.get(it.section_pos);
      if (!g) {
        g = { sectionPos: it.section_pos, title: sectionTitle(it.section_pos), entries: [] };
        groups.set(it.section_pos, g);
      }
      g.entries.push({
        position: it.position,
        label: g.entries.length + 1,
        answered: answeredOf(it),
        flagged: !!answers[it.position]?.flagged,
        sectionPos: it.section_pos,
      });
    }
    return Array.from(groups.values());
  }, [visibleItems, answers, answeredOf, sectionTitle]);

  const curIndex = Math.max(0, visibleItems.findIndex((i) => i.position === currentPos));
  const curItem: AttemptItemState | undefined = visibleItems[curIndex];

  // ---- actions ----
  const onAnswer = useCallback((position: number, response: ResponseObj) => {
    setAnswers((prev) => ({ ...prev, [position]: { response, flagged: prev[position]?.flagged ?? false } }));
    queueRef.current?.set(position, { response });
  }, []);

  const onToggleFlag = useCallback((position: number) => {
    const cur = answersRef.current[position] ?? { response: null, flagged: false };
    const flagged = !cur.flagged;
    queueRef.current?.set(position, { flagged });
    setAnswers((prev) => ({ ...prev, [position]: { response: prev[position]?.response ?? null, flagged } }));
  }, []);

  // --- Phase 8b S3 begin --- scrolling mode: moving = scroll to the item and focus it (ScrollingItems), same position
  const scrolling = state?.display_mode === "scrolling";
  const scrollToItem = useCallback((position: number) => {
    setCurrentPos(position);
    setScrollReq((r) => ({ pos: position, n: (r?.n ?? 0) + 1 }));
  }, []);
  // --- Phase 8b S3 end ---

  const go = useCallback((delta: number) => {
    const next = visibleItems[Math.min(visibleItems.length - 1, Math.max(0, curIndex + delta))];
    if (next) {
      if (scrolling) scrollToItem(next.position); // Phase 8b S3
      else setCurrentPos(next.position);
    }
  }, [visibleItems, curIndex, scrolling, scrollToItem]);

  /** Time-up (or forced) submit: random 0-15 s spread, flush, submit with leftovers, retry until success. */
  const runTimeUpSubmit = useCallback(async () => {
    if (busyRef.current.timeUp) return;
    busyRef.current.timeUp = true;
    setTimeUp(true);
    setTimeUpError(null);
    const q = queueRef.current;
    const graceS = stateRef.current?.grace_s ?? 45;
    if (q) q.setContinuous(false);
    await sleep(timeUpSubmitDelayMs(Math.random, graceS));
    const giveUpAt = Date.now() + (graceS + 60) * 1000;
    for (let attempt = 0; ; attempt++) {
      try {
        await q?.flushNow();
        const out = await submitAttempt(attemptId, { answers: q?.peek(20) ?? [] });
        q?.clear();
        goResult(out);
        return;
      } catch (e) {
        const info = classifyFailure(e);
        if (info.kind === "closed") {
          q?.clear();
          goResult();
          return;
        }
        if (Date.now() > giveUpAt) {
          setTimeUpError(e);
          busyRef.current.timeUp = false;
          return;
        }
        await sleep(backoffMs(attempt));
      }
    }
  }, [attemptId, goResult]);

  /** Section timer reached zero (forward-only, not the last section): flush, then close; server may be ahead. */
  const runSectionTimeout = useCallback(async () => {
    const s = stateRef.current;
    if (!s || busyRef.current.sectionTimeout) return;
    busyRef.current.sectionTimeout = true;
    try {
      await queueRef.current?.flushNow();
      for (let i = 0; i < 6; i++) {
        try {
          const next = await timed(() => closeSection(attemptId, s.current_section_pos));
          applyState(next, { resetPos: true });
          return;
        } catch (e) {
          const failure = classifyCloseFailure(e);
          if (failure === "use_submit") {
            busyRef.current.sectionTimeout = false;
            void runTimeUpSubmit();
            return;
          }
          if (failure === "not_current" || failure === "closed") {
            await refresh();
            return;
          }
          await sleep(2000);
        }
      }
      await refresh();
    } finally {
      busyRef.current.sectionTimeout = false;
    }
  }, [attemptId, applyState, refresh, runTimeUpSubmit, timed]);

  const onTimerExpire = useCallback(() => {
    const s = stateRef.current;
    if (!s) return;
    const last = s.navigation !== "section_forward_only" || s.current_section_pos >= Math.max(...s.sections.map((x) => x.pos), 0);
    const attemptDone = s.deadline_at !== null && Date.parse(s.deadline_at) - clock.now() <= 0;
    if (last || attemptDone) void runTimeUpSubmit();
    else void runSectionTimeout();
  }, [clock, runSectionTimeout, runTimeUpSubmit]);

  const confirmSectionEnd = async () => {
    const s = stateRef.current;
    if (!s) return;
    setDialogBusy(true);
    setDialogError(null);
    try {
      const flushed = await queueRef.current?.flushNow();
      if (flushed === false) {
        setDialogError({ code: "network" });
        return;
      }
      const next = await timed(() => closeSection(attemptId, s.current_section_pos));
      setDialog(null);
      applyState(next, { resetPos: true });
    } catch (e) {
      const failure = classifyCloseFailure(e);
      if (failure === "use_submit") {
        setDialog("submit");
      } else if (failure === "not_current" || failure === "closed") {
        setDialog(null);
        await refresh(true);
      } else {
        setDialogError(e);
      }
    } finally {
      setDialogBusy(false);
    }
  };

  const confirmSubmit = async () => {
    setDialogBusy(true);
    setDialogError(null);
    try {
      const q = queueRef.current;
      const flushed = await q?.flushNow();
      if (flushed === false && (q?.pending ?? 0) > 20) {
        setDialogError({ code: "network" });
        return;
      }
      const out = await submitAttempt(attemptId, { answers: q?.peek(20) ?? [] });
      q?.clear();
      goResult(out);
    } catch (e) {
      const info = classifyFailure(e);
      if (info.kind === "closed") {
        queueRef.current?.clear();
        goResult();
      } else {
        setDialogError(e);
      }
    } finally {
      setDialogBusy(false);
    }
  };

  const finishPressed = () => {
    setDialogError(null);
    setDialog(forwardOnly && !isLastSection ? "section" : "submit");
  };

  // ---- keyboard shortcuts: arrows move, F flags, 1-5 / A-E pick a choice ----
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (dialog || paletteOpen || timeUp || closedInfo || e.ctrlKey || e.metaKey || e.altKey) return;
      if (isTypingTarget(e.target) || !state || !content || !curItem) return;
      const k = e.key;
      if (k === "ArrowRight") { e.preventDefault(); go(1); return; }
      if (k === "ArrowLeft") { e.preventDefault(); go(-1); return; }
      // S7b, P9: physical keys (`e.code`), so F, A-E and 1-5 also work with a Russian or Kyrgyz layout.
      const code = e.code;
      if (code === "KeyF") { e.preventDefault(); onToggleFlag(curItem.position); return; }
      const q = itemQuestion(state, content, curItem);
      if (!q) return;
      const digit = e.shiftKey ? null : /^(?:Digit|Numpad)([1-5])$/.exec(code);
      const letterKey = /^Key([A-E])$/.exec(code);
      const idx = digit ? Number(digit[1]) - 1 : letterKey ? letterKey[1].charCodeAt(0) - 65 : -1;
      if (idx < 0) return;
      if (q.type === "comparison" && idx < 4) {
        onAnswer(curItem.position, { choice: "ABCD"[idx] });
      } else if (q.type === "single_choice") {
        const choices = (curItem.choice_order ?? (q.data.choices ?? []).map((c) => c.id));
        if (choices[idx]) onAnswer(curItem.position, { choice_id: choices[idx] });
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [dialog, paletteOpen, timeUp, closedInfo, state, content, curItem, go, onToggleFlag, onAnswer]);


  // Header height, for the sticky passage bar under it (the header wraps differently per language and width).
  const ready = !!state && !!content;
  useEffect(() => {
    const el = headerRef.current;
    if (!ready || !el) return;
    const measure = () => setHeaderH(el.getBoundingClientRect().height);
    measure();
    if (typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, [ready]);

  const selectFromSheet = useCallback((position: number) => {
    if (scrolling) scrollToItem(position); // Phase 8b S3
    else setCurrentPos(position);
    setPaletteOpen(false);
  }, [scrolling, scrollToItem]);

  // S11a, F5: the sheet's own button disappears with the sheet. Open the finish dialog one frame later, from the
  // header button, so the dialog's Cancel returns focus to a live element.
  const finishFromSheet = () => {
    setPaletteOpen(false);
    requestAnimationFrame(() => {
      paletteButtonRef.current?.focus();
      finishPressed();
    });
  };

  // ---- render ----
  if (loadError) {
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center overflow-y-auto bg-slate-50 p-4">
        <div className="w-full max-w-md space-y-4">
          <ErrorMessage error={loadError} onRetry={() => void load()} />
          <Link href={returnPath ?? `/${lang}/courses/${courseId}`} className="text-sm font-medium text-brand-700 hover:underline">
            {returnPath ? t("player.scrolling.back") : t("player.backToCourse")}
          </Link>
        </div>
      </div>
    );
  }
  if (!state || !content) {
    // S7b, P11: the player's own layout as a skeleton, never a blank page with a sentence.
    return (
      <LoadingState label={t("player.loading")} className="fixed inset-0 z-50 flex flex-col overflow-y-auto bg-slate-50">
        <div aria-hidden="true" className="border-b border-slate-200 bg-white">
          <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-4 py-2.5">
            <div className="w-48 space-y-2">
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-3 w-2/3" />
            </div>
            <Skeleton className="h-8 w-24 rounded-xl" />
          </div>
          <div className="h-1 w-full bg-slate-100" />
        </div>
        <div aria-hidden="true" className="mx-auto grid w-full max-w-6xl flex-1 grid-cols-1 gap-5 px-4 py-5 lg:grid-cols-[minmax(0,1fr)_17rem]">
          <QuestionSkeleton />
          <div className="hidden rounded-2xl border border-slate-200 bg-white p-4 lg:block">
            <Skeleton className="mb-3 h-4 w-24" />
            <div className="grid grid-cols-5 gap-2">
              {Array.from({ length: 10 }, (_, i) => <Skeleton key={i} className="h-10 rounded-xl" />)}
            </div>
          </div>
        </div>
      </LoadingState>
    );
  }

  const q = curItem ? itemQuestion(state, content, curItem) : undefined;
  const passage = curItem ? itemPassage(content, curItem, q) : null;
  const passageOpen = passage ? !passageClosed[passage.id] : false;
  const deadline = effectiveDeadlineMs(state);
  const curSection = content.sections.find((s) => s.pos === (curItem?.section_pos ?? state.current_section_pos));
  const curInstructions = sectionText(curSection?.instructions, content.language ?? lang);
  const lastInSection = curIndex >= visibleItems.length - 1;
  const progressPct = visibleItems.length ? Math.round((counts.answered / visibleItems.length) * 100) : 0;
  const finishLabel = forwardOnly && !isLastSection ? t("player.finishSection") : t("player.finishTest");
  const stickyTop = Math.round(headerH) + 8;

  const togglePassage = () => {
    if (!passage) return;
    const opening = !passageOpen;
    setPassageClosed((prev) => ({ ...prev, [passage.id]: !opening }));
    // Opening: show the text from its start; closing: back to the question. Both just under the sticky bar.
    requestAnimationFrame(() => {
      const target = opening ? passageRef.current : questionAreaRef.current;
      target?.scrollIntoView({ block: "start" });
    });
  };

  return (
    <div ref={scrollRootRef} className="fixed inset-0 z-50 flex flex-col overflow-y-auto bg-slate-50">
      <header ref={headerRef} className="sticky top-0 z-10 border-b border-slate-200 bg-white/95 backdrop-blur">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-x-3 gap-y-2 px-4 py-2.5">
          <div className="min-w-0 basis-full sm:basis-auto">
            <p className="truncate text-sm font-bold text-slate-900">{sectionTitle(curItem?.section_pos ?? state.current_section_pos)}</p>
            <p className="text-xs text-slate-600">
              {t("player.progress", { answered: counts.answered, total: visibleItems.length })}
              {forwardOnly ? ` · ${t("player.sectionOf", { n: state.current_section_pos, total: lastSectionPos })}` : ""}
            </p>
          </div>
          {/* S11a, F7: a problem state (offline, error) may take its own line on phones instead of squeezing to one word per line.
              Phase 8b UX: in scrolling mode the save pill is icon-only on phones and the row wraps rather than clipping
              it if it still does not fit; one-per-page (ORT) keeps its layout. */}
          <div className={cn(
            "flex min-w-0 flex-1 items-center justify-between gap-3 sm:flex-none sm:justify-end",
            (["offline", "error", "auth", "closed"].includes(snap.status) || deadline === null || scrolling) && "flex-wrap gap-y-2",
          )}>
            <SaveStatus snap={snap} onRetry={() => queueRef.current?.retryNow()} compact={scrolling} />
            <div className="ml-auto flex shrink-0 items-center gap-2">
              <DeadlineTimer deadlineMs={deadline} getNowMs={() => clock.now()} onExpire={onTimerExpire}
                label={forwardOnly ? t("player.timer.sectionLeft") : t("player.timer.left")}
                onTick={(rem) => queueRef.current?.setContinuous(rem <= LAST_MINUTE_MS)} />
              <button
                ref={paletteButtonRef}
                type="button"
                onClick={() => setPaletteOpen(true)}
                aria-haspopup="dialog"
                aria-expanded={paletteOpen}
                aria-label={t("player.palette.openLabel", { n: curIndex + 1, total: visibleItems.length })}
                className={cn(
                  "relative inline-flex min-h-11 items-center gap-1.5 rounded-xl border border-slate-300 bg-white px-3 text-sm font-semibold text-slate-800 shadow-sm hover:bg-slate-50 lg:hidden",
                  focusRing,
                )}
              >
                <LayoutGrid className="h-4 w-4" aria-hidden="true" />
                {t("player.palette.open", { n: curIndex + 1, total: visibleItems.length })}
                {counts.flagged > 0 ? (
                  <span aria-hidden="true" className="absolute -right-1 -top-1 h-2.5 w-2.5 rounded-full border border-white bg-amber-500" />
                ) : null}
              </button>
            </div>
          </div>
        </div>
        <div className="h-1 w-full bg-slate-100" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={progressPct} aria-label={t("player.progressBar")}>
          <div className="h-1 bg-brand-600 transition-all" style={{ width: `${progressPct}%` }} />
        </div>
      </header>

      {state.is_preview ? (
        <div className="flex items-center justify-center gap-2 bg-amber-100 px-4 py-2 text-sm font-medium text-amber-900">
          <Eye className="h-4 w-4 shrink-0" aria-hidden="true" />
          {t("player.previewBanner")}
        </div>
      ) : null}
      {otherTab ? (
        <div role="alert" className="flex items-center justify-center gap-2 bg-red-50 px-4 py-2 text-sm font-medium text-red-800">
          <TriangleAlert className="h-4 w-4 shrink-0" aria-hidden="true" />
          {t("player.otherTab")}
        </div>
      ) : null}
      {rejected.length > 0 ? (
        <div role="alert" className="flex flex-wrap items-center justify-center gap-2 bg-red-50 px-4 py-2 text-sm text-red-800">
          <TriangleAlert className="h-4 w-4 shrink-0" aria-hidden="true" />
          {t("player.rejected", { list: rejected.map((p) => p + 1).join(", ") })}
          <Button variant="link" size="sm" className="text-red-800" onClick={() => setRejected([])}>{t("player.dismiss")}</Button>
        </div>
      ) : null}

      <main className="mx-auto grid w-full max-w-6xl flex-1 grid-cols-1 gap-5 px-4 py-5 lg:grid-cols-[minmax(0,1fr)_17rem]">
        <div className="min-w-0 space-y-4">
          {/* --- Phase 8b S3 --- scrolling display mode (PHASE_8B_DESIGN 8.1); one-per-page (ORT) below is unchanged */}
          {scrolling ? (
            sectionError ? (
              <ErrorMessage error={sectionError} onRetry={() => setSectionRetry((n) => n + 1)} />
            ) : sectionLoading ? (
              <LoadingState label={t("player.loading")}><QuestionSkeleton /></LoadingState>
            ) : (
              <ScrollingItems state={state} content={content} visibleItems={visibleItems} currentPos={currentPos} answers={answers}
                onAnswer={onAnswer} onToggleFlag={onToggleFlag} onCurrentChange={setCurrentPos} onNavigate={scrollToItem}
                scrollRequest={scrollReq} scrollRootRef={scrollRootRef} headerHeight={headerH} stickyTop={stickyTop}
                passageDisplay={state.passage_display ?? null} instructions={curInstructions} sectionTitle={sectionTitle}
                forwardOnly={forwardOnly} finishLabel={finishLabel} onFinish={finishPressed} />
            )
          ) : (<>
          {curInstructions ? (
            <details className="rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm text-slate-700" open={curIndex === 0}>
              <summary className="cursor-pointer py-1 font-semibold text-slate-800">{t("player.instructions")}</summary>
              <p className="mt-2 whitespace-pre-line">{curInstructions}</p>
            </details>
          ) : null}

          {sectionError ? (
            <ErrorMessage error={sectionError} onRetry={() => setSectionRetry((n) => n + 1)} />
          ) : sectionLoading ? (
            <LoadingState label={t("player.loading")}><QuestionSkeleton /></LoadingState>
          ) : curItem && q ? (
            <>
              {passage ? (
                <PassageToggle passage={passage} open={passageOpen} controls={`passage-${passage.id}`} top={stickyTop} onToggle={togglePassage} />
              ) : null}
              <div ref={questionAreaRef} style={{ scrollMarginTop: stickyTop + 52 }} className={passage ? "grid grid-cols-1 gap-4 xl:grid-cols-2" : ""}>
                {passage ? (
                  <PassagePane ref={passageRef} id={`passage-${passage.id}`} passage={passage} open={passageOpen} scrollMarginTop={stickyTop + 52} display={state.passage_display} />
                ) : null}
                <ItemView
                  key={curItem.position}
                  question={q}
                  choiceOrder={curItem.choice_order}
                  number={curIndex + 1}
                  total={visibleItems.length}
                  response={answers[curItem.position]?.response ?? null}
                  flagged={!!answers[curItem.position]?.flagged}
                  onChange={(r) => onAnswer(curItem.position, r)}
                  onToggleFlag={() => onToggleFlag(curItem.position)}
                />
              </div>
            </>
          ) : (
            <p className="rounded-xl border border-slate-200 bg-white p-6 text-sm text-slate-600">{t("player.noQuestion")}</p>
          )}

          <div className="flex items-center justify-between gap-3">
            <Button variant="secondary" className="sm:min-h-10" onClick={() => go(-1)} disabled={curIndex <= 0} leftIcon={<ChevronLeft className="h-4 w-4" aria-hidden="true" />}>
              {t("player.prev")}
            </Button>
            {lastInSection ? (
              <Button className="sm:min-h-10" onClick={finishPressed}>{finishLabel}</Button>
            ) : (
              <Button className="sm:min-h-10" onClick={() => go(1)} rightIcon={<ChevronRight className="h-4 w-4" aria-hidden="true" />}>
                {t("player.next")}
              </Button>
            )}
          </div>
          <p className="hidden text-xs text-slate-500 lg:block">{t("player.shortcuts")}</p>
          </>)}
        </div>

        {/* Desktop: palette and the finish action beside the question. Phones and tablets use the sheet below. */}
        {/* Phase 8b S3: in scrolling mode the palette stays in view while the list scrolls (one-per-page: unchanged) */}
        <aside className={cn("hidden space-y-3 lg:block", scrolling && "lg:sticky lg:self-start")} style={scrolling ? { top: stickyTop } : undefined}>
          <Palette groups={paletteGroups} currentPosition={curItem?.position ?? -1} onSelect={scrolling ? scrollToItem : setCurrentPos} />
          <Button variant="secondary" fullWidth onClick={finishPressed} className="border-brand-600 text-brand-700 hover:bg-brand-50">
            {finishLabel}
          </Button>
        </aside>
      </main>

      <Dialog
        open={paletteOpen}
        onClose={() => setPaletteOpen(false)}
        title={t("player.palette.title")}
        description={t("player.progress", { answered: counts.answered, total: visibleItems.length })}
        initialFocusRef={paletteCurrentRef}
        className="mb-0 w-full max-w-none rounded-b-none sm:mb-auto sm:w-[calc(100%-2rem)] sm:max-w-md sm:rounded-b-2xl"
        // S11a, F4: the finish action stays pinned in the footer; only the palette scrolls.
        footer={(
          <Button variant="secondary" fullWidth onClick={finishFromSheet} className="border-brand-600 text-brand-700 hover:bg-brand-50 sm:flex-1">
            {finishLabel}
          </Button>
        )}
      >
        <aside>
          <Palette groups={paletteGroups} currentPosition={curItem?.position ?? -1} onSelect={selectFromSheet} hideTitle currentRef={paletteCurrentRef} />
        </aside>
      </Dialog>

      {dialog === "section" ? (
        <SectionEndDialog sectionTitle={sectionTitle(state.current_section_pos)} unanswered={counts.unanswered} flagged={counts.flagged}
          busy={dialogBusy} error={dialogError} onConfirm={() => void confirmSectionEnd()} onCancel={() => setDialog(null)} />
      ) : null}
      {dialog === "submit" ? (
        <SubmitDialog unanswered={forwardOnly ? counts.unanswered : totalCounts.unanswered} flagged={forwardOnly ? counts.flagged : totalCounts.flagged}
          busy={dialogBusy} error={dialogError} onConfirm={() => void confirmSubmit()} onCancel={() => setDialog(null)} />
      ) : null}
      {timeUp ? <TimeUpDialog error={timeUpError} onRetry={() => void runTimeUpSubmit()} /> : null}
      {closedInfo ? (
        <ClosedDialog finished={closedInfo.finished} onContinue={() => { if (closedInfo.finished) goResult(); else setClosedInfo(null); }} />
      ) : null}
    </div>
  );
}

/** A question card placeholder (first load and the per-section load). */
function QuestionSkeleton() {
  return (
    <div aria-hidden="true" className="space-y-5 rounded-2xl border border-slate-200 bg-white p-5 md:p-7">
      <div className="flex items-center justify-between border-b border-slate-100 pb-4">
        <Skeleton className="h-6 w-28" />
        <Skeleton className="h-9 w-24 rounded-xl" />
      </div>
      <SkeletonText lines={3} />
      <div className="space-y-2">
        {Array.from({ length: 4 }, (_, i) => <Skeleton key={i} className="h-12 rounded-xl" />)}
      </div>
    </div>
  );
}
