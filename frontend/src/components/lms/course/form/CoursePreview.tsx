"use client";

/*
 * FB8-5 S3 (STAFF_UX_AUDIT 4, 5): the live preview beside the create form and the course settings: the one course card
 * (`CourseCard`, 360 px, 150 px cover) fed with what is being typed. A cover that is not uploaded yet is the chosen
 * file's object URL, framed at the chosen focus (the card's image takes `object-position` from a CSS variable).
 * Sticky from `lg`; on phones it sits above the form.
 */
import React from "react";
import { useTranslation } from "@/lib/i18n/context";
import { CourseCard, type CourseCardData } from "@/components/lms/course/CourseCard";
import { cn } from "@/components/ui";
import type { CoverPreview } from "./CoverPicker";

export function CoursePreview({ course, cover, className }: {
  course: CourseCardData;
  /** a chosen, not yet saved cover (overrides `course.cover_url`) */
  cover?: CoverPreview | null;
  className?: string;
}) {
  const { t } = useTranslation();
  const data: CourseCardData = cover ? { ...course, cover_url: cover.url } : course;
  const pos = cover ? `${Math.round(cover.fx * 100)}% ${Math.round(cover.fy * 100)}%` : "50% 50%";
  return (
    <aside aria-label={t("courses.create.previewLabel")} data-testid="course-preview" data-cover-url={data.cover_url ?? ""}
      className={cn("lg:sticky lg:top-6", className)}>
      <p className="mb-2 text-sm font-medium text-slate-700">{t("courses.create.previewTitle")}</p>
      <ul className="max-w-[360px] [&_img]:[object-position:var(--cover-pos)]" style={{ "--cover-pos": pos } as React.CSSProperties}>
        <CourseCard course={data} href={null} headingLevel={2} />
      </ul>
      <p className="mt-2 max-w-[360px] text-xs leading-5 text-slate-500">{t("courses.create.previewHint")}</p>
    </aside>
  );
}
