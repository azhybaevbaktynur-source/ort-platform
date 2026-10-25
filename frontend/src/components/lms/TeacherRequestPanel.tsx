"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useTranslation } from "@/lib/i18n/context";
import { useLmsMe } from "@/lib/lms/useLmsMe";
import { listMyTeacherRequests, submitTeacherRequest } from "@/lib/lms/teacher";
import type { MyTeacherRequestOut } from "@/lib/lms/types";
import { ErrorMessage } from "@/components/lms/ErrorMessage";
// Phase 6b S6b: design-system pieces, dates without seconds (UX S15), plain status sentence (6a carry-over)
import { Badge, Button, Skeleton, Textarea, type BadgeTone } from "@/components/ui";
import { fmtShortDateTime } from "@/components/lms/home/format";

/** Independent teacher request: today's become-teacher form and state (moved here in Phase 6, §7). */
export function TeacherRequestPanel() {
  const { lang, t } = useTranslation();
  const { me, reload } = useLmsMe();
  const [requests, setRequests] = useState<MyTeacherRequestOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setRequests(await listMyTeacherRequests());
      setError(null);
    } catch (e) {
      setError(e);
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => { void load(); }, [load]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await submitTeacherRequest(message.trim() || undefined);
      setMessage("");
      await Promise.all([load(), reload()]);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };

  const status = me?.teacher_status ?? "none";
  const pending = status === "pending" || requests.some((r) => r.status === "pending");
  const canAsk = (status === "none" || status === "revoked") && !pending;
  const latestRejected = requests.find((r) => r.status === "rejected");
  const badge: Record<string, BadgeTone> = { pending: "warning", approved: "success", rejected: "danger", cancelled: "neutral" };
  // One plain sentence, only once there is something to say (a request exists); the boxes below explain
  // pending / approved / revoked / rejected, so the sentence covers the remaining case.
  const showStatusLine = !loading && requests.length > 0 && status === "none" && !pending && !latestRejected;

  return (
    <div>
      <p className="mb-4 text-base leading-6 text-slate-600 sm:text-sm">{t("teacherRequest.intro")}</p>
      {showStatusLine && <p className="mb-6 text-base leading-6 text-slate-700 sm:text-sm">{t("teacherAccess.statusLine.none")}</p>}

      {error ? <ErrorMessage error={error} onRetry={load} className="mb-4" /> : null}

      {status === "approved" && (
        <div role="status" className="mb-6 rounded-2xl border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-900">
          {t("teacherRequest.approvedBody")}{" "}
          <Link href={`/${lang}/courses/new`} className="font-semibold underline">{t("teacherRequest.createCourse")}</Link>
        </div>
      )}
      {pending && status !== "approved" && (
        <div role="status" className="mb-6 rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">{t("teacherRequest.pendingBody")}</div>
      )}
      {status === "revoked" && (
        <div role="status" className="mb-6 rounded-2xl border border-red-200 bg-red-50 p-4 text-sm text-red-900">{t("teacherRequest.revokedBody")}</div>
      )}
      {canAsk && latestRejected && (
        <div role="status" className="mb-6 rounded-2xl border border-red-200 bg-red-50 p-4 text-sm text-red-900">
          <p>{t("teacherRequest.rejectedBody")}</p>
          {latestRejected.reason && <p className="mt-1"><strong>{t("teacherRequest.reason")}:</strong> {latestRejected.reason}</p>}
        </div>
      )}

      {canAsk && (
        <form onSubmit={submit} className="mb-8 rounded-2xl border border-slate-200 bg-white p-4 sm:p-6">
          <Textarea id="tr-message" label={t("teacherRequest.messageLabel")} rows={5} maxLength={2000} value={message}
            onChange={(e) => setMessage(e.target.value)} placeholder={t("teacherRequest.messagePlaceholder")}
            hint={`${message.length}/2000`} />
          <Button type="submit" loading={busy} className="mt-3 w-full sm:w-auto">{t("teacherRequest.submit")}</Button>
        </form>
      )}

      <h3 className="mb-3 text-base font-semibold text-slate-900">{t("teacherRequest.history")}</h3>
      {loading && (
        <div role="status" aria-live="polite"><span className="sr-only">{t("ui.loading")}</span><Skeleton className="h-16 w-full rounded-2xl" /></div>
      )}
      {!loading && requests.length === 0 && <p className="text-base leading-6 text-slate-600 sm:text-sm">{t("teacherRequest.noHistory")}</p>}
      <ul className="space-y-3">
        {requests.map((r) => (
          <li key={r.id} className="rounded-2xl border border-slate-200 bg-white p-4 text-sm">
            <div className="flex items-center justify-between gap-2">
              <Badge tone={badge[r.status] ?? "neutral"}>{t(`teacherRequest.requestStatus.${r.status}`)}</Badge>
              <time dateTime={r.created_at} className="text-sm text-slate-600">{fmtShortDateTime(r.created_at, lang)}</time>
            </div>
            {r.message && <p className="mt-2 whitespace-pre-wrap text-slate-700">{r.message}</p>}
            {r.reason && <p className="mt-2 text-slate-700"><strong>{t("teacherRequest.reason")}:</strong> {r.reason}</p>}
          </li>
        ))}
      </ul>
    </div>
  );
}
