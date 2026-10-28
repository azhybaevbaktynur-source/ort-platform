"use client";

import React from "react";
import { usePathname } from "next/navigation";
import { useTranslation } from "@/lib/i18n/context";
import { TabsNav } from "@/components/ui";
import { useCourse } from "./CourseContext";

/**
 * Role-aware tabs. Settings is shown to teachers only; the server stays authoritative.
 * Phase 6b S5c (UX T29): one scrollable row (design-system `TabsNav`) with the active tab kept in view.
 * Phase 8a S4a: Modules, Pages, Files and Announcements for staff in every course (students: StudentCourseTabs).
 */
export function CourseTabs({ courseId, showSettings }: { courseId: string; showSettings: boolean }) {
  const { lang, t } = useTranslation();
  const pathname = usePathname();
  const { course } = useCourse();
  const role = course.my_enrollment.role;
  const showBank = role === "teacher" || role === "assistant";
  const base = `/${lang}/courses/${courseId}`;
  const tabs = [
    { href: base, label: t("courses.home.tab"), exact: true },
    // --- Phase 8a S4a: course structure tabs for staff, in every course (ORT too; additive, PHASE_8A_DESIGN 8.2) ---
    { href: `${base}/modules`, label: t("modules.tab") },
    // --- Phase 8a S4a end ---
    { href: `${base}/people`, label: t("courses.people.tab") },
    // --- Phase 7a S5: Assignments (every gradable item); the quiz builder list keeps its own tab ---
    { href: `${base}/assignments`, label: t("assignments.tab") },
    { href: `${base}/assessments`, label: t("assignments.tabQuizzes") },
    // --- Phase 8a S4a begin ---
    { href: `${base}/pages`, label: t("pages.title") },
    { href: `${base}/files`, label: t("courseFiles.title") },
    { href: `${base}/announcements`, label: t("announcements.title") },
    // --- Phase 8a S4a end ---
    { href: `${base}/grades`, label: t("gradebook.tab") },
    ...(showBank ? [{ href: `${base}/bank`, label: t("bank.tab") }] : []),
    ...(showSettings ? [{ href: `${base}/settings`, label: t("courses.settings.tab") }] : []),
  ];
  return (
    <TabsNav
      label={t("courses.home.tabsLabel")}
      className="mb-6"
      items={tabs.map((tab) => ({
        href: tab.href,
        label: tab.label,
        active: tab.exact ? pathname === tab.href : pathname.startsWith(tab.href),
      }))}
    />
  );
}
