"use client";

import React, { useId, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  BarChart3, Bookmark, ClipboardList, Compass, Download, Dumbbell, Ellipsis, GraduationCap, House, KeyRound, LogOut,
  PlayCircle, Plus, Settings,
} from "lucide-react";
import { useTranslation, type Language } from "@/lib/i18n/context";
import { inter } from "@/lib/fonts";
import { fmtPassEnd } from "@/lib/lms/access";
import type { HomeCourseOut } from "@/lib/lms/homeTypes";
import { pickLocalized } from "@/lib/lms/localized";
import { studentNavLinks, type StudentNavKey, type StudentNavLink } from "@/lib/lms/studentNav";
import { usePwa } from "@/components/pwa/PwaProvider";
import { GoldPill } from "@/components/ui/GoldPill";
import { Sheet } from "@/components/ui/Sheet";
import { SidebarNav, type SidebarNavGroup, type SidebarNavItem } from "@/components/ui/SidebarNav";
import { TabBar, TAB_BAR_SPACE, type TabBarItem } from "@/components/ui/TabBar";
import { cn, focusRing } from "@/components/ui/utils";
import type { AppHeaderArea, AppHeaderLink } from "@/components/ui/AppHeader";
import type { StudentShellData } from "./useStudentShellData";
import { LeaveCourseDialog } from "@/components/lms/home/LeaveCourseLink"; // U9
import { GettingStartedSheet, ProgressRing, useGettingStarted, type GettingStartedState } from "./gettingStarted"; // U8

/*
 * Student UI U2 (docs/phases/STUDENT_UI_DESIGN.md §2): the frame of the student area.
 * - from 1024 px: a 264 px navy sidebar (brand, exam switcher, links, access pill, install, other areas, account);
 * - below: a 56 px top bar (brand, current exam, account) and a bottom tab bar (Главная · Тесты · Практика ·
 *   Аналитика · Ещё; without an exam course Главная · Каталог · Ещё) with a "More" sheet.
 * `LmsShell` keeps one tree for both frames (the chrome sits in a fixed slot, <main> never remounts) and never uses
 * this frame on the ORT lobby and attempt routes (§2.4). Inter applies inside `STUDENT_FRAME` only.
 */

/** Classes of the frame's root: Inter (scoped here), the "Sky and teal" palette (§1.1: `.student-theme` re-points the
 * `brand` and `navy` colours, page background #eef6fc), room for the sidebar from 1024 px. Put it after `bg-slate-50`
 * in `cn()` so the background wins. */
export const STUDENT_FRAME = cn(inter.variable, "student-theme bg-[#eef6fc] font-sans lg:pl-[264px]");
/** The sidebar's teal gradient (§1.1: #0e4a6b → #13698f; `navy-800` is #0e4a6b inside `.student-theme`). */
export const STUDENT_SIDEBAR_BG = "bg-gradient-to-b from-navy-800 to-[#13698f]";
/** Classes of <main> in the student frame: content up to 1200 px, room for the tab bar on phones. */
export const STUDENT_MAIN = cn("mx-auto w-full max-w-[1200px] px-4 pt-6 sm:px-6 lg:px-8 lg:pt-8", TAB_BAR_SPACE);

export interface StudentShellProps {
  data: StudentShellData;
  /** Path without the language prefix. */
  rest: string;
  tab: string | null;
  user: { name: string; email: string };
  /** Areas other than Learning the person has (Teaching, Organization, Platform, Parent). */
  otherAreas: AppHeaderArea[];
  accountLinks: (AppHeaderLink & { icon?: React.ReactNode })[];
  onLanguageChange: (lang: Language) => void;
  onLogout: () => void;
  /** The student-view test student: no access pill, no install. */
  testStudent: boolean;
}

const ICONS: Record<StudentNavKey, React.ReactNode> = {
  home: <House />,
  analytics: <BarChart3 />,
  saved: <Bookmark />,
  lessons: <PlayCircle />,
  tests: <ClipboardList />,
  practice: <Dumbbell />,
  catalog: <Compass />,
};

const LANGS: Language[] = ["en", "ky", "ru"];

function initials(name: string): string {
  const parts = name.replace(/@.*/, "").split(/[\s._-]+/).filter(Boolean);
  const s = (parts[0]?.[0] ?? "") + (parts.length > 1 ? parts[parts.length - 1][0] : "");
  return (s || name[0] || "?").toUpperCase();
}

function useNav(props: StudentShellProps) {
  const { lang, t } = useTranslation();
  const { data, rest, tab } = props;
  const links = studentNavLinks({ lang, rest, tab, courseId: data.current?.id ?? null, features: data.features });
  const label: Record<StudentNavKey, string> = {
    home: t("student.nav.home"), analytics: t("student.nav.analytics"), saved: t("student.nav.saved"),
    lessons: t("student.nav.lessons"), tests: t("student.nav.tests"), practice: t("student.nav.practice"),
    catalog: t("student.nav.catalog"),
  };
  const item = (l: StudentNavLink | null): SidebarNavItem[] =>
    l ? [{ key: l.key, href: l.href, label: label[l.key], icon: ICONS[l.key], active: l.active }] : [];
  return { links, label, item };
}

/** U9 (review 5, 6): the same links on every page and in the same order as the tab bar: Главная, Тесты, Практика,
 * Аналитика, then Видеоуроки and Сохранённые (no module sub-links: the phone has none either). */
function useMenuGroups(props: StudentShellProps): SidebarNavGroup[] {
  const { links, item } = useNav(props);
  const { data } = props;
  if (!data.current) return [{ key: "main", items: [...item(links.home), ...item(links.catalog)] }];
  return [
    { key: "main", items: [...item(links.home), ...item(links.tests), ...(data.features?.practice ? item(links.practice) : []), ...item(links.analytics), ...item(links.lessons), ...item(links.saved)] },
  ];
}

/** A row of the account and exam sheets. */
const SHEET_ROW = cn("flex min-h-11 w-full items-center gap-3 rounded-control px-3 text-left text-sm font-medium leading-5 text-slate-800 hover:bg-slate-100",
  focusRing, "focus-visible:ring-offset-0");

/** Course title in the student's language. */
function useCourseTitle() {
  const { lang, t } = useTranslation();
  return (c: HomeCourseOut) => pickLocalized(c.title, lang, c.default_language) || t("courses.list.untitled");
}

/** The access pill: "Открыть все экзамены" (gold) or, with a pass, "Доступ до …" (quiet). */
function AccessPill({ data, onNavigate }: { data: StudentShellData; onNavigate?: () => void }) {
  const { lang, t } = useTranslation();
  if (!data.current) return null;
  const href = `/${lang}/unlock`;
  if (data.access?.active) {
    const until = fmtPassEnd(data.access.ends_at, lang, false);
    return <GoldPill href={href} block variant="secondary" onClick={onNavigate}>{until ? t("student.access.until", { date: until }) : t("student.access.open")}</GoldPill>;
  }
  return <GoldPill href={href} block onClick={onNavigate}>{t("access.menu")}</GoldPill>;
}

/** Name, language, account links and log out: the account sheet and the bottom of "More". */
function AccountPanel({ props, onNavigate }: { props: StudentShellProps; onNavigate: () => void }) {
  const { lang, t } = useTranslation();
  const langLabelId = useId();
  const langName: Record<Language, string> = { en: t("common.english"), ky: t("common.kyrgyz"), ru: t("common.russian") };
  const { user, accountLinks } = props;
  const row = SHEET_ROW;
  return (
    <div className="space-y-3">
      <div className="px-3">
        <p className="text-xs font-medium uppercase tracking-wide text-slate-600">{t("shell.account.signedInAs")}</p>
        <p className="mt-1 break-words text-base font-semibold leading-6 text-slate-900">{user.name}</p>
        {user.email !== user.name && <p className="break-all text-sm leading-5 text-slate-600">{user.email}</p>}
      </div>
      <div className="border-t border-slate-100 px-3 pt-3">
        <p id={langLabelId} className="mb-2 text-sm font-medium text-slate-800">{t("shell.account.language")}</p>
        <div role="group" aria-labelledby={langLabelId} className="grid grid-cols-3 gap-1 rounded-control bg-slate-100 p-1">
          {LANGS.map((l) => (
            <button key={l} type="button" aria-pressed={l === lang} lang={l} title={langName[l]} onClick={() => props.onLanguageChange(l)}
              className={cn("min-h-11 rounded-lg px-2 text-sm font-semibold", focusRing, "focus-visible:ring-offset-0",
                l === lang ? "bg-white text-brand-800 shadow-sm" : "text-slate-700 hover:text-slate-900")}>
              {l.toUpperCase()}<span className="sr-only"> {langName[l]}</span>
            </button>
          ))}
        </div>
      </div>
      {accountLinks.length > 0 && (
        <ul className="space-y-0.5 border-t border-slate-100 pt-2">
          {accountLinks.map((l) => (
            <li key={l.href}>
              <Link href={l.href} aria-current={l.active ? "page" : undefined} onClick={onNavigate}
                className={cn(row, l.active && "bg-brand-50 text-brand-800")}>
                {l.icon && <span aria-hidden="true" className="inline-flex shrink-0 text-slate-600 [&>svg]:h-5 [&>svg]:w-5">{l.icon}</span>}
                <span className="min-w-0 flex-1 break-words">{l.label}</span>
              </Link>
            </li>
          ))}
        </ul>
      )}
      <div className="border-t border-slate-100 pt-2">
        <button type="button" onClick={() => { onNavigate(); props.onLogout(); }} className={row}>
          <LogOut aria-hidden="true" className="h-5 w-5 shrink-0 text-slate-600" />
          {t("common.logout")}
        </button>
      </div>
    </div>
  );
}

/** The exam courses as chips (switch) plus "+" (U9: opens the exam sheet with the catalog, the code and leaving; the
 * sheet itself has no "+"). One course: its title only. */
function ExamSwitcher({ props, tone, onNavigate, onAdd }: {
  props: StudentShellProps; tone: "navy" | "light"; onNavigate?: () => void; onAdd?: { open: () => void; expanded: boolean; controls: string };
}) {
  const { lang, t } = useTranslation();
  const router = useRouter();
  const title = useCourseTitle();
  const { data, rest } = props;
  const switchTo = (id: string) => {
    const old = data.current?.id;
    data.setCurrent(id);
    onNavigate?.();
    // inside a page of the old exam: the same section of the new one (course page, progress, practice, modules)
    if (old && old !== id && rest.startsWith(`/courses/${old}`)) {
      const section = rest.slice(`/courses/${old}`.length).split("/")[1] ?? "";
      const keep = ["progress", "practice", "modules", "saved"].includes(section) ? `/${section}` : "";
      router.push(`/${lang}/courses/${id}${keep}`);
    }
  };
  const add = onAdd ? (
    <button type="button" onClick={onAdd.open} aria-label={t("student.switcher.add")} title={t("student.switcher.add")}
      aria-haspopup="dialog" aria-expanded={onAdd.expanded} aria-controls={onAdd.controls}
      className={cn("inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-control border",
        tone === "navy"
          ? "border-white/20 text-white hover:bg-white/[0.08] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white"
          : cn("border-slate-300 text-slate-700 hover:bg-slate-100", focusRing))}>
      <Plus aria-hidden="true" className="h-5 w-5" />
    </button>
  ) : null;
  if (data.courses.length <= 1) {
    return (
      <div className="flex items-center gap-2">
        {data.current && (
          <p className={cn("min-w-0 flex-1 break-words text-sm font-semibold leading-5", tone === "navy" ? "text-white/90" : "text-slate-900")}>
            {title(data.current)}
          </p>
        )}
        {add}
      </div>
    );
  }
  return (
    <div role="group" aria-label={t("student.switcher.label")} className="flex flex-wrap gap-1.5">
      {data.courses.map((c) => {
        const on = c.id === data.current?.id;
        return (
          <button key={c.id} type="button" aria-pressed={on} onClick={() => switchTo(c.id)}
            className={cn("min-h-11 max-w-full rounded-control px-3 text-left text-sm font-semibold leading-5",
              tone === "navy"
                ? cn("focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white",
                  on ? "bg-white text-navy-800" : "bg-white/[0.08] text-white/90 hover:bg-white/15")
                : cn(focusRing, "focus-visible:ring-offset-0", on ? "bg-brand-50 text-brand-800 ring-1 ring-brand-200" : "bg-slate-100 text-slate-800 hover:bg-slate-200"))}>
            <span className="break-words">{title(c)}</span>
          </button>
        );
      })}
      {add}
    </div>
  );
}

/** U9 (review 1, 2): the exam sheet: switch, then find a course in the catalog, join by code, leave the current one. */
function ExamSheetBody({ props, onNavigate, onLeave }: { props: StudentShellProps; onNavigate: () => void; onLeave: () => void }) {
  const { lang, t } = useTranslation();
  const { data, testStudent } = props;
  const icon = "h-5 w-5 shrink-0 text-slate-600";
  return (
    <div className="space-y-3 px-3 pb-2">
      <ExamSwitcher props={props} tone="light" onNavigate={onNavigate} />
      <ul className="space-y-0.5 border-t border-slate-100 pt-2">
        <li>
          <Link href={`/${lang}/courses/catalog`} onClick={onNavigate} className={SHEET_ROW}>
            <Plus aria-hidden="true" className={icon} /><span className="min-w-0 flex-1 break-words">{t("home.prep.addCourse")}</span>
          </Link>
        </li>
        <li>
          <Link href={`/${lang}/courses/join`} onClick={onNavigate} className={SHEET_ROW}>
            <KeyRound aria-hidden="true" className={icon} /><span className="min-w-0 flex-1 break-words">{t("home.primary.join")}</span>
          </Link>
        </li>
        {!testStudent && data.current && (
          <li className="border-t border-slate-100 pt-2">
            <button type="button" onClick={onLeave} className={cn(SHEET_ROW, "text-danger-700 hover:bg-danger-50")}>
              <LogOut aria-hidden="true" className="h-5 w-5 shrink-0" /><span className="min-w-0 flex-1 break-words">{t("courses.home.leave")}</span>
            </button>
          </li>
        )}
      </ul>
    </div>
  );
}

function OtherAreas({ areas, tone, onNavigate }: { areas: AppHeaderArea[]; tone: "navy" | "light"; onNavigate?: () => void }) {
  const { t } = useTranslation();
  if (areas.length === 0) return null;
  return (
    <SidebarNav label={t("student.nav.otherAreas")} tone={tone} onNavigate={onNavigate}
      groups={[{ key: "areas", label: t("student.nav.otherAreas"), items: areas.map((a) => ({ key: a.key, href: a.href, label: a.label, icon: a.icon })) }]} />
  );
}

function InstallItem({ tone, onNavigate }: { tone: "navy" | "light"; onNavigate?: () => void }) {
  const { t } = useTranslation();
  const pwa = usePwa();
  if (!pwa.installKind) return null;
  return (
    <SidebarNav label={t("pwa.install.menu")} tone={tone}
      groups={[{ key: "install", items: [{ key: "install", label: t("pwa.install.menu"), icon: <Download />, onClick: () => { onNavigate?.(); pwa.install(); } }] }]} />
  );
}

/** U8 (§3.6): the checklist of the current exam course; nothing for the test student or without an exam course. */
function useShellGettingStarted(props: StudentShellProps): GettingStartedState {
  const { data, rest, testStudent } = props;
  return useGettingStarted({
    courseId: data.current?.id ?? null, practice: data.current ? data.features?.practice ?? null : null, pathKey: rest,
    enabled: !testStudent && !!data.current, seeded: rest === "/courses", // the home seeds it from its own page
  });
}

/** "Начало работы 2/4": a sidebar item that opens the checklist sheet; hidden until known and once complete. */
function GettingStartedPill({ state, tone, onOpen }: { state: GettingStartedState; tone: "navy" | "light"; onOpen: () => void }) {
  const { t } = useTranslation();
  if (!state.ready || state.complete) return null;
  return (
    <SidebarNav label={t("student.nav.gettingStarted")} tone={tone}
      groups={[{ key: "getting-started", items: [{
        key: "getting-started", label: t("student.nav.gettingStarted"), onClick: onOpen,
        icon: <ProgressRing done={state.done} total={state.total} />, badge: `${state.done}/${state.total}`,
      }] }]} />
  );
}

/** Desktop sidebar plus the phone top bar, the exam and account sheets. */
export function StudentChrome(props: StudentShellProps) {
  const { lang, t } = useTranslation();
  const title = useCourseTitle();
  const { data, user, testStudent } = props;
  const groups = useMenuGroups(props);
  const [sheet, setSheet] = useState<"account" | "exam" | "start" | null>(null);
  const close = () => setSheet(null);
  const accountId = useId();
  const examId = useId();
  const startId = useId();
  const start = useShellGettingStarted(props);
  // U9: leaving the current exam course, confirmed in a dialog opened after the exam sheet closed (one modal at a time)
  const [leaving, setLeaving] = useState<HomeCourseOut | null>(null);

  return (
    <>
      {/* ---- desktop: the navy sidebar ---- */}
      <aside className={cn("fixed inset-y-0 left-0 z-30 hidden w-[264px] flex-col text-white lg:flex", STUDENT_SIDEBAR_BG)}>
        <div className="flex min-h-0 flex-1 flex-col gap-5 overflow-y-auto px-4 pb-4 pt-5">
          <Link href={`/${lang}/courses`}
            className="inline-flex min-h-11 items-center gap-2.5 rounded-control focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white">
            <span aria-hidden="true" className="flex h-9 w-9 shrink-0 items-center justify-center rounded-control bg-white/10 text-white">
              <GraduationCap className="h-5 w-5" />
            </span>
            <span className="min-w-0 truncate text-base font-bold leading-5 text-white">{t("common.appName")}</span>
          </Link>
          {data.loaded && data.courses.length > 0 && (
            <ExamSwitcher props={props} tone="navy" onAdd={{ open: () => setSheet("exam"), expanded: sheet === "exam", controls: examId }} />
          )}
          <SidebarNav label={t("student.nav.label")} groups={groups} />
          <div className="mt-auto space-y-3">
            <GettingStartedPill state={start} tone="navy" onOpen={() => setSheet("start")} />
            {!testStudent && <AccessPill data={data} />}
            {!testStudent && <InstallItem tone="navy" />}
            <OtherAreas areas={props.otherAreas} tone="navy" />
          </div>
        </div>
        <div className="border-t border-white/10 px-4 py-3">
          <button type="button" onClick={() => setSheet("account")} aria-haspopup="dialog" aria-expanded={sheet === "account"} aria-controls={accountId}
            aria-label={t("shell.account.menu", { name: user.name })}
            className="flex min-h-11 w-full items-center gap-3 rounded-control px-2 text-left hover:bg-white/[0.08] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white">
            <span aria-hidden="true" className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-white text-sm font-semibold text-navy-800">{initials(user.name)}</span>
            <span aria-hidden="true" className="min-w-0 flex-1 truncate text-sm font-medium text-white">{user.name}</span>
            <Settings aria-hidden="true" className="h-5 w-5 shrink-0 text-white/[0.72]" />
          </button>
        </div>
      </aside>

      {/* ---- phone: the top bar ---- */}
      <header className="sticky top-0 z-30 border-b border-slate-200 bg-white lg:hidden">
        <div className="flex h-14 items-center gap-2 px-4">
          <Link href={`/${lang}/courses`} aria-label={t("common.appName")}
            className={cn("inline-flex h-11 shrink-0 items-center rounded-control", focusRing)}>
            <span aria-hidden="true" className="flex h-9 w-9 items-center justify-center rounded-control bg-navy-800 text-white">
              <GraduationCap className="h-5 w-5" />
            </span>
          </Link>
          {data.current ? (
            <button type="button" onClick={() => setSheet("exam")} aria-haspopup="dialog" aria-expanded={sheet === "exam"} aria-controls={examId}
              aria-label={t("student.switcher.open", { name: title(data.current) })}
              className={cn("inline-flex min-h-11 min-w-0 items-center gap-1.5 rounded-full border border-slate-200 bg-slate-50 px-3 text-sm font-semibold text-slate-800 hover:bg-slate-100", focusRing)}>
              <span aria-hidden="true" className="min-w-0 truncate">{title(data.current)}</span>
            </button>
          ) : (
            <span className="min-w-0 truncate text-base font-bold text-slate-900">{t("common.appName")}</span>
          )}
          <button type="button" onClick={() => setSheet("account")} aria-haspopup="dialog" aria-expanded={sheet === "account"} aria-controls={accountId}
            aria-label={t("shell.account.menu", { name: user.name })}
            className={cn("ml-auto inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-full", focusRing)}>
            <span aria-hidden="true" className="flex h-9 w-9 items-center justify-center rounded-full bg-navy-800 text-sm font-semibold text-white">{initials(user.name)}</span>
          </button>
        </div>
      </header>

      <Sheet id={accountId} open={sheet === "account"} onClose={close} title={t("student.account.title")}>
        <AccountPanel props={props} onNavigate={close} />
      </Sheet>
      <Sheet id={examId} open={sheet === "exam"} onClose={close} title={t("student.switcher.label")}>
        <ExamSheetBody props={props} onNavigate={close} onLeave={() => { setLeaving(data.current); close(); }} />
      </Sheet>
      {leaving && (
        <LeaveCourseDialog courseId={leaving.id} courseTitle={title(leaving)} open onCancel={() => setLeaving(null)}
          onLeft={() => {
            data.forget(leaving.id);
            window.location.assign(`/${lang}/courses`); // the home and the menu read everything again
          }} />
      )}
      <GettingStartedSheet id={startId} state={start} open={sheet === "start"} onClose={close} />
    </>
  );
}

/** Phone bottom bar and its "More" sheet. */
export function StudentTabBar(props: StudentShellProps) {
  const { t } = useTranslation();
  const { links, item, label } = useNav(props);
  const { data, testStudent } = props;
  const [more, setMore] = useState(false);
  const [startOpen, setStartOpen] = useState(false);
  const moreId = useId();
  const startId = useId();
  const close = () => setMore(false);
  const start = useShellGettingStarted(props);
  const slot = (l: StudentNavLink | null): TabBarItem[] =>
    l ? [{ key: l.key, href: l.href, label: label[l.key], icon: ICONS[l.key], active: l.active && !more }] : [];
  const moreSlot: TabBarItem = { key: "more", label: t("student.nav.more"), icon: <Ellipsis />, onClick: () => setMore(true), expanded: more, controls: moreId };
  const items: TabBarItem[] = data.current
    ? [...slot(links.home), ...slot(links.tests), ...slot(links.practice), ...slot(links.analytics), moreSlot]
    : [...slot(links.home), ...slot(links.catalog), moreSlot];
  const moreLinks: SidebarNavItem[] = data.current ? [...item(links.lessons), ...item(links.saved)] : [];
  return (
    <>
      <TabBar label={t("student.nav.tabBar")} items={items} />
      <Sheet id={moreId} open={more} onClose={close} title={t("student.nav.more")} tone="navy">
        <div className="space-y-4">
          {moreLinks.length > 0 && <SidebarNav label={t("student.nav.label")} tone="light" onNavigate={close} groups={[{ key: "more", items: moreLinks }]} />}
          {/* U8: the checklist sheet opens after "More" closed (one modal at a time) */}
          <GettingStartedPill state={start} tone="light" onOpen={() => { close(); setStartOpen(true); }} />
          {!testStudent && data.current && <div className="px-3"><AccessPill data={data} onNavigate={close} /></div>}
          {!testStudent && <InstallItem tone="light" onNavigate={close} />}
          <OtherAreas areas={props.otherAreas} tone="light" onNavigate={close} />
          <div className="border-t border-slate-100 pt-3"><AccountPanel props={props} onNavigate={close} /></div>
        </div>
      </Sheet>
      <GettingStartedSheet id={startId} state={start} open={startOpen} onClose={() => setStartOpen(false)} />
    </>
  );
}
