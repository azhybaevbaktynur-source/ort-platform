"use client";

import React from "react";
import { LmsShell } from "@/components/lms/LmsShell";

export default function OrgAreaLayout({ children }: { children: React.ReactNode }) {
  return <LmsShell>{children}</LmsShell>;
}
