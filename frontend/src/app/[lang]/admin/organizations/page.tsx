"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Plus } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import {
  SLUG_RE, createOrganization, listOrganizations, slugify, type OrganizationOut, type OrgStatus,
} from "@/lib/lms/organizations";
import { fmtApiDate } from "@/lib/format";
import { Modal } from "@/components/lms/assessments/Modal";
import { Pager } from "@/components/lms/Pager";
import { EmptyBox, Loading, OrgBadge, OrgError, btn, inputCls, labelCls } from "@/components/lms/org/OrgUi";

const STATUSES: (OrgStatus | "")[] = ["", "active", "suspended"];

export default function AdminOrganizationsPage() {
  const { lang, t } = useTranslation();
  const router = useRouter();
  const [input, setInput] = useState("");
  const [q, setQ] = useState("");
  const [status, setStatus] = useState<OrgStatus | "">("");
  const [items, setItems] = useState<OrganizationOut[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    const h = setTimeout(() => setQ(input.trim()), 350);
    return () => clearTimeout(h);
  }, [input]);

  const load = useCallback(async (next?: string | null) => {
    setLoading(true);
    setError(null);
    try {
      const page = await listOrganizations({ q, status, cursor: next });
      setItems((prev) => (next ? [...prev, ...page.items] : page.items));
      setCursor(page.next_cursor);
    } catch (e) {
      setError(e);
    } finally {
      setLoading(false);
    }
  }, [q, status]);
  useEffect(() => { void load(); }, [load]);

  const n = (v: number | undefined) => (typeof v === "number" ? v : "—");
  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-bold text-slate-900">{t("organizations.admin.title")}</h1>
        <button type="button" className={btn.primary} onClick={() => setCreating(true)}>
          <Plus className="h-4 w-4" aria-hidden="true" />{t("organizations.admin.create")}
        </button>
      </div>
      <div className="mb-4 flex flex-wrap items-end gap-3">
        <div className="w-full sm:w-64">
          <label htmlFor="o-q" className={labelCls}>{t("lms.common.search")}</label>
          <input id="o-q" value={input} onChange={(e) => setInput(e.target.value)} placeholder={t("organizations.admin.searchPlaceholder")} className={inputCls} />
        </div>
        <div className="w-full sm:w-48">
          <label htmlFor="o-st" className={labelCls}>{t("organizations.admin.status")}</label>
          <select id="o-st" value={status} onChange={(e) => setStatus(e.target.value as OrgStatus | "")} className={inputCls}>
            {STATUSES.map((s) => <option key={s} value={s}>{s ? t(`organizations.status.${s}`) : t("organizations.admin.anyStatus")}</option>)}
          </select>
        </div>
      </div>
      {error ? <OrgError error={error} onRetry={() => load()} className="mb-4" /> : null}
      {loading && items.length === 0 && !error && <Loading />}
      {!loading && !error && items.length === 0 && (
        <EmptyBox text={q || status ? t("organizations.admin.emptySearch") : t("organizations.admin.empty")}>
          {!q && !status && <button type="button" className={btn.secondary} onClick={() => setCreating(true)}>{t("organizations.admin.create")}</button>}
        </EmptyBox>
      )}
      {items.length > 0 && (
        <>
          <p className="mb-2 text-xs text-slate-500">{t("organizations.admin.shown", { n: items.length })}</p>
          <ul className="divide-y divide-slate-100 rounded-2xl border border-slate-200 bg-white text-sm">
            {items.map((o) => (
              <li key={o.id} className="flex flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3">
                <div className="min-w-0 flex-1 basis-56">
                  <Link href={`/${lang}/admin/organizations/${o.id}`} className="font-medium text-brand-700 hover:underline">{o.name}</Link>
                  <p className="truncate text-xs text-slate-500">{o.slug} · {t("organizations.admin.createdOn", { date: fmtApiDate(o.created_at, lang) })}</p>
                </div>
                <OrgBadge tone={o.status} labelKey={`organizations.status.${o.status}`} />
                <dl className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-600">
                  <div className="flex gap-1"><dt>{t("organizations.counts.orgAdmins")}:</dt><dd className="font-semibold text-slate-900">{n(o.counts?.org_admins)}</dd></div>
                  <div className="flex gap-1"><dt>{t("organizations.counts.teachers")}:</dt><dd className="font-semibold text-slate-900">{n(o.counts?.teachers)}</dd></div>
                  <div className="flex gap-1"><dt>{t("organizations.counts.courses")}:</dt><dd className="font-semibold text-slate-900">{n(o.counts?.courses)}</dd></div>
                </dl>
              </li>
            ))}
          </ul>
        </>
      )}
      <Pager nextCursor={cursor} loading={loading} onMore={() => load(cursor)} />
      <CreateOrganizationDialog open={creating} onClose={() => setCreating(false)}
        onCreated={(o) => { setCreating(false); router.push(`/${lang}/admin/organizations/${o.id}`); }} />
    </div>
  );
}

function CreateOrganizationDialog({ open, onClose, onCreated }: { open: boolean; onClose: () => void; onCreated: (o: OrganizationOut) => void }) {
  const { t } = useTranslation();
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [slugTouched, setSlugTouched] = useState(false);
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [checked, setChecked] = useState(false);

  useEffect(() => { if (open) { setName(""); setSlug(""); setSlugTouched(false); setEmail(""); setError(null); setChecked(false); } }, [open]);

  const effectiveSlug = slugTouched ? slug : slugify(name);
  const nameOk = name.trim().length > 0;
  const slugOk = SLUG_RE.test(effectiveSlug);
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setChecked(true);
    if (!nameOk || !slugOk) return;
    setBusy(true);
    setError(null);
    try {
      onCreated(await createOrganization({ name: name.trim(), slug: effectiveSlug, contact_email: email.trim() || undefined }));
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal open={open} title={t("organizations.admin.createTitle")} onClose={onClose} busy={busy}>
      <form onSubmit={submit} noValidate className="space-y-4">
        <div>
          <label htmlFor="no-name" className={labelCls}>{t("organizations.fields.name")}</label>
          <input id="no-name" value={name} maxLength={200} disabled={busy} aria-invalid={checked && !nameOk}
            onChange={(e) => setName(e.target.value)} className={inputCls} />
          {checked && !nameOk && <p role="alert" className="mt-1 text-xs text-red-700">{t("organizations.fields.nameMissing")}</p>}
        </div>
        <div>
          <label htmlFor="no-slug" className={labelCls}>{t("organizations.fields.slug")}</label>
          <input id="no-slug" value={effectiveSlug} maxLength={64} disabled={busy} aria-invalid={checked && !slugOk}
            onChange={(e) => { setSlugTouched(true); setSlug(e.target.value.toLowerCase()); }} className={`${inputCls} font-mono`} />
          <p className={`mt-1 text-xs ${checked && !slugOk ? "text-red-700" : "text-slate-500"}`}>{t("organizations.fields.slugHint")}</p>
        </div>
        <div>
          <label htmlFor="no-email" className={labelCls}>{t("organizations.fields.contactEmail")}</label>
          <input id="no-email" type="email" value={email} disabled={busy} onChange={(e) => setEmail(e.target.value)} className={inputCls} />
        </div>
        <p className="text-xs text-slate-500">{t("organizations.admin.createHint")}</p>
        <OrgError error={error} />
        <div className="flex flex-wrap justify-end gap-2">
          <button type="button" className={btn.secondary} disabled={busy} onClick={onClose}>{t("lms.common.cancel")}</button>
          <button type="submit" className={btn.primary} disabled={busy}>{busy ? t("lms.common.loading") : t("organizations.admin.create")}</button>
        </div>
      </form>
    </Modal>
  );
}
