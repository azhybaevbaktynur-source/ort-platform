"use client";

import React, { useMemo, useState } from "react";
import { BarChart3, Bookmark, ClipboardList, Dumbbell, Ellipsis, House, NotebookPen, PlayCircle } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { inter } from "@/lib/fonts";
import {
  Button, Card, Countdown, GoldPill, Heatmap, LockOverlay, Meter, SectionTag, Sheet, SidebarNav, TabBar, cn, examDayStart,
  type HeatmapDay,
} from "@/components/ui";

/* Student UI U1 (STUDENT_UI_DESIGN §1): the new primitives on the dev showcase, in the student shell's font. */

const SECTIONS = ["math_1", "math_2", "analogies", "reading", "grammar"];

/** Sample activity: a fixed pattern (no randomness, so every render is the same). */
function sampleDays(end: string): HeatmapDay[] {
  const out: HeatmapDay[] = [];
  const endMs = Date.parse(`${end}T00:00:00Z`);
  for (let i = 0; i < 91; i++) {
    const n = [0, 3, 0, 8, 17, 0, 32, 2, 0, 12][(i * 7) % 10];
    out.push({ date: new Date(endMs - i * 86_400_000).toISOString().slice(0, 10), answered: n });
  }
  return out;
}

export function StudentUiDemo() {
  const { lang, t } = useTranslation();
  const d = (k: string, p?: Record<string, string | number>) => t(`ui.demo.student.${k}`, p);
  const [sheetOpen, setSheetOpen] = useState(false);
  const end = "2026-11-06";
  const days = useMemo(() => sampleDays(end), []);
  const total = days.reduce((s, x) => s + x.answered, 0);
  const examDay = useMemo(() => {
    const dt = new Date(Date.now() + 30 * 86_400_000);
    return examDayStart(dt.toISOString().slice(0, 10));
  }, []);
  const topics = [
    { name: d("topicA"), value: 38 },
    { name: d("topicB"), value: 72 },
    { name: d("topicC"), value: 91 },
  ];
  const meters = (
    <ul className="space-y-3">
      {topics.map((x) => (
        <li key={x.name}>
          <p className="mb-1 text-sm font-medium text-slate-800">{x.name}</p>
          <Meter value={x.value} label={d("meterLabel", { name: x.name })} />
        </li>
      ))}
    </ul>
  );
  const base = `/${lang}/dev/ui`;
  return (
    <div className={cn(inter.variable, "font-sans space-y-4")}>
      <Card>
        <h3 className="mb-3 text-base font-semibold text-slate-900">{d("tags")}</h3>
        <div className="flex flex-wrap gap-2">
          {SECTIONS.map((s) => <SectionTag key={s} section={s} />)}
        </div>
      </Card>
      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <h3 className="mb-3 text-base font-semibold text-slate-900">{d("meters")}</h3>
          {meters}
        </Card>
        <Card>
          <h3 className="mb-3 text-base font-semibold text-slate-900">{d("countdown")}</h3>
          <Countdown target={examDay} label={d("countdown")} />
          <div className="mt-4 flex flex-wrap gap-2">
            <GoldPill href={`${base}#student`}>{t("access.menu")}</GoldPill>
            <GoldPill href={`${base}#student`} variant="secondary">{t("access.pill.until", { date: "31.05.2027" })}</GoldPill>
          </div>
        </Card>
      </div>
      <Card>
        <h3 className="mb-3 text-base font-semibold text-slate-900">{d("heatmap")}</h3>
        <Heatmap days={days} end={end} label={d("heatmap")} summary={d("heatmapSummary", { n: total })} />
      </Card>
      <LockOverlay locked title={d("lockTitle")} body={d("lockBody")} action={<GoldPill href={`${base}#student`}>{t("access.menu")}</GoldPill>}>
        <Card>{meters}</Card>
      </LockOverlay>
      <div className="grid gap-4 md:grid-cols-2">
        <div>
          <h3 className="mb-2 text-base font-semibold text-slate-900">{d("sidebar")}</h3>
          <div className="rounded-card bg-navy-800 p-4">
            <SidebarNav label={d("sidebar")} groups={[
              { key: "main", items: [
                { key: "home", label: t("student.nav.home"), href: `${base}#student`, icon: <House />, active: true },
                { key: "analytics", label: t("student.nav.analytics"), href: `${base}#student`, icon: <BarChart3 /> },
                { key: "saved", label: t("student.nav.saved"), href: `${base}#student`, icon: <Bookmark /> },
              ] },
              { key: "lessons", label: t("student.nav.lessonsGroup"), items: [
                { key: "lessons", label: t("student.nav.lessons"), href: `${base}#student`, icon: <PlayCircle /> },
              ] },
              { key: "practice", label: t("student.nav.practiceGroup"), items: [
                { key: "tests", label: t("student.nav.tests"), href: `${base}#student`, icon: <ClipboardList /> },
                { key: "practice", label: t("student.nav.practice"), href: `${base}#student`, icon: <Dumbbell /> },
                { key: "mistakes", label: t("student.nav.mistakes"), href: `${base}#student`, icon: <NotebookPen /> },
              ] },
            ]} />
          </div>
        </div>
        <div className="space-y-4">
          <div>
            <h3 className="mb-2 text-base font-semibold text-slate-900">{d("tabBar")}</h3>
            <div className="overflow-hidden rounded-card border border-slate-200">
              <TabBar label={d("tabBar")} className="static lg:block" items={[
                { key: "home", label: t("student.nav.home"), icon: <House />, href: `${base}#student`, active: true },
                { key: "tests", label: t("student.nav.tests"), icon: <ClipboardList />, href: `${base}#student` },
                { key: "practice", label: t("student.nav.practice"), icon: <Dumbbell />, href: `${base}#student` },
                { key: "analytics", label: t("student.nav.analytics"), icon: <BarChart3 />, href: `${base}#student` },
                { key: "more", label: t("student.nav.more"), icon: <Ellipsis />, onClick: () => setSheetOpen(true), expanded: sheetOpen },
              ]} />
            </div>
          </div>
          <Card>
            <h3 className="mb-3 text-base font-semibold text-slate-900">{d("sheet")}</h3>
            <Button variant="secondary" onClick={() => setSheetOpen(true)}>{d("openSheet")}</Button>
          </Card>
        </div>
      </div>
      <Sheet open={sheetOpen} onClose={() => setSheetOpen(false)} title={t("student.nav.more")} tone="navy">
        <p className="px-3 pb-3 text-sm leading-6 text-slate-700">{d("sheetBody")}</p>
        <SidebarNav label={d("sheet")} tone="light" onNavigate={() => setSheetOpen(false)} groups={[{ key: "more", items: [
          { key: "lessons", label: t("student.nav.lessons"), href: `${base}#student`, icon: <PlayCircle /> },
          { key: "saved", label: t("student.nav.saved"), href: `${base}#student`, icon: <Bookmark /> },
          { key: "mistakes", label: t("student.nav.mistakes"), href: `${base}#student`, icon: <NotebookPen /> },
        ] }]} />
      </Sheet>
    </div>
  );
}
