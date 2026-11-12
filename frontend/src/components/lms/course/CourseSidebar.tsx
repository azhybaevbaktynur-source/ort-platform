"use client";

// Phase 8c S1 (PHASE_8C_DESIGN §2.1-§2.3): the short left course sidebar for staff and read-only viewers (step 3a:
// students have the course space, `CourseFrame`), a "Course menu" sheet on phones (`AreaShell` `phone="drawer"`).
// Links and active state come from `courseNavItems` (lib/lms/nav.ts); readers do not get Announcements and Files
// until something is published there.
// FB8-5 S1 (STAFF_UX_AUDIT §2, D-FB8-5-1/2): staff get the five sections and a labelled "More" group; no crossed-eye
// marker any more: a hidden area says so with a badge on its own page header.
import React from "react";
import { usePathname } from "next/navigation";
import {
  BarChart3, BookOpen, Bookmark, ClipboardList, Dumbbell, FolderOpen, GraduationCap, Library, Megaphone, Settings,
  TrendingUp, Users,
} from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { courseNavItems, courseNavRole, type CourseNavKey } from "@/lib/lms/nav";
import { isStaffCourse, type CourseOut } from "@/lib/lms/types";
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
  practice: <Dumbbell />,
  progress: <TrendingUp />,
  saved: <Bookmark />,
  analytics: <BarChart3 />,
};

export function CourseSidebar({ course, children }: { course: CourseOut; children: React.ReactNode }) {
  const { t } = useTranslation();
  const pathname = usePathname() || "";
  const role = courseNavRole(course);
  // Phase 9 UX: same predicate as the course layout's Teaching area (org admins get the staff serializer)
  const links = courseNavItems(course, role, pathname, t, { staffShape: isStaffCourse(course) });
  return (
    <AreaShell
      label={t("courses.home.tabsLabel")}
      phone="drawer"
      menuLabel={t("courseNav.menu")}
      items={links.map((l) => ({
        href: l.href, label: l.label, active: l.active, icon: ICONS[l.key],
        group: l.group === "more" ? t("courseNav.more") : undefined,
      }))}
    >
      {children}
    </AreaShell>
  );
}
