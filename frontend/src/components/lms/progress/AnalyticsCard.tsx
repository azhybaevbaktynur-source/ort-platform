"use client";

import React, { useId } from "react";
import { GoldPill, LinkButton, LockOverlay, Mascot, cn, type MascotPose } from "@/components/ui";
import { useTranslation } from "@/lib/i18n/context";

/*
 * Student UI U6 (STUDENT_UI_DESIGN §3.3): the flat card every analytics block sits in, its designed empty state, a
 * legend in words, and the optional pass lock (off by default, D8).
 */

export function AnalyticsCard({ title, subtitle, aside, children, className, locked = false }: {
  title: React.ReactNode;
  subtitle?: React.ReactNode;
  /** Right side of the header (a summary number, a legend). */
  aside?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  /** Behind the pass: the content is blurred under a LockOverlay (free by default, D8). */
  locked?: boolean;
}) {
  const { lang, t } = useTranslation();
  const id = useId();
  return (
    <section aria-labelledby={id} className={cn("min-w-0 rounded-card border border-slate-200 bg-white p-4 sm:p-5", className)}>
      <header className="mb-4 flex flex-wrap items-start justify-between gap-x-4 gap-y-2">
        <div className="min-w-0">
          <h2 id={id} className="text-lg font-semibold leading-7 text-slate-900">{title}</h2>
          {subtitle && <p className="text-sm leading-5 text-slate-600">{subtitle}</p>}
        </div>
        {aside && <div className="min-w-0 text-sm leading-5 text-slate-700">{aside}</div>}
      </header>
      <LockOverlay locked={locked} title={t("progress.analytics.lock.title")} body={t("progress.analytics.lock.body")}
        action={<GoldPill href={`/${lang}/pro`}>{t("progress.analytics.lock.action")}</GoldPill>}>
        {children}
      </LockOverlay>
    </section>
  );
}

/** "Пока нет данных" with the mascot and the next step, inside a card. */
export function CardEmpty({ hint, pose = "thinking", compact = false }: { hint: React.ReactNode; pose?: MascotPose; compact?: boolean }) {
  const { t } = useTranslation();
  return (
    <div className={cn("flex items-center gap-4 rounded-xl bg-slate-50 px-4 text-left", compact ? "py-3" : "py-5")}>
      <Mascot pose={pose} size={compact ? 48 : 64} />
      <div className="min-w-0">
        <p className="text-base font-semibold leading-6 text-slate-900">{t("progress.analytics.empty.title")}</p>
        <p className="text-sm leading-5 text-slate-600">{hint}</p>
      </div>
    </div>
  );
}

/** STUDENT_UI_FIX_PLAN 4.3: "Пока мало данных" (mascot, one line, the action) instead of rows rated on too few answers. */
export function NotEnoughData({ body, href, compact = false }: { body: React.ReactNode; href: string; compact?: boolean }) {
  const { t } = useTranslation();
  return (
    <div className={cn("flex flex-col items-start gap-3 rounded-xl bg-slate-50 px-4 sm:flex-row sm:items-center sm:gap-4", compact ? "py-3" : "py-5")}>
      <Mascot pose="thinking" size={compact ? 48 : 64} />
      <div className="min-w-0 flex-1">
        <p className="text-base font-semibold leading-6 text-slate-900">{t("progress.analytics.notEnough.title")}</p>
        <p className="text-sm leading-5 text-slate-600">{body}</p>
      </div>
      <LinkButton href={href} variant="secondary" className="shrink-0">{t("progress.analytics.notEnough.action")}</LinkButton>
    </div>
  );
}

export interface LegendItem {
  key: string;
  label: React.ReactNode;
  /** CSS colour of the swatch, or a style (the hatched "wrong" swatch). */
  color?: string;
  style?: React.CSSProperties;
  /** A dashed line instead of a square (the average line). */
  line?: boolean;
}

/** Legend in words; the swatches are decoration (the words say which series is which). */
export function Legend({ items, label, className }: { items: LegendItem[]; label: string; className?: string }) {
  return (
    <ul aria-label={label} className={cn("flex flex-wrap items-center gap-x-4 gap-y-1 text-sm leading-5 text-slate-700", className)}>
      {items.map((i) => (
        <li key={i.key} className="inline-flex items-center gap-1.5">
          {i.line
            ? <span aria-hidden="true" className="inline-block w-4 border-t-2 border-dashed border-slate-700" />
            : <span aria-hidden="true" className="inline-block h-3 w-3 shrink-0 rounded-[3px]" style={{ background: i.color, ...i.style }} />}
          {i.label}
        </li>
      ))}
    </ul>
  );
}

/** The accuracy bands as a legend: "85 % и выше — хорошо" etc. */
export function BandLegend({ className }: { className?: string }) {
  const { t } = useTranslation();
  return (
    <Legend className={className} label={t("progress.analytics.legend.label")} items={[
      { key: "high", color: "rgb(16 185 129)", label: t("progress.analytics.legend.high") },
      { key: "mid", color: "#f59e0b", label: t("progress.analytics.legend.mid") },
      { key: "low", color: "#f43f5e", label: t("progress.analytics.legend.low") },
    ]} />
  );
}

/** A horizontally scrolling box for a wide chart: only the chart scrolls, never the page. */
export function ChartScroll({ minWidth, children }: { minWidth: number; children: React.ReactNode }) {
  return (
    <div className="-mx-1 overflow-x-auto px-1 pb-1">
      <div style={{ minWidth }}>{children}</div>
    </div>
  );
}
