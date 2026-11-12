"use client";

// Step 3b S2 (CATALOG_AND_TEACHERS_DESIGN 2.6): Записи → «Каталог платформы». The course's place in the catalog list,
// decided by the platform admin: off → request; pending → withdraw; listed → remove (confirmed); declined → the
// admin's note and resend; blocked → no button. Platform and template-locked (ORT) courses have no request: the
// platform lists them. The server decides every transition (`courses/listing.py`); this card only reflects it.
import React, { useState } from "react";
import Link from "next/link";
import { useTranslation } from "@/lib/i18n/context";
import { formatJoinCode, requestListing, withdrawListing } from "@/lib/lms/courses";
import { LISTING_TONE, listingActions, listingMissing, missingFromError } from "@/lib/lms/listing";
import { templateUi } from "@/lib/lms/templates";
import { pickLocalized } from "@/lib/lms/localized";
import { fmtApiDate } from "@/lib/format";
import type { CourseStaffOut, ListingState } from "@/lib/lms/types";
import { ErrorMessage } from "@/components/lms/ErrorMessage";
import { Badge, Button, Card, ConfirmDialog, cn, focusRing, toast } from "@/components/ui";

export function CatalogListingCard({ course, onSaved }: { course: CourseStaffOut; onSaved: (c: CourseStaffOut) => void }) {
  const { lang, t } = useTranslation();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [confirmRemove, setConfirmRemove] = useState(false);
  const listing = course.listing ?? { state: "off" as ListingState, requested_at: null, decided_at: null, note: null, content_changed: false };
  const state = listing.state;
  const locked = templateUi(course).locked;
  const platform = !!course.is_platform_course;
  const managedByPlatform = locked || platform;
  const serverMissing = missingFromError(error);
  const missing = serverMissing ?? ((state === "off" || state === "declined") && !managedByPlatform ? listingMissing(course) : []);
  const date = (v: string | null) => fmtApiDate(v, lang) || "—";
  const linkOpen = course.visibility === "catalog" && course.status === "published" && state !== "blocked";

  const run = async (kind: "request" | "withdraw" | "remove") => {
    setBusy(true);
    setError(null);
    try {
      const updated = kind === "request" ? await requestListing(course.id) : await withdrawListing(course.id);
      onSaved(updated);
      toast.success(t(kind === "request" ? "catalog.listing.toast.requested" : kind === "remove" ? "catalog.listing.toast.removed" : "catalog.listing.toast.withdrawn"));
      setConfirmRemove(false);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };

  // the off line names the join code only while it works (published, «По коду приглашения»)
  const codeWorks = course.status === "published" && course.enrollment_mode === "invite_code";
  const offKey = course.visibility === "catalog" ? (codeWorks ? "catalog.listing.off" : "catalog.listing.offLink")
    : codeWorks ? "catalog.listing.offPrivate" : "catalog.listing.offHidden";
  const text = state === "off"
    ? t(offKey, { code: formatJoinCode(course.join_code) })
    : state === "pending" ? t("catalog.listing.pending", { date: date(listing.requested_at) })
      : state === "listed" ? t("catalog.listing.listed", { date: date(listing.decided_at) })
        : state === "declined" ? t("catalog.listing.declined", { date: date(listing.decided_at) })
          : t("catalog.listing.blocked", { date: date(listing.decided_at) });

  const actions = managedByPlatform ? [] : listingActions(state);
  const label = { request: "catalog.listing.request", withdraw: "catalog.listing.withdraw", remove: "catalog.listing.remove", resend: "catalog.listing.resend" } as const;

  return (
    <Card title={t("catalog.listing.title")} data-testid="catalog-listing" data-state={state}>
      <div className="space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone={LISTING_TONE[state]}>{t(`catalog.listing.states.${state}`)}</Badge>
        </div>
        <p className="text-sm leading-6 text-slate-700">{text}</p>
        {state === "declined" && listing.note && (
          <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm leading-6 text-amber-900">
            <p className="font-medium">{t("catalog.listing.noteLabel")}</p>
            <p className="whitespace-pre-wrap break-words">{listing.note}</p>
          </div>
        )}
        {state === "listed" && listing.content_changed && (
          <p className="text-sm leading-6 text-amber-700">{t("catalog.listing.contentChanged")}</p>
        )}
        {managedByPlatform && (
          <p className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm leading-6 text-slate-700">
            {t(locked ? "catalog.listing.lockedNote" : "catalog.listing.platformNote")}
          </p>
        )}
        {actions.length > 0 && missing.length > 0 && (
          <div className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm leading-6 text-slate-700" data-testid="listing-missing">
            <p className="font-medium text-slate-900">{t("catalog.listing.incomplete.heading")}</p>
            <ul className="mt-1 list-disc space-y-0.5 pl-5">
              {missing.map((m) => <li key={m}>{t(`catalog.listing.incomplete.${m}`)}</li>)}
            </ul>
          </div>
        )}
        {error && !serverMissing && !confirmRemove ? <ErrorMessage error={error} /> : null}
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          {actions.map((a) => (
            <Button key={a} size="sm" variant={a === "request" || a === "resend" ? "primary" : "secondary"} loading={busy}
              disabled={busy || ((a === "request" || a === "resend") && missing.length > 0)}
              onClick={() => (a === "remove" ? (setError(null), setConfirmRemove(true)) : void run(a === "resend" ? "request" : a))}>
              {t(label[a])}
            </Button>
          ))}
          {linkOpen && (
            <Link href={`/${lang}/courses/catalog/${course.id}`} className={cn("inline-flex min-h-11 items-center text-sm font-medium text-brand-700 hover:underline sm:min-h-0", focusRing)}>
              {t("catalog.listing.openLanding")}
            </Link>
          )}
          <Link href={`/${lang}/courses/catalog`} className={cn("inline-flex min-h-11 items-center text-sm font-medium text-brand-700 hover:underline sm:min-h-0", focusRing)}>
            {t("catalog.listing.openPreview")}
          </Link>
        </div>
      </div>
      {confirmRemove && (
        <ConfirmDialog open tone="danger" busy={busy} title={t("catalog.listing.removeTitle")}
          object={pickLocalized(course.title, lang, course.default_language) || undefined} effect={t("catalog.listing.removeBody")}
          error={error ? <ErrorMessage error={error} /> : undefined}
          confirmLabel={t("catalog.listing.remove")} onConfirm={() => void run("remove")}
          onCancel={() => { setConfirmRemove(false); setError(null); }} />
      )}
    </Card>
  );
}
