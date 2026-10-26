"use client";

import React from "react";
import { LmsShell } from "@/components/lms/LmsShell";
import { TeacherTemplatesGate } from "@/components/lms/examTemplates/TeacherTemplatesGate";

export default function ExamTemplatesLayout({ children }: { children: React.ReactNode }) {
  return (
    <LmsShell>
      <TeacherTemplatesGate>{children}</TeacherTemplatesGate>
    </LmsShell>
  );
}
