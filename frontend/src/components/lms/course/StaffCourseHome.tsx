"use client";

import React, { useState } from "react";
import { useRouter } from "next/navigation";
import { ClipboardList, LayoutList, Library } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { leaveCourse } from "@/lib/lms/courses";
import { pickLocalized } from "@/lib/lms/localized";
import type { CourseStaffOut } from "@/lib/lms/types";
import { ErrorMessage } from "@/components/lms/ErrorMessage";
import { JoinCodeDisplay } from "@/components/lms/JoinCodeDisplay";
import { Button, Card, ConfirmDialog, DescriptionList, LinkButton, PageHeader } from "@/components/ui";

/**
 * Staff course home (Phase 6b S5c). Replaces the roadmap sentence with a real next step (create an assessment,
 * add questions) until modules arrive in Phase 8, and shows the join code to teachers. Same API calls as before.
 */
export function StaffCourseHome({ course }: { course: CourseStaffOut }) {
  const { lang, t } = useTranslation();
  const router = useRouter();
  const [leaving, setLeaving] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const base = `/${lang}/courses/${course.id}`;
  const title = pickLocalized(course.title, lang, course.default_language) || t("courses.list.untitled");
  const description = pickLocalized(course.description, lang, course.default_language);
  const isTeacher = course.my_enrollment.role === "teacher";
  const canEdit = course.status !== "concluded";

  const leave = async () => {
    setBusy(true);
    setError(null);
    try {
      await leaveCourse(course.id);
      router.push(`/${lang}/courses`);
    } catch (e) {
      setError(e);
      setBusy(false);
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader title={t("teaching.homeTitle")} className="mb-2" />
      {course.status === "draft" && (
        <p role="status" className="rounded-xl border border-warning-200 bg-warning-50 px-4 py-3 text-sm text-warning-900">{t("courses.home.draftNotice")}</p>
      )}
      {course.status === "concluded" && (
        <p role="status" className="rounded-xl border border-slate-200 bg-slate-100 px-4 py-3 text-sm text-slate-700">{t("courses.home.concludedNotice")}</p>
      )}

      {canEdit && (
        <Card title={t("teaching.nextStepTitle")} description={t("teaching.nextStepBody")}>
          <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap">
            <LinkButton href={`${base}/assessments?new=1`} leftIcon={<ClipboardList className="h-4 w-4" aria-hidden="true" />}>
              {t("teaching.createAssessment")}
            </LinkButton>
            <LinkButton variant="secondary" href={`${base}/bank`} leftIcon={<Library className="h-4 w-4" aria-hidden="true" />}>
              {t("teaching.addQuestions")}
            </LinkButton>
          </div>
        </Card>
      )}

      {/* --- Phase 8a S4a: link to the module outline and what students see first (PHASE_8A_DESIGN 8.1) --- */}
      <Card title={t("modules.staffHome.title")}
        description={t(`modules.staffHome.body.${course.home_kind ?? "assignments"}`)}>
        <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap">
          <LinkButton variant="secondary" href={`${base}/modules`} leftIcon={<LayoutList className="h-4 w-4" aria-hidden="true" />}>
            {t("modules.staffHome.open")}
          </LinkButton>
          {isTeacher && <LinkButton variant="link" href={`${base}/settings#course-home`}>{t("modules.staffHome.changeHome")}</LinkButton>}
        </div>
      </Card>
      {/* --- Phase 8a S4a end --- */}

      <div className="grid gap-6 lg:grid-cols-2">
        <Card title={t("courses.home.about")}>
          <p className="whitespace-pre-line break-words text-sm leading-6 text-slate-800">{description || t("courses.home.noDescription")}</p>
          <DescriptionList className="mt-5" twoColumns items={[
            { term: t("courses.home.owner"), description: course.owner_display_name || "—" },
            { term: t("courses.home.myRole"), description: t(`courses.roles.${course.my_enrollment.role}`) },
            { term: t("courses.home.languages"), description: course.languages.map((l) => t(`courses.languages.${l}`)).join(", ") },
            { term: t("courses.home.activeStudents"), description: `${course.active_student_count}${course.enrollment_limit ? ` / ${course.enrollment_limit}` : ""}` },
          ]} />
        </Card>
        {isTeacher && (
          <Card title={t("courses.settings.joinCode")} description={t("courses.settings.joinCodeHint")}>
            <JoinCodeDisplay code={course.join_code} />
            {(course.status !== "published" || course.enrollment_mode !== "invite_code") && (
              <p className="mt-2 text-sm text-warning-800">{t("courses.settings.joinCodeInactive")}</p>
            )}
            <LinkButton variant="link" className="mt-3" href={`${base}/settings`}>{t("teaching.manageEnrollment")}</LinkButton>
          </Card>
        )}
      </div>

      {!course.is_owner && (
        <div>
          <Button variant="link" className="text-danger-700 hover:text-danger-800" onClick={() => setLeaving(true)}>{t("courses.home.leave")}</Button>
        </div>
      )}
      <ConfirmDialog open={leaving} tone="danger" busy={busy} title={t("courses.home.leaveTitle")} object={title}
        effect={t("courses.home.leaveBody")} error={error ? <ErrorMessage error={error} /> : undefined}
        confirmLabel={t("courses.home.leave")} onConfirm={() => void leave()} onCancel={() => setLeaving(false)} />
    </div>
  );
}
