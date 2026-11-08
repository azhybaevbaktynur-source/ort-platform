"use client";

// S3 access, platform admin: which tests of platform courses are paid (one switch per test, audited) and whether
// practice is free per platform course. The ORT builder screens are unchanged (rule 9): the tier is set only here.
import React, { useCallback, useEffect, useState } from "react";
import { useTranslation } from "@/lib/i18n/context";
import { pickLocalized } from "@/lib/lms/localized";
import { fmtApiDate } from "@/lib/format";
import {
  listExams, listPlatformCourses, setExamTier, setPracticeFree, type AccessTier, type ExamOut, type PlatformCourseOut,
} from "@/lib/lms/access";
import { Badge, Card, EmptyState, ErrorState, PageHeader, Select, Skeleton, Switch, Table, toast, type TableColumn } from "@/components/ui";
import { useAdminCrumbs } from "@/components/lms/admin/AdminShell";
import { useErrorText } from "@/components/lms/home/useErrorText";

export default function AdminPaidExamsPage() {
  const { lang, t } = useTranslation();
  const crumbs = useAdminCrumbs();
  const errorText = useErrorText();
  const [courses, setCourses] = useState<PlatformCourseOut[] | null>(null);
  const [courseId, setCourseId] = useState("");
  const [tier, setTier] = useState<AccessTier | "">("");
  const [items, setItems] = useState<ExamOut[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  useEffect(() => {
    listPlatformCourses().then(setCourses).catch(() => setCourses([]));
  }, []);
  const load = useCallback(async (next?: string | null) => {
    setLoading(true);
    setError(null);
    try {
      const page = await listExams({ cursor: next, course_id: courseId || undefined, tier });
      setItems((prev) => (next ? [...prev, ...page.items] : page.items));
      setCursor(page.next_cursor);
    } catch (e) { setError(e); } finally { setLoading(false); }
  }, [courseId, tier]);
  useEffect(() => { void load(); }, [load]);

  const toggle = async (e: ExamOut, paid: boolean) => {
    setBusyId(e.id);
    try {
      const out = await setExamTier(e.id, paid ? "paid" : "free");
      setItems((prev) => prev.map((x) => (x.id === out.id ? out : x)));
      toast.success(t("access.admin.exams.saved"));
    } catch (err) { toast.error(errorText(err)); } finally { setBusyId(null); }
  };
  const togglePractice = async (c: PlatformCourseOut, free: boolean) => {
    setBusyId(c.id);
    try {
      const out = await setPracticeFree(c.id, free);
      setCourses((prev) => (prev ?? []).map((x) => (x.id === out.id ? out : x)));
      toast.success(t("access.admin.exams.saved"));
    } catch (err) { toast.error(errorText(err)); } finally { setBusyId(null); }
  };

  const columns: TableColumn<ExamOut>[] = [
    { key: "exam", header: t("access.admin.exams.columns.exam"), primary: true, cell: (e) => (
      <span className="break-words font-medium text-slate-900">{pickLocalized(e.title, lang) || t("assessments.untitled")}</span>
    ) },
    { key: "course", header: t("access.admin.exams.columns.course"), cell: (e) => <span className="text-sm text-slate-700">{pickLocalized(e.course_title, lang)}</span> },
    { key: "published", header: t("access.admin.exams.columns.published"), cell: (e) => e.published_at
      ? <span className="text-sm text-slate-600">{fmtApiDate(e.published_at, lang)}</span>
      : <Badge>{t("access.admin.exams.draft")}</Badge>, nowrap: true },
    { key: "paid", header: t("access.admin.exams.columns.paid"), cell: (e) => (
      <Switch label={<span className="sr-only">{t("access.admin.exams.paidToggle", { title: pickLocalized(e.title, lang) })}</span>}
        checked={e.access_tier === "paid"} busy={busyId === e.id} onChange={(v) => void toggle(e, v)} />
    ) },
  ];

  const courseOptions = [{ value: "", label: t("access.admin.exams.allCourses") },
    ...(courses ?? []).map((c) => ({ value: c.id, label: pickLocalized(c.title, lang) }))];
  return (
    <div>
      <PageHeader title={t("access.admin.pages.exams")} description={t("access.admin.subtitles.exams")}
        breadcrumbs={crumbs({ label: t("access.admin.pages.exams") })} />
      <p className="mb-4 max-w-3xl text-sm leading-5 text-slate-700">{t("access.admin.exams.hint")}</p>
      <Table caption={t("access.admin.exams.title")} columns={columns} rows={items} rowKey={(e) => e.id}
        search={
          <div className="flex flex-wrap gap-3">
            <Select id="exam-course" label={t("access.admin.exams.course")} value={courseId} options={courseOptions}
              onChange={(e) => setCourseId(e.target.value)} containerClassName="w-full sm:w-72" />
            <Select id="exam-tier" label={t("access.admin.exams.tier")} value={tier} containerClassName="w-full sm:w-56"
              onChange={(e) => setTier(e.target.value as AccessTier | "")}
              options={[{ value: "", label: t("access.admin.exams.allTiers") }, { value: "paid", label: t("access.paid") }, { value: "free", label: t("access.free") }]} />
          </div>
        }
        loading={loading && items.length === 0}
        error={error && items.length === 0 ? <ErrorState variant="inline" message={errorText(error)} onRetry={() => void load()} /> : undefined}
        empty={<EmptyState variant="plain" title={t("access.admin.exams.empty")} />}
        pagination={{ nextCursor: cursor, loading, onLoadMore: () => void load(cursor) }} />
      <Card className="mt-8" title={t("access.admin.exams.practiceTitle")} description={t("access.admin.exams.practiceHint")}>
        {courses === null ? <Skeleton className="h-6 w-1/2" /> : courses.length === 0 ? (
          <p className="text-sm text-slate-600">{t("access.admin.exams.practiceEmpty")}</p>
        ) : (
          <ul className="divide-y divide-slate-100">
            {courses.map((c) => (
              <li key={c.id} className="flex flex-wrap items-center justify-between gap-3 py-2">
                <span className="min-w-0 break-words font-medium text-slate-900">{pickLocalized(c.title, lang)}</span>
                <Switch label={t("access.admin.exams.practiceFree")} checked={c.practice_free} busy={busyId === c.id}
                  onChange={(v) => void togglePractice(c, v)} containerClassName="w-full sm:w-auto" />
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
