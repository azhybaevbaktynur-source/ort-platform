"use client";

// Exam prep S2: one bar per exam section from the latest released result (what the result already stores: points per
// section). The number is the text ("18 of 30"); the bar only shows the share.
import React from "react";
import { useTranslation } from "@/lib/i18n/context";
import { type ExamPrepOut } from "@/lib/lms/examPrep";
import { cn } from "@/components/ui";

const num = (v: string | number) => {
  const n = Number(v);
  return Number.isFinite(n) ? n : 0;
};
const plain = (n: number) => (Number.isInteger(n) ? String(n) : n.toFixed(1));

export function SectionBars({ data, className }: { data: ExamPrepOut; className?: string }) {
  const { t } = useTranslation();
  return (
    <section aria-labelledby="exam-sections" className={cn("min-w-0 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm", className)}>
      <h2 id="exam-sections" className="text-base font-semibold leading-6 text-slate-900">{t("examPrep.sections.title")}</h2>
      {data.sections.length === 0 ? (
        <p className="mt-2 text-sm leading-6 text-slate-600">{t("examPrep.sections.empty")}</p>
      ) : (
        <>
          <p className="text-sm leading-5 text-slate-600">{t("examPrep.sections.subtitle")}</p>
          <ul className="mt-3 space-y-3">
            {data.sections.map((s) => {
              const raw = num(s.raw);
              const possible = num(s.possible);
              const pct = possible > 0 ? Math.max(0, Math.min(100, (raw / possible) * 100)) : 0;
              const name = t(`sections.${s.key}`);
              const score = t("examPrep.sections.score", { raw: plain(raw), possible: plain(possible) });
              return (
                <li key={s.key}>
                  <div className="flex items-baseline justify-between gap-3 text-sm leading-5">
                    <span className="min-w-0 break-words text-slate-800">{name}</span>
                    <span className="shrink-0 font-semibold tabular-nums text-slate-900">{score}</span>
                  </div>
                  <div role="progressbar" aria-label={name} aria-valuemin={0} aria-valuemax={possible} aria-valuenow={raw} aria-valuetext={score}
                    className="mt-1.5 h-2.5 overflow-hidden rounded-full bg-slate-100">
                    <div className="h-full rounded-full bg-brand-600" style={{ width: `${pct}%` }} />
                  </div>
                </li>
              );
            })}
          </ul>
        </>
      )}
    </section>
  );
}
