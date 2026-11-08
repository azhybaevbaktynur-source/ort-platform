"use client";

import React from "react";
import { useCourse } from "@/components/lms/CourseContext";
import { HiddenAreaBadge } from "@/components/lms/course/StaffCourseUi";
import { PracticeList } from "@/components/lms/practice/PracticeList";

// FB8-5 S1 (STAFF_UX_AUDIT §2, D-FB8-5-2): staff see "Hidden" above the list while no practice quiz is published
// (the sidebar no longer marks it).
export default function PracticeRoute() {
  const { course } = useCourse();
  const role = course.my_enrollment.role;
  const staff = (role === "teacher" || role === "assistant") && !course.my_enrollment.read_only;
  return (
    <>
      {staff && course.features && !course.features.practice && (
        <div className="mb-2 flex"><HiddenAreaBadge course={course} area="practice" /></div>
      )}
      <PracticeList />
    </>
  );
}
