"use client";

// FB8-5 S3 (STAFF_UX_AUDIT 5): Access / Pro: the course status with its lifecycle (Publish or Reopen as the one
// button; Unpublish and Conclude in the "⋯" menu, confirmed) and what Pro means for this course. Pro is owned by the
// server and the platform admin (Admin → Pro), so this section only explains and links; it changes nothing there.
import React, { useState } from "react";
import { useTranslation } from "@/lib/i18n/context";
import { concludeCourse, publishCourse, reopenCourse, unpublishCourse } from "@/lib/lms/courses";
import { pickLocalized } from "@/lib/lms/localized";
import { useAuth } from "@/lib/auth-context";
import type { CourseStaffOut } from "@/lib/lms/types";
import { ErrorMessage } from "@/components/lms/ErrorMessage";
import { StatusBadge } from "@/components/lms/course/CourseCard";
import { Button, Card, ConfirmDialog, LinkButton, OverflowMenu } from "@/components/ui";
import { SavedNote, SectionLayout, useSave } from "./shared";

type Step = "publish" | "unpublish" | "conclude" | "reopen";

export function AccessSection({ course, onSaved }: { course: CourseStaffOut; onSaved: (c: CourseStaffOut) => void }) {
  const { lang, t } = useTranslation();
  const { userProfile } = useAuth();
  const s = useSave();
  const [confirm, setConfirm] = useState<null | "unpublish" | "conclude">(null);
  const st = course.status;
  const courseName = pickLocalized(course.title, lang, course.default_language) || t("courses.list.untitled");

  const step = (name: Step) => {
    const fn = { publish: publishCourse, unpublish: unpublishCourse, conclude: concludeCourse, reopen: reopenCourse }[name];
    return s.run(async () => onSaved(await fn(course.id)));
  };
  const menu = st === "published"
    ? [{ id: "status", items: [
      { id: "unpublish", label: t("courses.settings.unpublish") },
      { id: "conclude", label: t("courses.settings.conclude") },
    ] }]
    : [];

  return (
    <SectionLayout>
      <Card title={t("courses.settings.lifecycle")} actions={<StatusBadge status={st} />}>
        <div className="space-y-4">
          <p className="text-sm text-slate-600">{t(`courses.settings.lifecycleHint.${st}`)}</p>
          <div className="flex flex-wrap items-center gap-2">
            {st === "draft" && <Button size="sm" loading={s.busy} onClick={() => void step("publish")}>{t("courses.settings.publish")}</Button>}
            {st === "concluded" && <Button size="sm" loading={s.busy} onClick={() => void step("reopen")}>{t("courses.settings.reopen")}</Button>}
            {menu.length > 0 && (
              <OverflowMenu trigger="button" text={t("courses.settings.statusMenu")} label={t("courses.settings.statusMenu")} disabled={s.busy}
                groups={menu} onSelect={(id) => { s.setError(null); s.setSaved(false); setConfirm(id as "unpublish" | "conclude"); }} />
            )}
            <SavedNote show={s.saved} />
          </div>
          {!confirm && <ErrorMessage error={s.error} />}
        </div>
      </Card>

      <Card title={t("courses.settings.access.title")}>
        {course.is_platform_course ? (
          <div className="space-y-3 text-sm leading-6 text-slate-700">
            <p>{t("courses.settings.access.platformPro")}</p>
            <p>{t("courses.settings.access.practiceFree")}</p>
            {userProfile?.is_platform_admin ? (
              <div className="flex flex-wrap gap-2 pt-1">
                <LinkButton size="sm" variant="secondary" href={`/${lang}/admin/access/exams`}>{t("courses.settings.access.paidExamsLink")}</LinkButton>
                <LinkButton size="sm" variant="secondary" href={`/${lang}/admin/access`}>{t("courses.settings.access.proLink")}</LinkButton>
              </div>
            ) : (
              <p className="text-slate-600">{t("courses.settings.access.adminOnly")}</p>
            )}
            {/* FB8 item 3 (later slice): the "exam link" select of a platform course goes here. */}
          </div>
        ) : (
          <p className="text-sm leading-6 text-slate-600">{t("courses.settings.access.notPlatform")}</p>
        )}
      </Card>

      {confirm && (
        <ConfirmDialog open tone="primary" busy={s.busy} object={courseName}
          title={t(confirm === "unpublish" ? "courses.settings.unpublishTitle" : "courses.settings.concludeTitle")}
          effect={t(confirm === "unpublish" ? "courses.settings.unpublishBody" : "courses.settings.concludeBody")}
          error={s.error ? <ErrorMessage error={s.error} /> : undefined}
          confirmLabel={t(confirm === "unpublish" ? "courses.settings.unpublish" : "courses.settings.conclude")}
          onConfirm={() => { void step(confirm).then((ok) => { if (ok) setConfirm(null); }); }}
          onCancel={() => { setConfirm(null); s.setError(null); }} />
      )}
    </SectionLayout>
  );
}
