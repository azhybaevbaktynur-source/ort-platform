"use client";

import React, { useId, useState } from "react";
import Link from "next/link";
import {
  BookOpen, Compass, Download, Ellipsis, FlaskConical, GraduationCap, House, LayoutGrid, LogOut, PlayCircle, Settings,
} from "lucide-react";
import { useTranslation, type Language } from "@/lib/i18n/context";
import { inter } from "@/lib/fonts";
import { fmtPassEnd } from "@/lib/lms/access";
import type { HomeCourseOut } from "@/lib/lms/homeTypes";
import { pickLocalized } from "@/lib/lms/localized";
import { courseGroups, type CourseGroupKey } from "@/lib/lms/examFamilies";
import { continueTarget } from "@/lib/lms/lastPlace";
import { useLastPlaceRead } from "@/lib/lms/useLastPlace";
import { courseIdOfPath, courseRows, studentNavLinks, type StudentNavKey, type StudentNavLink } from "@/lib/lms/studentNav";
import { prefetchExamPrep, prefetchModules } from "@/lib/lms/pageData"; // PERFORMANCE_AUDIT S3
import { usePwa } from "@/components/pwa/PwaProvider";
import { GoldPill } from "@/components/ui/GoldPill";
import { Sheet } from "@/components/ui/Sheet";
import { SidebarNav, type SidebarNavGroup, type SidebarNavItem } from "@/components/ui/SidebarNav";
import { TabBar, TAB_BAR_SPACE, type TabBarItem } from "@/components/ui/TabBar";
import { cn, focusRing } from "@/components/ui/utils";
import type { AppHeaderArea, AppHeaderLink } from "@/components/ui/AppHeader";
import type { StudentShellData } from "./useStudentShellData";
import { GettingStartedSheet, ProgressRing, useGettingStarted, type GettingStartedState } from "./gettingStarted"; // U8

/*
 * Student UI U2, step 3a S3 (docs/phases/STUDENT_IA_DESIGN.md §2.1): the global frame of people who learn (and of the
 * test student in Student view). The frame is about the person; a course space (S2, `CourseFrame`) is about one
 * course, so no global link carries a course id and there is no exam switcher or "current course".
 * - from 1024 px: a 264 px teal sidebar: brand → /home; Главная · Каталог (S7 v3: no «Мои курсы» page, V1); the «Мои
 *   курсы» rows (recent first, 6 + «Все курсы (N)» → /home#courses; none: the group is hidden; a row opens the course's
 *   last tab, else Обзор); at the bottom Начало работы, the Pro pill, install, other areas and the account button;
 * - below: a 56 px top bar (brand, page title, account) and the bottom bar Главная · Продолжить · Каталог · Ещё (V6).
 * «Войти по коду» lives only in the catalog's header (V5). The test student has no Каталог, Pro or install.
 * `LmsShell` keeps one tree for both frames; only the player is full-screen. Inter applies inside `STUDENT_FRAME` only.
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
  user: { name: string; email: string };
  /** Areas other than Learning the person has (Teaching, Organization, Platform, Parent). */
  otherAreas: AppHeaderArea[];
  accountLinks: (AppHeaderLink & { icon?: React.ReactNode })[];
  onLanguageChange: (lang: Language) => void;
  onLogout: () => void;
  /** The student-view test student: no Каталог, Pro or install. */
  testStudent: boolean;
}

const ICONS: Record<StudentNavKey, React.ReactNode> = {
  home: <House />,
  catalog: <Compass />,
};

/** The row icon by exam family (ОРТ / НЦТ / other). */
const FAMILY_ICON: Record<CourseGroupKey, React.ReactNode> = {
  ort: <GraduationCap />,
  nct: <FlaskConical />,
  other: <BookOpen />,
};

const LANGS: Language[] = ["en", "ky", "ru"];

function initials(name: string): string {
  const parts = name.replace(/@.*/, "").split(/[\s._-]+/).filter(Boolean);
  const s = (parts[0]?.[0] ?? "") + (parts.length > 1 ? parts[parts.length - 1][0] : "");
  return (s || name[0] || "?").toUpperCase();
}

/** Course title in the student's language. */
function useCourseTitle() {
  const { lang, t } = useTranslation();
  return (c: HomeCourseOut) => pickLocalized(c.title, lang, c.default_language) || t("courses.list.untitled");
}

/** The global links, the «Мои курсы» rows and «Продолжить», from the shell data and this device's last place. */
function useNav(props: StudentShellProps) {
  const { lang, t } = useTranslation();
  const title = useCourseTitle();
  const { data, rest, testStudent } = props;
  const { place, recent } = useLastPlaceRead();
  const links = studentNavLinks({ lang, rest, testStudent });
  const label: Record<StudentNavKey, string> = {
    home: t("student.nav.home"), catalog: t("student.nav.catalog"),
  };
  const item = (l: StudentNavLink | null): SidebarNavItem[] =>
    l ? [{ key: l.key, href: l.href, label: label[l.key], icon: ICONS[l.key], active: l.active }] : [];
  const groups = courseGroups(data.courses);
  const rows = courseRows({ lang, rest, courses: data.courses, recent, place, loaded: data.loaded });
  const courseItems: SidebarNavItem[] = [
    ...rows.rows.map((r): SidebarNavItem => {
      const progressText = r.progress ? t("course.header.progress", { done: r.progress.done, total: r.progress.total }) : null;
      return {
        key: `course:${r.course.id}`, href: r.href, label: title(r.course), icon: FAMILY_ICON[groups.get(r.course.id) ?? "other"], active: r.active,
        badge: r.progress && progressText ? (
          <span title={progressText} className="inline-flex">
            <ProgressRing done={r.progress.done} total={r.progress.total} /><span className="sr-only">{progressText}</span>
          </span>
        ) : undefined,
      };
    }),
    ...(rows.all ? [{ key: "all-courses", href: rows.all.href, label: t("student.nav.allCourses", { n: rows.all.count }), icon: <LayoutGrid /> }] : []),
  ];
  const coursesGroup: SidebarNavGroup | null = courseItems.length > 0
    ? { key: "my-courses", label: t("student.nav.myCourses"), items: courseItems }
    : null;
  // «Продолжить» (phone bar): the last place, else a course's resume or next lesson, else the newest exam course; no
  // course: the catalog (S7, V8; the test student: the hub)
  const target = continueTarget(lang, place, data.courses);
  const continueHref = !data.loaded ? `/${lang}/home` : target.kind === "catalog" && testStudent ? `/${lang}/home` : target.href;
  return { links, label, item, coursesGroup, continueHref };
}

/**
 * PERFORMANCE_AUDIT S3 (§5.2): a hover, focus or touch on a course row asks its Обзор's cheap, side-effect-free reads
 * before the click (an exam course: the exam-prep page; a course with lessons: its modules). The cache keeps it to
 * one request; Next's `<Link>` prefetches the route code itself.
 */
function usePrefetchIntent(props: StudentShellProps) {
  const { courses } = props.data;
  return (e: React.SyntheticEvent) => {
    const href = (e.target as Element | null)?.closest?.("a[href]")?.getAttribute("href");
    if (!href) return;
    const id = courseIdOfPath(href.replace(/^\/(en|ky|ru)(?=\/)/, ""));
    const c = id ? courses.find((x) => x.id === id) : undefined;
    if (!c) return;
    if (c.student_layout === "exam_prep") prefetchExamPrep(c.id);
    if (c.features?.modules) prefetchModules(c.id);
  };
}

/** A row of the account sheet. */
const SHEET_ROW = cn("flex min-h-11 w-full items-center gap-3 rounded-control px-3 text-left text-sm font-medium leading-5 text-slate-800 hover:bg-slate-100",
  focusRing, "focus-visible:ring-offset-0");

/** The access pill: "Открыть все экзамены" (gold) or, with Pro, "Pro до …" (quiet); both open /pro. */
function AccessPill({ data, onNavigate }: { data: StudentShellData; onNavigate?: () => void }) {
  const { lang, t } = useTranslation();
  if (!data.loaded) return null;
  const href = `/${lang}/pro`;
  if (data.access?.active) {
    const until = fmtPassEnd(data.access.ends_at, lang, false);
    return <GoldPill href={href} block variant="secondary" onClick={onNavigate}>{until ? t("access.pill.until", { date: until }) : t("access.pill.active")}</GoldPill>;
  }
  return <GoldPill href={href} block onClick={onNavigate}>{t("access.menu")}</GoldPill>;
}

function LogoutButton({ props, onNavigate }: { props: StudentShellProps; onNavigate: () => void }) {
  const { t } = useTranslation();
  return (
    <button type="button" onClick={() => { onNavigate(); props.onLogout(); }} className={SHEET_ROW}>
      <LogOut aria-hidden="true" className="h-5 w-5 shrink-0 text-slate-600" />
      {t("common.logout")}
    </button>
  );
}

/** Item 4 (phone): the sign-out row is the sheet's pinned footer, so the panel itself ends with the links. */
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

/** U8, step 3a S3: one checklist per student, from the newest exam course; nothing for the test student or without
 * an exam course. */
function useShellGettingStarted(props: StudentShellProps): GettingStartedState {
  const { data, rest, testStudent } = props;
  const exam = data.courses.find((c) => c.student_layout === "exam_prep") ?? null;
  return useGettingStarted({
    courseId: exam?.id ?? null, practice: exam ? exam.features?.practice ?? null : null, pathKey: rest,
    enabled: !testStudent && !!exam,
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

/** The phone top bar's title: the global page, or the course being viewed. */
function usePageTitle(props: StudentShellProps): string {
  const { t } = useTranslation();
  const title = useCourseTitle();
  const { rest, data } = props;
  if (rest === "/home") return t("student.nav.home");
  if (rest === "/courses/catalog" || rest.startsWith("/courses/catalog/")) return t("student.nav.catalog");
  const id = courseIdOfPath(rest);
  const c = id ? data.courses.find((x) => x.id === id) : undefined;
  return c ? title(c) : t("common.appName");
}

/** Desktop sidebar plus the phone top bar and the account sheet. */
export function StudentChrome(props: StudentShellProps) {
  const { lang, t } = useTranslation();
  const { data, user, testStudent } = props;
  const nav = useNav(props);
  const groups: SidebarNavGroup[] = [
    { key: "main", items: [...nav.item(nav.links.home), ...nav.item(nav.links.catalog)] },
    ...(nav.coursesGroup ? [nav.coursesGroup] : []),
  ];
  const intent = usePrefetchIntent(props); // PERFORMANCE_AUDIT S3
  const pageTitle = usePageTitle(props);
  const [sheet, setSheet] = useState<"account" | "start" | null>(null);
  const close = () => setSheet(null);
  const accountId = useId();
  const startId = useId();
  const start = useShellGettingStarted(props);

  return (
    <>
      {/* ---- desktop: the teal sidebar ---- */}
      <aside className={cn("fixed inset-y-0 left-0 z-30 hidden w-[264px] flex-col text-white lg:flex", STUDENT_SIDEBAR_BG)}>
        <div className="flex min-h-0 flex-1 flex-col gap-5 overflow-y-auto px-4 pb-4 pt-5">
          <Link href={`/${lang}/home`}
            className="inline-flex min-h-11 items-center gap-2.5 rounded-control focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white">
            <span aria-hidden="true" className="flex h-9 w-9 shrink-0 items-center justify-center rounded-control bg-white/10 text-white">
              <GraduationCap className="h-5 w-5" />
            </span>
            <span className="min-w-0 truncate text-base font-bold leading-5 text-white">{t("common.appName")}</span>
          </Link>
          {/* PERFORMANCE_AUDIT S3: `contents` keeps the sidebar's layout; the wrapper only listens */}
          <div className="contents" onPointerOver={intent} onFocus={intent}>
            <SidebarNav label={t("student.nav.label")} groups={groups} />
          </div>
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

      {/* ---- phone: the top bar (brand, page title, account) ---- */}
      <header className="sticky top-0 z-30 border-b border-slate-200 bg-white lg:hidden">
        <div className="flex h-14 items-center gap-2 px-4">
          <Link href={`/${lang}/home`} aria-label={t("common.appName")}
            className={cn("inline-flex h-11 shrink-0 items-center rounded-control", focusRing)}>
            <span aria-hidden="true" className="flex h-9 w-9 items-center justify-center rounded-control bg-navy-800 text-white">
              <GraduationCap className="h-5 w-5" />
            </span>
          </Link>
          <span className="min-w-0 truncate text-base font-bold text-slate-900">{pageTitle}</span>
          <button type="button" onClick={() => setSheet("account")} aria-haspopup="dialog" aria-expanded={sheet === "account"} aria-controls={accountId}
            aria-label={t("shell.account.menu", { name: user.name })}
            className={cn("ml-auto inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-full", focusRing)}>
            <span aria-hidden="true" className="flex h-9 w-9 items-center justify-center rounded-full bg-navy-800 text-sm font-semibold text-white">{initials(user.name)}</span>
          </button>
        </div>
      </header>

      <Sheet id={accountId} open={sheet === "account"} onClose={close} title={t("student.account.title")}
        footer={<LogoutButton props={props} onNavigate={close} />}>
        <AccountPanel props={props} onNavigate={close} />
      </Sheet>
      <GettingStartedSheet id={startId} state={start} open={sheet === "start"} onClose={close} />
    </>
  );
}

/** Phone bottom bar (Главная · Продолжить · Каталог · Ещё; S7 v3 V6) and its «Ещё» sheet. */
export function StudentTabBar(props: StudentShellProps) {
  const { lang, t } = useTranslation();
  const nav = useNav(props);
  const { links } = nav;
  const { data, rest, testStudent } = props;
  const [more, setMore] = useState(false);
  const [startOpen, setStartOpen] = useState(false);
  const moreId = useId();
  const startId = useId();
  const close = () => setMore(false);
  const start = useShellGettingStarted(props);
  const intent = usePrefetchIntent(props); // PERFORMANCE_AUDIT S3
  const here = `/${lang}${rest}`;
  const items: TabBarItem[] = [
    { key: "home", href: links.home.href, label: t("student.nav.home"), icon: <House />, active: links.home.active && !more },
    // a link whose target is decided on the client; current when it leads to this very page, unless another item of
    // the bar already is (S7: with no course it leads to the catalog, whose own item is then current)
    { key: "continue", href: nav.continueHref, label: t("student.nav.continue"), icon: <PlayCircle />,
      active: nav.continueHref.split(/[?#]/)[0] === here && !links.home.active && !links.catalog?.active && !more },
    ...(links.catalog ? [{ key: "catalog", href: links.catalog.href, label: t("student.nav.catalog"), icon: <Compass />, active: links.catalog.active && !more }] : []),
    { key: "more", label: t("student.nav.more"), icon: <Ellipsis />, onClick: () => setMore(true), expanded: more, controls: moreId },
  ];
  return (
    <>
      <div className="contents" onTouchStart={intent} onPointerOver={intent} onFocus={intent}>
        <TabBar label={t("student.nav.tabBar")} items={items} />
      </div>
      <Sheet id={moreId} open={more} onClose={close} title={t("student.nav.more")} tone="navy"
        footer={<LogoutButton props={props} onNavigate={close} />}>
        <div className="space-y-4">
          {nav.coursesGroup && <SidebarNav label={t("student.nav.myCourses")} tone="light" onNavigate={close} groups={[nav.coursesGroup]} />}
          {/* U8: the checklist sheet opens after "More" closed (one modal at a time) */}
          <GettingStartedPill state={start} tone="light" onOpen={() => { close(); setStartOpen(true); }} />
          {!testStudent && <div className="px-3"><AccessPill data={data} onNavigate={close} /></div>}
          {!testStudent && <InstallItem tone="light" onNavigate={close} />}
          <OtherAreas areas={props.otherAreas} tone="light" onNavigate={close} />
          <div className="border-t border-slate-100 pt-3"><AccountPanel props={props} onNavigate={close} /></div>
        </div>
      </Sheet>
      <GettingStartedSheet id={startId} state={start} open={startOpen} onClose={() => setStartOpen(false)} />
    </>
  );
}
