"use client";

import React, { useEffect, useId, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowLeft } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { createScheme, getScheme } from "@/lib/lms/grading";
import { SCHEME_TYPES, type SchemeParams, type SchemeType } from "@/lib/lms/gradingTypes";
import { cleanLocalized, pickLocalized } from "@/lib/lms/localized";
import { LMS_LANGS, type Lang, type LocalizedText } from "@/lib/lms/types";
import { useLmsMe } from "@/lib/lms/useLmsMe";
import { LocalizedTextInput } from "@/components/lms/LocalizedTextInput";
import { btnPrimary, cardCls } from "@/components/lms/content/ui";
import { SchemeError } from "./SchemeError";
import { SchemeWorkbench } from "./SchemeWorkbench";
import { cleanParams, defaultParams, normalizeParams, validateParams } from "./params";

type ParamsByType = Partial<Record<SchemeType, SchemeParams>>;

/**
 * Create a scheme (version 1). With `fromId` it starts as a copy of that scheme's version
 * (`fromVersionId`, default current): "Duplicate to my library".
 */
export function NewSchemeForm({ fromId, fromVersionId }: { fromId: string | null; fromVersionId: string | null }) {
  const { lang, t } = useTranslation();
  const router = useRouter();
  const { me, loading: meLoading } = useLmsMe();
  const id = useId();
  const [title, setTitle] = useState<LocalizedText>({});
  const [type, setType] = useState<SchemeType>("percent");
  const [byType, setByType] = useState<ParamsByType>({});
  const [loadingFrom, setLoadingFrom] = useState(!!fromId);
  const [fromError, setFromError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [titleMissing, setTitleMissing] = useState(false);

  useEffect(() => {
    if (!fromId) return;
    let alive = true;
    (async () => {
      try {
        const src = await getScheme(fromId);
        const v = src.versions.find((x) => x.id === fromVersionId)
          ?? src.versions.find((x) => x.id === src.current_version?.id)
          ?? [...src.versions].sort((a, b) => b.version_no - a.version_no)[0];
        if (!alive) return;
        const name = pickLocalized(src.title, lang as Lang);
        setTitle({ [lang]: t("schemes.editor.copyOf", { title: name }) });
        if (v) {
          setType(v.type);
          setByType({ [v.type]: normalizeParams(v.params) });
        }
      } catch (e) {
        if (alive) setFromError(e);
      } finally {
        if (alive) setLoadingFrom(false);
      }
    })();
    return () => { alive = false; };
    // load once per source; `t`/`lang` only shape the initial title
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fromId, fromVersionId]);

  const params = byType[type] ?? defaultParams(type);
  const setParams = (p: SchemeParams) => setByType((cur) => ({ ...cur, [type]: p }));
  const cleaned = useMemo(() => cleanParams(type, params), [type, params]);
  const issues = useMemo(() => validateParams(type, cleaned), [type, cleaned]);

  if (meLoading || loadingFrom) return <p role="status" className="text-sm text-slate-500">{t("lms.common.loading")}</p>;
  if (me && !me.can_create_courses) {
    return (
      <div className="mx-auto max-w-xl rounded-2xl border border-slate-200 bg-white p-6">
        <p className="text-sm text-slate-700">{t("schemes.editor.teacherOnly")}</p>
        <Link href={`/${lang}/grading-schemes`} className="mt-3 inline-block text-sm font-semibold text-brand-700 underline">{t("schemes.editor.back")}</Link>
      </div>
    );
  }

  const submit = async (ev: React.FormEvent) => {
    ev.preventDefault();
    const cleanTitle = cleanLocalized(title, LMS_LANGS);
    if (!Object.keys(cleanTitle).length) { setTitleMissing(true); return; }
    setTitleMissing(false);
    if (issues.length) return;
    setBusy(true);
    setError(null);
    try {
      const s = await createScheme({ title: cleanTitle, type, params: cleaned });
      router.push(`/${lang}/grading-schemes/${s.id}`);
    } catch (e) {
      setError(e);
      setBusy(false);
    }
  };

  return (
    <form onSubmit={submit} noValidate className="space-y-5">
      <Link href={`/${lang}/grading-schemes`} className="inline-flex items-center gap-1 text-sm text-slate-600 hover:text-slate-900">
        <ArrowLeft className="h-4 w-4" aria-hidden="true" />{t("schemes.editor.back")}
      </Link>
      <h1 className="text-2xl font-bold text-slate-900">{t("schemes.editor.newTitle")}</h1>
      {fromError ? <SchemeError error={fromError} /> : null}

      <div className={`${cardCls} space-y-4`}>
        <LocalizedTextInput label={t("schemes.editor.title")} languages={LMS_LANGS} defaultLanguage={lang as Lang}
          value={title} onChange={setTitle} maxLength={200} required disabled={busy} />
        {titleMissing && <p role="alert" className="text-sm text-red-700">{t("lms.errors.title_required")}</p>}
        <fieldset disabled={busy}>
          <legend className="mb-2 text-sm font-medium text-slate-700">{t("schemes.editor.type")}</legend>
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {SCHEME_TYPES.map((ty) => (
              <label key={ty} htmlFor={`${id}-${ty}`}
                className={`flex cursor-pointer gap-2 rounded-xl border p-3 text-sm ${ty === type ? "border-brand-500 bg-brand-50" : "border-slate-200 bg-white hover:bg-slate-50"}`}>
                <input id={`${id}-${ty}`} type="radio" name={`${id}-type`} value={ty} checked={ty === type} onChange={() => setType(ty)} className="mt-0.5" />
                <span>
                  <span className="block font-semibold text-slate-900">{t(`schemes.types.${ty}`)}</span>
                  <span className="block text-xs text-slate-600">{t(`schemes.typeSummaries.${ty}`)}</span>
                </span>
              </label>
            ))}
          </div>
        </fieldset>
      </div>

      <SchemeWorkbench type={type} params={params} onChange={setParams} issues={issues} readOnly={busy} />

      {error ? <SchemeError error={error} /> : null}
      <div className="flex flex-wrap items-center gap-3">
        <button type="submit" className={btnPrimary} disabled={busy || issues.length > 0}>
          {busy ? t("schemes.editor.creating") : t("schemes.editor.create")}
        </button>
        <p className="text-xs text-slate-500">{t("schemes.editor.createHint")}</p>
      </div>
    </form>
  );
}
