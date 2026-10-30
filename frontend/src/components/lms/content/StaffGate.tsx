"use client";

import React, { useEffect, useState } from "react";
import { useTranslation } from "@/lib/i18n/context";
import { listBanks } from "@/lib/lms/content";
import type { BankOut } from "@/lib/lms/contentTypes";
import { useTemplateUi } from "@/lib/lms/templates";
import { useCourse } from "@/components/lms/CourseContext";
import { LoadingState } from "@/components/ui";

function NotAuthorized() {
  const { t } = useTranslation();
  return <p role="alert" className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">{t("bank.notAuthorized")}</p>;
}

/** Question bank is for course teachers and assistants only (the server enforces it too). */
export function StaffGate({ children }: { children: React.ReactNode }) {
  const { course } = useCourse();
  const role = course.my_enrollment.role;
  if (role !== "teacher" && role !== "assistant") return <NotAuthorized />;
  return <>{children}</>;
}

// --- Phase 9 S2 begin --- (PHASE_9_DESIGN 4.2: org admins edit organization-shared banks in their home course)
/**
 * The bank area's gate: course staff as before; an org admin (read-only observer of the course) enters only when
 * the server lists at least one bank of the course for them (it lists exactly the organization-shared banks
 * `can_edit_bank` allows, else refuses). Never in ORT courses (ORT stays as it is).
 */
export function BankGate({ children }: { children: React.ReactNode }) {
  const { course } = useCourse();
  const isOrt = useTemplateUi().key === "ort";
  const role = course.my_enrollment.role;
  const staff = role === "teacher" || role === "assistant";
  const observer = !staff && !!course.my_enrollment.read_only && !isOrt;
  const [allowed, setAllowed] = useState<boolean | null>(null);
  useEffect(() => {
    if (!observer) return;
    let alive = true;
    listBanks(course.id, { limit: 1, kind: "all" })
      .then((page) => { if (alive) setAllowed(page.items.length > 0); })
      .catch(() => { if (alive) setAllowed(false); });
    return () => { alive = false; };
  }, [observer, course.id]);
  if (staff) return <>{children}</>;
  if (!observer) return <NotAuthorized />;
  if (allowed === null) return <LoadingState rows={2} />;
  return allowed ? <>{children}</> : <NotAuthorized />;
}

/**
 * Edit controls of one bank's content (questions, passages, rename): the server's `bank.can_edit` once the bank is
 * loaded (course staff, or an org admin on an organization-shared bank); before that, the staff role. Concluded
 * courses are read-only.
 */
export function useCanEditBank(bank: Pick<BankOut, "can_edit"> | null | undefined): boolean {
  const { course } = useCourse();
  const role = course.my_enrollment.role;
  if (course.status === "concluded") return false;
  return bank ? !!bank.can_edit : role === "teacher" || role === "assistant";
}
// --- Phase 9 S2 end ---

/** Concluded courses are read-only for content (server returns the status gate error). */
export function useCanEditContent(): boolean {
  const { course } = useCourse();
  return course.status !== "concluded" && (course.my_enrollment.role === "teacher" || course.my_enrollment.role === "assistant");
}
