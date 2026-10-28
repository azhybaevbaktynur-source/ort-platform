"use client";

import React from "react";
import { useTranslation } from "@/lib/i18n/context";
import { pickLocalized } from "@/lib/lms/localized";
import type { EditScope, ScopeRequiredDetails } from "@/lib/lms/quizEditorTypes";
import type { Lang } from "@/lib/lms/types";
import { Badge, Button, Dialog } from "@/components/ui";

/**
 * 7c-2: the question of this card is used in other quizzes. Asked once, when the card is closed with "Done".
 * "Update in all" is disabled with its reason when the teacher cannot edit the source bank.
 */
export function ScopeDialog({
  details, busy, defaultLanguage, onChoose, onCancel, passageChild = false,
}: {
  details: ScopeRequiredDetails | null;
  busy: boolean;
  defaultLanguage: Lang;
  onChoose: (scope: EditScope) => void;
  onCancel: () => void;
  /** Phase 7c S5: a question inside a passage block cannot leave it (409 passage_child_scope): only "all" is offered. */
  passageChild?: boolean;
}) {
  const { lang, t } = useTranslation();
  const n = details?.assessment_count ?? 0;
  const others = (details?.assessments ?? []).filter((x) => !x.is_this);
  return (
    <Dialog open={!!details} onClose={onCancel} busy={busy} title={t("quizEditor.scope.title")}
      description={t("quizEditor.scope.body", { n })}
      footer={(
        <>
          <Button variant="secondary" disabled={busy} onClick={onCancel}>{t("quizEditor.scope.cancel")}</Button>
          <Button variant="secondary" disabled={busy || passageChild}
            aria-describedby={passageChild ? "scope-this-reason" : undefined} onClick={() => onChoose("this")}>{t("quizEditor.scope.this")}</Button>
          <Button variant="primary" loading={busy} disabled={!details?.can_update_all}
            aria-describedby={details && !details.can_update_all ? "scope-all-reason" : undefined}
            onClick={() => onChoose("all")}>{t("quizEditor.scope.all", { n: n + 1 })}</Button>
        </>
      )}>
      {others.length > 0 && (
        <ul className="mb-3 space-y-1.5">
          {others.map((x) => (
            <li key={x.id} className="flex flex-wrap items-center gap-2 text-sm text-slate-800">
              <span className="min-w-0 break-words">{pickLocalized(x.title, lang, defaultLanguage) || t("assessments.untitled")}</span>
              {x.status === "published" && <Badge tone="info">{t("quizEditor.scope.published")}</Badge>}
            </li>
          ))}
          {n > others.length && <li className="text-sm text-slate-600">{t("quizEditor.scope.more", { n: n - others.length })}</li>}
        </ul>
      )}
      <p className="text-sm text-slate-700">{t("quizEditor.scope.republishNote")}</p>
      {details && passageChild && (
        <p id="scope-this-reason" className="mt-2 text-sm text-slate-700">{t("quizEditor.errors.passage_child_scope")}</p>
      )}
      {details && !details.can_update_all && (
        <p id="scope-all-reason" className="mt-2 text-sm text-amber-900">{t("quizEditor.scope.allDisabled")}</p>
      )}
    </Dialog>
  );
}
