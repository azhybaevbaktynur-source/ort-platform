"use client";

// Phase 10 S3: the course Practice page. Students: published sets with best %, attempts and Start / Continue.
// Staff: the same rows plus a menu (Rename, Refresh questions, Delete) and "New set".
import React, { useCallback, useEffect, useState } from "react";
import { Dumbbell, Lock, Plus } from "lucide-react";
import { useRouter } from "next/navigation";
import { useTranslation } from "@/lib/i18n/context";
import { useCourse } from "@/components/lms/CourseContext";
import { useCanEditContent } from "@/components/lms/content/StaffGate";
import { ErrorMessage } from "@/components/lms/ErrorMessage";
import {
  Button, ConfirmDialog, Dialog, EmptyState, GoldPill, Input, LoadingState, MenuButton, PageHeader, Pagination, SectionTag, cn, toast,
} from "@/components/ui";
import { StudentPageHeader } from "@/components/lms/student/StudentPageHeader";
import { fmtDayMonthTime } from "@/components/lms/home/format";
import { startAttempt } from "@/lib/lms/attempts";
import { ORT_SECTIONS } from "@/lib/lms/contentTypes";
import { pickLocalized } from "@/lib/lms/localized";
import { templateUi } from "@/lib/lms/templates";
import { deletePractice, listPractice, updatePractice, type PracticeSetOut } from "@/lib/lms/practice";
import { PracticeDialog } from "./PracticeDialog";

/** The ORT sections a set draws from (its blocks), in ORT order; blocks without a known section add no tag. */
function sectionsOf(s: PracticeSetOut): string[] {
  const used = new Set(s.blocks.map((b) => b.section));
  return ORT_SECTIONS.filter((k) => used.has(k));
}

export function PracticeList() {
  const { lang, t } = useTranslation();
  const router = useRouter();
  const { course } = useCourse();
  const canEdit = useCanEditContent();
  const [items, setItems] = useState<PracticeSetOut[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [more, setMore] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [actionError, setActionError] = useState<unknown>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [dialog, setDialog] = useState(false);
  const [renaming, setRenaming] = useState<PracticeSetOut | null>(null);
  const [renameTo, setRenameTo] = useState("");
  const [deleting, setDeleting] = useState<PracticeSetOut | null>(null);

  const load = useCallback(async (next?: string | null) => {
    if (next) setMore(true); else setLoading(true);
    setError(null);
    try {
      const page = await listPractice(course.id, { cursor: next, limit: 25 });
      setItems((p) => (next ? [...p, ...page.items] : page.items));
      setCursor(page.next_cursor);
    } catch (e) { setError(e); } finally { setLoading(false); setMore(false); }
  }, [course.id]);
  useEffect(() => { void load(); }, [load]);

  const name = (s: PracticeSetOut) => pickLocalized(s.title, lang, course.default_language);

  const start = async (s: PracticeSetOut) => {
    setBusyId(s.id); setActionError(null);
    try {
      const id = s.open_attempt_id ?? (await startAttempt(course.id, s.id, {})).id;
      router.push(`/${lang}/courses/${course.id}/attempts/${id}`);
    } catch (e) { setActionError(e); setBusyId(null); }
  };

  const refresh = async (s: PracticeSetOut) => {
    setBusyId(s.id); setActionError(null);
    try { await updatePractice(course.id, s.id, {}); toast.success(t("practice.refreshed")); await load(); }
    catch (e) { setActionError(e); } finally { setBusyId(null); }
  };
  const rename = async () => {
    if (!renaming || !renameTo.trim()) return;
    setBusyId(renaming.id); setActionError(null);
    try {
      await updatePractice(course.id, renaming.id, { title: Object.fromEntries(course.languages.map((l) => [l, renameTo.trim()])) });
      setRenaming(null); await load();
    } catch (e) { setActionError(e); } finally { setBusyId(null); }
  };
  const remove = async () => {
    if (!deleting) return;
    setBusyId(deleting.id); setActionError(null);
    try { await deletePractice(course.id, deleting.id); setDeleting(null); await load(); }
    catch (e) { setDeleting(null); setActionError(e); } finally { setBusyId(null); }
  };

  const newButton = canEdit ? (
    <Button onClick={() => setDialog(true)} leftIcon={<Plus className="h-4 w-4" aria-hidden="true" />}>{t("practice.new")}</Button>
  ) : undefined;
  // Student UI U8 (STUDENT_UI_DESIGN §3.6, §5.1 d): students get the student pages' header (course name under the
  // title in exam-prep courses, whose course header is dropped here) and cards with section tags; staff keep theirs
  const examPrep = templateUi(course).studentLayout === "exam_prep";

  // §5.1 e (students): one primary button, on the set to continue (else the first open one); the rest secondary
  const startable = items.filter((s) => s.status === "published" && !s.locked);
  const primaryId = (startable.find((s) => s.open_attempt_id) ?? startable.find((s) => !s.my_attempts) ?? startable[0])?.id ?? null;

  return (
    <div className={cn(!canEdit && "space-y-5")}>
      {canEdit ? <PageHeader title={t("practice.title")} primaryAction={newButton} /> : (
        <StudentPageHeader title={t("practice.title")}
          subtitle={examPrep ? pickLocalized(course.title, lang, course.default_language) : undefined} />
      )}
      {canEdit && <p className="-mt-2 mb-4 max-w-2xl text-sm leading-5 text-slate-600">{t("practice.staffHint")}</p>}
      <ErrorMessage error={actionError} className="mb-4" />
      {loading ? <LoadingState /> : error ? <ErrorMessage error={error} onRetry={() => void load()} /> : items.length === 0 ? (
        <EmptyState mascot={canEdit ? "working" : "reading"} title={t(canEdit ? "practice.emptyStaff" : "practice.empty")} icon={<Dumbbell className="h-6 w-6" aria-hidden="true" />} action={newButton} />
      ) : (
        <ul className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {items.map((s) => (
            <li key={s.id} className="flex min-w-0 flex-col gap-3 rounded-card border border-slate-200 bg-white p-4 sm:p-5">
              {sectionsOf(s).length > 0 && (
                <div className="flex flex-wrap items-center gap-1.5">
                  {sectionsOf(s).map((k) => <SectionTag key={k} section={k} />)}
                </div>
              )}
              <div className="min-w-0">
                <h2 className="break-words text-base font-semibold leading-6 text-slate-900">{name(s)}</h2>
                <p className="mt-1 text-sm leading-5 text-slate-600">
                  {[
                    t("practice.questions", { n: s.item_count }),
                    s.my_best_percent !== null && s.my_best_percent !== undefined ? t("practice.best", { percent: Math.round(s.my_best_percent) }) : null,
                    s.my_attempts ? t("practice.attempts", { n: s.my_attempts }) : null,
                  ].filter(Boolean).join(" · ")}
                </p>
                {s.my_last_at && <p className="mt-0.5 text-sm leading-5 text-slate-600">{t("practice.lastAt", { date: fmtDayMonthTime(s.my_last_at, lang) })}</p>}
              </div>
              <div className="mt-auto flex flex-wrap items-center gap-2">
                {s.status === "published" && (s.locked ? ( // S3 access: practice of a platform course needs a pass
                  <span className="flex min-w-0 flex-1 flex-wrap items-center gap-2">
                    <span className="inline-flex items-center gap-1.5 text-sm text-slate-600"><Lock aria-hidden="true" className="h-4 w-4" />{t("practice.locked")}</span>
                    <GoldPill href={`/${lang}/pro`} icon={<Lock />} block className="justify-center">{t("practice.unlock")}</GoldPill>
                  </span>
                ) : (
                  <Button loading={busyId === s.id} onClick={() => void start(s)} className="flex-1 sm:flex-none"
                    variant={canEdit || s.id === primaryId ? "primary" : "secondary"}>
                    {t(s.open_attempt_id ? "practice.continue" : "practice.start")}<span className="sr-only">: {name(s)}</span>
                  </Button>
                ))}
                {canEdit && (
                  <MenuButton label={<span aria-label={t("practice.actions")}>…</span>} variant="secondary" align="end"
                    items={[
                      { id: "rename", label: t("practice.rename") },
                      { id: "refresh", label: t("practice.refresh") },
                      { id: "delete", label: t("practice.delete") },
                    ]}
                    onSelect={(id) => {
                      if (id === "rename") { setRenaming(s); setRenameTo(name(s)); }
                      else if (id === "refresh") void refresh(s);
                      else setDeleting(s);
                    }} />
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
      <Pagination nextCursor={cursor} onLoadMore={() => void load(cursor)} loading={more} />
      {canEdit && (
        <PracticeDialog open={dialog} courseId={course.id} languages={course.languages} defaultLanguage={course.default_language} set={null}
          onClose={() => setDialog(false)} onSaved={() => { setDialog(false); void load(); }} />
      )}
      <Dialog open={!!renaming} onClose={() => setRenaming(null)} busy={!!busyId && busyId === renaming?.id} title={t("practice.rename")}
        footer={<>
          <Button variant="secondary" onClick={() => setRenaming(null)}>{t("common.cancel")}</Button>
          <Button onClick={() => void rename()} loading={!!busyId && busyId === renaming?.id} disabled={!renameTo.trim()}>{t("common.save")}</Button>
        </>}>
        <Input label={t("practice.dialog.name")} value={renameTo} maxLength={200} onChange={(e) => setRenameTo(e.target.value)} />
      </Dialog>
      <ConfirmDialog open={!!deleting} title={t("practice.deleteTitle")} object={deleting ? name(deleting) : undefined} effect={t("practice.deleteEffect")}
        confirmLabel={t("practice.delete")} tone="danger" busy={!!busyId && busyId === deleting?.id}
        onConfirm={() => void remove()} onCancel={() => setDeleting(null)} />
    </div>
  );
}
