"use client";

// The student's quiet "Leave course" at the bottom of a course home (today's home and the modules view).
import React, { useState } from "react";
import { useRouter } from "next/navigation";
import { LogOut } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { leaveCourse } from "@/lib/lms/courses";
import { pickLocalized } from "@/lib/lms/localized";
import { useCourse } from "@/components/lms/CourseContext";
import { Button, ConfirmDialog } from "@/components/ui";
import { useErrorText } from "./useErrorText";

export function LeaveCourseLink() {
  const { lang, t } = useTranslation();
  const router = useRouter();
  const { course } = useCourse();
  const errorText = useErrorText();
  const [leaving, setLeaving] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  const leave = async () => {
    setBusy(true);
    setError(null);
    try {
      await leaveCourse(course.id);
      router.push(`/${lang}/courses`);
    } catch (e) {
      setError(e);
      setBusy(false);
    }
  };

  return (
    <>
      <div className="border-t border-slate-200 pt-4">
        <Button variant="link" className="text-slate-600 hover:text-danger-700" leftIcon={<LogOut aria-hidden="true" className="h-4 w-4" />} onClick={() => setLeaving(true)}>
          {t("courses.home.leave")}
        </Button>
      </div>
      <ConfirmDialog open={leaving} tone="danger" busy={busy} error={error ? errorText(error) : undefined}
        title={t("courses.home.leaveTitle")} object={pickLocalized(course.title, lang, course.default_language) || t("courses.list.untitled")}
        effect={t("courses.home.leaveBody")} confirmLabel={t("courses.home.leave")}
        onConfirm={() => void leave()} onCancel={() => setLeaving(false)} />
    </>
  );
}
