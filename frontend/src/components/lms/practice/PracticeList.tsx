"use client";

// Phase 10 S3: the course Practice page. Students: published sets with best %, attempts and Start / Continue.
// Staff: the same rows plus a menu (Rename, Refresh questions, Delete) and "New set".
import React, { useCallback, useEffect, useState } from "react";
import { Dumbbell, Plus } from "lucide-react";
import { useRouter } from "next/navigation";
import { useTranslation } from "@/lib/i18n/context";
import { useCourse } from "@/components/lms/CourseContext";
import { useCanEditContent } from "@/components/lms/content/StaffGate";
import { ErrorMessage } from "@/components/lms/ErrorMessage";
import { Button, ConfirmDialog, Dialog, EmptyState, Input, LoadingState, MenuButton, PageHeader, Pagination, toast } from "@/components/ui";
import { startAttempt } from "@/lib/lms/attempts";
import { pickLocalized } from "@/lib/lms/localized";
import { deletePractice, listPractice, updatePractice, type PracticeSetOut } from "@/lib/lms/practice";
import { PracticeDialog } from "./PracticeDialog";

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

  return (
    <div>
      <PageHeader title={t("practice.title")} primaryAction={newButton} />
      <ErrorMessage error={actionError} className="mb-4" />
      {loading ? <LoadingState /> : error ? <ErrorMessage error={error} onRetry={() => void load()} /> : items.length === 0 ? (
        <EmptyState title={t(canEdit ? "practice.emptyStaff" : "practice.empty")} icon={<Dumbbell className="h-6 w-6" aria-hidden="true" />} action={newButton} />
      ) : (
        <ul className="space-y-3">
          {items.map((s) => (
            <li key={s.id} className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-200 bg-white p-4 sm:p-5">
              <div className="min-w-0">
                <h2 className="break-words text-base font-semibold text-slate-900">{name(s)}</h2>
                <p className="mt-0.5 text-sm text-slate-600">
                  {[
                    t("practice.questions", { n: s.item_count }),
                    s.my_best_percent !== null && s.my_best_percent !== undefined ? t("practice.best", { percent: Math.round(s.my_best_percent) }) : null,
                    s.my_attempts ? t("practice.attempts", { n: s.my_attempts }) : null,
                  ].filter(Boolean).join(" · ")}
                </p>
              </div>
              <div className="flex items-center gap-2">
                {s.status === "published" && (
                  <Button loading={busyId === s.id} onClick={() => void start(s)}>
                    {t(s.open_attempt_id ? "practice.continue" : "practice.start")}<span className="sr-only">: {name(s)}</span>
                  </Button>
                )}
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
