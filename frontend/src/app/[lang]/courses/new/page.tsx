"use client";

/*
 * FB8-5 S3 (STAFF_UX_AUDIT 4, D-FB8-5-6): create a course. A compact 720 px form with the live course card beside it
 * (above it on phones): organization (several only), template (only when the organization holds a grant), main
 * language + optional translations, title, description, cover (kept in the browser, uploaded right after the course
 * exists), enrollment. After create: the catalog switch (PATCH visibility) and the cover upload; a failure there
 * shows a toast and opens the matching settings section, the course itself is made.
 */
import React, { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { useTranslation } from "@/lib/i18n/context";
import { createCourse, updateCourse } from "@/lib/lms/courses";
import { uploadCourseCover } from "@/lib/lms/courseCover";
import { cleanLocalized } from "@/lib/lms/localized";
import { useLmsMe } from "@/lib/lms/useLmsMe";
import { templateTitle } from "@/lib/lms/templates";
import type { EnrollmentMode, Lang, LocalizedText } from "@/lib/lms/types";
import { ErrorMessage } from "@/components/lms/ErrorMessage";
import { LocalizedTextInput } from "@/components/lms/LocalizedTextInput";
import { LanguageFields, moveSingleLanguageText } from "@/components/lms/course/form/LanguageFields";
import { CoverPicker, type PendingCover } from "@/components/lms/course/form/CoverPicker";
import { CoursePreview } from "@/components/lms/course/form/CoursePreview";
import { listMyOrganizations, orgPickerLabel, type MyOrganizationOut } from "@/lib/lms/organizations"; // Phase 6 S4b
import { Button, Card, Input, LinkButton, PageHeader, STAFF_WIDTH, Select, Switch, cn, useToast } from "@/components/ui";

/** Modes a new course can have (form modes need an active form, which only exists after create). */
const CREATE_MODES: EnrollmentMode[] = ["invite_code", "open", "closed"];

export default function NewCoursePage() {
  const { lang, t } = useTranslation();
  const router = useRouter();
  const { toast } = useToast();
  const { me, loading } = useLmsMe();
  const initial = lang as Lang;
  const [languages, setLanguages] = useState<Lang[]>([initial]);
  const [defaultLanguage, setDefaultLanguage] = useState<Lang>(initial);
  const [title, setTitle] = useState<LocalizedText>({});
  const [description, setDescription] = useState<LocalizedText>({});
  const [mode, setMode] = useState<EnrollmentMode>("invite_code");
  const [limit, setLimit] = useState("");
  const [catalog, setCatalog] = useState(false);
  const [cover, setCover] = useState<PendingCover | null>(null);
  const [templateKey, setTemplateKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [titleMissing, setTitleMissing] = useState(false);
  // --- Phase 6 S4b: a teacher in several organizations chooses one (else 422 organization_required) ---
  const [orgs, setOrgs] = useState<MyOrganizationOut[]>([]);
  const [orgId, setOrgId] = useState("");
  const [orgMissing, setOrgMissing] = useState(false);
  useEffect(() => {
    let alive = true;
    listMyOrganizations()
      .then((rows) => { if (alive) setOrgs(rows.filter((o) => o.can_create_courses)); })
      .catch(() => { if (alive) setOrgs([]); });
    return () => { alive = false; };
  }, []);
  const chooseOrg = orgs.length > 1;
  // --- Phase 6 S4b end ---
  /** the organization the course goes to: the chosen one, or the only one */
  const org = chooseOrg ? orgs.find((o) => o.id === orgId) ?? null : orgs[0] ?? null;
  const templateKeys = useMemo(() => org?.template_keys ?? [], [org]);
  // a template granted to the previous organization only is dropped
  useEffect(() => { if (templateKey && !templateKeys.includes(templateKey)) setTemplateKey(""); }, [templateKey, templateKeys]);

  if (loading) return <p role="status" className="text-sm text-slate-500">{t("lms.common.loading")}</p>;
  if (me && !me.can_create_courses) {
    return (
      <div role="alert" className="rounded-2xl border border-slate-200 bg-white p-8 text-center">
        <h1 className="text-xl font-bold text-slate-900">{t("teacherOnly.title")}</h1>
        <p className="mt-2 text-base leading-6 text-slate-600 sm:text-sm">{t("teacherOnly.courseBody")}</p>
        <div className="mt-6 flex flex-col-reverse justify-center gap-3 sm:flex-row">
          <LinkButton href={`/${lang}/courses`}>{t("teacherOnly.back")}</LinkButton>
        </div>
      </div>
    );
  }

  const changeLanguages = (ls: Lang[], d: Lang, from: Lang) => {
    setTitle((v) => moveSingleLanguageText(v, languages, from, d));
    setDescription((v) => moveSingleLanguageText(v, languages, from, d));
    setLanguages(ls);
    setDefaultLanguage(d);
  };

  const submit = async (ev: React.FormEvent) => {
    ev.preventDefault();
    const cleanTitle = cleanLocalized(title, languages);
    const noOrg = chooseOrg && !orgId; // Phase 6 S4b
    setOrgMissing(noOrg);
    if (!cleanTitle[defaultLanguage]) {
      setTitleMissing(true);
      return;
    }
    setTitleMissing(false);
    if (noOrg) return;
    setBusy(true);
    setError(null);
    let course;
    try {
      const n = limit.trim() ? parseInt(limit, 10) : null;
      const cleanDescription = cleanLocalized(description, languages);
      course = await createCourse({
        title: cleanTitle,
        // an empty description is left out: the server refuses `{}` (at least one non-empty translation)
        ...(Object.keys(cleanDescription).length ? { description: cleanDescription } : {}),
        languages,
        default_language: defaultLanguage,
        enrollment_mode: mode,
        enrollment_limit: n,
        ...(chooseOrg ? { organization_id: orgId } : {}), // Phase 6 S4b
        ...(templateKey ? { template_key: templateKey } : {}),
      });
    } catch (e) {
      setError(e);
      setBusy(false);
      return;
    }
    // the course exists: what follows only adds to it; a failure opens the settings section to finish there
    const base = `/${lang}/courses/${course.id}`;
    if (catalog) {
      try {
        await updateCourse(course.id, { visibility: "catalog" });
      } catch {
        toast.error(t("courses.create.catalogFailed"));
        router.push(`${base}/settings?section=enrollment`);
        return;
      }
    }
    if (cover) {
      try {
        await uploadCourseCover(course.id, cover.file, cover.fx, cover.fy);
      } catch {
        toast.error(t("courses.create.coverFailed"));
        router.push(`${base}/settings?section=cover`);
        return;
      }
    }
    router.push(base);
  };

  const previewOrg = org && org.kind !== "personal" ? org.name : null;

  return (
    <div className={cn("w-full", STAFF_WIDTH.formPreview)}>
      <PageHeader title={t("courses.create.pageTitle")} description={t("courses.create.subtitle")} />
      <div className="flex flex-col gap-6 lg:grid lg:grid-cols-[minmax(0,720px)_360px] lg:items-start lg:gap-8">
        <CoursePreview className="lg:order-2" cover={cover}
          course={{
            id: "new-course", title, description, languages, default_language: defaultLanguage,
            owner_display_name: me?.display_name ?? null, organization_display_name: previewOrg, cover_url: null,
          }} />
        <form onSubmit={submit} noValidate className="min-w-0 space-y-6 lg:order-1">
          <Card title={t("courses.create.basics")} headingLevel={2}>
            <div className="space-y-5">
              {/* --- Phase 6 S4b --- */}
              {chooseOrg && (
                <Select id="new-org" label={t("organizations.fields.organization")} value={orgId} disabled={busy}
                  aria-invalid={orgMissing || undefined} placeholder={t("organizations.fields.organizationPick")}
                  onChange={(e) => setOrgId(e.target.value)}
                  error={orgMissing ? t("organizations.errors.organization_required") : undefined}
                  hint={orgMissing ? undefined : t("organizations.fields.organizationHint")}
                  options={orgs.map((o) => ({ value: o.id, label: orgPickerLabel(o, t) }))} />
              )}
              {/* --- Phase 6 S4b end --- */}
              {templateKeys.length > 0 && (
                <Select id="new-template" label={t("templates.field")} value={templateKey} disabled={busy}
                  onChange={(e) => setTemplateKey(e.target.value)}
                  hint={templateKey ? t("templates.lockedHint") : t("templates.generalHint")}
                  options={[{ value: "", label: t("templates.general") },
                    ...templateKeys.map((k) => ({ value: k, label: templateTitle(t, k) }))]} />
              )}
              <LanguageFields idPrefix="new" languages={languages} defaultLanguage={defaultLanguage} disabled={busy} onChange={changeLanguages} />
              <div>
                <LocalizedTextInput label={t("courses.create.courseTitle")} languages={languages} defaultLanguage={defaultLanguage}
                  value={title} onChange={setTitle} maxLength={200} required disabled={busy} fallbackHint />
                {titleMissing && <p role="alert" className="mt-1 text-sm text-danger-700">{t("lms.errors.title_required")}</p>}
              </div>
              <LocalizedTextInput label={t("courses.create.description")} languages={languages} defaultLanguage={defaultLanguage}
                value={description} onChange={setDescription} multiline maxLength={5000} disabled={busy} />
            </div>
          </Card>
          <Card title={t("courses.cover.title")} headingLevel={2}>
            <CoverPicker value={cover} onChange={setCover} disabled={busy} />
          </Card>
          <Card title={t("courses.settings.enrollment")} headingLevel={2}>
            <div className="space-y-4">
              <div className="grid gap-4 sm:grid-cols-2">
                <Select id="enroll-mode" label={t("courses.create.modeLabel")} value={mode} disabled={busy}
                  onChange={(e) => setMode(e.target.value as EnrollmentMode)}
                  hint={mode === "invite_code" ? t("courses.create.modeHintInviteCode") : t(`enrollmentForm.modeHints.${mode}`)}
                  options={CREATE_MODES.map((m) => ({ value: m, label: t(`enrollmentForm.modes.${m}`) }))} />
                <Input id="enroll-limit" type="number" min={1} max={10000} label={t("courses.create.limit")} value={limit} disabled={busy}
                  onChange={(e) => setLimit(e.target.value)} placeholder={t("courses.create.limitPlaceholder")} />
              </div>
              <Switch id="new-visibility" label={t("catalog.listing.linkAccess")} checked={catalog} disabled={busy}
                hint={t("courses.create.catalogHint")} onChange={setCatalog} />
            </div>
          </Card>
          <ErrorMessage error={error} />
          <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
            <LinkButton href={`/${lang}/courses`} variant="secondary">{t("lms.common.cancel")}</LinkButton>
            <Button type="submit" loading={busy}>{t("courses.create.submit")}</Button>
          </div>
        </form>
      </div>
    </div>
  );
}
