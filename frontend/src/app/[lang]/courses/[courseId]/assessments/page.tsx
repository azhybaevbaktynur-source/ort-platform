"use client";

import React from "react";
import { useCourse } from "@/components/lms/CourseContext";
import { StaffAssessmentList } from "@/components/lms/assessments/StaffAssessmentList";
import { StudentAssessmentList } from "@/components/lms/assessments/StudentAssessmentList";

export default function AssessmentsPage() {
  const { course } = useCourse();
  const role = course.my_enrollment.role;
  return role === "teacher" || role === "assistant" ? <StaffAssessmentList /> : <StudentAssessmentList />;
}
