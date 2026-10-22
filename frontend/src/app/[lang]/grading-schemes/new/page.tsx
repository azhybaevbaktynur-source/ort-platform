"use client";

import React, { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { NewSchemeForm } from "@/components/lms/grading/schemes/NewSchemeForm";

function NewSchemeInner() {
  const sp = useSearchParams();
  return <NewSchemeForm fromId={sp.get("from")} fromVersionId={sp.get("version")} />;
}

export default function NewGradingSchemePage() {
  return (
    <Suspense fallback={null}>
      <NewSchemeInner />
    </Suspense>
  );
}
