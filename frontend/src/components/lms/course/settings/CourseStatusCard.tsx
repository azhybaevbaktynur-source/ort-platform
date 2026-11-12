"use client";

// FB8-5 S3 (STAFF_UX_AUDIT 5): the course status with its lifecycle (Publish or Reopen as the one button; Unpublish and
// Conclude in the "⋯" menu, confirmed). Fix round 2026-11-12 (1d): moved from Access / Pro to the top of General, so
// every teacher of the course has it (Access / Pro is shown to platform admins on platform courses only).
import React, { useState } from "react";
import { useTranslation } from "@/lib/i18n/context";
import { concludeCourse, publishCourse, reopenCourse, unpublishCourse } from "@/lib/lms/courses";
import { pickLocalized } from "@/lib/lms/localized";
import type { CourseStaffOut } from "@/lib/lms/types";
import { ErrorMessage } from "@/components/lms/ErrorMessage";
import { StatusBadge } from "@/components/lms/course/CourseCard";
import { Button, Card, ConfirmDialog, OverflowMenu } from "@/components/ui";
import { SavedNote, useSave } from "./shared";

type Step = "publish" | "unpublish" | "conclude" | "reopen";

export function CourseStatusCard({ course, onSaved }: { course: CourseStaffOut; onSaved: (c: CourseStaffOut) => void }) {
  const { lang, t } = useTranslation();
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
    <>
      <Card title={t("courses.settings.lifecycle")} actions={<StatusBadge status={st} />}>
        <div className="space-y-4" data-testid="settings-status">
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

      {confirm && (
        <ConfirmDialog open tone="primary" busy={s.busy} object={courseName}
          title={t(confirm === "unpublish" ? "courses.settings.unpublishTitle" : "courses.settings.concludeTitle")}
          effect={t(confirm === "unpublish" ? "courses.settings.unpublishBody" : "courses.settings.concludeBody")}
          error={s.error ? <ErrorMessage error={s.error} /> : undefined}
          confirmLabel={t(confirm === "unpublish" ? "courses.settings.unpublish" : "courses.settings.conclude")}
          onConfirm={() => { void step(confirm).then((ok) => { if (ok) setConfirm(null); }); }}
          onCancel={() => { setConfirm(null); s.setError(null); }} />
      )}
    </>
  );
}
