"use client";

import React, { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { ChooseCourses } from "@/components/lms/home/ChooseCourses";

/** Step 3a S4 (STUDENT_IA_DESIGN §4): «Выберите курсы»; `?first=1` (after sign-up) offers «Пропустить». */
function ChoosePage() {
  const first = useSearchParams().get("first") === "1";
  return <ChooseCourses first={first} />;
}

export default function CoursesChoosePage() {
  return (
    <Suspense fallback={null}>
      <ChoosePage />
    </Suspense>
  );
}
