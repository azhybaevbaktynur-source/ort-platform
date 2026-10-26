"use client";

// Phase 7b S4: /exam-templates is for people who teach or create courses (and platform admins); the server scopes
// every list and action, this only avoids an empty page for students.
import React from "react";
import { LayoutTemplate } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { useLmsMe } from "@/lib/lms/useLmsMe";
import { EmptyState, LinkButton, LoadingState } from "@/components/ui";

export function TeacherTemplatesGate({ children }: { children: React.ReactNode }) {
  const { lang, t } = useTranslation();
  const { me, loading } = useLmsMe();
  if (loading && !me) return <LoadingState label={t("lms.common.loading")} />;
  if (me && !me.is_teacher && !me.can_create_courses && !me.is_platform_admin) {
    return (
      <EmptyState icon={<LayoutTemplate />} title={t("examTemplates.noAccess.title")} description={t("examTemplates.noAccess.body")}
        action={<LinkButton variant="secondary" href={`/${lang}/courses`}>{t("examTemplates.noAccess.back")}</LinkButton>} />
    );
  }
  return <>{children}</>;
}
