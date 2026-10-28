"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { isLmsApiError } from "@/lib/lms/client";
import { createDraft, updateDraft } from "@/lib/lms/quizEditor";
import type { CardDraftConflictDetails, CardPayload, DraftCreateIn, DraftOut } from "@/lib/lms/quizEditorTypes";

export type AutosaveStatus = "idle" | "saving" | "saved" | "conflict" | "gone" | "error";

export interface SavedDraft { id: string; rev: number }

const RETRY_MS = 5000;

/**
 * Debounced autosave of one card draft (PHASE_7C_DESIGN 8.2, 7c-4). Saves are serialized (one request at a time, the
 * last payload wins); a missing draft is created on the first save (`createBody`). A 409 `draft_conflict` (another tab)
 * or `draft_exists` stops saving until the card resolves it (`adopt`); a 404 `draft_not_found` means the draft or the
 * card is gone. `flush()` waits for every pending save and returns the draft id and revision to commit with.
 */
export function useDraftAutosave({
  courseId, assessmentId, initialDraft, createBody, delay = 800,
}: {
  courseId: string;
  assessmentId: string;
  initialDraft: DraftOut | null;
  /** Where to create the draft when none exists yet (an existing card: `{ item_id }`). */
  createBody: () => Omit<DraftCreateIn, "payload">;
  delay?: number;
}) {
  const idRef = useRef<string | null>(initialDraft?.id ?? null);
  const revRef = useRef<number>(initialDraft?.draft_rev ?? 0);
  const pending = useRef<CardPayload | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const chain = useRef<Promise<void>>(Promise.resolve());
  const stopped = useRef(false);
  const mounted = useRef(true);
  const inflight = useRef(false);
  const createRef = useRef(createBody);
  createRef.current = createBody;
  const [status, setStatusState] = useState<AutosaveStatus>(initialDraft ? "saved" : "idle");
  const [conflict, setConflict] = useState<CardDraftConflictDetails | null>(null);
  const [draftId, setDraftId] = useState<string | null>(idRef.current);
  const setStatus = (s: AutosaveStatus) => { if (mounted.current) setStatusState(s); };

  const run = useCallback(async (keepalive?: unknown) => {
    const p = pending.current;
    if (!p || stopped.current) return;
    pending.current = null;
    setStatus("saving");
    inflight.current = true;
    // Phase 7c UX: the last save when the page is hidden or left must outlive the page (`keepalive`).
    const opts = { keepalive: keepalive === true };
    try {
      let d: DraftOut;
      if (!idRef.current) {
        d = await createDraft(courseId, assessmentId, { ...createRef.current(), payload: p }, opts);
        idRef.current = d.id;
        if (mounted.current) setDraftId(d.id);
      } else {
        d = await updateDraft(courseId, assessmentId, idRef.current, { draft_rev: revRef.current, payload: p }, opts);
      }
      revRef.current = d.draft_rev;
      setStatus(pending.current ? "saving" : "saved");
    } catch (e) {
      if (isLmsApiError(e) && e.code === "draft_conflict") {
        stopped.current = true;
        if (pending.current === null) pending.current = p;
        if (mounted.current) setConflict(e.details as unknown as CardDraftConflictDetails);
        setStatus("conflict");
      } else if (isLmsApiError(e) && e.code === "draft_exists") {
        // Another tab opened this card first: its draft is the current state.
        const other = e.details as unknown as DraftOut;
        idRef.current = other.id;
        stopped.current = true;
        if (pending.current === null) pending.current = p;
        if (mounted.current) {
          setDraftId(other.id);
          setConflict({ draft_rev: other.draft_rev, payload: other.payload, updated_by_name: other.updated_by_name });
        }
        setStatus("conflict");
      } else if (isLmsApiError(e) && (e.code === "draft_not_found" || e.code === "item_not_found")) {
        stopped.current = true;
        setStatus("gone");
      } else {
        if (pending.current === null) pending.current = p;
        setStatus("error");
        if (timer.current) clearTimeout(timer.current);
        timer.current = setTimeout(() => { timer.current = null; chain.current = chain.current.then(run); }, RETRY_MS);
      }
    } finally {
      inflight.current = false;
    }
  }, [courseId, assessmentId]); // eslint-disable-line react-hooks/exhaustive-deps

  const schedule = useCallback((payload: CardPayload) => {
    pending.current = payload;
    if (stopped.current) return;
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => { timer.current = null; chain.current = chain.current.then(run); }, delay);
  }, [delay, run]);

  /** Sends what is pending and waits for it. Null when the draft cannot be saved (conflict, gone, error). */
  const flush = useCallback(async (): Promise<SavedDraft | null> => {
    if (timer.current) { clearTimeout(timer.current); timer.current = null; }
    if (pending.current && !stopped.current) chain.current = chain.current.then(run);
    await chain.current;
    if (stopped.current || pending.current || !idRef.current) return null;
    return { id: idRef.current, rev: revRef.current };
  }, [run]);

  /** Continue from a known draft state (after a conflict was resolved or the draft was re-created). */
  const adopt = useCallback((id: string, rev: number) => {
    idRef.current = id;
    revRef.current = rev;
    stopped.current = false;
    setDraftId(id);
    setConflict(null);
    setStatus("saved");
  }, []);

  /** Stop saving and forget pending changes (discard, or the card closes). */
  const cancel = useCallback(() => {
    if (timer.current) { clearTimeout(timer.current); timer.current = null; }
    pending.current = null;
    stopped.current = true;
  }, []);

  /** Id of the draft right now (null until the first save of a card that had none). */
  const currentId = useCallback(() => idRef.current, []);

  /** A commit found a newer draft revision (another tab): show the conflict like an autosave would. */
  const markConflict = useCallback((details: CardDraftConflictDetails) => {
    stopped.current = true;
    setConflict(details);
    setStatus("conflict");
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  /** A commit found the draft gone (committed or discarded elsewhere, or the card was removed). */
  const markGone = useCallback(() => {
    stopped.current = true;
    setStatus("gone");
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Leaving the page with a change still waiting for the debounce: send it now (best effort).
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      if (timer.current) { clearTimeout(timer.current); timer.current = null; }
      if (pending.current && !stopped.current) chain.current = chain.current.then(run);
    };
  }, [run]);

  // Phase 7c UX (no lost keystrokes): the tab is hidden, closed or navigated away within the debounce: send the pending
  // change at once with `keepalive`, and ask before leaving while a save is still waiting or running.
  useEffect(() => {
    const sendNow = () => {
      if (!pending.current || stopped.current) return;
      if (timer.current) { clearTimeout(timer.current); timer.current = null; }
      chain.current = chain.current.then(() => run(true));
    };
    const onVisibility = () => { if (document.visibilityState === "hidden") sendNow(); };
    const onBeforeUnload = (e: BeforeUnloadEvent) => {
      if ((pending.current && !stopped.current) || inflight.current) {
        sendNow();
        e.preventDefault();
        e.returnValue = "";
      }
    };
    window.addEventListener("pagehide", sendNow);
    window.addEventListener("beforeunload", onBeforeUnload);
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      window.removeEventListener("pagehide", sendNow);
      window.removeEventListener("beforeunload", onBeforeUnload);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [run]);

  return { status, conflict, draftId, schedule, flush, adopt, cancel, currentId, markConflict, markGone };
}
