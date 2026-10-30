"use client";

import React, { useEffect, useState } from "react";
import { Info } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { updateOrgSettings, type OrgSettingsViewOut } from "@/lib/lms/organizations";
import type { CatalogDefaults, OrganizationSettings } from "@/lib/lms/types";
import { Button, Card, Input, Select, Switch, toast } from "@/components/ui";
import { OrgError } from "./OrgUi";

const MODES: CatalogDefaults["enrollment_mode"][] = ["invite_code", "open", "closed", "form_review"];

/**
 * Phase 9 S2 (PHASE_9_DESIGN 4.3): the settings of a tree. They live on the root; a department (or a suspended
 * organization) shows them read-only with the reason. One Save at the end (sends only what changed).
 */
export function OrgSettingsForm({ view, readOnly, onSaved }: { view: OrgSettingsViewOut; readOnly: boolean; onSaved: (v: OrgSettingsViewOut) => void }) {
  const { t } = useTranslation();
  const [value, setValue] = useState<OrganizationSettings>(view.settings);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  useEffect(() => { setValue(view.settings); }, [view]);

  const personal = view.kind === "personal";
  const locked = readOnly || !view.editable || busy;
  const retentionOk = Number.isInteger(value.application_retention_days)
    && value.application_retention_days >= 30 && value.application_retention_days <= 90;
  const set = <K extends keyof OrganizationSettings>(k: K, v: OrganizationSettings[K]) => setValue((p) => ({ ...p, [k]: v }));
  const setDefaults = (patch: Partial<CatalogDefaults>) => set("catalog_defaults", { ...value.catalog_defaults, ...patch });

  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!retentionOk) return;
    setBusy(true);
    setError(null);
    try {
      const body = {
        teachers_can_create_courses: value.teachers_can_create_courses,
        catalog_defaults: value.catalog_defaults,
        application_retention_days: value.application_retention_days,
        student_invitations_enabled: value.student_invitations_enabled,
        ...(personal ? {} : { bank_sharing_enabled: value.bank_sharing_enabled }),
      };
      const out = await updateOrgSettings(view.organization_id, body);
      onSaved(out);
      toast.success(t("orgSettings.saved"));
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };

  return (
    <form onSubmit={save} noValidate className="space-y-4">
      {!view.editable && (
        <p role="status" className="flex items-start gap-3 rounded-2xl border border-slate-200 bg-slate-50 p-4 text-sm leading-6 text-slate-700">
          <Info aria-hidden="true" className="mt-0.5 h-5 w-5 shrink-0" />
          <span className="min-w-0 break-words">{t("orgSettings.readOnly", { root: view.root_name })}</span>
        </p>
      )}
      <Card title={t("orgSettings.coursesTitle")}>
        <Switch label={t("orgSettings.teachersCanCreate")} hint={t("orgSettings.teachersCanCreateHint")}
          checked={value.teachers_can_create_courses} disabled={locked} onChange={(v) => set("teachers_can_create_courses", v)} />
      </Card>
      <Card title={t("orgSettings.banksTitle")}>
        <Switch label={t("orgSettings.bankSharing")}
          hint={personal ? t("orgSettings.bankSharingPersonal") : t("orgSettings.bankSharingHint")}
          checked={!personal && value.bank_sharing_enabled} disabled={locked || personal}
          onChange={(v) => set("bank_sharing_enabled", v)} />
      </Card>
      <Card title={t("orgSettings.studentsTitle")}>
        <Switch label={t("orgSettings.studentInvitations")} hint={t("orgSettings.studentInvitationsHint")}
          checked={value.student_invitations_enabled} disabled={locked} onChange={(v) => set("student_invitations_enabled", v)} />
        <Input type="number" inputMode="numeric" min={30} max={90} containerClassName="mt-4 sm:max-w-xs"
          label={t("orgSettings.retention")} hint={t("orgSettings.retentionHint")} disabled={locked}
          error={!retentionOk ? t("orgSettings.retentionHint") : undefined}
          trailing={<span className="pr-3 text-sm text-slate-600">{t("orgSettings.days")}</span>}
          value={Number.isFinite(value.application_retention_days) ? String(value.application_retention_days) : ""}
          onChange={(e) => set("application_retention_days", e.target.value === "" ? NaN : Number(e.target.value))} />
      </Card>
      <Card title={t("orgSettings.defaultsTitle")} description={t("orgSettings.defaultsHint")}>
        <div className="grid gap-4 sm:grid-cols-2">
          <Select label={t("orgSettings.visibility")} value={value.catalog_defaults.visibility} disabled={locked}
            options={(["private", "catalog"] as const).map((v) => ({ value: v, label: t(`orgSettings.visibilityOptions.${v}`) }))}
            onChange={(e) => setDefaults({ visibility: e.target.value as CatalogDefaults["visibility"] })} />
          <Select label={t("orgSettings.enrollmentMode")} value={value.catalog_defaults.enrollment_mode} disabled={locked}
            options={MODES.map((m) => ({ value: m, label: t(`orgSettings.modes.${m}`) }))}
            onChange={(e) => setDefaults({ enrollment_mode: e.target.value as CatalogDefaults["enrollment_mode"] })} />
        </div>
      </Card>
      <OrgError error={error} />
      {view.editable && (
        <div className="flex justify-end">
          <Button type="submit" loading={busy} disabled={readOnly || !retentionOk} className="w-full sm:w-auto">{t("orgSettings.save")}</Button>
        </div>
      )}
    </form>
  );
}
