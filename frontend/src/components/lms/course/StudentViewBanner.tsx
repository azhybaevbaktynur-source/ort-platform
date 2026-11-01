"use client";

// UX rework S1 (UX_REWORK_DESIGN F): the Student view banner on every page of the frame while this tab is the course's
// test student, and the button that starts the mode. The session lives in `lib/api.ts`; entering, resetting and leaving
// load the course page again, so nothing from the other identity stays in memory.
import React, { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import { Eye } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { enterStudentView, getStudentView, leaveStudentView, resetStudentView } from "@/lib/api";
import { lmsErrorKey } from "@/components/lms/ErrorMessage";
import { Button, ConfirmDialog, toast } from "@/components/ui";

function useErrorToast() {
  const { t } = useTranslation();
  return (e: unknown) => { toast.error(t(lmsErrorKey((e as { code?: string })?.code))); };
}

export function StudentViewBanner() {
  const { t } = useTranslation();
  const showError = useErrorToast();
  const pathname = usePathname() || "";
  const [active, setActive] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  useEffect(() => { setActive(!!getStudentView()); }, []);
  if (!active) return null;

  const reset = async () => {
    setBusy(true);
    try {
      await resetStudentView(); // loads the course page again
    } catch (e) {
      setBusy(false);
      setConfirming(false);
      showError(e);
    }
  };
  // Player, result and review pages have sticky parts of their own at the top, so the banner scrolls away there
  const sticky = pathname.includes("/attempts/") ? "" : "sticky top-0";

  return (
    <div role="status" data-testid="student-view-banner"
      className={`${sticky} z-30 border-b border-warning-200 bg-warning-50 text-warning-900`}>
      <div className="mx-auto flex w-full max-w-[1600px] flex-wrap items-center gap-x-3 gap-y-1.5 px-4 py-2 text-sm leading-6 sm:px-6 lg:px-8">
        <Eye aria-hidden="true" className="h-4 w-4 shrink-0" />
        <p className="min-w-0 flex-1 basis-[calc(100%-1.75rem)] font-medium sm:basis-auto">{t("studentView.banner")}</p>
        <div className="flex w-full flex-wrap gap-2 sm:w-auto">
          {/* phones: short labels, so the banner stays two rows */}
          <Button size="sm" variant="secondary" className="min-w-0 flex-1 sm:flex-none" onClick={() => setConfirming(true)}>
            <span className="sm:hidden">{t("studentView.resetShort")}</span>
            <span className="hidden sm:inline">{t("studentView.reset")}</span>
          </Button>
          <Button size="sm" variant="secondary" className="min-w-0 flex-1 sm:flex-none" onClick={() => leaveStudentView()}>
            <span className="sm:hidden">{t("studentView.leaveShort")}</span>
            <span className="hidden sm:inline">{t("studentView.leave")}</span>
          </Button>
        </div>
      </div>
      <ConfirmDialog open={confirming} onCancel={() => setConfirming(false)} onConfirm={() => void reset()} busy={busy}
        title={t("studentView.resetTitle")} effect={t("studentView.resetBody")} confirmLabel={t("studentView.reset")} />
    </div>
  );
}

/** "Student view" (a real teacher or assistant enrollment; the server decides, the caller hides it otherwise). */
export function StudentViewButton({ courseId }: { courseId: string }) {
  const { t } = useTranslation();
  const showError = useErrorToast();
  const [busy, setBusy] = useState(false);
  const start = async () => {
    setBusy(true);
    try {
      await enterStudentView(courseId); // loads the course page as the test student
    } catch (e) {
      setBusy(false);
      showError(e);
    }
  };
  return (
    <Button size="sm" variant="secondary" leftIcon={<Eye aria-hidden="true" />} loading={busy} onClick={() => void start()}>
      {t("studentView.button")}
    </Button>
  );
}
