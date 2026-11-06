"use client";

// Phase 8a S4b: the page. Phase 8c S3 (PHASE_8C_DESIGN §5.2): staff get the page object (Edit and Preview tabs by
// `?tab=`); students (and read-only org admins) the page view as before.
// Student UI U7 (STUDENT_UI_DESIGN §3.5): a page opened from the syllabus (`?m={module}&i={item}`) gets the previous /
// next lesson footer.
import React, { Suspense } from "react";
import { useParams, useSearchParams } from "next/navigation";
import { useCourse } from "@/components/lms/CourseContext";
import { PageObject } from "@/components/lms/pages/PageObject";
import { PageView } from "@/components/lms/pages/PageView";
import { PageLessonFooter } from "@/components/lms/modules/LessonView";
import { LoadingState } from "@/components/ui";

export default function PageRoute() {
  const { course } = useCourse();
  const { pageId } = useParams<{ pageId: string }>();
  const role = course.my_enrollment.role;
  if (role === "teacher" || role === "assistant") {
    return <Suspense fallback={<LoadingState />}><PageObject key={pageId} pageId={pageId} /></Suspense>;
  }
  return (
    <>
      <PageView pageId={pageId} />
      {role === "student" && <Suspense fallback={null}><LessonFooter /></Suspense>}
    </>
  );
}

function LessonFooter() {
  const params = useSearchParams();
  const m = params?.get("m");
  const i = params?.get("i");
  const uuid = /^[0-9a-f-]{36}$/;
  if (!m || !i || !uuid.test(m) || !uuid.test(i)) return null;
  return <PageLessonFooter moduleId={m} itemId={i} />;
}
