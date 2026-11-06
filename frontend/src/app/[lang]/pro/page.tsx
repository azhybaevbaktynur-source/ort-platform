"use client";

// F6b Pro (docs/phases/SUBSCRIPTION_DESIGN.md 6): the student's plan (Pro until a date, or Free), what Free and Pro
// include (from `/me/access/offer`), the plans (the season plan and the prices only when the admin set them), how to pay
// (the owner's text, or the `access.howToPay` placeholder) and the gift-code field under a disclosure. No payment yet:
// choosing a plan only shows the "how to pay" text for it. The exam countdown is not here.
import React, { useCallback, useEffect, useId, useState } from "react";
import { Check, ChevronRight, KeyRound, Star } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import {
  fmtPassEnd, fmtPlanDay, fmtPrice, getMyOffer, redeemCode, type OfferOut, type OfferPlanOut, type PlanId,
} from "@/lib/lms/access";
import { Button, Card, ErrorState, Input, LinkButton, Skeleton, cn, focusRing, toast } from "@/components/ui";
import { useErrorText } from "@/components/lms/home/useErrorText";
import { StudentPageHeader } from "@/components/lms/student/StudentPageHeader";

type T = (k: string, v?: Record<string, string | number>) => string;

function Ticks({ rows, tone }: { rows: string[]; tone: "free" | "pro" }) {
  return (
    <ul className="space-y-2.5">
      {rows.map((r) => (
        <li key={r} className="flex items-start gap-2 text-sm leading-5 text-slate-800">
          <Check aria-hidden="true" className={cn("mt-0.5 h-4 w-4 shrink-0", tone === "pro" ? "text-gold-700" : "text-success-700")} />
          <span className="min-w-0">{r}</span>
        </li>
      ))}
    </ul>
  );
}

/** Free and Pro side by side (stacked under 640 px); gold only on the Pro column's border (SF-3). */
function Compare({ offer, t }: { offer: OfferOut; t: T }) {
  const free = [t("access.pro.compare.freeTests"), ...(offer.practice_free ? [t("access.pro.compare.practiceFree")] : []),
    t("access.pro.compare.analytics"), t("access.pro.compare.results")];
  const pro = [t("access.pro.compare.everythingFree"), ...offer.includes.map((k) => t(`access.pro.compare.${k}`)),
    t("access.pro.compare.keep")];
  return (
    <Card title={t("access.pro.compare.title")}>
      <div className="grid gap-3 sm:grid-cols-2">
        <section aria-labelledby="pro-col-free" className="rounded-xl border border-slate-200 p-4">
          <h3 id="pro-col-free" className="mb-3 text-base font-semibold leading-6 text-slate-900">{t("access.pro.compare.free")}</h3>
          <Ticks rows={free} tone="free" />
        </section>
        <section aria-labelledby="pro-col-pro" className="rounded-xl border-2 border-gold-300 p-4">
          <h3 id="pro-col-pro" className="mb-3 flex items-center gap-1.5 text-base font-semibold leading-6 text-slate-900">
            <Star aria-hidden="true" className="h-4 w-4 fill-current text-gold-600" />{t("access.pro.compare.pro")}
          </h3>
          <Ticks rows={pro} tone="pro" />
        </section>
      </div>
    </Card>
  );
}

function planSub(p: OfferPlanOut, t: T, lang: string): string {
  if (p.days) return t("access.admin.batches.lengthDaysValue", { count: p.days });
  return p.season_end ? t("access.admin.batches.lengthUntil", { date: fmtPlanDay(p.season_end, lang) }) : "";
}

/** The plans as radio cards, then how to pay for the chosen one. */
function Plans({ offer, t, lang }: { offer: OfferOut; t: T; lang: string }) {
  const [chosen, setChosen] = useState<PlanId | null>(offer.plans[0]?.id ?? null);
  useEffect(() => {
    if (!offer.plans.some((p) => p.id === chosen)) setChosen(offer.plans[0]?.id ?? null);
  }, [offer.plans, chosen]);
  const name = useId();
  const plan = offer.plans.find((p) => p.id === chosen) ?? null;
  const text = (offer.how_to_pay[lang as keyof OfferOut["how_to_pay"]] || offer.how_to_pay.ru || "").trim() || t("access.howToPay");
  return (
    <Card title={t("access.pro.plans.title")} aria-label={t("access.pro.plans.title")}>
      <fieldset>
        <legend className="sr-only">{t("access.pro.plans.title")}</legend>
        <div className="space-y-2">
          {offer.plans.map((p) => {
            const on = p.id === chosen;
            return (
              <label key={p.id}
                className={cn("flex min-h-14 cursor-pointer items-center gap-3 rounded-xl border px-4 py-3 transition-colors focus-within:ring-2 focus-within:ring-brand-600 focus-within:ring-offset-2",
                  on ? "border-brand-600 bg-brand-50" : "border-slate-200 bg-white hover:border-slate-300")}>
                <input type="radio" name={name} value={p.id} checked={on} onChange={() => setChosen(p.id)} className="h-4 w-4 shrink-0 accent-brand-600" />
                <span className="min-w-0 flex-1">
                  <span className="block text-base font-semibold leading-6 text-slate-900">{t(`access.plan.${p.id}`)}</span>
                  <span className="block text-sm leading-5 text-slate-600">{planSub(p, t, lang)}</span>
                </span>
                {p.price_kgs !== null && (
                  <span className="shrink-0 text-base font-semibold tabular-nums text-slate-900">{t("access.pro.plans.price", { price: fmtPrice(p.price_kgs, lang) })}</span>
                )}
              </label>
            );
          })}
        </div>
      </fieldset>
      {plan && (
        <p className="mt-3 text-sm leading-5 text-slate-700" aria-live="polite">
          {t("access.pro.plans.newEnd", { date: fmtPassEnd(plan.new_ends_at, lang, false) })}
        </p>
      )}
      <div className="mt-5 border-t border-slate-100 pt-5">
        <h3 className="text-base font-semibold leading-6 text-slate-900">{t("access.pro.pay.title")}</h3>
        {plan && (
          <p className="mt-1 text-sm font-medium leading-5 text-slate-800">
            {plan.price_kgs !== null
              ? t("access.pro.pay.chosenPrice", { plan: t(`access.plan.${plan.id}`), price: fmtPrice(plan.price_kgs, lang) })
              : t("access.pro.pay.chosen", { plan: t(`access.plan.${plan.id}`) })}
          </p>
        )}
        <p className="mt-2 whitespace-pre-line break-words text-base leading-6 text-slate-700">{text}</p>
      </div>
    </Card>
  );
}

function Status({ offer, t, lang }: { offer: OfferOut | null; t: T; lang: string }) {
  if (!offer) return <Skeleton className="h-16 w-full rounded-2xl" />;
  const s = offer.status;
  return (
    <section aria-label={t("access.pro.status.title")}
      className={cn("flex flex-wrap items-center gap-x-4 gap-y-1 rounded-2xl border px-4 py-3 sm:px-5",
        s.active ? "border-slate-200 bg-white" : "border-slate-200 bg-slate-50")}>
      {s.active ? (
        <>
          <p className="flex items-center gap-2 text-base font-semibold leading-6 text-slate-900">
            <Star aria-hidden="true" className="h-4 w-4 fill-current text-gold-600" />
            {t("access.pro.status.active", { date: fmtPassEnd(s.ends_at, lang, false) })}
          </p>
          <p className="text-sm leading-5 text-slate-600">{t("access.pro.status.daysLeft", { count: s.days_left })}</p>
        </>
      ) : (
        <>
          <p className="text-base font-semibold leading-6 text-slate-900">{t("access.pro.status.free")}</p>
          <p className="text-sm leading-5 text-slate-600">{t("access.pro.status.freeHint")}</p>
        </>
      )}
    </section>
  );
}

function Voucher({ onRedeemed, t, lang }: { onRedeemed: () => void; t: T; lang: string }) {
  const errorText = useErrorText();
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const submit = async (ev: React.FormEvent) => {
    ev.preventDefault();
    if (!code.trim()) { setError(t("lms.errors.code_invalid")); return; }
    setBusy(true);
    setError(null);
    try {
      const out = await redeemCode(code);
      setCode("");
      const msg = t("access.pro.voucher.success", { date: fmtPassEnd(out.ends_at ?? out.pass_ends_at, lang, false) });
      setDone(msg);
      toast.success(msg);
      onRedeemed();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  };
  return (
    <details className="group rounded-2xl border border-slate-200 bg-white shadow-sm">
      <summary className={cn("flex min-h-12 cursor-pointer list-none items-center gap-2 rounded-2xl px-4 py-3 text-base font-medium leading-6 text-slate-900 sm:px-6 [&::-webkit-details-marker]:hidden", focusRing)}>
        <ChevronRight aria-hidden="true" className="h-4 w-4 shrink-0 text-slate-500 transition-transform group-open:rotate-90" />
        {t("access.pro.voucher.toggle")}
      </summary>
      <form onSubmit={submit} noValidate className="flex flex-col gap-3 px-4 pb-4 sm:flex-row sm:items-start sm:px-6 sm:pb-6">
        <Input id="pro-code" label={t("access.pro.voucher.label")} hint={t("access.unlock.codeHint")} containerClassName="min-w-0 flex-1 sm:max-w-md"
          autoComplete="off" autoCapitalize="characters" spellCheck={false} maxLength={40} value={code}
          error={error ?? undefined} className="font-mono uppercase tracking-wider"
          onChange={(e) => { setCode(e.target.value); if (error) setError(null); if (done) setDone(null); }} />
        <Button type="submit" variant="secondary" loading={busy} leftIcon={<KeyRound aria-hidden="true" className="h-4 w-4" />} className="w-full sm:mt-7 sm:w-auto">
          {t("access.unlock.redeem")}
        </Button>
      </form>
      {done && <p role="status" className="px-4 pb-4 text-sm font-medium leading-5 text-success-800 sm:px-6">{done}</p>}
    </details>
  );
}

export default function ProPage() {
  const { lang, t } = useTranslation();
  const errorText = useErrorText();
  const [offer, setOffer] = useState<OfferOut | null>(null);
  const [loadError, setLoadError] = useState<unknown>(null);

  const load = useCallback(async () => {
    setLoadError(null);
    try { setOffer(await getMyOffer()); } catch (e) { setLoadError(e); }
  }, []);
  useEffect(() => { void load(); }, [load]);

  return (
    <div className="w-full max-w-[60rem]">
      <StudentPageHeader title={t("access.pro.title")} subtitle={t("access.pro.intro")} className="mb-6" />
      {loadError && !offer ? <ErrorState message={errorText(loadError)} onRetry={() => void load()} className="mb-6" /> : (
        <div className="space-y-6">
          <Status offer={offer} t={t} lang={lang} />
          {!offer ? <Skeleton className="h-64 w-full rounded-2xl" /> : (
            <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] lg:items-start">
              <Compare offer={offer} t={t} />
              <Plans offer={offer} t={t} lang={lang} />
            </div>
          )}
          <Voucher onRedeemed={() => void load()} t={t} lang={lang} />
        </div>
      )}
      <div className="mt-6">
        <LinkButton variant="link" href={`/${lang}/courses`}>{t("access.unlock.back")}</LinkButton>
      </div>
    </div>
  );
}
