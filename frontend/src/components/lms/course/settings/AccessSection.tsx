"use client";

// FB8-5 S3 (STAFF_UX_AUDIT 5): Access / Pro: what Pro means for this course, and the exam link. Pro is owned by the
// server and the platform admin (Admin → Pro), so this section only explains and links; it changes nothing there.
// Fix round 2026-11-12 (1d): the settings page shows this section to platform admins on platform courses only (the
// server refuses everyone else anyway); the course status card moved to General.
import React, { useEffect, useState } from "react";
import { useTranslation } from "@/lib/i18n/context";
import { getAdminCourse, listAdminCourses } from "@/lib/lms/admin";
import { updateCourse } from "@/lib/lms/courses";
import { pickLocalized } from "@/lib/lms/localized";
import type { CourseStaffOut, LocalizedText } from "@/lib/lms/types";
import { ErrorMessage } from "@/components/lms/ErrorMessage";
import { Button, Card, LinkButton, Select } from "@/components/ui";
import { SavedNote, SectionLayout, useSave } from "./shared";

// --- TEACHER_TO_STUDENT_MAP §2.6 begin --- (the exam link of a platform lesson course; the server checks every rule)
interface ExamChoice { id: string; title: LocalizedText }
const CHOICES_LIMIT = 100;

/** The platform's exam-prep courses in one request (`GET /platform/courses?exam_prep=true`, platform admins only, the
 * server's rule for a link target), plus the linked exam when the list no longer has it (deleted since). */
async function loadExamChoices(course: CourseStaffOut): Promise<ExamChoice[]> {
  const page = await listAdminCourses({ exam_prep: true, limit: CHOICES_LIMIT });
  const out: ExamChoice[] = page.items.filter((c) => c.id !== course.id).map((c) => ({ id: c.id, title: c.title }));
  const linked = course.exam_course_id;
  if (linked && !out.some((c) => c.id === linked)) {
    const c = await getAdminCourse(linked).catch(() => null);
    out.push({ id: linked, title: c?.title ?? {} });
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
    ...(choices ?? []).map((c) => ({ value: c.id, label: pickLocalized(c.title, lang) || t("courses.list.untitled") })),
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

export function AccessSection({ course, onSaved }: { course: CourseStaffOut; onSaved: (c: CourseStaffOut) => void }) {
  const { lang, t } = useTranslation();
  return (
    <SectionLayout>
      <Card title={t("courses.settings.access.title")}>
        <div className="space-y-3 text-sm leading-6 text-slate-700">
          <p>{t("courses.settings.access.platformPro")}</p>
          <p>{t("courses.settings.access.practiceFree")}</p>
          <div className="flex flex-wrap gap-2 pt-1">
            <LinkButton size="sm" variant="secondary" href={`/${lang}/admin/access/exams`}>{t("courses.settings.access.paidExamsLink")}</LinkButton>
            <LinkButton size="sm" variant="secondary" href={`/${lang}/admin/access`}>{t("courses.settings.access.proLink")}</LinkButton>
          </div>
          {/* TEACHER_TO_STUDENT_MAP §2.6: the exam a platform lesson course belongs to */}
          {!course.template && !course.sandbox_for_template_id && <ExamLinkField course={course} onSaved={onSaved} />}
        </div>
      </Card>
    </SectionLayout>
  );
}
