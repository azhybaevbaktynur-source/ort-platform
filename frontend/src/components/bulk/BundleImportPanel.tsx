"use client";

import React, { useState } from "react";
import Link from "next/link";
import { AlertCircle, AlertTriangle, CheckCircle2, ImageIcon, PackageCheck, RefreshCw } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { getAuthHeader } from "@/lib/api";

interface BundleIssue {
  severity: "error" | "warning";
  code: string;
  message: string;
  bundle?: string | null;
  file?: string | null;
  row?: number | null;
  column?: string | null;
  params?: Record<string, unknown>;
}

interface BundleSummary {
  root: string;
  sourceId?: string | null;
  hasManifest: boolean;
  language: string;
  examSetId: string;
  examSetTitle: string;
  examSetExists: boolean;
  questionCount: number;
  sections: Record<string, number>;
  created: Record<string, number>;
  updated: Record<string, number>;
  images: number;
}

interface BundleImportReport {
  ok: boolean;
  committed: boolean;
  bundles: BundleSummary[];
  errors: BundleIssue[];
  warnings: BundleIssue[];
  imagesTotal: number;
  imagesNew: number;
  imagesExisting: number;
}

interface BundleImportPanelProps {
  file: File;
  /** Used only for bundles without manifest.json */
  language: "ky" | "ru";
  onReset: () => void;
}

async function postBundle(endpoint: string, file: File, language: string): Promise<BundleImportReport> {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("language", language);
  const res = await fetch(endpoint, { method: "POST", headers: await getAuthHeader(), body: formData });
  if (!res.ok) {
    let msg = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      msg = typeof body.detail === "string" ? body.detail : msg;
    } catch {
      // ignore
    }
    throw new Error(msg);
  }
  return res.json();
}

export const BundleImportPanel: React.FC<BundleImportPanelProps> = ({ file, language, onReset }) => {
  const { lang, t } = useTranslation();
  const [preview, setPreview] = useState<BundleImportReport | null>(null);
  const [result, setResult] = useState<BundleImportReport | null>(null);
  const [busy, setBusy] = useState<"validate" | "import" | null>(null);
  const [requestError, setRequestError] = useState<string | null>(null);

  const issueText = (issue: BundleIssue) => {
    const key = `bundleImport.errors.${issue.code}`;
    const params = Object.fromEntries(
      Object.entries(issue.params || {}).map(([k, v]) => [k, Array.isArray(v) ? v.join(", ") : String(v ?? "")])
    );
    const translated = t(key, params);
    // No translation (e.g. row validation messages from the CSV validator) or missing params: show the server text
    return translated === key || /\{\w+\}/.test(translated) ? issue.message : translated;
  };

  const run = async (kind: "validate" | "import") => {
    setBusy(kind);
    setRequestError(null);
    try {
      const report = await postBundle(
        kind === "validate" ? "/api/v1/bulk/validate-bundle" : "/api/v1/bulk/import-bundle",
        file,
        language
      );
      if (kind === "validate") {
        setPreview(report);
        setResult(null);
      } else {
        setResult(report);
        if (!report.committed) setPreview(report);
      }
    } catch (err: unknown) {
      setRequestError(t("bundleImport.requestFailed", { message: err instanceof Error ? err.message : String(err) }));
    } finally {
      setBusy(null);
    }
  };

  const sectionName = (sec: string) => {
    const label = t(`sections.${sec}`);
    return label === `sections.${sec}` ? sec : label;
  };

  const totalQuestions = (report: BundleImportReport) => report.bundles.reduce((n, b) => n + b.questionCount, 0);

  const renderIssues = (issues: BundleIssue[], kind: "error" | "warning") => {
    if (issues.length === 0) return null;
    const isError = kind === "error";
    return (
      <div
        className={`rounded-2xl border text-xs ${
          isError ? "bg-rose-50 border-rose-200 text-rose-900" : "bg-amber-50 border-amber-200 text-amber-900"
        }`}
      >
        <div className="flex items-center gap-2 px-4 pt-3 font-bold">
          {isError ? <AlertCircle className="w-4 h-4" /> : <AlertTriangle className="w-4 h-4" />}
          {t(isError ? "bundleImport.errorsHeading" : "bundleImport.warningsHeading", { count: issues.length })}
        </div>
        <div className="max-h-72 overflow-auto px-4 pb-3 pt-2">
          <table className="w-full text-left">
            <thead>
              <tr className="opacity-70">
                <th className="py-1 pr-3 font-semibold whitespace-nowrap">{t("bundleImport.row")}</th>
                <th className="py-1 pr-3 font-semibold whitespace-nowrap">{t("bundleImport.column")}</th>
                <th className="py-1 pr-3 font-semibold whitespace-nowrap">{t("bundleImport.file")}</th>
                <th className="py-1 font-semibold">{t("bundleImport.message")}</th>
              </tr>
            </thead>
            <tbody>
              {issues.map((issue, idx) => (
                <tr key={idx} className="align-top border-t border-black/5">
                  <td className="py-1 pr-3 font-mono">{issue.row ?? "—"}</td>
                  <td className="py-1 pr-3 font-mono">{issue.column ?? "—"}</td>
                  <td className="py-1 pr-3 font-mono break-all">{issue.file ?? issue.bundle ?? "—"}</td>
                  <td className="py-1">{issueText(issue)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    );
  };

  const renderBundles = (report: BundleImportReport, done: boolean) => (
    <div className="space-y-3">
      {report.bundles.map((b) => {
        const sections = Object.keys(b.sections);
        return (
          <div key={b.root + b.examSetId} className="p-4 bg-slate-50 rounded-2xl border border-slate-200 space-y-3">
            <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-slate-700">
              <span>
                <strong>{t("bundleImport.source")}:</strong>{" "}
                <span className="font-mono">{b.sourceId || t("bundleImport.noManifest")}</span> ({b.language.toUpperCase()})
              </span>
              <span>
                <strong>{t("bundleImport.folder")}:</strong> <span className="font-mono">{b.root}</span>
              </span>
              <span>
                <strong>{t("bundleImport.examSet")}:</strong> <span className="font-mono">{b.examSetId}</span>{" "}
                {!done && (
                  <span className="text-slate-500">
                    ({t(b.examSetExists ? "bundleImport.examSetExisting" : "bundleImport.examSetNew")})
                  </span>
                )}
              </span>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-xs text-left">
                <thead>
                  <tr className="text-slate-500">
                    <th className="py-1 pr-3 font-semibold">{t("bundleImport.section")}</th>
                    <th className="py-1 pr-3 font-semibold text-right">{t("bundleImport.total")}</th>
                    <th className="py-1 pr-3 font-semibold text-right">
                      {t(done ? "bundleImport.created" : "bundleImport.toCreate")}
                    </th>
                    <th className="py-1 font-semibold text-right">
                      {t(done ? "bundleImport.updated" : "bundleImport.toUpdate")}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {sections.map((sec) => (
                    <tr key={sec} className="border-t border-slate-200">
                      <td className="py-1 pr-3 text-slate-800">{sectionName(sec)}</td>
                      <td className="py-1 pr-3 text-right font-mono">{b.sections[sec]}</td>
                      <td className="py-1 pr-3 text-right font-mono text-emerald-700">{b.created[sec] || 0}</td>
                      <td className="py-1 text-right font-mono text-indigo-700">{b.updated[sec] || 0}</td>
                    </tr>
                  ))}
                  <tr className="border-t border-slate-300 font-bold">
                    <td className="py-1 pr-3">{t("bundleImport.total")}</td>
                    <td className="py-1 pr-3 text-right font-mono">{b.questionCount}</td>
                    <td className="py-1 pr-3 text-right font-mono text-emerald-700">
                      {Object.values(b.created).reduce((a, n) => a + n, 0)}
                    </td>
                    <td className="py-1 text-right font-mono text-indigo-700">
                      {Object.values(b.updated).reduce((a, n) => a + n, 0)}
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
            {done && (
              <Link
                href={`/${lang}/exams/${b.examSetId}`}
                className="inline-block px-4 py-2 bg-emerald-600 text-white rounded-xl text-xs font-semibold hover:bg-emerald-700 transition"
              >
                {t("bundleImport.openExam")}
              </Link>
            )}
          </div>
        );
      })}
      <div className="flex items-center gap-2 text-xs text-slate-600">
        <ImageIcon className="w-4 h-4" />
        {t(done ? "bundleImport.imagesDone" : "bundleImport.images", {
          total: report.imagesTotal,
          new: report.imagesNew,
          existing: report.imagesExisting,
        })}
      </div>
    </div>
  );

  if (result && result.committed) {
    return (
      <div className="space-y-4">
        <div className="p-5 bg-emerald-50 rounded-2xl border border-emerald-200 flex items-center gap-3">
          <CheckCircle2 className="w-8 h-8 text-emerald-600 flex-shrink-0" />
          <h4 className="font-bold text-slate-900 text-base">{t("bundleImport.doneTitle")}</h4>
        </div>
        {renderBundles(result, true)}
        {renderIssues(result.warnings, "warning")}
        <button
          type="button"
          onClick={onReset}
          className="px-4 py-2 bg-white text-slate-700 border border-slate-200 rounded-xl text-xs font-semibold hover:bg-slate-50 transition"
        >
          {t("bundleImport.reset")}
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {!preview && (
        <button
          type="button"
          onClick={() => run("validate")}
          disabled={busy !== null}
          className="w-full py-3 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl text-sm font-semibold shadow-sm transition flex items-center justify-center gap-2 disabled:opacity-50"
        >
          {busy === "validate" ? <RefreshCw className="w-4 h-4 animate-spin" /> : <PackageCheck className="w-4 h-4" />}
          <span>{t(busy === "validate" ? "bundleImport.validating" : "bundleImport.validate")}</span>
        </button>
      )}

      {requestError && (
        <div className="p-3 bg-rose-50 border border-rose-200 rounded-xl text-xs text-rose-800">{requestError}</div>
      )}

      {preview && (
        <div className="space-y-4">
          {result && !result.committed && (
            <div className="p-3 bg-rose-50 border border-rose-200 rounded-xl text-sm font-bold text-rose-800">
              {t("bundleImport.failedTitle")}
            </div>
          )}
          <div
            className={`p-4 rounded-2xl border flex items-center gap-2 text-sm font-bold ${
              preview.ok ? "bg-emerald-50 border-emerald-200 text-emerald-800" : "bg-rose-50 border-rose-200 text-rose-800"
            }`}
          >
            {preview.ok ? <CheckCircle2 className="w-5 h-5" /> : <AlertCircle className="w-5 h-5" />}
            {preview.ok ? t("bundleImport.okTitle") : t("bundleImport.errorTitle", { count: preview.errors.length })}
          </div>
          {preview.bundles.length > 0 && renderBundles(preview, false)}
          {renderIssues(preview.errors, "error")}
          {renderIssues(preview.warnings, "warning")}
          {(preview.errors.length > 0 || preview.warnings.length > 0) && (
            <p className="text-[11px] text-slate-500">{t("bundleImport.rowHint")}</p>
          )}

          <div className="flex flex-col sm:flex-row gap-2">
            <button
              type="button"
              onClick={() => run("import")}
              disabled={!preview.ok || busy !== null}
              className="flex-1 py-3 bg-emerald-600 hover:bg-emerald-700 text-white rounded-xl text-sm font-semibold shadow-sm transition flex items-center justify-center gap-2 disabled:opacity-50"
            >
              {busy === "import" && <RefreshCw className="w-4 h-4 animate-spin" />}
              <span>
                {busy === "import"
                  ? t("bundleImport.importing")
                  : t("bundleImport.confirm", { count: totalQuestions(preview) })}
              </span>
            </button>
            <button
              type="button"
              onClick={onReset}
              disabled={busy !== null}
              className="py-3 px-4 bg-white text-slate-700 border border-slate-200 rounded-xl text-sm font-semibold hover:bg-slate-50 transition disabled:opacity-50"
            >
              {t("bundleImport.reset")}
            </button>
          </div>
        </div>
      )}
    </div>
  );
};
