"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useTranslation } from "@/lib/i18n/context";

/** Old route (Phase 1): the teacher request now lives on /teacher-access (Phase 6 §7). */
export default function BecomeTeacherRedirect() {
  const { lang, t } = useTranslation();
  const router = useRouter();
  useEffect(() => { router.replace(`/${lang}/teacher-access`); }, [lang, router]);
  return <p role="status" className="text-sm text-slate-500">{t("lms.common.loading")}</p>;
}
