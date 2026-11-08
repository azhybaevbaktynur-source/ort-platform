"use client";

// Phase 7a S5: Assignments tab. Staff get the table, students (and read-only org admins) the cards.
// FB8-5 S1 (STAFF_UX_AUDIT §2): for staff this is the Assignments tab of Content, under the same tab row as the Course page.
import React from "react";
import { useCourse } from "@/components/lms/CourseContext";
import { ContentTabs } from "@/components/lms/course/ContentTabs";
import { StaffAssignmentList } from "@/components/lms/assignments/StaffAssignmentList";
import { StudentAssignmentList } from "@/components/lms/assignments/StudentAssignmentList";

export default function AssignmentsPage() {
  const { course } = useCourse();
  const role = course.my_enrollment.role;
  if (role === "teacher" || role === "assistant") {
    return (
      <>
        <ContentTabs course={course} active="assignments" />
        <StaffAssignmentList />
      </>
    );
  }
  return <StudentAssignmentList />;
}
