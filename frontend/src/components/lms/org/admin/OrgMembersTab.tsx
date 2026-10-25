"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useTranslation } from "@/lib/i18n/context";
import {
  addOrganizationMember, listOrganizationMembers, removeOrganizationMember, type OrganizationOut, type OrgMemberOut, type OrgRole,
} from "@/lib/lms/organizations";
import { fmtApiDate } from "@/lib/format";
import { Pager } from "@/components/lms/Pager";
import { ConfirmDialog } from "@/components/lms/ConfirmDialog";
import { ReasonDialog } from "@/components/lms/admin/ReasonDialog";
import { UserPicker, platformUserSearch, type PickedUser } from "@/components/lms/UserPicker";
import { EmptyBox, Loading, OrgBadge, OrgError, btn, cardCls } from "../OrgUi";
import { toast } from "@/components/ui/Toast";

/** Platform admin: organization admins or teachers, with "Assign admin" / "Add teacher" (UserPicker) and remove. */
export function OrgMembersTab({ org, role, onChanged }: { org: OrganizationOut; role: OrgRole; onChanged: () => void }) {
  const { lang, t } = useTranslation();
  const [items, setItems] = useState<OrgMemberOut[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [picked, setPicked] = useState<PickedUser | null>(null);
  const [confirmAdd, setConfirmAdd] = useState(false);
  const [removing, setRemoving] = useState<OrgMemberOut | null>(null);
  const [busy, setBusy] = useState(false);
  const [dialogError, setDialogError] = useState<unknown>(null);
  const search = useMemo(() => platformUserSearch(), []);
  const isAdmins = role === "org_admin";

  const load = useCallback(async (next?: string | null) => {
    setLoading(true);
    setError(null);
    try {
      const page = await listOrganizationMembers(org.id, { role, state: "active", cursor: next });
      setItems((prev) => (next ? [...prev, ...page.items] : page.items));
      setCursor(page.next_cursor);
    } catch (e) {
      setError(e);
    } finally {
      setLoading(false);
    }
  }, [org.id, role]);
  useEffect(() => { void load(); }, [load]);

  const add = async () => {
    if (!picked) return;
    setBusy(true);
    setDialogError(null);
    try {
      await addOrganizationMember(org.id, picked.id, role);
      toast.success(t(isAdmins ? "organizations.members.adminAdded" : "organizations.members.teacherAdded", { name: picked.display_name || picked.email }));
      setPicked(null);
      setConfirmAdd(false);
      await load();
      onChanged();
    } catch (e) {
      setDialogError(e);
    } finally {
      setBusy(false);
    }
  };
  const remove = async (reason: string) => {
    if (!removing) return;
    setBusy(true);
    setDialogError(null);
    try {
      await removeOrganizationMember(org.id, removing.user_id, reason);
      toast.success(t("organizations.members.removed", { name: removing.display_name || removing.email }));
      setRemoving(null);
      await load();
      onChanged();
    } catch (e) {
      setDialogError(e);
    } finally {
      setBusy(false);
    }
  };

  const pickedName = picked ? picked.display_name || picked.email : "";
  const removingName = removing ? removing.display_name || removing.email : "";
  return (
    <div className="space-y-4">
      <div className={cardCls}>
        <h3 className="mb-1 font-semibold text-slate-900">{t(isAdmins ? "organizations.members.assignAdmin" : "organizations.members.addTeacher")}</h3>
        <p className="mb-3 text-sm text-slate-600">{t(isAdmins ? "organizations.members.assignAdminHint" : "organizations.members.addTeacherHint")}</p>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
          <div className="flex-1">
            <UserPicker label={t("organizations.members.person")} value={picked} onChange={setPicked} search={search}
              excludeIds={items.map((m) => m.user_id)} />
          </div>
          <button type="button" className={btn.primary} disabled={!picked} onClick={() => { setDialogError(null); setConfirmAdd(true); }}>
            {t(isAdmins ? "organizations.members.assignAdmin" : "organizations.members.addTeacher")}
          </button>
        </div>
      </div>
      {error ? <OrgError error={error} onRetry={() => load()} /> : null}
      {loading && items.length === 0 && !error && <Loading />}
      {!loading && !error && items.length === 0 && <EmptyBox text={t(isAdmins ? "organizations.members.noAdmins" : "organizations.members.noTeachers")} />}
      {items.length > 0 && (
        <ul className="divide-y divide-slate-100 rounded-2xl border border-slate-200 bg-white text-sm">
          {items.map((m) => (
            <li key={m.user_id} className="flex flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3">
              <div className="min-w-0 flex-1 basis-56">
                <Link href={`/${lang}/admin/users/${m.user_id}`} className="font-medium text-brand-700 hover:underline">{m.display_name || m.email}</Link>
                <p className="truncate text-xs text-slate-500">{m.email} · {t("organizations.members.since", { date: fmtApiDate(m.created_at, lang) })}</p>
              </div>
              {m.disabled && <OrgBadge tone="blocked" labelKey="organizations.members.state.blocked" />}
              <button type="button" className={btn.smallDanger} onClick={() => { setDialogError(null); setRemoving(m); }}>
                {t("organizations.members.remove")}
              </button>
            </li>
          ))}
        </ul>
      )}
      <Pager nextCursor={cursor} loading={loading} onMore={() => load(cursor)} />
      <ConfirmDialog
        open={confirmAdd}
        title={t(isAdmins ? "organizations.members.assignAdminTitle" : "organizations.members.addTeacherTitle", { name: pickedName })}
        body={t(isAdmins ? "organizations.members.assignAdminBody" : "organizations.members.addTeacherBody", { name: pickedName, org: org.name })}
        confirmLabel={t(isAdmins ? "organizations.members.assignAdmin" : "organizations.members.addTeacher")}
        busy={busy} error={dialogError} onConfirm={() => void add()} onCancel={() => setConfirmAdd(false)}
      />
      <ReasonDialog
        open={!!removing}
        title={t("organizations.members.removeTitle", { name: removingName })}
        body={t(isAdmins ? "organizations.members.removeAdminBody" : "organizations.members.removeBody", { name: removingName, org: org.name })}
        confirmLabel={t("organizations.members.remove")} danger busy={busy} error={dialogError}
        onConfirm={(r) => void remove(r)} onCancel={() => setRemoving(null)}
      />
    </div>
  );
}
