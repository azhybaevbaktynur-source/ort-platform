"use client";

// FB8-5 S1 (STAFF_UX_AUDIT §2, D-FB8-5-1/7): the tab row of the staff "Content" section, under the course bar on the
// Course page and on `/assignments` (links, `aria-current`). General courses: Structure (the module outline, the Course
// page) and Assignments. ORT: Exams (the exam table, the Course page by default), Structure (`?tab=structure`, or a
// `#m-…` link) and Assignments.
import React from "react";
import { useTranslation } from "@/lib/i18n/context";
import { templateUi } from "@/lib/lms/templates";
import type { CourseOut } from "@/lib/lms/types";
import { TabsNav } from "@/components/ui";

export type ContentTab = "exams" | "structure" | "assignments";

/** ORT (the locked `ort` template) shows the Exams tab first. */
export function hasExamsTab(course: Pick<CourseOut, "template">): boolean {
  const ui = templateUi(course);
  return ui.locked && ui.key === "ort";
}

export function ContentTabs({ course, active, className }: { course: CourseOut; active: ContentTab; className?: string }) {
  const { lang, t } = useTranslation();
  const base = `/${lang}/courses/${course.id}`;
  const exams = hasExamsTab(course);
  const items = [
    ...(exams ? [{ href: base, label: t("courseNav.tabs.exams"), active: active === "exams" }] : []),
    { href: exams ? `${base}?tab=structure` : base, label: t("courseNav.tabs.structure"), active: active === "structure" },
    { href: `${base}/assignments`, label: t("courseNav.tabs.assignments"), active: active === "assignments" },
  ];
  return <TabsNav label={t("courseNav.tabs.label")} items={items} className={className ?? "mb-4"} />;
}
