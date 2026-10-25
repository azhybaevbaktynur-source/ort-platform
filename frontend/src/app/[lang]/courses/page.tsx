"use client";

// Phase 6b S6b: /[lang]/courses is the student home (PHASE_6_DESIGN 8.4). People with a Teaching area keep the
// Teaching / Learning tabs; the Learning tab is the same home. The catalog moved to /courses/catalog
// (old links to /courses#catalog are redirected there).
import React, { Suspense, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { KeyRound, LayoutGrid, Plus, Trash2 } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { useAuth } from "@/lib/auth-context";
import { listMyCourses } from "@/lib/lms/courses";
import { useLmsMe } from "@/lib/lms/useLmsMe";
import type { CourseCard as CourseCardDto } from "@/lib/lms/types";
import { CourseCard } from "@/components/lms/CourseCard";
import { StudentHome } from "@/components/lms/home/StudentHome";
import { useErrorText } from "@/components/lms/home/useErrorText";
import {
  Badge, EmptyState, ErrorState, LinkButton, LoadingState, PageHeader, Pagination, TabPanel, Tabs, cn, focusRing,
} from "@/components/ui";

type Tab = "teaching" | "learning";

/** Phase 6b integration: the header's Teaching / Learning areas link to `?view=teaching|learning`. */
function ViewSync({ onView }: { onView: (v: Tab) => void }) {
  const view = useSearchParams().get("view");
  useEffect(() => {
    if (view === "teaching" || view === "learning") onView(view);
  }, [view, onView]);
  return null;
}
const TABS_ID = "my-courses";

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
      const page = await listMyCourses("teaching", next);
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
      {error && items.length === 0 ? <ErrorState message={errorText(error)} onRetry={() => void load()} retrying={loading} /> : null}
      {error && items.length > 0 ? <ErrorState variant="inline" message={errorText(error)} onRetry={() => void load(cursor)} /> : null}
      {loading && items.length === 0 && !error && <LoadingState rows={3} />}
      {!loading && !error && items.length === 0 && (
        <EmptyState title={t("courses.list.emptyTeaching")}
          action={me?.can_create_courses ? <LinkButton href={`/${lang}/courses/new`}>{t("courses.list.create")}</LinkButton> : undefined} />
      )}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {items.map((c) => <CourseCard key={c.id} course={c} />)}
      </div>
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
  const { me } = useLmsMe();
  const { userProfile } = useAuth();
  const [tab, setTab] = useState<Tab | null>(null);
  useCatalogHashRedirect();

  // UX F4 / Phase 6 S8 (UX S1): the Teaching / Learning tabs only for people who teach (MeOut.is_teacher) and
  // platform admins. Until MeOut loads, the cached profile decides (no flash for most users).
  const hasTeaching = me ? me.is_teacher || me.is_platform_admin
    : !!userProfile && (userProfile.teacher_status === "approved" || !!userProfile.is_platform_admin);

  // Phase 6b S11b (UX 15): `?view=` wins over the default (ViewSync may run before MeOut arrives), and switching
  // the tab updates `?view=` so the header area follows the tab.
  const router = useRouter();
  useEffect(() => {
    if (!me || tab !== null) return;
    const v = new URLSearchParams(window.location.search).get("view");
    setTab(v === "teaching" || v === "learning" ? v : me.is_teacher || me.can_create_courses ? "teaching" : "learning");
  }, [me, tab]);
  const changeTab = (v: Tab) => {
    setTab(v);
    router.replace(`/${lang}/courses?view=${v}`, { scroll: false });
  };

  if (!hasTeaching) return <StudentHome />;

  const current: Tab = tab ?? "teaching";
  const teaching = current === "teaching";
  return (
    <div>
      <PageHeader title={t("courses.list.title")}
        badge={me?.teacher_status === "pending" ? <Badge tone="warning">{t("courses.list.requestPending")}</Badge> : undefined}
        primaryAction={teaching && me?.can_create_courses
          ? <LinkButton href={`/${lang}/courses/new`} leftIcon={<Plus className="h-4 w-4" aria-hidden="true" />}>{t("courses.list.create")}</LinkButton>
          : undefined}
        secondaryActions={teaching
          ? <LinkButton variant="secondary" href={`/${lang}/courses/join`} leftIcon={<KeyRound className="h-4 w-4" aria-hidden="true" />}>{t("courses.list.join")}</LinkButton>
          : undefined}
      />
      <Suspense fallback={null}><ViewSync onView={setTab} /></Suspense>
      <Tabs id={TABS_ID} label={t("courses.list.title")} value={current} onChange={(v) => changeTab(v as Tab)} className="mb-6"
        items={[{ id: "teaching", label: t("courses.list.teaching") }, { id: "learning", label: t("courses.list.learning") }]} />
      <TabPanel tabsId={TABS_ID} value={current}>
        {teaching ? <TeachingList /> : <StudentHome embedded />}
      </TabPanel>
    </div>
  );
}
