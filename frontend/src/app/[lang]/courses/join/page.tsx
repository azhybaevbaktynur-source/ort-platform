"use client";

import React, { Suspense } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { LayoutGrid } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { JoinCodeForm } from "@/components/lms/JoinCodeForm";
import { Card, PageHeader, cn, focusRing } from "@/components/ui";

// Phase 6b S6b (UX S10): one name for the action ("Join with code"), and a way to the catalog for students
// without a code.
function JoinInner() {
  const { lang, t } = useTranslation();
  const router = useRouter();
  const params = useSearchParams();
  return (
    <div className="mx-auto w-full max-w-md">
      <PageHeader title={t("courses.join.title")}
        breadcrumbs={[{ label: t("lms.nav.myCourses"), href: `/${lang}/courses` }, { label: t("courses.join.title") }]} />
      <Card>
        <JoinCodeForm initialCode={params.get("code") || ""} onJoined={(r) => router.push(`/${lang}/courses/${r.course.id}`)} />
      </Card>
      <p className="mt-4 text-base leading-6 text-slate-600 sm:text-sm">
        {t("courses.join.noCode")}{" "}
        <Link href={`/${lang}/courses/catalog`}
          className={cn("inline-flex min-h-11 items-center gap-1 rounded font-semibold text-brand-700 hover:underline sm:min-h-0", focusRing)}>
          <LayoutGrid aria-hidden="true" className="h-4 w-4" />{t("home.openCatalog")}
        </Link>
      </p>
    </div>
  );
}

export default function JoinPage() {
  return (
    <Suspense fallback={null}>
      <JoinInner />
    </Suspense>
  );
}
