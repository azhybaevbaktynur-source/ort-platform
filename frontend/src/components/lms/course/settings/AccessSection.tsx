"use client";

// FB8-5 S3 (STAFF_UX_AUDIT 5): Access / Pro: the course status with its lifecycle (Publish or Reopen as the one
// button; Unpublish and Conclude in the "⋯" menu, confirmed) and what Pro means for this course. Pro is owned by the
// server and the platform admin (Admin → Pro), so this section only explains and links; it changes nothing there.
import React, { useEffect, useState } from "react";
import { useTranslation } from "@/lib/i18n/context";
import { listCatalog } from "@/lib/lms/catalog";
import { concludeCourse, getCourse, publishCourse, reopenCourse, unpublishCourse, updateCourse } from "@/lib/lms/courses";
import { pickLocalized } from "@/lib/lms/localized";
import { templateUi } from "@/lib/lms/templates";
import { useAuth } from "@/lib/auth-context";
import type { CourseStaffOut, LocalizedText } from "@/lib/lms/types";
import { ErrorMessage } from "@/components/lms/ErrorMessage";
import { StatusBadge } from "@/components/lms/course/CourseCard";
import { Button, Card, ConfirmDialog, LinkButton, OverflowMenu, Select } from "@/components/ui";
import { SavedNote, SectionLayout, useSave } from "./shared";

// --- TEACHER_TO_STUDENT_MAP §2.6 begin --- (the exam link of a platform lesson course; the server checks every rule)
interface ExamChoice { id: string; title: LocalizedText; default_language: CourseStaffOut["default_language"] }
const CATALOG_LIMIT = 100;

/** The platform's exam-prep courses: platform courses of the catalog whose template has the exam-prep layout (the
 * course read carries the template), plus the linked exam when the catalog does not list it. */
async function loadExamChoices(course: CourseStaffOut): Promise<ExamChoice[]> {
  const page = await listCatalog(null, CATALOG_LIMIT);
  const ids = page.items.filter((c) => c.is_platform_course && c.id !== course.id).map((c) => c.id);
  if (course.exam_course_id && !ids.includes(course.exam_course_id)) ids.push(course.exam_course_id);
  const read = await Promise.allSettled(ids.map((id) => getCourse(id)));
  const out: ExamChoice[] = [];
  for (const r of read) {
    if (r.status === "fulfilled" && templateUi(r.value).studentLayout === "exam_prep") {
      out.push({ id: r.value.id, title: r.value.title, default_language: r.value.default_language });
    }
  }
  return out;
}

function ExamLinkField({ course, onSaved }: { course: CourseStaffOut; onSaved: (c: CourseStaffOut) => void }) {
  const { lang, t } = useTranslation();
  const s = useSave();
  const linked = course.exam_course_id ?? "";
  const [value, setValue] = useState(linked);
  const [choices, setChoices] = useState<ExamChoice[] | null>(null);
  const [loadError, setLoadError] = useState(false);
  useEffect(() => { setValue(course.exam_course_id ?? ""); }, [course.exam_course_id]);
  useEffect(() => {
    let live = true;
    loadExamChoices(course).then((c) => { if (live) setChoices(c); }).catch(() => { if (live) { setChoices([]); setLoadError(true); } });
    return () => { live = false; };
    // the choices are read once per course
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [course.id]);
  const save = () => s.run(async () => onSaved(await updateCourse(course.id, { exam_course_id: value || null })));
  const options = [
    { value: "", label: t("courses.settings.examLink.none") },
    ...(choices ?? []).map((c) => ({ value: c.id, label: pickLocalized(c.title, lang, c.default_language) || t("courses.list.untitled") })),
  ];
  return (
    <div className="space-y-2 border-t border-slate-100 pt-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
        <Select id="s-exam-link" containerClassName="min-w-0 sm:w-80" label={t("courses.settings.examLink.label")}
          value={value} disabled={s.busy || choices === null} onChange={(e) => { setValue(e.target.value); s.setSaved(false); }}
          aria-describedby="s-exam-link-help" options={options} />
        <Button variant="secondary" loading={s.busy} disabled={value === linked || choices === null} onClick={() => void save()}
          className="self-start sm:self-auto">
          {t("common.save")}
        </Button>
      </div>
      <p id="s-exam-link-help" className="text-sm leading-5 text-slate-600">{t("courses.settings.examLink.help")}</p>
      {loadError && <p className="text-sm text-danger-700">{t("courses.settings.examLink.loadFailed")}</p>}
      <SavedNote show={s.saved} />
      <ErrorMessage error={s.error} />
    </div>
  );
}
// --- TEACHER_TO_STUDENT_MAP §2.6 end ---

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
            {/* TEACHER_TO_STUDENT_MAP §2.6: the exam a platform lesson course belongs to (platform admins) */}
            {userProfile?.is_platform_admin && !course.template && !course.sandbox_for_template_id && (
              <ExamLinkField course={course} onSaved={onSaved} />
            )}
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
