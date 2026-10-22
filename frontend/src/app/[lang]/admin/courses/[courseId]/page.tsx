"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useTranslation } from "@/lib/i18n/context";
import {
  adminCoursePeople, adminDeleteCourse, adminRestoreCourse, adminTransferOwnership, getAdminCourse, relistCourse, unlistCourse,
} from "@/lib/lms/admin";
import type { AdminCourseOut, RosterEntryOut } from "@/lib/lms/types";
import { pickLocalized } from "@/lib/lms/localized";
import { ErrorMessage } from "@/components/lms/ErrorMessage";
import { Pager } from "@/components/lms/Pager";
import { ReasonDialog } from "@/components/lms/admin/ReasonDialog";

type Action = "delete" | "restore" | "unlist" | "relist" | "transfer";

export default function AdminCourseDetailPage() {
  const { courseId } = useParams<{ courseId: string }>();
  const { lang, t } = useTranslation();
  const [course, setCourse] = useState<AdminCourseOut | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [action, setAction] = useState<Action | null>(null);
  const [newOwner, setNewOwner] = useState("");
  const [busy, setBusy] = useState(false);
  const [dialogError, setDialogError] = useState<unknown>(null);
  const [people, setPeople] = useState<RosterEntryOut[] | null>(null);
  const [peopleCursor, setPeopleCursor] = useState<string | null>(null);
  const [peopleLoading, setPeopleLoading] = useState(false);

  const load = useCallback(async () => {
    setError(null);
    try {
      setCourse(await getAdminCourse(courseId));
    } catch (e) {
      setError(e);
    }
  }, [courseId]);
  useEffect(() => { void load(); }, [load]);

  const loadPeople = async (next?: string | null) => {
    setPeopleLoading(true);
    setError(null);
    try {
      const page = await adminCoursePeople(courseId, next);
      setPeople((prev) => (next && prev ? [...prev, ...page.items] : page.items));
      setPeopleCursor(page.next_cursor);
    } catch (e) {
      setError(e);
    } finally {
      setPeopleLoading(false);
    }
  };

  const run = async (reason: string) => {
    if (!action) return;
    setBusy(true);
    setDialogError(null);
    try {
      let updated: AdminCourseOut;
      if (action === "delete") updated = await adminDeleteCourse(courseId, reason);
      else if (action === "restore") updated = await adminRestoreCourse(courseId, reason);
      else if (action === "unlist") updated = await unlistCourse(courseId, reason || undefined);
      else if (action === "relist") updated = await relistCourse(courseId, reason || undefined);
      else updated = await adminTransferOwnership(courseId, newOwner.trim(), reason);
      setCourse(updated);
      setAction(null);
      if (action === "transfer") setNewOwner("");
    } catch (e) {
      setDialogError(e);
    } finally {
      setBusy(false);
    }
  };

  const back = <Link href={`/${lang}/admin/courses`} className="text-sm font-medium text-brand-700 hover:underline">{t("platformAdmin.courses.back")}</Link>;
  if (error && !course) return <div>{back}<ErrorMessage error={error} onRetry={load} className="mt-4" /></div>;
  if (!course) return <p role="status" className="text-sm text-slate-500">{t("lms.common.loading")}</p>;

  const isDeleted = !!course.deleted_at;
  const btn = "rounded-xl border px-3 py-1.5 text-sm font-medium disabled:opacity-50";
  const open = (a: Action) => { setDialogError(null); setAction(a); };
  const titles: Record<Action, string> = {
    delete: t("platformAdmin.courses.deleteTitle"), restore: t("platformAdmin.courses.restoreTitle"),
    unlist: t("platformAdmin.courses.unlistTitle"), relist: t("platformAdmin.courses.relistTitle"),
    transfer: t("platformAdmin.courses.transferTitle"),
  };
  const labels: Record<Action, string> = {
    delete: t("platformAdmin.courses.delete"), restore: t("platformAdmin.courses.restore"),
    unlist: t("platformAdmin.courses.unlist"), relist: t("platformAdmin.courses.relist"),
    transfer: t("platformAdmin.courses.transfer"),
  };

  return (
    <div>
      {back}
      <h1 className="mb-1 mt-2 text-2xl font-bold text-slate-900">{pickLocalized(course.title, lang, "en") || course.id}</h1>
      <p className="mb-4 text-sm text-slate-500">
        {t("platformAdmin.courses.owner")}: <Link href={`/${lang}/admin/users/${course.owner.id}`} className="text-brand-700 hover:underline">{course.owner.display_name || course.owner.email}</Link>
      </p>
      {error ? <ErrorMessage error={error} onRetry={load} className="mb-4" /> : null}
      <div className="mb-6 rounded-2xl border border-slate-200 bg-white p-5 text-sm">
        <dl className="grid gap-2 sm:grid-cols-2">
          <div><dt className="text-xs text-slate-500">{t("platformAdmin.courses.status")}</dt><dd>{t(`courses.status.${course.status}`)}</dd></div>
          <div><dt className="text-xs text-slate-500">{t("platformAdmin.courses.visibility")}</dt><dd>{t(`platformAdmin.courses.visibilityValues.${course.visibility}`)}</dd></div>
          <div><dt className="text-xs text-slate-500">{t("platformAdmin.courses.students")}</dt><dd>{course.active_student_count}</dd></div>
          <div><dt className="text-xs text-slate-500">{t("platformAdmin.users.created")}</dt><dd>{new Date(course.created_at).toLocaleString(lang)}</dd></div>
          {course.unlisted_by_admin_at && <div><dt className="text-xs text-slate-500">{t("platformAdmin.courses.unlisted")}</dt><dd>{new Date(course.unlisted_by_admin_at).toLocaleString(lang)}</dd></div>}
          {course.deleted_at && <div><dt className="text-xs text-slate-500">{t("platformAdmin.courses.deleted")}</dt><dd>{new Date(course.deleted_at).toLocaleString(lang)}</dd></div>}
        </dl>
        <div className="mt-4 flex flex-wrap gap-2">
          {isDeleted ? (
            <button type="button" className={`${btn} border-emerald-300 text-emerald-700 hover:bg-emerald-50`} onClick={() => open("restore")}>{labels.restore}</button>
          ) : (
            <>
              {course.unlisted_by_admin_at ? (
                <button type="button" className={`${btn} border-slate-300 text-slate-700 hover:bg-slate-50`} onClick={() => open("relist")}>{labels.relist}</button>
              ) : (
                <button type="button" className={`${btn} border-amber-300 text-amber-800 hover:bg-amber-50`} onClick={() => open("unlist")}>{labels.unlist}</button>
              )}
              <button type="button" className={`${btn} border-red-300 text-red-700 hover:bg-red-50`} onClick={() => open("delete")}>{labels.delete}</button>
            </>
          )}
        </div>
      </div>

      {!isDeleted && (
        <div className="mb-6 rounded-2xl border border-slate-200 bg-white p-5 text-sm">
          <h2 className="mb-1 font-semibold text-slate-900">{t("platformAdmin.courses.transferHeading")}</h2>
          <p className="mb-3 text-slate-600">{t("platformAdmin.courses.transferHint")}</p>
          <div className="flex flex-wrap items-end gap-2">
            <div>
              <label htmlFor="new-owner" className="block text-xs font-medium text-slate-600">{t("platformAdmin.courses.newOwnerId")}</label>
              <input id="new-owner" value={newOwner} onChange={(e) => setNewOwner(e.target.value)} className="w-72 rounded-xl border border-slate-300 px-3 py-2 text-sm" />
            </div>
            <button type="button" disabled={!newOwner.trim()} className={`${btn} border-slate-300 text-slate-700 hover:bg-slate-50`} onClick={() => open("transfer")}>{labels.transfer}</button>
          </div>
        </div>
      )}

      <h2 className="mb-2 text-lg font-semibold text-slate-900">{t("platformAdmin.courses.roster")}</h2>
      {people === null ? (
        <div>
          <p className="mb-2 text-sm text-slate-600">{t("platformAdmin.courses.rosterAudited")}</p>
          <button type="button" disabled={peopleLoading} onClick={() => loadPeople()} className={`${btn} border-slate-300 text-slate-700 hover:bg-slate-50`}>
            {peopleLoading ? t("lms.common.loading") : t("platformAdmin.courses.showRoster")}
          </button>
        </div>
      ) : (
        <>
          <div className="overflow-x-auto rounded-2xl border border-slate-200 bg-white">
            <table className="w-full text-left text-sm">
              <thead className="bg-slate-50 text-xs uppercase text-slate-500">
                <tr><th className="px-3 py-2">{t("platformAdmin.users.user")}</th><th className="px-3 py-2">{t("platformAdmin.courses.role")}</th><th className="px-3 py-2">{t("platformAdmin.courses.status")}</th></tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {people.map((p) => (
                  <tr key={p.enrollment_id}>
                    <td className="px-3 py-2">{p.user.display_name || p.user.email}<p className="text-xs text-slate-500">{p.user.email}</p></td>
                    <td className="px-3 py-2">{t(`courses.roles.${p.role}`)}{p.is_owner ? ` (${t("platformAdmin.courses.ownerTag")})` : ""}</td>
                    <td className="px-3 py-2">{p.state}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pager nextCursor={peopleCursor} loading={peopleLoading} onMore={() => loadPeople(peopleCursor)} />
        </>
      )}

      <ReasonDialog
        open={!!action} title={action ? titles[action] : ""} confirmLabel={action ? labels[action] : undefined}
        danger={action === "delete"} optional={action === "unlist" || action === "relist"} busy={busy} error={dialogError}
        onConfirm={run} onCancel={() => setAction(null)}
      />
    </div>
  );
}
