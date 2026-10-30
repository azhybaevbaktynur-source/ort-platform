"use client";

// Phase 8c S2 (PHASE_8C_DESIGN §3): the teacher Course page. Desktop: the outline on the left and the sticky 320 px
// To do panel on the right; below `lg` the To do panel is one line above the outline. General courses: the module
// outline (embedded `ModuleOutlineEditor`) with the "Unsorted" group last. ORT courses (§3.7): today's exam list
// (`StaffAssessmentList`, same content) with the To do panel, and the outline below in a collapsed "Course structure"
// section. The course title (`StaffCourseBar`) is the page `<h1>`; no dashboard cards, no About card.
import React, { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ChevronRight } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { leaveCourse } from "@/lib/lms/courses";
import { pickLocalized } from "@/lib/lms/localized";
import type { ModuleStaffOut } from "@/lib/lms/modulesTypes";
import { templateUi } from "@/lib/lms/templates";
import type { CourseStaffOut } from "@/lib/lms/types";
import { ErrorMessage } from "@/components/lms/ErrorMessage";
import { StaffAssessmentList } from "@/components/lms/assessments/StaffAssessmentList";
import { ModuleOutlineEditor } from "@/components/lms/modules/ModuleOutlineEditor";
import { Button, ConfirmDialog, cn, focusRing } from "@/components/ui";
import { TodoPanel } from "./TodoPanel";
import { UnsortedGroup } from "./UnsortedGroup";

const STRUCTURE_KEY = (courseId: string) => `coursePage.structure:${courseId}`;

export function TeacherCoursePage({ course }: { course: CourseStaffOut }) {
  const { lang, t } = useTranslation();
  const router = useRouter();
  const ui = templateUi(course);
  const ortCourse = ui.locked && ui.key === "ort";
  const canEdit = course.status !== "concluded";
  const [modules, setModules] = useState<ModuleStaffOut[]>([]);
  const [outlineKey, setOutlineKey] = useState(0);
  const [sideKey, setSideKey] = useState(0);
  const [unsortedOpen, setUnsortedOpen] = useState(true);
  const [structureOpen, setStructureOpen] = useState(!ortCourse);
  const [leaving, setLeaving] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  // ORT: the "Course structure" section remembers its state per tab; a `#m-…` link (Back from an object, To do)
  // opens it
  useEffect(() => {
    if (!ortCourse) return;
    let open = false;
    try { open = window.sessionStorage.getItem(STRUCTURE_KEY(course.id)) === "1"; } catch { /* storage unavailable */ }
    const reveal = () => { if (window.location.hash.startsWith("#m-") || window.location.hash === "#unsorted") setStructureOpen(true); };
    setStructureOpen(open);
    reveal();
    window.addEventListener("hashchange", reveal);
    return () => window.removeEventListener("hashchange", reveal);
  }, [ortCourse, course.id]);
  const toggleStructure = () => {
    const next = !structureOpen;
    setStructureOpen(next);
    try { window.sessionStorage.setItem(STRUCTURE_KEY(course.id), next ? "1" : "0"); } catch { /* storage unavailable */ }
  };

  const onOutlineChanged = useCallback(() => setSideKey((k) => k + 1), []);
  const onPlaced = useCallback(() => { setOutlineKey((k) => k + 1); setSideKey((k) => k + 1); }, []);
  const openUnsorted = () => {
    setUnsortedOpen(true);
    window.requestAnimationFrame(() => document.getElementById("unsorted")?.scrollIntoView({ block: "start", behavior: "smooth" }));
  };

  const leave = async () => {
    setBusy(true);
    setError(null);
    try {
      await leaveCourse(course.id);
      router.push(`/${lang}/courses`);
    } catch (e) {
      setError(e);
      setBusy(false);
    }
  };

  const outline = (
    <ModuleOutlineEditor embedded refreshKey={outlineKey} onChanged={onOutlineChanged} onModules={setModules} onAddExisting={openUnsorted}
      afterModules={(
        <UnsortedGroup courseId={course.id} defaultLang={course.default_language} modules={modules} canEdit={canEdit}
          open={unsortedOpen} onOpenChange={setUnsortedOpen} refreshKey={sideKey} onPlaced={onPlaced} onChanged={onOutlineChanged} />
      )} />
  );

  return (
    <div className="space-y-4">
      {course.status === "draft" && (
        <p role="status" className="rounded-xl border border-warning-200 bg-warning-50 px-4 py-3 text-sm text-warning-900">{t("courses.home.draftNotice")}</p>
      )}
      {course.status === "concluded" && (
        <p role="status" className="rounded-xl border border-slate-200 bg-slate-100 px-4 py-3 text-sm text-slate-700">{t("courses.home.concludedNotice")}</p>
      )}
      <div className="flex flex-col gap-4 lg:grid lg:grid-cols-[minmax(0,1fr)_320px] lg:items-start lg:gap-8">
        <TodoPanel course={course} refreshKey={sideKey} className="lg:sticky lg:top-6 lg:col-start-2 lg:row-start-1" />
        <div className="min-w-0 space-y-6 lg:col-start-1 lg:row-start-1">
          {ortCourse ? (
            <>
              <StaffAssessmentList embedded />
              <div className="rounded-2xl border border-slate-200 bg-white">
                <button type="button" aria-expanded={structureOpen} aria-controls="course-structure" onClick={toggleStructure}
                  className={cn("flex min-h-12 w-full items-center gap-3 rounded-2xl px-4 py-3 text-left", focusRing)}>
                  <ChevronRight aria-hidden="true" className={cn("h-5 w-5 shrink-0 text-slate-600 transition-transform", structureOpen && "rotate-90")} />
                  <span className="min-w-0">
                    <span className="block text-lg font-semibold leading-7 text-slate-900">{t("coursePage.structure")}</span>
                    <span className="block text-sm leading-6 text-slate-600">{t("coursePage.structureHint")}</span>
                  </span>
                </button>
                <div id="course-structure" hidden={!structureOpen} className="border-t border-slate-100 p-3 sm:p-4">
                  {structureOpen && outline}
                </div>
              </div>
            </>
          ) : outline}
          {!course.is_owner && (
            <div>
              <Button variant="link" className="text-danger-700 hover:text-danger-800" onClick={() => setLeaving(true)}>{t("courses.home.leave")}</Button>
            </div>
          )}
        </div>
      </div>
      <ConfirmDialog open={leaving} tone="danger" busy={busy} title={t("courses.home.leaveTitle")}
        object={pickLocalized(course.title, lang, course.default_language) || t("courses.list.untitled")}
        effect={t("courses.home.leaveBody")} error={error ? <ErrorMessage error={error} /> : undefined}
        confirmLabel={t("courses.home.leave")} onConfirm={() => void leave()} onCancel={() => setLeaving(false)} />
    </div>
  );
}
