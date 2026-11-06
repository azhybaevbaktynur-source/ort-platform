"use client";

import React from "react";
import { Check, Circle, Clock, Minus, X } from "lucide-react";
import { Badge, cn, type BadgeTone } from "@/components/ui";
import { useTranslation } from "@/lib/i18n/context";
import { MathRenderer } from "@/components/math/MathRenderer";
import { TemplatePassage } from "@/components/lms/PlainPassage";
import type { Correctness, ReviewItemOut, StudentQuestion } from "@/lib/lms/attemptTypes";
import { fmtPoints } from "@/components/lms/assessments/format";
import type { PassageDisplay } from "@/lib/lms/blocks";
import type { StudentQuestionOut } from "@/lib/lms/contentTypes";

// Design-system Badge with an icon, so colour is never the only signal (S7b, cross-cutting).
const TONE: Record<Correctness, BadgeTone> = {
  correct: "success",
  incorrect: "danger",
  partial: "warning",
  unanswered: "neutral",
  pending: "info",
};
const ICON: Record<Correctness, React.ReactNode> = {
  correct: <Check aria-hidden="true" />,
  incorrect: <X aria-hidden="true" />,
  partial: <Circle aria-hidden="true" />,
  unanswered: <Minus aria-hidden="true" />,
  pending: <Clock aria-hidden="true" />,
};

export function CorrectnessBadge({ value }: { value: Correctness | null }) {
  const { t } = useTranslation();
  if (!value) return null;
  return <Badge tone={TONE[value]} icon={ICON[value]}>{t(`results.correctness.${value}`)}</Badge>;
}

function asArr(v: unknown): string[] {
  return Array.isArray(v) ? v.map(String) : [];
}

/** Human-readable text for a key entry (numeric / short answers, whose shape is type specific). */
function keyEntryText(a: unknown): string {
  if (a === null || a === undefined) return "";
  if (typeof a === "string" || typeof a === "number" || typeof a === "boolean") return String(a);
  if (typeof a === "object") {
    const o = a as Record<string, unknown>;
    if (o.kind === "range" || ("min" in o && "max" in o)) return `${o.min ?? o.low ?? ""} – ${o.max ?? o.high ?? ""}`;
    if ("value" in o) return o.tolerance ? `${String(o.value)} ± ${String(o.tolerance)}` : String(o.value);
    return JSON.stringify(a);
  }
  return String(a);
}

/** Read-only question with the student's answer (and the key when present). */
export function ReviewItemCard({
  item,
  number,
  maxPoints,
  children,
  viewer = "student",
  passageDisplay,
  anchorId,
}: {
  /** SF-1 / problem 3: the result page's anchor (`item-{position}`), the target of `#item-n` links. */
  anchorId?: string;
  item: ReviewItemOut;
  number: number;
  maxPoints?: number | string | null;
  children?: React.ReactNode;
  /** Phase 6b S5c (UX T12, T22): "staff" labels the answer "Student's answer". Both viewers use the body font (S7b, P7). */
  viewer?: "student" | "staff";
  /** Phase 8b S3 (PHASE_8B_DESIGN 8.2): renderer from the review payload (`passage_display`); absent = course template. */
  passageDisplay?: PassageDisplay | null;
}) {
  const { t } = useTranslation();
  const answerLabel = viewer === "staff" ? t("teaching.studentAnswer") : t("results.yourAnswer");
  const q: StudentQuestion = item.question;
  const resp = (item.response ?? {}) as Record<string, unknown>;
  const key = item.key ?? null;
  const passage = item.passage ?? q.passage ?? null;
  const max = maxPoints ?? q.points ?? null;
  const sd = q.data as StudentQuestionOut["data"]; // Phase 10 S1: structured fields
  const keyList = (name: string): Record<string, unknown>[] => (key && Array.isArray(key[name]) ? (key[name] as Record<string, unknown>[]) : []);

  return (
    <article id={anchorId} className={cn("space-y-4 rounded-2xl border border-slate-200 bg-white p-5", anchorId && "scroll-mt-20")} aria-label={t("results.questionN", { n: number })}>
      <header className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 pb-3">
        <h3 className="rounded-lg bg-brand-50 px-3 py-1 text-xs font-bold uppercase tracking-wide text-brand-700">{t("results.questionN", { n: number })}</h3>
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <CorrectnessBadge value={item.correctness} />
          {item.score !== null && item.score !== undefined && (
            <span className="font-semibold text-slate-700">
              {max !== null && max !== undefined ? t("results.scoreOf", { score: fmtPoints(item.score), max: fmtPoints(max), count: fmtPoints(max) }) : fmtPoints(item.score)}
            </span>
          )}
        </div>
      </header>

      {passage && (
        <details className="rounded-xl border border-slate-200 bg-slate-50 p-3">
          <summary className="cursor-pointer text-sm font-medium text-slate-700">{passage.title || t("results.passage")}</summary>
          <div className="mt-2"><TemplatePassage text={passage.body} display={passageDisplay} /></div>
        </details>
      )}

      {q.stem ? <MathRenderer content={q.stem} className="text-base leading-relaxed text-slate-900" /> : null}
      {q.image_url ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={q.image_url} alt={t("results.imageAlt")} className="max-h-72 w-auto rounded-lg border border-slate-100" />
      ) : null}

      {(q.type === "single_choice" || q.type === "multiple_answers") && (
        <ul className="space-y-2">
          {(q.data.choices ?? []).map((c) => {
            const picked = q.type === "single_choice" ? resp.choice_id === c.id : asArr(resp.choice_ids).includes(c.id);
            const correct = key ? (q.type === "single_choice" ? key.correct === c.id : asArr(key.correct).includes(c.id)) : false;
            const cls = correct ? "border-emerald-400 bg-emerald-50" : picked ? "border-red-300 bg-red-50" : "border-slate-200 bg-white";
            return (
              <li key={c.id} className={`flex items-start gap-3 rounded-xl border px-4 py-2.5 ${cls}`}>
                <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center" aria-hidden="true">
                  {correct ? <Check className="h-4 w-4 text-emerald-700" /> : picked ? <X className="h-4 w-4 text-red-700" /> : null}
                </span>
                <span className="min-w-0 flex-1">
                  {c.text ? <MathRenderer content={c.text} className="text-base text-slate-900" /> : null}
                  {c.image_url ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={c.image_url} alt="" className="mt-1 max-h-32 w-auto rounded-md" />
                  ) : null}
                </span>
                {/* Phase 6 S8: layout only; the label wraps instead of widening the card at 375 px (long ky text). */}
                <span className="min-w-0 max-w-[45%] text-right text-xs font-medium text-slate-600">
                  {picked ? answerLabel : ""}{picked && correct ? " · " : ""}{correct ? t("results.correctAnswer") : ""}
                </span>
              </li>
            );
          })}
        </ul>
      )}

      {q.type === "true_false" && (
        <dl className="grid gap-2 text-sm sm:grid-cols-2">
          <div><dt className="text-xs text-slate-500">{answerLabel}</dt><dd className="font-medium">{typeof resp.value === "boolean" ? (resp.value ? t("results.true") : t("results.false")) : t("results.noAnswer")}</dd></div>
          {key && typeof key.correct === "boolean" && <div><dt className="text-xs text-slate-500">{t("results.correctAnswer")}</dt><dd className="font-medium text-emerald-700">{key.correct ? t("results.true") : t("results.false")}</dd></div>}
        </dl>
      )}

      {q.type === "comparison" && (
        <div className="space-y-2">
          <div className="grid gap-3 sm:grid-cols-2">
            {(["a", "b"] as const).map((k) => (
              <div key={k} className="rounded-xl border border-slate-200 bg-slate-50 p-3 text-center">
                <p className="mb-1 text-xs font-bold uppercase text-slate-500">{k === "a" ? t("results.columnA") : t("results.columnB")}</p>
                <MathRenderer content={(k === "a" ? q.data.column_a : q.data.column_b) || "—"} />
              </div>
            ))}
          </div>
          <dl className="grid gap-2 text-sm sm:grid-cols-2">
            <div><dt className="text-xs text-slate-500">{answerLabel}</dt><dd className="font-medium">{typeof resp.choice === "string" ? t(`bank.types.comparison.labels.${resp.choice}`) : t("results.noAnswer")}</dd></div>
            {key && typeof key.correct === "string" && <div><dt className="text-xs text-slate-500">{t("results.correctAnswer")}</dt><dd className="font-medium text-emerald-700">{t(`bank.types.comparison.labels.${key.correct}`)}</dd></div>}
          </dl>
        </div>
      )}

      {(q.type === "numeric" || q.type === "short_text") && (
        <dl className="grid gap-2 text-sm sm:grid-cols-2">
          <div>
            <dt className="text-xs text-slate-500">{answerLabel}</dt>
            <dd className="font-mono font-medium">{(q.type === "numeric" ? (resp.value as string | undefined) : (resp.text as string | undefined)) || t("results.noAnswer")}</dd>
          </div>
          {key && Array.isArray(key.answers) && key.answers.length > 0 && (
            <div><dt className="text-xs text-slate-500">{t("results.acceptedAnswers")}</dt><dd className="font-mono font-medium text-emerald-700">{key.answers.map(keyEntryText).join(" ; ")}</dd></div>
          )}
        </dl>
      )}

      {q.type === "matching" && (() => {
        const given = (resp.pairs ?? {}) as Record<string, string>;
        const rightText = new Map((sd.rights ?? []).map((r) => [r.id, r.text]));
        const keyPairs = new Map(keyList("pairs").map((p) => [String(p.left_id), String(p.right_id)]));
        return (
          <ul className="space-y-2">
            {(sd.lefts ?? []).map((l) => {
              const g = given[l.id];
              const ok = key ? keyPairs.get(l.id) === g : false;
              const cls = !key ? "border-slate-200 bg-white" : ok ? "border-emerald-400 bg-emerald-50" : "border-red-300 bg-red-50";
              return (
                <li key={l.id} className={`rounded-xl border px-4 py-2.5 text-sm ${cls}`}>
                  <MathRenderer content={l.text} className="font-medium text-slate-900" />
                  <p className="text-slate-700">{answerLabel}: {g ? rightText.get(g) ?? g : t("results.noAnswer")}</p>
                  {key && !ok && <p className="font-medium text-emerald-700">{t("results.correctAnswer")}: {rightText.get(keyPairs.get(l.id) ?? "") ?? ""}</p>}
                </li>
              );
            })}
          </ul>
        );
      })()}

      {q.type === "fill_blank" && (() => {
        const given = (resp.blanks ?? {}) as Record<string, string>;
        const blanks = keyList("blanks");
        const n = blanks.length || sd.blank_count || Object.keys(given).length;
        return (
          <ol className="space-y-1 text-sm">
            {Array.from({ length: n }, (_, i) => {
              const answers = Array.isArray(blanks[i]?.answers) ? (blanks[i].answers as string[]) : null;
              return (
                <li key={i} className="rounded-xl border border-slate-200 px-4 py-2">
                  <span className="text-xs text-slate-500">{t("results.structured.blankN", { n: i + 1 })}</span>{" "}
                  <span className="font-mono font-medium">{given[String(i + 1)] || t("results.noAnswer")}</span>
                  {answers && <span className="block font-mono font-medium text-emerald-700">{t("results.acceptedAnswers")}: {answers.join(" ; ")}</span>}
                </li>
              );
            })}
          </ol>
        );
      })()}

      {q.type === "ordering" && (() => {
        const text = new Map((sd.items ?? []).map((i) => [i.id, i.text]));
        const given = Array.isArray(resp.order) ? (resp.order as string[]) : [];
        const correct = key && Array.isArray(key.order) ? (key.order as string[]) : null;
        return (
          <div className="grid gap-3 sm:grid-cols-2">
            <div>
              <p className="mb-1 text-xs text-slate-500">{answerLabel}</p>
              {given.length ? (
                <ol className="space-y-1 text-sm">
                  {given.map((id, i) => (
                    <li key={`${id}-${i}`} className={`rounded-xl border px-3 py-1.5 ${correct ? (correct[i] === id ? "border-emerald-400 bg-emerald-50" : "border-red-300 bg-red-50") : "border-slate-200"}`}>
                      {i + 1}. {text.get(id) ?? id}
                    </li>
                  ))}
                </ol>
              ) : <p className="text-sm text-slate-500">{t("results.noAnswer")}</p>}
            </div>
            {correct && (
              <div>
                <p className="mb-1 text-xs text-slate-500">{t("results.correctAnswer")}</p>
                <ol className="space-y-1 text-sm">{correct.map((id, i) => <li key={id} className="rounded-xl border border-slate-200 px-3 py-1.5 text-emerald-700">{i + 1}. {text.get(id) ?? id}</li>)}</ol>
              </div>
            )}
          </div>
        );
      })()}

      {q.type === "essay" && (
        <div>
          <p className="mb-1 text-xs text-slate-500">{answerLabel}</p>
          {typeof resp.text === "string" && resp.text.trim() ? (
            <p className="whitespace-pre-wrap rounded-xl border border-slate-200 bg-slate-50 p-3 text-sm text-slate-900">{resp.text}</p>
          ) : (
            <p className="text-sm text-slate-500">{t("results.noAnswer")}</p>
          )}
        </div>
      )}

      {item.explanation ? (
        <div className="rounded-xl border border-sky-200 bg-sky-50 p-3">
          <p className="mb-1 text-xs font-semibold text-sky-800">{t("results.explanation")}</p>
          <MathRenderer content={item.explanation} className="text-sm text-slate-900" />
        </div>
      ) : null}
      {item.feedback ? (
        <div className="rounded-xl border border-violet-200 bg-violet-50 p-3">
          <p className="mb-1 text-xs font-semibold text-violet-800">{t("results.teacherFeedback")}</p>
          <p className="whitespace-pre-wrap text-sm text-slate-900">{item.feedback}</p>
        </div>
      ) : null}
      {children}
    </article>
  );
}
