"use client";

import React, { createContext, Suspense, useContext, useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { BookOpen, Building2, KeyRound, Lock, Presentation, ShieldCheck, Users } from "lucide-react";
import { useTranslation, type Language } from "@/lib/i18n/context";
import { useAuth } from "@/lib/auth-context";
import { gateOpenPath } from "@/lib/api"; // Phase 11 S3
import { LmsMeProvider, useLmsMeLoader } from "@/lib/lms/useLmsMe";
import { useCachedMe } from "@/lib/lms/meCache"; // PERFORMANCE_AUDIT S1
import { areaFromUrl, hidesLearning, isPlayerRoute, shellKindFor, urlAreaFor, type ShellKind, type ShellMe } from "@/lib/lms/shellKind"; // S1
import { useCurrentOrg } from "@/lib/lms/currentOrg"; // item 4
import { AppHeader, Brand, type AppHeaderArea, type AreaKey } from "@/components/ui/AppHeader";
import { ErrorState, LoadingState, SHELL_WIDTH, Skeleton, cn } from "@/components/ui";
import { EXAM_COLUMN_INNER, EXAM_COLUMN_OUTER } from "@/components/ui/shellWidth";
import { inter } from "@/lib/fonts"; // SF-1: the player route's font
import { lmsErrorKey } from "./ErrorMessage";
import { PendingInvitationsBanner } from "./PendingInvitationsBanner"; // Phase 6 S4b
import { InvitationAcceptedNotice } from "./InvitationAcceptedNotice"; // Phase 6 S8
import { StudentViewBanner } from "./course/StudentViewBanner"; // UX rework S1
import { PrivacyBanner } from "@/components/privacy/PrivacyBanner"; // Phase 11 S3
// --- Student UI U2 ---
import type { CourseOut } from "@/lib/lms/types";
import { courseIdOfPath } from "@/lib/lms/studentNav";
import { STUDENT_FRAME, STUDENT_MAIN, StudentChrome, StudentTabBar } from "./student/StudentShell";
import { useStudentShellData } from "./student/useStudentShellData";
import { StudentShellDataContext } from "./student/StudentShellDataContext"; // Student UI U3

/*
 * Phase 6b S5b: the frame of every signed-in page (courses/*, admin/*, org/*, grading-schemes, invitations).
 * `AppHeader` with the area switcher replaces the old link rows. Area URLs: Learning `/courses` (or
 * `/courses?view=learning` for people who also teach), Teaching `/courses?view=teaching`, Organization
 * `/org/{id}` (or the picker `/org`), Platform `/admin`.
 */

/** Phase 8c S1 (PHASE_8C_DESIGN §2.5): a page's area plus whether the area's sub-menu (the header's second row on
 * desktop, the sections in the phone menu) is hidden there; course pages hide it (the course sidebar navigates). */
interface DeclaredArea {
  area: AreaKey;
  hideSections: boolean;
}
type DeclareArea = (value: DeclaredArea | null) => void;
const AreaDeclareContext = createContext<DeclareArea>(() => {});

/**
 * Lets a page tell the header which area it belongs to when the URL alone cannot (a course page is
 * Teaching for its staff and Learning for its students). Pass null to fall back to the URL rule.
 */
export function useDeclareArea(area: AreaKey | null, opts: { hideSections?: boolean } = {}) {
  const declare = useContext(AreaDeclareContext);
  const hideSections = !!opts.hideSections;
  useEffect(() => {
    declare(area ? { area, hideSections } : null);
    return () => declare(null);
  }, [area, hideSections, declare]);
}

/** Reads `?view=` (needs a Suspense boundary for static pages). Student UI U2: also `?tab=` (the shell's active link). */
function ViewParam({ onChange, onTab }: { onChange: (v: string | null) => void; onTab: (v: string | null) => void }) {
  const params = useSearchParams();
  const view = params.get("view");
  const tab = params.get("tab");
  useEffect(() => { onChange(view); }, [view, onChange]);
  useEffect(() => { onTab(tab); }, [tab, onTab]);
  return null;
}

// --- Student UI U2 begin --- (STUDENT_UI_DESIGN §2): the course layout tells the student shell which course it loaded
type DeclareCourse = (course: CourseOut | null) => void;
const StudentCourseDeclareContext = createContext<DeclareCourse>(() => {});

/** The course layout's loaded course, for the student shell (its lessons/practice links, a course joined just now). */
export function useDeclareStudentCourse(course: CourseOut | null) {
  const declare = useContext(StudentCourseDeclareContext);
  useEffect(() => {
    declare(course);
    return () => declare(null);
  }, [course, declare]);
}

// --- Student UI U2 end ---

// --- SF-1 begin --- (STUDENT_UI_FIX_PLAN §2.1, replaces STUDENT_UI_DESIGN §2.4): the lobby, the result and the review
// follow the area rule (students: the student shell); the player route (exact path) has no chrome at all, only the
// student tokens and Inter. PlayerShell is a fixed overlay and is not changed; it inherits the CSS variables and font.
// PERFORMANCE_AUDIT S1: the rule lives in lib/lms/shellKind.ts (with the rest of the frame decision)
export { isPlayerRoute };
/** The player route's only frame: full viewport, Inter, `.student-theme`; no sidebar, tab bar, header or banners. */
const PLAYER_FRAME = cn(inter.variable, "student-theme min-h-screen font-sans");
/** Result and review pages outside the student shell (staff previews, sandbox) keep their wide column. */
const ATTEMPT_PAGE = /^\/courses\/[^/]+\/attempts\//;
// --- SF-1 end ---

// --- PERFORMANCE_AUDIT S1 begin --- (§5.1): the frame is decided once (`shellKindFor`), never drawn and then swapped.
/** `?view=` read at render time (null on the server and during hydration), so a cached answer decides at once. */
const noSubscribe = () => () => {};
const readView = () => new URLSearchParams(window.location.search).get("view");

/** The loading frame used while nothing decides the frame yet: brand bar + skeleton; no sidebar, no area pills. */
function NeutralTopBar({ lang }: { lang: string }) {
  return (
    <div data-testid="shell-neutral" className="border-b border-slate-200 bg-white">
      <div className={cn("flex h-14 items-center gap-3", SHELL_WIDTH)}>
        <Brand href={`/${lang}/courses`} />
        <Skeleton className="ml-auto h-9 w-9 rounded-full" />
      </div>
    </div>
  );
}

function NeutralBody({ label }: { label: string }) {
  return (
    <>
      <Skeleton className="mb-6 h-8 w-2/3 max-w-sm" />
      <LoadingState label={label} />
    </>
  );
}
// --- PERFORMANCE_AUDIT S1 end ---

/**
 * Top-level frame for every LMS page. Redirects signed-out users to login, loads MeOut once and provides it
 * through `useLmsMe()`. A 401 from MeOut (expired or pre-cutover token) signs out once and goes to login.
 */
export function LmsShell({ children }: { children: React.ReactNode }) {
  const { lang, setLang, t } = useTranslation();
  const { user, userProfile, loading: authLoading, signOut } = useAuth();
  const pathname = usePathname();
  const router = useRouter();
  const signedIn = !authLoading && !!user;
  const meState = useLmsMeLoader(signedIn);
  const { me } = meState;
  const unauthorized = meState.error?.status === 401;
  // PERFORMANCE_AUDIT S1: `?view=` is read from the URL at render time; ViewParam's state only re-renders the shell
  const [, setView] = useState<string | null>(null);
  const view = useSyncExternalStore(noSubscribe, readView, () => null);
  const cachedMe = useCachedMe(); // S1: the cached answer, readable from the render right after hydration
  const [tab, setTab] = useState<string | null>(null); // Student UI U2
  const [declaredCourse, setDeclaredCourse] = useState<CourseOut | null>(null); // Student UI U2
  const [declaredArea, setDeclared] = useState<DeclaredArea | null>(null);
  const declared = declaredArea?.area ?? null;
  const testStudent = !!userProfile?.is_test_student; // UX rework S1: Student view
  const consentBlocked = meState.error?.code === "consent_required"; // Phase 11 S3: the gate refuses the profile too

  useEffect(() => {
    if (!authLoading && !user) {
      router.replace(`/${lang}/login?redirect=${encodeURIComponent(pathname)}`);
    }
  }, [authLoading, user, lang, pathname, router]);

  const signedOut = useRef(false);
  useEffect(() => {
    if (unauthorized && !signedOut.current) {
      signedOut.current = true;
      void signOut();
    }
  }, [unauthorized, signOut]);

  const switchLang = (l: Language) => {
    setLang(l);
    const rest = pathname.replace(/^\/(en|ky|ru)(?=\/|$)/, "");
    const qs = typeof window !== "undefined" ? window.location.search : "";
    router.push(`/${l}${rest}${qs}`);
  };

  const logout = async () => {
    await signOut();
    if (testStudent) return; // UX rework S1: this only ended Student view; the teacher stays signed in
    router.replace(`/${lang}/login`);
  };

  // Role flags: MeOut is authoritative. The cached /auth/me profile is only the fallback when MeOut fails.
  const isAdmin = me ? me.is_platform_admin : !!userProfile?.is_platform_admin;
  const teacherStatus = me ? me.teacher_status : userProfile?.teacher_status;
  const canCreate = me ? me.can_create_courses : teacherStatus === "approved";
  const isTeacher = me ? me.is_teacher : teacherStatus === "approved";
  const hasTeaching = isTeacher || canCreate;
  // Owner feedback 2026-11-08 (item 2): people who teach see Learning only once they learn somewhere (MeOut decides;
  // until it loads, and for an older answer without the field, Learning stays). Student view is another user.
  const hideLearning = hidesLearning(me);

  // UX rework 2: the areas come from one answer, kept across pages (`useLmsMeLoader`), so the menu is the same everywhere.
  const orgs = me?.admin_organizations ?? [];
  const currentOrg = useCurrentOrg(); // item 4: the organization `OrgShell` has open (header switcher)
  const isGuardian = me ? !!me.is_guardian : !!userProfile?.is_guardian; // Phase 11
  const areasLoading = !me && !meState.error;

  const rest = pathname.replace(/^\/(en|ky|ru)(?=\/|$)/, "") || "/";
  // Same default as the /courses page (its Teaching tab opens first for teachers and course creators); without
  // Learning, `/courses?view=learning` is Teaching (the page replaces the URL); other student URLs still open
  const urlArea: AreaKey = urlAreaFor(rest, view, me);
  // A page's own declaration wins only where the URL does not decide (course pages).
  const activeArea: AreaKey = urlArea === "learning" && declared ? declared : urlArea;
  // Phase 8c S1: inside a course (declared area with hidden sections) no area shows its sub-menu
  const hideSections = urlArea === "learning" && !!declaredArea?.hideSections;

  const areas = useMemo<AppHeaderArea[]>(() => {
    const base = `/${lang}`;
    const list: AppHeaderArea[] = hideLearning ? [] : [
      { key: "learning", label: t("shell.areas.learning"), href: hasTeaching ? `${base}/courses?view=learning` : `${base}/courses`, icon: <BookOpen /> },
    ];
    if (hasTeaching || isAdmin) {
      const sections = [{ href: `${base}/courses?view=teaching`, label: t("shell.teaching.courses"), active: rest === "/courses" && urlArea === "teaching" }];
      if (canCreate) sections.push({ href: `${base}/courses/new`, label: t("lms.nav.create"), active: rest === "/courses/new" });
      if (canCreate || isAdmin) sections.push({ href: `${base}/grading-schemes`, label: t("lms.nav.gradingSchemes"), active: rest.startsWith("/grading-schemes") });
      sections.push({ href: `${base}/exam-templates`, label: t("examTemplates.nav.title"), active: rest.startsWith("/exam-templates") }); // Phase 7b S4
      list.push({ key: "teaching", label: t("shell.areas.teaching"), href: `${base}/courses?view=teaching`, icon: <Presentation />, sections });
    }
    // Item 4 (ADMIN_ORGS_DESIGN §2.5, D-ORG-3): a platform admin can manage every organization, so they always get the
    // switcher: their own organizations, the foreign one open right now (from `OrgShell`, no extra request) and
    // "All organizations" (Admin → Organizations). Never the whole list in the menu.
    const inOrg = (id: string) => rest === `/org/${id}` || rest.startsWith(`/org/${id}/`);
    const foreign = currentOrg && inOrg(currentOrg.id) && !orgs.some((o) => o.id === currentOrg.id) ? currentOrg : null;
    if (isAdmin) {
      list.push({
        key: "organization", label: t(orgs.length > 1 ? "shell.areas.organizations" : "shell.areas.organization"),
        href: orgs.length === 1 ? `${base}/org/${orgs[0].id}` : `${base}/org`, icon: <Building2 />,
        choices: [
          ...orgs.map((o) => ({ href: `${base}/org/${o.id}`, label: o.name, active: inOrg(o.id) })),
          ...(foreign ? [{ href: `${base}/org/${foreign.id}`, label: t("shell.areas.asPlatformAdmin", { name: foreign.name }), active: true }] : []),
          { href: `${base}/admin/organizations`, label: t("shell.areas.allOrganizations"), active: false, separated: true },
        ],
      });
    } else if (orgs.length === 1) {
      list.push({ key: "organization", label: t("shell.areas.organization"), href: `${base}/org/${orgs[0].id}`, icon: <Building2 /> });
    } else if (orgs.length > 1) {
      list.push({
        key: "organization", label: t("shell.areas.organizations"), href: `${base}/org`, icon: <Building2 />,
        choices: orgs.map((o) => ({ href: `${base}/org/${o.id}`, label: o.name, active: rest === `/org/${o.id}` || rest.startsWith(`/org/${o.id}/`) })),
      });
    }
    if (isGuardian) list.push({ key: "parent", label: t("privacy.nav.parent"), href: `${base}/parent`, icon: <Users /> }); // Phase 11
    if (isAdmin) list.push({ key: "platform", label: t("shell.areas.platform"), href: `${base}/admin`, icon: <ShieldCheck /> });
    return hideSections ? list.map((a) => ({ ...a, sections: undefined })) : list;
  }, [lang, t, hasTeaching, hideLearning, isAdmin, canCreate, isGuardian, me, rest, urlArea, hideSections, currentOrg]); // `orgs` comes from `me`

  // --- PERFORMANCE_AUDIT S1 begin --- (§5.1; replaces Student UI U2's `studentFrame` guess and the two pre-auth
  // skeletons): the frame comes from `shellKindFor` over the cached (or fresh) answer. Nothing known yet: the neutral
  // frame. When `/me/lms` fails, the cached /auth/me profile decides as before.
  const pathCourseId = courseIdOfPath(rest);
  const playerRoute = isPlayerRoute(rest);
  const knownMe: ShellMe | null = me ?? cachedMe;
  const fallbackMe: ShellMe | null = meState.error ? { is_teacher: isTeacher, can_create_courses: canCreate, is_platform_admin: isAdmin } : null;
  const shellMe = signedIn && !unauthorized ? knownMe ?? fallbackMe : null;
  const computedKind = shellKindFor({ rest, view, declared, me: shellMe });
  // Latched per page: a background refresh that would change the frame is applied on the next navigation, never
  // mid-page. The frame is recomputed when the URL changes, when the page declares its area and when the first
  // answer arrives (cold). A page whose area is still unknown keeps the frame it was opened from.
  const latchKey = `${pathname}?${view ?? ""}#${declared ?? ""}#${shellMe ? 1 : 0}`;
  const [latch, setLatch] = useState<{ key: string; kind: ShellKind } | null>(null);
  let kind: ShellKind = computedKind;
  if (latch && latch.key === latchKey) {
    kind = latch.kind;
  } else {
    if (computedKind === "neutral" && shellMe && (latch?.kind === "app" || latch?.kind === "student")) kind = latch.kind;
    setLatch({ key: latchKey, kind }); // render-time update: React renders again before anything is committed
  }
  const studentFrame = kind === "student";
  // Cold (nothing cached): the page renders hidden under the neutral frame, so its requests run alongside /me/lms
  const hideChildren = kind === "neutral" && !shellMe;
  // ...and so does the student shell's data when the URL and the cached profile say student (no extra round)
  const profileTeaches = userProfile?.teacher_status === "approved" || !!userProfile?.is_platform_admin;
  const guessStudent = hideChildren && !profileTeaches && areaFromUrl(rest, view) === "learning";
  const studentData = useStudentShellData({
    enabled: signedIn && !unauthorized && (studentFrame || guessStudent),
    pathCourseId, declared: declaredCourse, onHome: rest === "/courses", pathKey: rest,
  });

  if (authLoading || !user || unauthorized) {
    // SF-1: the player route waits in its own chrome-less frame
    if (playerRoute) {
      return <div className={PLAYER_FRAME}><LoadingState label={t("lms.common.loading")} className="px-4 py-6" /></div>;
    }
    // S1: one neutral frame for everyone (the server render and the first client render have no answer)
    return (
      <div className="min-h-screen bg-slate-50">
        <NeutralTopBar lang={lang} />
        <main className={cn("py-6 sm:py-8", SHELL_WIDTH)}><NeutralBody label={t("lms.common.loading")} /></main>
      </div>
    );
  }
  // --- PERFORMANCE_AUDIT S1 end ---

  const name = testStudent ? t("studentView.testStudentName") : me?.display_name || userProfile?.displayName || user.email || "";
  const email = testStudent ? name : me?.email || user.email || ""; // the header hides an email equal to the name
  const accountLinks = testStudent ? [] : [
    { href: `/${lang}/pro`, label: t("access.pro.menu"), icon: <KeyRound />, active: rest === "/pro" }, // F6b Pro
    { href: `/${lang}/privacy`, label: t("privacy.title"), icon: <Lock />, active: rest === "/privacy" }, // Phase 11 S3
  ];

  const meError = meState.error && !me && !consentBlocked ? meState.error : null;
  const gated = meError ? (
    <ErrorState message={t(lmsErrorKey(meError.code))} onRetry={() => void meState.reload()} />
  ) : consentBlocked && !gateOpenPath(rest) ? (
    <LoadingState label={t("lms.common.loading")} />
  ) : children;
  // SF-1 (§2.1): the player route renders with no chrome at all (no header, sidebar, tab bar or banners)
  if (playerRoute) {
    return (
      <AreaDeclareContext.Provider value={setDeclared}>
        <StudentCourseDeclareContext.Provider value={setDeclaredCourse}>
          <LmsMeProvider value={meState}>
            <StudentShellDataContext.Provider value={null}>
              <Suspense fallback={null}><ViewParam onChange={setView} onTab={setTab} /></Suspense>
              <div className={PLAYER_FRAME}>
                <main id="main" tabIndex={-1} className="focus:outline-none">{gated}</main>
              </div>
            </StudentShellDataContext.Provider>
          </LmsMeProvider>
        </StudentCourseDeclareContext.Provider>
      </AreaDeclareContext.Provider>
    );
  }
  const content = (
    <>
      {/* --- Phase 6 S4b / S8: invitation banner and notice stay under the header --- */}
      <PendingInvitationsBanner enabled={!!me && !testStudent} />
      <InvitationAcceptedNotice />
      {/* Phase 11 S3: the one small home-page line; never on the player's paths */}
      {rest === "/courses" && signedIn && !testStudent && !consentBlocked && <PrivacyBanner />}
      {gated}
    </>
  );
  const examColumn = !studentFrame && ATTEMPT_PAGE.test(rest);
  // Student UI U2: the same children in both frames (chrome slot, banner, main, tab bar slot), so React keeps <main>
  const studentProps = {
    data: studentData, rest, tab, user: { name, email }, accountLinks, onLanguageChange: switchLang,
    onLogout: () => void logout(), testStudent, otherAreas: areas.filter((a) => a.key !== "learning"),
  };
  return (
    <AreaDeclareContext.Provider value={setDeclared}>
      <StudentCourseDeclareContext.Provider value={setDeclaredCourse}>
      <LmsMeProvider value={meState}>
        <StudentShellDataContext.Provider value={studentFrame ? studentData : null}>
        <Suspense fallback={null}><ViewParam onChange={setView} onTab={setTab} /></Suspense>
        <div className={cn("min-h-screen bg-slate-50", studentFrame && STUDENT_FRAME)}>
          <a href="#main"
            className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-2 focus:z-50 focus:rounded-xl focus:bg-white focus:px-4 focus:py-3 focus:text-sm focus:font-semibold focus:text-brand-800 focus:shadow-lg">
            {t("shell.skipToContent")}
          </a>
          {studentFrame ? <StudentChrome {...studentProps} /> : kind === "neutral" ? <NeutralTopBar lang={lang} /> : (
            <AppHeader
              brandHref={`/${lang}/courses`}
              areas={areas}
              areasLoading={areasLoading}
              activeArea={activeArea}
              user={{ name, email }}
              accountLinks={accountLinks}
              onLanguageChange={switchLang}
              onLogout={() => void logout()}
              routeKey={pathname}
            />
          )}
          <StudentViewBanner />
          <main id="main" tabIndex={-1} className={studentFrame ? cn(STUDENT_MAIN, "focus:outline-none") : cn("py-6 focus:outline-none sm:py-8", SHELL_WIDTH)}>
            {/* S1: cold, the page renders hidden under the neutral skeleton (its requests start at once) */}
            {hideChildren ? <NeutralBody label={t("lms.common.loading")} /> : null}
            {/* UX rework (PUR-6): result and review outside the student shell (staff previews) keep their column; SF-1:
                inside the student shell the course layout gives them the reading column. S1: the two wrappers are
                always there (`contents` when unused), so a frame change never remounts the page */}
            <div className={hideChildren ? "hidden" : examColumn ? EXAM_COLUMN_OUTER : "contents"}>
              <div className={examColumn ? EXAM_COLUMN_INNER : "contents"}>{content}</div>
            </div>
          </main>
          {studentFrame ? <StudentTabBar {...studentProps} /> : null}
        </div>
        </StudentShellDataContext.Provider>
      </LmsMeProvider>
      </StudentCourseDeclareContext.Provider>
    </AreaDeclareContext.Provider>
  );
}
