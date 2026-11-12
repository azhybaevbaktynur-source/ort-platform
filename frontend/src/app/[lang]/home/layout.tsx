"use client";

import React from "react";
import { LmsShell } from "@/components/lms/LmsShell";

// Step 3a S3: Главная `/home` (the hub) in the signed-in frame
export default function HomeLayout({ children }: { children: React.ReactNode }) {
  return <LmsShell>{children}</LmsShell>;
}
