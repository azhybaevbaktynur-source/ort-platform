"use client";

import React, { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useTranslation } from "@/lib/i18n/context";
import {
  concludeCourse, deleteCourse, formatJoinCode as formatCode, listPeople, publishCourse, regenerateJoinCode, reopenCourse, transferOwnership,
  unpublishCourse, updateCourse,
} from "@/lib/lms/courses";
import { cleanLocalized } from "@/lib/lms/localized";
import { isStaffCourse, type CourseStaffOut, type Lang, type LocalizedText, type RosterEntryOut } from "@/lib/lms/types";
import { useCourse } from "@/components/lms/CourseContext";
import { ErrorMessage } from "@/components/lms/ErrorMessage";
import { JoinCodeDisplay } from "@/components/lms/JoinCodeDisplay";
import { LanguagePicker } from "@/components/lms/LanguagePicker";
import { LocalizedTextInput } from "@/components/lms/LocalizedTextInput";
import { CourseGradingSection } from "@/components/lms/grading/settings/CourseGradingSection";
import { CourseHomeSection } from "@/components/lms/modules/CourseHomeSection"; // Phase 8a S4a
import { ConfirmDialog, PageHeader, buttonClasses } from "@/components/ui";
import { pickLocalized } from "@/lib/lms/localized";

// Phase 6b S5c: design-system buttons; each settings card keeps its own save (one sticky save bar is Phase 7, UX T28).
const card = "rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:p-6";
const primaryBtn = buttonClasses({ variant: "primary", size: "sm" });
const secondaryBtn = buttonClasses({ variant: "secondary", size: "sm" });
const dangerOutlineBtn = buttonClasses({ variant: "secondary", size: "sm", className: "border-danger-300 text-danger-700 hover:bg-danger-50" });
const dangerBtn = buttonClasses({ variant: "danger", size: "sm" });

function Settings({ course }: { course: CourseStaffOut }) {
  const { lang, t } = useTranslation();
  const router = useRouter();
  const { setCourse } = useCourse();
  const isOwner = course.is_owner;

  const [languages, setLanguages] = useState<Lang[]>(course.languages);
  const [defaultLanguage, setDefaultLanguage] = useState<Lang>(course.default_language);
  const [title, setTitle] = useState<LocalizedText>(course.title);
  const [description, setDescription] = useState<LocalizedText>(course.description ?? {});
  const [mode, setMode] = useState<"invite_code" | "closed">(course.enrollment_mode === "closed" ? "closed" : "invite_code");
  const [limit, setLimit] = useState(course.enrollment_limit ? String(course.enrollment_limit) : "");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<{ section: string; err: unknown } | null>(null);
  const [saved, setSaved] = useState<string | null>(null);
  const [confirm, setConfirm] = useState<null | "regenerate" | "unpublish" | "conclude" | "delete" | "transfer">(null);
  const [teachers, setTeachers] = useState<RosterEntryOut[]>([]);
  const [newOwner, setNewOwner] = useState("");

  useEffect(() => {
    if (!isOwner) return;
    listPeople(course.id, { role: "teacher", state: "active", limit: 100 })
      .then((p) => setTeachers((p.items as RosterEntryOut[]).filter((e) => !e.is_owner)))
      .catch(() => setTeachers([]));
  }, [course.id, isOwner]);

  const run = async (section: string, fn: () => Promise<void>) => {
    setBusy(section);
    setError(null);
    setSaved(null);
    try {
      await fn();
      setSaved(section);
      return true;
    } catch (err) {
      setError({ section, err });
      return false;
    } finally {
      setBusy(null);
    }
  };

  // The API returns CourseStaffOut for every course mutation; keep the shared context in sync.
  const apply = (c: CourseStaffOut) => setCourse(c);
  const errFor = (s: string) => (error?.section === s ? error.err : null);
  const savedFor = (s: string) => saved === s && <p role="status" className="text-sm text-success-700">{t("courses.settings.saved")}</p>;

  const saveGeneral = (ev: React.FormEvent) => {
    ev.preventDefault();
    void run("general", async () => {
      apply(await updateCourse(course.id, {
        title: cleanLocalized(title, languages),
        description: cleanLocalized(description, languages),
        languages,
        default_language: defaultLanguage,
      }));
    });
  };
  const saveEnrollment = (ev: React.FormEvent) => {
    ev.preventDefault();
    void run("enrollment", async () => {
      apply(await updateCourse(course.id, { enrollment_mode: mode, enrollment_limit: limit.trim() ? parseInt(limit, 10) : null }));
    });
  };

  const lifecycle = (name: "publish" | "unpublish" | "conclude" | "reopen") => {
    const fn = { publish: publishCourse, unpublish: unpublishCourse, conclude: concludeCourse, reopen: reopenCourse }[name];
    return run("lifecycle", async () => apply(await fn(course.id)));
  };

  const doConfirm = async () => {
    if (confirm === "regenerate") {
      if (await run("enrollment", async () => { const r = await regenerateJoinCode(course.id); apply({ ...course, join_code: r.join_code }); })) setConfirm(null);
    } else if (confirm === "unpublish") {
      if (await lifecycle("unpublish")) setConfirm(null);
    } else if (confirm === "conclude") {
      if (await lifecycle("conclude")) setConfirm(null);
    } else if (confirm === "delete") {
      if (await run("danger", async () => { await deleteCourse(course.id); router.push(`/${lang}/courses`); })) setConfirm(null);
    } else if (confirm === "transfer") {
      if (await run("danger", async () => apply(await transferOwnership(course.id, newOwner)))) setConfirm(null);
    }
  };

  const dialogCfg = {
    regenerate: { title: t("courses.settings.regenerateTitle"), body: t("courses.settings.regenerateBody"), label: t("courses.settings.regenerate"), danger: false, section: "enrollment" },
    unpublish: { title: t("courses.settings.unpublishTitle"), body: t("courses.settings.unpublishBody"), label: t("courses.settings.unpublish"), danger: false, section: "lifecycle" },
    conclude: { title: t("courses.settings.concludeTitle"), body: t("courses.settings.concludeBody"), label: t("courses.settings.conclude"), danger: false, section: "lifecycle" },
    delete: { title: t("courses.settings.deleteTitle"), body: t("courses.settings.deleteBody"), label: t("courses.settings.delete"), danger: true, section: "danger" },
    transfer: { title: t("courses.settings.transferTitle"), body: t("courses.settings.transferBody"), label: t("courses.settings.transfer"), danger: true, section: "danger" },
  } as const;
  const cfg = confirm ? dialogCfg[confirm] : null;
  const st = course.status;

  const courseName = pickLocalized(course.title, lang, course.default_language) || t("courses.list.untitled");
  const ownerName = teachers.find((e) => e.user.id === newOwner);
  const objectFor = (c: NonNullable<typeof confirm>) =>
    c === "transfer" && ownerName ? `${courseName} → ${ownerName.user.display_name || ownerName.user.email}` : c === "regenerate" ? formatCode(course.join_code) : courseName;

  return (
    <div className="space-y-6">
      <PageHeader title={t("courses.settings.tab")} className="mb-2" />
      <form onSubmit={saveGeneral} className={`${card} space-y-5`} noValidate>
        <h2 className="text-lg font-bold text-slate-900">{t("courses.settings.general")}</h2>
        <LanguagePicker languages={languages} defaultLanguage={defaultLanguage} disabled={busy === "general"}
          onChange={(ls, d) => { setLanguages(ls); setDefaultLanguage(d); }} />
        <LocalizedTextInput label={t("courses.create.courseTitle")} languages={languages} defaultLanguage={defaultLanguage}
          value={title} onChange={setTitle} maxLength={200} required disabled={busy === "general"} />
        <LocalizedTextInput label={t("courses.create.description")} languages={languages} defaultLanguage={defaultLanguage}
          value={description} onChange={setDescription} multiline maxLength={5000} disabled={busy === "general"} />
        <ErrorMessage error={errFor("general")} />
        <div className="flex items-center gap-3">
          <button type="submit" disabled={busy === "general"} className={primaryBtn}>{busy === "general" ? t("lms.common.loading") : t("lms.common.save")}</button>
          {savedFor("general")}
        </div>
      </form>

      {/* --- Phase 8a S4a: course home (locked on ORT with the template note) --- */}
      <CourseHomeSection course={course} />
      {/* --- Phase 8a S4a end --- */}

      <section className={`${card} space-y-5`}>
        <h2 className="text-lg font-bold text-slate-900">{t("courses.settings.enrollment")}</h2>
        <div>
          <p className="mb-2 text-sm font-medium text-slate-700">{t("courses.settings.joinCode")}</p>
          <JoinCodeDisplay code={course.join_code} />
          <p className="mt-2 text-xs text-slate-500">{t("courses.settings.joinCodeHint")}</p>
          {(st !== "published" || course.enrollment_mode !== "invite_code") && (
            <p className="mt-1 text-xs text-amber-700">{t("courses.settings.joinCodeInactive")}</p>
          )}
          <button type="button" className={`${secondaryBtn} mt-3`} disabled={busy === "enrollment"} onClick={() => { setError(null); setConfirm("regenerate"); }}>
            {t("courses.settings.regenerate")}
          </button>
        </div>
        <form onSubmit={saveEnrollment} className="space-y-4" noValidate>
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label htmlFor="s-mode" className="mb-1 block text-sm font-medium text-slate-700">{t("courses.create.enrollmentMode")}</label>
              <select id="s-mode" value={mode} disabled={busy === "enrollment"} onChange={(e) => setMode(e.target.value as "invite_code" | "closed")}
                className="w-full rounded-xl border border-slate-300 px-3 py-2.5 text-sm">
                <option value="invite_code">{t("courses.create.modeInviteCode")}</option>
                <option value="closed">{t("courses.create.modeClosed")}</option>
              </select>
            </div>
            <div>
              <label htmlFor="s-limit" className="mb-1 block text-sm font-medium text-slate-700">{t("courses.create.limit")}</label>
              <input id="s-limit" type="number" min={1} max={10000} value={limit} disabled={busy === "enrollment"} onChange={(e) => setLimit(e.target.value)}
                placeholder={t("courses.create.limitPlaceholder")} className="w-full rounded-xl border border-slate-300 px-3 py-2.5 text-sm" />
              <p className="mt-1 text-xs text-slate-500">{t("courses.settings.activeStudents", { count: course.active_student_count })}</p>
            </div>
          </div>
          <ErrorMessage error={errFor("enrollment")} />
          <div className="flex items-center gap-3">
            <button type="submit" disabled={busy === "enrollment"} className={primaryBtn}>{busy === "enrollment" ? t("lms.common.loading") : t("lms.common.save")}</button>
            {savedFor("enrollment")}
          </div>
        </form>
      </section>

      <CourseGradingSection courseId={course.id} languages={course.languages} defaultLanguage={course.default_language} />

      <section className={`${card} space-y-4`}>
        <h2 className="text-lg font-bold text-slate-900">{t("courses.settings.lifecycle")}</h2>
        <p className="text-sm text-slate-600">{t(`courses.settings.lifecycleHint.${st}`)}</p>
        <div className="flex flex-wrap gap-2">
          {st === "draft" && <button type="button" disabled={busy === "lifecycle"} onClick={() => void lifecycle("publish")} className={primaryBtn}>{t("courses.settings.publish")}</button>}
          {st === "published" && (
            <>
              <button type="button" disabled={busy === "lifecycle"} onClick={() => { setError(null); setConfirm("unpublish"); }} className={secondaryBtn}>{t("courses.settings.unpublish")}</button>
              <button type="button" disabled={busy === "lifecycle"} onClick={() => { setError(null); setConfirm("conclude"); }} className={secondaryBtn}>{t("courses.settings.conclude")}</button>
            </>
          )}
          {st === "concluded" && <button type="button" disabled={busy === "lifecycle"} onClick={() => void lifecycle("reopen")} className={primaryBtn}>{t("courses.settings.reopen")}</button>}
        </div>
        {!confirm && <ErrorMessage error={errFor("lifecycle")} />}
        {savedFor("lifecycle")}
      </section>

      {isOwner && (
        <section className="space-y-5 rounded-2xl border border-danger-200 bg-white p-4 shadow-sm sm:p-6">
          <h2 className="text-lg font-bold text-danger-700">{t("courses.settings.danger")}</h2>
          <div>
            <label htmlFor="s-owner" className="mb-1 block text-sm font-medium text-slate-700">{t("courses.settings.newOwner")}</label>
            <div className="flex flex-wrap items-center gap-2">
              <select id="s-owner" value={newOwner} onChange={(e) => setNewOwner(e.target.value)} className="min-h-11 w-full min-w-0 rounded-xl border border-slate-300 px-3 py-2 text-base sm:min-h-9 sm:w-auto sm:min-w-[14rem] sm:text-sm">
                <option value="">{teachers.length ? t("courses.settings.chooseTeacher") : t("courses.settings.noOtherTeachers")}</option>
                {teachers.map((e) => <option key={e.user.id} value={e.user.id}>{e.user.display_name || e.user.email}</option>)}
              </select>
              <button type="button" disabled={!newOwner} onClick={() => { setError(null); setConfirm("transfer"); }}
                className={dangerOutlineBtn}>
                {t("courses.settings.transfer")}
              </button>
            </div>
            <p className="mt-1 text-xs text-slate-500">{t("courses.settings.transferHint")}</p>
          </div>
          <div>
            <button type="button" onClick={() => { setError(null); setConfirm("delete"); }} className={dangerBtn}>
              {t("courses.settings.delete")}
            </button>
            <p className="mt-1 text-xs text-slate-500">{t("courses.settings.deleteHint")}</p>
          </div>
        </section>
      )}

      {cfg && (
        <ConfirmDialog open tone={cfg.danger ? "danger" : "primary"} busy={busy === cfg.section} title={cfg.title}
          object={confirm ? objectFor(confirm) : undefined} effect={cfg.body}
          error={errFor(cfg.section) ? <ErrorMessage error={errFor(cfg.section)} /> : undefined}
          confirmLabel={cfg.label} onConfirm={doConfirm} onCancel={() => { setConfirm(null); setError(null); }} />
      )}
    </div>
  );
}

export default function SettingsPage() {
  const { course } = useCourse();
  const { t } = useTranslation();
  if (!isStaffCourse(course) || course.my_enrollment.role !== "teacher") {
    return <p className="text-sm text-slate-600">{t("lms.errors.forbidden")}</p>;
  }
  // key resets the form state when the course id changes
  return <Settings key={course.id} course={course} />;
}
