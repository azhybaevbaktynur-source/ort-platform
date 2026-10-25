"use client";

import React, { useEffect, useRef } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { GraduationCap, KeyRound, LayoutDashboard, LogOut, Plus, Scale, ShieldCheck, UserCircle, UserPlus } from "lucide-react";
import { useTranslation, type Language } from "@/lib/i18n/context";
import { useAuth } from "@/lib/auth-context";
import { LmsMeProvider, useLmsMeLoader } from "@/lib/lms/useLmsMe";
import { ErrorMessage } from "./ErrorMessage";
import { OrgNavLink } from "./org/OrgNavLink"; // Phase 6 S4

const LANGS: Language[] = ["en", "ru", "ky"];

/**
 * Top-level frame for every LMS page (courses/*, admin/*). Redirects signed-out users to login,
 * loads MeOut once and provides it through `useLmsMe()`. A 401 from MeOut (expired or pre-cutover
 * token) signs out and goes to login instead of showing an error.
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
    router.push(`/${l}${rest}`);
  };

  const logout = async () => {
    await signOut();
    router.replace(`/${lang}/login`);
  };

  if (authLoading || !user || unauthorized) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-50 text-sm text-slate-500" role="status">
        {t("lms.common.loading")}
      </div>
    );
  }

  // Role links: MeOut is authoritative; until it loads, the cached /auth/me profile avoids a flash.
  const isAdmin = me ? me.is_platform_admin : !!userProfile?.is_platform_admin;
  const teacherStatus = me ? me.teacher_status : userProfile?.teacher_status;
  const canCreate = me ? me.can_create_courses : teacherStatus === "approved";
  // Phase 6 S4: "I am a teacher" for everyone who cannot create courses yet (shows pending state too).
  const canRequestTeacher = !canCreate && !isAdmin;
  const name = me?.display_name || userProfile?.displayName || user.email;

  const linkCls = (href: string, exact = false) => {
    const active = exact ? pathname === href : pathname === href || pathname.startsWith(`${href}/`);
    return `inline-flex items-center gap-1.5 rounded-xl px-3 py-2 text-sm font-medium ${active ? "bg-brand-50 text-brand-700" : "text-slate-700 hover:bg-slate-100"}`;
  };
  const coursesHref = `/${lang}/courses`;
  return (
    <LmsMeProvider value={meState}>
      <div className="min-h-screen bg-slate-50">
        <header className="border-b border-slate-200 bg-white">
          <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-2 px-4 py-3">
            <Link href={coursesHref} className="mr-2 inline-flex items-center gap-2 text-base font-bold text-slate-900">
              <GraduationCap className="h-5 w-5 text-brand-600" aria-hidden="true" />
              {t("common.appName")}
            </Link>
            <nav aria-label={t("lms.nav.label")} className="order-last flex w-full flex-wrap items-center gap-1">
              <Link href={coursesHref} className={linkCls(coursesHref, true)}><GraduationCap className="h-4 w-4" aria-hidden="true" />{t("lms.nav.myCourses")}</Link>
              <Link href={`${coursesHref}#catalog`} className={linkCls(`${coursesHref}#catalog`)}><LayoutDashboard className="h-4 w-4" aria-hidden="true" />{t("lms.nav.catalog")}</Link>
              <Link href={`${coursesHref}/join`} className={linkCls(`${coursesHref}/join`)}><KeyRound className="h-4 w-4" aria-hidden="true" />{t("lms.nav.join")}</Link>
              {canCreate && (
                <Link href={`${coursesHref}/new`} className={linkCls(`${coursesHref}/new`)}><Plus className="h-4 w-4" aria-hidden="true" />{t("lms.nav.create")}</Link>
              )}
              {/* --- Phase 6 S4: "Become teacher" moved to the account group as "I am a teacher"; org admin link --- */}
              <OrgNavLink enabled={!!me} className={(href) => linkCls(href)} />
              {/* --- Phase 6 S4 end --- */}
              {(canCreate || isAdmin) && (
                <Link href={`/${lang}/grading-schemes`} className={linkCls(`/${lang}/grading-schemes`)}><Scale className="h-4 w-4" aria-hidden="true" />{t("lms.nav.gradingSchemes")}</Link>
              )}
              {isAdmin && (
                <Link href={`/${lang}/admin`} className={linkCls(`/${lang}/admin`)}><ShieldCheck className="h-4 w-4" aria-hidden="true" />{t("lms.nav.platformAdmin")}</Link>
              )}
            </nav>
            <div role="group" aria-label={t("common.language")} className="ml-auto flex gap-1">
              {LANGS.map((l) => (
                <button key={l} type="button" aria-pressed={l === lang} onClick={() => switchLang(l)}
                  className={`rounded-lg px-2.5 py-1 text-xs font-bold ${l === lang ? "bg-brand-600 text-white" : "bg-slate-100 text-slate-600 hover:bg-slate-200"}`}>
                  {l.toUpperCase()}
                </button>
              ))}
            </div>
            <div role="group" aria-label={t("lms.nav.account")} className="flex items-center gap-1">
              <span className="inline-flex max-w-[14rem] items-center gap-1.5 truncate px-2 text-sm text-slate-700" title={user.email}>
                <UserCircle className="h-4 w-4 flex-shrink-0 text-slate-500" aria-hidden="true" />
                <span className="truncate">{name}</span>
              </span>
              {/* --- Phase 6 S4 --- */}
              {canRequestTeacher && (
                <Link href={`/${lang}/teacher-access`} className={linkCls(`/${lang}/teacher-access`)}><UserPlus className="h-4 w-4" aria-hidden="true" />{t("teacherAccess.navLink")}</Link>
              )}
              {/* --- Phase 6 S4 end --- */}
              <button type="button" onClick={() => void logout()}
                className="inline-flex items-center gap-1.5 rounded-xl px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100">
                <LogOut className="h-4 w-4" aria-hidden="true" />{t("common.logout")}
              </button>
            </div>
          </div>
        </header>
        <main className="mx-auto max-w-6xl px-4 py-8">
          {meState.error && !me ? <ErrorMessage error={meState.error} onRetry={meState.reload} /> : children}
        </main>
      </div>
    </LmsMeProvider>
  );
}
