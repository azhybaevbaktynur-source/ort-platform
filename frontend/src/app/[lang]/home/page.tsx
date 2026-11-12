"use client";

// Step 3a S3 (STUDENT_IA_DESIGN §2.2, decision D1): Главная `/home` is the hub of people who learn (and of the test
// student in Student view). A person who teaches never gets a student page: `/home` takes them to the Teaching list
// (`/courses`; the shell already draws the app frame for them, `urlAreaFor`).
import React, { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useTranslation } from "@/lib/i18n/context";
import { useAuth } from "@/lib/auth-context";
import { useLmsMe } from "@/lib/lms/useLmsMe";
import { useCachedMe } from "@/lib/lms/meCache";
import { teaches } from "@/lib/lms/shellKind";
import { LoadingState } from "@/components/ui";
import { StudentHub } from "@/components/lms/home/StudentHub";

export default function HomePage() {
  const { lang, t } = useTranslation();
  const router = useRouter();
  const { me: fresh } = useLmsMe();
  const cachedMe = useCachedMe();
  const me = fresh ?? cachedMe;
  const { userProfile } = useAuth();
  const hasTeaching = me ? teaches(me)
    : !!userProfile && (userProfile.teacher_status === "approved" || !!userProfile.is_platform_admin);
  useEffect(() => {
    if (hasTeaching) router.replace(`/${lang}/courses`);
  }, [hasTeaching, lang, router]);
  if (hasTeaching) return <LoadingState label={t("lms.common.loading")} />;
  return <StudentHub />;
}
