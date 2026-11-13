"use client";

// FB8-5 S3 (STAFF_UX_AUDIT 5): Cover: the upload/crop/remove section (`CourseCoverSection`) with the course card beside
// it instead of the section's own previews; the card shows the chosen frame before it is saved.
import React, { useCallback, useState } from "react";
import { useTranslation } from "@/lib/i18n/context";
import { pickLocalized } from "@/lib/lms/localized";
import type { CourseStaffOut } from "@/lib/lms/types";
import { CourseCoverSection } from "@/components/lms/course/CourseCoverSection"; // F7b
import { CoursePreview } from "@/components/lms/course/form/CoursePreview";
import type { CoverPreview } from "@/components/lms/course/form/CoverPicker";
import { SectionLayout, cardDataOf } from "./shared";

export function CoverSettingsSection({ course, onSaved }: { course: CourseStaffOut; onSaved: (c: CourseStaffOut) => void }) {
  const { lang, t } = useTranslation();
  const [pending, setPending] = useState<CoverPreview | null>(null);
  const onPreview = useCallback((p: CoverPreview | null) => setPending(p), []);
  const courseName = pickLocalized(course.title, lang, course.default_language) || t("courses.list.untitled");
  return (
    <SectionLayout preview={<CoursePreview course={cardDataOf(course)} cover={pending} />}>
      <CourseCoverSection courseId={course.id} title={courseName} examFamily={course.exam_family} subject={course.subject} previews={false}
        onPreview={onPreview} coverUrl={course.cover_url} onChanged={(url) => onSaved({ ...course, cover_url: url })} />
    </SectionLayout>
  );
}
