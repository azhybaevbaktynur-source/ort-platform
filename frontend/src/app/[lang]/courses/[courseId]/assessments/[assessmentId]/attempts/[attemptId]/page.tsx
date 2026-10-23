"use client";

import React from "react";
import { useParams } from "next/navigation";
import { StaffGate } from "@/components/lms/content/StaffGate";
import { StaffAttemptDetail } from "@/components/lms/results/StaffAttemptDetail";

export default function StaffAttemptPage() {
  const params = useParams<{ courseId: string; assessmentId: string; attemptId: string }>();
  return (
    <StaffGate>
      <StaffAttemptDetail courseId={params.courseId} assessmentId={params.assessmentId} attemptId={params.attemptId} />
    </StaffGate>
  );
}
