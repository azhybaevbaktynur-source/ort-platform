"use client";

import React from "react";
import { useCourse } from "@/components/lms/CourseContext";
import { HiddenAreaBadge } from "@/components/lms/course/StaffCourseUi";
import { PracticeList } from "@/components/lms/practice/PracticeList";
import { ToCourseTab } from "@/components/lms/course/ToCourseTab"; // step 3a S2
import { inCourseSpace } from "@/lib/lms/templates"; // step 3a S2

// FB8-5 S1 (STAFF_UX_AUDIT §2, D-FB8-5-2): staff see "Hidden" above the list while no practice quiz is published
// (the sidebar no longer marks it).
export default function PracticeRoute() {
  const { course } = useCourse();
  const role = course.my_enrollment.role;
  const staff = (role === "teacher" || role === "assistant") && !course.my_enrollment.read_only;
  // step 3a S2 (§3.7, D6): a student's practice sets are the «Тренировки» section of the Тесты tab
  if (inCourseSpace(course)) return <ToCourseTab courseId={course.id} path="/tests#practice" />;
  return (
    <>
      {staff && course.features && !course.features.practice && (
        <div className="mb-2 flex"><HiddenAreaBadge course={course} area="practice" /></div>
      )}
      <PracticeList />
    </>
  );
}
