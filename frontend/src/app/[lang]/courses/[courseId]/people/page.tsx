"use client";

import React, { useCallback, useEffect, useState } from "react";
import { useTranslation } from "@/lib/i18n/context";
import { addStaff, changeEnrollmentRole, listPeople, removeEnrollment } from "@/lib/lms/courses";
import { useLmsMe } from "@/lib/lms/useLmsMe";
import { isStaffCourse, type CourseRole, type RosterEntryOut, type StaffPublicOut } from "@/lib/lms/types";
import { useCourse } from "@/components/lms/CourseContext";
import { ErrorMessage } from "@/components/lms/ErrorMessage";
import { Pager } from "@/components/lms/Pager";
import { RosterTable } from "@/components/lms/RosterTable";
// --- Phase 6b S5c: staff people tab on the design system ---
import { useListCount } from "@/components/lms/course/StaffCourseUi";
import { Button, Card, ConfirmDialog, EmptyState, Input, LoadingState, PageHeader, SearchInput, Select } from "@/components/ui";
// --- Phase 6b S5c end ---
// --- Phase 6 S4b: invite staff without an account ---
import { createCourseStaffInvitation } from "@/lib/lms/invitations";
import { toastInvitationSent } from "@/components/lms/org/InviteDialog";
import { OrgError } from "@/components/lms/org/OrgUi";
// --- Phase 6 S4b end ---
import { AccommodationsSection } from "@/components/lms/accommodations/AccommodationsSection"; // Phase 7a S5

// S6b: student view
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
  const { lang, t } = useTranslation();
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
  // --- Phase 6 S4b: no account with this email -> offer a staff invitation ---
  const [inviteEmail, setInviteEmail] = useState<string | null>(null);
  const [inviting, setInviting] = useState(false);
  const [inviteError, setInviteError] = useState<unknown>(null);
  // --- Phase 6 S4b end ---

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
  const countText = useListCount(); // Phase 6b S5c

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
    setInviteEmail(null);
    setInviteError(null);
    try {
      await addStaff(course.id, { email: email.trim(), role: addRole });
      setEmail("");
      await load();
    } catch (err) {
      if ((err as { code?: string }).code === "user_not_found") setInviteEmail(email.trim()); // Phase 6 S4b
      else setAddError(err);
    } finally {
      setAdding(false);
    }
  };

  // --- Phase 6 S4b ---
  const sendInvite = async () => {
    if (!inviteEmail) return;
    setInviting(true);
    setInviteError(null);
    try {
      const inv = await createCourseStaffInvitation(course.id, { email: inviteEmail, role: addRole, language: lang });
      toastInvitationSent(t, inv, inviteEmail);
      setInviteEmail(null);
      setEmail("");
    } catch (err) {
      setInviteError(err);
    } finally {
      setInviting(false);
    }
  };
  // --- Phase 6 S4b end ---

  return (
    <div className="space-y-6">
      {/* Phase 6b S5c: PageHeader, add-staff card with design-system fields, roster Table with phone cards (UX T2). */}
      <PageHeader title={t("courses.people.tab")} className="mb-2" />
      {canManage && (
        <Card as="section" title={t("courses.people.addStaff")}>
        <form onSubmit={submitAdd} noValidate>
          <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_auto_auto] sm:items-end">
            <Input id="staff-email" type="email" label={t("courses.people.email")} value={email} disabled={adding || inviting}
              onChange={(e) => { setEmail(e.target.value); setInviteEmail(null); }} />
            <Select id="staff-role" label={t("courses.people.role")} value={addRole} disabled={adding || inviting}
              onChange={(e) => setAddRole(e.target.value as "teacher" | "assistant")}
              options={[{ value: "assistant", label: t("courses.roles.assistant") }, ...(isOwner ? [{ value: "teacher", label: t("courses.roles.teacher") }] : [])]} />
            <Button type="submit" variant="secondary" loading={adding} disabled={!email.trim()}>{t("courses.people.add")}</Button>
          </div>
          <ErrorMessage error={addError} className="mt-3" />
          {/* --- Phase 6 S4b --- */}
          {inviteEmail && (
            <div role="status" className="mt-3 space-y-3 rounded-xl border border-sky-200 bg-sky-50 p-4 text-sm text-sky-900">
              <p>{t("invitations.staff.noAccount", { email: inviteEmail })}</p>
              <Button variant="secondary" loading={inviting} onClick={() => void sendInvite()}>{t("invitations.staff.send")}</Button>
              <p className="text-xs">{t("invitations.staff.sentHint")}</p>
              <OrgError error={inviteError} />
            </div>
          )}
          {/* --- Phase 6 S4b end --- */}
        </form>
        </Card>
      )}

      <div className="grid gap-3 sm:grid-cols-[auto_auto_minmax(0,1fr)] sm:items-end">
        <Select id="f-role" label={t("courses.people.role")} value={role} onChange={(e) => setRole(e.target.value)}
          options={[
            { value: "", label: t("courses.people.allRoles") },
            { value: "teacher", label: t("courses.roles.teacher") },
            { value: "assistant", label: t("courses.roles.assistant") },
            { value: "student", label: t("courses.roles.student") },
          ]} />
        <Select id="f-state" label={t("courses.people.state")} value={state} onChange={(e) => setState(e.target.value as "active" | "removed")}
          options={[{ value: "active", label: t("courses.people.states.active") }, { value: "removed", label: t("courses.people.states.removed") }]} />
        <form onSubmit={(e) => { e.preventDefault(); setQuery(q.trim()); }} className="flex items-end gap-2" role="search">
          <SearchInput id="f-q" value={q} onChange={(v) => { setQ(v); if (!v) setQuery(""); }} containerClassName="min-w-0 flex-1" />
          <Button type="submit" variant="secondary">{t("lms.common.search")}</Button>
        </form>
      </div>

      {error ? <ErrorMessage error={error} onRetry={() => load()} /> : null}
      {loading && items.length === 0 && !error && <LoadingState rows={3} />}
      {!loading && !error && items.length === 0 && <EmptyState title={t("courses.people.empty")} />}
      {items.length > 0 && (
        <RosterTable
          entries={items}
          busyId={busyId}
          countText={countText(items.length, !!cursor)}
          pagination={{ nextCursor: cursor, loading, onLoadMore: () => void load(cursor) }}
          // Owner may manage anyone but the owner; other teachers only students and assistants (P1-8). Never yourself (use leave).
          canChangeRole={(e) => canManage && e.state === "active" && !e.is_owner && e.user.id !== me?.id && (isOwner || e.role !== "teacher")}
          roleOptions={() => (isOwner ? ["teacher", "assistant", "student"] : ["assistant", "student"])}
          canRemove={(e) => canManage && e.state === "active" && !e.is_owner && e.user.id !== me?.id && (isOwner || e.role !== "teacher")}
          onChangeRole={onChangeRole}
          onRemove={(e) => { setRemoveError(null); setRemoving(e); }}
        />
      )}

      {/* --- Phase 7a S5: accommodations per student (teacher only, PHASE_7A_DESIGN 4.4) --- */}
      {isTeacher && course.status !== "concluded" && <AccommodationsSection courseId={course.id} />}
      {/* --- Phase 7a S5 end --- */}

      <ConfirmDialog open={!!removing} tone="danger" busy={!!busyId} title={t("courses.people.removeTitle")}
        object={removing ? `${removing.user.display_name || removing.user.email} · ${t(`courses.roles.${removing.role}`)}` : undefined}
        effect={t("courses.people.removeBody", { name: removing ? removing.user.display_name || removing.user.email : "" })}
        error={removeError ? <ErrorMessage error={removeError} /> : undefined}
        confirmLabel={t("courses.people.remove")} onConfirm={doRemove} onCancel={() => setRemoving(null)} />
    </div>
  );
}
