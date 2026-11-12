"use client";

import React from "react";
import { useCourse } from "@/components/lms/CourseContext";
import { StaffGradebook } from "@/components/lms/gradebook/StaffGradebook";
import { StudentGrades } from "@/components/lms/results/StudentGrades";
import { ToCourseTab } from "@/components/lms/course/ToCourseTab"; // step 3a S2
import { inCourseSpace } from "@/lib/lms/templates"; // step 3a S2

/** Grades tab: staff see the gradebook, students their own grades. The server decides what each may read. */
export default function GradesPage() {
  const { course } = useCourse();
  const role = course.my_enrollment.role;
  // step 3a S2 (§3.7, D3): a student's grades are the «Оценки» block of the Аналитика tab
  if (inCourseSpace(course)) return <ToCourseTab courseId={course.id} path="/analytics#grades" />;
  return role === "teacher" || role === "assistant" ? <StaffGradebook /> : <StudentGrades courseId={course.id} />;
}
