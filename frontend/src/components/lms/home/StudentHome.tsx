"use client";

// UX rework (UX_REWORK_DESIGN C): the student dashboard, one call (`GET /me/home`). Title with two secondary actions,
// banners when needed, course cards on the left, "To do", recent grades and announcements on the right. Phone: to-do
// first when there is any, then the cards. A teacher's Learning tab is the same screen.
import React, { useCallback, useEffect, useState } from "react";
import { BookOpen, KeyRound, LayoutGrid, Trophy } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { getHome } from "@/lib/lms/home";
import type { HomeOut } from "@/lib/lms/homeTypes";
import { listMyCourses } from "@/lib/lms/courses";
import type { CourseCard } from "@/lib/lms/types";
import { pickLocalized } from "@/lib/lms/localized";
import { Badge, Button, EmptyState, ErrorState, LinkButton, Pagination, Skeleton, cn } from "@/components/ui";
import { useGradeText } from "@/components/lms/results/GradeBadge";
import { PendingApplicationsLine } from "@/components/lms/catalog/ApplicationStatus"; // Phase 9 S4
import { DashboardCourseCard } from "./DashboardCourseCard";
import { fmtDayMonthTime } from "./format";
import { SideRow, SideSection, TodoRows } from "./TodoList";
import { useErrorText } from "./useErrorText";

const CARD_GRID = "grid gap-4 sm:grid-cols-2 xl:grid-cols-3 min-[1700px]:grid-cols-4";

/** Small celebration: gold is for achievements only (UX §5). */
function PersonalBestBadge() {
  const { t } = useTranslation();
  return (
    <Badge icon={<Trophy aria-hidden="true" />} className="border-gold-300 bg-gold-100 text-gold-900">{t("home.personalBest")}</Badge>
  );
}

function CourseCards({ data }: { data: HomeOut }) {
  const { lang, t } = useTranslation();
  const errorText = useErrorText();
  const [more, setMore] = useState<CourseCard[] | null>(null); // every course, once the student asked for them
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const load = useCallback(async (next?: string | null) => {
    setLoading(true);
    setError(null);
    try {
      const page = await listMyCourses("learning", next);
      setMore((p) => (next && p ? [...p, ...page.items] : page.items));
      setCursor(page.next_cursor);
    } catch (e) {
      setError(e);
    } finally {
      setLoading(false);
    }
  }, []);
  const known = new Map(data.courses.map((c) => [c.id, c]));
  const teacherOf = (id: string, name: string | null) => (known.get(id)?.is_platform_course ? t("home.platformCourse") : name);
  return (
    <>
      <ul className={CARD_GRID}>
        {more
          ? more.map((c) => (
            <DashboardCourseCard key={c.id} id={c.id} title={pickLocalized(c.title, lang, c.default_language) || t("courses.list.untitled")}
              teacher={teacherOf(c.id, c.owner_display_name)} nextDue={known.get(c.id)?.next_due_at} />
          ))
          : data.courses.map((c) => (
            <DashboardCourseCard key={c.id} id={c.id} title={pickLocalized(c.title, lang) || t("courses.list.untitled")}
              teacher={teacherOf(c.id, c.owner_display_name)} nextDue={c.next_due_at} />
          ))}
      </ul>
      {error ? <ErrorState variant="inline" message={errorText(error)} onRetry={() => void load(cursor)} className="mt-3" /> : null}
      {more
        ? <Pagination nextCursor={cursor} loading={loading} onLoadMore={() => void load(cursor)} className="mt-2" />
        : data.courses_total > data.courses.length && (
          <div className="mt-3">
            <Button variant="link" loading={loading} onClick={() => void load()}>{t("home.courses.showAll", { n: data.courses_total })}</Button>
          </div>
        )}
    </>
  );
}

function Dashboard({ data }: { data: HomeOut }) {
  const { lang, t } = useTranslation();
  const gradeText = useGradeText();
  const base = `/${lang}/courses`;
  const untitled = t("assessments.untitled");
  const todo = data.todo ?? [];
  const grades = data.latest_results.slice(0, 3);
  const news = (data.announcements ?? []).slice(0, 3);
  const pendingApps = <PendingApplicationsLine items={data.pending_applications ?? []} />;

  if (data.courses_total === 0 && todo.length === 0) {
    return (
      <div className="space-y-6">
        {pendingApps}
        <EmptyState icon={<BookOpen />} title={t("home.courses.emptyTitle")} description={t("home.courses.emptyBody")}
          action={(
            <>
              <LinkButton size="lg" href={`${base}/join`} leftIcon={<KeyRound aria-hidden="true" className="h-5 w-5" />}>{t("home.primary.join")}</LinkButton>
              <LinkButton size="lg" href={`${base}/catalog`} leftIcon={<LayoutGrid aria-hidden="true" className="h-5 w-5" />}>{t("home.openCatalog")}</LinkButton>
            </>
          )} />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {pendingApps}
      {/* phones: to-do (when there is any), cards, the rest. From `lg` the cards span the left column. */}
      <div className="flex flex-col gap-6 lg:grid lg:grid-cols-[minmax(0,1fr)_340px] lg:grid-rows-[auto_1fr] lg:items-start">
        <div className={cn("min-w-0 lg:col-start-2 lg:row-start-1", todo.length === 0 && "order-2 lg:order-none")}>
          <SideSection id="home-todo" title={t("home.todo.title")}>
            {todo.length > 0
              ? <TodoRows rows={todo} />
              : <p className="px-3 py-3 text-base leading-6 text-slate-600 sm:text-sm">{t("home.todo.empty")}</p>}
          </SideSection>
        </div>
        <section aria-labelledby="home-courses" className="min-w-0 lg:col-start-1 lg:row-span-2 lg:row-start-1">
          <h2 id="home-courses" className="mb-2 text-lg font-semibold leading-7 text-slate-900">{t("home.courses.title")}</h2>
          <CourseCards data={data} />
        </section>
        {(grades.length > 0 || news.length > 0) && (
          <div className="order-3 min-w-0 space-y-6 lg:order-none lg:col-start-2 lg:row-start-2">
            {grades.length > 0 && (
              <SideSection id="home-results" title={t("home.results.title")}>
                <ul className="divide-y divide-slate-100">
                  {grades.map((r) => {
                    // a released manual grade opens its assignment page (grade and feedback)
                    const href = r.kept_attempt_id ? `${base}/${r.course_id}/attempts/${r.kept_attempt_id}/result`
                      : r.assignment_id && r.kind && r.kind !== "quiz" ? `${base}/${r.course_id}/assignments/${r.assignment_id}` : `${base}/${r.course_id}/grades`;
                    return (
                      <SideRow key={r.assignment_id ?? r.assessment_id ?? href} href={href} title={pickLocalized(r.title, lang) || untitled}
                        lines={(
                          <>
                            <span className="block break-words">{pickLocalized(r.course_title, lang)}</span>
                            {r.is_personal_best && <span className="mt-1 block"><PersonalBestBadge /></span>}
                          </>
                        )}
                        aside={gradeText(r, r.scheme_type ?? undefined) || null} />
                    );
                  })}
                </ul>
              </SideSection>
            )}
            {news.length > 0 && (
              <SideSection id="home-announcements" title={t("home.announcements.title")}>
                <ul className="divide-y divide-slate-100">
                  {news.map((r) => (
                    <SideRow key={r.id} href={`${base}/${r.course_id}/announcements`} title={r.title}
                      lines={(
                        <>
                          <span className="block break-words">{pickLocalized(r.course_title, lang) || t("courses.list.untitled")}</span>
                          <span className="block">{fmtDayMonthTime(r.published_at, lang)}</span>
                        </>
                      )} />
                  ))}
                </ul>
              </SideSection>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function DashboardSkeleton() {
  const { t } = useTranslation();
  return (
    <div role="status" aria-live="polite">
      <span className="sr-only">{t("ui.loading")}</span>
      <div aria-hidden="true" className="flex flex-col gap-6 lg:grid lg:grid-cols-[minmax(0,1fr)_340px] lg:items-start">
        <div className="min-w-0 lg:col-start-1 lg:row-start-1">
          <Skeleton className="mb-3 h-6 w-32" />
          <div className={CARD_GRID}>
            {[0, 1, 2].map((i) => (
              <div key={i} className="overflow-hidden rounded-2xl border border-slate-200 bg-white">
                <Skeleton className="h-24 w-full rounded-none" />
                <div className="space-y-2 p-4"><Skeleton className="h-4 w-2/3" /><Skeleton className="h-4 w-1/2" /></div>
              </div>
            ))}
          </div>
        </div>
        <div className="min-w-0 lg:col-start-2 lg:row-start-1">
          <Skeleton className="mb-3 h-6 w-32" />
          <div className="space-y-3 rounded-2xl border border-slate-200 bg-white p-4">
            <Skeleton className="h-5 w-3/4" /><Skeleton className="h-5 w-2/3" /><Skeleton className="h-5 w-3/4" />
          </div>
        </div>
      </div>
    </div>
  );
}

/** The student dashboard. `embedded`: inside the Teaching/Learning tabs (the page already has its h1). */
export function StudentHome({ embedded = false }: { embedded?: boolean }) {
  const { lang, t } = useTranslation();
  const errorText = useErrorText();
  const [data, setData] = useState<HomeOut | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await getHome());
    } catch (e) {
      setError(e);
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => { void load(); }, [load]);

  const Title = embedded ? "h2" : "h1";
  const isNew = !!data && data.courses_total === 0 && (data.todo ?? []).length === 0; // its empty state has the two actions
  return (
    <div className="w-full space-y-6">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <Title className="text-2xl font-bold leading-8 text-slate-900">{t("home.dashboard")}</Title>
        {!isNew && (
          <div className="flex flex-wrap gap-2">
            <LinkButton variant="secondary" href={`/${lang}/courses/join`} leftIcon={<KeyRound aria-hidden="true" className="h-4 w-4" />}>{t("home.primary.join")}</LinkButton>
            <LinkButton variant="secondary" href={`/${lang}/courses/catalog`} leftIcon={<LayoutGrid aria-hidden="true" className="h-4 w-4" />}>{t("lms.nav.catalog")}</LinkButton>
          </div>
        )}
      </header>
      {error && !data ? (
        <ErrorState message={errorText(error)} onRetry={() => void load()} retrying={loading} />
      ) : !data ? (
        <DashboardSkeleton />
      ) : (
        <Dashboard data={data} />
      )}
    </div>
  );
}
