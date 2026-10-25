"use client";

import React from "react";
import { OrgShell } from "@/components/lms/org/OrgShell";

export default function OrgLayout({ children }: { children: React.ReactNode }) {
  return <OrgShell>{children}</OrgShell>;
}
