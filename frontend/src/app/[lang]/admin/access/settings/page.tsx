"use client";

// F6b Pro settings, platform admin (docs/phases/SUBSCRIPTION_DESIGN.md 7): the season end (no date: no season plan),
// a price per plan (empty: «уточняйте») and the "how to pay" text per language (ky/en fall back to ru at read time;
// all empty: the `access.howToPay` placeholder). Save sends only what changed (the API merges, audited).
import React, { useCallback, useEffect, useState } from "react";
import { useTranslation } from "@/lib/i18n/context";
import { getProSettings, putProSettings, type PlanId, type ProSettingsIn, type ProSettingsOut } from "@/lib/lms/access";
import { Button, Card, ErrorState, Input, LoadingState, PageHeader, Textarea, toast } from "@/components/ui";
import { useAdminCrumbs } from "@/components/lms/admin/AdminShell";
import { useErrorText } from "@/components/lms/home/useErrorText";

const PLANS: PlanId[] = ["month_1", "month_3", "season"];
const LANGS = ["ru", "ky", "en"] as const;
type Lang = (typeof LANGS)[number];
const MAX_PRICE = 1_000_000;

interface Form { season_end: string; prices: Record<PlanId, string>; how_to_pay: Record<Lang, string> }

const toForm = (s: ProSettingsOut): Form => ({
  season_end: s.season_end ?? "",
  prices: { month_1: s.prices.month_1?.toString() ?? "", month_3: s.prices.month_3?.toString() ?? "", season: s.prices.season?.toString() ?? "" },
  how_to_pay: { ru: s.how_to_pay.ru, ky: s.how_to_pay.ky, en: s.how_to_pay.en },
});

/** The patch: only the keys whose value differs from what was loaded. */
function diff(saved: Form, form: Form): ProSettingsIn {
  const out: ProSettingsIn = {};
  if (form.season_end !== saved.season_end) out.season_end = form.season_end || null;
  for (const p of PLANS) {
    if (form.prices[p].trim() !== saved.prices[p]) (out.prices ??= {})[p] = form.prices[p].trim() === "" ? null : Number(form.prices[p]);
  }
  for (const l of LANGS) {
    if (form.how_to_pay[l] !== saved.how_to_pay[l]) (out.how_to_pay ??= {})[l] = form.how_to_pay[l];
  }
  return out;
}

export default function AdminProSettingsPage() {
  const { lang, t } = useTranslation();
  const crumbs = useAdminCrumbs();
  const errorText = useErrorText();
  const [saved, setSaved] = useState<Form | null>(null);
  const [form, setForm] = useState<Form | null>(null);
  const [loadError, setLoadError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoadError(null);
    try { const f = toForm(await getProSettings()); setSaved(f); setForm(f); } catch (e) { setLoadError(e); }
  }, []);
  useEffect(() => { void load(); }, [load]);

  const priceBad = (v: string) => v.trim() !== "" && !(/^\d+$/.test(v.trim()) && Number(v) <= MAX_PRICE);
  const save = async (ev: React.FormEvent) => {
    ev.preventDefault();
    if (!form || !saved) return;
    if (PLANS.some((p) => priceBad(form.prices[p]))) { setError(t("access.admin.settings.priceInvalid")); return; }
    const patch = diff(saved, form);
    if (Object.keys(patch).length === 0) { toast.info(t("access.admin.settings.unchanged")); return; }
    setBusy(true);
    setError(null);
    try {
      const f = toForm(await putProSettings(patch));
      setSaved(f);
      setForm(f);
      toast.success(t("access.admin.settings.saved"));
    } catch (e) { setError(errorText(e)); } finally { setBusy(false); }
  };

  const langName: Record<Lang, string> = { ru: t("common.russian"), ky: t("common.kyrgyz"), en: t("common.english") };
  const header = (
    <>
      <PageHeader title={t("access.admin.pages.settings")} description={t("access.admin.subtitles.settings")}
        breadcrumbs={crumbs({ label: t("access.admin.pages.settings") })} />
    </>
  );
  if (loadError && !form) return <div>{header}<ErrorState message={errorText(loadError)} onRetry={() => void load()} /></div>;
  if (!form) return <div>{header}<LoadingState label={t("lms.common.loading")} /></div>;
  const set = (f: Partial<Form>) => { setForm({ ...form, ...f }); if (error) setError(null); };

  return (
    <div>
      {header}
      <form onSubmit={save} noValidate className="max-w-3xl space-y-6">
        <Card title={t("access.admin.settings.seasonTitle")}>
          <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
            <Input id="pro-season-end" type="date" label={t("access.admin.settings.seasonEnd")} value={form.season_end}
              onChange={(e) => set({ season_end: e.target.value })} containerClassName="max-w-xs" />
            {form.season_end && (
              <Button type="button" variant="link" onClick={() => set({ season_end: "" })} className="self-start sm:mb-1 sm:self-auto">{t("access.admin.settings.seasonClear")}</Button>
            )}
          </div>
          <p className="mt-2 text-sm leading-5 text-slate-600">{t("access.admin.settings.seasonHint")}</p>
          {!form.season_end && <p className="mt-1 text-sm font-medium leading-5 text-slate-700">{t("access.admin.settings.seasonNone")}</p>}
        </Card>
        <Card title={t("access.admin.settings.pricesTitle")} description={t("access.admin.settings.pricesHint")}>
          <div className="grid gap-4 sm:grid-cols-3 sm:items-end">
            {PLANS.map((p) => (
              <Input key={p} id={`pro-price-${p}`} label={t("access.admin.settings.priceLabel", { plan: t(`access.plan.${p}`) })}
                inputMode="numeric" value={form.prices[p]} optional
                error={priceBad(form.prices[p]) ? t("access.admin.settings.priceInvalid") : undefined}
                onChange={(e) => set({ prices: { ...form.prices, [p]: e.target.value.replace(/[^0-9]/g, "").slice(0, 7) } })} />
            ))}
          </div>
        </Card>
        <Card title={t("access.admin.settings.payTitle")} description={t("access.admin.settings.payHint")}>
          <div className="space-y-4">
            {LANGS.map((l) => (
              <Textarea key={l} id={`pro-pay-${l}`} label={langName[l]} rows={4} maxLength={2000} lang={l}
                value={form.how_to_pay[l]} optional={l !== "ru"}
                onChange={(e) => set({ how_to_pay: { ...form.how_to_pay, [l]: e.target.value } })} />
            ))}
          </div>
        </Card>
        {error && <p role="alert" className="text-sm font-medium text-danger-700">{error}</p>}
        <Button type="submit" loading={busy} className="w-full sm:w-auto">{t("access.admin.settings.save")}</Button>
      </form>
    </div>
  );
}
