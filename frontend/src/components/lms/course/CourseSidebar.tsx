"use client";

// Phase 8c S1 (PHASE_8C_DESIGN §2.1-§2.3): the short left course sidebar for staff and students, a "Course menu"
// sheet on phones (`AreaShell` `phone="drawer"`). Links and active state come from `courseNavItems` (lib/lms/nav.ts);
// students do not get Announcements and Files until something is published there, staff see a "hidden from
// students" mark on those links instead.
import React from "react";
import { usePathname } from "next/navigation";
import {
  BookOpen, ClipboardList, EyeOff, FolderOpen, GraduationCap, Library, Megaphone, Settings, Users,
} from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { courseNavItems, courseNavRole, type CourseNavKey } from "@/lib/lms/nav";
import type { CourseOut } from "@/lib/lms/types";
import { AreaShell } from "@/components/ui/AreaShell";

const ICONS: Record<CourseNavKey, React.ReactNode> = {
  course: <BookOpen />,
  announcements: <Megaphone />,
  assignments: <ClipboardList />,
  grades: <GraduationCap />,
  people: <Users />,
  bank: <Library />,
  settings: <Settings />,
  files: <FolderOpen />,
};

export function CourseSidebar({ course, children }: { course: CourseOut; children: React.ReactNode }) {
  const { t } = useTranslation();
  const pathname = usePathname() || "";
  const role = courseNavRole(course);
  const links = courseNavItems(course, role, pathname, t);
  const anyHidden = links.some((l) => l.hiddenFromStudents);
  return (
    <AreaShell
      label={t("courses.home.tabsLabel")}
      phone="drawer"
      menuLabel={t("courseNav.menu")}
      navFooter={anyHidden ? t("courseNav.hiddenHelp") : undefined}
      items={links.map((l) => ({
        href: l.href, label: l.label, active: l.active, icon: ICONS[l.key],
        marker: l.hiddenFromStudents ? { icon: <EyeOff />, label: t("courseNav.hiddenFromStudents") } : null,
      }))}
    >
      {children}
    </AreaShell>
  );
}
