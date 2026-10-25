"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { KeyRound, Plus, Trash2 } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { listMyCourses } from "@/lib/lms/courses";
import { useLmsMe } from "@/lib/lms/useLmsMe";
import type { CourseCard as CourseCardDto } from "@/lib/lms/types";
import { CatalogSection } from "@/components/lms/CatalogSection";
import { CourseCard } from "@/components/lms/CourseCard";
import { ErrorMessage } from "@/components/lms/ErrorMessage";
import { JoinDialog } from "@/components/lms/JoinDialog";
import { Pager } from "@/components/lms/Pager";

type Tab = "teaching" | "learning";

export default function CoursesPage() {
  const { lang, t } = useTranslation();
  const router = useRouter();
  const { me } = useLmsMe();
  const [tab, setTab] = useState<Tab | null>(null);
  const [items, setItems] = useState<CourseCardDto[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [joinOpen, setJoinOpen] = useState(false);
  // UX F4: the Teaching / Learning tabs only for people who teach (can create courses, or staff in some course).
  // Others get one plain list; one teaching probe (limit 1) decides for users without the create permission.
  const [hasTeaching, setHasTeaching] = useState<boolean | null>(null);
  useEffect(() => {
    if (!me) return;
    if (me.can_create_courses || me.is_platform_admin) {
      setHasTeaching(true);
      return;
    }
    let alive = true;
    listMyCourses("teaching", null, 1)
      .then((page) => { if (alive) setHasTeaching(page.items.length > 0); })
      .catch(() => { if (alive) setHasTeaching(false); });
    return () => { alive = false; };
  }, [me]);

  // Default tab: teachers start on Teaching, everyone else on Learning.
  useEffect(() => {
    if (me && tab === null) setTab(me.can_create_courses ? "teaching" : "learning");
  }, [me, tab]);

  const load = useCallback(async (which: Tab, next?: string | null) => {
    setLoading(true);
    setError(null);
    try {
      const page = await listMyCourses(which, next);
      setItems((prev) => (next ? [...prev, ...page.items] : page.items));
      setCursor(page.next_cursor);
    } catch (e) {
      setError(e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (tab) {
      setItems([]);
      setCursor(null);
      void load(tab);
    }
  }, [tab, load]);

  const tabBtn = (id: Tab, label: string) => (
    <button type="button" role="tab" aria-selected={tab === id} onClick={() => setTab(id)}
      className={`-mb-px border-b-2 px-4 py-2.5 text-sm font-semibold ${tab === id ? "border-brand-600 text-brand-700" : "border-transparent text-slate-500 hover:text-slate-800"}`}>
      {label}
    </button>
  );

  return (
    <div>
      <CatalogSection onJoined={() => tab && load(tab)} />
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-bold text-slate-900">{t("courses.list.title")}</h1>
        <div className="flex flex-wrap items-center gap-2">
          {me?.teacher_status === "pending" && (
            <span className="rounded-full bg-amber-100 px-3 py-1 text-xs font-semibold text-amber-800">{t("courses.list.requestPending")}</span>
          )}
          <button type="button" onClick={() => setJoinOpen(true)}
            className="inline-flex items-center gap-1.5 rounded-xl border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50">
            <KeyRound className="h-4 w-4" aria-hidden="true" />{t("courses.list.join")}
          </button>
          {me?.can_create_courses && (
            <Link href={`/${lang}/courses/new`} className="inline-flex items-center gap-1.5 rounded-xl bg-brand-600 px-4 py-2 text-sm font-semibold text-white hover:bg-brand-700">
              <Plus className="h-4 w-4" aria-hidden="true" />{t("courses.list.create")}
            </Link>
          )}
        </div>
      </div>

      {/* UX F4: no "become a teacher" card here; the header's "I am a teacher" link leads to /teacher-access. */}
      {hasTeaching && (
        <div role="tablist" aria-label={t("courses.list.title")} className="mb-5 flex items-center border-b border-slate-200">
          {tabBtn("teaching", t("courses.list.teaching"))}
          {tabBtn("learning", t("courses.list.learning"))}
          {me?.can_create_courses && (
            <Link href={`/${lang}/courses/trash`} className="ml-auto inline-flex items-center gap-1.5 px-3 py-2 text-sm text-slate-500 hover:text-slate-800">
              <Trash2 className="h-4 w-4" aria-hidden="true" />{t("courses.list.trash")}
            </Link>
          )}
        </div>
      )}

      {error ? <ErrorMessage error={error} onRetry={() => tab && load(tab)} /> : null}
      {loading && items.length === 0 && !error && <p role="status" className="text-sm text-slate-500">{t("lms.common.loading")}</p>}
      {!loading && !error && items.length === 0 && (
        <p className="rounded-2xl border border-dashed border-slate-300 p-8 text-center text-sm text-slate-500">
          {tab === "teaching" ? t("courses.list.emptyTeaching") : t("courses.list.emptyLearning")}
        </p>
      )}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {items.map((c) => <CourseCard key={c.id} course={c} />)}
      </div>
      <Pager nextCursor={cursor} loading={loading} onMore={() => tab && load(tab, cursor)} />

      <JoinDialog open={joinOpen} onClose={() => setJoinOpen(false)} onJoined={(r) => router.push(`/${lang}/courses/${r.course.id}`)} />
    </div>
  );
}
