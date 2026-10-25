"use client";

import React, { createContext, Suspense, useContext, useEffect, useMemo, useRef, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { BookOpen, Building2, Presentation, ShieldCheck, UserPlus } from "lucide-react";
import { useTranslation, type Language } from "@/lib/i18n/context";
import { useAuth } from "@/lib/auth-context";
import { LmsMeProvider, useLmsMeLoader } from "@/lib/lms/useLmsMe";
import { listMyOrganizations, type MyOrganizationOut } from "@/lib/lms/organizations";
import { AppHeader, Brand, type AppHeaderArea, type AreaKey } from "@/components/ui/AppHeader";
import { ErrorState, LoadingState, Skeleton } from "@/components/ui";
import { lmsErrorKey } from "./ErrorMessage";
import { PendingInvitationsBanner } from "./PendingInvitationsBanner"; // Phase 6 S4b
import { InvitationAcceptedNotice } from "./InvitationAcceptedNotice"; // Phase 6 S8

/*
 * Phase 6b S5b: the frame of every signed-in page (courses/*, admin/*, org/*, grading-schemes, teacher-access).
 * `AppHeader` with the area switcher replaces the old link rows. Area URLs: Learning `/courses` (or
 * `/courses?view=learning` for people who also teach), Teaching `/courses?view=teaching`, Organization
 * `/org/{id}` (or the picker `/org`), Platform `/admin`.
 */

type DeclareArea = (area: AreaKey | null) => void;
const AreaDeclareContext = createContext<DeclareArea>(() => {});

/**
 * Lets a page tell the header which area it belongs to when the URL alone cannot (a course page is
 * Teaching for its staff and Learning for its students). Pass null to fall back to the URL rule.
 */
export function useDeclareArea(area: AreaKey | null) {
  const declare = useContext(AreaDeclareContext);
  useEffect(() => {
    declare(area);
    return () => declare(null);
  }, [area, declare]);
}

/** Reads `?view=` (needs a Suspense boundary for static pages). */
function ViewParam({ onChange }: { onChange: (v: string | null) => void }) {
  const params = useSearchParams();
  const view = params.get("view");
  useEffect(() => { onChange(view); }, [view, onChange]);
  return null;
}

function areaFromUrl(rest: string, view: string | null): AreaKey {
  if (rest === "/admin" || rest.startsWith("/admin/")) return "platform";
  if (rest === "/org" || rest.startsWith("/org/")) return "organization";
  if (rest.startsWith("/grading-schemes") || rest === "/courses/new" || rest === "/courses/trash") return "teaching";
  if (rest === "/courses" && view === "teaching") return "teaching";
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
  const [declared, setDeclared] = useState<AreaKey | null>(null);
  const [orgs, setOrgs] = useState<MyOrganizationOut[]>([]);

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

  // Organizations the person administers (Organization area). Navigation only: fails silently.
  useEffect(() => {
    if (!me) return;
    let alive = true;
    listMyOrganizations()
      .then((rows) => { if (alive) setOrgs((Array.isArray(rows) ? rows : []).filter((o) => o.role === "org_admin")); })
      .catch(() => { if (alive) setOrgs([]); });
    return () => { alive = false; };
  }, [me]);

  const switchLang = (l: Language) => {
    setLang(l);
    const rest = pathname.replace(/^\/(en|ky|ru)(?=\/|$)/, "");
    const qs = typeof window !== "undefined" ? window.location.search : "";
    router.push(`/${l}${rest}${qs}`);
  };

  const logout = async () => {
    await signOut();
    router.replace(`/${lang}/login`);
  };

  // Role flags: MeOut is authoritative; until it loads, the cached /auth/me profile avoids a flash.
  const isAdmin = me ? me.is_platform_admin : !!userProfile?.is_platform_admin;
  const teacherStatus = me ? me.teacher_status : userProfile?.teacher_status;
  const canCreate = me ? me.can_create_courses : teacherStatus === "approved";
  // Phase 6 S8 (UX S1): "I am a teacher" only for people who teach nowhere yet.
  const isTeacher = me ? me.is_teacher : teacherStatus === "approved";
  const hasTeaching = isTeacher || canCreate;
  const canRequestTeacher = !isAdmin && !isTeacher;

  const rest = pathname.replace(/^\/(en|ky|ru)(?=\/|$)/, "") || "/";
  const urlArea = areaFromUrl(rest, view);
  // A page's own declaration wins only where the URL does not decide (course pages).
  const activeArea: AreaKey = urlArea === "learning" && declared ? declared : urlArea;

  const areas = useMemo<AppHeaderArea[]>(() => {
    const base = `/${lang}`;
    const list: AppHeaderArea[] = [
      { key: "learning", label: t("shell.areas.learning"), href: hasTeaching ? `${base}/courses?view=learning` : `${base}/courses`, icon: <BookOpen /> },
    ];
    if (hasTeaching || isAdmin) {
      const sections = [{ href: `${base}/courses?view=teaching`, label: t("shell.teaching.courses"), active: rest === "/courses" && view === "teaching" }];
      if (canCreate) sections.push({ href: `${base}/courses/new`, label: t("lms.nav.create"), active: rest === "/courses/new" });
      if (canCreate || isAdmin) sections.push({ href: `${base}/grading-schemes`, label: t("lms.nav.gradingSchemes"), active: rest.startsWith("/grading-schemes") });
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
    if (isAdmin) list.push({ key: "platform", label: t("shell.areas.platform"), href: `${base}/admin`, icon: <ShieldCheck /> });
    return list;
  }, [lang, t, hasTeaching, isAdmin, canCreate, orgs, rest, view]);

  if (authLoading || !user || unauthorized) {
    // Student finding S16: the frame (header + skeleton content) shows at once, never a blank screen.
    return (
      <div className="min-h-screen bg-slate-50">
        <header className="border-b border-slate-200 bg-white">
          <div className="mx-auto flex h-14 max-w-6xl items-center gap-3 px-4 sm:h-16">
            <Brand href={`/${lang}/courses`} />
            <Skeleton className="ml-auto h-9 w-9 rounded-full" />
          </div>
        </header>
        <main className="mx-auto max-w-6xl px-4 py-6 sm:py-8">
          <Skeleton className="mb-6 h-8 w-2/3 max-w-sm" />
          <LoadingState label={t("lms.common.loading")} />
        </main>
      </div>
    );
  }

  const name = me?.display_name || userProfile?.displayName || user.email || "";
  const email = me?.email || user.email || "";
  const accountLinks = canRequestTeacher
    ? [{ href: `/${lang}/teacher-access`, label: t("teacherAccess.navLink"), icon: <UserPlus />, active: rest === "/teacher-access" }]
    : [];

  const meError = meState.error && !me ? meState.error : null;
  return (
    <AreaDeclareContext.Provider value={setDeclared}>
      <LmsMeProvider value={meState}>
        <Suspense fallback={null}><ViewParam onChange={setView} /></Suspense>
        <div className="min-h-screen bg-slate-50">
          <a href="#main"
            className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-2 focus:z-50 focus:rounded-xl focus:bg-white focus:px-4 focus:py-3 focus:text-sm focus:font-semibold focus:text-brand-800 focus:shadow-lg">
            {t("shell.skipToContent")}
          </a>
          <AppHeader
            brandHref={`/${lang}/courses`}
            areas={areas}
            activeArea={activeArea}
            user={{ name, email }}
            accountLinks={accountLinks}
            onLanguageChange={switchLang}
            onLogout={() => void logout()}
            routeKey={pathname}
          />
          <main id="main" tabIndex={-1} className="mx-auto max-w-6xl px-4 py-6 focus:outline-none sm:py-8">
            {/* --- Phase 6 S4b / S8: invitation banner and notice stay under the header --- */}
            <PendingInvitationsBanner enabled={!!me} />
            <InvitationAcceptedNotice />
            {meError ? (
              <ErrorState message={t(lmsErrorKey(meError.code))} onRetry={() => void meState.reload()} />
            ) : children}
          </main>
        </div>
      </LmsMeProvider>
    </AreaDeclareContext.Provider>
  );
}
