"use client";

import React from "react";
import { CourseAnalytics } from "@/components/lms/analytics/CourseAnalytics";
import { StudentAnalyticsTab } from "@/components/lms/progress/StudentAnalyticsTab"; // step 3a S2
import { useCourse } from "@/components/lms/CourseContext";
import { inCourseSpace } from "@/lib/lms/templates";

/** Step 3a S2 (STUDENT_IA_DESIGN §3.2, N4): students get the course's Аналитика tab; staff and read-only viewers the
 * quiz statistics as before (the same pattern as the course page). */
export default function CourseAnalyticsRoute() {
  const { course } = useCourse();
  if (inCourseSpace(course)) return <StudentAnalyticsTab />;
  return <CourseAnalytics />;
}
