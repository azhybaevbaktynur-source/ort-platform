"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useTranslation } from "@/lib/i18n/context";
import { useLmsMe } from "@/lib/lms/useLmsMe";
import { listMyTeacherRequests, submitTeacherRequest } from "@/lib/lms/teacher";
import type { MyTeacherRequestOut } from "@/lib/lms/types";
import { fmtApiDateTime } from "@/lib/format";
import { ErrorMessage } from "@/components/lms/ErrorMessage";

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
  const badge: Record<string, string> = {
    pending: "bg-amber-100 text-amber-800", approved: "bg-emerald-100 text-emerald-800",
    rejected: "bg-red-100 text-red-800", cancelled: "bg-slate-100 text-slate-600",
  };

  return (
    <div>
      <p className="mb-4 text-sm text-slate-600">{t("teacherRequest.intro")}</p>
      <p className="mb-6 text-sm text-slate-700">
        {t("teacherRequest.currentStatus")}: <strong>{t(`teacherRequest.status.${status}`)}</strong>
      </p>

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
        <form onSubmit={submit} className="mb-8 rounded-2xl border border-slate-200 bg-white p-5">
          <label htmlFor="tr-message" className="block text-sm font-medium text-slate-700">{t("teacherRequest.messageLabel")}</label>
          <textarea id="tr-message" rows={5} maxLength={2000} value={message} onChange={(e) => setMessage(e.target.value)}
            placeholder={t("teacherRequest.messagePlaceholder")}
            className="mt-1 w-full rounded-xl border border-slate-300 px-3 py-2 text-sm" />
          <p className="mt-1 text-xs text-slate-500">{message.length}/2000</p>
          <button type="submit" disabled={busy}
            className="mt-3 min-h-[44px] rounded-xl bg-brand-600 px-4 py-2 text-sm font-semibold text-white hover:bg-brand-700 disabled:opacity-50">
            {busy ? t("lms.common.loading") : t("teacherRequest.submit")}
          </button>
        </form>
      )}

      <h3 className="mb-3 text-base font-semibold text-slate-900">{t("teacherRequest.history")}</h3>
      {loading && <p role="status" className="text-sm text-slate-500">{t("lms.common.loading")}</p>}
      {!loading && requests.length === 0 && <p className="text-sm text-slate-500">{t("teacherRequest.noHistory")}</p>}
      <ul className="space-y-3">
        {requests.map((r) => (
          <li key={r.id} className="rounded-2xl border border-slate-200 bg-white p-4 text-sm">
            <div className="flex items-center justify-between gap-2">
              <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${badge[r.status] || badge.cancelled}`}>{t(`teacherRequest.requestStatus.${r.status}`)}</span>
              <time className="text-xs text-slate-500">{fmtApiDateTime(r.created_at, lang)}</time>
            </div>
            {r.message && <p className="mt-2 whitespace-pre-wrap text-slate-700">{r.message}</p>}
            {r.reason && <p className="mt-2 text-slate-700"><strong>{t("teacherRequest.reason")}:</strong> {r.reason}</p>}
          </li>
        ))}
      </ul>
    </div>
  );
}
