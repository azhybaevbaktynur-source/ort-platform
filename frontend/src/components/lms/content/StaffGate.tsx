"use client";

import React from "react";
import { useTranslation } from "@/lib/i18n/context";
import { useCourse } from "@/components/lms/CourseContext";

/** Question bank is for course teachers and assistants only (the server enforces it too). */
export function StaffGate({ children }: { children: React.ReactNode }) {
  const { t } = useTranslation();
  const { course } = useCourse();
  const role = course.my_enrollment.role;
  if (role !== "teacher" && role !== "assistant") {
    return <p role="alert" className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">{t("bank.notAuthorized")}</p>;
  }
  return <>{children}</>;
}

/** Concluded courses are read-only for content (server returns the status gate error). */
export function useCanEditContent(): boolean {
  const { course } = useCourse();
  return course.status !== "concluded" && (course.my_enrollment.role === "teacher" || course.my_enrollment.role === "assistant");
}
