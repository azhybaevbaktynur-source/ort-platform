"use client";

// Student UI U8 (docs/phases/STUDENT_UI_DESIGN.md §3.4, §5.1 a): Сохранённые `/courses/{c}/saved`, the one place for the
// questions a student flagged during tests (tab Сохранённые, `GET /courses/{c}/my/saved`) and the mistakes notebook
// (tab Ошибки, `?tab=mistakes`; `/progress?tab=mistakes` redirects here). A saved row shows only questions whose results
// are visible (the server sends the question only then): section tag, test, date, the stem in two lines, "Открыть".
import React, { Suspense, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCourse } from "@/components/lms/CourseContext";
import { MistakesList } from "@/components/lms/progress/MistakesList";
import { StudentPageHeader } from "@/components/lms/student/StudentPageHeader";
import { Pager } from "@/components/lms/Pager";
import { useErrorText } from "@/components/lms/home/useErrorText";
import { fmtDayMonthTime } from "@/components/lms/home/format";
import { MathRenderer } from "@/components/math/MathRenderer";
import { EmptyState, ErrorState, SectionTag, Skeleton, TabPanel, Tabs, cn, focusRing } from "@/components/ui";
import { useTranslation } from "@/lib/i18n/context";
import { pickLocalized } from "@/lib/lms/localized";
import { listSaved, type SavedOut } from "@/lib/lms/progress";
import { inCourseSpace, templateUi } from "@/lib/lms/templates";

type Tab = "saved" | "mistakes";
type Shown = SavedOut & { item: NonNullable<SavedOut["item"]> };

function SavedList({ courseId }: { courseId: string }) {
  const { lang, t } = useTranslation();
  const errorText = useErrorText();
  const [items, setItems] = useState<Shown[] | null>(null);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<unknown>(null);

  const load = useCallback(async (next?: string | null) => {
    setLoading(true);
    setError(null);
    try {
      const page = await listSaved(courseId, next);
      const shown = page.items.filter((s): s is Shown => s.item !== null);
      setItems((prev) => (next && prev ? [...prev, ...shown] : shown));
      setCursor(page.next_cursor);
    } catch (e) {
      setError(e);
    } finally {
      setLoading(false);
    }
  }, [courseId]);
  useEffect(() => { void load(); }, [load]);

  if (error && items === null) return <ErrorState message={errorText(error)} onRetry={() => void load()} retrying={loading} />;
  if (items === null) {
    return (
      <div role="status" aria-live="polite" className="space-y-3">
        <span className="sr-only">{t("ui.loading")}</span>
        {[0, 1, 2].map((i) => <Skeleton key={i} className="h-28 w-full rounded-card" />)}
      </div>
    );
  }
  if (items.length === 0 && !cursor) {
    return <EmptyState mascot="thinking" title={t("student.saved.empty")} description={t("student.saved.emptyHint")} />;
  }
  return (
    <div className="space-y-3">
      <ul className="space-y-3" aria-busy={loading || undefined}>
        {items.map((s) => {
          const test = pickLocalized(s.assessment_title, lang) || t("assessments.untitled");
          const q = s.item.question;
          // a comparison question (math_1) has no stem: its two columns stand in for it
          const columns = q.data?.column_a || q.data?.column_b
            ? `${t("results.columnA")}: ${q.data.column_a || "—"} · ${t("results.columnB")}: ${q.data.column_b || "—"}` : "";
          const stem = q.stem?.trim() || columns;
          const n = s.item.position;
          return (
            <li key={`${s.attempt_id}:${s.position}`}
              className="flex min-w-0 flex-col gap-3 rounded-card border border-slate-200 bg-white p-4 sm:flex-row sm:items-center sm:gap-4 sm:p-5">
              <div className="min-w-0 flex-1 space-y-2">
                <p className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1 text-sm leading-5 text-slate-600">
                  {s.section && <SectionTag section={s.section} />}
                  <span className="min-w-0 break-words">
                    <span className="font-medium text-slate-800">{test}</span>
                    {s.submitted_at && <> · <span className="whitespace-nowrap">{fmtDayMonthTime(s.submitted_at, lang)}</span></>}
                  </span>
                </p>
                {stem ? (
                  <MathRenderer content={stem} className="line-clamp-2 break-words text-base leading-6 text-slate-900" />
                ) : (
                  <p className="text-base leading-6 text-slate-900">{t("student.saved.question", { n })}</p>
                )}
              </div>
              <Link href={`/${lang}/courses/${courseId}/attempts/${s.attempt_id}/result#item-${n}`}
                className={cn("inline-flex min-h-11 shrink-0 items-center justify-center self-start rounded-control border border-slate-300 bg-white px-4 text-sm font-semibold text-slate-800 hover:bg-slate-50 sm:self-center", focusRing)}>
                {t("student.saved.open")}<span className="sr-only">: {t("student.saved.question", { n })}, {test}</span>
              </Link>
            </li>
          );
        })}
      </ul>
      {items.length === 0 && cursor && <p className="text-sm leading-5 text-slate-600">{t("student.saved.hiddenOnPage")}</p>}
      {error ? <ErrorState variant="inline" message={errorText(error)} onRetry={() => void load(cursor)} /> : null}
      <Pager nextCursor={cursor} loading={loading} onMore={() => void load(cursor)} />
    </div>
  );
}

function SavedTabs() {
  const { lang, t } = useTranslation();
  const { course } = useCourse();
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const fromUrl: Tab = params.get("tab") === "mistakes" ? "mistakes" : "saved";
  const [tab, setTab] = useState<Tab>(fromUrl);
  useEffect(() => { setTab(fromUrl); }, [fromUrl]);
  const choose = (v: string) => {
    const next = v === "mistakes" ? "mistakes" : "saved";
    setTab(next);
    router.replace(next === "mistakes" ? `${pathname}?tab=mistakes` : pathname, { scroll: false });
  };
  const id = "saved-tabs";
  return (
    <div className="space-y-5">
      {/* exam-prep courses drop the course header here, so the course name is the subtitle */}
      {/* step 3a S2: the compact course header names the course */}
      <StudentPageHeader title={t("student.saved.title")}
        subtitle={templateUi(course).studentLayout === "exam_prep" && !inCourseSpace(course) ? pickLocalized(course.title, lang, course.default_language) : undefined} />
      <Tabs id={id} label={t("student.saved.tabsLabel")} value={tab} onChange={choose}
        items={[{ id: "saved", label: t("student.saved.tabs.saved") }, { id: "mistakes", label: t("student.saved.tabs.mistakes") }]} />
      <TabPanel tabsId={id} value="saved" hidden={tab !== "saved"}>
        {tab === "saved" && <SavedList courseId={course.id} />}
      </TabPanel>
      <TabPanel tabsId={id} value="mistakes" hidden={tab !== "mistakes"}>
        {tab === "mistakes" && <MistakesList courseId={course.id} />}
      </TabPanel>
    </div>
  );
}

/** Сохранённые: flagged questions and the mistakes notebook. The server answers 404/403 for anyone but the student. */
export function SavedPage() {
  return (
    <Suspense fallback={null}>
      <SavedTabs />
    </Suspense>
  );
}
