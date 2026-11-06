"use client";

// Exam prep S2: the student's released exam scores over time, a plain inline SVG (no chart library). One series, so no
// legend; the y axis is the exam's scale (ORT 60..245); the target is a dashed gold line; the latest point carries its
// number. Hovering or focusing a point shows its test, score and date; the same values are in a list for screen readers.
import React, { useEffect, useRef, useState } from "react";
import { useTranslation } from "@/lib/i18n/context";
import { pickLocalized } from "@/lib/lms/localized";
import { wholeNumber, type ExamPrepOut } from "@/lib/lms/examPrep";
import { fmtShortDateTime } from "@/components/lms/home/format";
import { cn } from "@/components/ui";

const DEFAULT_W = 600;
const PAD = { left: 40, right: 20, top: 18, bottom: 18 };

export function ScoreHistory({ data, className }: { data: ExamPrepOut; className?: string }) {
  const { lang, t } = useTranslation();
  const [active, setActive] = useState<number | null>(null);
  // the drawing is as wide as its box, so its text keeps its real size on a phone
  const box = useRef<HTMLDivElement>(null);
  const hasPoints = data.history.some((p) => wholeNumber(p.value) !== null);
  const [W, setW] = useState(DEFAULT_W);
  useEffect(() => {
    const el = box.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(([e]) => setW(Math.max(240, Math.round(e.contentRect.width))));
    ro.observe(el);
    return () => ro.disconnect();
  }, [hasPoints]);
  const H = W < 480 ? 180 : 220;
  const points = data.history
    .map((p) => ({ ...p, n: wholeNumber(p.value) }))
    .filter((p): p is typeof p & { n: number } => p.n !== null);
  const lo = wholeNumber(data.goal.scale_min) ?? Math.min(...points.map((p) => p.n), 0);
  const hi = wholeNumber(data.goal.scale_max) ?? Math.max(...points.map((p) => p.n), 1);
  const target = data.goal.target_score;
  const span = Math.max(hi - lo, 1);
  const y = (v: number) => PAD.top + (1 - (Math.min(Math.max(v, lo), hi) - lo) / span) * (H - PAD.top - PAD.bottom);
  const x = (i: number) => points.length <= 1
    ? (PAD.left + W - PAD.right) / 2
    : PAD.left + (i / (points.length - 1)) * (W - PAD.left - PAD.right);
  const untitled = t("assessments.untitled");
  const describe = (i: number) => {
    const p = points[i];
    return t("examPrep.history.point", { title: pickLocalized(p.title, lang) || untitled, value: p.n, date: fmtShortDateTime(p.at, lang) });
  };
  const last = points.length - 1;

  return (
    <section aria-labelledby="exam-history" className={cn("min-w-0 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm", className)}>
      <h2 id="exam-history" className="text-base font-semibold leading-6 text-slate-900">{t("examPrep.history.title")}</h2>
      {points.length === 0 ? (
        <p className="mt-2 text-sm leading-6 text-slate-600">{t("examPrep.history.empty")}</p>
      ) : (
        <>
          <div ref={box} className="relative mt-3">
            <svg viewBox={`0 0 ${W} ${H}`} className="block h-auto w-full" role="img" aria-label={t("examPrep.history.chart")}>
              {/* recessive scale lines: bottom and top of the exam's scale */}
              {[lo, hi].map((v) => (
                <g key={v}>
                  <line x1={PAD.left} x2={W - PAD.right} y1={y(v)} y2={y(v)} className="stroke-slate-200" strokeWidth={1} />
                  <text x={PAD.left - 8} y={y(v)} dy="0.35em" textAnchor="end" className="fill-slate-500 text-[13px]">{v}</text>
                </g>
              ))}
              {target !== null && (
                <g>
                  <line x1={PAD.left} x2={W - PAD.right} y1={y(target)} y2={y(target)} className="stroke-gold-500" strokeWidth={2} strokeDasharray="6 5" />
                  <text x={W - PAD.right} y={y(target) - 6} textAnchor="end" className="fill-gold-900 text-[13px] font-semibold">
                    {t("examPrep.history.target", { value: target })}
                  </text>
                </g>
              )}
              {points.length > 1 && (
                <polyline fill="none" className="stroke-brand-600" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round"
                  points={points.map((p, i) => `${x(i)},${y(p.n)}`).join(" ")} />
              )}
              {points.map((p, i) => (
                <g key={p.attempt_id} tabIndex={0} role="img" aria-label={describe(i)} className="cursor-default outline-none"
                  onMouseEnter={() => setActive(i)} onMouseLeave={() => setActive(null)}
                  onFocus={() => setActive(i)} onBlur={() => setActive(null)}>
                  <circle cx={x(i)} cy={y(p.n)} r={14} className="fill-transparent" />
                  <circle cx={x(i)} cy={y(p.n)} r={active === i ? 7 : 5} className="fill-brand-600 stroke-white" strokeWidth={2} />
                </g>
              ))}
              {last >= 0 && (
                <text x={x(last)} y={y(points[last].n) - 12} textAnchor={points.length > 1 ? "end" : "middle"}
                  className="fill-slate-900 text-[15px] font-bold">{points[last].n}</text>
              )}
            </svg>
            {active !== null && (
              <div role="status" className="pointer-events-none absolute left-1/2 top-0 max-w-[90%] -translate-x-1/2 rounded-lg bg-slate-900 px-2.5 py-1.5 text-xs leading-5 text-white shadow">
                {describe(active)}
              </div>
            )}
          </div>
          <ol className="sr-only">
            {points.map((p, i) => <li key={p.attempt_id}>{describe(i)}</li>)}
          </ol>
        </>
      )}
    </section>
  );
}
