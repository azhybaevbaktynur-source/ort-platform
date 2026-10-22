"use client";

import React, { Suspense } from "react";
import { useParams, useSearchParams } from "next/navigation";
import { StudentResult } from "@/components/lms/results/StudentResult";
import { UnsavedNotice } from "@/components/lms/player/UnsavedNotice";

function UnsavedFromQuery() {
  const search = useSearchParams();
  return <UnsavedNotice value={search.get("unsaved")} />;
}

export default function AttemptResultPage() {
  const params = useParams<{ courseId: string; attemptId: string }>();
  return (
    <>
      <Suspense fallback={null}>
        <UnsavedFromQuery />
      </Suspense>
      <StudentResult courseId={params.courseId} attemptId={params.attemptId} />
    </>
  );
}
