"use client";

// FB8-5 S3 (STAFF_UX_AUDIT 5): General: main language + translations, title, description (one Save), then the course
// home and, on exam-prep courses, the exam date (each its own Save, as before). The card beside it follows the typing.
// Fix round 2026-11-12 (1d): the course status card (publish, unpublish, conclude) comes first.
import React, { useState } from "react";
import { useTranslation } from "@/lib/i18n/context";
import { updateCourse } from "@/lib/lms/courses";
import { cleanLocalized } from "@/lib/lms/localized";
import { templateUi } from "@/lib/lms/templates";
import type { CourseStaffOut, Lang, LocalizedText } from "@/lib/lms/types";
import { ErrorMessage } from "@/components/lms/ErrorMessage";
import { LocalizedTextInput } from "@/components/lms/LocalizedTextInput";
import { CourseHomeSection } from "@/components/lms/modules/CourseHomeSection"; // Phase 8a S4a
import { ExamDateSection } from "@/components/lms/examPrep/ExamDateSection"; // Exam prep S2
import { LanguageFields, moveSingleLanguageText } from "@/components/lms/course/form/LanguageFields";
import { CoursePreview } from "@/components/lms/course/form/CoursePreview";
import { Button, Card } from "@/components/ui";
import { CourseStatusCard } from "./CourseStatusCard";
import { SavedNote, SectionLayout, cardDataOf, useSave } from "./shared";

export function GeneralSection({ course, onSaved }: { course: CourseStaffOut; onSaved: (c: CourseStaffOut) => void }) {
  const { t } = useTranslation();
  const [languages, setLanguages] = useState<Lang[]>(course.languages);
  const [defaultLanguage, setDefaultLanguage] = useState<Lang>(course.default_language);
  const [title, setTitle] = useState<LocalizedText>(course.title);
  const [description, setDescription] = useState<LocalizedText>(course.description ?? {});
  const s = useSave();

  const changeLanguages = (ls: Lang[], d: Lang, from: Lang) => {
    setTitle((v) => moveSingleLanguageText(v, languages, from, d));
    setDescription((v) => moveSingleLanguageText(v, languages, from, d));
    setLanguages(ls);
    setDefaultLanguage(d);
  };

  const save = (ev: React.FormEvent) => {
    ev.preventDefault();
    const cleanDescription = cleanLocalized(description, languages);
    void s.run(async () => {
      onSaved(await updateCourse(course.id, {
        title: cleanLocalized(title, languages),
        // an empty description clears it with null: the server refuses `{}` (at least one non-empty translation)
        description: (Object.keys(cleanDescription).length ? cleanDescription : null) as LocalizedText,
        languages,
        default_language: defaultLanguage,
      }));
    });
  };

  const preview = (
    <CoursePreview course={cardDataOf(course, {
      title: cleanLocalized(title, languages), description: cleanLocalized(description, languages), languages, default_language: defaultLanguage,
    })} />
  );

  return (
    <SectionLayout preview={preview}>
      <CourseStatusCard course={course} onSaved={onSaved} />
      <Card title={t("courses.settings.general")}>
        <form onSubmit={save} className="space-y-5" noValidate data-testid="settings-general">
          <LanguageFields idPrefix="s" languages={languages} defaultLanguage={defaultLanguage} disabled={s.busy} onChange={changeLanguages} />
          <LocalizedTextInput label={t("courses.create.courseTitle")} languages={languages} defaultLanguage={defaultLanguage}
            value={title} onChange={setTitle} maxLength={200} required disabled={s.busy} fallbackHint />
          <LocalizedTextInput label={t("courses.create.description")} languages={languages} defaultLanguage={defaultLanguage}
            value={description} onChange={setDescription} multiline maxLength={5000} disabled={s.busy} />
          <ErrorMessage error={s.error} />
          <div className="flex items-center gap-3">
            <Button type="submit" size="sm" loading={s.busy}>{t("lms.common.save")}</Button>
            <SavedNote show={s.saved} />
          </div>
        </form>
      </Card>
      {/* --- Phase 8a S4a: course home (locked on ORT with the template note) --- */}
      <CourseHomeSection course={course} />
      {templateUi(course).studentLayout === "exam_prep" && <ExamDateSection course={course} />}
    </SectionLayout>
  );
}
