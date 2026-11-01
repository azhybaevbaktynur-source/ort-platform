"use client";

import React from "react";
import { useParams } from "next/navigation";
import { QuizStatsView } from "@/components/lms/analytics/QuizStatsView";

export default function QuizStatsRoute() {
  const params = useParams<{ assessmentId: string }>();
  return <QuizStatsView assessmentId={params.assessmentId} />;
}
