"use client";

// Phase 8a S4a: `/courses/[courseId]/modules`: the outline editor for teachers and assistants, the modules view for
// students (and read-only, without progress, for an org admin reading the course).
import React from "react";
import { useCourse } from "@/components/lms/CourseContext";
import { ModuleOutlineEditor } from "@/components/lms/modules/ModuleOutlineEditor";
import { StudentModulesView } from "@/components/lms/modules/StudentModulesView";
import { isStaffCourse } from "@/lib/lms/types";

export default function ModulesPage() {
  const { course } = useCourse();
  const role = course.my_enrollment.role;
  if (isStaffCourse(course) && (role === "teacher" || role === "assistant") && !course.my_enrollment.read_only) return <ModuleOutlineEditor />;
  return <StudentModulesView />;
}
