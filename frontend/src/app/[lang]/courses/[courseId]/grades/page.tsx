"use client";

import React from "react";
import { useParams } from "next/navigation";
import { StudentGrades } from "@/components/lms/results/StudentGrades";

// Student branch only; the staff gradebook branch (slice F3) is merged in by the orchestrator.
export default function GradesPage() {
  const { courseId } = useParams<{ courseId: string }>();
  return <StudentGrades courseId={courseId} />;
}
