"use client";

// Phase 6b S6b: the course catalog on its own page (/courses/catalog; was a block above "My courses", UX S3).
// F7c: the shared CourseCard (cover, one meta line, one action); search and language chips, the rest under "More filters".
// Phase 9 S4: search and filters, the organization and a mode badge on each card, the title opens the course landing,
// form-mode courses offer "Apply" (or show the student's application status).
// Step 3a S4 (STUDENT_IA_DESIGN §2.4, decision N9): family chips ОРТ · НЦТ · Курсы преподавателей (only families with
// listed courses, from `GET /catalog/exams`; `?exam=` in the URL; the default chip is the family of the student's
// newest exam course, else ОРТ). A family view lists its courses by subject section (`GET /catalog/courses?exam=`:
// main courses first); «Курсы преподавателей» is the list with search and filters (`exam=other`: no family). Without
// any family the page is the plain list as before. A quiet «Подобрать курсы» opens the choose step.
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { KeyRound, Sparkles } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { isActiveMember, isFormMode, joinOpenCourse, listCatalog, listExams, type CatalogCourseOut, type CatalogFilters as Filters } from "@/lib/lms/catalog";
import { chooseCoursesHref, defaultFamily, subjectSections } from "@/lib/lms/chooseCourses";
import { EXAM_SUBJECTS } from "@/lib/lms/types";
import { Badge, Button, EmptyState, ErrorState, LinkButton, PageHeader, Pagination, Skeleton, cn, focusRing } from "@/components/ui";
import { COURSE_GRID, CourseCard } from "@/components/lms/course/CourseCard";
import { CatalogFilters } from "@/components/lms/catalog/CatalogFilters";
import { ApplicationStatusBadge } from "@/components/lms/catalog/ApplicationStatus";
import { useErrorText } from "./useErrorText";
import { useLmsMe } from "@/lib/lms/useLmsMe"; // fix round 1b
import { hidesLearning } from "@/lib/lms/shellKind"; // fix round 1b
import { useStudentShellDataContext } from "@/components/lms/student/StudentShellDataContext"; // step 3a S3

function CatalogSkeleton() {
  const { t } = useTranslation();
  return (
    <div role="status" aria-live="polite">
      <span className="sr-only">{t("ui.loading")}</span>
      <div aria-hidden="true" className={COURSE_GRID}>
        {Array.from({ length: 3 }, (_, i) => (
          <div key={i} className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
            <Skeleton className="h-[150px] w-full rounded-none" />
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

/** A chip's key: one family, or `other` (the courses without a family: «Курсы преподавателей»). */
type ExamView = "ort" | "nct" | "other";
/** `all`: no family exists, the plain list as before step 3a S4. */
type View = ExamView | "all";
const asView = (v: string | null): ExamView | null => (v === "ort" || v === "nct" || v === "other" ? v : null);
/** A family view shows the whole family at once (≤ 50 listed courses by design); a cursor still follows. */
const FAMILY_PAGE = 48;

export function CatalogView() {
  const { lang, t } = useTranslation();
  const router = useRouter();
  const errorText = useErrorText();
  // fix round 1b (owner decision 2026-11-12): people who teach never join as students; Student view where they teach
  const teaches = hidesLearning(useLmsMe().me);
  // step 3a S3: a global page of the student frame (sidebar Каталог): no breadcrumbs there
  const shell = useStudentShellDataContext();
  const studentFrame = !!shell;
  // --- step 3a S4: the chips ---
  const asked = asView(useSearchParams().get("exam"));
  const [families, setFamilies] = useState<string[] | null>(null);
  useEffect(() => {
    let live = true;
    listExams().then((rows) => { if (live) setFamilies(rows.map((r) => r.family)); })
      .catch(() => { if (live) setFamilies([]); }); // no chips: the plain list still works
    return () => { live = false; };
  }, []);
  const mine = shell?.courses;
  // before the families are known the default chip is guessed (ОРТ or the newest exam course's family), so the list
  // loads at once; it switches only when that family turns out to have no listed course
  const view: View = useMemo(() => {
    if (asked) return asked;
    const guess = (defaultFamily(families ?? ["ort", "nct"], mine ?? []) ?? "all") as View;
    return families && families.length === 0 ? "all" : guess;
  }, [asked, families, mine]);
  const familyView = view === "ort" || view === "nct";
  const chips: ExamView[] = families && families.length > 0 ? [...(["ort", "nct"] as const).filter((f) => families.includes(f)), "other"] : [];
  // --- step 3a S4 end ---
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
  // step 3a S4: a family view has no search or filters (its sections are short); the list views keep them
  const filtered = !familyView && !!(filters.q || filters.language || filters.mode || filters.organization_id);
  // --- Phase 9 S4 end ---
  const shownView = useRef<View>(view);

  const load = useCallback(async (next?: string | null) => {
    const mine = ++seq.current; // a newer search wins over a slower older one
    setLoading(true);
    setError(null);
    if (!next && shownView.current !== view) { shownView.current = view; setItems([]); setCursor(null); } // another chip
    try {
      const page = familyView
        ? await listCatalog(next, FAMILY_PAGE, { exam: view })
        : await listCatalog(next, 12, { ...filters, exam: view === "other" ? "other" : undefined });
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
  }, [filters, view, familyView]);
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

  /** a badge only when it matters: a code or an application is needed to get in */
  const modeBadge = (c: CatalogCourseOut) => {
    if (isActiveMember(c) || c.my_application) return undefined;
    if (c.enrollment_mode === "invite_code") return <Badge tone="neutral">{t("courses.card.byCode")}</Badge>;
    if (isFormMode(c.enrollment_mode)) return <Badge tone="info">{t("courses.card.byApplication")}</Badge>;
    return undefined;
  };

  const landing = (c: CatalogCourseOut) => `/${lang}/courses/catalog/${c.id}`;

  const action = (c: CatalogCourseOut) => {
    // no single main action on the catalog: every card button is secondary (step 3a S6)
    if (teaches) {
      const staff = isActiveMember(c) && (c.my_enrollment?.role === "teacher" || c.my_enrollment?.role === "assistant");
      // owner 2026-11-12: Student view only on the course page itself
      return staff ? <LinkButton fullWidth variant="secondary" href={`/${lang}/courses/${c.id}`}>{t("catalog.open")}</LinkButton> : null;
    }
    if (isActiveMember(c)) {
      return <LinkButton fullWidth variant="secondary" href={`/${lang}/courses/${c.id}`}>{t("catalog.open")}</LinkButton>;
    }
    if (c.enrollment_mode === "open") {
      return (
        <Button fullWidth variant="secondary" loading={joining === c.id} disabled={joining !== null && joining !== c.id} onClick={() => void join(c)}>
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
      return <LinkButton fullWidth variant="secondary" href={`${landing(c)}/apply`}>{t("catalog.apply")}</LinkButton>;
    }
    // --- Phase 9 S4 end ---
    return (
      <p className="text-sm leading-6 text-slate-600">
        {c.enrollment_mode === "invite_code" ? t("catalog.needsCode") : t("catalog.closed")}
      </p>
    );
  };

  const card = (c: CatalogCourseOut, headingLevel: 2 | 3, main = false) => (
    <CourseCard key={c.id} course={c} href={landing(c)} headingLevel={headingLevel}
      badges={main || modeBadge(c)
        ? <>{main && <Badge tone="neutral">{t(`courses.languages.${c.default_language}`)}</Badge>}{modeBadge(c)}</>
        : undefined}
      action={(
        <>
          {action(c)}
          {joinError?.id === c.id && <ErrorState variant="inline" message={errorText(joinError.error)} className="mt-3" />}
        </>
      )} />
  );
  const chipLabel = (k: ExamView) => (k === "other" ? t("catalog.groups.teachers") : t(`exam.family.${k}`));

  return (
    <div className="w-full">
      <PageHeader title={t("catalog.title")} description={t("catalog.subtitle")}
        breadcrumbs={studentFrame ? undefined : [{ label: t("lms.nav.myCourses"), href: `/${lang}/courses` }, { label: t("catalog.title") }]}
        secondaryActions={teaches ? undefined : <LinkButton variant="secondary" href={`/${lang}/courses/join`} leftIcon={<KeyRound className="h-4 w-4" aria-hidden="true" />}>{t("home.primary.join")}</LinkButton>} />

      {/* step 3a S4: the family chips and the quiet way to the choose step */}
      {(chips.length > 0 || !teaches) && (
        <div className="mb-4 flex flex-wrap items-center gap-x-4 gap-y-2">
          {chips.length > 0 && (
            <div role="group" aria-label={t("catalog.groups.label")} className="flex flex-wrap gap-2">
              {chips.map((k) => {
                const on = k === view;
                return (
                  <Link key={k} href={`/${lang}/courses/catalog?exam=${k}`} replace scroll={false} aria-current={on ? "page" : undefined}
                    className={cn("inline-flex min-h-11 items-center rounded-full border px-4 text-sm font-semibold transition-colors sm:min-h-9",
                      on ? "border-brand-600 bg-brand-600 text-white" : "border-slate-300 bg-white text-slate-700 hover:border-brand-400 hover:text-brand-700",
                      focusRing)}>
                    {chipLabel(k)}
                  </Link>
                );
              })}
            </div>
          )}
          {!teaches && (
            <Link href={chooseCoursesHref(lang)}
              className={cn("inline-flex min-h-11 items-center gap-1.5 rounded text-sm font-semibold text-brand-700 hover:underline sm:min-h-0", focusRing)}>
              <Sparkles aria-hidden="true" className="h-4 w-4" />{t("catalog.groups.pick")}
            </Link>
          )}
        </div>
      )}

      {!familyView && (
        <CatalogFilters value={filters} onChange={setFilters}
          organizations={Array.from(orgs, ([id, name]) => ({ id, name })).sort((a, b) => a.name.localeCompare(b.name))} />
      )}

      {/* Phase 9 UX: how many courses a search found (cursor pages: "shown, more below" while more pages exist) */}
      <p role="status" aria-live="polite" className="mb-3 text-sm leading-6 text-slate-600 empty:hidden">
        {filtered && !loading && !error && items.length > 0
          ? t(cursor ? "catalog.resultCountMore" : "catalog.resultCount", { count: items.length }) : null}
      </p>
      {error && items.length === 0 ? <ErrorState message={errorText(error)} onRetry={() => void load()} retrying={loading} /> : null}
      {error && items.length > 0 ? <ErrorState variant="inline" message={errorText(error)} onRetry={() => void load(cursor)} className="mb-4" /> : null}
      {loading && items.length === 0 && !error && <CatalogSkeleton />}
      {!loading && !error && items.length === 0 && (filtered ? (
        <EmptyState mascot="thinking" title={t("catalog.noResults.title")} description={t("catalog.noResults.body")}
          action={<Button variant="secondary" onClick={() => setFilters({})}>{t("ui.resetFilters")}</Button>} />
      ) : (
        <EmptyState mascot="thinking" title={t("home.catalogEmpty.title")} description={t("home.catalogEmpty.body")}
          action={teaches ? undefined : <LinkButton href={`/${lang}/courses/join`}>{t("home.primary.join")}</LinkButton>} />
      ))}
      {items.length > 0 && familyView && (
        // step 3a S4: the family by subject section, the main course first (both languages, each with its tag)
        // the main course section spans the grid; each subject is one column of the same grid (§7.6: side by side)
        <div className={cn(COURSE_GRID, "gap-y-6")} aria-busy={loading || undefined}>
          {subjectSections(items, EXAM_SUBJECTS).map((s) => (
            <section key={s.key} aria-labelledby={`catalog-sec-${s.key}`} className={cn("min-w-0", s.key === "main" && "col-span-full")}>
              <h2 id={`catalog-sec-${s.key}`} className="mb-3 text-xs font-bold uppercase tracking-wide text-slate-600">
                {s.key === "main" ? t("catalog.groups.mainCourse") : t(`exam.subject.${s.key}`)}
              </h2>
              <ul className={s.key === "main" ? COURSE_GRID : "grid grid-cols-1 gap-4"}>{s.courses.map((c) => card(c, 3, s.key === "main"))}</ul>
            </section>
          ))}
        </div>
      )}
      {items.length > 0 && !familyView && (
        <ul className={COURSE_GRID} aria-busy={loading || undefined}>
          {items.map((c) => card(c, 2))}
        </ul>
      )}
      <Pagination nextCursor={cursor} loading={loading} onLoadMore={() => void load(cursor)} />
    </div>
  );
}
