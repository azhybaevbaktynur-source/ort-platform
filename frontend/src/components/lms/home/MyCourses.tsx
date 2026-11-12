"use client";

// Step 3a S3 (STUDENT_IA_DESIGN §2.3): «Мои курсы» `/courses` for people who learn: every active student course as a
// card, grouped ОРТ · НЦТ · Другие курсы (anchors `#ort`, `#nct`, `#other`; lesson courses attached to an exam in its
// group with «К экзамену: …»), paginated by `GET /me/home/courses`. Header: «Добавить курс» (the choose step) and the
// quiet «Войти по коду». The first page is drawn from the shell's cached course list while it loads.
import React, { useCallback, useEffect, useState } from "react";
import { KeyRound, Plus } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { useAuth } from "@/lib/auth-context";
import { listHomeCourses } from "@/lib/lms/home";
import { chooseCoursesHref } from "@/lib/lms/chooseCourses"; // until S4: the catalog
import type { HomeCourseOut } from "@/lib/lms/homeTypes";
import { LMS_ME_STALE_EVENT } from "@/lib/lms/meStale";
import { EmptyState, ErrorState, LinkButton, Pagination, Skeleton } from "@/components/ui";
import { StudentPageHeader } from "@/components/lms/student/StudentPageHeader";
import { useStudentShellDataContext } from "@/components/lms/student/StudentShellDataContext";
import { CourseGroups } from "./CourseGroups";
import { useErrorText } from "./useErrorText";

/** After the cards drew, follow `#ort` / `#nct` / `#other` from the hub's «Все курсы …» links. */
function useHashScroll(ready: boolean) {
  useEffect(() => {
    if (!ready) return;
    const id = window.location.hash.slice(1);
    if (!id) return;
    document.getElementById(id)?.scrollIntoView({ block: "start" });
  }, [ready]);
}

export function MyCourses() {
  const { lang, t } = useTranslation();
  const errorText = useErrorText();
  const shell = useStudentShellDataContext();
  const testStudent = !!useAuth().userProfile?.is_test_student; // Student view: no choose step, no code
  const [items, setItems] = useState<HomeCourseOut[] | null>(null);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);

  const load = useCallback(async (next?: string | null) => {
    setLoading(true);
    setError(null);
    try {
      const page = await listHomeCourses(next);
      setItems((prev) => (next && prev ? [...prev, ...page.items] : page.items));
      setCursor(page.next_cursor);
    } catch (e) {
      setError(e);
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => { void load(); }, [load]);
  useEffect(() => {
    const stale = () => { void load(); };
    window.addEventListener(LMS_ME_STALE_EVENT, stale);
    return () => window.removeEventListener(LMS_ME_STALE_EVENT, stale);
  }, [load]);

  const courses = items ?? (shell?.loaded ? shell.courses : null);
  useHashScroll(!!items);

  const actions = testStudent ? undefined : (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
      <LinkButton href={chooseCoursesHref(lang)} leftIcon={<Plus aria-hidden="true" className="h-4 w-4" />}>{t("courses.mine.addCourse")}</LinkButton>
      <LinkButton href={`/${lang}/courses/join`} variant="link" leftIcon={<KeyRound aria-hidden="true" className="h-4 w-4" />}>{t("courses.mine.join")}</LinkButton>
    </div>
  );

  return (
    <div className="w-full space-y-6">
      <StudentPageHeader title={t("courses.mine.title")} action={courses && courses.length > 0 ? actions : undefined} />
      {courses === null ? (
        error ? <ErrorState message={errorText(error)} onRetry={() => void load()} retrying={loading} /> : (
          <div aria-hidden="true" className="grid gap-4 grid-cols-[repeat(auto-fill,minmax(min(100%,256px),360px))]">
            {[0, 1, 2].map((i) => <Skeleton key={i} className="h-64 w-full rounded-2xl" />)}
          </div>
        )
      ) : courses.length === 0 && !loading ? (
        <EmptyState mascot="hello" title={t("home.hub.emptyTitle")} description={t("home.hub.emptyBody")}
          action={testStudent ? undefined : (
            <>
              <LinkButton size="lg" href={chooseCoursesHref(lang)}>{t("home.hub.choose")}</LinkButton>
              <LinkButton size="lg" variant="secondary" href={`/${lang}/courses/join`}>{t("home.hub.join")}</LinkButton>
            </>
          )} />
      ) : (
        <>
          <CourseGroups courses={courses} level={2} />
          {error && items ? <ErrorState variant="inline" message={errorText(error)} onRetry={() => void load(cursor)} /> : null}
          {items && <Pagination nextCursor={cursor} loading={loading} onLoadMore={() => void load(cursor)} />}
        </>
      )}
    </div>
  );
}
