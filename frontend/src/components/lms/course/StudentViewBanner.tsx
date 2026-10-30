"use client";

// Phase 8c S1 (PHASE_8C_DESIGN §2.4, §6.2): the sticky banner over a course in the read-only Student view, and the
// button that starts it. The mode is a per-tab flag (`sessionStorage`, see `lib/api.ts`); starting or leaving it
// reloads the page so every course request is sent again with (or without) `X-View-As: student`.
import React from "react";
import { Eye } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { setStudentView } from "@/lib/api";
import { Button } from "@/components/ui";

function reload() {
  if (typeof window !== "undefined") window.location.reload();
}

export function StudentViewBanner({ courseId }: { courseId: string }) {
  const { t } = useTranslation();
  return (
    <div role="status"
      className="sticky top-0 z-30 -mx-4 mb-4 flex flex-wrap items-center gap-x-3 gap-y-2 border-y border-warning-200 bg-warning-50 px-4 py-2.5 text-sm leading-6 text-warning-900 sm:mx-0 sm:rounded-xl sm:border">
      <Eye aria-hidden="true" className="h-4 w-4 shrink-0" />
      <p className="min-w-0 flex-1">{t("studentView.banner")}</p>
      <Button size="sm" variant="secondary" onClick={() => { setStudentView(courseId, false); reload(); }}>
        {t("studentView.leave")}
      </Button>
    </div>
  );
}

/** "Student view" (teacher and assistant; never in a template sandbox, the caller decides). */
export function StudentViewButton({ courseId }: { courseId: string }) {
  const { t } = useTranslation();
  return (
    <Button size="sm" variant="secondary" leftIcon={<Eye aria-hidden="true" />}
      onClick={() => { setStudentView(courseId, true); reload(); }}>
      {t("studentView.button")}
    </Button>
  );
}
