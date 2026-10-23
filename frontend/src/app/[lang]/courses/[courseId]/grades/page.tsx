"use client";

import React from "react";
import { useCourse } from "@/components/lms/CourseContext";
import { StaffGradebook } from "@/components/lms/gradebook/StaffGradebook";
import { StudentGrades } from "@/components/lms/results/StudentGrades";

/** Grades tab: staff see the gradebook, students their own grades. The server decides what each may read. */
export default function GradesPage() {
  const { course } = useCourse();
  const role = course.my_enrollment.role;
  return role === "teacher" || role === "assistant" ? <StaffGradebook /> : <StudentGrades courseId={course.id} />;
}
