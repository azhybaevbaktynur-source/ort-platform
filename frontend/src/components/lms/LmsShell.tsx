"use client";

import React, { createContext, Suspense, useContext, useEffect, useMemo, useRef, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { BookOpen, Building2, KeyRound, Lock, Presentation, ShieldCheck, Users } from "lucide-react";
import { useTranslation, type Language } from "@/lib/i18n/context";
import { useAuth } from "@/lib/auth-context";
import { gateOpenPath } from "@/lib/api"; // Phase 11 S3
import { LmsMeProvider, useLmsMeLoader } from "@/lib/lms/useLmsMe";
import { AppHeader, AreaPillsSkeleton, Brand, type AppHeaderArea, type AreaKey } from "@/components/ui/AppHeader";
import { ErrorState, LoadingState, SHELL_WIDTH, Skeleton, cn } from "@/components/ui";
import { EXAM_COLUMN_INNER, EXAM_COLUMN_OUTER } from "@/components/ui/shellWidth";
import { lmsErrorKey } from "./ErrorMessage";
import { PendingInvitationsBanner } from "./PendingInvitationsBanner"; // Phase 6 S4b
import { InvitationAcceptedNotice } from "./InvitationAcceptedNotice"; // Phase 6 S8
import { StudentViewBanner } from "./course/StudentViewBanner"; // UX rework S1
import { PrivacyBanner } from "@/components/privacy/PrivacyBanner"; // Phase 11 S3
// --- Student UI U2 ---
import type { CourseOut } from "@/lib/lms/types";
import { courseIdOfPath } from "@/lib/lms/studentNav";
import { STUDENT_FRAME, STUDENT_MAIN, STUDENT_SIDEBAR_BG, StudentChrome, StudentTabBar } from "./student/StudentShell";
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

/** ORT frames that never change (§2.4): the assessment lobby and every attempt page keep the AppHeader frame. */
const ORT_FRAME = [/^\/courses\/[^/]+\/assessments\/[^/]+$/, /^\/courses\/[^/]+\/attempts(\/|$)/];
const isOrtFrame = (rest: string) => ORT_FRAME.some((re) => re.test(rest));
// --- Student UI U2 end ---

/**
 * Area of a URL. `/courses` follows `?view=`; without it, `coursesDefault` (the tab `/courses` opens with:
 * Teaching for people who teach or create courses). Phase 6b S11b (UX 15).
 */
function areaFromUrl(rest: string, view: string | null, coursesDefault: AreaKey = "learning"): AreaKey {
  if (rest === "/admin" || rest.startsWith("/admin/")) return "platform";
  if (rest === "/org" || rest.startsWith("/org/")) return "organization";
  if (rest === "/parent" || rest.startsWith("/parent/")) return "parent"; // Phase 11
  if (rest.startsWith("/grading-schemes") || rest === "/courses/new" || rest === "/courses/trash") return "teaching";
  if (rest.startsWith("/exam-templates")) return "teaching"; // Phase 7b S4
  if (rest === "/courses") {
    if (view === "teaching" || view === "learning") return view;
    return coursesDefault;
  }
  return "learning";
}

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
  const [view, setView] = useState<string | null>(null);
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

  // UX rework 2: the areas come from one answer, kept across pages (`useLmsMeLoader`), so the menu is the same everywhere.
  const orgs = me?.admin_organizations ?? [];
  const isGuardian = me ? !!me.is_guardian : !!userProfile?.is_guardian; // Phase 11
  const areasLoading = !me && !meState.error;

  const rest = pathname.replace(/^\/(en|ky|ru)(?=\/|$)/, "") || "/";
  // Same default as the /courses page: its Teaching tab opens first for teachers and course creators.
  const coursesDefault: AreaKey = me && (me.is_teacher || me.is_platform_admin) && (me.is_teacher || me.can_create_courses) ? "teaching" : "learning";
  const urlArea = areaFromUrl(rest, view, coursesDefault);
  // A page's own declaration wins only where the URL does not decide (course pages).
  const activeArea: AreaKey = urlArea === "learning" && declared ? declared : urlArea;
  // Phase 8c S1: inside a course (declared area with hidden sections) no area shows its sub-menu
  const hideSections = urlArea === "learning" && !!declaredArea?.hideSections;

  const areas = useMemo<AppHeaderArea[]>(() => {
    const base = `/${lang}`;
    const list: AppHeaderArea[] = [
      { key: "learning", label: t("shell.areas.learning"), href: hasTeaching ? `${base}/courses?view=learning` : `${base}/courses`, icon: <BookOpen /> },
    ];
    if (hasTeaching || isAdmin) {
      const sections = [{ href: `${base}/courses?view=teaching`, label: t("shell.teaching.courses"), active: rest === "/courses" && urlArea === "teaching" }];
      if (canCreate) sections.push({ href: `${base}/courses/new`, label: t("lms.nav.create"), active: rest === "/courses/new" });
      if (canCreate || isAdmin) sections.push({ href: `${base}/grading-schemes`, label: t("lms.nav.gradingSchemes"), active: rest.startsWith("/grading-schemes") });
      sections.push({ href: `${base}/exam-templates`, label: t("examTemplates.nav.title"), active: rest.startsWith("/exam-templates") }); // Phase 7b S4
      list.push({ key: "teaching", label: t("shell.areas.teaching"), href: `${base}/courses?view=teaching`, icon: <Presentation />, sections });
    }
    if (orgs.length === 1) {
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
  }, [lang, t, hasTeaching, isAdmin, canCreate, isGuardian, me, rest, urlArea, hideSections]); // `orgs` comes from `me`

  // --- Student UI U2 begin --- (STUDENT_UI_DESIGN §2.1, §2.4): the Learning area gets the student shell, except the
  // ORT lobby and attempt routes. A course page of someone who teaches waits for the course's own declaration (a
  // course they teach is Teaching); the frames share one tree, so switching never remounts the page.
  const pathCourseId = courseIdOfPath(rest);
  const ortFrame = isOrtFrame(rest);
  const awaitingCourseArea = !!pathCourseId && !declared && (hasTeaching || isAdmin);
  const studentFrame = signedIn && !unauthorized && activeArea === "learning" && !ortFrame && !awaitingCourseArea;
  const studentData = useStudentShellData({
    enabled: studentFrame, pathCourseId, declared: declaredCourse, onHome: rest === "/courses", pathKey: rest,
  });
  // --- Student UI U2 end ---

  if (authLoading || !user || unauthorized) {
    // Student UI U2: a student path (the cached profile does not teach) gets the student frame's skeleton
    const teachesCached = userProfile?.teacher_status === "approved" || !!userProfile?.is_platform_admin;
    if (!ortFrame && urlArea === "learning" && !teachesCached) {
      return (
        <div className={cn("min-h-screen bg-slate-50", STUDENT_FRAME)}>
          <div aria-hidden="true" className={cn("fixed inset-y-0 left-0 hidden w-[264px] lg:block", STUDENT_SIDEBAR_BG)} />
          <div aria-hidden="true" className="flex h-14 items-center gap-2 border-b border-slate-200 bg-white px-4 lg:hidden">
            <span className="h-9 w-9 rounded-control bg-navy-800" />
            <Skeleton className="ml-auto h-9 w-9 rounded-full" />
          </div>
          <main className={STUDENT_MAIN}>
            <Skeleton className="mb-6 h-8 w-2/3 max-w-sm" />
            <LoadingState label={t("lms.common.loading")} />
          </main>
        </div>
      );
    }
    // Student finding S16: the frame (header + skeleton content) shows at once, never a blank screen.
    return (
      <div className="min-h-screen bg-slate-50">
        <header className="border-b border-slate-200 bg-white">
          <div className={cn("flex h-14 items-center gap-3 sm:h-16", SHELL_WIDTH)}>
            <Brand href={`/${lang}/courses`} />
            <AreaPillsSkeleton />
            <Skeleton className="ml-auto h-9 w-9 rounded-full" />
          </div>
        </header>
        <main className={cn("py-6 sm:py-8", SHELL_WIDTH)}>
          <Skeleton className="mb-6 h-8 w-2/3 max-w-sm" />
          <LoadingState label={t("lms.common.loading")} />
        </main>
      </div>
    );
  }

  const name = testStudent ? t("studentView.testStudentName") : me?.display_name || userProfile?.displayName || user.email || "";
  const email = testStudent ? name : me?.email || user.email || ""; // the header hides an email equal to the name
  const accountLinks = testStudent ? [] : [
    { href: `/${lang}/unlock`, label: t("access.menu"), icon: <KeyRound />, active: rest === "/unlock" }, // S3 access
    { href: `/${lang}/privacy`, label: t("privacy.title"), icon: <Lock />, active: rest === "/privacy" }, // Phase 11 S3
  ];

  const meError = meState.error && !me && !consentBlocked ? meState.error : null;
  const content = (
    <>
      {/* --- Phase 6 S4b / S8: invitation banner and notice stay under the header --- */}
      <PendingInvitationsBanner enabled={!!me && !testStudent} />
      <InvitationAcceptedNotice />
      {/* Phase 11 S3: the one small home-page line; never on the player's paths */}
      {rest === "/courses" && signedIn && !testStudent && !consentBlocked && <PrivacyBanner />}
      {meError ? (
        <ErrorState message={t(lmsErrorKey(meError.code))} onRetry={() => void meState.reload()} />
      ) : consentBlocked && !gateOpenPath(rest) ? (
        <LoadingState label={t("lms.common.loading")} />
      ) : children}
    </>
  );
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
          {studentFrame ? <StudentChrome {...studentProps} /> : (
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
            {/* UX rework (PUR-6): the attempt pages (result, review) keep their column; the player is its own overlay */}
            {/^\/courses\/[^/]+\/attempts(\/|$)/.test(rest)
              ? <div className={EXAM_COLUMN_OUTER}><div className={EXAM_COLUMN_INNER}>{content}</div></div>
              : content}
          </main>
          {studentFrame ? <StudentTabBar {...studentProps} /> : null}
        </div>
        </StudentShellDataContext.Provider>
      </LmsMeProvider>
      </StudentCourseDeclareContext.Provider>
    </AreaDeclareContext.Provider>
  );
}
