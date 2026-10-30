"use client";

// Phase 8c S3 (PHASE_8C_DESIGN §4.2): redirect stub, kept one phase (removed at the Phase 9 kickoff): the page object's
// Edit tab (query carried over). Students land on the page view of the same URL, which ignores `tab`.
import React from "react";
import { useParams } from "next/navigation";
import { useTranslation } from "@/lib/i18n/context";
import { useCourse } from "@/components/lms/CourseContext";
import { RedirectStub } from "@/components/lms/assignments/objectNav";

export default function EditPageRedirect() {
  const { lang } = useTranslation();
  const { course } = useCourse();
  const { pageId } = useParams<{ pageId: string }>();
  return <RedirectStub target={`/${lang}/courses/${course.id}/pages/${pageId}`} set={{ tab: "edit" }} />;
}
