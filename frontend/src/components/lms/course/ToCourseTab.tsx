"use client";

// Step 3a S2 (docs/phases/STUDENT_IA_DESIGN.md §3.7): an old student URL of a course leads to its new place (client-side,
// replace; the query is kept, and the fragment unless the target names its own). Students only: staff keep their pages.
import React, { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useTranslation } from "@/lib/i18n/context";
import { LoadingState } from "@/components/ui";

/** `path`: relative to the course (`""` = Обзор, `/lessons`, `/tests#practice`, …); `query`: false drops the query. */
export function ToCourseTab({ courseId, path, query = true }: { courseId: string; path: string; query?: boolean }) {
  const { lang, t } = useTranslation();
  const router = useRouter();
  useEffect(() => {
    const [p, own] = path.split("#", 2);
    const search = query ? window.location.search : "";
    const hash = own !== undefined ? `#${own}` : window.location.hash;
    router.replace(`/${lang}/courses/${courseId}${p}${search}${hash}`);
  }, [router, lang, courseId, path, query]);
  return <LoadingState label={t("lms.common.loading")} />;
}
