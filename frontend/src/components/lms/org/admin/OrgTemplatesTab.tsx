"use client";

import React, { useCallback, useEffect, useState } from "react";
import { useTranslation } from "@/lib/i18n/context";
import {
  grantTemplate, listOrganizationTemplates, revokeTemplate, type OrganizationOut, type OrgTemplateGrantOut,
} from "@/lib/lms/organizations";
import { templateTitle } from "@/lib/lms/templates";
import { fmtApiDate } from "@/lib/format";
import { ConfirmDialog, EmptyState, ReasonDialog, Switch, Table, toast, type TableColumn } from "@/components/ui";
import { LoadError, OrgBadge, OrgError } from "../OrgUi";

/** Platform admin: one row per registry template with a "Granted" switch (the confirm dialog names the effect). */
export function OrgTemplatesTab({ org }: { org: OrganizationOut }) {
  const { lang, t } = useTranslation();
  const [rows, setRows] = useState<OrgTemplateGrantOut[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [target, setTarget] = useState<OrgTemplateGrantOut | null>(null);
  const [busy, setBusy] = useState(false);
  const [dialogError, setDialogError] = useState<unknown>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      // One row per registry template, granted or not (the backend lists every known template).
      setRows(await listOrganizationTemplates(org.id));
    } catch (e) {
      setError(e);
    }
  }, [org.id]);
  useEffect(() => { void load(); }, [load]);

  const confirm = async (reason = "") => {
    if (!target) return;
    setBusy(true);
    setDialogError(null);
    try {
      if (target.granted) await revokeTemplate(org.id, target.key, reason);
      else await grantTemplate(org.id, target.key);
      toast.success(t(target.granted ? "organizations.templates.revoked" : "organizations.templates.granted", { template: templateTitle(t, target.key) }));
      setTarget(null);
      await load();
    } catch (e) {
      setDialogError(e);
    } finally {
      setBusy(false);
    }
  };

  const name = target ? templateTitle(t, target.key) : "";
  const columns: TableColumn<OrgTemplateGrantOut>[] = [
    {
      key: "template", header: t("templates.field"), primary: true,
      cell: (r) => (
        <>
          {templateTitle(t, r.key)}
          <span className="block text-sm font-normal text-slate-600">
            {t("organizations.templates.grantOnly")}
            {r.granted && r.granted_at ? ` · ${t("organizations.templates.grantedOn", { date: fmtApiDate(r.granted_at, lang) })}` : ""}
          </span>
        </>
      ),
    },
    {
      key: "state", header: t("organizations.admin.status"),
      cell: (r) => <OrgBadge tone={r.granted ? "granted" : "notGranted"} labelKey={r.granted ? "organizations.templates.stateGranted" : "organizations.templates.stateNotGranted"} />,
    },
    {
      key: "switch", header: "", actions: true, align: "right",
      cell: (r) => (
        <Switch id={`tpl-${r.key}`} label={t("organizations.templates.switch")} checked={r.granted}
          containerClassName="w-full sm:w-auto"
          onChange={() => { setDialogError(null); setTarget(r); }} />
      ),
    },
  ];
  return (
    <div className="space-y-3">
      <p className="text-sm text-slate-700">{t("organizations.templates.intro")}</p>
      <Table
        caption={t("organizations.admin.tabs.templates")}
        columns={columns}
        rows={rows ?? []}
        rowKey={(r) => r.key}
        loading={rows === null && !error}
        error={error ? <LoadError error={error} onRetry={load} /> : undefined}
        empty={<EmptyState title={t("organizations.templates.empty")} />}
      />
      {/* Phase 6 S8 (UX P2): revoke asks for an optional reason (audited) and names the organization and the
          effect; grant is a simple confirm. Toast on success both ways. */}
      <ReasonDialog
        open={!!target?.granted} optional
        title={t("organizations.templates.revokeTitle", { template: name, org: org.name })}
        object={name}
        effect={t("organizations.templates.revokeBody", { template: name, org: org.name })}
        confirmLabel={t("organizations.templates.revoke")}
        tone="danger" busy={busy} error={dialogError ? <OrgError error={dialogError} /> : undefined}
        onConfirm={(reason) => void confirm(reason)} onCancel={() => setTarget(null)}
      />
      <ConfirmDialog
        open={!!target && !target.granted}
        title={t("organizations.templates.grantTitle", { template: name, org: org.name })}
        object={name}
        effect={t("organizations.templates.grantBody", { template: name, org: org.name })}
        confirmLabel={t("organizations.templates.grant")}
        busy={busy} error={dialogError ? <OrgError error={dialogError} /> : undefined}
        onConfirm={() => void confirm()} onCancel={() => setTarget(null)}
      />
    </div>
  );
}
