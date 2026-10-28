"use client";

import React, { Suspense } from "react";
import { useParams } from "next/navigation";
import { PageEditor } from "@/components/lms/pages/PageEditor";
import { StaffGate } from "@/components/lms/content/StaffGate";

export default function EditPageRoute() {
  const { pageId } = useParams<{ pageId: string }>();
  return <StaffGate><Suspense><PageEditor pageId={pageId} /></Suspense></StaffGate>;
}
