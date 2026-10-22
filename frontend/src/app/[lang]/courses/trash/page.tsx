"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useTranslation } from "@/lib/i18n/context";
import { listTrash, restoreCourse } from "@/lib/lms/courses";
import type { CourseCard as CourseCardDto } from "@/lib/lms/types";
import { CourseCard } from "@/components/lms/CourseCard";
import { ErrorMessage } from "@/components/lms/ErrorMessage";
import { Pager } from "@/components/lms/Pager";

export default function TrashPage() {
  const { lang, t } = useTranslation();
  const [items, setItems] = useState<CourseCardDto[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = useCallback(async (next?: string | null) => {
    setLoading(true);
    setError(null);
    try {
      const page = await listTrash(next);
      setItems((prev) => (next ? [...prev, ...page.items] : page.items));
      setCursor(page.next_cursor);
    } catch (e) {
      setError(e);
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => { void load(); }, [load]);

  const restore = async (id: string) => {
    setBusyId(id);
    setError(null);
    try {
      await restoreCourse(id);
      setItems((prev) => prev.filter((c) => c.id !== id));
    } catch (e) {
      setError(e);
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div>
      <Link href={`/${lang}/courses`} className="text-sm font-medium text-brand-700 hover:underline">{t("courses.trash.back")}</Link>
      <h1 className="mb-2 mt-2 text-2xl font-bold text-slate-900">{t("courses.trash.title")}</h1>
      <p className="mb-6 text-sm text-slate-600">{t("courses.trash.hint")}</p>
      {error ? <ErrorMessage error={error} onRetry={() => load()} className="mb-4" /> : null}
      {loading && items.length === 0 && !error && <p role="status" className="text-sm text-slate-500">{t("lms.common.loading")}</p>}
      {!loading && !error && items.length === 0 && (
        <p className="rounded-2xl border border-dashed border-slate-300 p-8 text-center text-sm text-slate-500">{t("courses.trash.empty")}</p>
      )}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {items.map((c) => (
          <CourseCard key={c.id} course={c} action={
            <button type="button" disabled={busyId === c.id} onClick={() => restore(c.id)}
              className="rounded-xl bg-brand-600 px-3 py-1.5 text-sm font-semibold text-white hover:bg-brand-700 disabled:opacity-50">
              {t("courses.trash.restore")}
            </button>
          } />
        ))}
      </div>
      <Pager nextCursor={cursor} loading={loading} onMore={() => load(cursor)} />
    </div>
  );
}
