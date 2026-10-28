"use client";

import React, { useEffect, useRef, useState } from "react";
import { AlertTriangle, ArrowDown, ArrowUp, Check, Copy, GripVertical, PencilLine } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { isLmsApiError } from "@/lib/lms/client";
import { getQuestion } from "@/lib/lms/content";
import { QUESTION_TYPES, type QuestionType } from "@/lib/lms/contentTypes";
import type { ItemOut, SectionOut } from "@/lib/lms/assessmentTypes";
import { commitDraft, createDraft, deleteDraft, rememberImage, resolvePayloadImages } from "@/lib/lms/quizEditor";
import type {
  CardDraftConflictDetails, CardPayload, DraftOut, EditScope, ScopeRequiredDetails,
} from "@/lib/lms/quizEditorTypes";
import { renderRichText } from "@/components/math/MathRenderer";
import { Badge, Button, ConfirmDialog, IconButton, toast } from "@/components/ui";
import { QuestionCardForm } from "@/components/lms/content/QuestionCardForm";
import {
  formFromPayload, formFromStaff, payloadFromForm, validateForm, type QuestionForm,
} from "@/components/lms/content/types/formModel";
import { fmtPoints } from "@/components/lms/assessments/format";
import { DraftConflictDialog } from "./DraftConflictDialog";
import { QuizError, fieldErrorKeys } from "./QuizError";
import { ScopeDialog } from "./ScopeDialog";
import type { CardCloser, CloseMode, QuizCtx } from "./quizCtx";
import { useDraftAutosave, type SavedDraft } from "./useDraftAutosave";

export interface CardActions {
  /** Undefined: the card is first / last (the button shows disabled). */
  onMoveUp?: () => void;
  onMoveDown?: () => void;
  /** Remove the item from the quiz (existing cards only; the editor offers "Undo"). */
  onDelete?: () => void;
  /** A new card after this one with the same content. */
  onDuplicate?: (payload: CardPayload) => void;
  /** Other sections the card can move to (shown when the quiz has two or more sections). */
  moveTargets?: { id: string; label: string }[];
  onMoveToSection?: (sectionId: string) => void;
}

/** Type options of a card: the section's allowed types (template and preset rules live there), plus its current type. */
export function cardTypeOptions(section: SectionOut | null, current?: QuestionType): QuestionType[] {
  const allowed = section?.rules.allowed_types;
  if (!allowed || allowed.length === 0) return QUESTION_TYPES;
  return QUESTION_TYPES.filter((q) => allowed.includes(q) || q === current);
}

/** True when a new card holds nothing worth keeping (closing it discards the draft). */
function isBlank(f: QuestionForm): boolean {
  return !f.stem.trim() && !f.explanation.trim() && !f.image
    && f.choices.every((c) => !c.text.trim() && !c.image)
    && !f.columnA.trim() && !f.columnB.trim()
    && f.numeric.every((n) => !n.value.trim() && !n.min.trim() && !n.max.trim())
    && !f.shortAnswers.trim() && !f.rubric.trim();
}

/**
 * Phase 7c S5: blank answers after the first two are dropped when the card is finished (Enter adds one more than
 * needed, and a new card starts with empty answers). Answers marked correct are kept, so the validation explains them.
 */
function pruneBlankChoices(f: QuestionForm): QuestionForm {
  if (f.type !== "single_choice" && f.type !== "multiple_answers") return f;
  const marked = (id: string) => (f.type === "single_choice" ? f.correctSingle === id : f.correctMulti.includes(id));
  const choices = [...f.choices];
  for (let i = choices.length - 1; i >= 0 && choices.length > 2; i--) {
    const c = choices[i];
    if (!c.text.trim() && !c.image && !marked(c.id)) choices.splice(i, 1);
  }
  return choices.length === f.choices.length ? f : { ...f, choices };
}

function rememberFormImages(f: QuestionForm) {
  rememberImage(f.image);
  f.choices.forEach((c) => rememberImage(c.image));
}

/**
 * One question card of the quiz editor (PHASE_7C_DESIGN 8.2, 8.3). Collapsed: one row with number, type, points,
 * chips and the first lines of the question. Open: the shared question form; typing autosaves a draft, "Done"
 * (or closing a valid card) creates a version.
 */
export function QuestionCard(props: {
  ctx: QuizCtx;
  section: SectionOut;
  /** The quiz item (an existing card); absent for a new card. */
  item?: ItemOut;
  /** The card's draft: of the item, or the new card itself. */
  draft?: DraftOut;
  label: string;
  open: boolean;
  onOpen: () => void;
  onClosed: () => void;
  actions: CardActions;
  dragProps?: React.HTMLAttributes<HTMLElement>;
  /** A question inside a passage block. */
  childOf?: ItemOut;
}) {
  return props.open ? <OpenCard {...props} /> : <CollapsedCard {...props} />;
}

function CollapsedCard({ ctx, item, draft, label, onOpen, dragProps }: React.ComponentProps<typeof QuestionCard>) {
  const { t } = useTranslation();
  const q = item?.question;
  const type = draft?.payload.type ?? q?.type;
  const points = item ? fmtPoints(item.points) : fmtPoints(draft?.payload.points);
  const stem = draft && !item ? draft.payload.stem : q?.stem_excerpt ?? "";
  const hasDraft = !!draft || !!item?.has_draft;
  const draftBad = draft ? validateForm(formFromPayload(draft.payload)) !== null : false;
  const used = q?.used_elsewhere ?? 0;
  // Phase 7c S5: the correct answer(s) of the saved version (owner's proposal 4); true/false tokens are translated
  const summary = item ? q?.correct_summary ?? null : null;
  const tf = q?.type === "true_false";
  const answer = tf && summary === "true" ? t("bank.editor.true") : tf && summary === "false" ? t("bank.editor.false") : summary;
  const draggable = !!dragProps && Object.keys(dragProps).length > 0;
  return (
    <div {...dragProps} className="rounded-2xl border border-slate-200 bg-white shadow-sm">
      <div className="flex items-start">
        {draggable && <GripVertical className="ml-2 mt-4 hidden h-4 w-4 shrink-0 cursor-grab text-slate-400 sm:block" aria-hidden="true" />}
        <button type="button" disabled={!ctx.canEdit} onClick={onOpen} aria-expanded={false}
          aria-label={ctx.canEdit ? t("quizEditor.card.openLabel", { label }) : undefined}
          className="min-h-11 min-w-0 flex-1 rounded-2xl px-3 py-3 text-left transition-colors hover:bg-slate-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand-600 disabled:cursor-default disabled:hover:bg-transparent">
          <span className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm">
            <span className="font-semibold text-slate-900">{label}</span>
            {type && <Badge>{t(`bank.types.${type}.name`)}</Badge>}
            <span className="text-slate-600">{t("quizEditor.card.points", { n: points || "0" })}</span>
            {hasDraft && (
              <Badge tone="warning" icon={<PencilLine aria-hidden="true" />}>
                {draftBad ? t("quizEditor.card.draftHasErrors") : t("quizEditor.card.draft")}
              </Badge>
            )}
            {used > 0 && <Badge tone="info">{t("quizEditor.card.usedIn", { n: used + 1 })}</Badge>}
            {q?.bank_kind === "shared" && <Badge>{t("quizEditor.card.sharedBank")}</Badge>}
            {q?.deleted && <Badge tone="danger">{t("assessments.item.deleted")}</Badge>}
            {q?.newer_version_available && <Badge tone="warning">{t("assessments.item.newerVersion")}</Badge>}
          </span>
          {stem
            ? <span className="mt-1 line-clamp-2 block break-words text-base text-slate-800 sm:text-sm" dangerouslySetInnerHTML={{ __html: renderRichText(stem) }} />
            : <span className="mt-1 block text-sm italic text-slate-500">{t("quizEditor.card.emptyStem")}</span>}
          {answer && (
            <span className="mt-1 flex items-start gap-1.5 text-sm text-emerald-800">
              <Check className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
              <span className="min-w-0 break-words line-clamp-2">
                <span className="font-medium">{t("quizEditor.card.correctAnswer")}</span>{" "}
                <span dangerouslySetInnerHTML={{ __html: renderRichText(answer) }} />
              </span>
            </span>
          )}
        </button>
      </div>
    </div>
  );
}

function OpenCard({ ctx, section, item, draft, label, onClosed, actions, childOf }: React.ComponentProps<typeof QuestionCard>) {
  const { t } = useTranslation();
  const { courseId, a } = ctx;
  const isNew = !item;
  const [form, setForm] = useState<QuestionForm | null>(null);
  const formRef = useRef<QuestionForm | null>(null);
  const initialJson = useRef("");
  const [loadError, setLoadError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [clientError, setClientError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<string[]>([]);
  const [scope, setScope] = useState<{ details: ScopeRequiredDetails; saved: SavedDraft } | null>(null);
  const [versionConflict, setVersionConflict] = useState(false);
  const [confirmDiscard, setConfirmDiscard] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const autosave = useDraftAutosave({
    courseId, assessmentId: a.id, initialDraft: draft ?? null,
    createBody: () => (item ? { item_id: item.id } : { section_id: section.id }),
  });

  // Seed the form: the draft when there is one, else the question's current version with this quiz's points.
  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        let f: QuestionForm;
        if (draft) {
          f = formFromPayload(draft.payload, await resolvePayloadImages(draft.payload));
        } else if (item?.question) {
          f = formFromStaff(await getQuestion(courseId, item.question.id));
          f.points = fmtPoints(item.points) || f.points;
          rememberFormImages(f);
        } else {
          throw new Error("card without content");
        }
        if (!alive) return;
        formRef.current = f;
        initialJson.current = JSON.stringify(f);
        setForm(f);
      } catch (e) {
        if (alive) setLoadError(e);
      }
    })();
    rootRef.current?.scrollIntoView({ block: "nearest" });
    return () => { alive = false; };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const change = (p: Partial<QuestionForm>) => {
    const cur = formRef.current;
    if (!cur) return;
    const next = { ...cur, ...p };
    formRef.current = next;
    setForm(next);
    setClientError(null);
    setFieldErrors([]);
    rememberFormImages(next);
    autosave.schedule(payloadFromForm(next));
  };

  const finish = async () => {
    autosave.cancel();
    await ctx.reload();
    onClosed();
  };

  const commit = async (saved: SavedDraft, sc?: EditScope): Promise<boolean> => {
    setError(null);
    setFieldErrors([]);
    try {
      const out = await commitDraft(courseId, a.id, saved.id, sc ? { draft_rev: saved.rev, scope: sc } : { draft_rev: saved.rev });
      setScope(null);
      if (out.applied === "this") toast.info(t("quizEditor.card.appliedThis"));
      else if (out.applied === "all") toast.success(t("quizEditor.card.appliedAll"));
      await finish();
      return true;
    } catch (e) {
      if (isLmsApiError(e) && e.code === "scope_required") {
        setScope({ details: e.details as unknown as ScopeRequiredDetails, saved });
      } else if (isLmsApiError(e) && e.code === "version_conflict") {
        setScope(null);
        setVersionConflict(true);
      } else if (isLmsApiError(e) && e.code === "draft_conflict") {
        setScope(null);
        autosave.markConflict(e.details as unknown as CardDraftConflictDetails);
      } else if (isLmsApiError(e) && e.code === "draft_not_found") {
        setScope(null);
        autosave.markGone();
      } else {
        setScope(null);
        if (isLmsApiError(e) && e.status === 422) setFieldErrors(fieldErrorKeys(e.details));
        setError(e);
      }
      return false;
    }
  };

  const doClose = async (mode: CloseMode): Promise<boolean> => {
    if (scope || versionConflict || autosave.conflict || confirmDiscard) return false;
    const f = formRef.current;
    if (!f) { autosave.cancel(); onClosed(); return true; }
    const touched = JSON.stringify(f) !== initialJson.current;
    if (!touched && !autosave.currentId()) { autosave.cancel(); onClosed(); return true; }
    setBusy(true);
    try {
      if (isNew && isBlank(f)) {
        // An empty new card is not worth keeping.
        autosave.cancel();
        const id = autosave.currentId();
        if (id) await deleteDraft(courseId, a.id, id).catch(() => undefined);
        await finish();
        return true;
      }
      const pruned = pruneBlankChoices(f);
      if (pruned !== f) {
        formRef.current = pruned;
        setForm(pruned);
        autosave.schedule(payloadFromForm(pruned));
      }
      const bad = validateForm(pruned);
      if (bad) {
        if (mode === "done") { setClientError(bad); return false; }
        // Closing an unfinished card keeps it as a draft ("Draft saved · has errors").
        if (!(await autosave.flush())) return false;
        await finish();
        return true;
      }
      const saved = await autosave.flush();
      if (!saved) return false;
      return await commit(saved);
    } finally {
      setBusy(false);
    }
  };

  // The editor asks the open card to close before opening another one or publishing. One close runs at a time.
  const inflight = useRef<Promise<boolean> | null>(null);
  const closeRef = useRef<CardCloser>(doClose);
  closeRef.current = (mode) => {
    if (!inflight.current) inflight.current = doClose(mode).finally(() => { inflight.current = null; });
    return inflight.current;
  };
  useEffect(() => {
    const fn: CardCloser = (mode) => closeRef.current(mode);
    ctx.closer.current = fn;
    // Click outside the card closes it (like "Done"); dialogs, menus and toasts do not count as outside.
    const onDown = (e: MouseEvent) => {
      const target = e.target as Element | null;
      if (!rootRef.current || !target || rootRef.current.contains(target)) return;
      if (!document.contains(target) || target.closest("dialog, [role='menu'], [data-quiz-keep-open]")) return;
      void closeRef.current("auto");
    };
    document.addEventListener("mousedown", onDown);
    return () => {
      document.removeEventListener("mousedown", onDown);
      if (ctx.closer.current === fn) ctx.closer.current = null;
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const discard = async () => {
    setBusy(true);
    try {
      autosave.cancel();
      const id = autosave.currentId();
      if (id) await deleteDraft(courseId, a.id, id);
      setConfirmDiscard(false);
      setVersionConflict(false);
      await finish();
    } catch (e) {
      setConfirmDiscard(false);
      setError(e);
    } finally {
      setBusy(false);
    }
  };

  // 409 version_conflict: "Keep my draft" re-creates the draft on top of the newer version (PHASE_7C_DESIGN 5.4).
  const keepDraftOnNewVersion = async () => {
    if (!item || !formRef.current) return;
    setBusy(true);
    try {
      const id = autosave.currentId();
      autosave.cancel();
      if (id) await deleteDraft(courseId, a.id, id).catch(() => undefined);
      const d = await createDraft(courseId, a.id, { item_id: item.id, payload: payloadFromForm(formRef.current) });
      autosave.adopt(d.id, d.draft_rev);
      setVersionConflict(false);
    } catch (e) {
      setVersionConflict(false);
      setError(e);
    } finally {
      setBusy(false);
    }
  };

  const takeTheirs = async () => {
    const c = autosave.conflict;
    const id = autosave.currentId();
    if (!c || !id) return;
    const f = formFromPayload(c.payload, await resolvePayloadImages(c.payload));
    formRef.current = f;
    setForm(f);
    autosave.adopt(id, c.draft_rev);
  };
  const keepMine = () => {
    const c = autosave.conflict;
    const id = autosave.currentId();
    if (!c || !id || !formRef.current) return;
    autosave.adopt(id, c.draft_rev);
    autosave.schedule(payloadFromForm(formRef.current));
  };

  // The draft or the card is gone (deleted, or finished in another tab): keep the text as a new card.
  const readd = async () => {
    if (!formRef.current) return;
    setBusy(true);
    try {
      await createDraft(courseId, a.id, { section_id: section.id, payload: payloadFromForm(formRef.current) });
      await finish();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };

  const languages = a.languages.filter((l) => ctx.courseLanguages.includes(l));
  const q = item?.question;
  const showPassageNote = !!childOf && q?.bank_kind === "shared" && (q.used_elsewhere ?? 0) > 0;
  const statusText = {
    idle: t("quizEditor.card.draftIdle"),
    saving: t("quizEditor.card.draftSaving"),
    saved: t("quizEditor.card.draftSaved"),
    conflict: t("quizEditor.card.draftConflict"),
    gone: t("quizEditor.card.gone"),
    error: t("quizEditor.card.draftError"),
  }[autosave.status];
  const hasDraft = !!autosave.draftId;

  return (
    <div ref={rootRef} className="rounded-2xl border-2 border-brand-300 bg-white p-3 shadow-md sm:p-4"
      onKeyDown={(e) => {
        if (e.key === "Escape" && !(e.target as Element).closest("dialog")) { e.stopPropagation(); void closeRef.current("auto"); }
      }}>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <h3 className="text-base font-semibold text-slate-900">{label}</h3>
        {q?.bank_kind === "shared" && <Badge>{t("quizEditor.card.sharedBank")}</Badge>}
        {(q?.used_elsewhere ?? 0) > 0 && <Badge tone="info">{t("quizEditor.card.usedIn", { n: (q?.used_elsewhere ?? 0) + 1 })}</Badge>}
      </div>
      {showPassageNote && <p role="note" className="mb-3 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-700">{t("quizEditor.passageChild.note")}</p>}
      {loadError ? <QuizError error={loadError} /> : !form ? (
        <p role="status" className="py-6 text-center text-sm text-slate-500">{t("lms.common.loading")}</p>
      ) : (
        <div className="space-y-4">
          <QuestionCardForm form={form} onChange={change} disabled={busy || autosave.status === "conflict"} courseId={courseId}
            languages={languages.length ? languages : a.languages} typeOptions={cardTypeOptions(section, form.type)}
            lockLanguage={!isNew || languages.length <= 1} showMeta={false} idPrefix={`qc-${item?.id ?? draft?.id ?? "new"}`}
            keyboardAnswers />
          {clientError && <p role="alert" className="text-sm text-red-700">{t(clientError)}</p>}
          {fieldErrors.length > 0 && (
            <ul role="alert" className="list-disc space-y-0.5 pl-5 text-sm text-red-700">
              {fieldErrors.map((k) => <li key={k}>{t("quizEditor.card.fieldError", { field: t(k) })}</li>)}
            </ul>
          )}
        </div>
      )}
      <QuizError error={error} className="mt-3" />
      {autosave.status === "gone" && (
        <div role="alert" className="mt-3 flex flex-wrap items-center gap-2 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
          <AlertTriangle className="h-4 w-4 shrink-0" aria-hidden="true" />
          <span className="min-w-0 flex-1">{t("quizEditor.card.goneBody")}</span>
          <Button variant="secondary" size="sm" disabled={busy || !form} onClick={() => void readd()}>{t("quizEditor.card.readd")}</Button>
          <Button variant="secondary" size="sm" disabled={busy} onClick={() => void finish()}>{t("quizEditor.card.close")}</Button>
        </div>
      )}

      <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-slate-100 pt-3">
        <p role="status" aria-live="polite" className={`min-w-full text-sm sm:min-w-0 sm:flex-1 ${autosave.status === "error" || autosave.status === "conflict" ? "text-amber-800" : "text-slate-600"}`}>
          {statusText}
        </p>
        <div className="flex w-full flex-wrap items-center gap-2 sm:w-auto sm:justify-end">
          <IconButton variant="secondary" icon={<ArrowUp />} aria-label={t("quizEditor.card.moveUp")} disabled={busy || !actions.onMoveUp} onClick={actions.onMoveUp} />
          <IconButton variant="secondary" icon={<ArrowDown />} aria-label={t("quizEditor.card.moveDown")} disabled={busy || !actions.onMoveDown} onClick={actions.onMoveDown} />
          {item && actions.onMoveToSection && (actions.moveTargets?.length ?? 0) > 0 && (
            <select aria-label={t("assessments.item.moveTo")} disabled={busy} value=""
              className="min-h-11 max-w-full rounded-xl border border-slate-300 bg-white px-2 text-sm sm:min-h-9"
              onChange={(e) => { const sid = e.target.value; if (sid) void autosave.flush().then(() => actions.onMoveToSection?.(sid)); }}>
              <option value="">{t("assessments.item.moveTo")}</option>
              {actions.moveTargets?.map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}
            </select>
          )}
          {item && actions.onDuplicate && (
            <Button variant="secondary" size="sm" leftIcon={<Copy className="h-4 w-4" aria-hidden="true" />} disabled={busy || !form}
              onClick={() => formRef.current && actions.onDuplicate?.(payloadFromForm(formRef.current))}>{t("quizEditor.card.duplicate")}</Button>
          )}
          {item && hasDraft && (
            <Button variant="secondary" size="sm" disabled={busy} onClick={() => setConfirmDiscard(true)}>{t("quizEditor.card.discard")}</Button>
          )}
          {item ? (
            actions.onDelete && <Button variant="dangerOutline" size="sm" disabled={busy} onClick={() => { autosave.cancel(); actions.onDelete?.(); }}>{t("quizEditor.card.delete")}</Button>
          ) : (
            <Button variant="dangerOutline" size="sm" disabled={busy} onClick={() => setConfirmDiscard(true)}>{t("quizEditor.card.delete")}</Button>
          )}
          <Button variant="primary" size="sm" loading={busy} disabled={!form || autosave.status === "gone"} onClick={() => void closeRef.current("done")}>
            {t("quizEditor.card.done")}
          </Button>
        </div>
      </div>

      <ScopeDialog details={scope?.details ?? null} busy={busy} defaultLanguage={ctx.defaultLanguage}
        onCancel={() => setScope(null)}
        onChoose={(sc) => {
          const s = scope;
          if (!s) return;
          setBusy(true);
          void commit(s.saved, sc).finally(() => setBusy(false));
        }} />
      <DraftConflictDialog kind={autosave.conflict ? "draft" : versionConflict ? "version" : null}
        otherName={autosave.conflict?.updated_by_name} busy={busy}
        onPrimary={() => (autosave.conflict ? keepMine() : void keepDraftOnNewVersion())}
        onSecondary={() => (autosave.conflict ? void takeTheirs() : void discard())}
        onClose={() => (autosave.conflict ? keepMine() : setVersionConflict(false))} />
      <ConfirmDialog open={confirmDiscard} tone="danger" busy={busy}
        title={isNew ? t("quizEditor.card.deleteNewTitle") : t("quizEditor.card.discardTitle")}
        effect={isNew ? t("quizEditor.card.deleteNewBody") : t("quizEditor.card.discardBody")}
        confirmLabel={isNew ? t("quizEditor.card.delete") : t("quizEditor.card.discard")}
        onConfirm={() => void discard()} onCancel={() => setConfirmDiscard(false)} />
    </div>
  );
}
