"use client";

// Phase 7a S5: quiz access code in the assessment settings (PHASE_7A_DESIGN 2.7, 5). The code is never sent back by
// the server: the field shows "a code is set" with Change / Clear, or an input with show / hide. Controlled value:
// undefined = unchanged, a string = set this code, null = clear.
import React, { useId, useState } from "react";
import { Eye, EyeOff, KeyRound } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { ACCESS_CODE_MAX, accessCodeIssue } from "@/lib/lms/accommodations";
import { Badge, Button, IconButton, Input } from "@/components/ui";

export function accessCodeError(value: string | null | undefined): string | null {
  return typeof value === "string" ? accessCodeIssue(value) : null;
}

export function AccessCodeField({ hasCode, value, onChange, disabled }: {
  hasCode: boolean;
  value: string | null | undefined;
  onChange: (v: string | null | undefined) => void;
  disabled?: boolean;
}) {
  const { t } = useTranslation();
  const id = useId();
  const [show, setShow] = useState(false);
  const issue = accessCodeError(value);
  const editing = typeof value === "string" || (!hasCode && value === undefined);
  const cleared = value === null;

  return (
    <fieldset className="space-y-2 rounded-xl border border-slate-200 p-4" disabled={disabled}>
      <legend className="px-1 text-sm font-bold text-slate-900">{t("accommodations.accessCode.title")}</legend>
      <p className="text-sm text-slate-600">{t("accommodations.accessCode.hint")}</p>
      {hasCode && !editing && !cleared && (
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone="info" icon={<KeyRound aria-hidden="true" />}>{t("accommodations.accessCode.isSet")}</Badge>
          <Button variant="secondary" size="sm" onClick={() => onChange("")}>{t("accommodations.accessCode.change")}</Button>
          <Button variant="secondary" size="sm" onClick={() => onChange(null)}>{t("accommodations.accessCode.clear")}</Button>
        </div>
      )}
      {cleared && (
        <div className="flex flex-wrap items-center gap-2">
          <p role="status" className="text-sm text-slate-800">{t("accommodations.accessCode.willClear")}</p>
          <Button variant="link" onClick={() => onChange(undefined)}>{t("accommodations.accessCode.undo")}</Button>
        </div>
      )}
      {editing && (
        <div className="space-y-2">
          <Input id={`${id}-code`} label={t("accommodations.accessCode.label")} optional={!hasCode} type={show ? "text" : "password"}
            autoComplete="off" spellCheck={false} maxLength={ACCESS_CODE_MAX + 8}
            value={value ?? ""} onChange={(e) => onChange(e.target.value === "" && !hasCode ? undefined : e.target.value)}
            hint={t("accommodations.accessCode.rules")}
            error={value && issue ? t(`accommodations.accessCode.issues.${issue}`) : undefined}
            trailing={<IconButton aria-label={show ? t("accommodations.accessCode.hide") : t("accommodations.accessCode.show")}
              icon={show ? <EyeOff /> : <Eye />} onClick={() => setShow((s) => !s)} />}
            containerClassName="sm:max-w-sm" />
          {hasCode && <Button variant="link" onClick={() => onChange(undefined)}>{t("accommodations.accessCode.keep")}</Button>}
        </div>
      )}
    </fieldset>
  );
}
