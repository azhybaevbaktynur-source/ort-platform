"use client";

import React from "react";
import { LmsShell } from "@/components/lms/LmsShell";

export default function GradingSchemesLayout({ children }: { children: React.ReactNode }) {
  return <LmsShell>{children}</LmsShell>;
}
