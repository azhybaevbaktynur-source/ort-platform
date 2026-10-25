"use client";

import React, { useCallback, useEffect, useState } from "react";
import { useTranslation } from "@/lib/i18n/context";
import {
  grantTemplate, listOrganizationTemplates, revokeTemplate, type OrganizationOut, type OrgTemplateGrantOut,
} from "@/lib/lms/organizations";
import { templateTitle } from "@/lib/lms/templates";
import { fmtApiDate } from "@/lib/format";
import { ConfirmDialog } from "@/components/lms/ConfirmDialog";
import { EmptyBox, Loading, OrgBadge, OrgError } from "../OrgUi";
import { toast } from "@/components/ui/Toast";

/** Platform admin: one row per registry template with a "Granted" switch (confirm dialog names the effect). */
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

  const confirm = async () => {
    if (!target) return;
    setBusy(true);
    setDialogError(null);
    try {
      if (target.granted) await revokeTemplate(org.id, target.key);
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

  if (error) return <OrgError error={error} onRetry={load} />;
  if (!rows) return <Loading />;
  if (rows.length === 0) return <EmptyBox text={t("organizations.templates.empty")} />;
  const name = target ? templateTitle(t, target.key) : "";
  return (
    <div className="space-y-3">
      <p className="text-sm text-slate-600">{t("organizations.templates.intro")}</p>
      <ul className="divide-y divide-slate-100 rounded-2xl border border-slate-200 bg-white text-sm">
        {rows.map((r) => {
          const title = templateTitle(t, r.key);
          const id = `tpl-${r.key}`;
          return (
            <li key={r.key} className="flex flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3">
              <div className="min-w-0 flex-1 basis-56">
                <p id={id} className="font-medium text-slate-900">{title}</p>
                <p className="text-xs text-slate-500">
                  {t("organizations.templates.grantOnly")}
                  {r.granted && r.granted_at ? ` · ${t("organizations.templates.grantedOn", { date: fmtApiDate(r.granted_at, lang) })}` : ""}
                </p>
              </div>
              <OrgBadge tone={r.granted ? "granted" : "notGranted"} labelKey={r.granted ? "organizations.templates.stateGranted" : "organizations.templates.stateNotGranted"} />
              <button type="button" role="switch" aria-checked={r.granted} aria-labelledby={id}
                onClick={() => { setDialogError(null); setTarget(r); }}
                className="inline-flex min-h-[44px] items-center gap-2 rounded-lg px-2 text-sm font-medium text-slate-700 hover:bg-slate-50">
                <span aria-hidden="true" className={`relative inline-block h-6 w-11 rounded-full transition-colors ${r.granted ? "bg-brand-600" : "bg-slate-300"}`}>
                  <span className={`absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-all ${r.granted ? "left-[1.375rem]" : "left-0.5"}`} />
                </span>
                {t("organizations.templates.switch")}
              </button>
            </li>
          );
        })}
      </ul>
      <ConfirmDialog
        open={!!target}
        title={t(target?.granted ? "organizations.templates.revokeTitle" : "organizations.templates.grantTitle", { template: name, org: org.name })}
        body={t(target?.granted ? "organizations.templates.revokeBody" : "organizations.templates.grantBody", { template: name, org: org.name })}
        confirmLabel={t(target?.granted ? "organizations.templates.revoke" : "organizations.templates.grant")}
        danger={!!target?.granted} busy={busy} error={dialogError}
        onConfirm={() => void confirm()} onCancel={() => setTarget(null)}
      />
    </div>
  );
}
