"use client";

import React, { useCallback, useMemo, useState } from "react";
import Link from "next/link";
import { useTranslation } from "@/lib/i18n/context";
import {
  addOrganizationMember, listOrganizationMembers, removeOrganizationMember, type OrganizationOut, type OrgMemberOut, type OrgRole,
} from "@/lib/lms/organizations";
import { fmtApiDate } from "@/lib/format";
import { Button, Card, ConfirmDialog, EmptyState, ReasonDialog, Table, UserPicker, toast, type TableColumn } from "@/components/ui";
import { platformUserSearch, type PickedUser } from "@/components/lms/UserPicker";
import { useCursorList } from "@/components/lms/admin/useCursorList";
import { MoreError, useTableState } from "@/components/lms/admin/ListParts";
import { OrgError } from "../OrgUi";

/** Platform admin: organization admins or teachers, with "Assign admin" / "Add teacher" (UserPicker) and remove. */
export function OrgMembersTab({ org, role, onChanged }: { org: OrganizationOut; role: OrgRole; onChanged: () => void }) {
  const { lang, t } = useTranslation();
  const fetchPage = useCallback((cursor: string | null) => listOrganizationMembers(org.id, { role, state: "active", cursor }), [org.id, role]);
  const list = useCursorList(fetchPage);
  const state = useTableState(list);
  const [picked, setPicked] = useState<PickedUser | null>(null);
  const [confirmAdd, setConfirmAdd] = useState(false);
  const [removing, setRemoving] = useState<OrgMemberOut | null>(null);
  const [busy, setBusy] = useState(false);
  const [dialogError, setDialogError] = useState<unknown>(null);
  const search = useMemo(() => platformUserSearch(), []);
  const isAdmins = role === "org_admin";

  const add = async () => {
    if (!picked) return;
    setBusy(true);
    setDialogError(null);
    try {
      await addOrganizationMember(org.id, picked.id, role);
      toast.success(t(isAdmins ? "organizations.members.adminAdded" : "organizations.members.teacherAdded", { name: picked.display_name || picked.email }));
      setPicked(null);
      setConfirmAdd(false);
      await list.reload();
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
      await removeOrganizationMember(org.id, removing.user.id, reason);
      toast.success(t("organizations.members.removed", { name: removing.user.display_name || removing.user.email }));
      setRemoving(null);
      await list.reload();
      onChanged();
    } catch (e) {
      setDialogError(e);
    } finally {
      setBusy(false);
    }
  };

  const pickedName = picked ? picked.display_name || picked.email : "";
  const removingName = removing ? removing.user.display_name || removing.user.email : "";
  const columns: TableColumn<OrgMemberOut>[] = [
    {
      key: "person", header: t("organizations.members.person"), primary: true,
      cell: (m) => (
        <>
          <Link href={`/${lang}/admin/users/${m.user.id}`} className="break-words font-semibold text-brand-700 hover:underline">{m.user.display_name || m.user.email}</Link>
          <span className="block break-all text-sm font-normal text-slate-600">{m.user.email}</span>
        </>
      ),
    },
    { key: "since", header: t("organizations.members.sinceColumn"), nowrap: true, cell: (m) => fmtApiDate(m.created_at, lang) },
    {
      key: "actions", header: "", actions: true, align: "right",
      cell: (m) => (
        <Button variant="secondary" size="sm" onClick={() => { setDialogError(null); setRemoving(m); }}>{t("organizations.members.remove")}</Button>
      ),
    },
  ];
  const addLabel = t(isAdmins ? "organizations.members.assignAdmin" : "organizations.members.addTeacher");
  return (
    <div className="space-y-4">
      <Card title={addLabel} headingLevel={3} description={t(isAdmins ? "organizations.members.assignAdminHint" : "organizations.members.addTeacherHint")}>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
          <div className="min-w-0 flex-1">
            <UserPicker label={t("organizations.members.person")} value={picked} onChange={setPicked} search={search}
              excludeIds={list.items.map((m) => m.user.id)} />
          </div>
          <Button variant="secondary" disabled={!picked} onClick={() => { setDialogError(null); setConfirmAdd(true); }}>{addLabel}</Button>
        </div>
      </Card>
      <Table
        caption={t(isAdmins ? "organizations.admin.tabs.admins" : "organizations.admin.tabs.teachers")}
        columns={columns}
        rows={list.items}
        rowKey={(m) => m.user.id}
        {...state}
        empty={<EmptyState title={t(isAdmins ? "organizations.members.noAdmins" : "organizations.members.noTeachers")} />}
      />
      <MoreError list={list} />
      <ConfirmDialog
        open={confirmAdd}
        title={t(isAdmins ? "organizations.members.assignAdminTitle" : "organizations.members.addTeacherTitle", { name: pickedName })}
        object={picked ? (picked.display_name ? `${picked.display_name} · ${picked.email}` : picked.email) : undefined}
        effect={t(isAdmins ? "organizations.members.assignAdminBody" : "organizations.members.addTeacherBody", { name: pickedName, org: org.name })}
        confirmLabel={addLabel}
        busy={busy} error={dialogError ? <OrgError error={dialogError} /> : undefined}
        onConfirm={() => void add()} onCancel={() => setConfirmAdd(false)}
      />
      <ReasonDialog
        open={!!removing}
        title={t("organizations.members.removeTitle", { name: removingName })}
        effect={t(isAdmins ? "organizations.members.removeAdminBody" : "organizations.members.removeBody", { name: removingName, org: org.name })}
        confirmLabel={t("organizations.members.remove")} tone="danger" busy={busy}
        error={dialogError ? <OrgError error={dialogError} /> : undefined}
        onConfirm={(r) => void remove(r)} onCancel={() => setRemoving(null)}
      />
    </div>
  );
}
