"use client";

// Phase 6b S6b: /[lang]/courses was the student home (PHASE_6_DESIGN 8.4). Owner decision 2026-11-12 (fix round 1e):
// student and teacher are separate accounts, so for everyone who teaches it is the Teaching list only (no Learning, no
// tabs, no "Join with code", whatever student enrolments the account still has); each course card enters Student view.
// Step 3a S7 (STUDENT_IA_DESIGN v3 V1, V2, V15): no learner «Мои курсы» page any more (the hub `/home` shows the
// courses, the sidebar lists them): for people who learn /courses redirects to /home (`#ort`, `#nct`, `#other` ->
// /home#courses; every query dropped, `?view=learning` included). For people who teach it stays the Teaching list (any
// old `?view=` dropped). /courses#catalog -> /courses/catalog for everyone.
import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Plus, Trash2 } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { listMyCourses } from "@/lib/lms/courses";
import { loadTeachingCourses } from "@/lib/lms/pageData";
import { useLmsMe } from "@/lib/lms/useLmsMe";
import { useCachedMe } from "@/lib/lms/meCache"; // PERFORMANCE_AUDIT S1
import { teaches } from "@/lib/lms/shellKind";
import type { CourseCard as CourseCardDto, MeOut } from "@/lib/lms/types";
import { COURSE_GRID, CourseCard, StatusBadge } from "@/components/lms/course/CourseCard";
import { TeacherApplicationNotice } from "@/components/lms/home/TeacherApplicationNotice";
import { useErrorText } from "@/components/lms/home/useErrorText";
import {
  Badge, EmptyState, ErrorState, LinkButton, LoadingState, PageHeader, Pagination, cn, focusRing,
} from "@/components/ui";

/** Old hub-group anchors of the removed «Мои курсы» page (S3): they all lead to the hub's «Мои курсы» section. */
const GROUP_HASHES = new Set(["#ort", "#nct", "#other", "#courses"]);

/** Step 3a S7 (V1, V15): where /courses leads a person who learns: the hub, its course section, or the catalog. */
function learnerCoursesTarget(lang: string, hash: string): string {
  if (hash === "#catalog") return `/${lang}/courses/catalog`;
  return GROUP_HASHES.has(hash) ? `/${lang}/home#courses` : `/${lang}/home`;
}

/** A person who learns: /courses is only a way to the hub (replace, so Back does not bounce). */
function ToHub() {
  const { lang, t } = useTranslation();
  const router = useRouter();
  useEffect(() => {
    router.replace(learnerCoursesTarget(lang, window.location.hash));
  }, [lang, router]);
  return <LoadingState label={t("lms.common.loading")} />;
}

/**
 * Step 3a S3 (§3.7): old links on the Teaching list: any `?view=` is dropped (the rest of the query kept); `#catalog`
 * opens the catalog page.
 */
function useLegacyRedirects() {
  const { lang } = useTranslation();
  const router = useRouter();
  useEffect(() => {
    const check = () => {
      if (window.location.hash === "#catalog") { router.replace(`/${lang}/courses/catalog`); return; }
      const params = new URLSearchParams(window.location.search);
      if (params.get("view") === null) return;
      params.delete("view");
      const qs = params.toString();
      router.replace(`/${lang}/courses${qs ? `?${qs}` : ""}${window.location.hash}`, { scroll: false });
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
            // owner 2026-11-12: the whole card opens the course; Student view lives only on the course page
            <CourseCard key={c.id} course={c} href={`/${lang}/courses/${c.id}`}
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
      {/* step 3b S2 (CATALOG_AND_TEACHERS_DESIGN 2.5): no catalog link here; the course settings link to the preview */}
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
  const { t } = useTranslation();
  const { me: fresh } = useLmsMe();
  const cachedMe = useCachedMe();
  const me = fresh ?? cachedMe; // PERFORMANCE_AUDIT S1: the cached answer first

  // UX F4 / Phase 6 S8 (UX S1): the Teaching list for people who teach (the same rule as the shell's areas); S7 (V2):
  // until `me` (fresh or cached) is known, the neutral loading state, as /home shows for teachers
  if (!me) return <LoadingState label={t("lms.common.loading")} />;
  if (!teaches(me)) return <ToHub />;
  return <TeachingPage me={me} />;
}

function TeachingPage({ me }: { me: MeOut }) {
  const { lang, t } = useTranslation();
  useLegacyRedirects();

  return (
    <div>
      <PageHeader title={t("courses.list.title")}
        badge={me.teacher_status === "pending" ? <Badge tone="warning">{t("courses.list.requestPending")}</Badge> : undefined}
        primaryAction={me.can_create_courses
          ? <LinkButton href={`/${lang}/courses/new`} leftIcon={<Plus className="h-4 w-4" aria-hidden="true" />}>{t("courses.list.create")}</LinkButton>
          : undefined}
      />
      <TeachingList />
    </div>
  );
}
