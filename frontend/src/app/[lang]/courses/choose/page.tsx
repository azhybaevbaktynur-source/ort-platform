"use client";

// Step 3a S7 (STUDENT_IA_DESIGN V3, V14, V15): the choose step is gone; the catalog is the one way to add a course. Old
// links still work: a person who learns goes to `/courses/catalog` (`?first=1`, after sign-up, → `?welcome=1`; other
// queries dropped); people who teach to their Teaching list (they never join as students); Student view's test student,
// who has no catalog, to the hub.
import React, { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useTranslation } from "@/lib/i18n/context";
import { useAuth } from "@/lib/auth-context";
import { useLmsMe } from "@/lib/lms/useLmsMe";
import { useCachedMe } from "@/lib/lms/meCache";
import { teaches } from "@/lib/lms/shellKind";
import { LoadingState } from "@/components/ui";

export default function CoursesChoosePage() {
  const { lang, t } = useTranslation();
  const router = useRouter();
  const { me: fresh } = useLmsMe();
  const cachedMe = useCachedMe();
  const me = fresh ?? cachedMe;
  const { userProfile } = useAuth();
  const known = !!me && !!userProfile;
  const hasTeaching = !!me && teaches(me);
  const testStudent = !!userProfile?.is_test_student;
  useEffect(() => {
    if (!known) return;
    if (hasTeaching) { router.replace(`/${lang}/courses`); return; }
    if (testStudent) { router.replace(`/${lang}/home`); return; }
    const first = new URLSearchParams(window.location.search).get("first") === "1";
    router.replace(`/${lang}/courses/catalog${first ? "?welcome=1" : ""}`);
  }, [known, hasTeaching, testStudent, lang, router]);
  return <LoadingState label={t("lms.common.loading")} />;
}
