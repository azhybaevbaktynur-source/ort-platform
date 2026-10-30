"use client";

// Phase 9 S4: apply to a course (`/courses/catalog/{id}/apply`; PHASE_9_DESIGN 4.7, 6, 8.1). The active form rendered
// with `FormRenderer`, the privacy note (who reads the answers and for how long), submit, then "Application sent"
// (form_review) or "You are in" (form_auto). Answers live in React state only: never stored, never logged.
import React, { useCallback, useEffect, useRef, useState } from "react";
import { CheckCircle2, Clock, ShieldCheck } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { answerErrors, submitApplication } from "@/lib/lms/applications";
import { getCourseLanding, isActiveMember, isFormMode, type CourseLandingOut } from "@/lib/lms/catalog";
import { pickLocalized } from "@/lib/lms/localized";
import type { AnswerValue, ApplicationOwnOut } from "@/lib/lms/types";
import { Button, ErrorState, LinkButton, LoadingState, PageHeader } from "@/components/ui";
import { FormRenderer, answersPayload, validateAnswers, type Answers } from "@/components/lms/enrollmentForm/FormRenderer";
import { useApplicationErrorText } from "./useApplicationErrorText";

export function ApplyPage({ courseId }: { courseId: string }) {
  const { lang, t } = useTranslation();
  const errorText = useApplicationErrorText();
  const [course, setCourse] = useState<CourseLandingOut | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<unknown>(null);
  const [values, setValues] = useState<Answers>({});
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [submitError, setSubmitError] = useState<unknown>(null);
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<ApplicationOwnOut | null>(null);
  const errorRef = useRef<HTMLDivElement>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      setCourse(await getCourseLanding(courseId));
    } catch (e) {
      setLoadError(e);
    } finally {
      setLoading(false);
    }
  }, [courseId]);
  useEffect(() => { void load(); }, [load]);

  const landingHref = `/${lang}/courses/catalog/${courseId}`;
  const catalogHref = `/${lang}/courses/catalog`;

  if (loading && !course) return <div className="mx-auto w-full max-w-2xl"><LoadingState rows={5} /></div>;
  if (loadError || !course) {
    return (
      <div className="mx-auto w-full max-w-2xl">
        <PageHeader title={t("applications.apply.title")} breadcrumbs={[{ label: t("catalog.title"), href: catalogHref }]} />
        <ErrorState message={errorText(loadError)} onRetry={() => void load()} retrying={loading}
          action={<LinkButton variant="secondary" href={catalogHref}>{t("catalog.landing.backToCatalog")}</LinkButton>} />
      </div>
    );
  }

  const title = pickLocalized(course.title, lang, course.default_language) || t("courses.list.untitled");
  const crumbs = [{ label: t("catalog.title"), href: catalogHref }, { label: title, href: landingHref }, { label: t("applications.apply.title") }];
  const form = course.form;

  // Done: "Application sent" (pending) or "You are in" (form_auto approved the application at once).
  if (result) {
    const approved = result.status === "approved";
    return (
      <div className="mx-auto w-full max-w-2xl">
        <PageHeader title={title} breadcrumbs={crumbs} />
        <section role="status" className="rounded-2xl border border-slate-200 bg-white p-6 text-center shadow-sm">
          {approved
            ? <CheckCircle2 className="mx-auto h-10 w-10 text-success-600" aria-hidden="true" />
            : <Clock className="mx-auto h-10 w-10 text-warning-600" aria-hidden="true" />}
          <h2 className="mt-3 text-xl font-semibold leading-7 text-slate-900">
            {approved ? t("applications.apply.approvedTitle") : t("applications.apply.sentTitle")}
          </h2>
          <p className="mt-2 text-base leading-6 text-slate-700">
            {approved ? t("applications.apply.approvedBody") : t("applications.apply.sentBody")}
          </p>
          <div className="mt-5 flex flex-col items-center gap-2 sm:flex-row sm:justify-center">
            {approved
              ? <LinkButton href={`/${lang}/courses/${course.id}`}>{t("catalog.landing.openCourse")}</LinkButton>
              : <LinkButton href={landingHref}>{t("applications.apply.viewStatus")}</LinkButton>}
            <LinkButton variant="secondary" href={catalogHref}>{t("catalog.landing.backToCatalog")}</LinkButton>
          </div>
        </section>
      </div>
    );
  }

  // Nothing to apply to: already in, already pending, not a form course or no active form.
  const blocked = isActiveMember(course) ? "member"
    : course.my_application?.status === "pending" ? "pending"
      : !isFormMode(course.enrollment_mode) || !form ? "notOpen" : null;
  if (blocked || !form) {
    return (
      <div className="mx-auto w-full max-w-2xl">
        <PageHeader title={title} breadcrumbs={crumbs} />
        <ErrorState title={t(`applications.apply.blocked.${blocked ?? "notOpen"}Title`)} message={t(`applications.apply.blocked.${blocked ?? "notOpen"}Body`)}
          action={blocked === "member"
            ? <LinkButton href={`/${lang}/courses/${course.id}`}>{t("catalog.landing.openCourse")}</LinkButton>
            : <LinkButton variant="secondary" href={landingHref}>{t("applications.apply.backToCourse")}</LinkButton>} />
      </div>
    );
  }

  const setAnswer = (key: string, value: AnswerValue) => {
    setValues((v) => ({ ...v, [key]: value }));
    if (fieldErrors[key]) setFieldErrors((e) => { const n = { ...e }; delete n[key]; return n; });
  };

  const submit = async (ev: React.FormEvent) => {
    ev.preventDefault();
    setSubmitError(null);
    const local = validateAnswers(form.fields, values);
    setFieldErrors(local);
    if (Object.keys(local).length) {
      setTimeout(() => errorRef.current?.focus(), 0);
      return;
    }
    setSubmitting(true);
    try {
      setResult(await submitApplication(course.id, form.id, answersPayload(form.fields, values)));
      setValues({}); // nothing of the answers stays in memory after the hand-off
    } catch (e) {
      const byField = answerErrors(e);
      if (byField) setFieldErrors(byField);
      else setSubmitError(e);
      if ((e as { code?: string }).code === "form_changed") void load();
      setTimeout(() => errorRef.current?.focus(), 0);
    } finally {
      setSubmitting(false);
    }
  };

  const errorCount = Object.keys(fieldErrors).length;
  const formTitle = pickLocalized(form.title, lang, course.default_language);

  return (
    <div className="mx-auto w-full max-w-2xl">
      <PageHeader title={formTitle || t("applications.apply.title")} description={title} breadcrumbs={crumbs} />
      <form onSubmit={submit} noValidate className="space-y-6">
        <div className="flex items-start gap-3 rounded-2xl border border-brand-200 bg-brand-50 p-4 text-base leading-6 text-brand-900 sm:text-sm">
          <ShieldCheck className="mt-0.5 h-5 w-5 shrink-0" aria-hidden="true" />
          <p>{t("applications.privacyNote")}</p>
        </div>
        <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:p-6">
          <FormRenderer form={form} lang={lang} defaultLanguage={course.default_language} values={values}
            onChange={setAnswer} errors={fieldErrors} disabled={submitting} idPrefix="apply" />
        </section>
        <div ref={errorRef} tabIndex={-1} className="focus:outline-none">
          {errorCount > 0 && (
            <ErrorState variant="inline" title={t("applications.apply.checkForm")} message={t("applications.apply.fixFields", { count: errorCount })} />
          )}
          {submitError ? <ErrorState variant="inline" message={errorText(submitError)} /> : null}
        </div>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
          <Button type="submit" size="lg" loading={submitting}>{t("applications.apply.submit")}</Button>
          <LinkButton variant="secondary" size="lg" href={landingHref}>{t("ui.cancel")}</LinkButton>
        </div>
      </form>
    </div>
  );
}
