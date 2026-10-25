"use client";

import React, { useCallback, useEffect, useId, useRef, useState } from "react";
import Link from "next/link";
import { Check, ChevronDown, GraduationCap, LogOut } from "lucide-react";
import { useTranslation, type Language } from "@/lib/i18n/context";
import { cn, focusRing } from "./utils";

/*
 * App header (Phase 6b S5b, PHASE_6_DESIGN.md §3 and §8.3): brand, area switcher with only the areas the
 * person has, and an account menu (name, email, language, extra links, log out). One row of at most
 * 64 px on every width; below 1024 px the switcher and the account become two compact menu buttons.
 */

export type AreaKey = "learning" | "teaching" | "organization" | "platform";

export interface AppHeaderLink {
  href: string;
  label: string;
  active?: boolean;
}

export interface AppHeaderArea {
  key: AreaKey;
  label: string;
  href: string;
  icon?: React.ReactNode;
  /** Choices inside the area (the organizations of a person who administers several): a dropdown on desktop. */
  choices?: AppHeaderLink[];
  /** Sections of the area, shown next to the switcher while the area is active (desktop) and under it in the phone menu. */
  sections?: AppHeaderLink[];
}

export interface AppHeaderProps {
  brandHref: string;
  areas: AppHeaderArea[];
  activeArea: AreaKey | null;
  user: { name: string; email: string };
  /** Extra links in the account menu (for example "I am a teacher"). */
  accountLinks?: (AppHeaderLink & { icon?: React.ReactNode })[];
  onLanguageChange: (lang: Language) => void;
  onLogout: () => void;
  /** Closes open menus when it changes (pass the pathname). */
  routeKey?: string;
}

const LANGS: Language[] = ["en", "ky", "ru"];

/** Brand mark: icon + `common.appName` (+ `landing.badge` as a tagline when asked). Shared by the auth pages. */
export function Brand({ href, hideNameOnPhone = false, tagline = false, className }: { href: string; hideNameOnPhone?: boolean; tagline?: boolean; className?: string }) {
  const { t } = useTranslation();
  return (
    <Link href={href} aria-label={hideNameOnPhone ? t("common.appName") : undefined}
      className={cn("inline-flex min-h-11 min-w-0 shrink-0 items-center gap-2.5 rounded-xl", focusRing, className)}>
      <span aria-hidden="true" className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-brand-600 text-white shadow-sm">
        <GraduationCap className="h-5 w-5" />
      </span>
      <span className={cn("min-w-0", hideNameOnPhone && "hidden sm:block")}>
        <span className="block truncate text-base font-bold leading-5 text-slate-900">{t("common.appName")}</span>
        {tagline && <span className="block text-xs leading-4 text-slate-600">{t("landing.badge")}</span>}
      </span>
    </Link>
  );
}

/** Open/close state of a header popover: closes on Escape (focus back to the button), outside click and route change. */
function usePopover(routeKey?: string) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  useEffect(() => { setOpen(false); }, [routeKey]);
  useEffect(() => {
    if (!open) return;
    const onDown = (e: PointerEvent) => { if (!rootRef.current?.contains(e.target as Node)) setOpen(false); };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") { setOpen(false); buttonRef.current?.focus(); }
    };
    document.addEventListener("pointerdown", onDown);
    document.addEventListener("keydown", onKey);
    return () => { document.removeEventListener("pointerdown", onDown); document.removeEventListener("keydown", onKey); };
  }, [open]);
  const onBlur = useCallback((e: React.FocusEvent) => {
    const next = e.relatedTarget as Node | null;
    if (next && !rootRef.current?.contains(next)) setOpen(false);
  }, []);
  return { open, setOpen, rootRef, buttonRef, onBlur };
}

const PANEL = "absolute top-full z-40 mt-1 rounded-2xl border border-slate-200 bg-white p-2 shadow-lg";
const ITEM = "flex min-h-11 w-full items-center gap-3 rounded-xl px-3 text-left text-sm font-medium leading-5";

function MenuLink({ href, active, children, onNavigate, indent = false }: { href: string; active?: boolean; children: React.ReactNode; onNavigate: () => void; indent?: boolean }) {
  return (
    <Link href={href} aria-current={active ? "page" : undefined} onClick={onNavigate}
      className={cn(ITEM, focusRing, "focus-visible:ring-offset-0", indent && "pl-10",
        active ? "bg-brand-50 text-brand-800" : "text-slate-800 hover:bg-slate-100")}>
      <span className="min-w-0 flex-1 break-words">{children}</span>
      {active && <Check aria-hidden="true" className="h-4 w-4 shrink-0 text-brand-700" />}
    </Link>
  );
}

/** Phone: one button with the current area that opens the list of areas (and their sections / organizations). */
function AreaMenu({ areas, activeArea, routeKey, className }: { areas: AppHeaderArea[]; activeArea: AreaKey | null; routeKey?: string; className?: string }) {
  const { t } = useTranslation();
  const pop = usePopover(routeKey);
  const panelId = useId();
  const current = areas.find((a) => a.key === activeArea) ?? areas[0];
  const close = () => pop.setOpen(false);
  return (
    <div ref={pop.rootRef} onBlur={pop.onBlur} className={cn("min-w-0", className)}>
      <button ref={pop.buttonRef} type="button" aria-expanded={pop.open} aria-controls={panelId} onClick={() => pop.setOpen(!pop.open)}
        className={cn("inline-flex min-h-11 max-w-full items-center gap-1.5 rounded-xl border border-slate-300 bg-white px-3 text-sm font-semibold text-slate-800 shadow-sm hover:bg-slate-50", focusRing)}>
        <span className="sr-only">{t("shell.areas.switch")}: </span>
        {current.icon && <span aria-hidden="true" className="inline-flex shrink-0 text-brand-700 [&>svg]:h-4 [&>svg]:w-4">{current.icon}</span>}
        <span className="min-w-0 truncate">{current.label}</span>
        <ChevronDown aria-hidden="true" className={cn("h-4 w-4 shrink-0 text-slate-600 transition-transform", pop.open && "rotate-180")} />
      </button>
      {pop.open && (
        <nav id={panelId} aria-label={t("shell.areas.label")} className={cn(PANEL, "left-4 right-4 max-h-[calc(100dvh-5rem)] overflow-y-auto")}>
          <ul className="space-y-0.5">
            {areas.map((a) => (
              <li key={a.key}>
                <Link href={a.href} aria-current={a.key === activeArea ? "true" : undefined} onClick={close}
                  className={cn(ITEM, focusRing, "focus-visible:ring-offset-0",
                    a.key === activeArea ? "bg-brand-50 font-semibold text-brand-800" : "text-slate-800 hover:bg-slate-100")}>
                  {a.icon && <span aria-hidden="true" className="inline-flex shrink-0 text-brand-700 [&>svg]:h-5 [&>svg]:w-5">{a.icon}</span>}
                  <span className="min-w-0 flex-1 break-words">{a.label}</span>
                  {a.key === activeArea && <Check aria-hidden="true" className="h-4 w-4 shrink-0 text-brand-700" />}
                </Link>
                {(a.choices?.length || a.sections?.length) ? (
                  <ul className="mt-0.5 space-y-0.5">
                    {[...(a.choices ?? []), ...(a.sections ?? [])].map((s) => (
                      <li key={s.href}><MenuLink href={s.href} active={s.active} onNavigate={close} indent>{s.label}</MenuLink></li>
                    ))}
                  </ul>
                ) : null}
              </li>
            ))}
          </ul>
        </nav>
      )}
    </div>
  );
}

const PILL = "inline-flex min-h-11 items-center gap-1.5 whitespace-nowrap rounded-xl px-3 text-sm font-semibold leading-5 transition-colors";
const PILL_ON = "bg-brand-50 text-brand-800";
const PILL_OFF = "text-slate-700 hover:bg-slate-100 hover:text-slate-900";

/** Desktop pill with a dropdown of choices (several organizations). */
function AreaDropdown({ area, active, routeKey }: { area: AppHeaderArea; active: boolean; routeKey?: string }) {
  const pop = usePopover(routeKey);
  const panelId = useId();
  return (
    <div ref={pop.rootRef} onBlur={pop.onBlur} className="relative">
      <button ref={pop.buttonRef} type="button" aria-expanded={pop.open} aria-controls={panelId} onClick={() => pop.setOpen(!pop.open)}
        className={cn(PILL, focusRing, active ? PILL_ON : PILL_OFF)}>
        {area.icon && <span aria-hidden="true" className="inline-flex [&>svg]:h-4 [&>svg]:w-4">{area.icon}</span>}
        {area.label}
        <ChevronDown aria-hidden="true" className={cn("h-4 w-4 transition-transform", pop.open && "rotate-180")} />
      </button>
      {pop.open && (
        <div id={panelId} className={cn(PANEL, "left-0 w-72")}>
          <ul className="space-y-0.5">
            {(area.choices ?? []).map((c) => (
              <li key={c.href}><MenuLink href={c.href} active={c.active} onNavigate={() => pop.setOpen(false)}>{c.label}</MenuLink></li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function initials(name: string): string {
  const parts = name.replace(/@.*/, "").split(/[\s._-]+/).filter(Boolean);
  const s = (parts[0]?.[0] ?? "") + (parts.length > 1 ? parts[parts.length - 1][0] : "");
  return (s || name[0] || "?").toUpperCase();
}

function AccountMenu({ user, links, onLanguageChange, onLogout, routeKey }: {
  user: AppHeaderProps["user"]; links: NonNullable<AppHeaderProps["accountLinks"]>; onLanguageChange: (l: Language) => void; onLogout: () => void; routeKey?: string;
}) {
  const { lang, t } = useTranslation();
  const pop = usePopover(routeKey);
  const panelId = useId();
  const langLabelId = useId();
  const langName: Record<Language, string> = { en: t("common.english"), ky: t("common.kyrgyz"), ru: t("common.russian") };
  return (
    <div ref={pop.rootRef} onBlur={pop.onBlur} className="shrink-0">
      <button ref={pop.buttonRef} type="button" aria-expanded={pop.open} aria-controls={panelId} onClick={() => pop.setOpen(!pop.open)}
        aria-label={t("shell.account.menu", { name: user.name })}
        className={cn("inline-flex min-h-11 items-center gap-2 rounded-xl px-1 text-sm font-medium text-slate-800 hover:bg-slate-100 lg:pr-2", focusRing)}>
        <span aria-hidden="true" className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-slate-800 text-sm font-semibold text-white">{initials(user.name)}</span>
        <span aria-hidden="true" className="hidden max-w-[12rem] truncate lg:block">{user.name}</span>
        <ChevronDown aria-hidden="true" className={cn("hidden h-4 w-4 text-slate-600 transition-transform lg:block", pop.open && "rotate-180")} />
      </button>
      {pop.open && (
        <div id={panelId} className={cn(PANEL, "left-4 right-4 sm:left-auto sm:right-4 sm:w-80")}>
          <div className="px-3 pb-3 pt-2">
            <p className="text-xs font-medium uppercase tracking-wide text-slate-600">{t("shell.account.signedInAs")}</p>
            <p className="mt-1 break-words text-base font-semibold leading-6 text-slate-900">{user.name}</p>
            {user.email !== user.name && <p className="break-all text-sm leading-5 text-slate-600">{user.email}</p>}
          </div>
          <div className="border-t border-slate-100 px-3 py-3">
            <p id={langLabelId} className="mb-2 text-sm font-medium text-slate-800">{t("shell.account.language")}</p>
            <div role="group" aria-labelledby={langLabelId} className="grid grid-cols-3 gap-1 rounded-xl bg-slate-100 p-1">
              {LANGS.map((l) => (
                <button key={l} type="button" aria-pressed={l === lang} lang={l} title={langName[l]} onClick={() => onLanguageChange(l)}
                  className={cn("min-h-11 rounded-lg px-2 text-sm font-semibold", focusRing, "focus-visible:ring-offset-0",
                    l === lang ? "bg-white text-brand-800 shadow-sm" : "text-slate-700 hover:text-slate-900")}>
                  {l.toUpperCase()}<span className="sr-only"> {langName[l]}</span>
                </button>
              ))}
            </div>
          </div>
          {links.length > 0 && (
            <ul className="space-y-0.5 border-t border-slate-100 pt-2">
              {links.map((l) => (
                <li key={l.href}>
                  <Link href={l.href} aria-current={l.active ? "page" : undefined} onClick={() => pop.setOpen(false)}
                    className={cn(ITEM, focusRing, "focus-visible:ring-offset-0", l.active ? "bg-brand-50 text-brand-800" : "text-slate-800 hover:bg-slate-100")}>
                    {l.icon && <span aria-hidden="true" className="inline-flex shrink-0 text-slate-600 [&>svg]:h-5 [&>svg]:w-5">{l.icon}</span>}
                    <span className="min-w-0 flex-1 break-words">{l.label}</span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
          <div className="mt-2 border-t border-slate-100 pt-2">
            <button type="button" onClick={() => { pop.setOpen(false); onLogout(); }}
              className={cn(ITEM, focusRing, "focus-visible:ring-offset-0 text-slate-800 hover:bg-slate-100")}>
              <LogOut aria-hidden="true" className="h-5 w-5 shrink-0 text-slate-600" />
              {t("common.logout")}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

/** The one header of the signed-in app. Areas with a single entry (only Learning) hide the switcher. */
export function AppHeader({ brandHref, areas, activeArea, user, accountLinks = [], onLanguageChange, onLogout, routeKey }: AppHeaderProps) {
  const { t } = useTranslation();
  const multi = areas.length > 1;
  const active = areas.find((a) => a.key === activeArea);
  return (
    <header className="border-b border-slate-200 bg-white">
      <div className="relative mx-auto flex h-14 max-w-6xl items-center gap-2 px-4 sm:h-16 sm:gap-3">
        <Brand href={brandHref} hideNameOnPhone={multi} />
        {multi && (
          <>
            <AreaMenu areas={areas} activeArea={activeArea} routeKey={routeKey} className="lg:hidden" />
            <nav aria-label={t("shell.areas.label")} className="ml-2 hidden min-w-0 items-center gap-1 lg:flex">
              <ul className="flex items-center gap-1">
                {areas.map((a) => (
                  <li key={a.key}>
                    {a.choices && a.choices.length > 0 ? (
                      <AreaDropdown area={a} active={a.key === activeArea} routeKey={routeKey} />
                    ) : (
                      <Link href={a.href} aria-current={a.key === activeArea ? "true" : undefined}
                        className={cn(PILL, focusRing, a.key === activeArea ? PILL_ON : PILL_OFF)}>
                        {a.icon && <span aria-hidden="true" className="inline-flex [&>svg]:h-4 [&>svg]:w-4">{a.icon}</span>}
                        {a.label}
                      </Link>
                    )}
                  </li>
                ))}
              </ul>
              {active?.sections && active.sections.length > 0 && (
                <ul aria-label={active.label} className="ml-1 flex items-center gap-1 border-l border-slate-200 pl-2">
                  {active.sections.map((s) => (
                    <li key={s.href}>
                      <Link href={s.href} aria-current={s.active ? "page" : undefined}
                        className={cn(PILL, "font-medium", focusRing, s.active ? "text-brand-800 underline decoration-2 underline-offset-8" : PILL_OFF)}>
                        {s.label}
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </nav>
          </>
        )}
        <div className="ml-auto flex items-center">
          <AccountMenu user={user} links={accountLinks} onLanguageChange={onLanguageChange} onLogout={onLogout} routeKey={routeKey} />
        </div>
      </div>
    </header>
  );
}
