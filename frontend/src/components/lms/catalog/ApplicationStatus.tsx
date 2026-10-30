"use client";

// Phase 9 S4: application status pieces shared by the student home, the catalog, the landing and the staff inbox
// (PHASE_9_DESIGN 4.9, 8.1). Never renders answers.
import React from "react";
import { Clock } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { pickLocalized } from "@/lib/lms/localized";
import type { HomePendingApplicationOut } from "@/lib/lms/homeTypes";
import type { ApplicationStatus } from "@/lib/lms/types";
import { Badge, type BadgeTone } from "@/components/ui";
import { HomeRow, HomeSection } from "@/components/lms/home/HomeRow";
import { fmtShortDateTime } from "@/components/lms/home/format";

const TONE: Record<ApplicationStatus, BadgeTone> = {
  pending: "warning",
  approved: "success",
  rejected: "danger",
  withdrawn: "neutral",
};

/** Status badge; `audience` picks the student wording ("Waiting for the teacher") or the staff one ("Pending"). */
export function ApplicationStatusBadge({ status, audience = "staff" }: { status: ApplicationStatus; audience?: "staff" | "student" }) {
  const { t } = useTranslation();
  return <Badge tone={TONE[status]}>{t(`applications.${audience === "student" ? "studentStatus" : "status"}.${status}`)}</Badge>;
}

/** Student home: "Pending applications" (at most three rows from `/me/home`; nothing when empty). */
export function PendingApplicationsLine({ items }: { items: HomePendingApplicationOut[] }) {
  const { lang, t } = useTranslation();
  if (!items.length) return null;
  return (
    <HomeSection id="home-pending-applications" title={t("applications.home.title")}>
      <ul className="divide-y divide-slate-100">
        {items.map((a) => (
          <HomeRow key={a.application_id} href={`/${lang}/courses/catalog/${a.course_id}`}
            title={pickLocalized(a.course_title, lang) || t("courses.list.untitled")}
            meta={(
              <span className="inline-flex items-center gap-1">
                <Clock className="h-4 w-4" aria-hidden="true" />
                {t("applications.home.sent", { date: fmtShortDateTime(a.submitted_at, lang) })}
              </span>
            )}
            aside={<ApplicationStatusBadge status="pending" audience="student" />} />
        ))}
      </ul>
    </HomeSection>
  );
}
