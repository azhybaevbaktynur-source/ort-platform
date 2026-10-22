"use client";

import React from "react";
import { LmsShell } from "@/components/lms/LmsShell";
import { AdminShell } from "@/components/lms/admin/AdminShell";

export default function AdminAreaLayout({ children }: { children: React.ReactNode }) {
  return (
    <LmsShell>
      <AdminShell>{children}</AdminShell>
    </LmsShell>
  );
}
