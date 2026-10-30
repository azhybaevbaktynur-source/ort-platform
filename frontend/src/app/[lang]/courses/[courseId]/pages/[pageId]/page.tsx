"use client";

// Phase 8a S4b: the page. Phase 8c S3 (PHASE_8C_DESIGN §5.2): staff get the page object (Edit and Preview tabs by
// `?tab=`); students (and read-only org admins) the page view as before.
import React, { Suspense } from "react";
import { useParams } from "next/navigation";
import { useCourse } from "@/components/lms/CourseContext";
import { PageObject } from "@/components/lms/pages/PageObject";
import { PageView } from "@/components/lms/pages/PageView";
import { LoadingState } from "@/components/ui";

export default function PageRoute() {
  const { course } = useCourse();
  const { pageId } = useParams<{ pageId: string }>();
  const role = course.my_enrollment.role;
  if (role === "teacher" || role === "assistant") {
    return <Suspense fallback={<LoadingState />}><PageObject key={pageId} pageId={pageId} /></Suspense>;
  }
  return <PageView pageId={pageId} />;
}
