"use client";

// Phase 8c S3 (PHASE_8C_DESIGN §5.3): the Close/Back control of the object pages (assignment, page, quiz editor, ORT
// section builder) and the redirect stubs of the old object routes (§4.2 rows 4-8). One rule: a validated `?from=`
// path (`safeFrom`, the same rule as the player's `?return=`), never history; the label names the area of the target
// ("Back to Course", "Back to Assignments"), taken from the course sidebar's active link for that path.
import React, { useEffect } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { ArrowLeft } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { courseNavItems, courseNavRole, safeFrom, withFrom } from "@/lib/lms/nav";
import { useCourse } from "@/components/lms/CourseContext";
import { LinkButton, LoadingState } from "@/components/ui";

export interface ObjectNav {
  /** Where Close/Back goes: the validated `?from=`, else `fallback`. */
  backHref: string;
  /** "Back to Course" (or "Back" when the target is outside the course areas). */
  backLabel: string;
  /** The area name of the target ("Course", "Assignments"), for a breadcrumb. */
  placeLabel: string;
  /** This page's own path and query: the `from` of links leaving it. */
  here: string;
  /** The raw validated `from` (null when absent or refused), to carry it over to another URL of the same object. */
  from: string | null;
}

/** `fallback` is a full path (`/<lang>/courses/<id>/...`); the default is the Course page. */
export function useObjectNav(fallback?: string): ObjectNav {
  const { lang, t } = useTranslation();
  const { course } = useCourse();
  const pathname = usePathname() ?? "";
  const search = useSearchParams();
  const base = `/${lang}/courses/${course.id}`;
  const fb = fallback ?? base;
  const raw = search?.get("from") ?? null;
  const backHref = safeFrom(raw, fb);
  const from = raw && backHref === raw ? raw : null;
  const backPath = backHref.split(/[?#]/)[0];
  const active = courseNavItems(course, courseNavRole(course), backPath, t).find((i) => i.active);
  const qs = search?.toString() ?? "";
  return {
    backHref,
    backLabel: active ? t("assignments.page.backTo", { place: active.label }) : t("common.back"),
    placeLabel: active ? active.label : t("common.back"),
    here: `${pathname}${qs ? `?${qs}` : ""}`,
    from,
  };
}

/** `href` with `from` appended when there is one. */
export function maybeFrom(href: string, from: string | null | undefined): string {
  return from ? withFrom(href, from) : href;
}

/** The one secondary control at the top left of an object page. */
export function BackLink({ nav }: { nav: ObjectNav }) {
  return (
    <div className="mb-3">
      <LinkButton variant="secondary" size="sm" href={nav.backHref} leftIcon={<ArrowLeft aria-hidden="true" className="h-4 w-4" />}>
        {nav.backLabel}
      </LinkButton>
    </div>
  );
}

/**
 * Redirect stub of an old object route (kept one phase, removed at the Phase 9 kickoff): `router.replace` to `target`
 * with the old query string carried over and `set` applied on top (route-level, client side, §4.2).
 */
export function RedirectStub({ target, set }: { target: string; set: Record<string, string> }) {
  const { t } = useTranslation();
  const router = useRouter();
  const key = JSON.stringify(set);
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    for (const [k, v] of Object.entries(JSON.parse(key) as Record<string, string>)) params.set(k, v);
    const qs = params.toString();
    router.replace(`${target}${qs ? `?${qs}` : ""}${window.location.hash}`);
  }, [router, target, key]);
  return <LoadingState label={t("lms.common.loading")} />;
}
