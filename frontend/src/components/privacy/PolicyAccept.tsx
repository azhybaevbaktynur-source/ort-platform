"use client";

import React from "react";
import Link from "next/link";
import { useTranslation } from "@/lib/i18n/context";
import { Checkbox } from "@/components/ui";

/** "I accept the privacy policy and terms of use": the words link to the policy text, in a new tab so a form stays. */
export function PolicyAccept({ checked, onChange, required = false }: { checked: boolean; onChange: (v: boolean) => void; required?: boolean }) {
  const { lang, t } = useTranslation();
  const parts = t("privacy.accept.label").split(/(\{privacy\}|\{terms\})/);
  const label = parts.map((part, i) => {
    if (part !== "{privacy}" && part !== "{terms}") return <React.Fragment key={i}>{part}</React.Fragment>;
    const kind = part === "{privacy}" ? "privacy" : "terms";
    return (
      <Link key={i} href={`/${lang}/policies/${kind}`} target="_blank" rel="noopener" className="font-semibold text-brand-700 underline underline-offset-2">
        {t(`privacy.accept.${kind}`)}
      </Link>
    );
  });
  return <Checkbox label={<>{label}</>} checked={checked} required={required} onChange={(e) => onChange(e.target.checked)} />;
}
