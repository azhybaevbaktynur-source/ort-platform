"use client";

import React, { Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useTranslation } from "@/lib/i18n/context";
import { JoinCodeForm } from "@/components/lms/JoinCodeForm";

function JoinInner() {
  const { lang, t } = useTranslation();
  const router = useRouter();
  const params = useSearchParams();
  return (
    <div className="mx-auto max-w-md rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
      <h1 className="mb-4 text-xl font-bold text-slate-900">{t("courses.join.title")}</h1>
      <JoinCodeForm initialCode={params.get("code") || ""} onJoined={(r) => router.push(`/${lang}/courses/${r.course.id}`)} />
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
