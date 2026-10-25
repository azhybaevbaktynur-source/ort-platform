"use client";

// Phase 7a S5: Assignments tab. Staff get the table, students (and read-only org admins) the cards.
import React from "react";
import { useCourse } from "@/components/lms/CourseContext";
import { StaffAssignmentList } from "@/components/lms/assignments/StaffAssignmentList";
import { StudentAssignmentList } from "@/components/lms/assignments/StudentAssignmentList";

export default function AssignmentsPage() {
  const { course } = useCourse();
  const role = course.my_enrollment.role;
  return role === "teacher" || role === "assistant" ? <StaffAssignmentList /> : <StudentAssignmentList />;
}
