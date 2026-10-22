"use client";

import React from "react";
import { useParams } from "next/navigation";
import { SchemeDetail } from "@/components/lms/grading/schemes/SchemeDetail";

export default function GradingSchemePage() {
  const params = useParams<{ schemeId: string }>();
  return <SchemeDetail key={params.schemeId} schemeId={params.schemeId} />;
}
