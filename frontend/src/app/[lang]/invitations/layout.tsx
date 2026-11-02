"use client";

import React from "react";
import { LmsShell } from "@/components/lms/LmsShell";

export default function InvitationsLayout({ children }: { children: React.ReactNode }) {
  return <LmsShell>{children}</LmsShell>;
}
