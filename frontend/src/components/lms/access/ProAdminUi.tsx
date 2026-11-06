"use client";

// F6b Pro, platform admin (docs/phases/SUBSCRIPTION_DESIGN.md 7): the one "Выдать Pro" dialog (person search unless
// the person is given, plan / days / end date, reason, a preview of the new end computed here; the server re-checks)
// and the "Отменить Pro" dialog (reason, danger). Used by the Pro tab and the person page.
import React, { useEffect, useMemo, useState } from "react";
import { useTranslation } from "@/lib/i18n/context";
import {
  bishkekDayEnd, cancelPro, fmtPassEnd, fmtPlanDay, getProSettings, getUserAccess, grantAccess,
  type PassSource, type PlanId, type UserAccessOut,
} from "@/lib/lms/access";
import { ConfirmDialog, Input, ReasonDialog, Textarea, UserPicker, cn, toast, type PickedUser } from "@/components/ui";
import { platformUserSearch } from "@/components/lms/UserPicker";
import { useErrorText } from "@/components/lms/home/useErrorText";

type T = (k: string, v?: Record<string, string | number>) => string;
type Mode = PlanId | "days" | "date";
const DAY = 86_400_000;
const PLAN_DAYS: Record<"month_1" | "month_3", number> = { month_1: 30, month_3: 90 };

export const planLabel = (plan: PlanId | null, t: T) => (plan ? t(`access.plan.${plan}`) : "—");
export const sourceLabel = (source: PassSource | null, t: T) => (source ? t(`access.source.${source}`) : "—");

/** The season end the admin set, when the season plan can still be granted (its Bishkek end of day is ahead), and
 *  whether the settings have been read (so a season preset is not dropped before they arrive). */
export function useSeasonSetting(enabled: boolean): { seasonEnd: string | null; loaded: boolean } {
  const [seasonEnd, setSeasonEnd] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  useEffect(() => {
    if (!enabled) return;
    let alive = true;
    setLoaded(false);
    getProSettings().then((s) => { if (alive) setSeasonEnd(s.season_end); }).catch(() => { if (alive) setSeasonEnd(null); })
      .finally(() => { if (alive) setLoaded(true); });
    return () => { alive = false; };
  }, [enabled]);
  return { seasonEnd: seasonEnd && bishkekDayEnd(seasonEnd).getTime() > Date.now() ? seasonEnd : null, loaded };
}

export function useSeasonEnd(enabled: boolean): string | null {
  return useSeasonSetting(enabled).seasonEnd;
}

export interface GrantProDialogProps {
  open: boolean;
  /** The person (person page, a row's "Продлить"); null: the dialog searches for one. */
  person: PickedUser | null;
  /** The person's current chain end when known (an active Pro is extended from it). */
  currentEnd?: string | null;
  /** Preselected plan ("Продлить" = the row's last plan). */
  preset?: PlanId | null;
  renew?: boolean;
  onClose: () => void;
  onGranted: (out: UserAccessOut, userId: string) => void;
}

export function GrantProDialog({ open, person, currentEnd, preset, renew = false, onClose, onGranted }: GrantProDialogProps) {
  const { lang, t } = useTranslation();
  const errorText = useErrorText();
  const { seasonEnd, loaded: seasonLoaded } = useSeasonSetting(open);
  const search = useMemo(() => platformUserSearch(), []);
  const [picked, setPicked] = useState<PickedUser | null>(null);
  const [pickedEnd, setPickedEnd] = useState<string | null>(null);
  const [mode, setMode] = useState<Mode>("month_1");
  const [days, setDays] = useState("30");
  const [endsOn, setEndsOn] = useState("");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setPicked(null); setPickedEnd(null); setMode(preset ?? "month_1"); setDays("30"); setEndsOn(""); setReason(""); setError(null);
  }, [open, preset]);
  // a searched person: read their chain end for the preview (the server extends from it)
  useEffect(() => {
    if (!picked) { setPickedEnd(null); return; }
    let alive = true;
    getUserAccess(picked.id).then((a) => { if (alive) setPickedEnd(a.active ? a.ends_at : null); }).catch(() => { if (alive) setPickedEnd(null); });
    return () => { alive = false; };
  }, [picked]);
  // a season plan preset while no season end is set (known only once the settings are read): fall back to a month
  useEffect(() => {
    if (open && seasonLoaded && mode === "season" && !seasonEnd) setMode("month_1");
  }, [open, seasonLoaded, mode, seasonEnd]);

  const who = person ?? picked;
  const endIso = person ? (currentEnd ?? null) : pickedEnd;
  const base = Math.max(Date.now(), endIso ? new Date(endIso).getTime() : 0);
  const d = Number(days);
  const daysOk = Number.isInteger(d) && d >= 1 && d <= 400;
  let newEnd: number | null = null;
  if (mode === "month_1" || mode === "month_3") newEnd = base + PLAN_DAYS[mode] * DAY;
  else if (mode === "days") newEnd = daysOk ? base + d * DAY : null;
  else if (mode === "season") newEnd = seasonEnd ? bishkekDayEnd(seasonEnd).getTime() : null;
  else newEnd = endsOn ? bishkekDayEnd(endsOn).getTime() : null;
  const noBenefit = newEnd !== null && newEnd <= base;

  // the season choice stays while the settings load, so a season row's "Продлить" keeps its plan
  const showSeason = !!seasonEnd || (!seasonLoaded && mode === "season");
  const modes: Mode[] = ["month_1", "month_3", ...(showSeason ? (["season"] as Mode[]) : []), "days", "date"];
  const modeLabel = (m: Mode) => m === "days" ? t("access.admin.batches.lengthDays")
    : m === "date" ? t("access.admin.batches.lengthDate")
      : m === "season" ? (seasonEnd ? t("access.admin.batches.planOption", { plan: t("access.plan.season"), length: fmtPlanDay(seasonEnd, lang) }) : t("access.plan.season"))
        : t("access.admin.batches.planOption", { plan: t(`access.plan.${m}`), length: t("access.admin.batches.lengthDaysValue", { count: PLAN_DAYS[m] }) });

  const submit = async () => {
    if (!who) { setError(t("access.admin.pro.pickPerson")); return; }
    if (mode === "days" && !daysOk) { setError(t(d >= 1 ? "lms.errors.grant_too_long" : "lms.errors.grant_length_required")); return; }
    if (mode === "season" && !seasonEnd) { setError(t(seasonLoaded ? "lms.errors.season_not_set" : "lms.common.loading")); return; }
    if (mode === "date" && !endsOn) { setError(t("lms.errors.grant_length_required")); return; }
    if (!reason.trim()) { setError(t("ui.reason.missing")); return; }
    setBusy(true);
    setError(null);
    try {
      const len = mode === "days" ? { duration_days: d } : mode === "date" ? { ends_on: endsOn } : { plan: mode };
      const out = await grantAccess(who.id, { ...len, reason: reason.trim() });
      toast.success(t("access.admin.pro.granted", { date: fmtPassEnd(out.ends_at, lang, false) }));
      onGranted(out, who.id);
    } catch (e) { setError(errorText(e)); } finally { setBusy(false); }
  };

  const radio = "inline-flex min-h-11 cursor-pointer items-center gap-2 rounded-xl border px-3 text-sm font-medium sm:min-h-9";
  return (
    <ConfirmDialog open={open} title={t(renew ? "access.admin.pro.renewTitle" : "access.admin.pro.grantTitle")}
      object={person ? (person.display_name || person.email) : undefined}
      effect={t(who && !endIso ? "access.admin.pro.grantBodyNew" : "access.admin.pro.grantBody")}
      confirmLabel={t(renew ? "access.admin.pro.renew" : "access.admin.pro.grant")} busy={busy} error={error ?? undefined}
      onConfirm={() => void submit()} onCancel={onClose}>
      <div className="space-y-4">
        {!person && (
          <UserPicker id="grant-person" label={t("access.admin.pro.person")} hint={t("access.admin.pro.personHint")}
            value={picked} onChange={(u) => { setPicked(u); setError(null); }} search={search} />
        )}
        <fieldset>
          <legend className="mb-2 text-sm font-medium text-slate-800">{t("access.admin.pro.length")}</legend>
          <div className="flex flex-wrap gap-2">
            {modes.map((m) => (
              <label key={m} className={cn(radio, mode === m ? "border-brand-600 bg-brand-50 text-brand-800" : "border-slate-300 bg-white text-slate-700")}>
                <input type="radio" name="grant-mode" value={m} checked={mode === m} onChange={() => setMode(m)} className="h-4 w-4" />
                {modeLabel(m)}
              </label>
            ))}
          </div>
        </fieldset>
        {mode === "days" && (
          <Input id="grant-days" label={t("access.admin.batches.days")} inputMode="numeric" value={days} containerClassName="max-w-xs"
            onChange={(e) => setDays(e.target.value.replace(/[^0-9]/g, "").slice(0, 3))} />
        )}
        {mode === "date" && (
          <Input id="grant-ends" type="date" label={t("access.admin.batches.endsOn")} hint={t("access.admin.batches.endsOnHint")}
            value={endsOn} onChange={(e) => setEndsOn(e.target.value)} containerClassName="max-w-xs" />
        )}
        {newEnd !== null && who && (
          <p aria-live="polite" className={cn("text-sm font-medium leading-5", noBenefit ? "text-warning-800" : "text-slate-800")}>
            {noBenefit ? t("access.admin.pro.previewNoBenefit")
              : t("access.admin.pro.preview", { date: fmtPassEnd(new Date(newEnd).toISOString(), lang, false) })}
          </p>
        )}
        <Textarea id="grant-reason" label={t("ui.reason.required")} rows={2} maxLength={500} value={reason}
          onChange={(e) => setReason(e.target.value)} />
      </div>
    </ConfirmDialog>
  );
}

export function CancelProDialog({ person, onClose, onCancelled, linkToPerson = true }: {
  /** Open while set. */
  person: { id: string; name: string } | null;
  /** The toast links to the person page (not on the person page itself). */
  linkToPerson?: boolean;
  onClose: () => void;
  onCancelled: (out: UserAccessOut, userId: string) => void;
}) {
  const { lang, t } = useTranslation();
  const errorText = useErrorText();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const openId = person?.id ?? null;
  useEffect(() => { if (openId) setError(null); }, [openId]);
  const run = async (reason: string) => {
    if (!person) return;
    setBusy(true);
    setError(null);
    try {
      const out = await cancelPro(person.id, reason);
      toast.success(t("access.admin.pro.cancelled"), undefined, linkToPerson
        ? { href: `/${lang}/admin/users/${person.id}`, label: t("access.admin.pro.openPerson", { name: person.name }) } : undefined);
      onCancelled(out, person.id);
    } catch (e) { setError(errorText(e)); } finally { setBusy(false); }
  };
  return (
    <ReasonDialog open={!!person} title={t("access.admin.pro.cancelTitle")} object={person?.name}
      effect={t("access.admin.pro.cancelBody")} confirmLabel={t("access.admin.pro.cancel")} tone="danger" busy={busy}
      error={error ?? undefined} onConfirm={(r) => void run(r)} onCancel={onClose} />
  );
}
