"use client";

import React from "react";
import { useParams } from "next/navigation";
import { StaffGate } from "@/components/lms/content/StaffGate";
import { StaffAttemptList } from "@/components/lms/results/StaffAttemptList";

export default function StaffAttemptsPage() {
  const params = useParams<{ courseId: string; assessmentId: string }>();
  return (
    <StaffGate>
      <StaffAttemptList courseId={params.courseId} assessmentId={params.assessmentId} />
    </StaffGate>
  );
}
