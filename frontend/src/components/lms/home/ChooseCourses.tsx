"use client";

// Step 3a S4 (STUDENT_IA_DESIGN §4, §7.6, decision N7): «Выберите курсы» `/courses/choose`, two steps on one page.
// 1 · Экзамен: one card per family with listed platform courses (`GET /catalog/exams`); one family only: straight to
// step 2. 2 · Курсы: the family's courses as checkboxes by subject section; the main course of the UI language
// pre-checked (en -> ru); courses the student is in checked and disabled. «Записаться (N)» -> `POST /catalog/choose`
// -> `/home`; «Пропустить» (`?first=1`, after sign-up) or «Назад». Nothing is joined without the press; nothing is
// stored about a skip. People who teach go to the Teaching list (as `urlAreaFor` does); the test student to the course.
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowLeft, ArrowRight, KeyRound } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { useAuth } from "@/lib/auth-context";
import { useLmsMe } from "@/lib/lms/useLmsMe";
import { useCachedMe } from "@/lib/lms/meCache";
import { getStudentView } from "@/lib/api";
import { teaches } from "@/lib/lms/shellKind";
import { chooseCourses, listExams, type ExamCourseOut, type ExamFamilyOut } from "@/lib/lms/catalog";
import { defaultChecked, defaultFamily, idsToJoin, joinedOfRefusal, subjectSections } from "@/lib/lms/chooseCourses";
import { deviceStorage, writePlace } from "@/lib/lms/lastPlace";
import { pickLocalized } from "@/lib/lms/localized";
import { EXAM_SUBJECTS, type Lang } from "@/lib/lms/types";
import { Button, EmptyState, ErrorState, LinkButton, LoadingState, Skeleton, cn, focusRing } from "@/components/ui";
import { StudentPageHeader } from "@/components/lms/student/StudentPageHeader";
import { useStudentShellDataContext } from "@/components/lms/student/StudentShellDataContext";
import { useErrorText } from "./useErrorText";

/** LobbyView's sticky action on phones: above the 64 px tab bar; in the page flow from `lg` (no tab bar). */
const STICKY_ACTION = "sticky bottom-[calc(76px+env(safe-area-inset-bottom))] z-10 rounded-card border border-slate-200 bg-white p-3 shadow-lg lg:static lg:border-0 lg:bg-transparent lg:p-0 lg:shadow-none";
const SECTION_TITLE = "mb-2 text-xs font-bold uppercase tracking-wide text-slate-600";

type SubmitProblem =
  | { kind: "consent" }
  | { kind: "refused"; joined: number }
  | { kind: "other"; error: unknown };

function ChooseSkeleton() {
  const { t } = useTranslation();
  return (
    <div role="status" aria-live="polite" className="mt-6">
      <span className="sr-only">{t("ui.loading")}</span>
      <div aria-hidden="true" className="space-y-3">
        <Skeleton className="h-4 w-32" />
        <div className="grid gap-3 sm:grid-cols-2">
          <Skeleton className="h-20 w-full rounded-card" />
          <Skeleton className="h-20 w-full rounded-card" />
        </div>
        <Skeleton className="mt-4 h-4 w-40" />
        <div className="grid gap-3 sm:grid-cols-2">
          {Array.from({ length: 4 }, (_, i) => <Skeleton key={i} className="h-16 w-full rounded-card" />)}
        </div>
      </div>
    </div>
  );
}

/** One course as a checkbox row: title, Pro mark, one-line description, counts; «Вы уже записаны» when in it. */
function CourseRow({ course, checked, onToggle }: { course: ExamCourseOut; checked: boolean; onToggle: (id: string) => void }) {
  const { lang, t } = useTranslation();
  const title = pickLocalized(course.title, lang as Lang, course.default_language) || t("courses.list.untitled");
  const description = pickLocalized(course.description, lang as Lang, course.default_language);
  const meta = [
    course.tests_count ? t("courses.card.tests", { count: course.tests_count }) : null,
    course.lessons_count ? t("courses.card.lessons", { count: course.lessons_count }) : null,
  ].filter(Boolean).join(" · ");
  const id = `choose-${course.id}`;
  const on = course.enrolled || checked;
  return (
    <li className="min-w-0">
      <label htmlFor={id}
        className={cn("flex min-h-11 items-start gap-3 rounded-card border bg-white p-3 transition-colors",
          course.enrolled ? "cursor-not-allowed border-slate-200 bg-slate-50" : "cursor-pointer hover:border-brand-300",
          on && !course.enrolled ? "border-brand-500 bg-brand-50" : "border-slate-200")}>
        <input id={id} type="checkbox" checked={on} disabled={course.enrolled} onChange={() => onToggle(course.id)}
          className="mt-0.5 h-5 w-5 shrink-0 cursor-pointer rounded border-slate-400 accent-brand-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-600 focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-60" />
        <span className="min-w-0 flex-1">
          <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <span className="min-w-0 break-words text-base font-semibold leading-6 text-slate-900 sm:text-sm">{title}</span>
            {course.has_paid_tests && (
              <span title={t("courses.card.proHint")}
                className="inline-flex items-center rounded-full border border-gold-200 bg-gold-50 px-2 py-0.5 text-xs font-semibold leading-5 text-gold-800">
                {t("courses.card.pro")}<span className="sr-only">{` (${t("courses.card.proHint")})`}</span>
              </span>
            )}
          </span>
          {description && <span title={description} className="block truncate text-sm leading-5 text-slate-600">{description}</span>}
          {meta && <span className="block text-sm leading-5 text-slate-600">{meta}</span>}
          {course.enrolled && <span className="mt-0.5 block text-sm font-semibold leading-5 text-success-700">{t("choose.alreadyIn")}</span>}
        </span>
      </label>
    </li>
  );
}

function ChooseInner({ first }: { first: boolean }) {
  const { lang, t } = useTranslation();
  const router = useRouter();
  const errorText = useErrorText();
  const { me } = useLmsMe();
  const shell = useStudentShellDataContext();
  const mine = useMemo(() => shell?.courses ?? [], [shell?.courses]);
  const [families, setFamilies] = useState<ExamFamilyOut[] | null>(null);
  const [loadError, setLoadError] = useState<unknown>(null);
  const [loading, setLoading] = useState(true);
  const [family, setFamily] = useState<string | null>(null);
  const [checked, setChecked] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<SubmitProblem | null>(null);
  const familyRef = useRef<string | null>(null);
  familyRef.current = family;
  const mineRef = useRef(mine);
  mineRef.current = mine;

  /** Reads the families; keeps the family and the still-choosable checks of a reload (after a refusal). */
  const load = useCallback(async (keepChecks = false) => {
    setLoading(true);
    setLoadError(null);
    try {
      const rows = await listExams();
      setFamilies(rows);
      const available = rows.map((r) => r.family);
      const current = familyRef.current && available.includes(familyRef.current as ExamFamilyOut["family"])
        ? familyRef.current : defaultFamily(available, mineRef.current);
      setFamily(current);
      const courses = rows.find((r) => r.family === current)?.courses ?? [];
      setChecked((prev) => keepChecks
        ? new Set(courses.filter((c) => !c.enrolled && prev.has(c.id)).map((c) => c.id))
        : new Set(defaultChecked(courses, lang)));
    } catch (e) {
      setLoadError(e);
    } finally {
      setLoading(false);
    }
  }, [lang]);
  useEffect(() => { void load(); }, [load]);

  const courses = useMemo(() => families?.find((f) => f.family === family)?.courses ?? [], [families, family]);
  const sections = useMemo(() => subjectSections(courses, EXAM_SUBJECTS), [courses]);
  const toJoin = idsToJoin(courses, checked);

  const pickFamily = (f: string) => {
    if (f === family) return;
    setFamily(f);
    setProblem(null);
    setChecked(new Set(defaultChecked(families?.find((x) => x.family === f)?.courses ?? [], lang)));
  };
  const toggle = (id: string) => {
    setProblem(null);
    setChecked((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  const submit = async () => {
    if (!toJoin.length || busy) return;
    setBusy(true);
    setProblem(null);
    try {
      await chooseCourses(toJoin);
      // «Продолжить» on the hub opens the first chosen course (its next step): it becomes the last place, the others
      // follow it in the recent list (the sidebar rows)
      if (me?.id) {
        const storage = deviceStorage();
        for (const id of [...toJoin].reverse()) writePlace(storage, me.id, { courseId: id, path: `/${lang}/courses/${id}`, kind: "overview" });
      }
      router.push(`/${lang}/home`);
    } catch (e) {
      const code = (e as { code?: string } | null)?.code;
      if (code === "consent_required") setProblem({ kind: "consent" });
      else if (code === "course_not_choosable") {
        setProblem({ kind: "refused", joined: joinedOfRefusal((e as { details?: unknown }).details).length });
        void load(true);
      } else setProblem({ kind: "other", error: e });
      setBusy(false);
    }
  };

  const back = () => {
    if (typeof window !== "undefined" && window.history.length > 1) router.back();
    else router.push(`/${lang}/home`);
  };
  const headerAction = first
    ? <LinkButton variant="secondary" href={`/${lang}/home`}>{t("choose.skip")}</LinkButton>
    : <Button variant="secondary" onClick={back} leftIcon={<ArrowLeft aria-hidden="true" className="h-4 w-4" />}>{t("choose.back")}</Button>;
  const codeLink = (
    <Link href={`/${lang}/courses/join`}
      className={cn("inline-flex min-h-11 items-center gap-1.5 rounded text-base font-semibold text-brand-700 hover:underline sm:min-h-0 sm:text-sm", focusRing)}>
      <KeyRound aria-hidden="true" className="h-4 w-4" />{t("choose.haveCode")}<ArrowRight aria-hidden="true" className="h-4 w-4" />
    </Link>
  );
  const familyName = (f: string) => t(`exam.family.${f}`);
  const several = (families?.length ?? 0) > 1;

  return (
    <div className="mx-auto w-full max-w-[1200px]">
      <StudentPageHeader title={t("choose.title")} subtitle={t("choose.subtitle")} action={headerAction} />

      {loading && !families && <ChooseSkeleton />}
      {loadError && !families ? (
        <div className="mt-6"><ErrorState message={errorText(loadError)} onRetry={() => void load()} retrying={loading} /></div>
      ) : null}
      {families && families.length === 0 && (
        <div className="mt-6">
          <EmptyState mascot="thinking" title={t("choose.noneTitle")} description={t("choose.noneBody")}
            action={<LinkButton href={`/${lang}/courses/join`} leftIcon={<KeyRound aria-hidden="true" className="h-4 w-4" />}>{t("home.hub.join")}</LinkButton>} />
        </div>
      )}

      {families && families.length > 0 && (
        <>
          <section aria-labelledby={several ? "choose-step1" : undefined} className="mt-6">
            {several && (
              <>
                <h2 id="choose-step1" className={SECTION_TITLE}>{t("choose.step1")}</h2>
                <div role="radiogroup" aria-labelledby="choose-step1" className="grid gap-3 sm:grid-cols-2">
                  {families.map((f) => {
                    const on = f.family === family;
                    return (
                      <label key={f.family}
                        className={cn("flex min-h-11 cursor-pointer items-start gap-3 rounded-card border bg-white p-3 transition-colors hover:border-brand-300",
                          on ? "border-brand-500 bg-brand-50" : "border-slate-200")}>
                        <input type="radio" name="choose-family" value={f.family} checked={on} onChange={() => pickFamily(f.family)}
                          className="mt-1 h-5 w-5 shrink-0 cursor-pointer accent-brand-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-600 focus-visible:ring-offset-2" />
                        <span className="min-w-0">
                          <span className="block text-base font-bold leading-6 text-slate-900">{familyName(f.family)}</span>
                          <span className="block text-sm leading-5 text-slate-600">
                            {t(`choose.familyHint.${f.family}`)} · {t("choose.courses", { count: f.courses.length })}
                          </span>
                        </span>
                      </label>
                    );
                  })}
                </div>
              </>
            )}
            <div className={several ? "mt-2" : ""}>{codeLink}</div>
          </section>

          <section aria-labelledby="choose-step2" className="mt-6">
            <h2 id="choose-step2" className={SECTION_TITLE}>
              {several ? t("choose.step2", { family: familyName(family ?? "") }) : t("choose.step2Only", { family: familyName(family ?? "") })}
            </h2>
            <div className="grid gap-x-4 gap-y-5 sm:grid-cols-2 lg:grid-cols-3">
              {sections.map((s) => (
                <div key={s.key} className={cn("min-w-0", s.key === "main" && "sm:col-span-2 lg:col-span-3")}>
                  <h3 className={SECTION_TITLE}>{s.key === "main" ? t("catalog.groups.mainCourse") : t(`exam.subject.${s.key}`)}</h3>
                  <ul className={cn("grid gap-2", s.key === "main" && "sm:grid-cols-2")}>
                    {s.courses.map((c) => <CourseRow key={c.id} course={c} checked={checked.has(c.id)} onToggle={toggle} />)}
                  </ul>
                </div>
              ))}
            </div>
          </section>

          <div className={cn("mt-6", STICKY_ACTION)}>
            {problem && (
              <div className="mb-3">
                {problem.kind === "consent" ? (
                  <ErrorState variant="inline" title={t("choose.errors.title")} message={t("choose.errors.consent")}
                    action={<LinkButton size="sm" variant="secondary" href={`/${lang}/privacy`}>{t("choose.errors.consentLink")}</LinkButton>} />
                ) : problem.kind === "refused" ? (
                  <ErrorState variant="inline" title={t("choose.errors.title")}
                    message={problem.joined ? t("choose.errors.partly", { count: problem.joined }) : t("choose.errors.notChoosable")} />
                ) : (
                  <ErrorState variant="inline" title={t("choose.errors.title")} message={errorText(problem.error)} onRetry={() => void submit()} retrying={busy} />
                )}
              </div>
            )}
            <div className="flex flex-col gap-2 lg:flex-row lg:items-center lg:justify-end">
              {!toJoin.length && <p className="text-sm leading-5 text-slate-600 lg:mr-auto">{t("choose.pickOne")}</p>}
              <Button size="lg" fullWidth className="lg:w-auto" loading={busy} disabled={!toJoin.length || busy} onClick={() => void submit()}
                rightIcon={<ArrowRight aria-hidden="true" className="h-4 w-4" />}>
                {t("choose.enrol", { count: toJoin.length })}
              </Button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

/** The page: people who teach never see the step (the Teaching list), the test student goes to the course. */
export function ChooseCourses({ first }: { first: boolean }) {
  const { lang, t } = useTranslation();
  const router = useRouter();
  const { me: fresh } = useLmsMe();
  const cachedMe = useCachedMe();
  const me = fresh ?? cachedMe;
  const { userProfile } = useAuth();
  const shell = useStudentShellDataContext();
  const hasTeaching = me ? teaches(me)
    : !!userProfile && (userProfile.teacher_status === "approved" || !!userProfile.is_platform_admin);
  // Student view is known from this tab's session before its profile arrives (read after mount: no SSR mismatch)
  const [viewCourse, setViewCourse] = useState<string | null | undefined>(undefined);
  useEffect(() => { setViewCourse(getStudentView()?.courseId ?? null); }, []);
  const testStudent = !!viewCourse || !!userProfile?.is_test_student;
  const shellKnown = !shell || shell.loaded;
  const testCourse = viewCourse || (testStudent && shell?.loaded ? shell.courses[0]?.id ?? null : null);
  useEffect(() => {
    if (hasTeaching) router.replace(`/${lang}/courses`);
    else if (testCourse) router.replace(`/${lang}/courses/${testCourse}`);
    else if (testStudent && shellKnown) router.replace(`/${lang}/home`);
  }, [hasTeaching, testStudent, testCourse, shellKnown, lang, router]);
  if (viewCourse === undefined || hasTeaching || testStudent) return <LoadingState label={t("lms.common.loading")} />;
  return <ChooseInner first={first} />;
}
