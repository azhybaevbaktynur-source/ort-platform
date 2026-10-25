"use client";

import React, { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { useTranslation } from "@/lib/i18n/context";
import { cleanLocalized } from "@/lib/lms/localized";
import { createOrgCourse, searchOrgMembers } from "@/lib/lms/organizations";
import { listCourseTemplates, templateTitle, type TemplateChoiceOut } from "@/lib/lms/templates";
import type { Lang, LocalizedText } from "@/lib/lms/types";
import { LanguagePicker } from "@/components/lms/LanguagePicker";
import { LocalizedTextInput } from "@/components/lms/LocalizedTextInput";
import { Button, Card, FieldError, LinkButton, PageHeader, Select, UserPicker, type PickedUser, type UserSearch } from "@/components/ui";
import { useOrg } from "@/components/lms/org/OrgShell";
import { OrgError } from "@/components/lms/org/OrgUi";

/** Org admin creates a course and assigns its owner (design §3, A2). */
export default function OrgNewCoursePage() {
  const { lang, t } = useTranslation();
  const router = useRouter();
  const { org, readOnly, crumbs } = useOrg();
  const initial: Lang = lang;
  const [languages, setLanguages] = useState<Lang[]>([initial]);
  const [defaultLanguage, setDefaultLanguage] = useState<Lang>(initial);
  const [title, setTitle] = useState<LocalizedText>({});
  const [description, setDescription] = useState<LocalizedText>({});
  const [templates, setTemplates] = useState<TemplateChoiceOut[]>([]);
  const [templatesError, setTemplatesError] = useState<unknown>(null);
  const [templateKey, setTemplateKey] = useState("");
  const [owner, setOwner] = useState<PickedUser | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [titleMissing, setTitleMissing] = useState(false);
  const [ownerMissing, setOwnerMissing] = useState(false);

  useEffect(() => {
    let alive = true;
    listCourseTemplates(org.id)
      .then((r) => { if (alive) setTemplates(Array.isArray(r) ? r : []); })
      .catch((e) => { if (alive) setTemplatesError(e); });
    return () => { alive = false; };
  }, [org.id]);

  const searchMembers: UserSearch = useMemo(() => async (q) => {
    return searchOrgMembers(org.id, q);
  }, [org.id]);

  const submit = async (ev: React.FormEvent) => {
    ev.preventDefault();
    const cleanTitle = cleanLocalized(title, languages);
    const noTitle = !cleanTitle[defaultLanguage];
    setTitleMissing(noTitle);
    setOwnerMissing(!owner);
    if (noTitle || !owner) return;
    setBusy(true);
    setError(null);
    try {
      const course = await createOrgCourse(org.id, {
        title: cleanTitle,
        description: cleanLocalized(description, languages),
        languages,
        default_language: defaultLanguage,
        organization_id: org.id,
        owner_id: owner.id,
        template_key: templateKey || null,
      });
      router.push(`/${lang}/org/${org.id}/courses/${course.id}`);
    } catch (e) {
      setError(e);
      setBusy(false);
    }
  };

  const disabled = busy || readOnly;
  const coursesHref = `/${lang}/org/${org.id}/courses`;
  return (
    <div className="max-w-2xl">
      <PageHeader title={t("organizations.courses.createTitle")} description={t("organizations.courses.createHint", { org: org.name })}
        breadcrumbs={crumbs({ label: t("organizations.org.nav.courses"), href: coursesHref }, { label: t("organizations.courses.createTitle") })} />
    <Card>
    <form onSubmit={submit} noValidate className="space-y-6">
      <LanguagePicker languages={languages} defaultLanguage={defaultLanguage} disabled={disabled}
        onChange={(ls, d) => { setLanguages(ls); setDefaultLanguage(d); }} />
      <LocalizedTextInput label={t("courses.create.courseTitle")} languages={languages} defaultLanguage={defaultLanguage}
        value={title} onChange={setTitle} maxLength={200} required disabled={disabled} />
      {titleMissing && <div role="alert" className="-mt-4"><FieldError>{t("lms.errors.title_required")}</FieldError></div>}
      <LocalizedTextInput label={t("courses.create.description")} languages={languages} defaultLanguage={defaultLanguage}
        value={description} onChange={setDescription} multiline maxLength={5000} disabled={disabled} />
      <div>
        <Select id="c-template" label={t("templates.field")} value={templateKey} disabled={disabled} onChange={(e) => setTemplateKey(e.target.value)}
          hint={templateKey ? t("templates.lockedHint") : t("templates.generalHint")}
          options={[{ value: "", label: t("templates.general") }, ...templates.map((tp) => ({ value: tp.key, label: templateTitle(t, tp.key, tp.title_key) }))]} />
        {templatesError ? <OrgError error={templatesError} className="mt-2" /> : null}
      </div>
      <div>
        <UserPicker label={t("organizations.courses.ownerField")} hint={t("organizations.courses.ownerHint")}
          value={owner} onChange={(u) => { setOwner(u); setOwnerMissing(false); }} search={searchMembers} disabled={disabled} />
        {ownerMissing && <div role="alert"><FieldError>{t("organizations.courses.ownerMissing")}</FieldError></div>}
      </div>
      <OrgError error={error} />
      <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
        <LinkButton variant="secondary" href={coursesHref}>{t("lms.common.cancel")}</LinkButton>
        <Button type="submit" disabled={readOnly} loading={busy}>{t("courses.create.submit")}</Button>
      </div>
    </form>
    </Card>
    </div>
  );
}
