"use client";

// Phase 6b S6b: the student home (PHASE_6_DESIGN 8.4; UX S3, S5, S13, S16). One call (`GET /me/home`), sections in
// order: greeting + one primary button, Continue, Next up, Latest results, My courses. Phone: one column with the
// shell's 16 px gutters; desktop: a 720 px column.
import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { BookOpen, KeyRound, LayoutGrid, Trophy } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { useAuth } from "@/lib/auth-context";
import { useLmsMe } from "@/lib/lms/useLmsMe";
import { getHome } from "@/lib/lms/home";
import type { HomeCourseOut, HomeNextUpOut, HomeOut } from "@/lib/lms/homeTypes";
import { KindIcon } from "@/components/lms/assignments/assignmentUi"; // Phase 7a S5
import { listMyCourses } from "@/lib/lms/courses";
import type { CourseCard } from "@/lib/lms/types";
import { pickLocalized } from "@/lib/lms/localized";
import { Badge, Button, EmptyState, ErrorState, LinkButton, Pagination, Skeleton, cn, focusRing } from "@/components/ui";
import { useGradeText } from "@/components/lms/results/GradeBadge";
import { HomeRow, HomeSection } from "./HomeRow";
import { DueText } from "./StudentAssessmentCard";
import { fmtShortDateTime } from "./format";
import { useErrorText } from "./useErrorText";

// --- Phase 7a S5: next-up rows are assignments: a quiz opens its lobby, text / file the submit page ---
function nextUpHref(coursesBase: string, r: HomeNextUpOut): string {
  if ((!r.kind || r.kind === "quiz") && r.assessment_id) return `${coursesBase}/${r.course_id}/assessments/${r.assessment_id}`;
  if (r.assignment_id) return `${coursesBase}/${r.course_id}/assignments/${r.assignment_id}`;
  return `${coursesBase}/${r.course_id}`;
}
// --- Phase 7a S5 end ---

const linkCls = cn("inline-flex min-h-11 items-center gap-1.5 rounded text-sm font-semibold text-brand-700 hover:underline sm:min-h-0", focusRing);

/** Small celebration: gold is for achievements only (UX §5). */
export function PersonalBestBadge() {
  const { t } = useTranslation();
  return (
    <Badge icon={<Trophy aria-hidden="true" />} className="border-gold-300 bg-gold-100 text-gold-900">{t("home.personalBest")}</Badge>
  );
}

function Greeting({ data, name, headingLevel, pending }: { data: HomeOut | null; name: string; headingLevel: 1 | 2; pending: boolean }) {
  const { lang, t } = useTranslation();
  const H = headingLevel === 1 ? "h1" : "h2";
  const title = name ? t("home.greeting", { name }) : t("home.greetingNoName");
  let line: React.ReactNode = null;
  let primary: React.ReactNode = null;
  if (data) {
    const running = data.in_progress[0];
    const next = data.next_up[0];
    if (running) {
      const runTitle = pickLocalized(running.assessment_title, lang) || t("assessments.untitled");
      // S11a, F2: a single unfinished attempt lives in the hero only (with its start date); no Continue section.
      line = data.in_progress.length === 1
        ? t("home.lead.continueStarted", { title: runTitle, date: fmtShortDateTime(running.started_at, lang) })
        : t("home.lead.continue", { title: runTitle });
      primary = <LinkButton size="lg" href={`/${lang}/courses/${running.course_id}/attempts/${running.attempt_id}`}>{t("home.primary.continue")}</LinkButton>;
    } else if (next) {
      line = t("home.lead.next", { title: pickLocalized(next.title, lang) || t("assessments.untitled") });
      primary = <LinkButton size="lg" href={nextUpHref(`/${lang}/courses`, next)}>{t("home.primary.start")}</LinkButton>; // Phase 7a S5
    } else if (data.courses_total > 0) {
      line = t("home.lead.caughtUp");
      primary = <LinkButton size="lg" href={`/${lang}/courses/join`} leftIcon={<KeyRound aria-hidden="true" className="h-5 w-5" />}>{t("home.primary.join")}</LinkButton>;
    }
    // A new student: the My courses empty state below is the hero and carries the one primary button.
  }
  return (
    <header className="space-y-3">
      <H className="break-words text-2xl font-bold leading-8 text-slate-900">{title}</H>
      {data ? (
        <>
          {line && <p className="text-base leading-6 text-slate-700">{line}</p>}
          {primary && <div className="[&>*]:w-full sm:[&>*]:w-auto">{primary}</div>}
        </>
      ) : pending && (
        <div aria-hidden="true" className="space-y-3">
          <Skeleton className="h-5 w-3/4" />
          <Skeleton className="h-12 w-full rounded-xl sm:w-56" />
        </div>
      )}
    </header>
  );
}

function SectionSkeleton({ rows = 2 }: { rows?: number }) {
  return (
    <div aria-hidden="true">
      <Skeleton className="mb-3 h-6 w-40" />
      <div className="space-y-1 rounded-2xl border border-slate-200 bg-white p-3 shadow-sm">
        {Array.from({ length: rows }, (_, i) => (
          <div key={i} className="flex min-h-11 items-center gap-3 px-1 py-2">
            <div className="flex-1 space-y-2"><Skeleton className="h-5 w-2/3" /><Skeleton className="h-4 w-1/2" /></div>
            <Skeleton className="h-5 w-16" />
          </div>
        ))}
      </div>
    </div>
  );
}

export function HomeSkeleton() {
  const { t } = useTranslation();
  return (
    <div role="status" aria-live="polite" className="space-y-6">
      <span className="sr-only">{t("ui.loading")}</span>
      <SectionSkeleton rows={2} />
      <SectionSkeleton rows={2} />
      <SectionSkeleton rows={3} />
    </div>
  );
}

function CourseMeta({ c }: { c: HomeCourseOut }) {
  const { lang, t } = useTranslation();
  return (
    <>
      <span>{c.is_platform_course ? t("home.platformCourse") : t("courses.list.owner", { name: c.owner_display_name })}</span>
      {c.next_due_at ? <DueText value={c.next_due_at} lang={lang} /> : <span>{t("home.noDue")}</span>}
    </>
  );
}

function AllCourses() {
  const { lang, t } = useTranslation();
  const errorText = useErrorText();
  const [items, setItems] = useState<CourseCard[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const load = useCallback(async (next?: string | null) => {
    setLoading(true);
    setError(null);
    try {
      const page = await listMyCourses("learning", next);
      setItems((p) => (next ? [...p, ...page.items] : page.items));
      setCursor(page.next_cursor);
    } catch (e) {
      setError(e);
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => { void load(); }, [load]);
  return (
    <>
      {error ? <ErrorState variant="inline" message={errorText(error)} onRetry={() => void load(cursor)} className="m-2" /> : null}
      <ul className="divide-y divide-slate-100">
        {items.map((c) => (
          <HomeRow key={c.id} href={`/${lang}/courses/${c.id}`} title={pickLocalized(c.title, lang, c.default_language) || t("courses.list.untitled")}
            meta={c.owner_display_name ? <span>{t("courses.list.owner", { name: c.owner_display_name })}</span> : null} />
        ))}
      </ul>
      {loading && items.length === 0 && <div className="p-3"><Skeleton className="h-5 w-2/3" /></div>}
      <Pagination nextCursor={cursor} loading={loading} onLoadMore={() => void load(cursor)} className="pb-2" />
    </>
  );
}

function Sections({ data }: { data: HomeOut }) {
  const { lang, t } = useTranslation();
  const gradeText = useGradeText();
  const [showAll, setShowAll] = useState(false);
  const base = `/${lang}/courses`;
  const untitled = t("assessments.untitled");

  if (data.courses_total === 0 && data.in_progress.length === 0) {
    return (
      <EmptyState icon={<BookOpen />} title={t("home.courses.emptyTitle")} description={t("home.courses.emptyBody")}
        action={(
          <>
            <LinkButton size="lg" href={`${base}/join`} leftIcon={<KeyRound aria-hidden="true" className="h-5 w-5" />}>{t("home.primary.join")}</LinkButton>
            <LinkButton size="lg" variant="secondary" href={`${base}/catalog`} leftIcon={<LayoutGrid aria-hidden="true" className="h-5 w-5" />}>{t("home.openCatalog")}</LinkButton>
          </>
        )} />
    );
  }

  return (
    <div className="space-y-8">
      {data.in_progress.length > 1 && (
        <HomeSection id="home-continue" title={t("home.continue.title")}>
          <ul className="divide-y divide-slate-100">
            {data.in_progress.map((r) => (
              <HomeRow key={r.attempt_id} href={`${base}/${r.course_id}/attempts/${r.attempt_id}`}
                title={pickLocalized(r.assessment_title, lang) || untitled}
                meta={<><span>{pickLocalized(r.course_title, lang)}</span><span>{t("home.startedAt", { date: fmtShortDateTime(r.started_at, lang) })}</span></>}
                actionLabel={t("home.action.continue")} />
            ))}
          </ul>
        </HomeSection>
      )}

      {/* --- Phase 8a S4a: "up next" in modules, one row per course ("Continue in Course: Item"), above assignments --- */}
      {(data.modules_next?.length ?? 0) > 0 && (
        <HomeSection id="home-modules-next" title={t("home.modulesNext.title")}>
          <ul className="divide-y divide-slate-100">
            {data.modules_next!.map((r) => (
              <HomeRow key={`${r.course_id}-${r.item_id}`} href={`${base}/${r.course_id}/modules`}
                title={pickLocalized(r.title, lang) || t("modules.untitledItem")}
                meta={(
                  <>
                    <span>{t("home.modulesNext.inCourse", { course: pickLocalized(r.course_title, lang) || t("courses.list.untitled") })}</span>
                    {r.module_title && <span>{pickLocalized(r.module_title, lang)}</span>}
                  </>
                )}
                actionLabel={t("home.modulesNext.action")} />
            ))}
          </ul>
        </HomeSection>
      )}
      {/* --- Phase 8a S4a end --- */}

      {/* --- Phase 8a S5: the latest three announcements of the student's courses (design 7.2, 8.1; never a body) --- */}
      {(data.announcements?.length ?? 0) > 0 && (
        <HomeSection id="home-announcements" title={t("home.announcements.title")}>
          <ul className="divide-y divide-slate-100">
            {data.announcements!.map((r) => (
              <HomeRow key={r.id} href={`${base}/${r.course_id}/announcements`} title={r.title}
                meta={(
                  <>
                    <span>{pickLocalized(r.course_title, lang) || t("courses.list.untitled")}</span>
                    <span>{fmtShortDateTime(r.published_at, lang)}</span>
                  </>
                )}
                actionLabel={t("home.announcements.action")} />
            ))}
          </ul>
        </HomeSection>
      )}

      <HomeSection id="home-next" title={t("home.next.title")}>
        {data.next_up.length === 0 ? (
          <p className="px-3 py-4 text-base leading-6 text-slate-600 sm:px-4">{t("home.next.empty")}</p>
        ) : (
          <ul className="divide-y divide-slate-100">
            {data.next_up.map((r) => (
              <HomeRow key={r.assignment_id ?? r.assessment_id ?? r.course_id} href={nextUpHref(base, r) /* Phase 7a S5 */}
                title={pickLocalized(r.title, lang) || untitled}
                meta={(
                  <>
                    {/* Phase 7a S5: kind icon + text */}
                    {r.kind && <span className="inline-flex items-center gap-1"><KindIcon kind={r.kind} />{t(`assignments.kinds.${r.kind}`)}</span>}
                    <span>{pickLocalized(r.course_title, lang)}</span>
                    {r.due_at ? <DueText value={r.due_at} lang={lang} />
                      : r.available_until ? <span>{t("home.until", { date: fmtShortDateTime(r.available_until, lang) })}</span> : null}
                    {r.attempts_left !== null && r.attempts_left !== undefined && <span>{t("home.attemptsLeft", { n: r.attempts_left })}</span>}
                  </>
                )}
                actionLabel={t("home.action.open")} />
            ))}
          </ul>
        )}
      </HomeSection>

      <HomeSection id="home-results" title={t("home.results.title")}>
        {data.latest_results.length === 0 ? (
          <p className="px-3 py-4 text-base leading-6 text-slate-600 sm:px-4">{t("home.results.empty")}</p>
        ) : (
          <ul className="divide-y divide-slate-100">
            {data.latest_results.map((r) => {
              const value = gradeText(r, r.scheme_type ?? undefined);
              // Phase 7a S5: a released manual grade opens its assignment page (grade and feedback)
              const href = r.kept_attempt_id ? `${base}/${r.course_id}/attempts/${r.kept_attempt_id}/result`
                : r.assignment_id && r.kind && r.kind !== "quiz" ? `${base}/${r.course_id}/assignments/${r.assignment_id}` : `${base}/${r.course_id}/grades`;
              return (
                <HomeRow key={r.assignment_id ?? r.assessment_id ?? href} href={href} title={pickLocalized(r.title, lang) || untitled}
                  meta={(
                    <>
                      <span>{pickLocalized(r.course_title, lang)}</span>
                      {r.is_personal_best && <PersonalBestBadge />}
                    </>
                  )}
                  aside={value ? <span className="text-lg font-bold leading-6 text-slate-900">{value}</span> : null}
                  actionLabel={t("home.action.result")} />
              );
            })}
          </ul>
        )}
      </HomeSection>

      <HomeSection id="home-courses" title={t("home.courses.title")}
        footer={(
          <>
            {!showAll && data.courses_total > data.courses.length && (
              <Button variant="link" onClick={() => setShowAll(true)}>{t("home.courses.showAll", { n: data.courses_total })}</Button>
            )}
            <Link href={`${base}/join`} className={linkCls}><KeyRound aria-hidden="true" className="h-4 w-4" />{t("home.primary.join")}</Link>
            <Link href={`${base}/catalog`} className={linkCls}><LayoutGrid aria-hidden="true" className="h-4 w-4" />{t("home.openCatalog")}</Link>
          </>
        )}>
        {showAll ? <AllCourses /> : (
          <ul className="divide-y divide-slate-100">
            {data.courses.map((c) => (
              <HomeRow key={c.id} href={`${base}/${c.id}`} title={pickLocalized(c.title, lang) || t("courses.list.untitled")}
                meta={<CourseMeta c={c} />}
                aside={c.in_progress ? <Badge tone="info">{t("home.status.in_progress")}</Badge> : null} />
            ))}
          </ul>
        )}
      </HomeSection>
    </div>
  );
}

/** The student home. `embedded`: inside the Teaching/Learning tabs (the page already has its h1). */
export function StudentHome({ embedded = false }: { embedded?: boolean }) {
  const { me } = useLmsMe();
  const { userProfile } = useAuth();
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

  // The cached profile gives the name at once; MeOut replaces it when loaded.
  const name = (me?.display_name || userProfile?.displayName || "").trim();
  return (
    <div className="mx-auto w-full max-w-[720px] space-y-8">
      <Greeting data={data} name={name} headingLevel={embedded ? 2 : 1} pending={!data && !error} />
      {error && !data ? (
        <ErrorState message={errorText(error)} onRetry={() => void load()} retrying={loading} />
      ) : !data ? (
        <HomeSkeleton />
      ) : (
        <Sections data={data} />
      )}
    </div>
  );
}
