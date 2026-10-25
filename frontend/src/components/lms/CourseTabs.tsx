"use client";

import React from "react";
import { usePathname } from "next/navigation";
import { useTranslation } from "@/lib/i18n/context";
import { TabsNav } from "@/components/ui";
import { useCourse } from "./CourseContext";

/**
 * Role-aware tabs. Settings is shown to teachers only; the server stays authoritative.
 * Phase 6b S5c (UX T29): one scrollable row (design-system `TabsNav`) with the active tab kept in view.
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
    { href: `${base}/people`, label: t("courses.people.tab") },
    // --- Phase 7a S5: Assignments (every gradable item); the quiz builder list keeps its own tab ---
    { href: `${base}/assignments`, label: t("assignments.tab") },
    { href: `${base}/assessments`, label: t("assignments.tabQuizzes") },
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
