"use client";

import React from "react";
import { useParams } from "next/navigation";
import { ApplyPage } from "@/components/lms/catalog/ApplyPage";

/** Phase 9 S4: apply to a course with its enrollment form (PHASE_9_DESIGN 4.7, 8.1). */
export default function CatalogApplyPage() {
  const { courseId } = useParams<{ courseId: string }>();
  return <ApplyPage key={courseId} courseId={courseId} />;
}
