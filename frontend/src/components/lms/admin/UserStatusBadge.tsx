"use client";

import React from "react";
import { useTranslation } from "@/lib/i18n/context";
import type { TeacherStatus } from "@/lib/lms/types";

const COLORS: Record<string, string> = {
  none: "bg-slate-100 text-slate-600",
  pending: "bg-amber-100 text-amber-800",
  approved: "bg-emerald-100 text-emerald-800",
  revoked: "bg-red-100 text-red-800",
  disabled: "bg-red-100 text-red-800",
  admin: "bg-indigo-100 text-indigo-800",
};

export function UserStatusBadge({ kind, status }: { kind: "teacher" | "account"; status: TeacherStatus | "disabled" | "admin" }) {
  const { t } = useTranslation();
  const label = kind === "teacher" ? t(`platformAdmin.teacherStatus.${status}`) : t(`platformAdmin.accountStatus.${status}`);
  return <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-semibold ${COLORS[status] || COLORS.none}`}>{label}</span>;
}
