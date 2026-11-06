"use client";

import React, { useEffect, useRef, useState } from "react";
import { useTranslation } from "@/lib/i18n/context";
import { ConfirmDialog, Input, Textarea, type ConfirmDialogProps } from "@/components/ui";

interface CodeReasonDialogProps extends Omit<ConfirmDialogProps, "onConfirm" | "children" | "initialFocusRef"> {
  onConfirm: (reason: string, code: string) => void;
}

/** S1: a sensitive admin action, confirmed with a reason and the acting admin's current authenticator code. */
export function CodeReasonDialog({ open, onConfirm, ...rest }: CodeReasonDialogProps) {
  const { t } = useTranslation();
  const [reason, setReason] = useState("");
  const [code, setCode] = useState("");
  const [missing, setMissing] = useState<"reason" | "code" | null>(null);
  const reasonRef = useRef<HTMLTextAreaElement>(null);
  useEffect(() => { if (open) { setReason(""); setCode(""); setMissing(null); } }, [open]);
  return (
    <ConfirmDialog
      {...rest}
      open={open}
      initialFocusRef={reasonRef}
      onConfirm={() => {
        if (!reason.trim()) { setMissing("reason"); reasonRef.current?.focus(); return; }
        if (code.length !== 6) { setMissing("code"); return; }
        onConfirm(reason.trim(), code);
      }}
    >
      <Textarea
        ref={reasonRef}
        containerClassName="mt-4"
        label={t("ui.reason.required")}
        hint={t("ui.reason.limit", { n: 500 })}
        error={missing === "reason" ? t("ui.reason.missing") : undefined}
        value={reason}
        maxLength={500}
        rows={3}
        required
        disabled={rest.busy}
        onChange={(e) => { setReason(e.target.value); setMissing(null); }}
      />
      <Input
        containerClassName="mt-4"
        label={t("adminSecurity.confirmCode.label")}
        hint={t("adminSecurity.confirmCode.hint")}
        error={missing === "code" ? t("adminSecurity.confirmCode.missing") : undefined}
        inputMode="numeric"
        autoComplete="one-time-code"
        placeholder="000000"
        maxLength={6}
        value={code}
        disabled={rest.busy}
        className="max-w-[12rem] font-mono text-lg tracking-[0.3em]"
        onChange={(e) => { setCode(e.target.value.replace(/\D/g, "").slice(0, 6)); setMissing(null); }}
      />
    </ConfirmDialog>
  );
}
