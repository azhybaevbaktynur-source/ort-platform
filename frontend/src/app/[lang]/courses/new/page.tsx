"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useTranslation } from "@/lib/i18n/context";
import { createCourse } from "@/lib/lms/courses";
import { cleanLocalized } from "@/lib/lms/localized";
import { useLmsMe } from "@/lib/lms/useLmsMe";
import type { Lang, LocalizedText } from "@/lib/lms/types";
import { ErrorMessage } from "@/components/lms/ErrorMessage";
import { LanguagePicker } from "@/components/lms/LanguagePicker";
import { LocalizedTextInput } from "@/components/lms/LocalizedTextInput";
import { listMyOrganizations, type MyOrganizationOut } from "@/lib/lms/organizations"; // Phase 6 S4b

export default function NewCoursePage() {
  const { lang, t } = useTranslation();
  const router = useRouter();
  const { me, loading } = useLmsMe();
  const initial: Lang = lang;
  const [languages, setLanguages] = useState<Lang[]>([initial]);
  const [defaultLanguage, setDefaultLanguage] = useState<Lang>(initial);
  const [title, setTitle] = useState<LocalizedText>({});
  const [description, setDescription] = useState<LocalizedText>({});
  const [mode, setMode] = useState<"invite_code" | "closed">("invite_code");
  const [limit, setLimit] = useState("");
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

  if (loading) return <p role="status" className="text-sm text-slate-500">{t("lms.common.loading")}</p>;
  if (me && !me.can_create_courses) {
    return (
      <div className="mx-auto max-w-xl rounded-2xl border border-slate-200 bg-white p-6">
        <p className="text-sm text-slate-700">{t("lms.errors.teacher_not_approved")}</p>
        <Link href={`/${lang}/courses/become-teacher`} className="mt-3 inline-block text-sm font-semibold text-brand-700 underline">{t("lms.nav.becomeTeacher")}</Link>
      </div>
    );
  }

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
    try {
      const n = limit.trim() ? parseInt(limit, 10) : null;
      const course = await createCourse({
        title: cleanTitle,
        description: cleanLocalized(description, languages),
        languages,
        default_language: defaultLanguage,
        enrollment_mode: mode,
        enrollment_limit: n,
        ...(chooseOrg ? { organization_id: orgId } : {}), // Phase 6 S4b
      });
      router.push(`/${lang}/courses/${course.id}`);
    } catch (e) {
      setError(e);
      setBusy(false);
    }
  };

  return (
    <form onSubmit={submit} noValidate className="mx-auto max-w-2xl space-y-6 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
      <h1 className="text-xl font-bold text-slate-900">{t("courses.create.title")}</h1>
      {/* --- Phase 6 S4b --- */}
      {chooseOrg && (
        <div>
          <label htmlFor="new-org" className="mb-1 block text-sm font-medium text-slate-700">{t("organizations.fields.organization")}</label>
          <select id="new-org" value={orgId} disabled={busy} aria-invalid={orgMissing} onChange={(e) => setOrgId(e.target.value)}
            className="w-full rounded-xl border border-slate-300 px-3 py-2.5 text-sm">
            <option value="">{t("organizations.fields.organizationPick")}</option>
            {orgs.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
          </select>
          <p className={`mt-1 text-xs ${orgMissing ? "text-red-700" : "text-slate-500"}`} role={orgMissing ? "alert" : undefined}>
            {orgMissing ? t("organizations.errors.organization_required") : t("organizations.fields.organizationHint")}
          </p>
        </div>
      )}
      {/* --- Phase 6 S4b end --- */}
      <LanguagePicker languages={languages} defaultLanguage={defaultLanguage} disabled={busy}
        onChange={(ls, d) => { setLanguages(ls); setDefaultLanguage(d); }} />
      <LocalizedTextInput label={t("courses.create.courseTitle")} languages={languages} defaultLanguage={defaultLanguage}
        value={title} onChange={setTitle} maxLength={200} required disabled={busy} />
      {titleMissing && <p role="alert" className="text-sm text-red-700">{t("lms.errors.title_required")}</p>}
      <LocalizedTextInput label={t("courses.create.description")} languages={languages} defaultLanguage={defaultLanguage}
        value={description} onChange={setDescription} multiline maxLength={5000} disabled={busy} />
      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <label htmlFor="enroll-mode" className="mb-1 block text-sm font-medium text-slate-700">{t("courses.create.enrollmentMode")}</label>
          <select id="enroll-mode" value={mode} disabled={busy} onChange={(e) => setMode(e.target.value as "invite_code" | "closed")}
            className="w-full rounded-xl border border-slate-300 px-3 py-2.5 text-sm">
            <option value="invite_code">{t("courses.create.modeInviteCode")}</option>
            <option value="closed">{t("courses.create.modeClosed")}</option>
          </select>
        </div>
        <div>
          <label htmlFor="enroll-limit" className="mb-1 block text-sm font-medium text-slate-700">{t("courses.create.limit")}</label>
          <input id="enroll-limit" type="number" min={1} max={10000} value={limit} disabled={busy} onChange={(e) => setLimit(e.target.value)}
            placeholder={t("courses.create.limitPlaceholder")} className="w-full rounded-xl border border-slate-300 px-3 py-2.5 text-sm" />
        </div>
      </div>
      <ErrorMessage error={error} />
      <div className="flex justify-end gap-2">
        <Link href={`/${lang}/courses`} className="rounded-xl border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50">{t("lms.common.cancel")}</Link>
        <button type="submit" disabled={busy} className="rounded-xl bg-brand-600 px-5 py-2 text-sm font-semibold text-white hover:bg-brand-700 disabled:opacity-50">
          {busy ? t("lms.common.loading") : t("courses.create.submit")}
        </button>
      </div>
    </form>
  );
}
