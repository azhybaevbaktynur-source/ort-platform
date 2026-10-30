"use client";

// Phase 9 S4: one application for course staff (PHASE_9_DESIGN 4.7, 4.9, 5.1, 6, 8.1, 8.4): the applicant, the status,
// the answers rendered with the form's fields (course staff only; org admins get the status row without answers),
// and for the teacher approve / reject with an optional note and a "send the note by email" tickbox. Answers are PII
// of possible minors: shown, never copied into logs, storage, toasts or error messages.
import React, { useCallback, useEffect, useState } from "react";
import { useTranslation } from "@/lib/i18n/context";
import {
  DECISION_NOTE_MAX, approveApplication, getApplication, hasAnswersPayload, rejectApplication,
} from "@/lib/lms/applications";
import { pickLocalized } from "@/lib/lms/localized";
import type { AnswerValue, ApplicationOut, ApplicationStaffOut, FieldOut, Lang } from "@/lib/lms/types";
import { Button, Checkbox, Dialog, ErrorState, LoadingState, Textarea, toast } from "@/components/ui";
import { ApplicationStatusBadge } from "@/components/lms/catalog/ApplicationStatus";
import { useApplicationErrorText } from "@/components/lms/catalog/useApplicationErrorText";
import { fmtShortDateTime } from "@/components/lms/home/format";
import { fmtDay } from "@/components/lms/catalog/CourseLanding";

function answerText(f: FieldOut, v: AnswerValue | undefined, lang: Lang, def: Lang): string | null {
  if (v === undefined || v === null || v === "" || (Array.isArray(v) && v.length === 0)) return null;
  const opt = (k: string) => pickLocalized(f.options?.find((o) => o.key === k)?.label ?? null, lang, def) || k;
  if (f.type === "single_choice" && typeof v === "string") return opt(v);
  if (f.type === "multi_choice" && Array.isArray(v)) return v.map(opt).join(", ");
  if (f.type === "date" && typeof v === "string") return fmtDay(v, lang) || v;
  return Array.isArray(v) ? v.join(", ") : String(v);
}

export function applicantName(a: Pick<ApplicationOut, "applicant">): string {
  return a.applicant.display_name || a.applicant.email;
}

export function ApplicationPanel({
  courseId, applicationId, open, onClose, canDecide, defaultLanguage, courseOpen, onDecided,
}: {
  courseId: string;
  applicationId: string | null;
  open: boolean;
  onClose: () => void;
  /** Teachers decide; assistants and org admins read. The server checks again. */
  canDecide: boolean;
  defaultLanguage: Lang;
  /** False on a concluded course: approve is refused (409 `course_not_open`), reject still works. */
  courseOpen: boolean;
  onDecided: (a: ApplicationOut) => void;
}) {
  const { lang, t } = useTranslation();
  const errorText = useApplicationErrorText();
  const [app, setApp] = useState<ApplicationStaffOut | ApplicationOut | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<unknown>(null);
  const [note, setNote] = useState("");
  const [sendNote, setSendNote] = useState(false);
  const [busy, setBusy] = useState<null | "approve" | "reject">(null);
  const [error, setError] = useState<unknown>(null);

  const load = useCallback(async () => {
    if (!applicationId) return;
    setLoading(true);
    setLoadError(null);
    try {
      setApp(await getApplication(courseId, applicationId));
    } catch (e) {
      setLoadError(e);
    } finally {
      setLoading(false);
    }
  }, [courseId, applicationId]);

  useEffect(() => {
    if (!open) return;
    setApp(null);
    setNote("");
    setSendNote(false);
    setError(null);
    void load();
  }, [open, load]);

  const decide = async (kind: "approve" | "reject") => {
    if (!app) return;
    setBusy(kind);
    setError(null);
    try {
      const body = { note: note.trim() || null, send_note: !!note.trim() && sendNote };
      const out = kind === "approve" ? await approveApplication(courseId, app.id, body) : await rejectApplication(courseId, app.id, body);
      toast.success(t(kind === "approve" ? "applications.panel.approved" : "applications.panel.rejected", { name: applicantName(out) }));
      onDecided(out);
      setNote("");
      await load();
    } catch (e) {
      setError(e);
      if ((e as { code?: string }).code === "application_decided") void load();
    } finally {
      setBusy(null);
    }
  };

  const staff = app && hasAnswersPayload(app) ? app : null;
  const pending = app?.status === "pending";
  const uiLang = lang as Lang;

  return (
    <Dialog open={open} onClose={onClose} size="full" busy={!!busy}
      title={app ? applicantName(app) : t("applications.panel.title")}
      description={app ? (
        <span className="flex flex-wrap items-center gap-2">
          <ApplicationStatusBadge status={app.status} />
          <span>{t("applications.panel.submitted", { date: fmtShortDateTime(app.submitted_at, lang) })}</span>
        </span>
      ) : undefined}
      footer={app && pending && canDecide ? (
        <div className="flex w-full flex-col gap-2 sm:flex-row sm:justify-end">
          <Button variant="dangerOutline" loading={busy === "reject"} disabled={!!busy} onClick={() => void decide("reject")}>
            {t("applications.panel.reject")}
          </Button>
          <Button loading={busy === "approve"} disabled={!!busy || !courseOpen} onClick={() => void decide("approve")}>
            {t("applications.panel.approve")}
          </Button>
        </div>
      ) : undefined}>
      {loading && !app && <LoadingState rows={4} />}
      {loadError ? <ErrorState variant="inline" message={errorText(loadError)} onRetry={() => void load()} /> : null}
      {app && (
        <div className="space-y-5">
          <p className="break-words text-sm leading-6 text-slate-600 [overflow-wrap:anywhere]">{app.applicant.email}</p>
          {app.decided_at && (
            <p className="text-sm leading-6 text-slate-700">
              {t("applications.panel.decided", {
                date: fmtShortDateTime(app.decided_at, lang),
                name: app.decided_by ? (app.decided_by.display_name || app.decided_by.email) : t("applications.panel.automatic"),
              })}
            </p>
          )}

          {/* Answers: course staff only; after the retention period they are deleted (row kept for counts). */}
          <section aria-labelledby="app-answers">
            <h3 id="app-answers" className="mb-2 text-base font-semibold leading-6 text-slate-900">{t("applications.panel.answers")}</h3>
            {!staff ? (
              <p className="rounded-xl bg-slate-50 px-4 py-3 text-sm leading-6 text-slate-700">{t("applications.panel.answersStaffOnly")}</p>
            ) : staff.answers === null || app.purged_at ? (
              <p className="rounded-xl bg-slate-50 px-4 py-3 text-sm leading-6 text-slate-700">{t("applications.panel.answersPurged")}</p>
            ) : (
              <dl className="divide-y divide-slate-100 rounded-xl border border-slate-200">
                {staff.fields.map((f) => {
                  const text = answerText(f, staff.answers?.[f.key], uiLang, defaultLanguage);
                  return (
                    <div key={f.key} className="px-4 py-3">
                      <dt className="text-sm font-medium leading-6 text-slate-600">{pickLocalized(f.label, uiLang, defaultLanguage) || f.key}</dt>
                      <dd className={`whitespace-pre-line break-words text-base leading-6 [overflow-wrap:anywhere] sm:text-sm ${text ? "text-slate-900" : "text-slate-500"}`}>
                        {text ?? t("applications.panel.noAnswer")}
                      </dd>
                    </div>
                  );
                })}
              </dl>
            )}
            {staff && app.form_version > 0 && (
              <p className="mt-2 text-xs text-slate-500">{t("applications.panel.formVersion", { n: app.form_version })}</p>
            )}
          </section>

          {staff?.decision_note && (
            <section aria-labelledby="app-note">
              <h3 id="app-note" className="mb-1 text-base font-semibold leading-6 text-slate-900">{t("applications.panel.noteShown")}</h3>
              <p className="whitespace-pre-line break-words rounded-xl bg-slate-50 px-4 py-3 text-sm leading-6 text-slate-800">{staff.decision_note}</p>
            </section>
          )}

          {pending && canDecide && (
            <section aria-labelledby="app-decide" className="space-y-3">
              <h3 id="app-decide" className="text-base font-semibold leading-6 text-slate-900">{t("applications.panel.decision")}</h3>
              <Textarea id="app-note-input" label={t("applications.panel.note")} optional value={note} rows={3}
                maxLength={DECISION_NOTE_MAX} hint={t("applications.panel.noteHint", { max: DECISION_NOTE_MAX })}
                disabled={!!busy} onChange={(e) => setNote(e.target.value)} />
              <Checkbox id="app-send-note" label={t("applications.panel.sendNote")} checked={sendNote && !!note.trim()}
                disabled={!!busy || !note.trim()} hint={t("applications.panel.sendNoteHint")}
                onChange={(e) => setSendNote(e.target.checked)} />
              {!courseOpen && <p className="text-sm leading-6 text-warning-800">{t("applications.panel.concluded")}</p>}
              {error ? <ErrorState variant="inline" message={errorText(error)} /> : null}
            </section>
          )}
          {!pending && error ? <ErrorState variant="inline" message={errorText(error)} /> : null}
        </div>
      )}
    </Dialog>
  );
}
