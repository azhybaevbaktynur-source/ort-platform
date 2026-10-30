"use client";

// Phase 9 S4: course landing in the catalog (`/courses/catalog/{id}`; PHASE_9_DESIGN 4.6, 8.1): title, organization,
// teachers, description, how to join, and one primary action (Open / Join / Apply / Enter code / closed). A student
// with an application sees its status here (and the teacher's note after a decision), and can withdraw it.
import React, { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { CalendarDays, Languages, Users, UserRound } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { parseApiDate } from "@/lib/format";
import { getCourseLanding, isActiveMember, isFormMode, joinOpenCourse, type CourseLandingOut } from "@/lib/lms/catalog";
import { listMyApplications, withdrawApplication } from "@/lib/lms/applications";
import { pickLocalized } from "@/lib/lms/localized";
import type { ApplicationOwnOut } from "@/lib/lms/types";
import { Button, ConfirmDialog, ErrorState, LinkButton, LoadingState, PageHeader, toast } from "@/components/ui";
import { CatalogModeBadge } from "./CatalogModeBadge";
import { ApplicationStatusBadge } from "./ApplicationStatus";
import { useApplicationErrorText } from "./useApplicationErrorText";
import { fmtShortDateTime } from "@/components/lms/home/format";

const SHOW_COUNT_FROM = 10;
const MY_APPLICATION_PAGES = 4; // `/me/applications` pages scanned for the landing's application (newest first)

export function fmtDay(value: string | null | undefined, lang: string): string {
  const d = parseApiDate(value);
  return d ? d.toLocaleDateString(lang === "en" ? "en-GB" : lang, { day: "numeric", month: "long", year: "numeric" }) : "";
}

/** The student's own application (status, dates, the teacher's note), found by id in `/me/applications`. */
async function findMyApplication(id: string): Promise<ApplicationOwnOut | null> {
  let cursor: string | null | undefined;
  for (let i = 0; i < MY_APPLICATION_PAGES; i += 1) {
    const page = await listMyApplications(cursor, 50);
    const hit = page.items.find((a) => a.id === id);
    if (hit) return hit;
    if (!page.next_cursor) return null;
    cursor = page.next_cursor;
  }
  return null;
}

function Fact({ icon, label, children }: { icon: React.ReactNode; label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-start gap-3">
      <span aria-hidden="true" className="mt-0.5 text-slate-500">{icon}</span>
      <div className="min-w-0">
        <dt className="text-sm font-medium leading-6 text-slate-600">{label}</dt>
        <dd className="break-words text-base leading-6 text-slate-900 sm:text-sm">{children}</dd>
      </div>
    </div>
  );
}

export function CourseLanding({ courseId }: { courseId: string }) {
  const { lang, t } = useTranslation();
  const router = useRouter();
  const errorText = useApplicationErrorText();
  const [course, setCourse] = useState<CourseLandingOut | null>(null);
  const [mine, setMine] = useState<ApplicationOwnOut | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<unknown>(null);
  const [confirmWithdraw, setConfirmWithdraw] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const c = await getCourseLanding(courseId);
      setCourse(c);
      setMine(c.my_application ? await findMyApplication(c.my_application.id).catch(() => null) : null);
    } catch (e) {
      setError(e);
    } finally {
      setLoading(false);
    }
  }, [courseId]);
  useEffect(() => { void load(); }, [load]);

  const catalogHref = `/${lang}/courses/catalog`;
  const crumbs = (title?: string) => [{ label: t("catalog.title"), href: catalogHref }, ...(title ? [{ label: title }] : [])];

  if (loading && !course) return <div className="mx-auto w-full max-w-3xl"><LoadingState rows={4} /></div>;
  if (error || !course) {
    const notFound = (error as { status?: number } | null)?.status === 404;
    return (
      <div className="mx-auto w-full max-w-3xl">
        <PageHeader title={t("catalog.title")} breadcrumbs={crumbs()} />
        <ErrorState title={notFound ? t("catalog.landing.notFoundTitle") : undefined}
          message={notFound ? t("catalog.landing.notFoundBody") : errorText(error)}
          onRetry={notFound ? undefined : () => void load()} retrying={loading}
          action={<LinkButton variant="secondary" href={catalogHref}>{t("catalog.landing.backToCatalog")}</LinkButton>} />
      </div>
    );
  }

  const title = pickLocalized(course.title, lang, course.default_language) || t("courses.list.untitled");
  const description = pickLocalized(course.description, lang, course.default_language);
  const formOpen = isFormMode(course.enrollment_mode) && !!course.form;
  const status = course.my_application?.status ?? null;
  const member = isActiveMember(course);

  const join = async () => {
    setBusy(true);
    setActionError(null);
    try {
      const res = await joinOpenCourse(course.id);
      router.push(`/${lang}/courses/${res.course.id}`);
    } catch (e) {
      setActionError(e);
      setBusy(false);
    }
  };

  const withdraw = async () => {
    if (!course.my_application) return;
    setBusy(true);
    setActionError(null);
    try {
      await withdrawApplication(course.id, course.my_application.id);
      setConfirmWithdraw(false);
      toast.success(t("applications.student.withdrawn"));
      await load();
    } catch (e) {
      setActionError(e);
    } finally {
      setBusy(false);
    }
  };

  let primary: React.ReactNode = null;
  if (member) {
    primary = <LinkButton size="lg" href={`/${lang}/courses/${course.id}`}>{t("catalog.landing.openCourse")}</LinkButton>;
  } else if (course.enrollment_mode === "open") {
    primary = <Button size="lg" loading={busy} onClick={() => void join()}>{t("catalog.join")}</Button>;
  } else if (formOpen && status !== "pending") {
    primary = (
      <LinkButton size="lg" href={`/${lang}/courses/catalog/${course.id}/apply`}>
        {status === "rejected" || status === "withdrawn" ? t("catalog.landing.applyAgain") : t("catalog.apply")}
      </LinkButton>
    );
  } else if (course.enrollment_mode === "invite_code") {
    primary = <LinkButton size="lg" href={`/${lang}/courses/join`}>{t("catalog.landing.enterCode")}</LinkButton>;
  } else if (status !== "pending") {
    primary = <p className="text-base font-medium leading-6 text-slate-700">{t("catalog.closed")}</p>;
  }

  return (
    <div className="mx-auto w-full max-w-3xl space-y-6">
      <PageHeader title={title} breadcrumbs={crumbs(title)} badge={<CatalogModeBadge mode={course.enrollment_mode} />}
        description={course.organization_name || undefined} />

      {/* The student's application (pending, or decided with the teacher's note). Phase 9 S5: an approved
          applicant (now a member) still sees the teacher's note, as the inbox promises ("shown to the student"). */}
      {course.my_application && (!member || (course.my_application.status === "approved" && !!mine?.decision_note)) && (
        <section aria-labelledby="landing-application" className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:p-6">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 id="landing-application" className="text-lg font-semibold leading-7 text-slate-900">{t("applications.student.title")}</h2>
            <ApplicationStatusBadge status={course.my_application.status} audience="student" />
          </div>
          <p className="mt-2 text-base leading-6 text-slate-700 sm:text-sm">{t(`applications.student.explain.${course.my_application.status}`)}</p>
          {mine && (
            <p className="mt-1 text-sm leading-6 text-slate-600">
              {t("applications.student.sentOn", { date: fmtShortDateTime(mine.submitted_at, lang) })}
              {mine.decided_at ? ` · ${t("applications.student.decidedOn", { date: fmtShortDateTime(mine.decided_at, lang) })}` : ""}
            </p>
          )}
          {mine?.decision_note && (
            <div className="mt-3 rounded-xl bg-slate-50 px-4 py-3">
              <p className="text-sm font-medium leading-6 text-slate-700">{t("applications.student.note")}</p>
              <p className="whitespace-pre-line break-words text-base leading-6 text-slate-800 sm:text-sm">{mine.decision_note}</p>
            </div>
          )}
          {status === "pending" && (
            <Button variant="secondary" className="mt-4" disabled={busy} onClick={() => { setActionError(null); setConfirmWithdraw(true); }}>
              {t("applications.student.withdraw")}
            </Button>
          )}
        </section>
      )}

      <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:p-6">
        {description
          ? <p className="whitespace-pre-line break-words text-base leading-7 text-slate-800">{description}</p>
          : <p className="text-base leading-6 text-slate-600">{t("catalog.landing.noDescription")}</p>}
        <dl className="mt-5 grid gap-4 sm:grid-cols-2">
          {course.teachers.length > 0 && (
            <Fact icon={<UserRound className="h-5 w-5" />} label={t("catalog.landing.teachers")}>{course.teachers.join(", ")}</Fact>
          )}
          <Fact icon={<Languages className="h-5 w-5" />} label={t("catalog.landing.languages")}>
            {course.languages.map((l) => t(`courses.languages.${l}`)).join(", ")}
          </Fact>
          {(course.starts_at || course.ends_at) && (
            <Fact icon={<CalendarDays className="h-5 w-5" />} label={t("catalog.landing.dates")}>
              {course.starts_at && course.ends_at
                ? t("catalog.landing.dateRange", { start: fmtDay(course.starts_at, lang), end: fmtDay(course.ends_at, lang) })
                : course.starts_at ? t("catalog.landing.startsOn", { date: fmtDay(course.starts_at, lang) })
                  : t("catalog.landing.endsOn", { date: fmtDay(course.ends_at, lang) })}
            </Fact>
          )}
          {course.student_count >= SHOW_COUNT_FROM && (
            <Fact icon={<Users className="h-5 w-5" />} label={t("catalog.landing.students")}>{course.student_count}</Fact>
          )}
        </dl>
      </section>

      {!member && (
        <section aria-labelledby="landing-join" className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:p-6">
          <h2 id="landing-join" className="text-lg font-semibold leading-7 text-slate-900">{t("catalog.landing.howToJoin")}</h2>
          <p className="mt-1 text-base leading-6 text-slate-700 sm:text-sm">
            {isFormMode(course.enrollment_mode) && !course.form ? t("catalog.landing.modeHelp.formUnavailable") : t(`catalog.landing.modeHelp.${course.enrollment_mode}`)}
          </p>
          {primary && <div className="mt-4">{primary}</div>}
          {actionError && !confirmWithdraw ? <ErrorState variant="inline" message={errorText(actionError)} className="mt-3" /> : null}
        </section>
      )}
      {member && <div>{primary}</div>}

      <ConfirmDialog open={confirmWithdraw} busy={busy} title={t("applications.student.withdrawTitle")} object={title}
        effect={t("applications.student.withdrawBody")} confirmLabel={t("applications.student.withdraw")}
        error={actionError && confirmWithdraw ? <ErrorState variant="inline" message={errorText(actionError)} /> : undefined}
        onConfirm={() => void withdraw()} onCancel={() => setConfirmWithdraw(false)} />
    </div>
  );
}
