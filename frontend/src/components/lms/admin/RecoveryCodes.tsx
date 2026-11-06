"use client";

import React, { useState } from "react";
import { Copy } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { Button, Card, Checkbox, toast } from "@/components/ui";

/** S1: recovery codes, shown once. The person confirms they saved them before the list goes away. */
export function RecoveryCodes({ codes, onDone }: { codes: string[]; onDone: () => void }) {
  const { t } = useTranslation();
  const [saved, setSaved] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(codes.join("\n"));
      toast.success(t("adminSecurity.codes.copied"));
    } catch {
      // clipboard blocked: the codes stay on screen to write down
    }
  };
  return (
    <Card title={t("adminSecurity.codes.title")} description={t("adminSecurity.codes.body")} className="mb-6"
      actions={<Button variant="secondary" size="sm" leftIcon={<Copy aria-hidden="true" className="h-4 w-4" />} onClick={() => void copy()}>{t("adminSecurity.codes.copy")}</Button>}>
      <ol data-testid="recovery-codes" className="mb-4 grid grid-cols-1 gap-2 font-mono text-base text-slate-900 sm:grid-cols-2">
        {codes.map((c) => (
          <li key={c} className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-center tracking-wider">{c}</li>
        ))}
      </ol>
      <Checkbox label={t("adminSecurity.codes.saved")} checked={saved} onChange={(e) => setSaved(e.target.checked)} />
      <Button className="mt-4" disabled={!saved} onClick={onDone}>{t("adminSecurity.codes.done")}</Button>
    </Card>
  );
}
