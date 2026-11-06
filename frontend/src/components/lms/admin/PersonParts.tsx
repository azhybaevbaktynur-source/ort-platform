"use client";

// S4 person page: the attempt lookup (status only, never answers or scores, decision A4), and the dialogs of the
// actions that need more than a reason: change the email address (A9) and correct the age group.
import React, { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useTranslation } from "@/lib/i18n/context";
import { listUserAttempts } from "@/lib/lms/admin";
import { EMAIL_RE } from "@/lib/lms/emailChange";
import type { AdminAttemptOut } from "@/lib/lms/types";
import { pickLocalized } from "@/lib/lms/localized";
import { fmtApiDateTimeShort } from "@/lib/format";
import { Badge, Button, Card, ConfirmDialog, Input, Select, Skeleton, Textarea, type BadgeTone } from "@/components/ui";
import { OrgError } from "@/components/lms/org/OrgUi";

const STATUS_TONE: Record<AdminAttemptOut["status"], BadgeTone> = {
  in_progress: "info", submitted: "success", needs_review: "warning", graded: "success", void: "neutral",
};

/** The person's attempts in every course, newest first, ten at a time. */
export function AttemptLookupSection({ userId }: { userId: string }) {
  const { lang, t } = useTranslation();
  const [items, setItems] = useState<AdminAttemptOut[] | null>(null);
  const [cursor, setCursor] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async (after: string | null) => {
    setLoading(true);
    setError(null);
    try {
      const page = await listUserAttempts(userId, after);
      setItems((prev) => (after && prev ? [...prev, ...page.items] : page.items));
      setCursor(page.next_cursor ?? null);
    } catch (e) {
      setError(e);
    } finally {
      setLoading(false);
    }
  }, [userId]);
  useEffect(() => { void load(null); }, [load]);

  const time = (iso: string | null) => (iso ? fmtApiDateTimeShort(iso, lang) : "—");
  return (
    <Card className="mb-6" title={t("person.attempts.title")} description={t("person.attempts.hint")} padding="none">
      <div className="px-4 pb-4 sm:px-6" data-testid="attempt-lookup">
        {error && !items ? <OrgError error={error} onRetry={() => void load(null)} /> : !items ? <Skeleton className="h-6 w-1/2" /> : items.length === 0 ? (
          <p className="text-sm text-slate-600">{t("person.attempts.empty")}</p>
        ) : (
          <>
            <ul className="divide-y divide-slate-100 border-y border-slate-100">
              {items.map((a) => (
                <li key={a.id} className="grid gap-x-4 gap-y-1 py-3 text-sm sm:grid-cols-[minmax(0,2fr)_minmax(0,1fr)_minmax(0,1fr)]">
                  <div className="min-w-0">
                    <p className="break-words font-medium text-slate-900">{pickLocalized(a.assessment_title, lang, a.course_default_language)}</p>
                    <Link href={`/${lang}/admin/courses/${a.course_id}`} className="break-words text-brand-700 hover:underline">
                      {pickLocalized(a.course_title, lang, a.course_default_language)}
                    </Link>
                    <span className="mt-1 flex flex-wrap gap-1">
                      <Badge tone={STATUS_TONE[a.status]}>{t(`person.attempts.statusValue.${a.status}`)}</Badge>
                      {a.is_practice && <Badge>{t("person.attempts.practice")}</Badge>}
                    </span>
                  </div>
                  <dl className="grid grid-cols-[auto_1fr] gap-x-2 text-slate-700 sm:block">
                    <dt className="text-slate-500">{t("person.attempts.started")}</dt>
                    <dd>{time(a.started_at)}</dd>
                    <dt className="text-slate-500 sm:mt-1">{t("person.attempts.finished")}</dt>
                    <dd>{time(a.submitted_at)}{a.submit_reason ? ` · ${t(`person.attempts.reason.${a.submit_reason}`)}` : ""}</dd>
                  </dl>
                  <dl className="grid grid-cols-[auto_1fr] gap-x-2 text-slate-700 sm:block">
                    <dt className="text-slate-500">{t("person.attempts.saved")}</dt>
                    <dd className="font-medium text-slate-900">{t("person.attempts.savedValue", { saved: a.saved_answers, total: a.item_count })}</dd>
                  </dl>
                </li>
              ))}
            </ul>
            {error ? <OrgError error={error} className="mt-3" /> : null}
            {cursor && (
              <Button className="mt-3" variant="secondary" size="sm" loading={loading} disabled={loading} onClick={() => void load(cursor)}>
                {t("person.attempts.more")}
              </Button>
            )}
          </>
        )}
      </div>
    </Card>
  );
}

/** New address and a reason; the link goes to the new address, nothing changes until it is opened. */
export function ChangeEmailDialog({ open, name, busy, error, onConfirm, onCancel }: {
  open: boolean; name: string; busy: boolean; error?: React.ReactNode;
  onConfirm: (email: string, reason: string) => void; onCancel: () => void;
}) {
  const { t } = useTranslation();
  const [email, setEmail] = useState("");
  const [reason, setReason] = useState("");
  const [problem, setProblem] = useState<string | null>(null);
  const emailRef = useRef<HTMLInputElement>(null);
  useEffect(() => { if (open) { setEmail(""); setReason(""); setProblem(null); } }, [open]);
  const submit = () => {
    const clean = email.trim();
    if (!EMAIL_RE.test(clean)) { setProblem(t("person.invalidEmail")); emailRef.current?.focus(); return; }
    if (!reason.trim()) { setProblem(t("ui.reason.missing")); return; }
    setProblem(null);
    onConfirm(clean, reason.trim());
  };
  return (
    <ConfirmDialog open={open} title={t("person.changeEmailTitle")} object={name} effect={t("person.changeEmailBody")}
      confirmLabel={t("person.changeEmailSend")} busy={busy} error={problem ?? error} initialFocusRef={emailRef}
      onConfirm={submit} onCancel={onCancel}>
      <div className="mt-4 space-y-4">
        <Input ref={emailRef} id="person-new-email" type="email" inputMode="email" autoComplete="off" label={t("person.newEmail")}
          value={email} onChange={(e) => setEmail(e.target.value)} />
        <Textarea id="person-email-reason" label={t("ui.reason.required")} rows={2} maxLength={500} value={reason}
          onChange={(e) => setReason(e.target.value)} />
      </div>
    </ConfirmDialog>
  );
}

const BANDS = ["under_14", "14_17", "18_plus"] as const;

/** The privacy function's age correction, with its rules said in the dialog; a reason is required here. */
export function AgeBandDialog({ open, name, current, busy, error, onConfirm, onCancel }: {
  open: boolean; name: string; current: string | null | undefined; busy: boolean; error?: React.ReactNode;
  onConfirm: (band: string, reason: string) => void; onCancel: () => void;
}) {
  const { t } = useTranslation();
  const [band, setBand] = useState("");
  const [reason, setReason] = useState("");
  const [problem, setProblem] = useState<string | null>(null);
  const selectRef = useRef<HTMLSelectElement>(null);
  useEffect(() => { if (open) { setBand(current ?? ""); setReason(""); setProblem(null); } }, [open, current]);
  const submit = () => {
    if (!band || band === current) { setProblem(t("person.ageSame")); selectRef.current?.focus(); return; }
    if (!reason.trim()) { setProblem(t("ui.reason.missing")); return; }
    setProblem(null);
    onConfirm(band, reason.trim());
  };
  return (
    <ConfirmDialog open={open} title={t("person.correctAgeTitle")} object={name} effect={t("person.correctAgeBody")}
      confirmLabel={t("person.ageSave")} busy={busy} error={problem ?? error} initialFocusRef={selectRef}
      onConfirm={submit} onCancel={onCancel}>
      <div className="mt-4 space-y-4">
        <Select ref={selectRef} id="person-age-band" label={t("person.ageNew")} value={band} placeholder={t("person.ageUnknown")}
          onChange={(e) => setBand(e.target.value)}
          options={BANDS.map((b) => ({ value: b, label: t(`privacy.age.${b}`) }))} />
        <Textarea id="person-age-reason" label={t("ui.reason.required")} rows={2} maxLength={500} value={reason}
          onChange={(e) => setReason(e.target.value)} />
      </div>
    </ConfirmDialog>
  );
}
