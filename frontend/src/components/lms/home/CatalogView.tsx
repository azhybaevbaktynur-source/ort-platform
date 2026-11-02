"use client";

// Phase 6b S6b: the course catalog on its own page (/courses/catalog; was a block above "My courses", UX S3).
// UX S11: the student count only from 10 up (an empty course does not look dead); language names, not codes.
// Phase 9 S4: search and filters, the organization and a mode badge on each card, the title opens the course landing,
// form-mode courses offer "Apply" (or show the student's application status).
import React, { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { KeyRound, LayoutGrid, SearchX, Users } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { isActiveMember, isFormMode, joinOpenCourse, listCatalog, type CatalogCourseOut, type CatalogFilters as Filters } from "@/lib/lms/catalog";
import { Button, EmptyState, ErrorState, LinkButton, PageHeader, Pagination, Skeleton } from "@/components/ui";
import { COURSE_GRID, CourseCard } from "@/components/lms/course/CourseCard";
import { CatalogFilters } from "@/components/lms/catalog/CatalogFilters";
import { CatalogModeBadge } from "@/components/lms/catalog/CatalogModeBadge";
import { ApplicationStatusBadge } from "@/components/lms/catalog/ApplicationStatus";
import { useErrorText } from "./useErrorText";

const SHOW_COUNT_FROM = 10;

function CatalogSkeleton() {
  const { t } = useTranslation();
  return (
    <div role="status" aria-live="polite">
      <span className="sr-only">{t("ui.loading")}</span>
      <div aria-hidden="true" className={COURSE_GRID}>
        {Array.from({ length: 3 }, (_, i) => (
          <div key={i} className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
            <Skeleton className="h-24 w-full rounded-none" />
            <div className="p-4">
              <Skeleton className="mb-2 h-4 w-2/3" />
              <Skeleton className="mb-4 h-4 w-1/2" />
              <Skeleton className="h-11 w-full rounded-xl" />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export function CatalogView() {
  const { lang, t } = useTranslation();
  const router = useRouter();
  const errorText = useErrorText();
  const [items, setItems] = useState<CatalogCourseOut[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [joining, setJoining] = useState<string | null>(null);
  const [joinError, setJoinError] = useState<{ id: string; error: unknown } | null>(null);
  // --- Phase 9 S4 ---
  const [filters, setFilters] = useState<Filters>({});
  const [orgs, setOrgs] = useState<Map<string, string>>(new Map());
  const seq = useRef(0);
  const filtered = !!(filters.q || filters.language || filters.mode || filters.organization_id);
  // --- Phase 9 S4 end ---

  const load = useCallback(async (next?: string | null) => {
    const mine = ++seq.current; // a newer search wins over a slower older one
    setLoading(true);
    setError(null);
    try {
      const page = await listCatalog(next, 12, filters);
      if (mine !== seq.current) return;
      setItems((prev) => (next ? [...prev, ...page.items] : page.items));
      setCursor(page.next_cursor);
      setOrgs((prev) => {
        const m = new Map(prev);
        let changed = false;
        for (const c of page.items) {
          // a personal organization's name means nothing to students: not a filter either
          if (c.organization_id && c.organization_display_name && !m.has(c.organization_id)) { m.set(c.organization_id, c.organization_display_name); changed = true; }
        }
        return changed ? m : prev;
      });
    } catch (e) {
      if (mine === seq.current) setError(e);
    } finally {
      if (mine === seq.current) setLoading(false);
    }
  }, [filters]);
  useEffect(() => { void load(); }, [load]);

  const join = async (course: CatalogCourseOut) => {
    setJoining(course.id);
    setJoinError(null);
    try {
      const res = await joinOpenCourse(course.id);
      router.push(`/${lang}/courses/${res.course.id}`);
    } catch (e) {
      setJoinError({ id: course.id, error: e });
      setJoining(null);
    }
  };

  const landing = (c: CatalogCourseOut) => `/${lang}/courses/catalog/${c.id}`;

  const action = (c: CatalogCourseOut) => {
    if (isActiveMember(c)) {
      return <LinkButton variant="secondary" fullWidth href={`/${lang}/courses/${c.id}`}>{t("catalog.open")}</LinkButton>;
    }
    if (c.enrollment_mode === "open") {
      return (
        <Button variant="secondary" fullWidth loading={joining === c.id} disabled={joining !== null && joining !== c.id} onClick={() => void join(c)}>
          {t("catalog.join")}
        </Button>
      );
    }
    // --- Phase 9 S4: form modes ---
    if (c.my_application?.status === "pending") {
      return (
        <div className="flex flex-wrap items-center justify-between gap-2">
          <ApplicationStatusBadge status="pending" audience="student" />
          <LinkButton variant="link" href={landing(c)}>{t("catalog.viewApplication")}</LinkButton>
        </div>
      );
    }
    if (isFormMode(c.enrollment_mode) && c.has_active_form) {
      return <LinkButton variant="secondary" fullWidth href={`${landing(c)}/apply`}>{t("catalog.apply")}</LinkButton>;
    }
    // --- Phase 9 S4 end ---
    return (
      <p className="text-sm leading-6 text-slate-600">
        {c.enrollment_mode === "invite_code" ? t("catalog.needsCode") : t("catalog.closed")}
      </p>
    );
  };

  return (
    <div className="w-full">
      <PageHeader title={t("catalog.title")} description={t("catalog.subtitle")}
        breadcrumbs={[{ label: t("lms.nav.myCourses"), href: `/${lang}/courses` }, { label: t("catalog.title") }]}
        secondaryActions={<LinkButton variant="secondary" href={`/${lang}/courses/join`} leftIcon={<KeyRound className="h-4 w-4" aria-hidden="true" />}>{t("home.primary.join")}</LinkButton>} />

      <CatalogFilters value={filters} onChange={setFilters}
        organizations={Array.from(orgs, ([id, name]) => ({ id, name })).sort((a, b) => a.name.localeCompare(b.name))} />

      {/* Phase 9 UX: how many courses a search found (cursor pages: "shown, more below" while more pages exist) */}
      <p role="status" aria-live="polite" className="mb-3 text-sm leading-6 text-slate-600 empty:hidden">
        {filtered && !loading && !error && items.length > 0
          ? t(cursor ? "catalog.resultCountMore" : "catalog.resultCount", { count: items.length }) : null}
      </p>
      {error && items.length === 0 ? <ErrorState message={errorText(error)} onRetry={() => void load()} retrying={loading} /> : null}
      {error && items.length > 0 ? <ErrorState variant="inline" message={errorText(error)} onRetry={() => void load(cursor)} className="mb-4" /> : null}
      {loading && items.length === 0 && !error && <CatalogSkeleton />}
      {!loading && !error && items.length === 0 && (filtered ? (
        <EmptyState icon={<SearchX />} title={t("catalog.noResults.title")} description={t("catalog.noResults.body")}
          action={<Button variant="secondary" onClick={() => setFilters({})}>{t("ui.resetFilters")}</Button>} />
      ) : (
        <EmptyState icon={<LayoutGrid />} title={t("home.catalogEmpty.title")} description={t("home.catalogEmpty.body")}
          action={<LinkButton href={`/${lang}/courses/join`}>{t("home.primary.join")}</LinkButton>} />
      ))}
      {items.length > 0 && (
        <ul className={COURSE_GRID} aria-busy={loading || undefined}>
          {items.map((c) => (
            <CourseCard key={c.id} course={c} href={landing(c)} headingLevel={2}
              badges={<CatalogModeBadge mode={c.enrollment_mode} />}
              meta={c.student_count >= SHOW_COUNT_FROM ? (
                <span className="inline-flex items-center gap-1">
                  <Users className="h-4 w-4" aria-hidden="true" />
                  {t("catalog.students", { count: c.student_count })}
                </span>
              ) : undefined}
              action={(
                <>
                  {action(c)}
                  {joinError?.id === c.id && <ErrorState variant="inline" message={errorText(joinError.error)} className="mt-3" />}
                </>
              )} />
          ))}
        </ul>
      )}
      <Pagination nextCursor={cursor} loading={loading} onLoadMore={() => void load(cursor)} />
    </div>
  );
}
