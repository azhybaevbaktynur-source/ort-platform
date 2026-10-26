"use client";

import React from "react";
import { ExamTemplatesPage } from "@/components/lms/examTemplates/ExamTemplatesPage";

export default function MyExamTemplatesPage() {
  return <ExamTemplatesPage area={{ kind: "teacher" }} />;
}
