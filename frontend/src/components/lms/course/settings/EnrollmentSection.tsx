"use client";

// FB8-5 S3 (STAFF_UX_AUDIT 5): Enrollment: the join code (copy; "new code" in the "⋯" menu, confirmed), mode, limit,
// link-access switch, the enrollment form link and the active student count. Save semantics as before (Phase 9 S4): the
// visibility is sent with the mode only when it changed. Step 3b S2: «Страница курса открыта по ссылке» (link access) and
// the «Каталог платформы» card below (the catalog list, decided by the platform admin).
import React, { useEffect, useState } from "react";
import Link from "next/link";
import { RefreshCw } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { formatJoinCode, regenerateJoinCode, updateCourse } from "@/lib/lms/courses";
import { isFormMode } from "@/lib/lms/catalog";
import { listFormVersions } from "@/lib/lms/enrollmentForms";
import { templateUi } from "@/lib/lms/templates";
import type { CourseStaffOut, EnrollmentMode, Visibility } from "@/lib/lms/types";
import { ErrorMessage } from "@/components/lms/ErrorMessage";
import { JoinCodeDisplay } from "@/components/lms/JoinCodeDisplay";
import { useApplicationErrorText } from "@/components/lms/catalog/useApplicationErrorText";
import { Button, Card, ConfirmDialog, ErrorState, Input, OverflowMenu, Select, Switch, buttonClasses } from "@/components/ui";
import { SavedNote, SectionLayout, useSave } from "./shared";
import { CatalogListingCard } from "./CatalogListingCard";

const SETTINGS_MODES: EnrollmentMode[] = ["invite_code", "open", "form_review", "form_auto", "closed"];

export function EnrollmentSection({ course, onSaved }: { course: CourseStaffOut; onSaved: (c: CourseStaffOut) => void }) {
  const { lang, t } = useTranslation();
  const [mode, setMode] = useState<EnrollmentMode>(course.enrollment_mode); // Phase 9 S4: five modes
  const [visibility, setVisibility] = useState<Visibility>(course.visibility); // Phase 9 S4: catalog switch
  const [limit, setLimit] = useState(course.enrollment_limit ? String(course.enrollment_limit) : "");
  const [confirmCode, setConfirmCode] = useState(false);
  const s = useSave();
  const code = useSave();
  const ortLocked = templateUi(course).locked;
  const formErrorText = useApplicationErrorText();
  /** `undefined` while loading, `null` when the course has no active form. */
  const [activeFormVersion, setActiveFormVersion] = useState<number | null | undefined>(undefined);
  useEffect(() => {
    if (ortLocked) return;
    listFormVersions(course.id)
      .then((vs) => setActiveFormVersion(vs.find((v) => v.status === "active")?.version ?? null))
      .catch(() => setActiveFormVersion(null));
  }, [course.id, ortLocked]);

  const save = (ev: React.FormEvent) => {
    ev.preventDefault();
    void s.run(async () => {
      onSaved(await updateCourse(course.id, {
        enrollment_mode: mode, enrollment_limit: limit.trim() ? parseInt(limit, 10) : null,
        ...(visibility !== course.visibility ? { visibility } : {}), // Phase 9 S4 (sent with the mode: form modes need the catalog)
      }));
    });
  };
  const regenerate = async () => {
    if (await code.run(async () => { const r = await regenerateJoinCode(course.id); onSaved({ ...course, join_code: r.join_code }); })) {
      setConfirmCode(false);
    }
  };
  const st = course.status;

  return (
    <SectionLayout>
      <Card title={t("courses.settings.enrollment")}>
        <div className="space-y-5">
          <div>
            <p className="mb-2 text-sm font-medium text-slate-700">{t("courses.settings.joinCode")}</p>
            <div className="flex flex-wrap items-center gap-2">
              <JoinCodeDisplay code={course.join_code} />
              <OverflowMenu label={t("courses.settings.joinCodeMenu")} disabled={code.busy}
                groups={[{ id: "code", items: [{ id: "regenerate", label: t("courses.settings.regenerate"), icon: <RefreshCw aria-hidden="true" className="h-4 w-4" /> }] }]}
                onSelect={() => { code.setError(null); code.setSaved(false); setConfirmCode(true); }} />
            </div>
            {/* Phase 9 UX: the reason the code does not work: a draft course, or the saved enrollment mode */}
            {st !== "published" ? (
              <p className="mt-1 text-xs text-amber-700">{t("courses.settings.joinCodeInactiveUnpublished")}</p>
            ) : course.enrollment_mode !== "invite_code" ? (
              <p className="mt-1 text-xs text-amber-700">
                {t(isFormMode(course.enrollment_mode) ? "courses.settings.joinCodeInactiveMode"
                  : course.enrollment_mode === "open" ? "courses.settings.joinCodeInactiveOpen" : "courses.settings.joinCodeInactiveClosed",
                { code: t("enrollmentForm.modes.invite_code") })}
              </p>
            ) : null}
            {code.saved && <p role="status" className="mt-1 text-sm text-success-700">{t("courses.settings.codeRegenerated")}</p>}
          </div>
          <form onSubmit={save} className="space-y-4" noValidate>
            <div className="grid gap-4 sm:grid-cols-2">
              {/* Phase 9 S4: five modes; form modes are fixed off on ORT courses (422 template_locked) */}
              <Select id="s-mode" label={t("courses.create.modeLabel")} value={mode} disabled={s.busy}
                onChange={(e) => setMode(e.target.value as EnrollmentMode)}
                hint={t(`enrollmentForm.modeHints.${mode}`)}
                options={SETTINGS_MODES.map((m) => ({
                  value: m,
                  label: `${t(`enrollmentForm.modes.${m}`)}${ortLocked && isFormMode(m) ? ` (${t("templates.lockedNote")})` : ""}`,
                  disabled: ortLocked && isFormMode(m),
                }))} />
              <Input id="s-limit" type="number" min={1} max={10000} label={t("courses.create.limit")} value={limit} disabled={s.busy}
                onChange={(e) => setLimit(e.target.value)} placeholder={t("courses.create.limitPlaceholder")}
                hint={t("courses.settings.activeStudents", { count: course.active_student_count })} />
            </div>
            {/* --- Phase 9 S4: link access (step 3b: no longer "in the catalog"), the enrollment form, the ORT lock note --- */}
            <Switch id="s-visibility" label={t("catalog.listing.linkAccess")} checked={visibility === "catalog"}
              disabled={s.busy}
              hint={isFormMode(mode) ? t("catalog.listing.linkAccessNeeded") : t("catalog.listing.linkAccessHint")}
              onChange={(on) => setVisibility(on ? "catalog" : "private")} />
            {/* step 3b §2.3: a course nobody can open by link leaves the catalog list (the server sets `off` on save) */}
            {visibility === "private" && course.visibility === "catalog" && (course.listing?.state === "listed" || course.listing?.state === "pending") && (
              <p role="status" className="-mt-2 text-sm leading-6 text-amber-700">{t("catalog.listing.privateWarning")}</p>
            )}
            {ortLocked ? (
              <p className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm leading-6 text-slate-700">{t("enrollmentForm.settings.ortNote")}</p>
            ) : (
              <div className="flex flex-col gap-2 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
                <div className="min-w-0">
                  <p className="text-sm font-medium text-slate-900">{t("enrollmentForm.title")}</p>
                  <p className="text-sm text-slate-600">
                    {activeFormVersion === undefined ? t("lms.common.loading")
                      : activeFormVersion === null ? t("enrollmentForm.settings.noActive")
                        : t("enrollmentForm.settings.active", { n: activeFormVersion })}
                  </p>
                </div>
                <Link href={`/${lang}/courses/${course.id}/settings/enrollment-form`} className={buttonClasses({ variant: "secondary", size: "sm", className: "shrink-0 whitespace-nowrap" })}>
                  {t("enrollmentForm.settings.open")}
                </Link>
              </div>
            )}
            {/* --- Phase 9 S4 end --- */}
            {s.error ? <ErrorState variant="inline" message={formErrorText(s.error)} /> : null}
            <div className="flex items-center gap-3">
              <Button type="submit" size="sm" loading={s.busy}>{t("lms.common.save")}</Button>
              <SavedNote show={s.saved} />
            </div>
          </form>
        </div>
      </Card>
      <CatalogListingCard course={course} onSaved={onSaved} />
      {confirmCode && (
        <ConfirmDialog open tone="primary" busy={code.busy} title={t("courses.settings.regenerateTitle")}
          object={formatJoinCode(course.join_code)} effect={t("courses.settings.regenerateBody")}
          error={code.error ? <ErrorMessage error={code.error} /> : undefined}
          confirmLabel={t("courses.settings.regenerate")} onConfirm={() => void regenerate()}
          onCancel={() => { setConfirmCode(false); code.setError(null); }} />
      )}
    </SectionLayout>
  );
}
