"use client";

// Phase 8c S2 (PHASE_8C_DESIGN §3): the teacher Course page. General courses: the module outline (`ModuleOutlineEditor`)
// with one collapsed "Not in modules" row last. The course title (`StaffCourseBar`) is the page `<h1>`; no dashboard
// cards, no About card.
// UX rework D (UR-4): what waits for grading is all that sits beside the outline: a right column from `xl`, one line link
// above it below `xl`, nothing when nothing waits. The join code moved to People.
// FB8-5 S1 (STAFF_UX_AUDIT §2, D-FB8-5-1/7): the page is the "Content" section with its tab row (`ContentTabs`):
// Structure (this page) and Assignments (`/assignments`). ORT courses: the Exams tab (the exam table,
// `StaffAssessmentList`) is the default and the outline is the Structure tab (`?tab=structure`); a `#m-…` link (Back
// from an object) opens the Structure tab. No collapsible section, nothing kept in `sessionStorage`.
import React, { useCallback, useEffect, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useTranslation } from "@/lib/i18n/context";
import type { ModuleStaffOut } from "@/lib/lms/modulesTypes";
import type { CourseStaffOut } from "@/lib/lms/types";
import { StaffAssessmentList } from "@/components/lms/assessments/StaffAssessmentList";
import { ModuleOutlineEditor } from "@/components/lms/modules/ModuleOutlineEditor";
import { cn } from "@/components/ui";
import { ContentTabs, hasExamsTab } from "./ContentTabs";
import { ToGradeColumn, ToGradeLine, useToGrade } from "./ToGrade";
import { UnsortedGroup } from "./UnsortedGroup";

export function TeacherCoursePage({ course }: { course: CourseStaffOut }) {
  const { t } = useTranslation();
  const router = useRouter();
  const pathname = usePathname() || "";
  const search = useSearchParams();
  const ortCourse = hasExamsTab(course);
  const canEdit = course.status !== "concluded";
  const [modules, setModules] = useState<ModuleStaffOut[]>([]);
  const [outlineKey, setOutlineKey] = useState(0);
  const [sideKey, setSideKey] = useState(0);
  const toGrade = useToGrade(course.id, sideKey);
  const waiting = toGrade && toGrade.to_grade_total > 0 ? toGrade : null;
  const tab = ortCourse && search?.get("tab") !== "structure" ? "exams" : "structure";

  // ORT: a `#m-…` link lands on the Exams tab URL; move it to the Structure tab, keeping the hash for the outline
  useEffect(() => {
    if (!ortCourse) return;
    const reveal = () => {
      const hash = window.location.hash;
      if (!hash.startsWith("#m-") || new URLSearchParams(window.location.search).get("tab") === "structure") return;
      const qs = new URLSearchParams(window.location.search);
      qs.set("tab", "structure");
      router.replace(`${pathname}?${qs.toString()}${hash}`, { scroll: false });
    };
    reveal();
    window.addEventListener("hashchange", reveal);
    return () => window.removeEventListener("hashchange", reveal);
  }, [ortCourse, router, pathname]);

  const onOutlineChanged = useCallback(() => setSideKey((k) => k + 1), []);
  const onPlaced = useCallback(() => { setOutlineKey((k) => k + 1); setSideKey((k) => k + 1); }, []);

  return (
    <div className="space-y-4">
      <ContentTabs course={course} active={tab} className="mb-0" />
      {course.status === "draft" && (
        <p role="status" className="rounded-xl border border-warning-200 bg-warning-50 px-4 py-3 text-sm text-warning-900">{t("courses.home.draftNotice")}</p>
      )}
      {course.status === "concluded" && (
        <p role="status" className="rounded-xl border border-slate-200 bg-slate-100 px-4 py-3 text-sm text-slate-700">{t("courses.home.concludedNotice")}</p>
      )}
      {waiting && <ToGradeLine courseId={course.id} data={waiting} className="xl:hidden" />}
      <div className={cn("min-w-0", waiting && "xl:grid xl:grid-cols-[minmax(0,1fr)_300px] xl:items-start xl:gap-8")}>
        <div className="min-w-0 space-y-6">
          {tab === "exams" ? <StaffAssessmentList embedded /> : (
            <ModuleOutlineEditor refreshKey={outlineKey} onChanged={onOutlineChanged} onModules={setModules}
              afterModules={(
                <UnsortedGroup courseId={course.id} defaultLang={course.default_language} modules={modules} canEdit={canEdit}
                  refreshKey={sideKey} onPlaced={onPlaced} onChanged={onOutlineChanged} />
              )} />
          )}
          {/* Phase 8c UX m9: no "Leave course" on the teacher Course page */}
        </div>
        {waiting && <ToGradeColumn course={course} data={waiting} className="hidden xl:sticky xl:top-6 xl:block" />}
      </div>
    </div>
  );
}
