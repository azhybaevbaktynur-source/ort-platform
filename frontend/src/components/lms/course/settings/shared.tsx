"use client";

// FB8-5 S3 (STAFF_UX_AUDIT 5): what the course settings sections share: the save state of one section (busy, error,
// "Saved"), the 720 px column with an optional sticky card preview, and the card data of a course.
import React, { useState } from "react";
import { useTranslation } from "@/lib/i18n/context";
import type { CourseCardData } from "@/components/lms/course/CourseCard";
import type { CourseStaffOut } from "@/lib/lms/types";
import { STAFF_WIDTH, cn } from "@/components/ui";

export type SettingsSection = "general" | "cover" | "enrollment" | "access" | "grading" | "danger";
export const SETTINGS_SECTIONS: SettingsSection[] = ["general", "cover", "enrollment", "access", "grading", "danger"];

/** One section's save: `run` clears the old state, shows "Saved" on success and keeps the error otherwise. */
export function useSave() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [saved, setSaved] = useState(false);
  const run = async (fn: () => Promise<void>): Promise<boolean> => {
    setBusy(true);
    setError(null);
    setSaved(false);
    try {
      await fn();
      setSaved(true);
      return true;
    } catch (err) {
      setError(err);
      return false;
    } finally {
      setBusy(false);
    }
  };
  return { busy, error, saved, run, setError, setSaved };
}

export function SavedNote({ show }: { show: boolean }) {
  const { t } = useTranslation();
  return show ? <p role="status" className="text-sm text-success-700">{t("courses.settings.saved")}</p> : null;
}

/** The section column: 720 px alone, or 720 px + the 360 px preview (beside it from `lg`, above it on phones). */
export function SectionLayout({ preview, children }: { preview?: React.ReactNode; children: React.ReactNode }) {
  if (!preview) return <div className={cn("w-full space-y-6", STAFF_WIDTH.form)}>{children}</div>;
  return (
    <div className={cn("flex w-full flex-col gap-6 lg:grid lg:grid-cols-[minmax(0,720px)_360px] lg:items-start lg:gap-8", STAFF_WIDTH.formPreview)}>
      <div className="lg:order-2">{preview}</div>
      <div className="min-w-0 space-y-6 lg:order-1">{children}</div>
    </div>
  );
}

/** The course as its card shows it (the organization line is left out: the settings do not know a personal one). */
export function cardDataOf(course: CourseStaffOut, over: Partial<CourseCardData> = {}): CourseCardData {
  return {
    id: course.id, title: course.title, description: course.description, languages: course.languages,
    default_language: course.default_language, owner_display_name: course.owner_display_name,
    organization_display_name: null, is_platform_course: course.is_platform_course, cover_url: course.cover_url ?? null,
    exam_family: course.exam_family, subject: course.subject,
    ...over,
  };
}
