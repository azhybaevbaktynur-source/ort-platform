"use client";

// Exam prep S2 (docs/ROADMAP_EXAM_PREP.md S2): "From the platform" on the student home: the platform's open courses the
// student is not in, as course cards with a one-tap join (the catalog's open join). After joining, the course opens.
import React, { useState } from "react";
import { useRouter } from "next/navigation";
import { useTranslation } from "@/lib/i18n/context";
import { joinOpenCourse } from "@/lib/lms/catalog";
import type { HomePlatformCourseOut } from "@/lib/lms/homeTypes";
import { Button, ErrorState } from "@/components/ui";
import { CourseCard } from "@/components/lms/course/CourseCard";
import { useErrorText } from "./useErrorText";

/** `joinVariant`: secondary where another card holds the page's primary button (Student UI U3 exam-prep home). */
export function PlatformCourses({ courses, grid, joinVariant = "primary" }: {
  courses: HomePlatformCourseOut[]; grid: string; joinVariant?: "primary" | "secondary";
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

  return (
    <section aria-labelledby="home-platform" className="min-w-0">
      <h2 id="home-platform" className="text-lg font-semibold leading-7 text-slate-900">{t("home.platform.title")}</h2>
      <p className="mb-3 text-sm leading-5 text-slate-600">{t("home.platform.subtitle")}</p>
      <ul className={grid}>
        {courses.map((c) => (
          <CourseCard key={c.id} course={c} href={`/${lang}/courses/catalog/${c.id}`}
            action={(
              <>
                <Button fullWidth variant={joinVariant} loading={joining === c.id} disabled={joining !== null && joining !== c.id}
                  onClick={() => void join(c.id)}>
                  {t("catalog.join")}
                </Button>
                {error?.id === c.id && <ErrorState variant="inline" message={errorText(error.error)} className="mt-3" />}
              </>
            )} />
        ))}
      </ul>
    </section>
  );
}
