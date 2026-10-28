"use client";

import React, { Suspense } from "react";
import { PageEditor } from "@/components/lms/pages/PageEditor";
import { StaffGate } from "@/components/lms/content/StaffGate";

export default function NewPageRoute() {
  return <StaffGate><Suspense><PageEditor /></Suspense></StaffGate>;
}
