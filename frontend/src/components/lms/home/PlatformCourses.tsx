"use client";

// Exam prep S2 (docs/ROADMAP_EXAM_PREP.md S2): "From the platform" on the student home: the platform's open courses the
// student is not in, as course cards with a one-tap join (the catalog's open join). After joining, the course opens.
// Student UI U9 (STUDENT_UI_REVIEW item 1): `compact` on the exam-prep home: slim cards (title, language, one
// secondary "Записаться"), no colour band.
import React, { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useTranslation } from "@/lib/i18n/context";
import { joinOpenCourse } from "@/lib/lms/catalog";
import type { HomePlatformCourseOut } from "@/lib/lms/homeTypes";
import { pickLocalized } from "@/lib/lms/localized";
import type { Lang } from "@/lib/lms/types";
import { Button, ErrorState, cn, focusRing } from "@/components/ui";
import { CourseCard } from "@/components/lms/course/CourseCard";
import { useErrorText } from "./useErrorText";

/** `joinVariant`: secondary where another card holds the page's primary button. */
export function PlatformCourses({ courses, grid = "", joinVariant = "primary", compact = false }: {
  courses: HomePlatformCourseOut[]; grid?: string; joinVariant?: "primary" | "secondary"; compact?: boolean;
}) {
  const { lang, t } = useTranslation();
  const router = useRouter();
  const errorText = useErrorText();
  const [joining, setJoining] = useState<string | null>(null);
  const [error, setError] = useState<{ id: string; error: unknown } | null>(null);
  if (courses.length === 0) return null;

  const join = async (id: string) => {
    setJoining(id);
    setError(null);
    try {
      const res = await joinOpenCourse(id);
      router.push(`/${lang}/courses/${res.course.id}`);
    } catch (e) {
      setError({ id, error: e });
      setJoining(null);
    }
  };
  const joinButton = (id: string, variant: "primary" | "secondary", fullWidth: boolean) => (
    <Button fullWidth={fullWidth} variant={variant} loading={joining === id} disabled={joining !== null && joining !== id}
      onClick={() => void join(id)}>
      {t("catalog.join")}
    </Button>
  );

  if (compact) {
    return (
      <section aria-labelledby="home-platform" className="min-w-0">
        <h2 id="home-platform" className="mb-2 text-lg font-semibold leading-7 text-slate-900">{t("home.platform.title")}</h2>
        <ul className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {courses.map((c) => {
            const title = pickLocalized(c.title, lang as Lang, c.default_language) || t("courses.list.untitled");
            const languages = c.languages.map((l) => t(`courses.languages.${l}`)).join(", ");
            return (
              <li key={c.id} className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-2 rounded-card border border-slate-200 bg-white px-4 py-3">
                <div className="min-w-0 flex-1">
                  <Link href={`/${lang}/courses/catalog/${c.id}`}
                    className={cn("break-words rounded text-base font-semibold leading-6 text-slate-900 hover:text-brand-700 hover:underline", focusRing)}>
                    {title}
                  </Link>
                  <p className="text-sm leading-5 text-slate-600">{languages}</p>
                </div>
                <div className="shrink-0">{joinButton(c.id, "secondary", false)}</div>
                {error?.id === c.id && <ErrorState variant="inline" message={errorText(error.error)} className="basis-full" />}
              </li>
            );
          })}
        </ul>
      </section>
    );
  }

  return (
    <section aria-labelledby="home-platform" className="min-w-0">
      <h2 id="home-platform" className="text-lg font-semibold leading-7 text-slate-900">{t("home.platform.title")}</h2>
      <p className="mb-3 text-sm leading-5 text-slate-600">{t("home.platform.subtitle")}</p>
      <ul className={grid}>
        {courses.map((c) => (
          <CourseCard key={c.id} course={c} href={`/${lang}/courses/catalog/${c.id}`}
            action={(
              <>
                {joinButton(c.id, joinVariant, true)}
                {error?.id === c.id && <ErrorState variant="inline" message={errorText(error.error)} className="mt-3" />}
              </>
            )} />
        ))}
      </ul>
    </section>
  );
}
