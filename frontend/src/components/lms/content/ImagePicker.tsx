"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import { ImagePlus, X } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { deleteAsset, listMyAssets, uploadAsset } from "@/lib/lms/content";
import type { AssetOut, ImageOut } from "@/lib/lms/contentTypes";
import { ContentError } from "./ContentError";
import { btnSmall, labelCls } from "./ui";

/** Image field: file input, drag-drop and paste upload to the course assets API; "my images" grid. */
export function ImagePicker({
  courseId,
  label,
  value,
  onChange,
  disabled,
  compact = false,
}: {
  courseId: string;
  label?: string;
  value: ImageOut | null;
  onChange: (img: ImageOut | null) => void;
  disabled?: boolean;
  compact?: boolean;
}) {
  const { t } = useTranslation();
  const fileRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [showMine, setShowMine] = useState(false);
  const [mine, setMine] = useState<AssetOut[]>([]);
  const [mineLoading, setMineLoading] = useState(false);

  const pick = (a: AssetOut) => onChange({ asset_id: a.id, url: a.url || "", sha256: a.sha256 });

  const upload = useCallback(async (file: File | undefined | null) => {
    if (!file || disabled) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const a = await uploadAsset(courseId, file);
      pick(a);
      if (a.deduplicated) setNotice(t("bank.image.alreadyUploaded"));
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [courseId, disabled, onChange, t]);

  const loadMine = useCallback(async () => {
    setMineLoading(true);
    try {
      setMine((await listMyAssets({ limit: 24 })).items.filter((a) => (a.visibility ?? "public") === "public"));
    } catch (e) {
      setError(e);
    } finally {
      setMineLoading(false);
    }
  }, []);
  useEffect(() => { if (showMine) void loadMine(); }, [showMine, loadMine]);

  const removeFromLibrary = async (a: AssetOut) => {
    try {
      await deleteAsset(a.id);
      setMine((m) => m.filter((x) => x.id !== a.id));
    } catch (e) {
      setError(e);
    }
  };

  return (
    <div
      onDragOver={(e) => { if (!disabled) e.preventDefault(); }}
      onDrop={(e) => { e.preventDefault(); void upload(e.dataTransfer.files?.[0]); }}
      onPaste={(e) => {
        const f = Array.from(e.clipboardData?.files || []).find((x) => x.type.startsWith("image/"));
        if (f) { e.preventDefault(); void upload(f); }
      }}
      tabIndex={-1}
    >
      {label && <span className={labelCls}>{label}</span>}
      <div className={`flex flex-wrap items-center gap-3 rounded-xl border border-dashed border-slate-300 bg-slate-50 ${compact ? "p-2" : "p-3"}`}>
        {value ? (
          <div className="relative">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={value.url} alt="" className={`${compact ? "h-16" : "h-28"} w-auto rounded-lg border border-slate-200 bg-white object-contain`} />
            <button type="button" disabled={disabled} onClick={() => { onChange(null); setNotice(null); }}
              aria-label={t("bank.image.remove")}
              className="absolute -right-2 -top-2 rounded-full border border-slate-300 bg-white p-0.5 text-slate-600 hover:text-red-600">
              <X className="h-3.5 w-3.5" aria-hidden="true" />
            </button>
          </div>
        ) : (
          <ImagePlus className="h-6 w-6 text-slate-400" aria-hidden="true" />
        )}
        <div className="flex flex-col gap-1.5">
          <div className="flex flex-wrap gap-1.5">
            <button type="button" disabled={disabled || busy} className={btnSmall} onClick={() => fileRef.current?.click()}>
              {busy ? t("bank.image.uploading") : value ? t("bank.image.replace") : t("bank.image.upload")}
            </button>
            <button type="button" disabled={disabled} className={btnSmall} onClick={() => setShowMine((s) => !s)}>
              {t("bank.image.mine")}
            </button>
          </div>
          {!compact && <p className="text-xs text-slate-500">{t("bank.image.hint")}</p>}
          {notice && <p role="status" className="text-xs text-emerald-700">{notice}</p>}
        </div>
        <input ref={fileRef} type="file" accept="image/png,image/jpeg,image/gif,image/webp" className="sr-only" tabIndex={-1}
          onChange={(e) => { void upload(e.target.files?.[0]); e.target.value = ""; }} />
      </div>
      {error ? <ContentError error={error} className="mt-2" /> : null}
      {showMine && (
        <div className="mt-2 rounded-xl border border-slate-200 bg-white p-2">
          {mineLoading && <p role="status" className="text-xs text-slate-500">{t("lms.common.loading")}</p>}
          {!mineLoading && mine.length === 0 && <p className="text-xs text-slate-500">{t("bank.image.noImages")}</p>}
          <ul className="grid grid-cols-3 gap-2 sm:grid-cols-6">
            {mine.map((a) => (
              <li key={a.id} className="group relative">
                <button type="button" onClick={() => { pick(a); setShowMine(false); }} className="block w-full" aria-label={a.original_filename || t("bank.image.choose")}>
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={a.url || ""} alt="" className="h-16 w-full rounded-lg border border-slate-200 object-contain" />
                </button>
                <button type="button" onClick={() => void removeFromLibrary(a)} aria-label={t("bank.image.deleteFromLibrary")}
                  className="absolute right-0.5 top-0.5 hidden rounded-full bg-white/90 p-0.5 text-slate-500 hover:text-red-600 group-hover:block group-focus-within:block">
                  <X className="h-3 w-3" aria-hidden="true" />
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
