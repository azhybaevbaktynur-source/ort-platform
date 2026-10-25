"use client";

import React, { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useTranslation } from "@/lib/i18n/context";
import { cleanLocalized } from "@/lib/lms/localized";
import { createOrgCourse, searchOrgMembers } from "@/lib/lms/organizations";
import { listCourseTemplates, templateTitle, type TemplateChoiceOut } from "@/lib/lms/templates";
import type { Lang, LocalizedText } from "@/lib/lms/types";
import { LanguagePicker } from "@/components/lms/LanguagePicker";
import { LocalizedTextInput } from "@/components/lms/LocalizedTextInput";
import { UserPicker, type PickedUser, type UserSearch } from "@/components/lms/UserPicker";
import { useOrg } from "@/components/lms/org/OrgShell";
import { OrgError, btn, cardCls, inputCls, labelCls } from "@/components/lms/org/OrgUi";

/** Org admin creates a course and assigns its owner (design §3, A2). */
export default function OrgNewCoursePage() {
  const { lang, t } = useTranslation();
  const router = useRouter();
  const { org, readOnly } = useOrg();
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
  return (
    <form onSubmit={submit} noValidate className={`${cardCls} mx-auto max-w-2xl space-y-6`}>
      <div>
        <Link href={`/${lang}/org/${org.id}/courses`} className="text-sm font-medium text-brand-700 hover:underline">{t("organizations.courses.back")}</Link>
        <h2 className="mt-2 text-xl font-bold text-slate-900">{t("organizations.courses.createTitle")}</h2>
        <p className="mt-1 text-sm text-slate-600">{t("organizations.courses.createHint", { org: org.name })}</p>
      </div>
      <LanguagePicker languages={languages} defaultLanguage={defaultLanguage} disabled={disabled}
        onChange={(ls, d) => { setLanguages(ls); setDefaultLanguage(d); }} />
      <LocalizedTextInput label={t("courses.create.courseTitle")} languages={languages} defaultLanguage={defaultLanguage}
        value={title} onChange={setTitle} maxLength={200} required disabled={disabled} />
      {titleMissing && <p role="alert" className="text-sm text-red-700">{t("lms.errors.title_required")}</p>}
      <LocalizedTextInput label={t("courses.create.description")} languages={languages} defaultLanguage={defaultLanguage}
        value={description} onChange={setDescription} multiline maxLength={5000} disabled={disabled} />
      <div>
        <label htmlFor="c-template" className={labelCls}>{t("templates.field")}</label>
        <select id="c-template" className={inputCls} value={templateKey} disabled={disabled} onChange={(e) => setTemplateKey(e.target.value)}>
          <option value="">{t("templates.general")}</option>
          {templates.map((tp) => <option key={tp.key} value={tp.key}>{templateTitle(t, tp.key, tp.title_key)}</option>)}
        </select>
        <p className="mt-1 text-xs text-slate-500">{templateKey ? t("templates.lockedHint") : t("templates.generalHint")}</p>
        {templatesError ? <OrgError error={templatesError} className="mt-2" /> : null}
      </div>
      <div>
        <UserPicker label={t("organizations.courses.ownerField")} hint={t("organizations.courses.ownerHint")}
          value={owner} onChange={(u) => { setOwner(u); setOwnerMissing(false); }} search={searchMembers} disabled={disabled} />
        {ownerMissing && <p role="alert" className="mt-1 text-sm text-red-700">{t("organizations.courses.ownerMissing")}</p>}
      </div>
      <OrgError error={error} />
      <div className="flex flex-wrap justify-end gap-2">
        <Link href={`/${lang}/org/${org.id}/courses`} className={btn.secondary}>{t("lms.common.cancel")}</Link>
        <button type="submit" disabled={disabled} className={btn.primary}>{busy ? t("lms.common.loading") : t("courses.create.submit")}</button>
      </div>
    </form>
  );
}
