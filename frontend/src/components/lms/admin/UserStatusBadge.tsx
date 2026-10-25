"use client";

import React from "react";
import { useTranslation } from "@/lib/i18n/context";
import type { TeacherStatus } from "@/lib/lms/types";
import { Badge, type BadgeTone } from "@/components/ui";

const TONES: Record<string, BadgeTone> = {
  none: "neutral",
  pending: "warning",
  approved: "success",
  revoked: "danger",
  disabled: "danger",
  admin: "info",
};

export function UserStatusBadge({ kind, status }: { kind: "teacher" | "account"; status: TeacherStatus | "disabled" | "admin" }) {
  const { t } = useTranslation();
  const label = kind === "teacher" ? t(`platformAdmin.teacherStatus.${status}`) : t(`platformAdmin.accountStatus.${status}`);
  return <Badge tone={TONES[status] ?? "neutral"}>{label}</Badge>;
}
