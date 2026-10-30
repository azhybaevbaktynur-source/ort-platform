"use client";

import React from "react";
import { useParams } from "next/navigation";
import { CourseLanding } from "@/components/lms/catalog/CourseLanding";

/** Phase 9 S4: course landing in the catalog (PHASE_9_DESIGN 4.6, 8.1). */
export default function CatalogCoursePage() {
  const { courseId } = useParams<{ courseId: string }>();
  return <CourseLanding key={courseId} courseId={courseId} />;
}
