"use client";

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Plus } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import {
  addItem, addSection, deleteItem as apiDeleteItem, deleteSection, getAssessment, reorderItems, reorderSections, startPreview,
  updateItem, updateSection,
} from "@/lib/lms/assessments";
import {
  isStaffAssessment, previewAttemptId, templateLockedFields, type AssessmentStaffOut, type ItemCreateIn, type ItemOut,
  type SectionIn, type SectionOut,
} from "@/lib/lms/assessmentTypes";
import { createDraft } from "@/lib/lms/quizEditor";
import type { CardPayload } from "@/lib/lms/quizEditorTypes";
import { pickLocalized } from "@/lib/lms/localized";
import { isAssessmentLocked, useTemplateUi } from "@/lib/lms/templates";
import type { Lang } from "@/lib/lms/types";
import { useCourse } from "@/components/lms/CourseContext";
import { useCanEditContent } from "@/components/lms/content/StaffGate";
import { useTabCrumbs } from "@/components/lms/course/StaffCourseUi";
import { Button, ConfirmDialog, PageHeader, TabPanel, Tabs } from "@/components/ui";
import { inputCls } from "@/components/lms/content/ui";
import { emptyForm, payloadFromForm } from "@/components/lms/content/types/formModel";
import type { AddItemsTab } from "@/components/lms/assessments/AddItemsDialog";
import { AssessmentError } from "@/components/lms/assessments/AssessmentError";
import { SectionDialog } from "@/components/lms/assessments/SectionDialog";
import { SettingsPanel } from "@/components/lms/assessments/SettingsPanel";
import { moveIndex } from "@/components/lms/assessments/format";
import { TemplateBadge } from "@/components/lms/examTemplates/TemplateBadge";
import { SaveAsTemplateDialog } from "@/components/lms/examTemplates/SaveAsTemplateDialog";
import { AddAtEnd } from "./AddBetween";
import { FindQuestionsDrawer } from "./FindQuestionsDrawer";
import { QuizError } from "./QuizError";
import { QuizPublishBar } from "./QuizPublishBar";
import { QuizSectionBlock, quizSectionName } from "./QuizSectionBlock";
import { cardTypeOptions } from "./QuestionCard";
import { draftKey, itemKey, type CardCloser, type QuizCtx, type QuizOps } from "./quizCtx";

type TabId = "questions" | "settings" | "preview";
const UNDO_MS = 10_000;

/** Card labels: questions are numbered through the quiz (passage children included); random groups are not. */
function cardLabels(a: AssessmentStaffOut, t: (k: string, p?: Record<string, string | number>) => string): Map<string, string> {
  const out = new Map<string, string>();
  let n = 0;
  for (const s of a.sections) {
    for (const it of s.items) {
      if (it.kind === "question") out.set(it.id, t("quizEditor.card.number", { n: ++n }));
      else if (it.kind === "passage") for (const c of it.children ?? []) out.set(c.id, t("quizEditor.card.number", { n: ++n }));
    }
  }
  return out;
}

/** What re-adds a removed top-level item ("Undo"). */
function readdBody(item: ItemOut): ItemCreateIn | null {
  const points = item.points === null || item.points === undefined ? undefined : Number(item.points);
  if (item.kind === "question" && item.question) return { kind: "question", question_id: item.question.id, points };
  if (item.kind === "passage" && item.passage) {
    return { kind: "passage", passage_id: item.passage.id, question_ids: (item.children ?? []).flatMap((c) => (c.question ? [c.question.id] : [])) };
  }
  if (item.kind === "pick" && item.pick) return { kind: "pick", pick: { bank_id: item.pick.bank_id, count: item.pick.count, filter: item.pick.filter }, points };
  return null;
}

/**
 * Phase 7c S3: the question-card editor for blank and template-created quizzes (PHASE_7C_DESIGN 8.1–8.3, owner
 * reference: Canvas "Questions" tab). Tabs: Questions (cards), Settings, Preview. One card is open at a time; typing
 * autosaves a draft, "Done" (or closing a valid card) saves a version; the publish bar sits on top.
 */
export function QuizEditor({ initial }: { initial: AssessmentStaffOut }) {
  const { lang, t } = useTranslation();
  const { course } = useCourse();
  const router = useRouter();
  const canEdit = useCanEditContent();
  const ui = useTemplateUi();
  const aid = initial.id;
  const base = `/${lang}/courses/${course.id}/assessments`;
  const [a, setA] = useState<AssessmentStaffOut>(initial);
  const aRef = useRef(initial);
  aRef.current = a;
  const [tab, setTab] = useState<TabId>("questions");
  const [actionError, setActionError] = useState<unknown>(null);
  const [openKey, setOpenKey] = useState<string | null>(null);
  const closer = useRef<CardCloser | null>(null);
  const [find, setFind] = useState<{ sectionId: string; tab: AddItemsTab; anchor: string | null; known: string[] } | null>(null);
  const findRef = useRef(find);
  findRef.current = find;
  const [undo, setUndo] = useState<{ run: () => Promise<void> } | null>(null);
  const undoTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [undoBusy, setUndoBusy] = useState(false);
  const [sectionDlg, setSectionDlg] = useState<{ section: SectionOut | null } | null>(null);
  const [secBusy, setSecBusy] = useState(false);
  const [secError, setSecError] = useState<unknown>(null);
  const [toDelete, setToDelete] = useState<SectionOut | null>(null);
  const [saveAsOpen, setSaveAsOpen] = useState(false);
  const [pLang, setPLang] = useState<Lang>(initial.languages[0]);
  const [pBusy, setPBusy] = useState(false);
  const [pError, setPError] = useState<unknown>(null);

  const reload = useCallback(async () => {
    try {
      const out = await getAssessment(course.id, aid);
      if (!isStaffAssessment(out)) { router.replace(`${base}/${aid}`); return; }
      aRef.current = out;
      setA(out);
    } catch (e) {
      setActionError(e);
    }
  }, [course.id, aid, base, router]);
  useEffect(() => () => { if (undoTimer.current) clearTimeout(undoTimer.current); }, []);

  const defaultLanguage: Lang = a.languages.includes(course.default_language) ? course.default_language : a.languages[0];
  const ctx: QuizCtx = {
    courseId: course.id, a, canEdit, courseLanguages: course.languages, defaultLanguage, reload,
    current: () => aRef.current, onError: setActionError, closer,
  };
  const closeOpen = useCallback(async () => (closer.current ? closer.current("auto") : true), []);
  const guard = useCallback(async (fn: () => Promise<unknown>) => {
    setActionError(null);
    try { await fn(); } catch (e) { setActionError(e); }
    await reload();
  }, [reload]);

  const ops: QuizOps = {
    openKey,
    requestOpen: (key) => {
      void (async () => {
        if (!(await closeOpen())) return;
        setOpenKey(key);
      })();
    },
    closed: () => setOpenKey(null),
    addQuestion: async (section, afterItemId, payload) => {
      if (!(await closeOpen())) return;
      setActionError(null);
      try {
        const body = payload ?? payloadFromForm(emptyForm(cardTypeOptions(section)[0] ?? "single_choice", defaultLanguage));
        const d = await createDraft(course.id, aid, { ...(section ? { section_id: section.id } : {}), after_item_id: afterItemId, payload: body });
        await reload();
        setOpenKey(draftKey(d.id));
      } catch (e) {
        setActionError(e);
      }
    },
    addFrom: (section, afterItemId, addTab) => {
      void (async () => {
        if (!(await closeOpen())) return;
        setFind({ sectionId: section.id, tab: addTab, anchor: afterItemId, known: section.items.map((i) => i.id) });
      })();
    },
    moveItem: async (section, from, to) => {
      const ids = moveIndex(section.items.map((i) => i.id), from, to);
      if (ids.every((id, k) => id === section.items[k].id)) return;
      await guard(() => reorderItems(course.id, aid, section.id, { item_ids: ids }));
    },
    moveChild: async (section, parent, from, to) => {
      const ids = moveIndex((parent.children ?? []).map((c) => c.id), from, to);
      await guard(() => reorderItems(course.id, aid, section.id, { item_ids: ids, parent_item_id: parent.id }));
    },
    moveToSection: async (item, sectionId) => {
      await guard(() => updateItem(course.id, aid, item.id, { section_id: sectionId }));
    },
    deleteItem: async (section, item, index, parent) => {
      if (openKey === itemKey(item.id)) setOpenKey(null);
      else if (!(await closeOpen())) return;
      setActionError(null);
      try {
        await apiDeleteItem(course.id, aid, item.id);
      } catch (e) {
        setActionError(e);
        await reload();
        return;
      }
      await reload();
      const body = parent ? null : readdBody(item);
      if (!body) return;
      if (undoTimer.current) clearTimeout(undoTimer.current);
      setUndo({
        run: async () => {
          const added = await addItem(course.id, aid, section.id, body);
          const newId = added[0]?.id;
          const fresh = await getAssessment(course.id, aid);
          const s = isStaffAssessment(fresh) ? fresh.sections.find((x) => x.id === section.id) : undefined;
          if (newId && s) {
            const order = s.items.map((i) => i.id).filter((id) => id !== newId);
            order.splice(Math.min(index, order.length), 0, newId);
            await reorderItems(course.id, aid, section.id, { item_ids: order });
          }
        },
      });
      undoTimer.current = setTimeout(() => setUndo(null), UNDO_MS);
    },
  };

  const runUndo = async () => {
    if (!undo) return;
    if (undoTimer.current) clearTimeout(undoTimer.current);
    setUndoBusy(true);
    await guard(undo.run);
    setUndoBusy(false);
    setUndo(null);
  };

  // Items added from a shared bank land at the end of the section; move them after the card the "+" was under.
  const onFindAdded = async () => {
    const f = findRef.current;
    if (!f) return;
    try {
      const fresh = await getAssessment(course.id, aid);
      const s = isStaffAssessment(fresh) ? fresh.sections.find((x) => x.id === f.sectionId) : undefined;
      if (s) {
        const all = s.items.map((i) => i.id);
        const added = all.filter((id) => !f.known.includes(id));
        let anchor = f.anchor;
        if (anchor && added.length) {
          const rest = all.filter((id) => !added.includes(id));
          const at = rest.indexOf(anchor);
          if (at >= 0 && at < rest.length - 1) {
            await reorderItems(course.id, aid, s.id, { item_ids: [...rest.slice(0, at + 1), ...added, ...rest.slice(at + 1)] });
          }
          anchor = added[added.length - 1];
        }
        setFind({ ...f, anchor, known: all });
      }
    } catch (e) {
      setActionError(e);
    }
    await reload();
  };

  // --- sections (7c-6: the default section stays hidden until a second one exists) ---
  const courseLocked = isAssessmentLocked(ui, a.preset);
  const examLocks = templateLockedFields(a);
  const structureLocked = courseLocked || examLocks.has("section_add_remove") || examLocks.has("section_order");
  const lockedNote = courseLocked ? t("templates.lockedNote") : t("examTemplates.lockedSections");
  const sectionIds = a.sections.map((s) => s.id);
  const moveSection = (from: number, to: number) => {
    const ids = moveIndex(sectionIds, from, to);
    if (ids.every((id, k) => id === sectionIds[k])) return;
    void guard(() => reorderSections(course.id, aid, ids));
  };
  const submitSection = async (v: SectionIn) => {
    setSecBusy(true);
    setSecError(null);
    try {
      if (sectionDlg?.section) await updateSection(course.id, aid, sectionDlg.section.id, v);
      else await addSection(course.id, aid, v);
      setSectionDlg(null);
      await reload();
    } catch (e) {
      setSecError(e);
    } finally {
      setSecBusy(false);
    }
  };
  const removeSection = async () => {
    if (!toDelete) return;
    setSecBusy(true);
    setSecError(null);
    try {
      await deleteSection(course.id, aid, toDelete.id);
      setToDelete(null);
      await reload();
    } catch (e) {
      setSecError(e);
    } finally {
      setSecBusy(false);
    }
  };

  const preview = async () => {
    if (!(await closeOpen())) return;
    setPBusy(true);
    setPError(null);
    try {
      const out = await startPreview(course.id, aid, a.languages.includes(pLang) ? pLang : a.languages[0]);
      const id = previewAttemptId(out);
      if (id) router.push(`/${lang}/courses/${course.id}/attempts/${id}`);
      else setPError({ code: "unknown" });
    } catch (e) {
      setPError(e);
    } finally {
      setPBusy(false);
    }
  };

  const labels = useMemo(() => cardLabels(a, t), [a, t]);
  const aTitle = pickLocalized(a.title, lang, course.default_language) || t("assessments.untitled");
  const crumbs = useTabCrumbs("assessments", [
    { label: aTitle, href: `${base}/${aid}` },
    { label: t("teaching.builderCrumb") },
  ], course.id);
  const templatable = canEdit && a.preset === "none" && !a.structure_locked && !a.exam_template?.template_locked;
  const showHeaders = a.sections.length > 1;
  const secName = (s: SectionOut) => quizSectionName(s, a.sections.indexOf(s), lang, defaultLanguage, t);

  const switchTab = (id: string) => {
    void (async () => {
      if (!(await closeOpen())) return;
      setTab(id as TabId);
    })();
  };

  return (
    <div className="space-y-4">
      <PageHeader breadcrumbs={crumbs} title={aTitle} className="mb-2" />
      {!canEdit && <p className="rounded-xl border border-amber-200 bg-amber-50 px-3.5 py-2 text-sm text-amber-900">{t("assessments.builder.readOnly")}</p>}
      <QuizPublishBar ctx={ctx} />
      <Tabs id="quiz-editor" label={t("quizEditor.tabs.label")} value={tab} onChange={switchTab} items={[
        { id: "questions", label: t("quizEditor.tabs.questions"), count: labels.size || undefined },
        { id: "settings", label: t("quizEditor.tabs.settings") },
        { id: "preview", label: t("quizEditor.tabs.preview") },
      ]} />

      <TabPanel tabsId="quiz-editor" value="questions" hidden={tab !== "questions"} className="space-y-4">
        <QuizError error={actionError} />
        {canEdit && structureLocked && showHeaders && <p role="note" className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-700">{lockedNote}</p>}
        {a.sections.length === 0 ? (
          <div className="space-y-3">
            <p className="rounded-2xl border border-dashed border-slate-300 bg-white px-4 py-8 text-center text-sm text-slate-600">{t("quizEditor.section.emptyQuiz")}</p>
            {canEdit && <AddAtEnd ops={ops} section={null} />}
          </div>
        ) : (
          <div className="space-y-4">
            {a.sections.map((s, i) => (
              <QuizSectionBlock key={s.id} ctx={ctx} ops={ops} section={s} index={i} count={a.sections.length} showHeader={showHeaders}
                labels={labels} structureLocked={structureLocked} lockedNote={lockedNote}
                onEdit={() => { setSecError(null); setSectionDlg({ section: s }); }}
                onDelete={() => { setSecError(null); setToDelete(s); }}
                onMoveBy={(d) => moveSection(i, i + d)} />
            ))}
          </div>
        )}
        {canEdit && (
          <div className="flex flex-wrap items-center gap-3 border-t border-slate-200 pt-4">
            <Button variant="secondary" leftIcon={<Plus className="h-4 w-4" aria-hidden="true" />} disabled={structureLocked}
              title={structureLocked ? lockedNote : undefined}
              onClick={() => { setSecError(null); setSectionDlg({ section: null }); }}>{t("assessments.section.add")}</Button>
            {a.sections.length === 1 && <p className="min-w-0 flex-1 basis-[14rem] text-sm text-slate-600">{t("quizEditor.section.firstBecomesSection1")}</p>}
          </div>
        )}
      </TabPanel>

      <TabPanel tabsId="quiz-editor" value="settings" hidden={tab !== "settings"} className="space-y-4">
        {a.exam_template && <TemplateBadge assessment={a} courseId={course.id} canEdit={canEdit} onChanged={reload} />}
        <SettingsPanel assessment={a} courseId={course.id} courseLanguages={course.languages} defaultLanguage={course.default_language}
          disabled={!canEdit} onSaved={reload} onConflict={reload} />
        {templatable && (
          <div className="flex flex-wrap items-center gap-3">
            <Button variant="secondary" onClick={() => setSaveAsOpen(true)}>{t("examTemplates.saveAs.action")}</Button>
            <SaveAsTemplateDialog open={saveAsOpen} assessment={a} courseId={course.id} onClose={() => setSaveAsOpen(false)} />
          </div>
        )}
      </TabPanel>

      <TabPanel tabsId="quiz-editor" value="preview" hidden={tab !== "preview"} className="space-y-3">
        <p className="text-sm text-slate-700">{t("quizEditor.preview.body")}</p>
        <div className="flex flex-wrap items-center gap-2">
          {a.languages.length > 1 && (
            <select aria-label={t("assessments.publish.previewLanguage")} className={`${inputCls} min-h-11 w-auto`} value={pLang} onChange={(e) => setPLang(e.target.value as Lang)}>
              {a.languages.map((l) => <option key={l} value={l}>{t(`courses.languages.${l}`)}</option>)}
            </select>
          )}
          <Button variant="primary" loading={pBusy} onClick={() => void preview()}>{t("assessments.publish.preview")}</Button>
        </div>
        <AssessmentError error={pError} />
      </TabPanel>

      <SectionDialog open={!!sectionDlg} section={sectionDlg?.section ?? null} assessment={a} languages={a.languages} defaultLanguage={defaultLanguage}
        busy={secBusy} error={secError} onSubmit={(v) => void submitSection(v)} onCancel={() => setSectionDlg(null)} />
      <ConfirmDialog open={!!toDelete} tone="danger" busy={secBusy} title={t("assessments.section.deleteTitle")}
        object={toDelete ? secName(toDelete) : undefined}
        effect={t("assessments.section.deleteBody", { name: toDelete ? secName(toDelete) : "" })}
        confirmLabel={t("assessments.section.delete")} onConfirm={() => void removeSection()} onCancel={() => setToDelete(null)}
        error={secError ? <AssessmentError error={secError} /> : undefined} />
      {find && (
        <FindQuestionsDrawer open courseId={course.id} assessmentId={aid} sectionId={find.sectionId} tab={find.tab}
          onClose={() => setFind(null)} onAdded={onFindAdded} />
      )}
      {undo && (
        <div role="status" data-quiz-keep-open
          className="fixed inset-x-4 bottom-4 z-40 flex items-center gap-3 rounded-2xl border border-slate-200 bg-white px-4 py-3 shadow-lg sm:left-auto sm:right-6 sm:w-96">
          <span className="min-w-0 flex-1 text-sm text-slate-800">{t("quizEditor.card.deleted")}</span>
          <Button variant="secondary" size="sm" loading={undoBusy} onClick={() => void runUndo()}>{t("quizEditor.card.undo")}</Button>
        </div>
      )}
    </div>
  );
}
