"use client";

// Phase 8a S4b: the page. Phase 8c S3 (PHASE_8C_DESIGN §5.2): staff get the page object (Edit and Preview tabs by
// `?tab=`); students (and read-only org admins) the page view as before.
// F5b (COURSE_LESSONS_DESIGN L3): a page lesson renders inline on the lesson page; an older link opened from the
// syllabus (`?from=module&m={module}&i={item}`) forwards a student there. Other links keep the page view.
import React, { Suspense, useEffect } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useTranslation } from "@/lib/i18n/context";
import { useCourse } from "@/components/lms/CourseContext";
import { PageObject } from "@/components/lms/pages/PageObject";
import { PageView } from "@/components/lms/pages/PageView";
import { LoadingState } from "@/components/ui";

const UUID = /^[0-9a-f-]{36}$/;

export default function PageRoute() {
  const { course } = useCourse();
  const { pageId } = useParams<{ pageId: string }>();
  const role = course.my_enrollment.role;
  if (role === "teacher" || role === "assistant") {
    return <Suspense fallback={<LoadingState />}><PageObject key={pageId} pageId={pageId} /></Suspense>;
  }
  if (role === "student") return <Suspense fallback={<LoadingState />}><StudentPage pageId={pageId} /></Suspense>;
  return <PageView pageId={pageId} />;
}

function StudentPage({ pageId }: { pageId: string }) {
  const { lang } = useTranslation();
  const { course } = useCourse();
  const router = useRouter();
  const params = useSearchParams();
  const m = params?.get("m") ?? "";
  const i = params?.get("i") ?? "";
  const lesson = params?.get("from") === "module" && UUID.test(m) && UUID.test(i) ? `/${lang}/courses/${course.id}/modules/${m}/items/${i}` : null;
  useEffect(() => {
    if (lesson) router.replace(lesson);
  }, [lesson, router]);
  if (lesson) return <LoadingState />;
  return <PageView pageId={pageId} />;
}
