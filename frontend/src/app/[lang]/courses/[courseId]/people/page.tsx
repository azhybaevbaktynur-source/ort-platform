"use client";

import React, { useCallback, useEffect, useState } from "react";
import { useTranslation } from "@/lib/i18n/context";
import { addStaff, changeEnrollmentRole, listPeople, removeEnrollment } from "@/lib/lms/courses";
import { useLmsMe } from "@/lib/lms/useLmsMe";
import { isStaffCourse, type CourseRole, type RosterEntryOut, type StaffPublicOut } from "@/lib/lms/types";
import { useCourse } from "@/components/lms/CourseContext";
import { ConfirmDialog } from "@/components/lms/ConfirmDialog";
import { ErrorMessage } from "@/components/lms/ErrorMessage";
import { Pager } from "@/components/lms/Pager";
import { RosterTable } from "@/components/lms/RosterTable";

function StaffList({ courseId }: { courseId: string }) {
  const { t } = useTranslation();
  const [items, setItems] = useState<StaffPublicOut[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const load = useCallback(async (next?: string | null) => {
    setLoading(true);
    setError(null);
    try {
      const page = await listPeople(courseId, { cursor: next });
      setItems((p) => (next ? [...p, ...(page.items as StaffPublicOut[])] : (page.items as StaffPublicOut[])));
      setCursor(page.next_cursor);
    } catch (e) {
      setError(e);
    } finally {
      setLoading(false);
    }
  }, [courseId]);
  useEffect(() => { void load(); }, [load]);
  return (
    <div>
      <h2 className="mb-3 text-lg font-bold text-slate-900">{t("courses.people.staffTitle")}</h2>
      {error ? <ErrorMessage error={error} onRetry={() => load()} /> : null}
      {loading && items.length === 0 && !error && <p role="status" className="text-sm text-slate-500">{t("lms.common.loading")}</p>}
      {!loading && !error && items.length === 0 && <p className="text-sm text-slate-500">{t("courses.people.empty")}</p>}
      <ul className="divide-y divide-slate-100 rounded-2xl border border-slate-200 bg-white">
        {items.map((s, i) => (
          <li key={i} className="flex items-center justify-between px-4 py-3 text-sm">
            <span className="font-medium text-slate-900">{s.display_name}</span>
            <span className="text-slate-500">{t(`courses.roles.${s.role}`)}</span>
          </li>
        ))}
      </ul>
      <Pager nextCursor={cursor} loading={loading} onMore={() => load(cursor)} />
    </div>
  );
}

export default function PeoplePage() {
  const { t } = useTranslation();
  const { course } = useCourse();
  const { me } = useLmsMe();
  const staff = isStaffCourse(course);
  const myRole = course.my_enrollment.role;
  const isTeacher = myRole === "teacher";
  const isOwner = staff && course.is_owner;

  const [role, setRole] = useState("");
  const [state, setState] = useState<"active" | "removed">("active");
  const [q, setQ] = useState("");
  const [query, setQuery] = useState("");
  const [items, setItems] = useState<RosterEntryOut[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [removing, setRemoving] = useState<RosterEntryOut | null>(null);
  const [removeError, setRemoveError] = useState<unknown>(null);
  const [email, setEmail] = useState("");
  const [addRole, setAddRole] = useState<"teacher" | "assistant">("assistant");
  const [adding, setAdding] = useState(false);
  const [addError, setAddError] = useState<unknown>(null);

  const load = useCallback(async (next?: string | null) => {
    setLoading(true);
    setError(null);
    try {
      const page = await listPeople(course.id, { role: role || undefined, state, q: query || undefined, cursor: next });
      setItems((p) => (next ? [...p, ...(page.items as RosterEntryOut[])] : (page.items as RosterEntryOut[])));
      setCursor(page.next_cursor);
    } catch (e) {
      setError(e);
    } finally {
      setLoading(false);
    }
  }, [course.id, role, state, query]);

  useEffect(() => { if (staff) void load(); }, [staff, load]);

  if (!staff) return <StaffList courseId={course.id} />;

  const canManage = isTeacher; // assistants cannot manage the roster (P1-8); the server decides
  const patchItem = (u: RosterEntryOut) => setItems((p) => p.map((x) => (x.enrollment_id === u.enrollment_id ? u : x)));

  const onChangeRole = async (e: RosterEntryOut, r: CourseRole) => {
    setBusyId(e.enrollment_id);
    setError(null);
    try {
      patchItem(await changeEnrollmentRole(course.id, e.enrollment_id, r));
    } catch (err) {
      setError(err);
    } finally {
      setBusyId(null);
    }
  };

  const doRemove = async () => {
    if (!removing) return;
    setBusyId(removing.enrollment_id);
    setRemoveError(null);
    try {
      await removeEnrollment(course.id, removing.enrollment_id);
      setRemoving(null);
      await load();
    } catch (err) {
      setRemoveError(err);
    } finally {
      setBusyId(null);
    }
  };

  const submitAdd = async (ev: React.FormEvent) => {
    ev.preventDefault();
    setAdding(true);
    setAddError(null);
    try {
      await addStaff(course.id, { email: email.trim(), role: addRole });
      setEmail("");
      await load();
    } catch (err) {
      setAddError(err);
    } finally {
      setAdding(false);
    }
  };

  return (
    <div className="space-y-6">
      {canManage && (
        <form onSubmit={submitAdd} className="rounded-2xl border border-slate-200 bg-white p-5" noValidate>
          <h2 className="mb-3 text-lg font-bold text-slate-900">{t("courses.people.addStaff")}</h2>
          <div className="flex flex-wrap items-end gap-3">
            <div className="min-w-[14rem] flex-1">
              <label htmlFor="staff-email" className="mb-1 block text-sm font-medium text-slate-700">{t("courses.people.email")}</label>
              <input id="staff-email" type="email" value={email} disabled={adding} onChange={(e) => setEmail(e.target.value)}
                className="w-full rounded-xl border border-slate-300 px-3 py-2 text-sm" />
            </div>
            <div>
              <label htmlFor="staff-role" className="mb-1 block text-sm font-medium text-slate-700">{t("courses.people.role")}</label>
              <select id="staff-role" value={addRole} disabled={adding} onChange={(e) => setAddRole(e.target.value as "teacher" | "assistant")}
                className="rounded-xl border border-slate-300 px-3 py-2 text-sm">
                <option value="assistant">{t("courses.roles.assistant")}</option>
                {isOwner && <option value="teacher">{t("courses.roles.teacher")}</option>}
              </select>
            </div>
            <button type="submit" disabled={adding || !email.trim()} className="rounded-xl bg-brand-600 px-4 py-2 text-sm font-semibold text-white hover:bg-brand-700 disabled:opacity-50">
              {adding ? t("lms.common.loading") : t("courses.people.add")}
            </button>
          </div>
          <ErrorMessage error={addError} className="mt-3" />
        </form>
      )}

      <div className="flex flex-wrap items-end gap-3">
        <div>
          <label htmlFor="f-role" className="mb-1 block text-xs font-medium text-slate-600">{t("courses.people.role")}</label>
          <select id="f-role" value={role} onChange={(e) => setRole(e.target.value)} className="rounded-xl border border-slate-300 px-3 py-2 text-sm">
            <option value="">{t("courses.people.allRoles")}</option>
            <option value="teacher">{t("courses.roles.teacher")}</option>
            <option value="assistant">{t("courses.roles.assistant")}</option>
            <option value="student">{t("courses.roles.student")}</option>
          </select>
        </div>
        <div>
          <label htmlFor="f-state" className="mb-1 block text-xs font-medium text-slate-600">{t("courses.people.state")}</label>
          <select id="f-state" value={state} onChange={(e) => setState(e.target.value as "active" | "removed")} className="rounded-xl border border-slate-300 px-3 py-2 text-sm">
            <option value="active">{t("courses.people.states.active")}</option>
            <option value="removed">{t("courses.people.states.removed")}</option>
          </select>
        </div>
        <form onSubmit={(e) => { e.preventDefault(); setQuery(q.trim()); }} className="flex items-end gap-2" role="search">
          <div>
            <label htmlFor="f-q" className="mb-1 block text-xs font-medium text-slate-600">{t("lms.common.search")}</label>
            <input id="f-q" type="search" value={q} onChange={(e) => setQ(e.target.value)} className="rounded-xl border border-slate-300 px-3 py-2 text-sm" />
          </div>
          <button type="submit" className="rounded-xl border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50">{t("lms.common.search")}</button>
        </form>
      </div>

      {error ? <ErrorMessage error={error} onRetry={() => load()} /> : null}
      {loading && items.length === 0 && !error && <p role="status" className="text-sm text-slate-500">{t("lms.common.loading")}</p>}
      {!loading && !error && items.length === 0 && <p className="rounded-2xl border border-dashed border-slate-300 p-8 text-center text-sm text-slate-500">{t("courses.people.empty")}</p>}
      {items.length > 0 && (
        <RosterTable
          entries={items}
          busyId={busyId}
          // Owner may manage anyone but the owner; other teachers only students and assistants (P1-8). Never yourself (use leave).
          canChangeRole={(e) => canManage && e.state === "active" && !e.is_owner && e.user.id !== me?.id && (isOwner || e.role !== "teacher")}
          roleOptions={() => (isOwner ? ["teacher", "assistant", "student"] : ["assistant", "student"])}
          canRemove={(e) => canManage && e.state === "active" && !e.is_owner && e.user.id !== me?.id && (isOwner || e.role !== "teacher")}
          onChangeRole={onChangeRole}
          onRemove={(e) => { setRemoveError(null); setRemoving(e); }}
        />
      )}
      <Pager nextCursor={cursor} loading={loading} onMore={() => load(cursor)} />

      <ConfirmDialog open={!!removing} danger busy={!!busyId} error={removeError} title={t("courses.people.removeTitle")}
        body={t("courses.people.removeBody", { name: removing ? removing.user.display_name || removing.user.email : "" })}
        confirmLabel={t("courses.people.remove")} onConfirm={doRemove} onCancel={() => setRemoving(null)} />
    </div>
  );
}
