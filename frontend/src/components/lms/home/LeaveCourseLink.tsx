"use client";

// The student's quiet "Leave course" at the bottom of a course home (today's home and the modules view), and its
// confirm dialog (Student UI U9: an exam-prep course is left from the student shell's exam sheet).
import React, { useState } from "react";
import { useRouter } from "next/navigation";
import { LogOut } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { useAuth } from "@/lib/auth-context";
import { leaveCourse } from "@/lib/lms/courses";
import { pickLocalized } from "@/lib/lms/localized";
import { useCourse } from "@/components/lms/CourseContext";
import { Button, ConfirmDialog } from "@/components/ui";
import { useErrorText } from "./useErrorText";

/** The confirm dialog of leaving a course; usable outside a course page. `onLeft` runs after the server answered
 * (default: to the home). */
export function LeaveCourseDialog({ courseId, courseTitle, open, onCancel, onLeft }: {
  courseId: string; courseTitle: string; open: boolean; onCancel: () => void; onLeft?: () => void;
}) {
  const { lang, t } = useTranslation();
  const router = useRouter();
  const errorText = useErrorText();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  const leave = async () => {
    setBusy(true);
    setError(null);
    try {
      await leaveCourse(courseId);
      setBusy(false);
      if (onLeft) onLeft();
      else router.push(`/${lang}/home`); // step 3a S7: the hub (no learner /courses page)
    } catch (e) {
      setError(e);
      setBusy(false);
    }
  };

  return (
    <ConfirmDialog open={open} tone="danger" busy={busy} error={error ? errorText(error) : undefined}
      title={t("courses.home.leaveTitle")} object={courseTitle}
      effect={t("courses.home.leaveBody")} confirmLabel={t("courses.home.leave")}
      onConfirm={() => void leave()} onCancel={() => { setError(null); onCancel(); }} />
  );
}

export function LeaveCourseLink() {
  const { lang, t } = useTranslation();
  const { course } = useCourse();
  const { userProfile } = useAuth();
  const [leaving, setLeaving] = useState(false);

  if (userProfile?.is_test_student) return null; // Student view: the test student cannot leave

  return (
    <>
      <div className="border-t border-slate-200 pt-4">
        <Button variant="link" className="text-slate-600 hover:text-danger-700" leftIcon={<LogOut aria-hidden="true" className="h-4 w-4" />} onClick={() => setLeaving(true)}>
          {t("courses.home.leave")}
        </Button>
      </div>
      <LeaveCourseDialog courseId={course.id} open={leaving} onCancel={() => setLeaving(false)}
        courseTitle={pickLocalized(course.title, lang, course.default_language) || t("courses.list.untitled")} />
    </>
  );
}
