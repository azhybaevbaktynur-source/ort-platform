"use client";

import React from "react";
import { useParams } from "next/navigation";
import { StudentResult } from "@/components/lms/results/StudentResult";

export default function AttemptResultPage() {
  const params = useParams<{ courseId: string; attemptId: string }>();
  return <StudentResult courseId={params.courseId} attemptId={params.attemptId} />;
}
