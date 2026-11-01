"use client";

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Eye, TriangleAlert } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { useLmsMe } from "@/lib/lms/useLmsMe";
import { ErrorMessage } from "@/components/lms/ErrorMessage";
import { Button, LoadingState, Skeleton, SkeletonText, cn } from "@/components/ui";
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
import type { PaletteGroup } from "./Palette";
import { PlayerTopBar, type BarPopup } from "./PlayerTopBar";
import { PlayerBottomBar } from "./PlayerBottomBar";
import { QuestionMap } from "./QuestionMap";
import { SectionReview } from "./SectionReview";
import { SplitPassage } from "./SplitPassage";
import { StudentViewBanner } from "@/components/lms/course/StudentViewBanner";
import { SaveStatus } from "./SaveStatus";
import { ClosedDialog, SectionEndDialog, SubmitDialog, TimeUpDialog } from "./PlayerDialogs";
import { isAnswered, isTypingTarget, itemPassage, itemQuestion, mergeContent, type ResponseObj } from "./playerUtils";
import { ScrollingItems, type ScrollRequest } from "./ScrollingItems"; // Phase 8b S3
import { useReturnPath, withReturn } from "./returnPath"; // Phase 8b S3
import { PracticeCheck, usePracticeFeedback } from "@/components/lms/practice/PracticeCheck"; // Phase 10 S3

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
  const practice = usePracticeFeedback(attemptId, !!state?.is_practice); // Phase 10 S3: inert unless a practice attempt
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
  // BLUEBOOK_PLAYER: the question map popup of the bottom bar, the top bar's popups, the review page. The review page
  // belongs to a section (its pos), so it closes by itself when the section advances (close, timer, another tab).
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [barPopup, setBarPopup] = useState<BarPopup>(null);
  const [reviewFor, setReviewFor] = useState<number | null>(null);
  const focusQuestionRef = useRef(false);
  const timerKey = `ort_player_timer_hidden:${attemptId}`;
  const [timerHidden, setTimerHidden] = useState<boolean>(() => {
    try {
      return typeof window !== "undefined" && window.sessionStorage.getItem(timerKey) === "1";
    } catch {
      return false;
    }
  });
  const paletteCurrentRef = useRef<HTMLButtonElement>(null);
  const paletteButtonRef = useRef<HTMLButtonElement>(null);
  // Below `lg` (S7b, P6): the reading text folds away under a sticky bar; open by default, per passage.
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
    if (practice.lockedRef.current[position]) return; // Phase 10 S3: a checked practice item is locked
    setAnswers((prev) => ({ ...prev, [position]: { response, flagged: prev[position]?.flagged ?? false } }));
    queueRef.current?.set(position, { response });
  }, [practice.lockedRef]);

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

  // ---- review page ----
  const reviewOpen = !!state && reviewFor === state.current_section_pos;
  const openReview = useCallback(() => {
    const s = stateRef.current;
    if (!s) return;
    setPaletteOpen(false);
    setReviewFor(s.current_section_pos);
  }, []);
  /** Back to a question from the review page: the current one, or the one the student picked. */
  const leaveReview = useCallback((position: number) => {
    setReviewFor(null);
    focusQuestionRef.current = true;
    if (scrolling) scrollToItem(position);
    else setCurrentPos(position);
  }, [scrolling, scrollToItem]);
  const closeReview = useCallback(() => leaveReview(currentPos), [leaveReview, currentPos]);

  // ---- keyboard shortcuts: arrows move, F flags, 1-5 / A-E pick a choice ----
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (dialog || paletteOpen || barPopup || timeUp || closedInfo || e.ctrlKey || e.metaKey || e.altKey) return;
      if (isTypingTarget(e.target) || !state || !content || !curItem) return;
      const k = e.key;
      // The review page shows no question: nothing to flag or answer here, the left arrow is its "Back".
      if (reviewOpen) {
        if (k === "ArrowLeft") { e.preventDefault(); closeReview(); }
        return;
      }
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
  }, [dialog, paletteOpen, barPopup, reviewOpen, closeReview, timeUp, closedInfo, state, content, curItem, go, onToggleFlag, onAnswer]);


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

  const selectFromMap = useCallback((position: number) => {
    setReviewFor(null);
    if (scrolling) scrollToItem(position); // Phase 8b S3
    else setCurrentPos(position);
    setPaletteOpen(false);
  }, [scrolling, scrollToItem]);

  const toggleTimer = useCallback(() => {
    setTimerHidden((hidden) => {
      try {
        window.sessionStorage.setItem(timerKey, hidden ? "0" : "1");
      } catch { /* storage unavailable: the choice lasts until a reload */ }
      return !hidden;
    });
  }, [timerKey]);

  // One question per page: another question starts at its top. Under the same text the text stays where it is (its own
  // pane from `lg`; below that the page goes to the question); a new text starts at its top.
  const shownRef = useRef<{ pos: number; passage: string | null } | null>(null);
  const curPosition = curItem?.position;
  // A section's content arrives after its first item is current: the id changes then, for the same position.
  const passageId = state && content && curItem ? itemPassage(content, curItem, itemQuestion(state, content, curItem))?.id ?? null : null;
  useEffect(() => {
    if (!curItem || scrolling || reviewOpen) return;
    const prev = shownRef.current;
    shownRef.current = { pos: curItem.position, passage: passageId };
    const area = questionAreaRef.current;
    if (focusQuestionRef.current) {
      focusQuestionRef.current = false;
      area?.focus({ preventScroll: true });
    }
    if (!prev || prev.pos === curItem.position) return;
    if (area) area.scrollTop = 0;
    const root = scrollRootRef.current;
    if (passageId && prev.passage === passageId) {
      const headerBottom = headerRef.current?.getBoundingClientRect().bottom ?? 0;
      if (area && area.getBoundingClientRect().top < headerBottom) area.scrollIntoView({ block: "start" });
    } else {
      if (passageRef.current) passageRef.current.scrollTop = 0;
      root?.scrollTo({ top: 0 });
    }
  }, [curPosition, passageId, scrolling, reviewOpen]); // eslint-disable-line react-hooks/exhaustive-deps

  // The review page starts at the top of the player.
  useEffect(() => {
    if (reviewOpen) scrollRootRef.current?.scrollTo({ top: 0 });
  }, [reviewOpen]);

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
        <div aria-hidden="true" className="grid grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] items-center gap-3 border-b border-slate-200 bg-white px-4 py-2.5 lg:px-8">
          <div className="max-w-48 space-y-2">
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-3 w-2/3" />
          </div>
          <Skeleton className="h-8 w-24 rounded-xl" />
          <Skeleton className="ml-auto h-8 w-10 rounded-xl" />
        </div>
        <div aria-hidden="true" className="w-full flex-1 px-4 py-5 lg:px-8">
          <div className="mx-auto w-full max-w-4xl"><QuestionSkeleton /></div>
        </div>
        <div aria-hidden="true" className="grid h-16 shrink-0 grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] items-center gap-2 border-t border-slate-200 bg-white px-4 lg:px-8">
          <span />
          <Skeleton className="h-11 w-36 rounded-xl" />
          <Skeleton className="ml-auto h-11 w-24 rounded-xl" />
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
  const sectionOf = forwardOnly ? t("player.sectionOf", { n: state.current_section_pos, total: lastSectionPos }) : null;
  const progressText = t("player.progress", { answered: counts.answered, total: visibleItems.length });
  const saveProblem = ["offline", "error", "auth", "closed"].includes(snap.status);
  const passageShown = !scrolling && !reviewOpen && !sectionError && !sectionLoading && !!passage && !!q;
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

  const questionBlock = (item: AttemptItemState, question: NonNullable<typeof q>) => (
    <>
      <ItemView
        key={item.position}
        question={question}
        choiceOrder={item.choice_order}
        number={curIndex + 1}
        total={visibleItems.length}
        response={answers[item.position]?.response ?? null}
        flagged={!!answers[item.position]?.flagged}
        disabled={state.is_practice ? !!practice.fb[item.position] : undefined}
        onChange={(r) => onAnswer(item.position, r)}
        onToggleFlag={() => onToggleFlag(item.position)}
      />
      {state.is_practice ? (
        <PracticeCheck
          key={`practice-${item.position}`}
          attemptId={attemptId}
          position={item.position}
          question={question}
          feedback={practice.fb[item.position]}
          answered={isAnswered(question.type, answers[item.position]?.response)}
          flush={async () => queueRef.current?.flushNow()}
          onChecked={practice.add}
        />
      ) : null}
    </>
  );

  return (
    <div ref={scrollRootRef} className="fixed inset-0 z-50 flex flex-col overflow-y-auto bg-slate-50">
      <StudentViewBanner />
      {state.is_preview ? (
        <div className="flex shrink-0 items-center justify-center gap-2 bg-amber-100 px-4 py-2 text-sm font-medium text-amber-900">
          <Eye className="h-4 w-4 shrink-0" aria-hidden="true" />
          {t("player.previewBanner")}
        </div>
      ) : null}

      <PlayerTopBar
        ref={headerRef}
        sectionTitle={sectionTitle(curItem?.section_pos ?? state.current_section_pos)}
        sectionOf={sectionOf}
        instructions={curInstructions}
        popup={barPopup}
        onPopup={setBarPopup}
        saveProblem={saveProblem}
        save={<SaveStatus snap={snap} onRetry={() => queueRef.current?.retryNow()} compact />}
        timer={(
          <DeadlineTimer deadlineMs={deadline} getNowMs={() => clock.now()} onExpire={onTimerExpire}
            label={forwardOnly ? t("player.timer.sectionLeft") : t("player.timer.left")}
            onTick={(rem) => queueRef.current?.setContinuous(rem <= LAST_MINUTE_MS)}
            hidden={timerHidden} onToggleHidden={toggleTimer} />
        )}
      />

      {otherTab ? (
        <div role="alert" className="flex shrink-0 items-center justify-center gap-2 bg-red-50 px-4 py-2 text-sm font-medium text-red-800">
          <TriangleAlert className="h-4 w-4 shrink-0" aria-hidden="true" />
          {t("player.otherTab")}
        </div>
      ) : null}
      {rejected.length > 0 ? (
        <div role="alert" className="flex shrink-0 flex-wrap items-center justify-center gap-2 bg-red-50 px-4 py-2 text-sm text-red-800">
          <TriangleAlert className="h-4 w-4 shrink-0" aria-hidden="true" />
          {t("player.rejected", { list: rejected.map((p) => p + 1).join(", ") })}
          <Button variant="link" size="sm" className="text-red-800" onClick={() => setRejected([])}>{t("player.dismiss")}</Button>
        </div>
      ) : null}

      <main className={cn("w-full flex-1 px-4 py-5 lg:px-8", passageShown && "lg:flex lg:min-h-0 lg:flex-col lg:overflow-hidden lg:p-0")}>
        {reviewOpen ? (
          <SectionReview groups={paletteGroups} currentPosition={curItem?.position ?? -1} summary={progressText} finishLabel={finishLabel}
            onJump={leaveReview} onFinish={finishPressed} />
        ) : null}
        {/* --- Phase 8b S3 --- scrolling display mode (PHASE_8B_DESIGN 8.1). The list stays mounted under the review
            page (hidden), so coming back finds it as it was. */}
        {scrolling ? (
          <div className={reviewOpen ? "hidden" : undefined}>
            {sectionError ? (
              <ErrorMessage error={sectionError} onRetry={() => setSectionRetry((n) => n + 1)} />
            ) : sectionLoading ? (
              <LoadingState label={t("player.loading")}><div className="mx-auto w-full max-w-4xl"><QuestionSkeleton /></div></LoadingState>
            ) : (
              <ScrollingItems state={state} content={content} visibleItems={visibleItems} currentPos={currentPos} answers={answers}
                onAnswer={onAnswer} onToggleFlag={onToggleFlag} onCurrentChange={setCurrentPos} onNavigate={scrollToItem}
                scrollRequest={scrollReq} scrollRootRef={scrollRootRef} headerHeight={headerH} stickyTop={stickyTop}
                passageDisplay={state.passage_display ?? null} sectionTitle={sectionTitle}
                forwardOnly={forwardOnly} onReview={openReview} />
            )}
          </div>
        ) : reviewOpen ? null : sectionError ? (
          <ErrorMessage error={sectionError} onRetry={() => setSectionRetry((n) => n + 1)} />
        ) : sectionLoading ? (
          <LoadingState label={t("player.loading")}><div className="mx-auto w-full max-w-4xl"><QuestionSkeleton /></div></LoadingState>
        ) : curItem && q ? (
          passage ? (
            <>
              <PassageToggle passage={passage} open={passageOpen} controls={`passage-${passage.id}`} top={stickyTop} onToggle={togglePassage} />
              <SplitPassage
                questionRef={questionAreaRef}
                questionStyle={{ scrollMarginTop: stickyTop + 52 }}
                passage={<PassagePane ref={passageRef} id={`passage-${passage.id}`} passage={passage} open={passageOpen} scrollMarginTop={stickyTop + 52} display={state.passage_display} fill />}
              >
                {questionBlock(curItem, q)}
              </SplitPassage>
            </>
          ) : (
            <div ref={questionAreaRef} tabIndex={-1} className="mx-auto w-full max-w-4xl space-y-4 outline-none">
              {questionBlock(curItem, q)}
            </div>
          )
        ) : (
          <p className="mx-auto w-full max-w-4xl rounded-xl border border-slate-200 bg-white p-6 text-sm text-slate-600">{t("player.noQuestion")}</p>
        )}
      </main>

      <PlayerBottomBar
        ref={paletteButtonRef}
        onBack={reviewOpen ? closeReview : curIndex > 0 ? () => go(-1) : null}
        onNext={reviewOpen ? null : lastInSection ? openReview : () => go(1)}
        n={curIndex + 1}
        total={visibleItems.length}
        mapOpen={paletteOpen}
        anyFlagged={counts.flagged > 0}
        onOpenMap={() => setPaletteOpen(true)}
      />

      <QuestionMap
        open={paletteOpen}
        onClose={() => setPaletteOpen(false)}
        groups={paletteGroups}
        currentPosition={curItem?.position ?? -1}
        description={sectionOf ? `${progressText} · ${sectionOf}` : progressText}
        currentRef={paletteCurrentRef}
        onSelect={selectFromMap}
        onReview={openReview}
      />

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
