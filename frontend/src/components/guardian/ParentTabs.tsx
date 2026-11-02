"use client";

import React, { useCallback, useEffect, useState } from "react";
import { useTranslation } from "@/lib/i18n/context";
import { Badge, Card, EmptyState, LoadingState, Select, TabPanel, Tabs, type BadgeTone } from "@/components/ui";
import { Pager } from "@/components/lms/Pager";
import { SafeHtml } from "@/components/lms/pages/SafeHtml";
import { fmtApiDate } from "@/lib/format";
import type { Num } from "@/lib/lms/gradingTypes";
import { pickLocalized } from "@/lib/lms/localized";
import type { Lang } from "@/lib/lms/types";
import { useGradeListText } from "@/components/lms/results/GradeBadge";
import { GuardianError } from "./GuardianError";
import {
  getDue, getGrades, listAnnouncements, listCourses, type GuardianAnnouncement, type GuardianCourse, type GuardianDue,
  type GuardianGrades, type GuardianGradeState,
} from "./api";

type Tab = "grades" | "due" | "announcements";
const TABS_ID = "parent-tabs";
const COURSE_PAGES_MAX = 5;

const STATE_TONE: Record<GuardianGradeState, BadgeTone> = {
  graded: "success", pending: "info", submitted: "info", missing: "danger", excused: "neutral", hidden: "neutral", not_started: "neutral",
};

function num(value: Num | null, lang: string): string {
  return value === null ? "" : Number(value).toLocaleString(lang, { maximumFractionDigits: 2 });
}

/** A failed read: a consent that went away while the page was open brings the consent screen back. */
function useReadError(onConsentNeeded: () => void) {
  return useCallback((e: unknown, set: (error: unknown) => void) => {
    if ((e as { code?: string } | null)?.code === "consent_required") onConsentNeeded();
    else set(e);
  }, [onConsentNeeded]);
}

function GradesPanel({ linkId, courseId, onConsentNeeded }: { linkId: string; courseId: string; onConsentNeeded: () => void }) {
  const { lang, t } = useTranslation();
  const gradeText = useGradeListText();
  const [data, setData] = useState<GuardianGrades | null>(null);
  const [error, setError] = useState<unknown>(null);
  const failed = useReadError(onConsentNeeded);

  const load = useCallback(() => {
    setData(null);
    setError(null);
    getGrades(linkId, courseId).then(setData).catch((e) => failed(e, setError));
  }, [linkId, courseId, failed]);

  useEffect(load, [load]);

  if (error) return <GuardianError error={error} onRetry={load} />;
  if (!data) return <LoadingState rows={3} />;
  if (data.items.length === 0) return <EmptyState mascot="reading" title={t("guardian.grades.empty")} />;
  return (
    <>
      {data.total && data.total.percent !== null && (
        <p className="mb-3 text-base font-semibold text-slate-900">
          {t("guardian.grades.total", { percent: num(data.total.percent, lang) })}
          {data.total.label && <span className="ml-2 font-medium text-slate-700">{data.total.label}</span>}
        </p>
      )}
      <ul className="divide-y divide-slate-200 rounded-2xl border border-slate-200 bg-white">
        {data.items.map((item, i) => (
          <li key={i} className="p-4">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <p className="min-w-0 flex-1 basis-48 break-words font-medium text-slate-900">{pickLocalized(item.title, lang as Lang)}</p>
              <Badge tone={STATE_TONE[item.state] ?? "neutral"}>{t(`guardian.state.${item.state}`)}</Badge>
            </div>
            <p className="mt-1 text-sm text-slate-600">
              {item.due_at ? t("guardian.dueOn", { date: fmtApiDate(item.due_at, lang) }) : t("guardian.noDate")}
            </p>
            {item.state === "graded" && (
              <p className="mt-1 text-sm font-semibold text-slate-900">
                {gradeText({ ...item, effective_points: item.points })}
                {/* a scheme's value reads differently from the points: both, as the student's Grades page shows them */}
                {item.scheme_type && item.scheme_type !== "points" && item.points !== null && item.possible !== null && (
                  <span className="ml-2 font-medium text-slate-700">{t("guardian.grades.points", { points: num(item.points, lang), possible: num(item.possible, lang) })}</span>
                )}
              </p>
            )}
          </li>
        ))}
      </ul>
    </>
  );
}

function DuePanel({ linkId, onConsentNeeded }: { linkId: string; onConsentNeeded: () => void }) {
  const { lang, t } = useTranslation();
  const [rows, setRows] = useState<GuardianDue[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  const failed = useReadError(onConsentNeeded);

  const load = useCallback(() => {
    setRows(null);
    setError(null);
    getDue(linkId).then(setRows).catch((e) => failed(e, setError));
  }, [linkId, failed]);

  useEffect(load, [load]);

  if (error) return <GuardianError error={error} onRetry={load} />;
  if (!rows) return <LoadingState rows={3} />;
  if (rows.length === 0) return <EmptyState mascot="reading" title={t("guardian.due.empty")} />;
  return (
    <ul className="divide-y divide-slate-200 rounded-2xl border border-slate-200 bg-white">
      {rows.map((row, i) => (
        <li key={i} className="p-4">
          <p className="break-words font-medium text-slate-900">{pickLocalized(row.title, lang as Lang)}</p>
          <p className="mt-0.5 break-words text-sm text-slate-600">{pickLocalized(row.course_title, lang as Lang)}</p>
          <p className="mt-1 text-sm font-medium text-slate-800">
            {row.due_at ? t("guardian.dueOn", { date: fmtApiDate(row.due_at, lang) }) : t("guardian.noDate")}
          </p>
        </li>
      ))}
    </ul>
  );
}

function AnnouncementsPanel({ linkId, courseId, onConsentNeeded }: { linkId: string; courseId: string; onConsentNeeded: () => void }) {
  const { lang, t } = useTranslation();
  const [rows, setRows] = useState<GuardianAnnouncement[] | null>(null);
  const [next, setNext] = useState<string | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const failed = useReadError(onConsentNeeded);

  const load = useCallback(() => {
    setRows(null);
    setError(null);
    listAnnouncements(linkId, courseId).then((page) => {
      setRows(page.items);
      setNext(page.next_cursor);
    }).catch((e) => failed(e, setError));
  }, [linkId, courseId, failed]);

  useEffect(load, [load]);

  const more = async () => {
    setLoadingMore(true);
    try {
      const page = await listAnnouncements(linkId, courseId, next);
      setRows((old) => [...(old ?? []), ...page.items]);
      setNext(page.next_cursor);
    } catch (e) {
      failed(e, setError);
    } finally {
      setLoadingMore(false);
    }
  };

  if (error) return <GuardianError error={error} onRetry={load} />;
  if (!rows) return <LoadingState rows={2} />;
  if (rows.length === 0) return <EmptyState mascot="reading" title={t("guardian.announcements.empty")} />;
  return (
    <>
      <ul className="space-y-3">
        {rows.map((row, i) => (
          <li key={i}>
            <Card>
              <h3 className="break-words text-base font-semibold text-slate-900">{row.title}</h3>
              {row.published_at && <p className="mt-0.5 text-sm text-slate-600">{fmtApiDate(row.published_at, lang)}</p>}
              {row.body_html && <SafeHtml html={row.body_html} className="mt-3" />}
            </Card>
          </li>
        ))}
      </ul>
      <Pager nextCursor={next} loading={loadingMore} onMore={() => void more()} />
    </>
  );
}

export function ParentTabs({ linkId, onConsentNeeded }: { linkId: string; onConsentNeeded: () => void }) {
  const { lang, t } = useTranslation();
  const [tab, setTab] = useState<Tab>("grades");
  const [courses, setCourses] = useState<GuardianCourse[] | null>(null);
  const [courseId, setCourseId] = useState("");
  const [error, setError] = useState<unknown>(null);
  const failed = useReadError(onConsentNeeded);

  const load = useCallback(async () => {
    setError(null);
    try {
      const all: GuardianCourse[] = [];
      let cursor: string | null = null;
      for (let page = 0; page < COURSE_PAGES_MAX; page += 1) {
        const out: { items: GuardianCourse[]; next_cursor: string | null } = await listCourses(linkId, cursor);
        all.push(...out.items);
        cursor = out.next_cursor;
        if (!cursor) break;
      }
      setCourses(all);
      setCourseId((old) => (all.some((c) => c.id === old) ? old : all[0]?.id ?? ""));
    } catch (e) {
      failed(e, setError);
    }
  }, [linkId, failed]);

  useEffect(() => { void load(); }, [load]);

  const noCourse = courses !== null && courses.length === 0;
  const coursePicker = courses && courses.length > 1 && (
    <Select label={t("guardian.course")} containerClassName="mb-4 max-w-md" value={courseId} onChange={(ev) => setCourseId(ev.target.value)}
      options={courses.map((c) => ({ value: c.id, label: pickLocalized(c.title, lang as Lang) }))} />
  );

  return (
    <>
      <Tabs id={TABS_ID} label={t("guardian.tabs.label")} value={tab} onChange={(id) => setTab(id as Tab)} items={[
        { id: "grades", label: t("guardian.tabs.grades") },
        { id: "due", label: t("guardian.tabs.due") },
        { id: "announcements", label: t("guardian.tabs.announcements") },
      ]} />
      <TabPanel tabsId={TABS_ID} value={tab}>
        {tab === "due" ? (
          <DuePanel linkId={linkId} onConsentNeeded={onConsentNeeded} />
        ) : error ? (
          <GuardianError error={error} onRetry={() => void load()} />
        ) : courses === null ? (
          <LoadingState rows={3} />
        ) : noCourse ? (
          <EmptyState mascot="reading" title={t("guardian.noCourses")} />
        ) : (
          <>
            {coursePicker}
            {tab === "grades"
              ? <GradesPanel linkId={linkId} courseId={courseId} onConsentNeeded={onConsentNeeded} />
              : <AnnouncementsPanel linkId={linkId} courseId={courseId} onConsentNeeded={onConsentNeeded} />}
          </>
        )}
      </TabPanel>
    </>
  );
}
