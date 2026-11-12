"use client";

// Phase 6b S6b: /[lang]/courses is the student home (PHASE_6_DESIGN 8.4). Owner decision 2026-11-12 (fix round 1e):
// student and teacher are separate accounts, so for everyone who teaches it is the Teaching list only (no Learning, no
// tabs, no "Join with code", whatever student enrolments the account still has); each course card enters Student view.
// The catalog moved to /courses/catalog (old links to /courses#catalog are redirected there).
import React, { Suspense, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { LayoutGrid, Plus, Trash2 } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { useAuth } from "@/lib/auth-context";
import { listMyCourses } from "@/lib/lms/courses";
import { loadTeachingCourses } from "@/lib/lms/pageData";
import { useLmsMe } from "@/lib/lms/useLmsMe";
import { useCachedMe } from "@/lib/lms/meCache"; // PERFORMANCE_AUDIT S1
import { hidesLearning, teaches } from "@/lib/lms/shellKind";
import type { CourseCard as CourseCardDto } from "@/lib/lms/types";
import { COURSE_GRID, CourseCard, StatusBadge } from "@/components/lms/course/CourseCard";
import { StudentViewButton } from "@/components/lms/course/StudentViewBanner";
import { StudentHome } from "@/components/lms/home/StudentHome";
import { TeacherApplicationNotice } from "@/components/lms/home/TeacherApplicationNotice";
import { useErrorText } from "@/components/lms/home/useErrorText";
import {
  Badge, EmptyState, ErrorState, LinkButton, LoadingState, PageHeader, Pagination, cn, focusRing,
} from "@/components/ui";

/** Phase 6b integration: the header links to `?view=teaching`; without Learning, `?view=learning` opens Teaching. */
function ViewSync({ noLearning }: { noLearning: boolean }) {
  const view = useSearchParams().get("view");
  const { lang } = useTranslation();
  const router = useRouter();
  useEffect(() => { // owner feedback 2026-11-08 (item 2), decision 2026-11-12 (1e)
    if (noLearning && view === "learning") router.replace(`/${lang}/courses?view=teaching`, { scroll: false });
  }, [noLearning, view, lang, router]);
  return null;
}

/** Old anchor links (`/courses#catalog`, e.g. in the header) open the catalog page. */
function useCatalogHashRedirect() {
  const { lang } = useTranslation();
  const router = useRouter();
  useEffect(() => {
    const check = () => {
      if (window.location.hash === "#catalog") router.replace(`/${lang}/courses/catalog`);
    };
    check();
    window.addEventListener("hashchange", check);
    return () => window.removeEventListener("hashchange", check);
  }, [lang, router]);
}

function TeachingList() {
  const { lang, t } = useTranslation();
  const errorText = useErrorText();
  const [items, setItems] = useState<CourseCardDto[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const { me } = useLmsMe();

  const load = useCallback(async (next?: string | null) => {
    setLoading(true);
    setError(null);
    try {
      const page = next ? await listMyCourses("teaching", next) : await loadTeachingCourses(); // header prefetch
      setItems((prev) => (next ? [...prev, ...page.items] : page.items));
      setCursor(page.next_cursor);
    } catch (e) {
      setError(e);
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => { void load(); }, [load]);

  return (
    <div className="space-y-4">
      {/* Accounts: a revoked teacher keeps this list, read-only. Fix round 2026-11-12 1e: otherwise the application line
          of everyone who teaches shows here only (StudentHome leaves it out for them) */}
      {me?.teacher_status === "revoked"
        ? <TeacherApplicationNotice application={{ status: "revoked" }} dismissible={false} />
        : me?.teacher_application && <TeacherApplicationNotice application={me.teacher_application} />}
      {error && items.length === 0 ? <ErrorState message={errorText(error)} onRetry={() => void load()} retrying={loading} /> : null}
      {error && items.length > 0 ? <ErrorState variant="inline" message={errorText(error)} onRetry={() => void load(cursor)} /> : null}
      {loading && items.length === 0 && !error && <LoadingState rows={3} />}
      {!loading && !error && items.length === 0 && (
        <EmptyState mascot="working" title={t("courses.list.emptyTeaching")}
          action={me?.can_create_courses ? <LinkButton href={`/${lang}/courses/new`}>{t("courses.list.create")}</LinkButton> : undefined} />
      )}
      {items.length > 0 && (
        <ul className={COURSE_GRID}>
          {items.map((c) => (
            <CourseCard key={c.id} course={c} href={`/${lang}/courses/${c.id}`}
              // fix round 2026-11-12 1e: see the course as a student (the server decides; staff enrolments only)
              action={c.my_role === "teacher" || c.my_role === "assistant" ? <StudentViewButton courseId={c.id} /> : undefined}
              badges={(
                <>
                  <StatusBadge status={c.status} />
                  {c.my_role && <span className="text-xs font-medium text-slate-600">{t(`courses.roles.${c.my_role}`)}</span>}
                </>
              )} />
          ))}
        </ul>
      )}
      <Pagination nextCursor={cursor} loading={loading} onLoadMore={() => void load(cursor)} />
      {/* --- Phase 6b S5c (UX T13): course creators reach the catalog after their own list, not above it --- */}
      {me?.can_create_courses && (
        <Link href={`/${lang}/courses/catalog`}
          className={cn("mr-6 inline-flex min-h-11 items-center gap-1.5 rounded text-sm font-medium text-brand-700 hover:underline sm:min-h-0", focusRing)}>
          <LayoutGrid className="h-4 w-4" aria-hidden="true" />{t("teaching.showCatalog")}
        </Link>
      )}
      {/* --- Phase 6b S5c end --- */}
      {me?.can_create_courses && (
        <Link href={`/${lang}/courses/trash`}
          className={cn("inline-flex min-h-11 items-center gap-1.5 rounded text-sm font-medium text-slate-600 hover:text-slate-900 sm:min-h-0", focusRing)}>
          <Trash2 className="h-4 w-4" aria-hidden="true" />{t("courses.list.trash")}
        </Link>
      )}
    </div>
  );
}

export default function CoursesPage() {
  const { lang, t } = useTranslation();
  const { me: fresh } = useLmsMe();
  const cachedMe = useCachedMe();
  const me = fresh ?? cachedMe; // PERFORMANCE_AUDIT S1: the cached answer first, the profile only as a fallback
  const { userProfile } = useAuth();
  useCatalogHashRedirect();

  // UX F4 / Phase 6 S8 (UX S1): the Teaching list for people who teach (the same rule as the shell's areas). Until
  // MeOut loads (and nothing is cached), the cached profile decides.
  const hasTeaching = me ? teaches(me)
    : !!userProfile && (userProfile.teacher_status === "approved" || !!userProfile.is_platform_admin);
  if (!hasTeaching) return <StudentHome />;

  return (
    <div>
      <Suspense fallback={null}><ViewSync noLearning={hidesLearning(me)} /></Suspense>
      <PageHeader title={t("courses.list.title")}
        badge={me?.teacher_status === "pending" ? <Badge tone="warning">{t("courses.list.requestPending")}</Badge> : undefined}
        primaryAction={me?.can_create_courses
          ? <LinkButton href={`/${lang}/courses/new`} leftIcon={<Plus className="h-4 w-4" aria-hidden="true" />}>{t("courses.list.create")}</LinkButton>
          : undefined}
      />
      <TeachingList />
    </div>
  );
}
